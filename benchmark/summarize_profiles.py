#!/usr/bin/env python3
"""Consolidate the repeatable profiling scenarios into a compact report."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import median
from typing import Any


SCENARIOS = {
    "chapter_layout_batch_4": [f"current-cpu-b4-run{i}.json" for i in (2, 3, 4)],
    "chapter_layout_batch_2": [f"current-cpu-b2-run{i}.json" for i in (1, 2, 3)],
    "chapter_layout_batch_1": [f"current-cpu-b1-run{i}.json" for i in (1, 2, 3)],
    "chapter_without_tables": [f"no-tables-cpu-b4-run{i}.json" for i in (1, 2, 3)],
    "chapter_queue_4": [f"current-cpu-b4-q4-run{i}.json" for i in (1, 2, 3)],
    "three_books_layout_batch_4": [
        f"three-books-stream-cpu-b4-run{i}.json" for i in (1, 2, 3)
    ],
    "three_books_layout_batch_1": [
        f"three-books-stream-cpu-b1-run{i}.json" for i in (1, 2, 3)
    ],
}


def range_report(values: list[float]) -> dict[str, float | list[float]]:
    return {
        "median": round(median(values), 3),
        "minimum": round(min(values), 3),
        "maximum": round(max(values), 3),
        "values": values,
    }


def find_span(profile: dict[str, Any], names: set[str]) -> dict[str, Any]:
    return next(
        span for span in profile["resources"]["spans"] if span["name"] in names
    )


def checkpoint(profile: dict[str, Any], name: str) -> dict[str, Any]:
    return next(
        point
        for point in profile["resources"]["checkpoints"]
        if point["name"] == name
    )


def summarize(profiles: list[dict[str, Any]]) -> dict[str, Any]:
    peaks = [profile["resources"]["peak"]["rss_mb"] for profile in profiles]
    elapsed = [
        checkpoint(profile, "process_finished")["at_seconds"] for profile in profiles
    ]
    imports = [
        find_span(profile, {"imports.docling_and_project"})["duration_seconds"]
        for profile in profiles
    ]
    initialization = [
        find_span(profile, {"pipeline.initialize"})["duration_seconds"]
        for profile in profiles
    ]
    pipeline = [
        find_span(profile, {"pipeline.convert_all", "pipeline.stream_all"})[
            "duration_seconds"
        ]
        for profile in profiles
    ]
    initialized_rss = [
        checkpoint(profile, "pipeline_initialized")["rss_mb"] for profile in profiles
    ]
    final_rss = [
        checkpoint(profile, "after_results_released")["rss_mb"] for profile in profiles
    ]
    return {
        "runs": len(profiles),
        "configuration": profiles[0]["configuration"],
        "quality_sha256": sorted(
            {digest for profile in profiles for digest in profile["quality_sha256"]}
        ),
        "peak_rss_mb": range_report(peaks),
        "elapsed_seconds": range_report(elapsed),
        "import_seconds": range_report(imports),
        "pipeline_initialization_seconds": range_report(initialization),
        "pipeline_work_seconds": range_report(pipeline),
        "rss_after_initialization_mb": range_report(initialized_rss),
        "rss_after_results_released_mb": range_report(final_rss),
    }


def comparison(before: dict[str, Any], after: dict[str, Any]) -> dict[str, float]:
    before_peak = before["peak_rss_mb"]["median"]
    after_peak = after["peak_rss_mb"]["median"]
    before_time = before["elapsed_seconds"]["median"]
    after_time = after["elapsed_seconds"]["median"]
    return {
        "peak_rss_change_mb": round(after_peak - before_peak, 3),
        "peak_rss_change_percent": round(100 * (after_peak / before_peak - 1), 2),
        "elapsed_change_seconds": round(after_time - before_time, 3),
        "elapsed_change_percent": round(100 * (after_time / before_time - 1), 2),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", type=Path, default=Path("benchmark/profiles"))
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scenarios = {}
    for name, filenames in SCENARIOS.items():
        scenarios[name] = summarize(
            [json.loads((args.profiles / filename).read_text()) for filename in filenames]
        )
    payload = {
        "summary_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scenarios": scenarios,
        "comparisons": {
            "chapter_batch_4_to_2": comparison(
                scenarios["chapter_layout_batch_4"],
                scenarios["chapter_layout_batch_2"],
            ),
            "chapter_batch_4_to_1": comparison(
                scenarios["chapter_layout_batch_4"],
                scenarios["chapter_layout_batch_1"],
            ),
            "chapter_tables_on_to_off": comparison(
                scenarios["chapter_layout_batch_4"],
                scenarios["chapter_without_tables"],
            ),
            "chapter_queue_100_to_4": comparison(
                scenarios["chapter_layout_batch_4"],
                scenarios["chapter_queue_4"],
            ),
            "three_books_batch_4_to_1": comparison(
                scenarios["three_books_layout_batch_4"],
                scenarios["three_books_layout_batch_1"],
            ),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload["comparisons"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
