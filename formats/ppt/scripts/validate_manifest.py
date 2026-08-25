#!/usr/bin/env python3
"""Validate the schema-v2 PowerPoint translation manifest."""

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
        "source_file",
        "source_sha256",
        "source_language",
        "target_language",
        "format",
        "occurrences",
        "translation_units",
        "image_groups",
        "risk_plan",
    ):
        if field not in data:
            raise ManifestError(f"missing top-level field: {field}")
    non_empty_string(data["source_file"], "source_file")
    source_sha = non_empty_string(data["source_sha256"], "source_sha256")
    if len(source_sha) != 64 or any(character not in "0123456789abcdef" for character in source_sha.lower()):
        raise ManifestError("source_sha256: expected 64 hexadecimal digits")
    non_empty_string(data["source_language"], "source_language")
    non_empty_string(data["target_language"], "target_language")
    if data["format"] != "powerpoint":
        raise ManifestError("format: expected powerpoint")
    if not isinstance(data["translation_units"], list):
        raise ManifestError("translation_units: expected an array")
    if not isinstance(data["occurrences"], list):
        raise ManifestError("occurrences: expected an array")
    if not isinstance(data["image_groups"], list):
        raise ManifestError("image_groups: expected an array")
    if not isinstance(data["risk_plan"], dict):
        raise ManifestError("risk_plan: expected an object")

    overlays = data.get("overlays", [])
    if not isinstance(overlays, list):
        raise ManifestError("overlays: expected an array")
    overlay_ids: set[str] = set()
    overlays_by_id: dict[str, dict] = {}
    for index, overlay in enumerate(overlays, start=1):
        label = f"overlays[{index}]"
        if not isinstance(overlay, dict):
            raise ManifestError(f"{label}: expected an object")
        overlay_id = non_empty_string(overlay.get("id"), f"{label}.id")
        if overlay_id in overlay_ids:
            raise ManifestError(f"{label}: duplicate id: {overlay_id}")
        overlay_ids.add(overlay_id)
        overlays_by_id[overlay_id] = overlay

    units: dict[str, dict] = {}
    translated = 0
    for index, unit in enumerate(data["translation_units"], start=1):
        label = f"translation_units[{index}]"
        if not isinstance(unit, dict):
            raise ManifestError(f"{label}: expected an object")
        for field in (
            "id",
            "source_text",
            "translation",
            "role",
            "context_signature",
            "protected_tokens",
        ):
            if field not in unit:
                raise ManifestError(f"{label}: missing field: {field}")
        unit_id = non_empty_string(unit["id"], f"{label}.id")
        if unit_id in units:
            raise ManifestError(f"{label}: duplicate id: {unit_id}")
        non_empty_string(unit["source_text"], f"{label}.source_text")
        if not isinstance(unit["translation"], str):
            raise ManifestError(f"{label}.translation: expected a string")
        non_empty_string(unit["role"], f"{label}.role")
        non_empty_string(unit["context_signature"], f"{label}.context_signature")
        protected_tokens = string_list(
            unit["protected_tokens"], f"{label}.protected_tokens"
        )
        if unit["translation"].strip():
            if require_translations:
                for token in protected_tokens:
                    if token not in unit["translation"]:
                        raise ManifestError(
                            f"{label}: protected token missing from translation: {token}"
                        )
            translated += 1
        elif require_translations:
            raise ManifestError(f"{label}: empty translation: {unit_id}")
        units[unit_id] = unit

    seen_occurrences: set[str] = set()
    for index, occurrence in enumerate(data["occurrences"], start=1):
        label = f"occurrences[{index}]"
        if not isinstance(occurrence, dict):
            raise ManifestError(f"{label}: expected an object")
        for field in (
            "id",
            "kind",
            "source_text",
            "translation_unit_id",
            "slide_index",
            "shape_id",
            "paragraph_index",
            "role",
            "context_signature",
            "protected_tokens",
        ):
            if field not in occurrence:
                raise ManifestError(f"{label}: missing field: {field}")
        occurrence_id = non_empty_string(occurrence["id"], f"{label}.id")
        if occurrence_id in seen_occurrences:
            raise ManifestError(f"{label}: duplicate id: {occurrence_id}")
        seen_occurrences.add(occurrence_id)
        non_empty_string(occurrence["kind"], f"{label}.kind")
        non_empty_string(occurrence["source_text"], f"{label}.source_text")
        unit_id = non_empty_string(
            occurrence["translation_unit_id"], f"{label}.translation_unit_id"
        )
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

    seen_image_hashes: set[str] = set()
    localized_images = 0
    skipped_target_language_images = 0
    covered_image_labels = 0
    for index, group in enumerate(data["image_groups"], start=1):
        label = f"image_groups[{index}]"
        if not isinstance(group, dict):
            raise ManifestError(f"{label}: expected an object")
        digest = non_empty_string(group.get("sha256"), f"{label}.sha256")
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest.lower()):
            raise ManifestError(f"{label}.sha256: expected 64 hexadecimal digits")
        if digest in seen_image_hashes:
            raise ManifestError(f"{label}: duplicate image sha256: {digest}")
        seen_image_hashes.add(digest)
        status = non_empty_string(
            group.get("screening_status"), f"{label}.screening_status"
        )
        if status not in {"pending", "retain", "localize", "manual_review"}:
            raise ManifestError(f"{label}.screening_status: unsupported status: {status}")
        if require_translations and status == "pending":
            raise ManifestError(f"{label}: image screening is still pending")
        screening = group.get("text_screening")
        if require_translations and not isinstance(screening, dict):
            raise ManifestError(f"{label}.text_screening: expected an object")
        if isinstance(screening, dict):
            if screening.get("method") != "single-pass-ocr-and-visual":
                raise ManifestError(
                    f"{label}.text_screening.method: expected single-pass-ocr-and-visual"
                )
            source_detected = screening.get("source_language_text_detected")
            target_present = screening.get("target_language_present")
            if not isinstance(source_detected, bool) or not isinstance(target_present, bool):
                raise ManifestError(
                    f"{label}.text_screening: detection flags must be boolean"
                )
            labels = screening.get("labels")
            if not isinstance(labels, list):
                raise ManifestError(f"{label}.text_screening.labels: expected an array")
            if source_detected and not labels:
                raise ManifestError(
                    f"{label}.text_screening.labels: detected source text requires labels"
                )
            if not source_detected and labels:
                raise ManifestError(
                    f"{label}.text_screening.labels: labels contradict detection result"
                )
            for label_index, text_label in enumerate(labels, start=1):
                item_label = f"{label}.text_screening.labels[{label_index}]"
                if not isinstance(text_label, dict):
                    raise ManifestError(f"{item_label}: expected an object")
                non_empty_string(text_label.get("id"), f"{item_label}.id")
                non_empty_string(text_label.get("source_text"), f"{item_label}.source_text")
                label_status = non_empty_string(
                    text_label.get("status"), f"{item_label}.status"
                )
                allowed_label_statuses = {
                    "localized", "target-language-already-present", "manual_review"
                }
                if label_status not in allowed_label_statuses:
                    raise ManifestError(
                        f"{item_label}.status: incomplete image-label coverage: {label_status}"
                    )
                if label_status == "localized":
                    non_empty_string(
                        text_label.get("translation"), f"{item_label}.translation"
                    )
                    overlay_id = non_empty_string(
                        text_label.get("overlay_id"), f"{item_label}.overlay_id"
                    )
                    if overlay_id not in overlay_ids:
                        raise ManifestError(f"{item_label}.overlay_id: unknown overlay: {overlay_id}")
                covered_image_labels += 1
            if status == "retain" and source_detected:
                if group.get("reason_code") != "target-language-already-present":
                    raise ManifestError(
                        f"{label}.reason_code: source-labels-covered-by-native-text is not allowed; "
                        "detected image text needs its own target-language status"
                    )
                if not target_present or any(
                    item.get("status") != "target-language-already-present" for item in labels
                ):
                    raise ManifestError(
                        f"{label}: retained source-language image is not fully target-language complete"
                    )
        if status in {"retain", "manual_review"}:
            non_empty_string(group.get("reason_code"), f"{label}.reason_code")
        if status == "localize":
            localization_mode = group.get("localization_mode")
            if localization_mode not in {"bilingual_below", "text_region_replace"}:
                raise ManifestError(
                    f"{label}.localization_mode: expected bilingual_below or text_region_replace"
                )
            if group.get("preserve_source_image") is not True:
                raise ManifestError(
                    f"{label}.preserve_source_image: expected true"
                )
            referenced_overlays = string_list(
                group.get("overlay_ids"), f"{label}.overlay_ids"
            )
            if not referenced_overlays:
                raise ManifestError(f"{label}.overlay_ids: expected at least one overlay")
            unknown_overlays = sorted(set(referenced_overlays) - overlay_ids)
            if unknown_overlays:
                raise ManifestError(
                    f"{label}.overlay_ids: unknown overlays: {', '.join(unknown_overlays)}"
                )
            if localization_mode == "text_region_replace":
                pixel_check = group.get("outside_mask_pixel_check")
                if (
                    not isinstance(pixel_check, dict)
                    or pixel_check.get("passed") is not True
                    or pixel_check.get("changed_pixels") != 0
                ):
                    raise ManifestError(
                        f"{label}.outside_mask_pixel_check: expected passed=true and changed_pixels=0"
                    )
                for overlay_id in referenced_overlays:
                    overlay = overlays_by_id[overlay_id]
                    if overlay.get("localization_mode") != "text_region_replace":
                        raise ManifestError(
                            f"overlays[{overlay_id}].localization_mode: expected text_region_replace"
                        )
                    background = overlay.get("background")
                    if not isinstance(background, dict) or background.get("mode") != "image_patch":
                        raise ManifestError(
                            f"overlays[{overlay_id}].background.mode: expected image_patch"
                        )
                    if overlay.get("source_region") != overlay.get("region"):
                        raise ManifestError(
                            f"overlays[{overlay_id}]: replacement region must equal source_region"
                        )
            localized_images += 1
        elif (
            status == "retain"
            and group.get("reason_code") == "target-language-already-present"
        ):
            skipped_target_language_images += 1

    return {
        "source_file": data["source_file"],
        "format": "powerpoint",
        "occurrences": len(data["occurrences"]),
        "translation_units": len(units),
        "image_groups": len(data["image_groups"]),
        "localized_images": localized_images,
        "skipped_target_language_images": skipped_target_language_images,
        "covered_image_labels": covered_image_labels,
        "translated": translated,
        "untranslated": len(units) - translated,
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
