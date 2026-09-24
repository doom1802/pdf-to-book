#!/usr/bin/env python3
"""Run PaddleOCR-VL on a reproducible prefix of a PDF."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from pypdf import PdfReader, PdfWriter


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_pdf", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--pages", type=int, default=5)
    parser.add_argument("--device", default="cpu")
    return parser.parse_args()


def make_pdf_prefix(source: Path, destination: Path, page_count: int) -> int:
    reader = PdfReader(source)
    selected_count = min(page_count, len(reader.pages))
    writer = PdfWriter()
    for page in reader.pages[:selected_count]:
        writer.add_page(page)

    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output_file:
        writer.write(output_file)
    return selected_count


def main() -> int:
    args = parse_args()
    input_pdf = args.input_pdf.resolve()
    output_dir = args.output_dir.resolve()
    cache_dir = Path("benchmark/cache/paddlex").resolve()
    temporary_pdf = Path("tmp/pdfs") / f"{input_pdf.stem}-first-{args.pages}.pdf"

    if not input_pdf.is_file():
        print(f"Input PDF not found: {input_pdf}", file=sys.stderr)
        return 2

    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(cache_dir))
    output_dir.mkdir(parents=True, exist_ok=True)
    selected_count = make_pdf_prefix(input_pdf, temporary_pdf, args.pages)

    # Import after setting the cache location: PaddleX initializes its cache on import.
    from paddleocr import PaddleOCRVL

    started_at = time.perf_counter()
    pipeline = PaddleOCRVL(pipeline_version="v1.6", device=args.device)
    page_results = list(pipeline.predict(input=str(temporary_pdf)))
    restructured = pipeline.restructure_pages(
        page_results,
        merge_tables=True,
        relevel_titles=True,
        concatenate_pages=True,
    )
    for result in restructured:
        result.save_to_json(save_path=str(output_dir))
        result.save_to_markdown(save_path=str(output_dir))

    elapsed_seconds = time.perf_counter() - started_at
    summary = {
        "parser": "PaddleOCR-VL",
        "pipeline_version": "v1.6",
        "device": args.device,
        "input": str(input_pdf),
        "pages": selected_count,
        "page_results": len(page_results),
        "elapsed_seconds": round(elapsed_seconds, 2),
        "output_dir": str(output_dir),
    }
    (output_dir / "benchmark-summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    temporary_pdf.unlink(missing_ok=True)
    try:
        temporary_pdf.parent.rmdir()
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
