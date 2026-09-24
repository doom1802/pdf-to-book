#!/usr/bin/env python3
"""Local interactive reviewer for the PDF parsing golden set."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = Path(__file__).resolve().parent / "static"
GOLDEN_ROOT = ROOT / "benchmark" / "golden"
ANNOTATIONS_ROOT = GOLDEN_ROOT / "annotations"
PREDICTIONS_ROOT = ROOT / "benchmark" / "results" / "golden-v0" / "predictions"
MANIFEST_PATH = GOLDEN_ROOT / "manifest.json"
SCHEMA_PATH = GOLDEN_ROOT / "schema.json"
IMAGE_CACHE = ROOT / "tmp" / "reviewer-pages"

sys.path.insert(0, str(GOLDEN_ROOT))
from evaluate import evaluate  # noqa: E402


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    ) as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        temporary_path = Path(stream.name)
    os.replace(temporary_path, path)


def manifest() -> dict[str, Any]:
    return read_json(MANIFEST_PATH)


def manifest_entry(page_id: str) -> dict[str, Any] | None:
    return next((page for page in manifest()["pages"] if page["id"] == page_id), None)


def annotation_path(page_id: str) -> Path:
    return ANNOTATIONS_ROOT / f"{page_id}.json"


def allowed_types() -> list[str]:
    schema = read_json(SCHEMA_PATH)
    return schema["properties"]["blocks"]["items"]["properties"]["type"]["enum"]


def validate_annotation(page_id: str, annotation: dict[str, Any]) -> None:
    errors = list(Draft202012Validator(read_json(SCHEMA_PATH)).iter_errors(annotation))
    if errors:
        raise ValueError(errors[0].message)
    entry = manifest_entry(page_id)
    if entry is None:
        raise ValueError("Unknown page")
    if annotation.get("id") != page_id:
        raise ValueError("The annotation id cannot be changed")
    if annotation.get("source") != entry["source"]:
        raise ValueError("The source cannot be changed")
    if annotation.get("page_number_pdf") != entry["page_number_pdf"]:
        raise ValueError("The PDF page number cannot be changed")
    status = annotation.get("annotation", {}).get("status")
    if status not in {"draft", "reviewed", "adjudicated"}:
        raise ValueError("Invalid annotation status")
    blocks = annotation.get("blocks")
    if not isinstance(blocks, list):
        raise ValueError("blocks must be a list")
    types = set(allowed_types())
    ids: set[str] = set()
    for index, block in enumerate(blocks):
        block_id = block.get("id")
        if not isinstance(block_id, str) or not block_id:
            raise ValueError(f"Block {index + 1} has no id")
        if block_id in ids:
            raise ValueError(f"Duplicate block id: {block_id}")
        ids.add(block_id)
        if block.get("type") not in types:
            raise ValueError(f"Invalid type for {block_id}")
        if block.get("reading_order") != index:
            raise ValueError("reading_order must follow the displayed block order")
        if not isinstance(block.get("include_in_epub"), bool):
            raise ValueError(f"include_in_epub must be boolean for {block_id}")
    for block in blocks:
        target = block.get("caption_block_id")
        if target is not None and not any(b["id"] == target and b["type"] == "caption" for b in blocks):
            raise ValueError(f"Invalid caption reference: {target}")


def update_manifest_status(page_id: str, annotation_status: str) -> None:
    value = manifest()
    status = "annotated_draft" if annotation_status == "draft" else annotation_status
    for page in value["pages"]:
        if page["id"] == page_id:
            page["status"] = status
            break
    write_json_atomic(MANIFEST_PATH, value)


def parser_predictions(page_id: str, gold: dict[str, Any]) -> list[dict[str, Any]]:
    predictions: list[dict[str, Any]] = []
    if not PREDICTIONS_ROOT.exists():
        return predictions
    for parser_dir in sorted(path for path in PREDICTIONS_ROOT.iterdir() if path.is_dir()):
        path = parser_dir / f"{page_id}.json"
        if not path.exists():
            continue
        prediction = read_json(path)
        predictions.append(
            {
                "parser": parser_dir.name,
                "prediction": prediction,
                "evaluation": evaluate(gold, prediction),
            }
        )
    return predictions


def render_source_page(page_id: str) -> Path:
    entry = manifest_entry(page_id)
    if entry is None:
        raise ValueError("Unknown page")
    IMAGE_CACHE.mkdir(parents=True, exist_ok=True)
    destination = IMAGE_CACHE / f"{page_id}.png"
    source = ROOT / entry["source"]
    if destination.exists() and destination.stat().st_mtime >= source.stat().st_mtime:
        return destination
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise RuntimeError(
            "pypdfium2 is required. Start the reviewer with .venv-docling/bin/python."
        ) from exc
    document = pdfium.PdfDocument(str(source))
    page = document[entry["page_number_pdf"] - 1]
    page.render(scale=2.0).to_pil().save(destination)
    return destination


class ReviewerHandler(SimpleHTTPRequestHandler):
    server_version = "GoldenReviewer/0.1"

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[reviewer] {self.address_string()} - {format % args}")

    def send_json(self, value: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def send_error_json(self, status: HTTPStatus, message: str) -> None:
        self.send_json({"error": message}, status)

    def do_GET(self) -> None:  # noqa: N802
        route = unquote(urlparse(self.path).path)
        if route == "/api/pages":
            value = manifest()
            self.send_json(
                {
                    "version": value["version"],
                    "pages": value["pages"],
                    "types": allowed_types(),
                }
            )
            return
        if route.startswith("/api/pages/"):
            parts = route.strip("/").split("/")
            if len(parts) == 4 and parts[3] == "source.png":
                page_id = parts[2]
                try:
                    path = render_source_page(page_id)
                    payload = path.read_bytes()
                except (ValueError, RuntimeError) as exc:
                    self.send_error_json(HTTPStatus.NOT_FOUND, str(exc))
                    return
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(payload)
                return
            if len(parts) == 3:
                page_id = parts[2]
                path = annotation_path(page_id)
                if manifest_entry(page_id) is None or not path.exists():
                    self.send_error_json(HTTPStatus.NOT_FOUND, "Annotation not found")
                    return
                gold = read_json(path)
                self.send_json(
                    {
                        "manifest": manifest_entry(page_id),
                        "annotation": gold,
                        "predictions": parser_predictions(page_id, gold),
                    }
                )
                return
        if route == "/":
            self.path = "/index.html"
        elif not route.startswith("/static/"):
            self.send_error_json(HTTPStatus.NOT_FOUND, "Not found")
            return
        else:
            self.path = route.removeprefix("/static")
        super().do_GET()

    def do_PUT(self) -> None:  # noqa: N802
        route = unquote(urlparse(self.path).path)
        parts = route.strip("/").split("/")
        if len(parts) != 3 or parts[:2] != ["api", "pages"]:
            self.send_error_json(HTTPStatus.NOT_FOUND, "Not found")
            return
        page_id = parts[2]
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 2_000_000:
                raise ValueError("Invalid request size")
            annotation = json.loads(self.rfile.read(length).decode("utf-8"))
            validate_annotation(page_id, annotation)
            write_json_atomic(annotation_path(page_id), annotation)
            update_manifest_status(page_id, annotation["annotation"]["status"])
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return
        self.send_json({"saved": True, "status": annotation["annotation"]["status"]})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    os.chdir(STATIC_ROOT)
    server = ThreadingHTTPServer((args.host, args.port), ReviewerHandler)
    print(f"Golden reviewer: http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
