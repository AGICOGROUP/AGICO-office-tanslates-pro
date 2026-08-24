from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

import pdfplumber
from PIL import Image
from pypdf import PdfReader

from contracts import ManifestError, validate_manifest
from extract_scan import _ocr_pass, find_pdftoppm, merge_ocr_records


CJK_RE = re.compile(r"[\u3400-\u9fff]")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_text(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())


def _box_iou(first: list[float], second: list[float]) -> float:
    x0, y0 = max(first[0], second[0]), max(first[1], second[1])
    x1, y1 = min(first[2], second[2]), min(first[3], second[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    intersection = (x1 - x0) * (y1 - y0)
    first_area = (first[2] - first[0]) * (first[3] - first[1])
    second_area = (second[2] - second[0]) * (second[3] - second[1])
    return intersection / max(first_area + second_area - intersection, 1e-9)


def filter_reviewed_ocr_false_positives(
    residual: list[dict], reviewed: list[dict]
) -> tuple[list[dict], list[dict]]:
    unexpected: list[dict] = []
    matched_indexes: set[int] = set()
    for record in residual:
        match = next(
            (
                index
                for index, item in enumerate(reviewed)
                if int(item["output_page"]) == int(record["output_page"])
                and _box_iou(item["box"], record["box"]) >= 0.5
            ),
            None,
        )
        if match is None:
            unexpected.append(record)
        else:
            matched_indexes.add(match)
    return unexpected, [item for index, item in enumerate(reviewed) if index in matched_indexes]


def filter_approved_bilingual_residuals(residual: list[dict], manifest: dict) -> list[dict]:
    pages = {int(page["source_page"]): page for page in manifest.get("pages", [])}
    source_lines = {line.get("id"): line for line in manifest.get("source_lines", [])}
    approved: dict[int, list[list[float]]] = {}
    for block in manifest.get("blocks", []):
        if block.get("action") == "add_bilingual":
            page_number = int(block["page"])
            for line_id in block.get("source_line_ids", []):
                line = source_lines.get(line_id)
                if line and int(line.get("page", -1)) == page_number:
                    approved.setdefault(page_number, []).append(
                        [float(value) for value in line["box"]]
                    )
            continue
        if block.get("status") != "bilingual_complete":
            continue
        page_number = int(block["page"])
        page = pages[page_number]
        x0, y0, x1, y1 = [int(round(value)) for value in block["box"]]
        with Image.open(page["render_path"]) as loaded:
            crop = loaded.convert("RGB").crop((x0, y0, x1, y1))
        actual_hash = hashlib.sha256(crop.tobytes()).hexdigest()
        expected_hash = str(block["bilingual_evidence"]["source_region_sha256"]).lower()
        if actual_hash != expected_hash:
            raise ValueError(f"bilingual source-region hash mismatch: {block['id']}")
        approved.setdefault(page_number, []).append([float(x0), float(y0), float(x1), float(y1)])
    unexpected: list[dict] = []
    for record in residual:
        page_number = int(record["source_page"])
        source_page = pages.get(page_number)
        if not source_page:
            unexpected.append(record)
            continue
        scale_x = float(source_page["pixel_width"]) / float(record["page_pixel_width"])
        scale_y = float(source_page["pixel_height"]) / float(record["page_pixel_height"])
        cx = ((float(record["box"][0]) + float(record["box"][2])) / 2) * scale_x
        cy = ((float(record["box"][1]) + float(record["box"][3])) / 2) * scale_y
        if not any(box[0] <= cx <= box[2] and box[1] <= cy <= box[3] for box in approved.get(page_number, [])):
            unexpected.append(record)
    return unexpected


def _translation_present(block: dict, extracted: str) -> bool:
    normalized_output = normalize_text(extracted)
    parts = [normalize_text(part) for part in block["translation"].splitlines() if normalize_text(part)]
    if len(parts) > 1:
        return all(part in normalized_output for part in parts)
    expected = normalize_text(block["translation"])
    return bool(expected) and expected in normalized_output


def evaluate_evidence(
    manifest: dict,
    extracted_by_page: dict[int, str],
    build_report: dict,
    output_page_count: int,
    geometry_match: bool,
    visual_review: dict,
    residual_cjk: list[dict],
    font_embedding_failures: list[str] | None = None,
    automated_overlap_failures: list[dict] | None = None,
) -> dict:
    try:
        coverage = validate_manifest(manifest)
        manifest_error = ""
    except ManifestError as exc:
        coverage = {}
        manifest_error = str(exc)

    required_blocks = [
        block for block in manifest.get("blocks", [])
        if block.get("action") in {"replace", "add_bilingual"}
    ]
    missing_translation_blocks = [
        block["id"]
        for block in required_blocks
        if not _translation_present(block, extracted_by_page.get(block["page"], ""))
    ]
    rendered_ids = {record["id"] for record in build_report.get("rendered_blocks", [])}
    for page in build_report.get("pages", []):
        rendered_ids.update(page.get("rendered_block_ids", []))
    missing_rendered_blocks = sorted(block["id"] for block in required_blocks if block["id"] not in rendered_ids)

    min_font_by_id = {
        block["id"]: float(block.get("min_font") or 6)
        for block in required_blocks
        if block.get("action") in {"replace", "add_bilingual"}
    }
    minimum_font_failures = [
        record["id"]
        for record in build_report.get("rendered_blocks", [])
        if float(record.get("font_size", 0)) + 1e-6 < min_font_by_id.get(record["id"], 0)
    ]
    incomplete_render_blocks = [
        record["id"]
        for record in build_report.get("rendered_blocks", [])
        if not record.get("complete", False)
    ]

    expected_source_crop_runs = [
        run
        for block in required_blocks
        for line in block.get("rich_lines", [])
        for run in line
        if run.get("type") == "source_crop"
    ]
    reported_source_crop_runs = build_report.get("source_crop_runs", [])
    source_crop_provenance_failures = []
    if len(reported_source_crop_runs) != len(expected_source_crop_runs):
        source_crop_provenance_failures.append(
            f"expected {len(expected_source_crop_runs)} source crops, reported {len(reported_source_crop_runs)}"
        )
    for index, record in enumerate(reported_source_crop_runs, start=1):
        if (
            len(record.get("source_box", [])) != 4
            or len(record.get("output_box_pt", [])) != 4
            or not re.fullmatch(r"[0-9a-f]{64}", str(record.get("pixel_sha256", "")))
            or not str(record.get("alt", "")).strip()
            or not record.get("source_page")
        ):
            source_crop_provenance_failures.append(f"invalid source-crop provenance record {index}")

    expected_mixed_color_ids = []
    for block in required_blocks:
        colors = {
            tuple(run.get("color", block.get("color", [0, 0, 0])))
            for line in block.get("rich_lines", [])
            for run in line
            if run.get("type") == "text"
        }
        if len(colors) > 1:
            expected_mixed_color_ids.append(block["id"])
    rendered_by_id = {record["id"]: record for record in build_report.get("rendered_blocks", [])}
    mixed_color_render_failures = [
        block_id
        for block_id in expected_mixed_color_ids
        if not rendered_by_id.get(block_id, {}).get("mixed_color", False)
    ]

    expected_output_pages = list(range(1, output_page_count + 1))
    reviewed_pages = sorted(visual_review.get("reviewed_output_pages", []))
    overlap_failures = list(visual_review.get("text_overlap_failures", []))
    overlap_failures.extend(automated_overlap_failures or [])
    clipping_failures = list(visual_review.get("clipping_failures", []))
    embedding_failures = font_embedding_failures or []

    report = {
        "manifest_error": manifest_error,
        "source_line_count": coverage.get("source_line_count", 0),
        "assigned_line_count": coverage.get("assigned_line_count", 0),
        "translated_block_count": coverage.get("translated_block_count", 0),
        "expected_render_block_count": len(required_blocks),
        "rendered_block_count": len(required_blocks) - len(missing_rendered_blocks),
        "missing_rendered_blocks": missing_rendered_blocks,
        "missing_translation_blocks": missing_translation_blocks,
        "incomplete_render_blocks": incomplete_render_blocks,
        "minimum_font_failures": minimum_font_failures,
        "unexpected_source_language": len(residual_cjk),
        "residual_cjk": residual_cjk,
        "output_page_count": output_page_count,
        "expected_output_page_count": len(manifest.get("selected_pages", [])),
        "page_geometry_match": geometry_match,
        "outside_approved_pixel_changes": int(
            build_report.get("outside_approved_pixel_changes", -1)
        ),
        "expected_source_crop_run_count": len(expected_source_crop_runs),
        "reported_source_crop_run_count": len(reported_source_crop_runs),
        "source_crop_provenance_failures": source_crop_provenance_failures,
        "mixed_color_render_failures": mixed_color_render_failures,
        "font_embedding_failures": embedding_failures,
        "text_overlap_failures": overlap_failures,
        "clipping_failures": clipping_failures,
        "reviewed_output_pages": reviewed_pages,
        "unreviewed_output_pages": sorted(set(expected_output_pages) - set(reviewed_pages)),
        "unreviewed_images": int(visual_review.get("unreviewed_images", 0)),
        "untranslated_clear_image_labels": int(
            visual_review.get("untranslated_clear_image_labels", 0)
        ),
        "logo_review_complete": bool(visual_review.get("logo_review_complete", False)),
        "header_footer_review_complete": bool(
            visual_review.get("header_footer_review_complete", False)
        ),
        "image_difference_review_complete": bool(
            visual_review.get("image_difference_review_complete", False)
        ),
        "full_render_review_complete": bool(
            visual_review.get("full_render_review_complete", False)
        ),
        "icon_review_complete": bool(visual_review.get("icon_review_complete", False)),
        "source_icon_provenance_complete": bool(
            visual_review.get("source_icon_provenance_complete", False)
        ),
        "icon_substitution_failures": list(
            visual_review.get("icon_substitution_failures", [])
        ),
        "mixed_color_failures": list(visual_review.get("mixed_color_failures", [])),
    }
    report["passed"] = all(
        [
            not report["manifest_error"],
            report["source_line_count"] == report["assigned_line_count"],
            not report["missing_rendered_blocks"],
            not report["missing_translation_blocks"],
            not report["incomplete_render_blocks"],
            not report["minimum_font_failures"],
            report["unexpected_source_language"] == 0,
            report["output_page_count"] == report["expected_output_page_count"],
            report["page_geometry_match"],
            report["outside_approved_pixel_changes"] == 0,
            not report["source_crop_provenance_failures"],
            not report["mixed_color_render_failures"],
            not report["font_embedding_failures"],
            not report["text_overlap_failures"],
            not report["clipping_failures"],
            not report["unreviewed_output_pages"],
            report["unreviewed_images"] == 0,
            report["untranslated_clear_image_labels"] == 0,
            report["logo_review_complete"],
            report["header_footer_review_complete"],
            report["image_difference_review_complete"],
            report["full_render_review_complete"],
            report["icon_review_complete"],
            report["source_icon_provenance_complete"],
            not report["icon_substitution_failures"],
            not report["mixed_color_failures"],
        ]
    )
    return report


def _word_in_regions(word: dict, regions: list[tuple[float, float, float, float]]) -> bool:
    center_x = (float(word["x0"]) + float(word["x1"])) / 2
    center_y = (float(word["top"]) + float(word["bottom"])) / 2
    return any(x0 <= center_x <= x1 and y0 <= center_y <= y1 for x0, y0, x1, y1 in regions)


def extract_output_text(
    pdf_path: Path,
    source_pages: list[int],
    ignore_overlap_regions: dict[int, list[tuple[float, float, float, float]]] | None = None,
) -> tuple[dict[int, str], list[dict]]:
    extracted_by_page: dict[int, str] = {}
    overlap_failures: list[dict] = []
    logical_reader = PdfReader(str(pdf_path))
    ignored = ignore_overlap_regions or {}
    with pdfplumber.open(pdf_path) as document:
        for index, page in enumerate(document.pages):
            source_page = source_pages[index]
            visual_text = page.extract_text() or ""
            logical_text = logical_reader.pages[index].extract_text() or ""
            extracted_by_page[source_page] = visual_text + "\n" + logical_text
            words = page.extract_words(use_text_flow=True, keep_blank_chars=False)
            for first_index, first in enumerate(words):
                if _word_in_regions(first, ignored.get(source_page, [])):
                    continue
                for second in words[first_index + 1 :]:
                    if _word_in_regions(second, ignored.get(source_page, [])):
                        continue
                    if second["top"] > first["bottom"] + 1:
                        continue
                    x_overlap = min(first["x1"], second["x1"]) - max(first["x0"], second["x0"])
                    y_overlap = min(first["bottom"], second["bottom"]) - max(first["top"], second["top"])
                    if x_overlap > 0.7 and y_overlap > 0.7:
                        overlap_failures.append(
                            {
                                "output_page": index + 1,
                                "first": first["text"],
                                "second": second["text"],
                            }
                        )
    return extracted_by_page, overlap_failures


def compare_geometry(manifest: dict, reader: PdfReader) -> bool:
    if len(reader.pages) != len(manifest["selected_pages"]):
        return False
    source_pages = {page["source_page"]: page for page in manifest["pages"]}
    for index, source_page_number in enumerate(manifest["selected_pages"]):
        expected = source_pages[source_page_number]
        actual = reader.pages[index]
        if abs(float(actual.mediabox.width) - expected["width_pt"]) > 0.02:
            return False
        if abs(float(actual.mediabox.height) - expected["height_pt"]) > 0.02:
            return False
    return True


def inspect_font_embedding(reader: PdfReader) -> list[str]:
    failures: set[str] = set()
    for page in reader.pages:
        resources = page.get("/Resources") or {}
        fonts = resources.get("/Font") or {}
        fonts = fonts.get_object() if hasattr(fonts, "get_object") else fonts
        for reference in fonts.values():
            font = reference.get_object()
            descriptor = font.get("/FontDescriptor")
            if descriptor is None:
                continue
            descriptor = descriptor.get_object()
            if not any(descriptor.get(key) is not None for key in ("/FontFile", "/FontFile2", "/FontFile3")):
                failures.add(str(font.get("/BaseFont", "unknown")))
    return sorted(failures)


def residual_cjk_ocr(pdf_path: Path, output_dir: Path, source_pages: list[int]) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = output_dir / "page"
    command = [find_pdftoppm(), "-r", "200", "-png", str(pdf_path), str(prefix)]
    subprocess.run(command, check=True, capture_output=True)
    from rapidocr_onnxruntime import RapidOCR

    engine = RapidOCR()
    residual = []
    for index, image_path in enumerate(sorted(output_dir.glob("page-*.png"))):
        with Image.open(image_path) as loaded:
            image = loaded.convert("RGB")
        records = merge_ocr_records(_ocr_pass(engine, image, 1.0) + _ocr_pass(engine, image, 2.0))
        for record in records:
            if CJK_RE.search(record["text"]):
                residual.append(
                    {
                        "output_page": index + 1,
                        "source_page": source_pages[index],
                        "text": record["text"],
                        "box": record["box"],
                        "score": record["score"],
                        "page_pixel_width": image.width,
                        "page_pixel_height": image.height,
                    }
                )
    return residual


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--build-report")
    parser.add_argument("--visual-review", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    source = Path(args.source).resolve()
    pdf_path = Path(args.pdf).resolve()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    build_report_path = (
        Path(args.build_report)
        if args.build_report
        else pdf_path.with_suffix(".build-report.json")
    )
    build_report = json.loads(build_report_path.read_text(encoding="utf-8"))
    visual_review = json.loads(Path(args.visual_review).read_text(encoding="utf-8"))
    source_hash = sha256_file(source)
    if str(manifest.get("source_sha256", "")).lower() != source_hash.lower():
        raise ValueError("manifest source SHA-256 does not match the source PDF")
    output_hash = sha256_file(pdf_path)
    if str(visual_review.get("candidate_sha256", "")).lower() != output_hash.lower():
        raise ValueError("visual review is not bound to the candidate PDF SHA-256")
    reader = PdfReader(str(pdf_path))
    extracted, automated_overlap = extract_output_text(
        pdf_path,
        manifest["selected_pages"],
        ignore_overlap_regions={},
    )
    residual = residual_cjk_ocr(
        pdf_path,
        Path(args.report).resolve().parent / "qa-ocr-render",
        manifest["selected_pages"],
    )
    residual = filter_approved_bilingual_residuals(residual, manifest)
    reviewed_false_positives = visual_review.get("reviewed_ocr_false_positives", [])
    residual, matched_false_positives = filter_reviewed_ocr_false_positives(
        residual, reviewed_false_positives
    )
    report = evaluate_evidence(
        manifest=manifest,
        extracted_by_page=extracted,
        build_report=build_report,
        output_page_count=len(reader.pages),
        geometry_match=compare_geometry(manifest, reader),
        visual_review=visual_review,
        residual_cjk=residual,
        font_embedding_failures=inspect_font_embedding(reader),
        automated_overlap_failures=automated_overlap,
    )
    report.update(
        {
            "source": str(source),
            "source_sha256": source_hash,
            "output": str(pdf_path),
            "output_sha256": output_hash,
            "selected_source_pages": manifest["selected_pages"],
            "reviewed_ocr_false_positives": matched_false_positives,
            "unmatched_reviewed_ocr_false_positives": [
                item for item in reviewed_false_positives if item not in matched_false_positives
            ],
        }
    )
    report["passed"] = report["passed"] and not report["unmatched_reviewed_ocr_false_positives"]
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "report": str(output.resolve())}, ensure_ascii=False))
    if not report["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
