"""Shared translation decisions, bounded batches and atomic task artifacts.

Format adapters retain their own manifests. Only this boundary knows their field
names; the translator uses the same compact decision protocol for all formats.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from translation_quality import technical_mismatch

FIELDS = {"word": ("units", "source", "target"),
          "excel": ("translation_units", "source", "translation"),
          "ppt": ("translation_units", "source_text", "translation")}


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def manifest_identity(manifest: dict, format_name: str) -> str:
    collection, source_field, _ = FIELDS[format_name]
    return fingerprint({"format": format_name, "source": manifest.get("source_sha256"),
                        "language": manifest.get("target_language"),
                        "units": [{key: unit.get(key) for key in
                                   ("id", source_field, "context", "context_key", "context_signature")}
                                  for unit in manifest.get(collection, [])]})


def decision_error(source: str, target: str, format_name: str, protected_tokens=()) -> str | None:
    if not isinstance(target, str) or not target.strip():
        return "translation required"
    if technical_mismatch(source, target, protected_tokens):
        return "technical values, units or identifiers changed; preserve the source values"
    if format_name == "word" and re.findall(r"[\t\n]", source) != re.findall(r"[\t\n]", target):
        return "preserve Word tab and line-break boundaries"
    if format_name != "word" and source.count("\n") > target.count("\n"):
        return "source line breaks are missing"
    return None


def build_worklist(manifest: dict, format_name: str, max_chars: int = 12000) -> dict:
    if max_chars < 1:
        raise ValueError("batch character budget must be positive")
    collection, source_field, target_field = FIELDS[format_name]
    units, batches, ids, size = [], [], [], 0
    for unit in manifest.get(collection, []):
        target = unit.get(target_field, "")
        error = unit.get("translation_error") or decision_error(unit[source_field], target, format_name, unit.get("protected_tokens", []))
        if not error:
            continue
        record = {"id": unit["id"], "source": unit[source_field], "translation": target,
                  "status": "pending", "context": unit.get("context", unit.get("context_key", unit.get("context_signature", ""))),
                  "protected_tokens": unit.get("protected_tokens", []),
                  "occurrence_count": unit.get("occurrence_count", 1)}
        if target or unit.get("translation_error"):
            record["error"] = error
        units.append(record)
        cost = len(record["source"]) + len(str(record["context"]))
        if ids and size + cost > max_chars:
            batches.append({"unit_ids": ids, "characters": size})
            ids, size = [], 0
        ids.append(unit["id"])
        size += cost
    if ids:
        batches.append({"unit_ids": ids, "characters": size})
    return {"schema_version": 2, "format": format_name,
            "job_identity": manifest_identity(manifest, format_name),
            "target_language": manifest.get("target_language"),
            "pending_count": len(units), "translation_units": units, "batches": batches}


def merge_decisions(manifest: dict, worklist: dict, format_name: str) -> tuple[dict, dict]:
    if worklist.get("job_identity") != manifest_identity(manifest, format_name):
        raise ValueError("worklist identity differs from the prepared job; use its current worklist")
    result = deepcopy(manifest)
    collection, source_field, target_field = FIELDS[format_name]
    units = {unit["id"]: unit for unit in result.get(collection, [])}
    accepted, rejected = [], []
    raw_decisions = worklist.get("translation_units", [])
    if not isinstance(raw_decisions, list):
        rejected.append({"id": None, "error": "translation_units must be an array"})
        raw_decisions = []
    decisions = []
    for decision in raw_decisions:
        if not isinstance(decision, dict) or type(decision.get("id")) not in {str, int}:
            rejected.append({"id": None, "error": "each decision needs an object with a string or integer id"})
        else:
            decisions.append(decision)
    counts = Counter(decision.get("id") for decision in decisions)
    for decision in decisions:
        unit_id = decision.get("id")
        unit = units.get(unit_id)
        error = None
        target = decision.get("translation", "")
        # A stale batch often includes blank placeholders for units accepted by
        # an earlier batch. They are absence of a decision, not a rollback.
        if unit is not None and not target and decision.get("status", "pending") == "pending":
            continue
        if format_name == "word" and isinstance(target, str):
            target = target.strip()
        if counts[unit_id] != 1:
            error = "duplicate decision ID; submit one decision per unit"
        elif unit is None:
            error = "unknown decision ID"
        elif decision.get("source") != unit[source_field]:
            error = "source text changed; edit translation only"
        else:
            error = decision_error(unit[source_field], target, format_name, unit.get("protected_tokens", []))
        if error:
            rejected.append({"id": unit_id, "error": error})
            if unit is not None:
                unit["translation_error"] = error
            continue
        unit[target_field] = target
        unit["status"] = "retain" if target == unit[source_field] else "translated"
        if unit["status"] == "retain":
            unit["reason"] = decision.get("reason") or "Reviewed: source is appropriate in the target document"
        unit.pop("translation_error", None)
        accepted.append(unit_id)
    remaining = build_worklist(result, format_name)["pending_count"]
    return result, {"accepted": accepted, "rejected": rejected, "pending_count": remaining,
                    "ready": remaining == 0 and not rejected}
