#!/usr/bin/env python3
"""Evaluate a normalized parser prediction against one golden page."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


ARTIFACT_TYPES = {"running_header", "running_footer", "page_number"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("gold", type=Path)
    parser.add_argument("prediction", type=Path)
    return parser.parse_args()


def load_page(path: Path) -> dict[str, Any]:
    page = json.loads(path.read_text(encoding="utf-8"))
    required = {"schema_version", "id", "source", "page_number_pdf", "language", "blocks"}
    missing = required - page.keys()
    if missing:
        raise ValueError(f"{path}: missing fields: {sorted(missing)}")
    orders = [block["reading_order"] for block in page["blocks"]]
    if len(orders) != len(set(orders)):
        raise ValueError(f"{path}: reading_order values must be unique")
    return page


def normalize_text(text: str, *, code: bool = False) -> str:
    text = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n")
    if code:
        return text
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().casefold()


def edit_distance(left: str, right: str) -> int:
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def accuracy(left: str, right: str, *, code: bool = False) -> float:
    left_normalized = normalize_text(left, code=code)
    right_normalized = normalize_text(right, code=code)
    denominator = max(len(left_normalized), len(right_normalized), 1)
    return max(0.0, 1.0 - edit_distance(left_normalized, right_normalized) / denominator)


def content_recovery(expected: str, observed: str) -> float:
    """Return how much expected content appears in order, ignoring block types and whitespace."""
    expected_normalized = normalize_text(expected)
    observed_normalized = normalize_text(observed)
    if not expected_normalized:
        return 1.0
    matcher = SequenceMatcher(
        None, expected_normalized, observed_normalized, autojunk=False
    )
    recovered_characters = sum(block.size for block in matcher.get_matching_blocks())
    return recovered_characters / len(expected_normalized)


def block_text(block: dict[str, Any]) -> str:
    return block.get("text") or block.get("description") or ""


def semantic_blocks(page: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        (block for block in page["blocks"] if block.get("include_in_epub", True)),
        key=lambda block: block["reading_order"],
    )


def similarity(gold: dict[str, Any], predicted: dict[str, Any]) -> float:
    if gold["type"] == "figure":
        if gold.get("image_sha256"):
            return float(predicted["type"] == "figure" and
                         gold["image_sha256"] == predicted.get("image_sha256"))
        return 1.0 if predicted["type"] == "figure" else 0.0
    gold_text = normalize_text(block_text(gold), code=gold["type"] == "code")
    predicted_text = normalize_text(
        block_text(predicted), code=gold["type"] == "code" or predicted["type"] == "code"
    )
    if not gold_text or not predicted_text:
        return 0.0
    return SequenceMatcher(None, gold_text, predicted_text, autojunk=False).ratio()


def match_blocks(
    gold_blocks: list[dict[str, Any]], predicted_blocks: list[dict[str, Any]], threshold: float = 0.55
) -> list[tuple[int, int, float]]:
    candidates: list[tuple[float, int, int]] = []
    for gold_index, gold_block in enumerate(gold_blocks):
        for predicted_index, predicted_block in enumerate(predicted_blocks):
            score = similarity(gold_block, predicted_block)
            if score >= threshold:
                candidates.append((score, gold_index, predicted_index))

    matches: list[tuple[int, int, float]] = []
    used_gold: set[int] = set()
    used_predicted: set[int] = set()
    for score, gold_index, predicted_index in sorted(candidates, reverse=True):
        if gold_index in used_gold or predicted_index in used_predicted:
            continue
        used_gold.add(gold_index)
        used_predicted.add(predicted_index)
        matches.append((gold_index, predicted_index, score))
    return sorted(matches)


def ratio(numerator: int, denominator: int) -> float:
    return 1.0 if denominator == 0 else numerator / denominator


def percent(value: float) -> float:
    return round(100.0 * value, 2)


def optional_percent(numerator: int | float, denominator: int) -> float | None:
    return None if denominator == 0 else percent(numerator / denominator)


def concatenate_text(blocks: list[dict[str, Any]], block_type: str | None = None) -> str:
    selected = blocks if block_type is None else [b for b in blocks if b["type"] == block_type]
    return "\n\n".join(block["text"] for block in selected if block.get("text"))


def evaluate(gold: dict[str, Any], prediction: dict[str, Any]) -> dict[str, Any]:
    gold_blocks = semantic_blocks(gold)
    predicted_blocks = semantic_blocks(prediction)
    matches = match_blocks(gold_blocks, predicted_blocks)

    matched_count = len(matches)
    type_correct = sum(
        gold_blocks[gold_index]["type"] == predicted_blocks[predicted_index]["type"]
        for gold_index, predicted_index, _ in matches
    )

    heading_matches = [
        (gold_blocks[gold_index], predicted_blocks[predicted_index])
        for gold_index, predicted_index, _ in matches
        if gold_blocks[gold_index]["type"] == "heading"
    ]
    heading_level_correct = sum(
        gold_block.get("level") == predicted_block.get("level")
        for gold_block, predicted_block in heading_matches
    )

    gold_code_blocks = [block for block in gold_blocks if block["type"] == "code"]
    code_matches = [
        (gold_blocks[gold_index], predicted_blocks[predicted_index])
        for gold_index, predicted_index, _ in matches
        if gold_blocks[gold_index]["type"] == "code"
    ]
    code_type_correct = sum(
        predicted_block["type"] == "code" for _, predicted_block in code_matches
    )

    ordered_matches = sorted(matches, key=lambda match: gold_blocks[match[0]]["reading_order"])
    concordant = 0
    pair_count = 0
    for left_index, left_match in enumerate(ordered_matches):
        for right_match in ordered_matches[left_index + 1 :]:
            pair_count += 1
            left_order = predicted_blocks[left_match[1]]["reading_order"]
            right_order = predicted_blocks[right_match[1]]["reading_order"]
            concordant += left_order < right_order

    artifact_blocks = [block for block in gold["blocks"] if block["type"] in ARTIFACT_TYPES]
    artifact_leaks = 0
    expected_text = normalize_text(concatenate_text(gold_blocks))
    observed_text = normalize_text(concatenate_text(predicted_blocks))
    for artifact in artifact_blocks:
        value = normalize_text(block_text(artifact))
        if not value:
            continue
        pattern = re.compile(r"(?<!\w)" + re.escape(value) + r"(?!\w)")
        # Count excess occurrences, including artifacts fused into a paragraph.
        # A legitimate occurrence in the source body is not itself a leak.
        excess = len(pattern.findall(observed_text)) > len(pattern.findall(expected_text))
        fuzzy_leak = any(
            similarity(artifact, predicted) >= 0.8
            and not any(similarity(body, predicted) >= 0.8 for body in gold_blocks)
            for predicted in predicted_blocks
        )
        if excess or fuzzy_leak:
            artifact_leaks += 1

    gold_figures = [block for block in gold_blocks if block["type"] == "figure"]
    gold_captions = [block for block in gold_blocks if block["type"] == "caption"]
    matched_gold_indices = {gold_index for gold_index, _, _ in matches}
    matched_figures = min(len(gold_figures), sum(b["type"] == "figure" for b in predicted_blocks))
    matched_captions = sum(
        gold_blocks[g]["type"] == "caption" and predicted_blocks[p]["type"] == "caption"
        for g, p, _ in matches
    )
    verifiable_figures = [b for b in gold_figures if b.get("image_sha256")]
    verified_figures = sum(
        gold_blocks[g]["type"] == "figure" and bool(gold_blocks[g].get("image_sha256"))
        and gold_blocks[g]["image_sha256"] == predicted_blocks[p].get("image_sha256")
        for g, p, _ in matches
    )

    metrics = {
        "text_recovery": percent(
            content_recovery(
                concatenate_text(gold_blocks), concatenate_text(predicted_blocks)
            )
        ),
        "text_accuracy": percent(
            accuracy(concatenate_text(gold_blocks), concatenate_text(predicted_blocks))
        ),
        "block_precision": percent(ratio(matched_count, len(predicted_blocks))),
        "block_recall": percent(ratio(matched_count, len(gold_blocks))),
        "block_f1": percent(
            ratio(2 * matched_count, len(gold_blocks) + len(predicted_blocks))
        ),
        "block_type_accuracy": optional_percent(type_correct, matched_count),
        "heading_level_accuracy": optional_percent(
            heading_level_correct, len(heading_matches)
        ),
        "reading_order_accuracy": optional_percent(concordant, pair_count),
        "code_accuracy": (
            percent(
                accuracy(
                    concatenate_text(gold_blocks, "code"),
                    concatenate_text(predicted_blocks, "code"),
                    code=True,
                )
            )
            if gold_code_blocks
            else None
        ),
        "code_text_recovery": (
            percent(
                content_recovery(
                    concatenate_text(gold_blocks, "code"),
                    concatenate_text(predicted_blocks),
                )
            )
            if gold_code_blocks
            else None
        ),
        "code_type_accuracy": optional_percent(
            code_type_correct, len(gold_code_blocks)
        ),
        "artifact_suppression_accuracy": optional_percent(
            len(artifact_blocks) - artifact_leaks, len(artifact_blocks)
        ),
        "figure_presence_recall": optional_percent(matched_figures, len(gold_figures)),
        "figure_recall": optional_percent(verified_figures, len(verifiable_figures)),
        "figure_verification_coverage": optional_percent(len(verifiable_figures), len(gold_figures)),
        "caption_recall": optional_percent(matched_captions, len(gold_captions)),
    }
    return {
        "gold_id": gold["id"],
        "prediction_id": prediction["id"],
        "counts": {
            "gold_blocks": len(gold_blocks),
            "predicted_blocks": len(predicted_blocks),
            "matched_blocks": matched_count,
        },
        "metrics_percent": metrics,
        "matches": [
            {
                "gold_block": gold_blocks[gold_index]["id"],
                "predicted_block": predicted_blocks[predicted_index]["id"],
                "text_similarity": percent(score),
            }
            for gold_index, predicted_index, score in matches
        ],
    }


def main() -> int:
    args = parse_args()
    result = evaluate(load_page(args.gold), load_page(args.prediction))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
