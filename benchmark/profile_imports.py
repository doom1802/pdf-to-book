#!/usr/bin/env python3
"""Measure cold-process import cost for the main runtime modules."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys


DEFAULT_MODULES = [
    "numpy",
    "PIL.Image",
    "torch",
    "transformers",
    "docling.document_converter",
    "pdf_to_book.docling_adapter",
]


WORKER = r"""
import importlib, json, resource, sys
from time import perf_counter
def rss_mb():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value / (1024 * 1024) if sys.platform == 'darwin' else value / 1024
before = rss_mb()
started = perf_counter()
importlib.import_module(sys.argv[1])
elapsed = perf_counter() - started
print(json.dumps({'seconds': elapsed, 'rss_before_mb': before,
                  'peak_rss_mb': rss_mb(), 'loaded_modules': len(sys.modules)}))
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", action="append", dest="modules")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.runs < 1:
        raise ValueError("runs must be positive")
    modules = args.modules or DEFAULT_MODULES
    measurements = {}
    for module in modules:
        runs = []
        for _ in range(args.runs):
            completed = subprocess.run(
                [sys.executable, "-c", WORKER, module],
                check=True,
                capture_output=True,
                text=True,
            )
            runs.append(json.loads(completed.stdout))
        measurements[module] = {
            "runs": runs,
            "median_seconds": round(
                statistics.median(run["seconds"] for run in runs), 6
            ),
            "median_peak_rss_mb": round(
                statistics.median(run["peak_rss_mb"] for run in runs), 3
            ),
            "median_rss_increase_mb": round(
                statistics.median(
                    run["peak_rss_mb"] - run["rss_before_mb"] for run in runs
                ),
                3,
            ),
        }
    payload = {
        "profile_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
        },
        "runs_per_module": args.runs,
        "modules": measurements,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({name: {k: v for k, v in values.items() if k != "runs"}
                      for name, values in measurements.items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
