#!/usr/bin/env python3
"""Check public PDFs against visual-review annotations and built EPUBs."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from zipfile import ZipFile

import jsonschema
from PIL import Image
import pypdfium2

from pdf_to_book.docling_adapter import adapt
from pdf_to_book.epub import render_content, write_epub
from pdf_to_book.validate import validate


ROOT = Path(__file__).resolve().parent
FIXED_DATE = datetime(2020, 1, 1, tzinfo=timezone.utc)


def normalized(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip().casefold()


def semantic_fingerprint(book: dict) -> str:
    """Exact snapshot baseline without platform-sensitive raster image bytes."""
    fields = ("id", "type", "text", "level", "caption_ids", "ordered",
              "marker", "group_id", "note_refs", "joined_ids", "text_method")

    def project(block: dict) -> dict:
        value = {key: block[key] for key in fields if key in block}
        value["page"] = page_of(block)
        value["has_asset"] = bool(block.get("asset"))
        if block.get("type") == "table":
            value["cells"] = [
                {key: cell.get(key) for key in (
                    "text", "start_row_offset_idx", "start_col_offset_idx",
                    "row_span", "col_span", "row_header", "column_header")}
                for cell in block["data"]["table_cells"]
            ]
        return value

    projection = {
        "pages": book["pages"],
        "source_sha256": book["source_sha256"],
        "blocks": [project(block) for block in book["blocks"]],
        "footnotes": [project(note) for note in book["footnotes"]],
        "outline": book.get("outline", []),
    }
    payload = json.dumps(projection, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def page_of(block: dict) -> int | None:
    provenance = block.get("provenance", [])
    return provenance[0].get("page_no") if provenance else None


def selected(blocks: list[dict], *, page: int | None = None, kind: str = "*") -> list[dict]:
    return [
        block for block in blocks
        if (page is None or page_of(block) == page)
        and (kind == "*" or block["type"] == kind)
    ]


def asset_is_readable(block: dict, work: Path, *, min_width: int = 1, min_height: int = 1) -> bool:
    asset = block.get("asset")
    if not asset:
        return False
    with Image.open(work / asset) as image:
        if image.width < min_width or image.height < min_height:
            return False
        lo, hi = image.convert("L").getextrema()
        return lo < 180 and hi > 220


def check(book: dict, xhtml: str, work: Path, spec: dict) -> bool:
    kind = spec["kind"]
    page = spec.get("page")
    blocks = selected(book["blocks"], page=page, kind=spec.get("type", "*"))
    if kind == "block":
        def matches(block: dict) -> bool:
            value = block.get("text", "")
            return (
                ("text" not in spec or (
                    value == spec["text"] if block["type"] == "code"
                    else normalized(value) == normalized(spec["text"])
                ))
                and ("contains" not in spec or normalized(spec["contains"]) in normalized(value))
                and ("level" not in spec or block.get("level") == spec["level"])
            )
        return any(matches(block) for block in blocks)
    if kind == "count":
        return len(blocks) >= spec["minimum"]
    if kind == "table_cell":
        return any(
            normalized(cell.get("text", "")) == normalized(spec["text"])
            and ("col_span" not in spec or cell.get("col_span") == spec["col_span"])
            for block in selected(book["blocks"], page=page, kind="table")
            for cell in block.get("data", {}).get("table_cells", [])
        )
    if kind == "figure_with_caption":
        by_id = {block["id"]: block for block in book["blocks"]}
        return any(
            asset_is_readable(block, work, min_width=spec.get("min_width", 1))
            and any(
                normalized(spec["caption"]) in normalized(by_id[caption]["text"])
                for caption in block.get("caption_ids", []) if caption in by_id
            )
            for block in selected(book["blocks"], page=page, kind="figure")
        )
    if kind == "footnote":
        return any(
            normalized(spec["contains"]) in normalized(note.get("text", ""))
            for note in selected(book["footnotes"], page=page)
        )
    if kind == "order":
        positions = []
        for text in spec["texts"]:
            match = next((index for index, block in enumerate(book["blocks"])
                          if (page is None or page_of(block) == page)
                          and normalized(text) in normalized(block.get("text", ""))), None)
            if match is None:
                return False
            positions.append(match)
        return positions == sorted(set(positions))
    if kind == "epub_contains":
        return spec["text"] in xhtml
    if kind == "epub_excludes":
        return spec["text"] not in xhtml
    if kind == "index_image":
        return any(
            asset_is_readable(block, work, min_width=spec["min_width"],
                              min_height=spec["min_height"])
            for block in selected(book["blocks"], page=page, kind="document_index")
        )
    if kind == "code_preserved":
        code = selected(book["blocks"], page=page, kind="code")
        preserved = sum(
            asset_is_readable(block, work, min_width=spec["min_width"])
            if block.get("asset") else ("\n" in block.get("text", "") and bool(block["text"].strip()))
            for block in code
        )
        return preserved >= spec["minimum"]
    raise ValueError(f"Unknown golden check: {kind}")


def _inside(relative_path: str) -> Path:
    path = (ROOT / relative_path).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError(f"Fixture path escapes public golden directory: {relative_path}")
    return path


def _native_json(case: dict, source: Path, work: Path, *, live: bool) -> Path:
    if not live:
        native = work / "native.json"
        with gzip.open(_inside(case["native"]), "rb") as compressed:
            native.write_bytes(compressed.read())
        return native
    executable = Path(sys.executable).with_name("docling")
    command = str(executable) if executable.is_file() else shutil.which("docling")
    if not command:
        raise RuntimeError("Live golden tests require pdf-to-book[convert]")
    output = work / "docling"
    env = os.environ.copy()
    local_cache = ROOT.parents[1] / "benchmark" / "cache" / "huggingface"
    if local_cache.is_dir():
        env.setdefault("HF_HOME", str(local_cache))
    result = subprocess.run(
        [command, "convert", str(source), "--pipeline", "standard", "--no-ocr",
         "--device", "cpu", "--table-mode", "fast", "--page-range",
         f"{case['pages'][0]}-{case['pages'][-1]}", "--to", "json",
         "--image-export-mode", "embedded", "--output", str(output)],
        capture_output=True, text=True, check=False, env=env,
    )
    if result.returncode:
        raise RuntimeError(f"Docling failed for {case['id']}:\n{result.stdout}\n{result.stderr}")
    return output / f"{source.stem}.json"


def run_case(case: dict, *, live: bool = False) -> list[str]:
    source = _inside(case["pdf"])
    if hashlib.sha256(source.read_bytes()).hexdigest() != case["source_sha256"]:
        raise AssertionError(f"{case['id']}: PDF checksum changed; re-review the annotation")
    document = pypdfium2.PdfDocument(str(source))
    try:
        if not all(1 <= number <= len(document) for number in case["pages"]):
            raise AssertionError(f"{case['id']}: annotated page is absent from PDF")
    finally:
        document.close()
    annotation = json.loads(_inside(case["annotation"]).read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(annotation, schema)
    if annotation["id"] != case["id"]:
        raise AssertionError(f"{case['id']}: annotation ID does not match manifest")
    if any(spec.get("page") not in (None, *case["pages"]) for spec in annotation["checks"]):
        raise AssertionError(f"{case['id']}: golden check references a page outside the case")
    with tempfile.TemporaryDirectory(prefix="public-golden-") as directory:
        work = Path(directory)
        native = _native_json(case, source, work, live=live)
        data = json.loads(native.read_text(encoding="utf-8"))
        if sorted(map(int, data["pages"])) != case["pages"]:
            raise AssertionError(f"{case['id']}: native page range differs from manifest")
        if data.get("origin", {}).get("filename") != source.name:
            raise AssertionError(f"{case['id']}: native source filename differs from PDF")
        book = adapt(native, source, case["id"], "Public golden corpus", "en", work / "assets")
        book["source_sha256"] = case["source_sha256"]
        xhtml = render_content(book)
        failures = [
            f"{case['id']}: {spec}"
            for spec in annotation["checks"] if not check(book, xhtml, work, spec)
        ]
        if not live and semantic_fingerprint(book) != case["semantic_sha256"]:
            failures.append(f"{case['id']}: complete semantic snapshot changed; review the PDF and update the baseline")
        epub = work / "book.epub"
        write_epub(book, work, epub, modified=FIXED_DATE)
        report = validate(epub)
        if not report["valid"]:
            failures.append(f"{case['id']}: EPUB validation failed: {report}")
        with ZipFile(epub) as archive:
            names = set(archive.namelist())
            for asset in book["assets"]:
                if "EPUB/" + asset["path"] not in names:
                    failures.append(f"{case['id']}: EPUB lacks {asset['path']}")
        first = epub.read_bytes()
        write_epub(book, work, work / "repeat.epub", modified=FIXED_DATE)
        if (work / "repeat.epub").read_bytes() != first:
            failures.append(f"{case['id']}: EPUB output is nondeterministic")
        if case.get("cli_smoke"):
            cli_output = work / "cli.epub"
            env = os.environ.copy()
            env["SOURCE_DATE_EPOCH"] = "946684800"
            result = subprocess.run(
                [sys.executable, "-m", "pdf_to_book", str(source), "--pages",
                 f"{case['pages'][0]}-{case['pages'][-1]}", "--title", case["id"],
                 "--docling-json", str(native), "--output", str(cli_output)],
                capture_output=True, text=True, check=False, env=env,
            )
            if result.returncode:
                failures.append(f"{case['id']}: CLI conversion failed: {result.stderr}")
            else:
                with ZipFile(cli_output) as archive:
                    if "EPUB/cover.xhtml" not in archive.namelist():
                        failures.append(f"{case['id']}: CLI EPUB has no cover")
        return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="rerun Docling instead of snapshots")
    parser.add_argument("--case", action="append", help="run only this case ID (repeatable)")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    if manifest["schema_version"] != "public-golden-1":
        raise ValueError("Unknown public golden manifest version")
    cases = [case for case in manifest["cases"] if not args.case or case["id"] in args.case]
    if not cases or (args.case and set(args.case) != {case["id"] for case in cases}):
        parser.error("Unknown or missing --case ID")
    failures = []
    for case in cases:
        case_failures = run_case(case, live=args.live)
        failures.extend(case_failures)
        print(f"{case['id']}: {'FAIL' if case_failures else 'PASS'}")
        for failure in case_failures:
            print("  " + failure)
    print(f"{len(cases)} cases, {len(failures)} failed golden checks")
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
