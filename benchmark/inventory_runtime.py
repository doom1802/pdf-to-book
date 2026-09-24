#!/usr/bin/env python3
"""Inventory the installed runtime and model cache by actual file size."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]


def unique_file_metrics(paths: Iterable[Path], *, follow_symlinks: bool) -> dict[str, int]:
    logical_bytes = 0
    allocated_bytes = 0
    file_count = 0
    seen: set[tuple[int, int]] = set()
    for path in paths:
        try:
            stat = path.stat() if follow_symlinks else path.lstat()
        except FileNotFoundError:
            continue
        if not path.is_file():
            continue
        key = (stat.st_dev, stat.st_ino)
        if key in seen:
            continue
        seen.add(key)
        file_count += 1
        logical_bytes += stat.st_size
        allocated_bytes += getattr(stat, "st_blocks", 0) * 512
    return {
        "files": file_count,
        "logical_bytes": logical_bytes,
        "allocated_bytes": allocated_bytes,
    }


def tree_files(root: Path) -> Iterable[Path]:
    for directory, _, filenames in os.walk(root, followlinks=False):
        base = Path(directory)
        for filename in filenames:
            yield base / filename


def distribution_metrics() -> list[dict[str, object]]:
    rows = []
    for distribution in importlib.metadata.distributions():
        paths = []
        for relative in distribution.files or []:
            path = Path(distribution.locate_file(relative))
            if path.is_file():
                paths.append(path)
        metrics = unique_file_metrics(paths, follow_symlinks=True)
        rows.append(
            {
                "name": distribution.metadata.get("Name", "unknown"),
                "version": distribution.version,
                **metrics,
            }
        )
    rows.sort(key=lambda row: int(row["logical_bytes"]), reverse=True)
    return rows


def model_repositories(cache: Path) -> list[dict[str, object]]:
    rows = []
    hub = cache / "hub"
    for repository in sorted(hub.glob("models--*")):
        snapshots = repository / "snapshots"
        metrics = unique_file_metrics(tree_files(snapshots), follow_symlinks=True)
        rows.append({"repository": repository.name, **metrics})
    rows.sort(key=lambda row: int(row["logical_bytes"]), reverse=True)
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache",
        type=Path,
        default=ROOT / "benchmark/cache/huggingface",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    environment = Path(sys.prefix)
    env_metrics = unique_file_metrics(tree_files(environment), follow_symlinks=False)
    cache_metrics = unique_file_metrics(tree_files(args.cache), follow_symlinks=False)
    payload = {
        "inventory_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "prefix": str(environment),
            **env_metrics,
        },
        "model_cache": {
            "path": str(args.cache.resolve()),
            **cache_metrics,
            "repositories": model_repositories(args.cache),
        },
        "distributions": distribution_metrics(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "environment_logical_mb": round(env_metrics["logical_bytes"] / 2**20, 2),
                "model_cache_logical_mb": round(cache_metrics["logical_bytes"] / 2**20, 2),
                "distributions": len(payload["distributions"]),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
