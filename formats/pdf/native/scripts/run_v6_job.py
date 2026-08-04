from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import v6_job_state as state
from extract_original_images import extract_inventory
from pypdf import PdfReader


HERE = Path(__file__).resolve().parent
IMAGE_LOCALIZATION_METHODS = {
    "native_edit",
    "deterministic_cleanup",
    "anchored_line_restore",
    "constrained_clean_base",
    "preserve_confirm",
    "preserve_bilingual",
}
IMAGE_ASSET_TYPES = {
    "editable_vector",
    "raster_simple",
    "raster_structured",
    "raster_complex",
    "unreadable",
}


def _run(script: str, *arguments: object) -> None:
    result = subprocess.run(
        [sys.executable, str(HERE / script), *(str(value) for value in arguments)],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact(job: dict[str, Any], name: str) -> Path:
    record = job["artifacts"].get(name)
    if not record:
        raise ValueError(f"missing artifact: {name}")
    return Path(record["path"])


def init_job(source: Path, jobs_root: Path) -> Path:
    job_dir = state.create_job(source, jobs_root)
    job = state.load_job(job_dir)
    manifest = job_dir / "manifest.json"
    if not manifest.exists():
        _run(
            "pdf_translation_pipeline.py",
            "extract",
            "--input",
            source.resolve(),
            "--manifest",
            manifest,
            "--source-language",
            "zh",
            "--target-language",
            "en",
        )
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    if not any(page.get("blocks") for page in manifest_data.get("pages", [])):
        raise ValueError(
            "scan-only PDF detected; use translate-scan-pdf-professionally"
        )
    state.bind_artifact(job_dir, "manifest", manifest)
    inventory_path = job_dir / "images" / "image-inventory.json"
    if not inventory_path.exists():
        extract_inventory(
            source.resolve(), job["source"]["sha256"], job_dir / "images"
        )
    state.bind_artifact(job_dir, "image_inventory", inventory_path)
    return job_dir


def _manifest_complete(path: Path) -> bool:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    blocks = [
        block
        for page in manifest.get("pages", [])
        for block in page.get("blocks", [])
    ]
    return bool(blocks) and all(
        str(block.get("translation", "")).strip() for block in blocks
    )


def _validate_image_localization_review(
    review: dict[str, Any], metadata: dict[str, Any], expected_ids: set[str]
) -> None:
    records = review.get("images", [])
    by_id = {str(record.get("id", "")): record for record in records}
    missing_records = sorted(expected_ids - set(by_id))
    if missing_records:
        raise ValueError(
            "missing image localization records: " + ", ".join(missing_records)
        )
    confirm_items = {
        str(item.get("label_id", "")) if isinstance(item, dict) else str(item)
        for item in review.get("confirm_items", [])
    }
    metadata_ids = {
        str(item.get("id", "")): item for item in metadata.get("images", [])
    }
    for image_id in sorted(expected_ids):
        record = by_id[image_id]
        labels = record.get("labels", [])
        expected = int(record.get("expected_label_count", -1))
        translated = int(record.get("translated_label_count", -1))
        preserved = int(record.get("preserved_label_count", -1))
        confirms = int(record.get("confirm_count", -1))
        if expected == 0 and not record.get("contains_source_text", False):
            if labels or any(value != 0 for value in (translated, preserved, confirms)):
                raise ValueError(f"image label coverage mismatch: {image_id}")
            continue
        method = str(record.get("method", ""))
        if method not in IMAGE_LOCALIZATION_METHODS:
            raise ValueError(
                f"unsupported image localization method for {image_id}: {method}"
            )
        asset_type = str(record.get("asset_type", ""))
        if asset_type not in IMAGE_ASSET_TYPES:
            raise ValueError(f"unsupported image asset type for {image_id}: {asset_type}")
        if expected < 0 or len(labels) != expected or translated + preserved != expected:
            raise ValueError(f"image label coverage mismatch: {image_id}")
        actual_translated = sum(
            1 for label in labels if label.get("status") == "translated"
        )
        actual_confirms = sum(1 for label in labels if label.get("status") == "confirm")
        actual_preserved = sum(
            1
            for label in labels
            if label.get("status") in {"confirm", "bilingual_present", "preserved"}
        )
        if (
            actual_translated != translated
            or actual_confirms != confirms
            or actual_preserved != preserved
        ):
            raise ValueError(f"image label coverage mismatch: {image_id}")
        label_ids = [str(label.get("id", "")) for label in labels]
        if not all(label_ids) or len(label_ids) != len(set(label_ids)):
            raise ValueError(f"invalid or duplicate image label ID: {image_id}")
        for label in labels:
            label_id = str(label["id"])
            label_method = str(label.get("method", method))
            if label_method not in IMAGE_LOCALIZATION_METHODS:
                raise ValueError(
                    f"unsupported image localization method for {label_id}: {label_method}"
                )
            if label.get("status") == "translated" and not str(
                label.get("translation", "")
            ).strip():
                raise ValueError(f"blank image-label translation: {label_id}")
            if label.get("status") == "confirm" and label_id not in confirm_items:
                raise ValueError(f"unreported confirm item: {label_id}")
        if method == "preserve_bilingual":
            clear_count = int(record.get("clear_source_label_count", -1))
            matched_count = int(record.get("matched_bilingual_pair_count", -1))
            unmatched_count = int(record.get("unmatched_source_label_count", -1))
            if (
                record.get("bilingual_complete") is not True
                or record.get("original_asset_preserved") is not True
                or clear_count <= 0
                or matched_count != clear_count
                or unmatched_count != 0
                or translated != 0
                or preserved != expected
                or any(label.get("status") != "bilingual_present" for label in labels)
            ):
                raise ValueError(f"incomplete bilingual coverage: {image_id}")
        if record.get("structural_review_complete") is not True:
            raise ValueError(f"structural image review incomplete: {image_id}")
        if translated and image_id not in metadata_ids:
            raise ValueError(f"missing vector metadata for translated image: {image_id}")


def resume(job_dir: Path) -> tuple[dict[str, Any], int]:
    job = state.load_job(job_dir)
    stage = job["stage"]
    if stage == "initialized":
        manifest = _artifact(job, "manifest")
        action = "build_native" if _manifest_complete(manifest) else "translate_manifest"
    elif stage == "native_translated":
        action = "review_images"
    elif stage == "images_annotated":
        action = "build_images"
    elif stage == "images_cleaned":
        action = "assemble"
    elif stage == "assembled":
        action = "complete_visual_review"
    else:
        action = "deliver"
    code = 0 if action == "deliver" else 2
    return {
        "job_dir": str(job_dir.resolve()),
        "stage": stage,
        "action": action,
        "user_input_required": False,
    }, code


def build_native(job_dir: Path) -> None:
    job = state.load_job(job_dir)
    if job["stage"] != "initialized":
        raise ValueError("build-native requires initialized stage")
    manifest = _artifact(job, "manifest")
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    if manifest_data.get("source_sha256") != job["source"]["sha256"]:
        raise ValueError("manifest source hash mismatch")
    state.bind_artifact(job_dir, "manifest", manifest)
    if not _manifest_complete(manifest):
        raise ValueError("manifest translations are incomplete")
    output = job_dir / "translated-native.pdf"
    _run(
        "native_selectable_rebuild.py",
        Path(job["source"]["path"]),
        manifest,
        output,
    )
    state.bind_artifact(job_dir, "native_pdf", output)
    rebuild_report = output.with_suffix(".rebuild-report.json")
    if rebuild_report.exists():
        state.bind_artifact(job_dir, "native_rebuild_report", rebuild_report)
    state.advance(job_dir, "native_translated", ("manifest", "native_pdf"))


def annotate_images(job_dir: Path, metadata: Path, review: Path) -> None:
    job = state.load_job(job_dir)
    if job["stage"] != "native_translated":
        raise ValueError("annotate-images requires native_translated stage")
    metadata_target = job_dir / "image-vector-metadata.json"
    review_target = job_dir / "image-review.json"
    shutil.copy2(metadata, metadata_target)
    shutil.copy2(review, review_target)
    review_data = json.loads(review_target.read_text(encoding="utf-8"))
    metadata_data = json.loads(metadata_target.read_text(encoding="utf-8"))
    if not review_data.get("complete"):
        raise ValueError("image review is incomplete")
    inventory = json.loads(
        _artifact(job, "image_inventory").read_text(encoding="utf-8")
    )
    expected_ids = {item["id"] for item in inventory.get("images", [])}
    reviewed_ids = set(review_data.get("reviewed_image_ids", []))
    missing_ids = sorted(expected_ids - reviewed_ids)
    if missing_ids:
        raise ValueError(
            "unreviewed original images: " + ", ".join(missing_ids)
        )
    _validate_image_localization_review(review_data, metadata_data, expected_ids)
    state.bind_artifact(job_dir, "image_metadata", metadata_target)
    state.bind_artifact(job_dir, "image_review", review_target)
    state.advance(
        job_dir,
        "images_annotated",
        ("native_pdf", "image_metadata", "image_review"),
    )


def build_images(job_dir: Path) -> None:
    job = state.load_job(job_dir)
    if job["stage"] != "images_annotated":
        raise ValueError("build-images requires images_annotated stage")
    metadata = _artifact(job, "image_metadata")
    report = job_dir / "clean-image-report.json"
    _run("build_clean_image_bases.py", metadata, "--report", report)
    report_data = json.loads(report.read_text(encoding="utf-8"))
    if any(item.get("outside_region_pixel_changes", 0) for item in report_data.get("images", [])):
        raise ValueError("image cleanup changed pixels outside approved regions")
    state.bind_artifact(job_dir, "clean_image_report", report)
    state.advance(
        job_dir,
        "images_cleaned",
        ("native_pdf", "image_metadata", "clean_image_report"),
    )


def assemble(job_dir: Path) -> None:
    job = state.load_job(job_dir)
    if job["stage"] != "images_cleaned":
        raise ValueError("assemble requires images_cleaned stage")
    output = job_dir / "candidate.pdf"
    _run(
        "apply_image_vector_text.py",
        _artifact(job, "native_pdf"),
        _artifact(job, "image_metadata"),
        output,
    )
    state.bind_artifact(job_dir, "candidate_pdf", output)
    state.advance(
        job_dir,
        "assembled",
        ("native_pdf", "image_metadata", "candidate_pdf"),
    )


def verify(
    job_dir: Path,
    visual_review_complete: bool,
    visual_review_report: Path | None = None,
) -> None:
    job = state.load_job(job_dir)
    if job["stage"] != "assembled":
        raise ValueError("verify requires assembled stage")
    candidate = _artifact(job, "candidate_pdf")
    reader = PdfReader(str(candidate))
    extracted_text = "\n".join(
        page.extract_text() or "" for page in reader.pages
    )
    cjk = re.findall(
        r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", extracted_text
    )
    if cjk:
        raise ValueError(f"extractable CJK remains: {len(cjk)} characters")
    if visual_review_report is None:
        raise ValueError("visual review report is required")
    visual = json.loads(
        visual_review_report.read_text(encoding="utf-8")
    )
    failed = []
    for key in (
        "all_pages_rendered",
        "logo_review_complete",
        "header_footer_high_resolution_review_complete",
        "image_structural_review_complete",
        "image_difference_review_complete",
    ):
        if visual.get(key) is not True:
            failed.append(key)
    for key in (
        "unreviewed_images",
        "untranslated_clear_image_labels",
        "unreported_confirm_items",
    ):
        if int(visual.get(key, -1)) != 0:
            failed.append(key)
    if visual.get("text_overlap_failures"):
        failed.append("text_overlap_failures")
    if visual.get("anchored_line_failures"):
        failed.append("anchored_line_failures")
    candidate_hash = _sha256(candidate)
    if str(visual.get("candidate_sha256", "")).lower() != candidate_hash.lower():
        failed.append("candidate_sha256")
    if failed:
        raise ValueError(
            "visual delivery gates failed: " + ", ".join(failed)
        )
    manifest = _artifact(job, "manifest")
    selectability_report = job_dir / "selectability-report.json"
    selectable_args: list[object] = [
        Path(job["source"]["path"]), manifest, candidate, "--report", selectability_report,
    ]
    if "image_metadata" in job["artifacts"]:
        metadata = json.loads(_artifact(job, "image_metadata").read_text(encoding="utf-8"))
        for page_number in sorted({int(item["page"]) for item in metadata.get("images", [])}):
            selectable_args.extend(["--allow-modified-image-page", page_number])
    _run("verify_selectable_output.py", *selectable_args)
    selectability = json.loads(selectability_report.read_text(encoding="utf-8"))

    typography = {"passed": True, "not_applicable": True}
    rebuild_record = job["artifacts"].get("native_rebuild_report")
    if rebuild_record:
        typography_report = job_dir / "typography-report.json"
        _run(
            "verify_native_typography.py",
            Path(job["source"]["path"]), manifest, Path(rebuild_record["path"]),
            "--report", typography_report,
        )
        typography = json.loads(typography_report.read_text(encoding="utf-8"))

    report = {
        "passed": True,
        "source_bound": True,
        "candidate": str(candidate),
        "source_sha256": job["source"]["sha256"],
        "candidate_sha256": candidate_hash,
        "extractable_cjk": len(cjk),
        "selectability_report": str(selectability_report),
        "selectability_passed": not any(selectability.get(key) for key in ("geometry_failures", "extractable_cjk_pages", "selectable_text_failures", "unapproved_image_changes")),
        "typography_passed": bool(typography.get("passed", False)),
        "outside_region_pixel_changes": sum(int(item.get("outside_region_pixel_changes", 0)) for item in json.loads(_artifact(job, "clean_image_report").read_text(encoding="utf-8")).get("images", [])) if "clean_image_report" in job["artifacts"] else 0,
        "visual_review_complete": True,
        "unreviewed_images": 0,
        "untranslated_clear_image_labels": 0,
        "logo_review_complete": True,
        "header_footer_high_resolution_review_complete": True,
        "image_structural_review_complete": True,
        "image_difference_review_complete": True,
        "unreported_confirm_items": 0,
        "anchored_line_failures": [],
        "text_overlap_failures": [],
    }
    report_path = job_dir / "final-qa.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    state.bind_artifact(job_dir, "final_qa", report_path)
    state.advance(
        job_dir, "verified", ("candidate_pdf", "final_qa")
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    init_parser = commands.add_parser("init")
    init_parser.add_argument("source", type=Path)
    init_parser.add_argument("--jobs-root", type=Path, required=True)
    for command in ("status", "resume", "build-native", "build-images", "assemble"):
        child = commands.add_parser(command)
        child.add_argument("job", type=Path)
    annotate = commands.add_parser("annotate-images")
    annotate.add_argument("job", type=Path)
    annotate.add_argument("--metadata", type=Path, required=True)
    annotate.add_argument("--review", type=Path, required=True)
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("job", type=Path)
    verify_parser.add_argument("--visual-review-complete", action="store_true")
    verify_parser.add_argument("--visual-review-report", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "init":
            job_dir = init_job(args.source, args.jobs_root)
            print(json.dumps({"job_dir": str(job_dir)}))
        elif args.command == "status":
            print(json.dumps(state.load_job(args.job), ensure_ascii=False))
        elif args.command == "resume":
            payload, code = resume(args.job)
            print(json.dumps(payload, ensure_ascii=False))
            raise SystemExit(code)
        elif args.command == "build-native":
            build_native(args.job)
        elif args.command == "annotate-images":
            annotate_images(args.job, args.metadata, args.review)
        elif args.command == "build-images":
            build_images(args.job)
        elif args.command == "assemble":
            assemble(args.job)
        elif args.command == "verify":
            verify(
                args.job,
                args.visual_review_complete,
                args.visual_review_report,
            )
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
