#!/usr/bin/env python3
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PIPELINE = SCRIPTS / "excel_pipeline.mjs"
ROUTER = SCRIPTS / "route_excel_file.py"
GLOSSARY_RESOLVER = SCRIPTS / "resolve_repo_glossary.py"
CONVERTER = SCRIPTS / "excel_com_convert.ps1"
VALIDATOR = SCRIPTS / "validate_manifest.py"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_worklist(manifest: dict[str, Any]) -> dict[str, Any]:
    units = []
    for unit in manifest.get("translation_units", []):
        if unit.get("status") != "pending":
            continue
        units.append({
            "id": unit["id"],
            "source": unit["source"],
            "context_key": unit.get("context_key", "unknown"),
            "protected_tokens": list(unit.get("protected_tokens", [])),
            "status": "pending",
            "translation": "",
            "reason": "",
        })
    images = []
    for image in manifest.get("images", []):
        if image.get("status") == "manual-review":
            images.append({
                "id": image["id"],
                "sha256": image["sha256"],
                "occurrences": list(image.get("occurrences", [])),
                "status": "manual-review",
                "reason_code": "manual-review",
            })
    return {
        "schema_version": 1,
        "target_language": manifest.get("target_language"),
        "pending_count": len(units),
        "translation_units": units,
        "images": images,
    }


def apply_worklist(manifest: dict[str, Any], worklist: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(manifest)
    all_units = {unit["id"]: unit for unit in result.get("translation_units", [])}
    pending = {
        unit_id: unit
        for unit_id, unit in all_units.items()
        if unit.get("status") == "pending"
    }
    decisions: dict[str, dict[str, Any]] = {}
    for decision in worklist.get("translation_units", []):
        unit_id = decision.get("id")
        if not unit_id or unit_id in decisions:
            raise ValueError(f"missing or duplicate worklist id: {unit_id or '<empty>'}")
        if unit_id not in all_units:
            raise ValueError(f"unknown worklist id: {unit_id}")
        if decision.get("source") != all_units[unit_id].get("source"):
            raise ValueError(f"source mismatch for decision: {unit_id}")
        if unit_id not in pending:
            current = all_units[unit_id]
            same = (
                decision.get("status") == current.get("status")
                and decision.get("translation") == current.get("translation")
                and (
                    current.get("status") != "retain"
                    or str(decision.get("reason", "")).strip() == str(current.get("reason", "")).strip()
                )
            )
            if not same:
                raise ValueError(f"conflicting worklist decision: {unit_id}")
            decisions[unit_id] = decision
            continue
        decisions[unit_id] = decision

    missing = sorted(set(pending) - set(decisions))
    if missing:
        raise ValueError(f"missing worklist decisions: {', '.join(missing)}")
    for unit_id, decision in decisions.items():
        if unit_id not in pending:
            continue
        status = decision.get("status")
        translation = decision.get("translation")
        if status not in {"translated", "retain"} or not isinstance(translation, str) or not translation.strip():
            raise ValueError(f"pending decision: {unit_id}")
        if status == "retain" and translation != pending[unit_id]["source"]:
            raise ValueError(f"retained decision changed source: {unit_id}")
        pending[unit_id]["status"] = status
        pending[unit_id]["translation"] = translation
        if status == "retain":
            reason = str(decision.get("reason", "")).strip()
            if not reason:
                raise ValueError(f"retained decision needs reason: {unit_id}")
            pending[unit_id]["reason"] = reason

    image_index = {image["id"]: image for image in result.get("images", [])}
    for decision in worklist.get("images", []):
        image_id = decision.get("id")
        if image_id not in image_index:
            raise ValueError(f"unknown image decision: {image_id}")
        status = decision.get("status")
        if status not in {"reviewed", "localized", "retain"}:
            raise ValueError(f"pending image decision: {image_id}")
        image_index[image_id]["status"] = status
        image_index[image_id]["reason_code"] = decision.get("reason_code")
    return result


def merge_timing_report(existing: dict[str, Any], additions: dict[str, int]) -> dict[str, Any]:
    stages = dict(existing.get("stages_ms", {}))
    stages.update({name: int(value) for name, value in additions.items()})
    return {"schema_version": 1, "stages_ms": stages, "total_ms": sum(stages.values())}


def finalize_stage_plan(completed_stages: list[str]) -> list[str]:
    completed = set(completed_stages)
    plan = []
    if "apply" not in completed:
        plan.extend(["merge-decisions", "validate", "apply"])
    if "verify" not in completed:
        plan.append("verify")
    if "office-validate" not in completed:
        plan.append("office-validate")
    return plan


def resolve_executable(explicit: str | None, env_name: str, fallback: str) -> str:
    candidate = explicit or os.environ.get(env_name) or shutil.which(fallback)
    if not candidate or not Path(candidate).exists():
        raise RuntimeError(f"executable not found; pass the corresponding option or set {env_name}")
    return str(Path(candidate).resolve())


def run_process(command: list[str], *, allowed: set[int] = {0}, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        capture_output=True,
        check=False,
    )
    stdout = completed.stdout.decode("utf-8-sig", errors="replace").strip()
    stderr = completed.stderr.decode("utf-8-sig", errors="replace").strip()
    if completed.returncode not in allowed:
        detail = stderr or stdout or f"exit code {completed.returncode}"
        raise RuntimeError(f"command failed: {' '.join(command)}\n{detail}")
    return stdout


def timed(stages: dict[str, int], name: str, operation):
    started = time.perf_counter()
    result = operation()
    stages[name] = max(0, round((time.perf_counter() - started) * 1000))
    return result


def node_environment(node_modules: str | None) -> dict[str, str]:
    env = dict(os.environ)
    if node_modules:
        env["NODE_PATH"] = str(Path(node_modules).resolve())
    env["PYTHONUTF8"] = "1"
    return env


def prepare_job(args: argparse.Namespace) -> dict[str, Any]:
    source = Path(args.source).resolve()
    job_dir = Path(args.job_dir).resolve()
    job_dir.mkdir(parents=True, exist_ok=True)
    node = resolve_executable(args.node_path, "CODEX_NODE", "node")
    env = node_environment(args.node_modules)
    stages: dict[str, int] = {}

    route_text = timed(stages, "route", lambda: run_process([sys.executable, str(ROUTER), str(source)]))
    route = json.loads(route_text)
    timed(stages, "glossary", lambda: run_process([sys.executable, str(GLOSSARY_RESOLVER)]))

    working_source = source
    if route.get("requires_conversion"):
        powershell = resolve_executable(args.powershell_path, "CODEX_POWERSHELL", "powershell.exe")
        working_source = Path(args.working_copy).resolve() if args.working_copy else job_dir.parent / "source-working.xlsx"
        if working_source.exists():
            raise RuntimeError(f"working copy already exists: {working_source}")
        timed(stages, "convert", lambda: run_process([
            powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(CONVERTER),
            "-SourcePath", str(source), "-OutputPath", str(working_source),
        ]))

    timed(stages, "inspect", lambda: run_process([
        node, str(PIPELINE), "inspect", "--input", str(working_source), "--job-dir", str(job_dir),
        "--target-language", args.target_language, "--output-mode", args.output_mode,
    ], env=env))
    timed(stages, "prepare", lambda: run_process([
        node, str(PIPELINE), "prepare", "--job-dir", str(job_dir),
    ], allowed={0, 3}, env=env))

    manifest_path = job_dir / "translation-manifest.json"
    worklist_path = job_dir / "translation-worklist.json"
    worklist = build_worklist(read_json(manifest_path))
    write_json(worklist_path, worklist)
    timing_path = job_dir / "stage-timings.json"
    write_json(timing_path, merge_timing_report({}, stages))
    return {
        "next_stage": "translate",
        "working_source": str(working_source),
        "manifest": str(manifest_path),
        "worklist": str(worklist_path),
        "glossary": str(job_dir / "relevant-glossary.json"),
        "pending": worklist["pending_count"],
        "images": len(worklist["images"]),
        "timings_ms": stages,
    }


def finalize_job(args: argparse.Namespace) -> dict[str, Any]:
    job_dir = Path(args.job_dir).resolve()
    output = Path(args.output).resolve()
    node = resolve_executable(args.node_path, "CODEX_NODE", "node")
    env = node_environment(args.node_modules)
    stages: dict[str, int] = {}
    state_path = job_dir / "job-state.json"
    manifest_path = job_dir / "translation-manifest.json"
    worklist_path = Path(args.worklist).resolve() if args.worklist else job_dir / "translation-worklist.json"
    state = read_json(state_path)
    source = Path(state["outputPaths"]["source"]).resolve()
    plan = finalize_stage_plan(state.get("completedStages", []))

    def merge_decisions() -> None:
        write_json(manifest_path, apply_worklist(read_json(manifest_path), read_json(worklist_path)))

    if "apply" not in plan:
        recorded_output = Path(state.get("outputPaths", {}).get("output", "")).resolve()
        if recorded_output != output or not output.is_file():
            raise RuntimeError("resume output does not match the completed apply stage")
    if "merge-decisions" in plan:
        timed(stages, "merge-decisions", merge_decisions)
    if "validate" in plan:
        timed(stages, "validate", lambda: run_process([sys.executable, str(VALIDATOR), str(manifest_path)]))
    if "apply" in plan:
        timed(stages, "apply", lambda: run_process([
            node, str(PIPELINE), "apply", "--input", str(source), "--job-dir", str(job_dir), "--output", str(output),
        ], env=env))
    if "verify" in plan:
        timed(stages, "verify", lambda: run_process([
            node, str(PIPELINE), "verify", "--source", str(source), "--job-dir", str(job_dir), "--output", str(output),
        ], env=env))
    if "office-validate" in plan:
        timed(stages, "office-validate", lambda: run_process([
            node, str(PIPELINE), "office-validate", "--job-dir", str(job_dir), "--output", str(output),
        ], env=env))

    timing_path = job_dir / "stage-timings.json"
    existing = read_json(timing_path) if timing_path.exists() else {}
    report = merge_timing_report(existing, stages)
    write_json(timing_path, report)
    return {
        "next_stage": "deliver",
        "output": str(output),
        "output_sha256": sha256_file(output),
        "timings_ms": stages,
        "total_pipeline_ms": report["total_ms"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fast deterministic Excel translation orchestration")
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--source", required=True)
    prepare.add_argument("--job-dir", required=True)
    prepare.add_argument("--target-language", required=True)
    prepare.add_argument("--output-mode", choices=("monolingual", "bilingual"), required=True)
    prepare.add_argument("--working-copy")
    prepare.add_argument("--node-path")
    prepare.add_argument("--node-modules")
    prepare.add_argument("--powershell-path")
    prepare.set_defaults(handler=prepare_job)

    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--job-dir", required=True)
    finalize.add_argument("--output", required=True)
    finalize.add_argument("--worklist")
    finalize.add_argument("--node-path")
    finalize.add_argument("--node-modules")
    finalize.set_defaults(handler=finalize_job)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = args.handler(args)
    except Exception as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"passed": True, **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
