#!/usr/bin/env python3
"""Measure isolated pipeline stages while enforcing the semantic quality contract."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
from statistics import median
import subprocess
import sys
import tempfile
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pdf_to_book.docling_adapter import adapt  # noqa: E402
from pdf_to_book.cover import add_pdf_cover  # noqa: E402
from pdf_to_book.epub import CSS, render_content, render_nav, write_epub  # noqa: E402
from pdf_to_book.quality import quality_report  # noqa: E402
from pdf_to_book.validate import validate  # noqa: E402

FIXED_MODIFIED = datetime(2026, 1, 1, tzinfo=timezone.utc)


def peak_rss_mb(who: int) -> float:
    value = resource.getrusage(who).ru_maxrss
    divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
    return round(value / divisor, 2)


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--docling-json", type=Path, required=True)
    parser.add_argument("--pages", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--author", required=True)
    parser.add_argument("--language", default="en")
    parser.add_argument("--device", default="cpu")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common(parser)
    parser.add_argument("--stage", choices=["epub", "full"], default="epub")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--quality-baseline", type=Path)
    parser.add_argument("--performance-baseline", type=Path)
    parser.add_argument("--max-time-regression", type=float, default=0.10)
    parser.add_argument("--max-memory-regression", type=float, default=0.10)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--run-directory", type=Path, help=argparse.SUPPRESS)
    return parser.parse_args()


def attach_source_hash(book: dict, source: Path) -> None:
    book["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()


def run_epub_worker(args: argparse.Namespace) -> dict:
    started = perf_counter()
    work = args.run_directory / "book"
    book = adapt(
        args.docling_json,
        args.source,
        args.title,
        args.author,
        args.language,
        work / "assets",
    )
    add_pdf_cover(book, args.source, work / "assets")
    attach_source_hash(book, args.source)
    write_epub(book, work, args.run_directory / "book.epub", modified=FIXED_MODIFIED)
    validation = validate(args.run_directory / "book.epub")
    elapsed = perf_counter() - started
    if not validation["valid"]:
        raise RuntimeError(validation["errors"])
    return {
        "seconds": round(elapsed, 6),
        "peak_rss_mb": peak_rss_mb(resource.RUSAGE_SELF),
        "quality": quality_report(
            book, stylesheet=CSS,
            content_xhtml=render_content(book), navigation_xhtml=render_nav(book),
        ),
    }


def run_full_worker(args: argparse.Namespace) -> dict:
    output = args.run_directory / "book.epub"
    environment = os.environ.copy()
    environment["SOURCE_DATE_EPOCH"] = str(int(FIXED_MODIFIED.timestamp()))
    environment.setdefault("HF_HOME", str(ROOT / "benchmark/cache/huggingface"))
    environment.setdefault("HF_HUB_OFFLINE", "1")
    command = [
        sys.executable, "-m", "pdf_to_book", str(args.source),
        "--pages", args.pages, "--title", args.title, "--author", args.author,
        "--language", args.language, "--device", args.device, "--output", str(output),
    ]
    started = perf_counter()
    completed = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True)
    elapsed = perf_counter() - started
    if completed.returncode:
        raise RuntimeError(completed.stdout + completed.stderr)
    book = json.loads(output.with_suffix("").joinpath("book.json").read_text())
    return {
        "seconds": round(elapsed, 6),
        "peak_rss_mb": peak_rss_mb(resource.RUSAGE_CHILDREN),
        "quality": quality_report(
            book, stylesheet=CSS,
            content_xhtml=render_content(book), navigation_xhtml=render_nav(book),
        ),
    }


def worker(args: argparse.Namespace) -> int:
    result = run_epub_worker(args) if args.stage == "epub" else run_full_worker(args)
    print(json.dumps(result, ensure_ascii=False))
    return 0


def worker_command(args: argparse.Namespace, directory: Path) -> list[str]:
    command = [
        sys.executable, str(Path(__file__).resolve()), "--worker",
        "--stage", args.stage, "--source", str(args.source),
        "--docling-json", str(args.docling_json), "--pages", args.pages,
        "--title", args.title, "--author", args.author,
        "--language", args.language, "--device", args.device,
        "--run-directory", str(directory),
    ]
    return command


def main() -> int:
    args = parse_args()
    if args.worker:
        return worker(args)
    if args.runs < 1:
        raise ValueError("--runs must be positive")
    expected = None
    if args.quality_baseline:
        expected = json.loads(args.quality_baseline.read_text())["report"]
    runs = []
    with tempfile.TemporaryDirectory(prefix="pdf-to-book-benchmark-") as temporary:
        root = Path(temporary)
        for index in range(args.runs):
            directory = root / f"run-{index + 1}"
            directory.mkdir()
            completed = subprocess.run(worker_command(args, directory), cwd=ROOT, capture_output=True, text=True)
            if completed.returncode:
                raise RuntimeError(completed.stdout + completed.stderr)
            result = json.loads(completed.stdout)
            if expected and result["quality"] != expected:
                raise RuntimeError(
                    f"Quality changed on run {index + 1}: "
                    f"{result['quality']['quality_sha256']} != {expected['quality_sha256']}"
                )
            runs.append(result)
    times = [run["seconds"] for run in runs]
    memory = [run["peak_rss_mb"] for run in runs]
    report = {
        "benchmark_version": 1,
        "stage": args.stage,
        "runs": args.runs,
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "quality_sha256": runs[0]["quality"]["quality_sha256"],
        "seconds": {
            "median": round(median(times), 6),
            "minimum": min(times),
            "maximum": max(times),
            "values": times,
        },
        "peak_rss_mb": {
            "median": round(median(memory), 2),
            "maximum": max(memory),
            "values": memory,
        },
    }
    failed = []
    if args.performance_baseline:
        baseline = json.loads(args.performance_baseline.read_text())
        time_limit = baseline["seconds"]["median"] * (1 + args.max_time_regression)
        memory_limit = baseline["peak_rss_mb"]["median"] * (1 + args.max_memory_regression)
        report["comparison"] = {
            "baseline": str(args.performance_baseline),
            "time_limit": round(time_limit, 6),
            "memory_limit_mb": round(memory_limit, 2),
        }
        if report["seconds"]["median"] > time_limit:
            failed.append("median time exceeded baseline tolerance")
        if report["peak_rss_mb"]["median"] > memory_limit:
            failed.append("median peak RSS exceeded baseline tolerance")
    report["failures"] = failed
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload)
    print(payload, end="")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
