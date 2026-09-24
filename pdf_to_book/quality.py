"""Stable, path-independent quality fingerprints for converted books."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from typing import Any


BLOCK_FIELDS = (
    "id",
    "type",
    "text",
    "number",
    "level",
    "language",
    "asset",
    "alt",
    "image_sha256",
    "display_width_percent",
    "source_aspect_ratio",
    "image_width_px",
    "image_height_px",
    "display_width_px",
    "caption_ids",
    "data",
    "group_id",
    "ordered",
    "marker",
    "hyperlink",
    "note_refs",
    "backlink",
)


def _stable_block(block: dict[str, Any]) -> dict[str, Any]:
    """Keep every field that can affect the reader-visible publication."""
    return {field: block[field] for field in BLOCK_FIELDS if field in block}


def quality_projection(book: dict[str, Any], *, stylesheet: str = "") -> dict[str, Any]:
    """Return the canonical reader-visible representation used by quality gates.

    Source paths, parser versions, timing data and PDF coordinates are deliberately
    excluded. They may change without changing the publication a reader receives.
    """
    return {
        "contract_version": 3,
        "schema_version": book.get("schema_version"),
        "title": book["title"],
        "author": book["author"],
        "language": book["language"],
        "source_sha256": book.get("source_sha256"),
        "pages": book["pages"],
        "outline": [
            {field: item[field] for field in ("title", "level", "page_no") if field in item}
            for item in book.get("outline", [])
        ],
        "blocks": [_stable_block(block) for block in book["blocks"]],
        "footnotes": [_stable_block(note) for note in book["footnotes"]],
        "assets": [
            {field: asset[field] for field in ("path", "media_type", "sha256")}
            for asset in book["assets"]
        ],
        "cover": {
            field: book["cover"][field]
            for field in (
                "path", "media_type", "sha256", "width_px", "height_px",
                "source_page", "alt",
            )
            if field in book.get("cover", {})
        } or None,
        "stylesheet_sha256": hashlib.sha256(stylesheet.encode("utf-8")).hexdigest(),
    }


def quality_fingerprint(book: dict[str, Any], *, stylesheet: str = "") -> str:
    payload = json.dumps(
        quality_projection(book, stylesheet=stylesheet),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def quality_report(
    book: dict[str, Any],
    *,
    stylesheet: str,
    content_xhtml: str,
    navigation_xhtml: str,
) -> dict[str, Any]:
    types = Counter(block["type"] for block in book["blocks"])
    text = "\n".join(block.get("text", "") for block in book["blocks"])
    code = [block for block in book["blocks"] if block["type"] == "code"]
    return {
        "contract_version": 3,
        "quality_sha256": quality_fingerprint(book, stylesheet=stylesheet),
        "source_sha256": book.get("source_sha256"),
        "pages": book["pages"],
        "block_count": len(book["blocks"]),
        "blocks_by_type": dict(sorted(types.items())),
        "text_characters": len(text),
        "code_blocks": len(code),
        "formulas": types["formula"],
        "code_lines": sum(len(block.get("text", "").splitlines()) for block in code),
        "headings": [
            {"text": block["text"], "level": block["level"]}
            for block in book["blocks"]
            if block["type"] == "heading"
        ],
        "figures": [
            {
                "id": block["id"],
                "sha256": block["image_sha256"],
                "width_percent": block["display_width_percent"],
                "width_px": block["image_width_px"],
                "height_px": block["image_height_px"],
            }
            for block in book["blocks"]
            if block["type"] == "figure"
        ],
        "cover": (
            {
                field: book["cover"][field]
                for field in (
                    "sha256", "width_px", "height_px", "source_page",
                )
            }
            if book.get("cover")
            else None
        ),
        "footnotes": [
            {
                "id": note["id"],
                "marker": note.get("marker"),
                "linked": bool(note.get("backlink")),
            }
            for note in book["footnotes"]
        ],
        "warnings": list(book.get("warnings", [])),
        "stylesheet_sha256": hashlib.sha256(stylesheet.encode("utf-8")).hexdigest(),
        "content_xhtml_sha256": hashlib.sha256(content_xhtml.encode("utf-8")).hexdigest(),
        "navigation_xhtml_sha256": hashlib.sha256(navigation_xhtml.encode("utf-8")).hexdigest(),
    }
