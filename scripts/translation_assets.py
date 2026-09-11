"""Compact image decisions for the common task interface."""
from copy import deepcopy
from pathlib import Path
import math
from zipfile import ZipFile

from translation_core import file_hash


def asset_field(format_name):
    return {"word": "image_reviews", "excel": "images", "ppt": "image_groups"}[format_name]


def prepare_assets(manifest, format_name, working, job_dir):
    if format_name == "word" and "image_reviews" not in manifest:
        grouped = {}
        for part, digest in manifest.get("media_sha256", {}).items():
            group = grouped.setdefault(digest, {"id": digest, "sha256": digest, "status": "pending", "media_paths": []})
            group["media_paths"].append(part)
        manifest["image_reviews"] = list(grouped.values())
    if format_name in {"word", "ppt"}:
        groups = manifest.get(asset_field(format_name), [])
        if groups:
            folder = job_dir / "images"
            folder.mkdir(exist_ok=True)
            with ZipFile(working) as archive:
                for group in groups:
                    paths = group.get("media_paths", [])
                    if paths:
                        output = folder / (group["sha256"] + Path(paths[0]).suffix)
                        if not output.exists():
                            output.write_bytes(archive.read(paths[0]))
                        group["source_image"] = str(output)
    return manifest


def pending_assets(manifest, format_name):
    pending = []
    field = "decision" if format_name == "ppt" else "status"
    accepted = {"skip_target", "skip_unclear", "overlay"} if format_name == "ppt" else {"reviewed", "localized", "retain"}
    for group in manifest.get(asset_field(format_name), []):
        if group.get(field) not in accepted or group.get("decision_error"):
            record = deepcopy(group)
            record["id"] = group.get("id", group["sha256"])
            if format_name == "ppt" and group.get("overlay_ids"):
                record["overlays"] = [deepcopy(item) for item in manifest.get("overlays", []) if item["id"] in group["overlay_ids"]]
            pending.append(record)
    return pending


def prepare_overlay(item):
    if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"].strip() or not item.get("translation"):
        raise ValueError("each overlay needs id and translation")
    overlay = deepcopy(item)
    location = overlay.get("location", {})
    if not isinstance(location, dict) or any(type(location.get(key)) is not int or location[key] < 1 for key in ("page_or_slide", "host_shape_id")):
        raise ValueError("overlay location needs positive page_or_slide and host_shape_id")
    for name in ("source_region", "region"):
        region = overlay.get(name, {})
        if not isinstance(region, dict) or any(type(region.get(key)) not in (int, float) or not math.isfinite(region[key]) for key in ("x", "y", "w", "h")):
            raise ValueError(f"overlay {name} needs finite x, y, w, h coordinates")
        if min(region["x"], region["y"]) < 0 or min(region["w"], region["h"]) <= 0 or region["x"] + region["w"] > 1 or region["y"] + region["h"] > 1:
            raise ValueError(f"overlay {name} must fit within the host image")
    if overlay["region"]["y"] + 1e-9 < overlay["source_region"]["y"] + overlay["source_region"]["h"]:
        raise ValueError("overlay region must be below the source label")
    overlay.setdefault("kind", "office_overlay")
    overlay.setdefault("localization_mode", "bilingual_below")
    overlay.setdefault("background", {"mode": "transparent"})
    overlay.setdefault("style", {"font_name": "Arial", "font_size_pt": 12, "bold": False, "text_rgb": "000000", "align": "left"})
    return overlay


def merge_assets(manifest, decisions, format_name):
    groups = {item.get("id", item["sha256"]): item for item in manifest.get(asset_field(format_name), [])}
    errors = []
    if not isinstance(decisions, list):
        return [{"id": None, "error": "images must be an array"}]
    for decision in decisions:
        if not isinstance(decision, dict) or not isinstance(decision.get("id"), str):
            errors.append({"id": None, "error": "each image decision needs an object with a string id"})
            continue
        key = decision.get("id")
        group = groups.get(key)
        try:
            if group is None or decision.get("sha256") != group["sha256"]:
                raise ValueError("image identity changed")
            field = "decision" if format_name == "ppt" else "status"
            value = decision.get(field)
            if value in {None, "pending", "manual-review"}:
                continue
            allowed = ({"skip_target", "skip_unclear", "overlay"} if format_name == "ppt" else
                       {"reviewed", "localized", "retain"} if format_name == "excel" else {"reviewed", "retain"})
            if value not in allowed:
                raise ValueError(f"use one of {', '.join(sorted(allowed))}")
            updates = {field: value}
            if value == "localized":
                replacement = Path(decision.get("replacement_path", ""))
                if not replacement.is_absolute() or not replacement.is_file():
                    raise ValueError("localized image needs an absolute replacement_path")
                updates.update(replacement_path=str(replacement), replacement_sha256=file_hash(replacement))
            if value == "overlay":
                overlays = decision.get("overlays", [])
                if not isinstance(overlays, list) or not overlays:
                    raise ValueError("overlay decision needs editable overlays with id and translation")
                overlays = [prepare_overlay(item) for item in overlays]
                ids = [item["id"] for item in overlays]
                if len(set(ids)) != len(ids):
                    raise ValueError("duplicate overlay IDs")
                old_ids = group.get("overlay_ids", [])
                existing = [item for item in manifest.get("overlays", []) if item["id"] not in old_ids]
                if set(ids) & {item["id"] for item in existing}:
                    raise ValueError("overlay IDs belong to another image")
                manifest["overlays"] = existing + deepcopy(overlays)
                updates["overlay_ids"] = ids
                updates["preserve_source_image"] = True
            elif format_name == "ppt":
                old_ids = set(group.get("overlay_ids", []))
                manifest["overlays"] = [item for item in manifest.get("overlays", []) if item["id"] not in old_ids]
                updates["overlay_ids"] = []
            group.update(updates)
            for optional in ("reason", "reason_code"):
                if optional in decision:
                    group[optional] = decision[optional]
            group.pop("decision_error", None)
        except (ValueError, OSError) as exc:
            errors.append({"id": key, "error": str(exc)})
            if group is not None:
                group["decision_error"] = str(exc)
    return errors
