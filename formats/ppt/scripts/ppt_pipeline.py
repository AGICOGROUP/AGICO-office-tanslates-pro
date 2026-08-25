#!/usr/bin/env python3
"""Run the single resumable PowerPoint translation pipeline."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

from inspect_pptx_package import InspectionError, inspect_package, sha256_file
from pptx_ooxml import OoxmlError, apply_manifest
from validate_manifest import ManifestError, validate_manifest


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

    image_groups = []
    for source_group in inventory.get("image_groups", []):
        group = dict(source_group)
        group.pop("screening_status", None)
        group.pop("text_screening", None)
        group.pop("reason_code", None)
        group["decision"] = "pending"
        group["overlay_ids"] = []
        image_groups.append(group)

    embedded_objects = []
    for source_object in inventory.get("embedded_objects", []):
        embedded = dict(source_object)
        embedded["status"] = "pending_native_handler"
        embedded_objects.append(embedded)

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
        "image_groups": image_groups,
        "embedded_objects": embedded_objects,
        "overlays": [],
    }


def new_state(inventory: dict, target_language: str) -> dict:
    return {
        "schema_version": 1,
        "source_file": inventory["source_file"],
        "source_path": inventory.get("source_path", ""),
        "source_sha256": inventory["source_sha256"],
        "target_language": target_language,
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


def verify_localized_image_hashes(manifest: dict, output_inventory: dict) -> list[dict]:
    output_hashes = {
        str(group.get("sha256", ""))
        for group in output_inventory.get("image_groups", [])
    }
    return [
        {"code": "overlay-image-changed", "sha256": str(group["sha256"])}
        for group in manifest.get("image_groups", [])
        if group.get("decision") == "overlay"
        and str(group.get("sha256", "")) not in output_hashes
    ]


def complete_delivery(
    state: dict, output: Path, *, visual_review_passed: bool
) -> None:
    if not state["stages"]["render"]["completed"]:
        raise PipelineError("render stage must pass before delivery")
    if not visual_review_passed:
        raise PipelineError("visual review must pass before delivery")
    if not output.is_file():
        raise PipelineError(f"translated presentation not found: {output}")
    mark_stage(state, "deliver", str(output.resolve()))


def build_render_plan(inventory: dict, verification_passed: bool) -> dict:
    all_slides = [int(item["index"]) for item in inventory.get("slides", [])]
    return {
        "mode": "single",
        "target_low_resolution": all_slides,
        "source_high_resolution": [],
        "target_high_resolution": [],
        "verification_passed": verification_passed,
    }


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
    source = args.input.resolve()
    working_source = source
    legacy_converted = False
    if source.suffix.lower() == ".ppt":
        powershell = shutil.which("powershell.exe")
        if not powershell:
            raise PipelineError("legacy .ppt conversion requires Microsoft PowerPoint")
        args.job_dir.mkdir(parents=True, exist_ok=True)
        working_source = (args.job_dir / "working-source.pptx").resolve()
        completed = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(Path(__file__).with_name("ppt_com.ps1")),
                "-Command",
                "convert",
                "-InputPath",
                str(source),
                "-OutputPath",
                str(working_source),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if completed.returncode != 0:
            raise PipelineError(completed.stderr.strip() or "legacy .ppt conversion failed")
        legacy_converted = True
    elif source.suffix.lower() != ".pptx":
        raise PipelineError("PowerPoint pipeline supports only .ppt and .pptx")

    inventory = inspect_package(working_source)
    inventory["source_file"] = source.name
    inventory["source_path"] = str(source)
    if legacy_converted:
        # inspect_package hashed the converted working copy; hash the immutable
        # legacy source once because it is the file verified at delivery.
        inventory["source_sha256"] = sha256_file(source)
    inventory["working_source_path"] = str(working_source)
    state = new_state(inventory, args.target_language)
    if legacy_converted:
        state["metrics"]["powerpoint_starts"] = 1
        state["metrics"]["presentation_opens"] = 1
        state["metrics"]["full_deck_passes"] += 1
    mark_stage(state, "preflight")
    inventory_path = args.job_dir / "inventory.json"
    write_json(inventory_path, inventory)
    mark_stage(state, "inspect", str(inventory_path))
    write_json(args.job_dir / "job-state.json", state)
    print(json.dumps({"next_stage": first_incomplete_stage(state)}))
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


def command_apply(args: argparse.Namespace) -> int:
    source = args.input.resolve()
    output = args.output.resolve()
    if source == output:
        raise PipelineError("refusing to overwrite the source presentation")
    inventory = read_json(args.job_dir / "inventory.json")
    state = read_json(args.job_dir / "job-state.json")
    manifest_path = args.job_dir / "translation-manifest.json"
    validation = validate_manifest(manifest_path, require_translations=True)
    mutation_source = Path(inventory.get("working_source_path", str(source))).resolve()
    if not mutation_source.is_file():
        raise PipelineError(f"working source not found: {mutation_source}")
    mark_stage(state, "translate", str(manifest_path))
    mark_stage(state, "validate", str(manifest_path))

    if int(validation.get("overlay_images", 0)) == 0:
        apply_report = apply_manifest(mutation_source, manifest_path, output)
        apply_report["engine"] = "ooxml"
    else:
        powershell = shutil.which("powershell.exe")
        if not powershell:
            raise PipelineError("Microsoft PowerPoint COM requires powershell.exe")
        command = [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(Path(__file__).with_name("ppt_com.ps1")),
            "-Command",
            "apply",
            "-InputPath",
            str(mutation_source),
            "-OutputPath",
            str(output),
            "-ManifestPath",
            str(manifest_path),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
        if completed.returncode != 0:
            raise PipelineError(completed.stderr.strip() or "PowerPoint COM apply failed")
        try:
            apply_report = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise PipelineError("PowerPoint COM apply returned invalid JSON") from exc
        apply_report["engine"] = "powerpoint-com"
        state["metrics"]["powerpoint_starts"] += 1
        state["metrics"]["presentation_opens"] += 2

    apply_report["manifest_validation"] = validation
    report_path = args.job_dir / "apply-report.json"
    write_json(report_path, apply_report)
    mark_stage(state, "apply", str(report_path))
    state["output_path"] = str(output)
    write_json(args.job_dir / "job-state.json", state)
    print(json.dumps(apply_report, ensure_ascii=False))
    return 0


def command_verify(args: argparse.Namespace) -> int:
    source = args.source.resolve()
    output = args.output.resolve()
    inventory = read_json(args.job_dir / "inventory.json")
    state = read_json(args.job_dir / "job-state.json")
    manifest = read_json(args.job_dir / "translation-manifest.json")
    errors: list[dict] = []
    if sha256_file(source) != inventory["source_sha256"]:
        errors.append({"code": "source-hash-mismatch"})
    output_inventory = inspect_package(output)
    errors.extend(verify_localized_image_hashes(manifest, output_inventory))
    if len(output_inventory["slides"]) != len(inventory["slides"]):
        errors.append(
            {
                "code": "slide-count-mismatch",
                "source": len(inventory["slides"]),
                "output": len(output_inventory["slides"]),
            }
        )
    units = {item["id"]: item for item in manifest["translation_units"]}
    output_by_id = {item["id"]: item for item in output_inventory["occurrences"]}
    for occurrence in manifest["occurrences"]:
        actual = output_by_id.get(occurrence["id"])
        expected = str(units[occurrence["translation_unit_id"]]["translation"]).strip()
        if actual is None:
            errors.append({"code": "missing-occurrence", "id": occurrence["id"]})
            continue
        actual_text = str(actual["source_text"]).strip()
        if actual_text != expected:
            errors.append(
                {
                    "code": "translation-mismatch",
                    "id": occurrence["id"],
                    "expected": expected,
                    "actual": actual_text,
                }
            )
        for token in occurrence.get("protected_tokens", []):
            if token not in actual_text:
                errors.append(
                    {"code": "protected-token-missing", "id": occurrence["id"], "token": token}
                )
    passed = not errors
    report = {
        "passed": passed,
        "source_file": source.name,
        "output_file": output.name,
        "source_sha256": inventory["source_sha256"],
        "output_sha256": output_inventory["source_sha256"],
        "occurrences_expected": len(manifest["occurrences"]),
        "occurrences_verified": len(manifest["occurrences"])
        - sum(1 for error in errors if error["code"] in {"missing-occurrence", "translation-mismatch"}),
        "errors": errors,
    }
    report_path = args.job_dir / "verification.json"
    write_json(report_path, report)
    render_plan = build_render_plan(inventory, passed)
    render_plan_path = args.job_dir / "render-plan.json"
    write_json(render_plan_path, render_plan)
    mark_stage(state, "verify", str(report_path))
    write_json(args.job_dir / "job-state.json", state)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if passed else 2


def run_office_export(
    input_path: Path,
    pdf_path: Path,
    thumbnail_directory: Path,
    high_resolution_slides: list[int],
) -> dict:
    powershell = shutil.which("powershell.exe")
    if not powershell:
        raise PipelineError("Microsoft PowerPoint verification requires powershell.exe")
    script = Path(__file__).resolve().parents[3] / "scripts" / "office_com_pdf.ps1"
    command = [
        powershell,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-InputPath",
        str(input_path),
        "-OutputPdf",
        str(pdf_path),
        "-Application",
        "powerpoint",
        "-ThumbnailDirectory",
        str(thumbnail_directory),
        "-HighResolutionSlides",
        ",".join(str(index) for index in high_resolution_slides),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if completed.returncode != 0:
        raise PipelineError(completed.stderr.strip() or "PowerPoint verification export failed")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise PipelineError("PowerPoint verification returned invalid JSON") from exc


def command_render(args: argparse.Namespace) -> int:
    source = args.source.resolve()
    output = args.output.resolve()
    state = read_json(args.job_dir / "job-state.json")
    verification = read_json(args.job_dir / "verification.json")
    plan = read_json(args.job_dir / "render-plan.json")
    if not verification.get("passed"):
        raise PipelineError("structural verification failed; repair before final Office rendering")
    render_root = args.job_dir / "final-renders"
    target_report = run_office_export(
        output,
        args.job_dir / "final.pdf",
        render_root / "target",
        plan["target_high_resolution"],
    )
    reports = {"target": target_report}
    state["metrics"]["powerpoint_starts"] += int(target_report["powerpoint_starts"])
    state["metrics"]["presentation_opens"] += int(target_report["presentation_opens"])
    state["metrics"]["full_deck_passes"] += 1
    if plan["source_high_resolution"]:
        source_report = run_office_export(
            source,
            args.job_dir / "source-baseline.pdf",
            render_root / "source",
            plan["source_high_resolution"],
        )
        reports["source"] = source_report
        state["metrics"]["powerpoint_starts"] += int(source_report["powerpoint_starts"])
        state["metrics"]["presentation_opens"] += int(source_report["presentation_opens"])
        state["metrics"]["full_deck_passes"] += 1
    office_report_path = args.job_dir / "office-verification.json"
    write_json(office_report_path, reports)
    mark_stage(state, "render", str(office_report_path))
    write_json(args.job_dir / "job-state.json", state)
    print(json.dumps(reports, ensure_ascii=False))
    return 0


def command_deliver(args: argparse.Namespace) -> int:
    output = args.output.resolve()
    state_path = args.job_dir / "job-state.json"
    state = read_json(state_path)
    complete_delivery(
        state,
        output,
        visual_review_passed=args.visual_review_passed,
    )
    write_json(state_path, state)
    print(json.dumps({"delivered": str(output)}, ensure_ascii=False))
    return 0


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
    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("--input", required=True, type=Path)
    apply_parser.add_argument("--job-dir", required=True, type=Path)
    apply_parser.add_argument("--output", required=True, type=Path)
    apply_parser.set_defaults(handler=command_apply)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--source", required=True, type=Path)
    verify_parser.add_argument("--job-dir", required=True, type=Path)
    verify_parser.add_argument("--output", required=True, type=Path)
    verify_parser.set_defaults(handler=command_verify)
    render_parser = subparsers.add_parser("render")
    render_parser.add_argument("--source", required=True, type=Path)
    render_parser.add_argument("--job-dir", required=True, type=Path)
    render_parser.add_argument("--output", required=True, type=Path)
    render_parser.set_defaults(handler=command_render)
    deliver_parser = subparsers.add_parser("deliver")
    deliver_parser.add_argument("--job-dir", required=True, type=Path)
    deliver_parser.add_argument("--output", required=True, type=Path)
    deliver_parser.add_argument("--visual-review-passed", action="store_true")
    deliver_parser.set_defaults(handler=command_deliver)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return int(args.handler(args))
    except (PipelineError, InspectionError, ManifestError, OoxmlError) as exc:
        print(f"pipeline error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
