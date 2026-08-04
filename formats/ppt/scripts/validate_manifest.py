#!/usr/bin/env python3
"""Validate an ordered PowerPoint translation manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REQUIRED_TOP_LEVEL = (
    "source_file",
    "source_language",
    "target_language",
    "format",
    "items",
)
REQUIRED_ITEM_FIELDS = (
    "id",
    "kind",
    "source_text",
    "translation",
    "context",
    "location",
    "protected_tokens",
)
LOCATION_FIELDS = {
    "ppt_paragraph": ("slide", "shape_id", "paragraph"),
    "ppt_table_cell": ("slide", "shape_id", "row", "column", "paragraph"),
    "ppt_note": ("slide", "shape_id", "paragraph"),
    "ppt_chart_text": ("slide", "shape_id", "chart_part"),
    "office_overlay": ("page_or_slide", "host_shape_id", "region_id"),
}
STRING_LOCATION_FIELDS = {"chart_part", "region_id"}
FORMAT_ITEM_KINDS = {"powerpoint": set(LOCATION_FIELDS)}


class ManifestError(ValueError):
    pass


def _non_empty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{label}: expected a non-empty string")
    return value


def _positive_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ManifestError(f"{label}: expected a positive integer")
    return value


def validate_manifest(path: str | Path, require_translations: bool = False) -> dict:
    manifest_path = Path(path)
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ManifestError(f"manifest not found: {manifest_path}") from exc
    except json.JSONDecodeError as exc:
        raise ManifestError(
            f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc

    if not isinstance(data, dict):
        raise ManifestError("manifest root must be an object")
    for field in REQUIRED_TOP_LEVEL:
        if field not in data:
            raise ManifestError(f"missing top-level field: {field}")

    _non_empty_string(data["source_file"], "source_file")
    _non_empty_string(data["source_language"], "source_language")
    _non_empty_string(data["target_language"], "target_language")
    document_format = _non_empty_string(data["format"], "format")
    if document_format != "powerpoint":
        raise ManifestError("format: expected powerpoint")
    if not isinstance(data["items"], list):
        raise ManifestError("items: expected an array")

    seen_ids: set[str] = set()
    translated = 0
    items_by_kind: dict[str, int] = {}
    for index, item in enumerate(data["items"], start=1):
        label = f"items[{index}]"
        if not isinstance(item, dict):
            raise ManifestError(f"{label}: expected an object")
        for field in REQUIRED_ITEM_FIELDS:
            if field not in item:
                raise ManifestError(f"{label}: missing field: {field}")

        item_id = _non_empty_string(item["id"], f"{label}.id")
        if item_id in seen_ids:
            raise ManifestError(f"{label}: duplicate id: {item_id}")
        seen_ids.add(item_id)

        kind = _non_empty_string(item["kind"], f"{label}.kind")
        if kind not in LOCATION_FIELDS:
            raise ManifestError(f"{label}.kind: unsupported kind: {kind}")
        if kind not in FORMAT_ITEM_KINDS[document_format]:
            raise ManifestError(
                f"{label}.kind: {kind} is not valid for format {document_format}"
            )
        _non_empty_string(item["source_text"], f"{label}.source_text")
        if not isinstance(item["translation"], str):
            raise ManifestError(f"{label}.translation: expected a string")
        if not isinstance(item["context"], dict):
            raise ManifestError(f"{label}.context: expected an object")
        if not isinstance(item["location"], dict):
            raise ManifestError(f"{label}.location: expected an object")
        for field in LOCATION_FIELDS[kind]:
            location_label = f"{label}.location.{field}"
            if field not in item["location"]:
                raise ManifestError(f"{location_label}: missing field")
            if field in STRING_LOCATION_FIELDS:
                _non_empty_string(item["location"][field], location_label)
            else:
                _positive_int(item["location"][field], location_label)
        if not isinstance(item["protected_tokens"], list):
            raise ManifestError(f"{label}.protected_tokens: expected an array")
        for token_index, token in enumerate(item["protected_tokens"], start=1):
            if not isinstance(token, str):
                raise ManifestError(
                    f"{label}.protected_tokens[{token_index}]: expected a string"
                )

        if item["translation"].strip():
            translated += 1
        elif require_translations:
            raise ManifestError(f"{label}: empty translation: {item_id}")
        items_by_kind[kind] = items_by_kind.get(kind, 0) + 1

    return {
        "source_file": data["source_file"],
        "format": document_format,
        "items": len(data["items"]),
        "translated": translated,
        "untranslated": len(data["items"]) - translated,
        "items_by_kind": items_by_kind,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="Path to the translation manifest JSON")
    parser.add_argument(
        "--require-translations",
        action="store_true",
        help="Reject any item with an empty translation",
    )
    args = parser.parse_args()

    try:
        summary = validate_manifest(args.manifest, args.require_translations)
    except ManifestError as exc:
        print(f"manifest error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
