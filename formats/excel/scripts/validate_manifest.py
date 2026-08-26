#!/usr/bin/env python3
"""Validate an Excel translation manifest before workbook mutation."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any


IMAGE_REASON_CODES = {
    "no-source-text",
    "logo-or-brand",
    "photograph",
    "localized",
    "manual-review",
}


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _token_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(token, str) for token in value)


def validate_v2(payload: dict[str, Any]) -> dict:
    errors: list[str] = []
    occurrences = payload.get("occurrences")
    translation_units = payload.get("translation_units")
    images = payload.get("images")
    if not isinstance(occurrences, list):
        errors.append("occurrences must be a list")
        occurrences = []
    if not isinstance(translation_units, list):
        errors.append("translation_units must be a list")
        translation_units = []
    if not isinstance(images, list):
        errors.append("images must be a list")
        images = []

    for field in ("source_file", "target_language", "output_mode"):
        if not _text(payload.get(field)):
            errors.append(f"{field} must be non-empty text")
    source_sha256 = payload.get("source_sha256")
    if not isinstance(source_sha256, str) or len(source_sha256) != 64:
        errors.append("source_sha256 must be a 64-character digest")
    if payload.get("output_mode") not in {"monolingual", "bilingual"}:
        errors.append("output_mode must be monolingual or bilingual")

    unit_map: dict[str, dict[str, Any]] = {}
    for index, unit in enumerate(translation_units):
        prefix = f"translation_units[{index}]"
        if not isinstance(unit, dict):
            errors.append(f"{prefix} must be an object")
            continue
        unit_id = unit.get("id")
        if not _text(unit_id) or unit_id in unit_map:
            errors.append(f"{prefix} has missing or duplicate id")
        else:
            unit_map[unit_id] = unit
        for field in ("source", "context_key"):
            if not _text(unit.get(field)):
                errors.append(f"{prefix}.{field} must be non-empty text")
        protected_tokens = unit.get("protected_tokens")
        if not _token_list(protected_tokens):
            errors.append(f"{prefix}.protected_tokens must be a list of text values")
            protected_tokens = []
        translation = unit.get("translation")
        status = unit.get("status")
        if status == "translated":
            if not _text(translation):
                errors.append(f"{prefix} translated unit needs translation")
        elif status == "retain":
            if not _text(unit.get("reason")):
                errors.append(f"{prefix} retained unit needs reason")
            if not isinstance(translation, str) or translation != unit.get("source"):
                errors.append(f"{prefix} retain translation must equal source")
        else:
            errors.append(f"{prefix} status must be translated or retain")
        for token in protected_tokens:
            if token not in (translation or ""):
                errors.append(f"{prefix} changed protected token: {token!r}")

    occurrence_seen: set[str] = set()
    for index, occurrence in enumerate(occurrences):
        prefix = f"occurrences[{index}]"
        if not isinstance(occurrence, dict):
            errors.append(f"{prefix} must be an object")
            continue
        occurrence_id = occurrence.get("id")
        if not _text(occurrence_id) or occurrence_id in occurrence_seen:
            errors.append(f"{prefix} has missing or duplicate id")
        else:
            occurrence_seen.add(occurrence_id)
        for field in ("kind", "sheet", "address", "source", "context_key"):
            if not _text(occurrence.get(field)):
                errors.append(f"{prefix}.{field} must be non-empty text")
        protected_tokens = occurrence.get("protected_tokens")
        if not _token_list(protected_tokens):
            errors.append(f"{prefix}.protected_tokens must be a list of text values")
            protected_tokens = []
        unit_id = occurrence.get("translation_unit_id")
        unit = unit_map.get(unit_id)
        if unit is None:
            errors.append(f"{prefix} references unknown translation_unit_id: {unit_id!r}")
            continue
        for field in ("source", "context_key", "protected_tokens"):
            if occurrence.get(field) != unit.get(field):
                errors.append(f"{prefix}.{field} does not match translation unit {unit_id}")

    image_seen: set[str] = set()
    for index, image in enumerate(images):
        prefix = f"images[{index}]"
        if not isinstance(image, dict):
            errors.append(f"{prefix} must be an object")
            continue
        image_id = image.get("id")
        if not _text(image_id) or image_id in image_seen:
            errors.append(f"{prefix} has missing or duplicate id")
        else:
            image_seen.add(image_id)
        digest = image.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            errors.append(f"{prefix}.sha256 must be a 64-character digest")
        locations = image.get("occurrences")
        if not isinstance(locations, list) or not locations or not all(_text(item) for item in locations):
            errors.append(f"{prefix}.occurrences must be a non-empty list of locations")
        if image.get("status") == "manual-review":
            errors.append(f"{prefix} manual-review is not deliverable")
        elif image.get("status") not in {"reviewed", "localized", "retain"}:
            errors.append(f"{prefix} has invalid status")
        if image.get("reason_code") not in IMAGE_REASON_CODES:
            errors.append(f"{prefix}.reason_code is invalid")

    return {
        "passed": not errors,
        "errors": errors,
        "counts": {
            "occurrences": len(occurrences),
            "translation_units": len(translation_units),
            "images": len(images),
        },
    }


def validate_legacy(payload: Any) -> dict:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return {
            "passed": False,
            "errors": ["manifest must be an object"],
            "counts": {"items": 0, "images": 0},
        }
    items = payload.get("items")
    images = payload.get("images")
    if not isinstance(items, list):
        errors.append("items must be a list")
        items = []
    if not isinstance(images, list):
        errors.append("images must be a list")
        images = []

    seen: set[str] = set()
    for index, item in enumerate(items):
        prefix = f"items[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id.strip() or item_id in seen:
            errors.append(f"{prefix} has missing or duplicate id")
        else:
            seen.add(item_id)
        status = item.get("status")
        source = item.get("source")
        translation = item.get("translation")
        if not isinstance(source, str):
            errors.append(f"{prefix}.source must be text")
        if status == "translated":
            if not isinstance(translation, str) or not translation.strip():
                errors.append(f"{prefix} translated item needs translation")
        elif status == "retain":
            if not isinstance(item.get("reason"), str) or not item["reason"].strip():
                errors.append(f"{prefix} retained item needs reason")
            if not isinstance(translation, str) or translation != source:
                errors.append(f"{prefix} retain translation must equal source")
        else:
            errors.append(f"{prefix} status must be translated or retain")
        protected_tokens = item.get("protected_tokens", [])
        if not isinstance(protected_tokens, list) or not all(isinstance(token, str) for token in protected_tokens):
            errors.append(f"{prefix}.protected_tokens must be a list of text values")
            protected_tokens = []
        for token in protected_tokens:
            if not isinstance(token, str) or token not in (translation or ""):
                errors.append(f"{prefix} changed protected token: {token!r}")

    image_seen: set[str] = set()
    for index, image in enumerate(images):
        prefix = f"images[{index}]"
        if not isinstance(image, dict):
            errors.append(f"{prefix} must be an object")
            continue
        image_id = image.get("id")
        if not isinstance(image_id, str) or not image_id.strip() or image_id in image_seen:
            errors.append(f"{prefix} has missing or duplicate id")
        else:
            image_seen.add(image_id)
        if image.get("status") not in {"reviewed", "localized", "retain"}:
            errors.append(f"{prefix} status must be reviewed, localized, or retain")
        if not isinstance(image.get("reason"), str) or not image["reason"].strip():
            errors.append(f"{prefix} needs review reason")

    return {
        "passed": not errors,
        "errors": errors,
        "counts": {"items": len(items), "images": len(images)},
    }


def validate(payload: Any) -> dict:
    if isinstance(payload, dict) and payload.get("schema_version") == 2:
        return validate_v2(payload)
    return validate_legacy(payload)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(json.dumps({"passed": False, "errors": ["usage: validate_manifest.py <manifest.json>"]}))
        return 2
    try:
        payload = json.loads(Path(args[0]).read_text(encoding="utf-8"))
        report = validate(payload)
    except (OSError, json.JSONDecodeError) as exc:
        report = {"passed": False, "errors": [str(exc)], "counts": {"items": 0, "images": 0}}
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
