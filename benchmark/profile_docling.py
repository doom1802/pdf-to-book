#!/usr/bin/env python3
"""Profile Docling model loading and PDF conversion without changing output.

The process is sampled continuously because ``resource.ru_maxrss`` only reports
one high-water mark.  Timed wrappers add attribution for model initialization
and the threaded pipeline stages; overlapping spans are reported as such.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import wraps
import gc
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import resource
import sys
import tempfile
import threading
from time import perf_counter
from typing import Any, Iterator

import psutil


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FIXED_MODIFIED = datetime(2026, 1, 1, tzinfo=timezone.utc)


def mb(value: int | float) -> float:
    return round(value / (1024 * 1024), 3)


@dataclass
class ResourceProfiler:
    interval_seconds: float
    started: float = field(default_factory=perf_counter)
    samples: list[dict[str, Any]] = field(default_factory=list)
    spans: list[dict[str, Any]] = field(default_factory=list)
    checkpoints: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.process = psutil.Process()
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._sample_loop, daemon=True)
        self.next_span_id = 0

    def now(self) -> float:
        return perf_counter() - self.started

    def _memory(self, full: bool = False) -> dict[str, Any]:
        info = self.process.memory_info()
        cpu = self.process.cpu_times()
        result: dict[str, Any] = {
            "rss_mb": mb(info.rss),
            "vms_mb": mb(info.vms),
            "threads": self.process.num_threads(),
            "cpu_user_seconds": round(cpu.user, 6),
            "cpu_system_seconds": round(cpu.system, 6),
        }
        if full:
            try:
                extended = self.process.memory_full_info()
                for name in ("uss", "pss", "swap"):
                    if hasattr(extended, name):
                        result[f"{name}_mb"] = mb(getattr(extended, name))
            except (psutil.AccessDenied, AttributeError, NotImplementedError):
                pass
            system_memory = psutil.virtual_memory()
            result["system_available_mb"] = mb(system_memory.available)
            try:
                io = self.process.io_counters()
                result["read_bytes"] = io.read_bytes
                result["write_bytes"] = io.write_bytes
            except (psutil.AccessDenied, AttributeError, NotImplementedError):
                pass
        torch = sys.modules.get("torch")
        if torch is not None and hasattr(torch, "backends") and hasattr(torch, "mps"):
            try:
                if torch.backends.mps.is_available():
                    result["mps_allocated_mb"] = mb(
                        torch.mps.current_allocated_memory()
                    )
                    result["mps_driver_mb"] = mb(torch.mps.driver_allocated_memory())
            except RuntimeError:
                pass
        return result

    def _sample_loop(self) -> None:
        deadline = perf_counter()
        while not self.stop_event.is_set():
            sample = {"at_seconds": round(self.now(), 6), **self._memory()}
            with self.lock:
                self.samples.append(sample)
            deadline += self.interval_seconds
            self.stop_event.wait(max(0.0, deadline - perf_counter()))

    def start(self) -> None:
        self.thread.start()
        self.checkpoint("process_started", full=True)

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join()
        self.checkpoint("process_finished", full=True)

    def checkpoint(
        self, name: str, *, full: bool = False, **metadata: Any
    ) -> dict[str, Any]:
        point = {
            "name": name,
            "at_seconds": round(self.now(), 6),
            **self._memory(full=full),
            **metadata,
        }
        with self.lock:
            self.checkpoints.append(point)
        return point

    @contextmanager
    def span(self, name: str, **metadata: Any) -> Iterator[None]:
        with self.lock:
            span_id = self.next_span_id
            self.next_span_id += 1
        start = self.checkpoint(f"{name}.start")
        started = self.now()
        try:
            yield
        finally:
            ended = self.now()
            end = self.checkpoint(f"{name}.end")
            with self.lock:
                relevant = [
                    sample
                    for sample in self.samples
                    if started <= sample["at_seconds"] <= ended
                ]
            peak = max(
                [start["rss_mb"], end["rss_mb"]]
                + [sample["rss_mb"] for sample in relevant]
            )
            self.spans.append(
                {
                    "id": span_id,
                    "name": name,
                    "thread": threading.current_thread().name,
                    "start_seconds": round(started, 6),
                    "end_seconds": round(ended, 6),
                    "duration_seconds": round(ended - started, 6),
                    "rss_start_mb": start["rss_mb"],
                    "rss_end_mb": end["rss_mb"],
                    "rss_delta_mb": round(end["rss_mb"] - start["rss_mb"], 3),
                    "cpu_user_seconds": round(
                        end["cpu_user_seconds"] - start["cpu_user_seconds"], 6
                    ),
                    "cpu_system_seconds": round(
                        end["cpu_system_seconds"] - start["cpu_system_seconds"], 6
                    ),
                    "peak_rss_mb": peak,
                    "peak_above_start_mb": round(peak - start["rss_mb"], 3),
                    **metadata,
                }
            )

    def report(self) -> dict[str, Any]:
        with self.lock:
            samples = list(self.samples)
            spans = sorted(self.spans, key=lambda value: value["start_seconds"])
            checkpoints = list(self.checkpoints)
        grouped: dict[str, dict[str, Any]] = {}
        for span in spans:
            aggregate = grouped.setdefault(
                span["name"],
                {
                    "calls": 0,
                    "total_seconds": 0.0,
                    "maximum_call_seconds": 0.0,
                    "maximum_peak_rss_mb": 0.0,
                    "maximum_peak_above_start_mb": 0.0,
                },
            )
            aggregate["calls"] += 1
            aggregate["total_seconds"] += span["duration_seconds"]
            aggregate["maximum_call_seconds"] = max(
                aggregate["maximum_call_seconds"], span["duration_seconds"]
            )
            aggregate["maximum_peak_rss_mb"] = max(
                aggregate["maximum_peak_rss_mb"], span["peak_rss_mb"]
            )
            aggregate["maximum_peak_above_start_mb"] = max(
                aggregate["maximum_peak_above_start_mb"],
                span["peak_above_start_mb"],
            )
        for aggregate in grouped.values():
            aggregate["total_seconds"] = round(aggregate["total_seconds"], 6)
        peak_sample = max(samples, key=lambda sample: sample["rss_mb"])
        ru_maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        ru_maxrss_mb = mb(ru_maxrss if sys.platform != "darwin" else ru_maxrss)
        # Linux reports KiB while Darwin reports bytes.
        if sys.platform != "darwin":
            ru_maxrss_mb = round(ru_maxrss / 1024, 3)
        return {
            "sample_interval_seconds": self.interval_seconds,
            "sample_count": len(samples),
            "peak": peak_sample,
            "ru_maxrss_mb": ru_maxrss_mb,
            "aggregates": grouped,
            "spans": spans,
            "checkpoints": checkpoints,
            "samples": samples,
        }


def timed_method(
    profiler: ResourceProfiler,
    cls: type,
    method_name: str,
    label: str,
    *,
    iterable: bool = False,
    batch_argument: int | None = None,
) -> None:
    original = getattr(cls, method_name)

    def metadata(args: tuple[Any, ...]) -> dict[str, Any]:
        if batch_argument is None or len(args) <= batch_argument:
            return {}
        try:
            items = args[batch_argument]
            result: dict[str, Any] = {"batch_items": len(items)}
            images = [getattr(item, "image", None) for item in items]
            images = [image for image in images if image is not None]
            if images:
                result["batch_megapixels"] = round(
                    sum(image.width * image.height for image in images) / 1_000_000,
                    3,
                )
                result["image_sizes"] = [
                    [image.width, image.height] for image in images
                ]
            return result
        except TypeError:
            return {}

    if iterable:
        @wraps(original)
        def wrapped_iterable(*args: Any, **kwargs: Any):
            result = original(*args, **kwargs)

            def measured():
                with profiler.span(label, **metadata(args)):
                    yield from result

            return measured()

        setattr(cls, method_name, wrapped_iterable)
    else:
        @wraps(original)
        def wrapped(*args: Any, **kwargs: Any):
            with profiler.span(label, **metadata(args)):
                return original(*args, **kwargs)

        setattr(cls, method_name, wrapped)


def package_versions(names: list[str]) -> dict[str, str | None]:
    values: dict[str, str | None] = {}
    for name in names:
        try:
            values[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            values[name] = None
    return values


def tree_metrics(path: Path) -> dict[str, int]:
    files = [item for item in path.rglob("*") if item.is_file()]
    return {
        "files": len(files),
        "bytes": sum(item.stat().st_size for item in files),
        "png_files": sum(item.suffix.lower() == ".png" for item in files),
        "png_bytes": sum(
            item.stat().st_size for item in files if item.suffix.lower() == ".png"
        ),
    }


def parse_pages(value: str) -> tuple[int, int]:
    try:
        start, end = (int(part) for part in value.split("-", 1))
    except ValueError as error:
        raise argparse.ArgumentTypeError("pages must be START-END") from error
    if start < 1 or end < start:
        raise argparse.ArgumentTypeError("pages must be a positive ordered range")
    return start, end


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, action="append", required=True)
    parser.add_argument("--pages", type=parse_pages, required=True)
    parser.add_argument("--device", choices=["auto", "cpu", "mps", "cuda"], default="cpu")
    parser.add_argument("--layout-batch-size", type=int, default=4)
    parser.add_argument("--table-batch-size", type=int, default=4)
    parser.add_argument("--queue-size", type=int, default=100)
    parser.add_argument("--sample-interval-ms", type=float, default=10.0)
    parser.add_argument("--no-tables", action="store_true")
    parser.add_argument("--no-page-images", action="store_true")
    parser.add_argument(
        "--retain-results",
        action="store_true",
        help="Retain every converted document before export (diagnostic anti-pattern)",
    )
    parser.add_argument("--quality-baseline", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for source in args.source:
        if not source.is_file():
            raise FileNotFoundError(source)
    if min(args.layout_batch_size, args.table_batch_size, args.queue_size) < 1:
        raise ValueError("batch and queue sizes must be positive")
    if args.sample_interval_ms <= 0:
        raise ValueError("sample interval must be positive")
    if args.quality_baseline and len(args.source) != 1:
        raise ValueError("the exact quality gate currently describes one source")

    os.environ.setdefault("HF_HOME", str(ROOT / "benchmark/cache/huggingface"))
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    profiler = ResourceProfiler(args.sample_interval_ms / 1000)
    profiler.start()

    with profiler.span("imports.docling_and_project"):
        from docling.datamodel.accelerator_options import AcceleratorOptions
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.models.inference_engines.object_detection.transformers_engine import (
            TransformersObjectDetectionEngine,
        )
        from docling.models.stages.layout.layout_object_detection_model import (
            LayoutObjectDetectionModel,
        )
        from docling.models.stages.layout.layout_postprocessing_model import (
            LayoutPostprocessingModel,
        )
        from docling.models.stages.page_assemble.page_assemble_model import (
            PageAssembleModel,
        )
        from docling.models.stages.page_preprocessing.page_preprocessing_model import (
            PagePreprocessingModel,
        )
        from docling.models.stages.table_structure.table_structure_model import (
            TableStructureModel,
        )
        from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline
        from docling_core.types.doc import ImageRefMode
        from pdf_to_book.docling_adapter import adapt
        from pdf_to_book.cover import add_pdf_cover
        from pdf_to_book.epub import CSS, render_content, render_nav, write_epub
        from pdf_to_book.quality import quality_report
        from pdf_to_book.validate import validate

    timed_method(
        profiler,
        TransformersObjectDetectionEngine,
        "initialize",
        "model_init.layout_transformers",
    )
    timed_method(
        profiler,
        TableStructureModel,
        "__init__",
        "model_init.tableformer",
    )
    timed_method(
        profiler,
        StandardPdfPipeline,
        "_init_models",
        "model_init.all_pipeline_models",
    )
    timed_method(
        profiler,
        PagePreprocessingModel,
        "__call__",
        "stage.page_preprocessing",
        iterable=True,
    )
    timed_method(
        profiler,
        LayoutObjectDetectionModel,
        "predict_layout",
        "stage.layout_total",
        batch_argument=2,
    )
    timed_method(
        profiler,
        TransformersObjectDetectionEngine,
        "predict_batch",
        "stage.layout_inference",
        batch_argument=1,
    )
    timed_method(
        profiler,
        LayoutPostprocessingModel,
        "__call__",
        "stage.layout_postprocessing",
        iterable=True,
    )
    timed_method(
        profiler,
        TableStructureModel,
        "predict_tables",
        "stage.table_structure",
        batch_argument=2,
    )
    timed_method(
        profiler,
        PageAssembleModel,
        "__call__",
        "stage.page_assemble",
        iterable=True,
    )

    with profiler.span("configuration"):
        pipeline_options = PdfPipelineOptions(
            accelerator_options=AcceleratorOptions(device=args.device),
            do_ocr=False,
            do_table_structure=not args.no_tables,
        )
        pipeline_options.table_structure_options.mode = TableFormerMode.FAST
        pipeline_options.table_structure_options.do_cell_matching = True
        pipeline_options.generate_page_images = not args.no_page_images
        pipeline_options.generate_picture_images = True
        pipeline_options.images_scale = 2
        pipeline_options.layout_batch_size = args.layout_batch_size
        pipeline_options.table_batch_size = args.table_batch_size
        pipeline_options.queue_max_size = args.queue_size
        converter = DocumentConverter(
            allowed_formats=[InputFormat.PDF],
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            },
        )

    with profiler.span("pipeline.initialize"):
        converter.initialize_pipeline(InputFormat.PDF)

    torch = sys.modules.get("torch")
    profiler.checkpoint(
        "pipeline_initialized",
        full=True,
        mps_available=bool(torch and torch.backends.mps.is_available()),
    )

    artifact_metrics: dict[str, int] = {}
    with tempfile.TemporaryDirectory(prefix="pdf-to-book-profile-") as temporary:
        directory = Path(temporary)
        quality_reports = []

        def export_and_adapt(index: int, source: Path, result: Any) -> None:
            target = directory / f"docling-{index}" / f"{result.input.file.stem}.json"
            target.parent.mkdir(parents=True)
            with profiler.span("docling.export_json", document=index):
                result.document.save_as_json(
                    filename=target,
                    image_mode=ImageRefMode.REFERENCED,
                )
            with profiler.span("project.adapt_and_epub", document=index):
                work = directory / f"book-{index}"
                book = adapt(
                    target,
                    source,
                    "Clean Code — Meaningful Names" if args.quality_baseline else source.stem,
                    "Robert C. Martin; chapter by Tim Ottinger" if args.quality_baseline else "",
                    "en",
                    work / "assets",
                )
                add_pdf_cover(book, source, work / "assets")
                book["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
                output = directory / f"book-{index}.epub"
                write_epub(book, work, output, modified=FIXED_MODIFIED)
                validation = validate(output)
                if not validation["valid"]:
                    raise RuntimeError(validation["errors"])
                quality_reports.append(
                    quality_report(
                        book,
                        stylesheet=CSS,
                        content_xhtml=render_content(book),
                        navigation_xhtml=render_nav(book),
                    )
                )

        if args.retain_results:
            with profiler.span("pipeline.convert_all", documents=len(args.source)):
                results = list(converter.convert_all(args.source, page_range=args.pages))
            for index, (source, result) in enumerate(zip(args.source, results)):
                export_and_adapt(index, source, result)
        else:
            iterator = converter.convert_all(args.source, page_range=args.pages)
            with profiler.span("pipeline.stream_all", documents=len(args.source)):
                for index, source in enumerate(args.source):
                    with profiler.span("pipeline.next_document", document=index):
                        result = next(iterator)
                    export_and_adapt(index, source, result)
                    del result
                    gc.collect()

        artifact_metrics = tree_metrics(directory)

        if args.quality_baseline:
            expected = json.loads(args.quality_baseline.read_text())["report"]
            if quality_reports[0] != expected:
                raise RuntimeError(
                    "quality changed: "
                    f"{quality_reports[0]['quality_sha256']} != {expected['quality_sha256']}"
                )

        if args.retain_results:
            del results
        gc.collect()
        profiler.checkpoint("after_results_released", full=True)

    profiler.stop()
    payload = {
        "profile_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "packages": package_versions(
                [
                    "docling",
                    "docling-core",
                    "docling-parse",
                    "torch",
                    "transformers",
                    "safetensors",
                    "pypdfium2",
                    "psutil",
                ]
            ),
        },
        "configuration": {
            "sources": [str(source.resolve()) for source in args.source],
            "pages": list(args.pages),
            "device_requested": args.device,
            "tables_enabled": not args.no_tables,
            "page_images_enabled": not args.no_page_images,
            "retain_results": args.retain_results,
            "layout_batch_size": args.layout_batch_size,
            "table_batch_size": args.table_batch_size,
            "queue_size": args.queue_size,
        },
        "quality_sha256": [report["quality_sha256"] for report in quality_reports],
        "temporary_artifacts": artifact_metrics,
        "resources": profiler.report(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    summary = {
        "output": str(args.output),
        "peak_rss_mb": payload["resources"]["peak"]["rss_mb"],
        "ru_maxrss_mb": payload["resources"]["ru_maxrss_mb"],
        "elapsed_seconds": payload["resources"]["checkpoints"][-1]["at_seconds"],
        "quality_sha256": payload["quality_sha256"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
