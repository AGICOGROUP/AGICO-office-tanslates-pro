#!/usr/bin/env python3
"""Validate the lightweight PowerPoint translation manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


class ManifestError(ValueError):
    pass


def non_empty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{label}: expected a non-empty string")
    return value


def positive_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ManifestError(f"{label}: expected a positive integer")
    return value


def string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ManifestError(f"{label}: expected an array of strings")
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
    if data.get("schema_version") != 2:
        raise ManifestError("schema_version: expected 2")
    for field in (
        "source_file", "source_sha256", "source_language", "target_language",
        "format", "occurrences", "translation_units", "image_groups",
    ):
        if field not in data:
            raise ManifestError(f"missing top-level field: {field}")
    if data["format"] != "powerpoint":
        raise ManifestError("format: expected powerpoint")
    source_sha = non_empty_string(data["source_sha256"], "source_sha256")
    if len(source_sha) != 64 or any(c not in "0123456789abcdef" for c in source_sha.lower()):
        raise ManifestError("source_sha256: expected 64 hexadecimal digits")
    for field in ("occurrences", "translation_units", "image_groups"):
        if not isinstance(data[field], list):
            raise ManifestError(f"{field}: expected an array")

    overlays = data.get("overlays", [])
    if not isinstance(overlays, list):
        raise ManifestError("overlays: expected an array")
    overlays_by_id: dict[str, dict] = {}
    for index, overlay in enumerate(overlays, start=1):
        label = f"overlays[{index}]"
        if not isinstance(overlay, dict):
            raise ManifestError(f"{label}: expected an object")
        overlay_id = non_empty_string(overlay.get("id"), f"{label}.id")
        if overlay_id in overlays_by_id:
            raise ManifestError(f"{label}: duplicate id: {overlay_id}")
        overlays_by_id[overlay_id] = overlay

    units: dict[str, dict] = {}
    translated = 0
    for index, unit in enumerate(data["translation_units"], start=1):
        label = f"translation_units[{index}]"
        if not isinstance(unit, dict):
            raise ManifestError(f"{label}: expected an object")
        for field in ("id", "source_text", "translation", "role", "context_signature", "protected_tokens"):
            if field not in unit:
                raise ManifestError(f"{label}: missing field: {field}")
        unit_id = non_empty_string(unit["id"], f"{label}.id")
        if unit_id in units:
            raise ManifestError(f"{label}: duplicate id: {unit_id}")
        non_empty_string(unit["source_text"], f"{label}.source_text")
        if not isinstance(unit["translation"], str):
            raise ManifestError(f"{label}.translation: expected a string")
        tokens = string_list(unit["protected_tokens"], f"{label}.protected_tokens")
        if require_translations and not unit["translation"].strip():
            raise ManifestError(f"{label}: empty translation: {unit_id}")
        if unit["translation"].strip():
            for token in tokens:
                if require_translations and token not in unit["translation"]:
                    raise ManifestError(f"{label}: protected token missing from translation: {token}")
            translated += 1
        units[unit_id] = unit

    occurrence_ids: set[str] = set()
    for index, occurrence in enumerate(data["occurrences"], start=1):
        label = f"occurrences[{index}]"
        if not isinstance(occurrence, dict):
            raise ManifestError(f"{label}: expected an object")
        for field in (
            "id", "kind", "source_text", "translation_unit_id", "slide_index",
            "shape_id", "paragraph_index", "role", "context_signature", "protected_tokens",
        ):
            if field not in occurrence:
                raise ManifestError(f"{label}: missing field: {field}")
        occurrence_id = non_empty_string(occurrence["id"], f"{label}.id")
        if occurrence_id in occurrence_ids:
            raise ManifestError(f"{label}: duplicate id: {occurrence_id}")
        occurrence_ids.add(occurrence_id)
        unit_id = non_empty_string(occurrence["translation_unit_id"], f"{label}.translation_unit_id")
        if unit_id not in units:
            raise ManifestError(f"{label}: unknown translation unit: {unit_id}")
        for field in ("slide_index", "shape_id", "paragraph_index"):
            positive_int(occurrence[field], f"{label}.{field}")
        if occurrence["kind"] == "ppt_table_cell":
            for field in ("row", "column", "package_paragraph_index"):
                if field not in occurrence:
                    raise ManifestError(f"{label}: missing field: {field}")
                positive_int(occurrence[field], f"{label}.{field}")
        tokens = string_list(occurrence["protected_tokens"], f"{label}.protected_tokens")
        unit = units[unit_id]
        if occurrence["source_text"] != unit["source_text"] or tokens != unit["protected_tokens"]:
            raise ManifestError(f"{label}: occurrence does not match translation unit {unit_id}")

    seen_hashes: set[str] = set()
    overlay_images = skipped_target_images = skipped_unclear_images = 0
    for index, group in enumerate(data["image_groups"], start=1):
        label = f"image_groups[{index}]"
        if not isinstance(group, dict):
            raise ManifestError(f"{label}: expected an object")
        digest = non_empty_string(group.get("sha256"), f"{label}.sha256")
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest.lower()):
            raise ManifestError(f"{label}.sha256: expected 64 hexadecimal digits")
        if digest in seen_hashes:
            raise ManifestError(f"{label}: duplicate image sha256: {digest}")
        seen_hashes.add(digest)
        decision = non_empty_string(group.get("decision"), f"{label}.decision")
        if decision == "pending" and require_translations:
            raise ManifestError(f"{label}: image decision is still pending")
        if decision not in {"pending", "skip_target", "skip_unclear", "overlay"}:
            raise ManifestError(f"{label}.decision: unsupported decision: {decision}")
        overlay_ids = string_list(group.get("overlay_ids", []), f"{label}.overlay_ids")
        if decision in {"skip_target", "skip_unclear"}:
            if overlay_ids:
                raise ManifestError(f"{label}.overlay_ids: skipped images cannot have overlays")
            skipped_target_images += decision == "skip_target"
            skipped_unclear_images += decision == "skip_unclear"
        elif decision == "overlay":
            if group.get("preserve_source_image") is not True:
                raise ManifestError(f"{label}.preserve_source_image: expected true")
            if not overlay_ids:
                raise ManifestError(f"{label}.overlay_ids: expected at least one overlay")
            for overlay_id in overlay_ids:
                overlay = overlays_by_id.get(overlay_id)
                if overlay is None:
                    raise ManifestError(f"{label}.overlay_ids: unknown overlay: {overlay_id}")
                if overlay.get("kind") != "office_overlay":
                    raise ManifestError(f"overlays[{overlay_id}].kind: expected office_overlay")
                if overlay.get("localization_mode") != "bilingual_below":
                    raise ManifestError(f"overlays[{overlay_id}].localization_mode: expected bilingual_below")
            overlay_images += 1

    embedded_objects = data.get("embedded_objects", [])
    if not isinstance(embedded_objects, list):
        raise ManifestError("embedded_objects: expected an array")
    warnings: list[str] = []
    preserved_embedded_objects = 0
    for index, embedded in enumerate(embedded_objects, start=1):
        if not isinstance(embedded, dict):
            raise ManifestError(f"embedded_objects[{index}]: expected an object")
        status = embedded.get("status", "preserved_untranslated")
        prog_id = embedded.get("prog_id", "unknown")
        if status == "preserved_untranslated":
            preserved_embedded_objects += 1
            warnings.append(f"embedded object {prog_id} preserved without translation")
        elif status == "pending_native_handler" and require_translations:
            raise ManifestError(
                f"embedded object {prog_id} requires its native handler before delivery"
            )
        elif status not in {"pending_native_handler", "translated"}:
            raise ManifestError(
                f"embedded_objects[{index}].status: unsupported status: {status}"
            )

    return {
        "source_file": data["source_file"],
        "format": "powerpoint",
        "occurrences": len(data["occurrences"]),
        "translation_units": len(units),
        "image_groups": len(data["image_groups"]),
        "overlay_images": overlay_images,
        "skipped_target_images": skipped_target_images,
        "skipped_unclear_images": skipped_unclear_images,
        "translated": translated,
        "untranslated": len(units) - translated,
        "embedded_objects": len(embedded_objects),
        "preserved_embedded_objects": preserved_embedded_objects,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--require-translations", action="store_true")
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
