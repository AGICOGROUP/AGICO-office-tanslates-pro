#!/usr/bin/env python3
"""One resumable task interface for native Office translation adapters."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from route_office_file import route
from translation_core import atomic_json, build_worklist, file_hash, fingerprint, merge_decisions
from translation_assets import prepare_assets, pending_assets, merge_assets

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = {name: ROOT / "formats" / name / "scripts" / filename for name, filename in
           {"word": "word_pipeline.py", "excel": "excel_fast_pipeline.py", "ppt": "ppt_pipeline.py"}.items()}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def run_adapter(format_name, *arguments):
    env = {**os.environ, "PYTHONUTF8": "1"}
    completed = subprocess.run([sys.executable, str(SCRIPTS[format_name]), *map(str, arguments)],
                               capture_output=True, text=True, encoding="utf-8-sig", errors="replace",
                               env=env, timeout=240, cwd=ROOT)
    if completed.returncode not in {0, 3}:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "adapter failed")
    for line in reversed(completed.stdout.splitlines()):
        try:
            report = json.loads(line)
            if isinstance(report, dict) and report:
                return report
        except json.JSONDecodeError:
            continue
    raise RuntimeError(f"{format_name} adapter returned no structured result; rerun the failed command")


def paths(job_dir):
    root = Path(job_dir).resolve()
    return root, root / "office-job.json", root / "translation-manifest.json", root / "translation-worklist.json"


def check_source(state):
    if (state.get("prepared") is not True or not state.get("working_source")
            or not state.get("working_sha256")):
        raise ValueError("prepare is incomplete; rerun office_pipeline.py prepare with the same source and job directory")
    source = Path(state["source"])
    if not source.is_file() or file_hash(source) != state["source_sha256"]:
        raise ValueError("source file changed since preparation; use a new job directory")
    working = Path(state.get("working_source", state["source"]))
    if not working.is_file() or (state.get("working_sha256") and file_hash(working) != state["working_sha256"]):
        raise ValueError("working source changed since preparation; use a new job directory")


def refresh_worklist(job_dir, manifest, format_name, max_chars=12000):
    work = build_worklist(manifest, format_name, max_chars)
    work["images"] = pending_assets(manifest, format_name)
    atomic_json(Path(job_dir) / "translation-worklist.json", work)
    return work


def summary(job_dir, state, manifest):
    work = build_worklist(manifest, state["format"], state.get("batch_chars", 12000))
    images = pending_assets(manifest, state["format"])
    pending = work["pending_count"] + len(images)
    return {"format": state["format"], "next_stage": "translate" if pending else "finalize",
            "pending_count": work["pending_count"], "pending_images": len(images),
            "worklist": str(Path(job_dir) / "translation-worklist.json"),
            "glossary": str(Path(job_dir) / "relevant-glossary.json"),
            "batches": len(work["batches"]), "warnings": manifest.get("warnings", [])}


def prepare_job(source, job_dir, target_language, output_mode="monolingual", batch_chars=12000):
    source = Path(source).resolve()
    job, state_path, manifest_path, work_path = paths(job_dir)
    code, routing = route(source)
    if code:
        raise ValueError(routing["error"])
    if batch_chars < 1:
        raise ValueError("batch character budget must be positive")
    format_name = routing["format"]
    if output_mode != "monolingual" and format_name != "excel":
        raise ValueError("paired-row bilingual mode is available for Excel only")
    identity = {"source": str(source), "source_sha256": file_hash(source),
                "format": format_name, "target_language": target_language, "output_mode": output_mode}
    job.mkdir(parents=True, exist_ok=True)
    state = read_json(state_path) if state_path.exists() else {**identity, "stages": {}, "batch_chars": batch_chars}
    if any(state.get(key) != value for key, value in identity.items()):
        raise ValueError("job identity changed; use a separate job directory")
    if not state.get("prepared"):
        atomic_json(state_path, state)
        if format_name == "word":
            run_adapter("word", "prepare", source, "--job-dir", job, "--target-language", target_language)
        elif format_name == "excel":
            run_adapter("excel", "prepare", "--source", source, "--job-dir", job,
                        "--target-language", target_language, "--output-mode", output_mode)
        else:
            run_adapter("ppt", "inspect", "--input", source, "--job-dir", job, "--target-language", target_language)
            run_adapter("ppt", "prepare", "--job-dir", job)
        manifest = read_json(manifest_path)
        if format_name == "word":
            working = Path(manifest["working_docx"])
        elif format_name == "excel":
            working = Path(read_json(job / "job-state.json")["outputPaths"]["source"])
        else:
            working = Path(read_json(job / "inventory.json")["working_source_path"])
        state.update(prepared=True, working_source=str(working), working_sha256=file_hash(working))
        manifest = prepare_assets(manifest, format_name, working, job)
        atomic_json(manifest_path, manifest)
        refresh_worklist(job, manifest, format_name, batch_chars)
        atomic_json(state_path, state)
    else:
        check_source(state)
        manifest = read_json(manifest_path)
        if not work_path.exists():
            refresh_worklist(job, manifest, format_name, batch_chars)
    return summary(job, state, manifest)


def merge_job(job_dir, decisions=None):
    job, state_path, manifest_path, work_path = paths(job_dir)
    state = read_json(state_path)
    check_source(state)
    manifest = read_json(manifest_path)
    work = read_json(Path(decisions) if decisions else work_path)
    manifest, report = merge_decisions(manifest, work, state["format"])
    report["rejected_images"] = merge_assets(manifest, work.get("images", []), state["format"])
    atomic_json(manifest_path, manifest)
    refresh_worklist(job, manifest, state["format"], state.get("batch_chars", 12000))
    report.update(summary(job, state, manifest))
    report["ready"] = not report["pending_count"] and not report["pending_images"] and not report["rejected"] and not report["rejected_images"]
    atomic_json(job / "translation-progress.json", report)
    return report


def unique_warnings(values):
    seen, result = set(), []
    for value in values:
        key = fingerprint(value)
        if key not in seen:
            result.append(value)
            seen.add(key)
    return result


def finalize_job(job_dir, output, decisions=None, visual_review_passed=False):
    job, state_path, manifest_path, work_path = paths(job_dir)
    state = read_json(state_path)
    output = Path(output).resolve()
    check_source(state)
    if output in {Path(state["source"]).resolve(), Path(state["working_source"]).resolve()}:
        raise ValueError("output must not overwrite the original source or working copy")
    format_name = state["format"]
    expected_suffix = {"word": ".docx", "excel": ".xlsx", "ppt": ".pptx"}[format_name]
    if output.suffix.lower() != expected_suffix:
        raise ValueError(f"output extension must be {expected_suffix}")
    if decisions or work_path.exists():
        progress = merge_job(job, decisions)
        if not progress["ready"]:
            return {**progress, "next_stage": "translate"}
    manifest = read_json(manifest_path)
    readiness = summary(job, state, manifest)
    if readiness["pending_count"] or readiness["pending_images"]:
        return readiness
    key = fingerprint({"manifest": manifest, "output": str(output)})
    stages = state.setdefault("stages", {})
    current_hash = file_hash(output) if output.is_file() else None
    delivery = stages.get("deliver", {})
    if delivery.get("key") == key and delivery.get("output_sha256") == current_hash and current_hash:
        return {**delivery["result"], "resumed": True}

    def stage(name, operation):
        previous = stages.get(name, {})
        output_hash = file_hash(output) if output.is_file() else None
        if previous.get("key") == key and previous.get("output_sha256") == output_hash and output_hash:
            return previous.get("result", {})
        started = time.perf_counter()
        try:
            result = operation()
        except RuntimeError as exc:
            message = str(exc)
            if format_name == "ppt":
                affected = False
                for group in manifest.get("image_groups", []):
                    if any(f"overlay {item_id}:" in message or f"overlays[{item_id}]" in message for item_id in group.get("overlay_ids", [])):
                        group["decision_error"] = message
                        affected = True
                if affected:
                    atomic_json(manifest_path, manifest)
                    refresh_worklist(job, manifest, format_name, state.get("batch_chars", 12000))
            state["last_error"] = {"stage": name, "message": message}
            atomic_json(state_path, state)
            raise
        stages[name] = {"key": key, "output_sha256": file_hash(output) if output.is_file() else None,
                        "elapsed_ms": round((time.perf_counter() - started) * 1000), "result": result}
        atomic_json(state_path, state)
        return result

    warnings = list(manifest.get("warnings", []))
    if format_name == "word":
        stage("apply", lambda: run_adapter("word", "apply", manifest_path, "--output", output))
        stage("verify", lambda: run_adapter("word", "validate", output, "--manifest", manifest_path))
        warnings.extend(read_json(job / "qa-report.json").get("warnings", []))
    elif format_name == "excel":
        native_state_path = job / "job-state.json"
        native_state = read_json(native_state_path)
        validated_hash = native_state.get("stageArtifacts", {}).get("validate", {}).get("manifest")
        if validated_hash and validated_hash != file_hash(manifest_path):
            retained = {"preflight", "inspect", "prepare"}
            native_state["completedStages"] = [item for item in native_state["completedStages"] if item in retained]
            native_state["stageArtifacts"] = {k: v for k, v in native_state.get("stageArtifacts", {}).items() if k in retained}
            atomic_json(native_state_path, native_state)
        report = stage("finalize", lambda: run_adapter("excel", "finalize", "--job-dir", job, "--output", output))
        warnings.extend(report.get("warnings", []))
    else:
        source = Path(state["source"])
        stage("apply", lambda: run_adapter("ppt", "apply", "--input", source, "--job-dir", job, "--output", output))
        stage("verify", lambda: run_adapter("ppt", "verify", "--source", source, "--job-dir", job, "--output", output))
        rendered = stage("render", lambda: run_adapter("ppt", "render", "--source", source, "--job-dir", job, "--output", output))
        render = rendered.get("target", {})
        # Existing adapter decides when an unavailable render is deliverable.
        # A real rendered slide still requires its actual visual review.
        if not visual_review_passed and not (render.get("code") == "office-unavailable" and render.get("slides_rendered") == 0):
            return {"next_stage": "visual-review", "output": str(output), "render": render,
                    "instructions": "Review available final slides, then finalize with --visual-review-passed"}
        args = ["deliver", "--job-dir", job, "--output", output]
        if visual_review_passed:
            args.append("--visual-review-passed")
        report = run_adapter("ppt", *args)
        warnings.extend(report.get("warnings", []))
    result = {"next_stage": "deliver", "output": str(output), "output_sha256": file_hash(output),
              "warnings": unique_warnings(warnings),
              "timings_ms": {name: value.get("elapsed_ms", 0) for name, value in stages.items() if name != "deliver"}}
    stages["deliver"] = {"key": key, "output_sha256": result["output_sha256"], "result": result}
    atomic_json(state_path, state)
    atomic_json(job / "delivery-report.json", result)
    return result


def status_job(job_dir):
    job, state_path, manifest_path, _ = paths(job_dir)
    state = read_json(state_path)
    check_source(state)
    manifest = read_json(manifest_path)
    result = summary(job, state, manifest)
    delivered = state.get("stages", {}).get("deliver", {})
    if delivered and not result["pending_count"] and not result["pending_images"]:
        output = Path(delivered["result"]["output"])
        key = fingerprint({"manifest": manifest, "output": str(output)})
        if output.is_file() and file_hash(output) == delivered.get("output_sha256") and key == delivered.get("key"):
            result.update(delivered["result"])
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("source", type=Path)
    prepare.add_argument("--target-language", required=True)
    prepare.add_argument("--output-mode", choices=("monolingual", "bilingual"), default="monolingual")
    prepare.add_argument("--batch-chars", type=int, default=12000)
    merge = commands.add_parser("merge")
    merge.add_argument("--decisions", type=Path)
    finalize = commands.add_parser("finalize")
    finalize.add_argument("--output", required=True, type=Path)
    finalize.add_argument("--decisions", type=Path)
    finalize.add_argument("--visual-review-passed", action="store_true")
    status = commands.add_parser("status")
    for command in (prepare, merge, finalize, status):
        command.add_argument("--job-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare_job(args.source, args.job_dir, args.target_language, args.output_mode, args.batch_chars)
        elif args.command == "merge":
            result = merge_job(args.job_dir, args.decisions)
        elif args.command == "finalize":
            result = finalize_job(args.job_dir, args.output, args.decisions, args.visual_review_passed)
        else:
            result = status_job(args.job_dir)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"next_stage": "repair", "error": str(exc),
                          "recovery": "Correct the reported input or decision and rerun this command; accepted decisions remain saved."}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
