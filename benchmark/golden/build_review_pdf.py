#!/usr/bin/env python3
"""Build a side-by-side PDF for visual review of normalized parser output."""

from __future__ import annotations

import argparse
import html
import json
import subprocess
import tempfile
import textwrap
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Preformatted

from evaluate import evaluate


ROOT = Path(__file__).resolve().parents[2]
SANS_FONT = "Helvetica"
MONO_FONT = "Courier"
TYPE_COLORS = {
    "chapter_label": colors.HexColor("#6D28D9"),
    "heading": colors.HexColor("#1D4ED8"),
    "paragraph": colors.HexColor("#334155"),
    "epigraph": colors.HexColor("#7C3AED"),
    "attribution": colors.HexColor("#7C3AED"),
    "list_item": colors.HexColor("#047857"),
    "code": colors.HexColor("#B45309"),
    "figure": colors.HexColor("#BE185D"),
    "caption": colors.HexColor("#BE185D"),
    "table": colors.HexColor("#0F766E"),
    "footnote": colors.HexColor("#64748B"),
    "exercise": colors.HexColor("#9A3412"),
    "running_header": colors.HexColor("#DC2626"),
    "running_footer": colors.HexColor("#DC2626"),
    "page_number": colors.HexColor("#DC2626"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold-dir", type=Path, required=True)
    parser.add_argument(
        "--prediction",
        action="append",
        required=True,
        metavar="NAME=DIR",
        help="Parser name and directory containing prediction JSON files",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pdftoppm", default="pdftoppm")
    return parser.parse_args()


def parse_prediction_specs(values: list[str]) -> list[tuple[str, Path]]:
    specs: list[tuple[str, Path]] = []
    for value in values:
        if "=" not in value:
            raise ValueError(f"Invalid prediction specification: {value}")
        name, directory = value.split("=", 1)
        specs.append((name, Path(directory)))
    return specs


def render_original(pdftoppm: str, source: Path, page_number: int, destination: Path) -> Path:
    prefix = destination / "original"
    subprocess.run(
        [
            pdftoppm,
            "-f",
            str(page_number),
            "-l",
            str(page_number),
            "-r",
            "120",
            "-png",
            "-singlefile",
            str(source),
            str(prefix),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    return prefix.with_suffix(".png")


def draw_original(
    pdf: canvas.Canvas, image_path: Path, x: float, y: float, width: float, height: float
) -> None:
    image = ImageReader(str(image_path))
    image_width, image_height = image.getSize()
    scale = min(width / image_width, height / image_height)
    draw_width = image_width * scale
    draw_height = image_height * scale
    pdf.setFillColor(colors.HexColor("#F8FAFC"))
    pdf.roundRect(x, y, width, height, 8, fill=1, stroke=0)
    pdf.drawImage(
        image,
        x + (width - draw_width) / 2,
        y + (height - draw_height) / 2,
        width=draw_width,
        height=draw_height,
        preserveAspectRatio=True,
        mask="auto",
    )


def metric_summary(metrics: dict[str, Any]) -> str:
    fields = [
        ("Text found", "text_recovery"),
        ("Text fidelity", "text_accuracy"),
        ("Block F1", "block_f1"),
        ("Types", "block_type_accuracy"),
        ("Code found", "code_text_recovery"),
        ("Code typed", "code_type_accuracy"),
        ("Code fidelity", "code_accuracy"),
    ]
    parts = []
    for label, key in fields:
        value = metrics.get(key)
        parts.append(f"{label}: {'n/a' if value is None else f'{value:.1f}%'}")
    return "   |   ".join(parts)


def make_flowable(block: dict[str, Any], width: float) -> tuple[Any, float]:
    block_type = block["type"]
    color = TYPE_COLORS.get(block_type, colors.HexColor("#334155"))
    content = block.get("text") or block.get("description") or "[element without text]"
    label = block_type.upper() + (" - EXCLUDED" if not block.get("include_in_epub", True) else "")
    if block_type == "code":
        max_characters = max(48, int(width / 4.2))
        wrapped_lines: list[str] = []
        for line in content.splitlines() or [""]:
            wrapped = textwrap.wrap(
                line,
                width=max_characters,
                replace_whitespace=False,
                drop_whitespace=False,
                subsequent_indent="    > ",
            )
            wrapped_lines.extend(wrapped or [""])
        display_content = "\n".join(wrapped_lines)
        flowable = Preformatted(
            f"{label}\n{display_content}",
            ParagraphStyle(
                "ReviewCode",
                fontName=MONO_FONT,
                fontSize=6.2,
                leading=7.4,
                textColor=color,
                backColor=colors.HexColor("#FFF7ED"),
                borderPadding=5,
                spaceAfter=4,
            ),
        )
    else:
        safe_content = html.escape(content).replace("\n", "<br/>")
        flowable = Paragraph(
            f'<font color="{color.hexval()}"><b>{html.escape(label)}</b></font><br/>{safe_content}',
            ParagraphStyle(
                "ReviewBlock",
                fontName=SANS_FONT,
                fontSize=6.8,
                leading=8.2,
                textColor=colors.HexColor("#0F172A"),
                backColor=colors.HexColor("#F8FAFC"),
                borderColor=color,
                borderWidth=0.6,
                borderPadding=4,
                spaceAfter=4,
            ),
        )
    _, height = flowable.wrap(width, 10_000)
    return flowable, height


def draw_review_pages(
    pdf: canvas.Canvas,
    gold: dict[str, Any],
    prediction: dict[str, Any],
    parser_name: str,
    original_image: Path,
) -> None:
    page_width, page_height = landscape(A3)
    margin = 28
    gap = 24
    header_height = 54
    panel_height = page_height - 2 * margin - header_height
    left_width = (page_width - 2 * margin - gap) * 0.43
    right_width = page_width - 2 * margin - gap - left_width
    blocks = sorted(prediction["blocks"], key=lambda block: block["reading_order"])
    metrics = evaluate(gold, prediction)["metrics_percent"]
    block_index = 0
    continuation = 0

    while block_index < len(blocks):
        pdf.setFillColor(colors.white)
        pdf.rect(0, 0, page_width, page_height, fill=1, stroke=0)
        pdf.setFont(SANS_FONT, 15)
        pdf.setFillColor(colors.HexColor("#0F172A"))
        suffix = "" if continuation == 0 else f" - continuation {continuation}"
        pdf.drawString(margin, page_height - margin - 15, f"{gold['id']} - {parser_name}{suffix}")
        pdf.setFont(SANS_FONT, 7.2)
        pdf.setFillColor(colors.HexColor("#475569"))
        pdf.drawString(margin, page_height - margin - 31, metric_summary(metrics))

        panel_y = margin
        draw_original(pdf, original_image, margin, panel_y, left_width, panel_height)
        right_x = margin + left_width + gap
        pdf.setFillColor(colors.HexColor("#EEF2FF"))
        pdf.roundRect(right_x, panel_y, right_width, panel_height, 8, fill=1, stroke=0)
        cursor_y = panel_y + panel_height - 12
        available_width = right_width - 20

        while block_index < len(blocks):
            flowable, block_height = make_flowable(blocks[block_index], available_width)
            if cursor_y - block_height < panel_y + 10:
                break
            cursor_y -= block_height
            flowable.drawOn(pdf, right_x + 10, cursor_y)
            cursor_y -= 4
            block_index += 1

        pdf.showPage()
        continuation += 1


def main() -> int:
    args = parse_args()
    prediction_specs = parse_prediction_specs(args.prediction)
    gold_pages = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(args.gold_dir.glob("*.json"))
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary_root = ROOT / "tmp" / "pdfs"
    temporary_root.mkdir(parents=True, exist_ok=True)

    pdf = canvas.Canvas(str(args.output), pagesize=landscape(A3))
    pdf.setTitle("PDF parser visual review")
    pdf.setAuthor("PDF to Book benchmark")
    page_count = 0
    with tempfile.TemporaryDirectory(prefix="review-", dir=temporary_root) as temporary_dir:
        temporary_path = Path(temporary_dir)
        for gold_id, gold in gold_pages.items():
            source = ROOT / gold["source"]
            rendered_dir = temporary_path / gold_id
            rendered_dir.mkdir(parents=True, exist_ok=True)
            original_image = render_original(
                args.pdftoppm, source, gold["page_number_pdf"], rendered_dir
            )
            for parser_name, prediction_dir in prediction_specs:
                prediction_path = prediction_dir / f"{gold_id}.json"
                if not prediction_path.exists():
                    continue
                prediction = json.loads(prediction_path.read_text(encoding="utf-8"))
                draw_review_pages(pdf, gold, prediction, parser_name, original_image)
                page_count += 1
    if page_count == 0:
        raise ValueError("No matching predictions found")
    pdf.save()
    print(f"Created {args.output} from {page_count} gold/parser comparisons")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
