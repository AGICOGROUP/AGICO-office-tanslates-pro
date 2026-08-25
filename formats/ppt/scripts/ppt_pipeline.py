#!/usr/bin/env python3
"""Run the single resumable PowerPoint translation pipeline."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

from inspect_pptx_package import InspectionError, inspect_package


STAGES = (
    "preflight",
    "inspect",
    "prepare",
    "translate",
    "validate",
    "apply",
    "verify",
    "render",
    "deliver",
)


class PipelineError(RuntimeError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def safe_reuse_key(occurrence: dict, target_language: str) -> str:
    payload = {
        "source_text": occurrence["source_text"],
        "target_language": target_language,
        "role": occurrence.get("role", "unknown"),
        "context_signature": occurrence.get("context_signature", "unknown"),
        "protected_tokens": occurrence.get("protected_tokens", []),
    }
    return sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def build_translation_manifest(
    inventory: dict, target_language: str, source_language: str = "auto"
) -> dict:
    units_by_key: dict[str, dict] = {}
    occurrences: list[dict] = []
    for source in inventory.get("occurrences", []):
        reuse_key = safe_reuse_key(source, target_language)
        unit = units_by_key.get(reuse_key)
        if unit is None:
            unit = {
                "id": f"tu-{reuse_key[:16]}",
                "reuse_key": reuse_key,
                "source_text": source["source_text"],
                "translation": "",
                "role": source.get("role", "unknown"),
                "context_signature": source.get("context_signature", "unknown"),
                "protected_tokens": list(source.get("protected_tokens", [])),
                "occurrence_count": 0,
            }
            units_by_key[reuse_key] = unit
        unit["occurrence_count"] += 1
        occurrence = dict(source)
        occurrence["translation_unit_id"] = unit["id"]
        occurrences.append(occurrence)

    return {
        "schema_version": 2,
        "source_file": inventory["source_file"],
        "source_path": inventory.get("source_path", ""),
        "source_sha256": inventory["source_sha256"],
        "source_language": source_language,
        "target_language": target_language,
        "format": "powerpoint",
        "occurrences": occurrences,
        "translation_units": list(units_by_key.values()),
        "image_groups": inventory.get("image_groups", []),
        "risk_plan": inventory.get(
            "risk_plan",
            {"route": "strict", "complex_reasons": [], "strict_reasons": ["missing-risk-plan"]},
        ),
    }


def new_state(inventory: dict, target_language: str) -> dict:
    return {
        "schema_version": 1,
        "source_file": inventory["source_file"],
        "source_path": inventory.get("source_path", ""),
        "source_sha256": inventory["source_sha256"],
        "target_language": target_language,
        "route": inventory.get("risk_plan", {}).get("route", "strict"),
        "stages": {stage: {"completed": False, "artifact": None} for stage in STAGES},
        "metrics": {
            "package_passes": inventory.get("metrics", {}).get("package_passes", 0),
            "powerpoint_starts": 0,
            "presentation_opens": 0,
            "full_deck_passes": inventory.get("metrics", {}).get("package_passes", 0),
        },
    }


def mark_stage(state: dict, stage: str, artifact: str | None = None) -> None:
    if stage not in STAGES:
        raise PipelineError(f"unknown stage: {stage}")
    state["stages"][stage] = {"completed": True, "artifact": artifact}


def first_incomplete_stage(state: dict) -> str | None:
    for stage in STAGES:
        if not state["stages"][stage]["completed"]:
            return stage
    return None


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise PipelineError(f"required artifact not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(f"invalid JSON artifact {path}: {exc}") from exc


def command_inspect(args: argparse.Namespace) -> int:
    inventory = inspect_package(args.input)
    state = new_state(inventory, args.target_language)
    mark_stage(state, "preflight")
    inventory_path = args.job_dir / "inventory.json"
    write_json(inventory_path, inventory)
    mark_stage(state, "inspect", str(inventory_path))
    write_json(args.job_dir / "job-state.json", state)
    print(json.dumps({"route": state["route"], "next_stage": first_incomplete_stage(state)}))
    return 0


def command_prepare(args: argparse.Namespace) -> int:
    inventory = read_json(args.job_dir / "inventory.json")
    state = read_json(args.job_dir / "job-state.json")
    manifest = build_translation_manifest(
        inventory,
        state["target_language"],
        args.source_language,
    )
    manifest_path = args.job_dir / "translation-manifest.json"
    write_json(manifest_path, manifest)
    mark_stage(state, "prepare", str(manifest_path))
    write_json(args.job_dir / "job-state.json", state)
    print(
        json.dumps(
            {
                "occurrences": len(manifest["occurrences"]),
                "translation_units": len(manifest["translation_units"]),
                "next_stage": "translate",
            }
        )
    )
    return 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("--input", required=True, type=Path)
    inspect_parser.add_argument("--job-dir", required=True, type=Path)
    inspect_parser.add_argument("--target-language", required=True)
    inspect_parser.set_defaults(handler=command_inspect)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--job-dir", required=True, type=Path)
    prepare_parser.add_argument("--source-language", default="auto")
    prepare_parser.set_defaults(handler=command_prepare)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return int(args.handler(args))
    except (PipelineError, InspectionError) as exc:
        print(f"pipeline error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
