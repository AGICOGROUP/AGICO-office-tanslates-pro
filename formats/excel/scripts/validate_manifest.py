#!/usr/bin/env python3
"""Validate an Excel translation manifest before workbook mutation."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any


def validate(payload: Any) -> dict:
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
