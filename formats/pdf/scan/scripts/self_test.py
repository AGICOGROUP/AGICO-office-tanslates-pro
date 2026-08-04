from __future__ import annotations

import json
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from pypdf import PdfReader

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_scan import build_pdf, clean_background
from contracts import ManifestError, validate_manifest
from extract_scan import merge_ocr_records
from verify_scan import evaluate_evidence


def valid_manifest(render_path: Path) -> dict:
    return {
        "source": "fixture.pdf",
        "source_sha256": "fixture",
        "selected_pages": [1],
        "pages": [{"source_page": 1, "width_pt": 144, "height_pt": 144, "render_path": str(render_path), "pixel_width": 200, "pixel_height": 200, "dpi": 100}],
        "source_lines": [{"id": "p01-l001", "page": 1, "box": [20, 20, 80, 40], "text": "测试", "score": 0.99}],
        "blocks": [{"id": "p01-title", "page": 1, "source_line_ids": ["p01-l001"], "source": "测试", "translation": "Test", "role": "title", "status": "translated", "action": "replace", "box": [20, 18, 100, 50], "clean_box": [18, 18, 82, 43], "background": [255, 255, 255], "min_font": 8, "max_font": 12}],
    }


class SkillTests(unittest.TestCase):
    def test_manifest_requires_exact_source_coverage(self) -> None:
        manifest = valid_manifest(Path("fixture.png"))
        manifest["source_lines"].append({"id": "p01-l002", "page": 1, "box": [1, 1, 2, 2], "text": "漏", "score": 1})
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)

    def test_cleanup_changes_only_approved_box(self) -> None:
        image = Image.new("RGB", (100, 100), "white")
        ImageDraw.Draw(image).rectangle((20, 20, 40, 40), fill="black")
        cleaned, report = clean_background(image, [{"action": "replace", "clean_box": [20, 20, 41, 41], "background": [255, 255, 255]}])
        self.assertEqual(report["outside_approved_pixel_changes"], 0)
        self.assertTrue(np.all(np.asarray(cleaned)[20:41, 20:41] == 255))

    def test_dual_scale_merge_deduplicates_same_label(self) -> None:
        records = [
            {"box": [10, 10, 30, 20], "text": "温度", "score": 0.8, "scale": 1},
            {"box": [10.5, 10, 30.5, 20], "text": "温度", "score": 0.95, "scale": 3},
        ]
        merged = merge_ocr_records(records)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["score"], 0.95)

    def test_build_adds_selectable_english_and_preserves_page_geometry(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = Image.new("RGB", (200, 200), "white")
            ImageDraw.Draw(image).text((20, 20), "source", fill="black")
            render = root / "page.png"
            image.save(render)
            output = root / "translated.pdf"
            report = build_pdf(valid_manifest(render), output)
            reader = PdfReader(str(output))
            self.assertIn("Test", reader.pages[0].extract_text())
            self.assertAlmostEqual(float(reader.pages[0].mediabox.width), 144, places=2)
            self.assertEqual(report["outside_approved_pixel_changes"], 0)

    def test_manifest_rejects_source_crop_outside_page(self) -> None:
        manifest = valid_manifest(Path("fixture.png"))
        manifest["blocks"][0]["rich_lines"] = [[
            {"type": "text", "text": "Test"},
            {"type": "source_crop", "source_box": [190, 10, 220, 30], "alt": "menu icon"},
        ]]
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)

    def test_build_rich_lines_reuses_exact_source_icon_pixels(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = Image.new("RGB", (200, 200), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((80, 20, 99, 39), fill=(244, 103, 24))
            draw.line((80, 20, 99, 39), fill=(14, 72, 190), width=3)
            render = root / "page.png"
            image.save(render)
            manifest = valid_manifest(render)
            block = manifest["blocks"][0]
            block.update(
                {
                    "translation": "Press [OK]",
                    "box": [20, 18, 150, 52],
                    "clean_box": [18, 18, 105, 45],
                    "rich_lines": [[
                        {"type": "text", "text": "Press ", "color": [0, 0, 0]},
                        {"type": "source_crop", "source_box": [80, 20, 100, 40], "alt": "original OK icon"},
                        {"type": "text", "text": "[OK]", "color": [1, 0.35, 0]},
                    ]],
                }
            )
            output = root / "translated.pdf"
            report = build_pdf(manifest, output)
            expected_hash = hashlib.sha256(image.crop((80, 20, 100, 40)).tobytes()).hexdigest()
            self.assertEqual(report["source_crop_run_count"], 1)
            self.assertEqual(report["mixed_color_block_count"], 1)
            self.assertEqual(report["source_crop_runs"][0]["pixel_sha256"], expected_hash)
            self.assertIn("Press", PdfReader(str(output)).pages[0].extract_text())
            self.assertIn("[OK]", PdfReader(str(output)).pages[0].extract_text())

    def test_delivery_requires_icon_and_mixed_color_reviews(self) -> None:
        manifest = valid_manifest(Path("fixture.png"))
        report = evaluate_evidence(
            manifest=manifest,
            extracted_by_page={1: "Test"},
            build_report={
                "rendered_blocks": [{"id": "p01-title", "font_size": 10, "complete": True}],
                "outside_approved_pixel_changes": 0,
            },
            output_page_count=1,
            geometry_match=True,
            visual_review={
                "reviewed_output_pages": [1],
                "text_overlap_failures": [],
                "clipping_failures": [],
                "unreviewed_images": 0,
                "untranslated_clear_image_labels": 0,
                "logo_review_complete": True,
                "header_footer_review_complete": True,
                "image_difference_review_complete": True,
                "full_render_review_complete": True,
            },
            residual_cjk=[],
            font_embedding_failures=[],
            automated_overlap_failures=[],
        )
        self.assertFalse(report["passed"])
        self.assertFalse(report["icon_review_complete"])
        self.assertFalse(report["source_icon_provenance_complete"])

    def test_delivery_rejects_missing_source_crop_provenance(self) -> None:
        manifest = valid_manifest(Path("fixture.png"))
        manifest["blocks"][0]["rich_lines"] = [[
            {"type": "text", "text": "Test"},
            {"type": "source_crop", "source_box": [80, 20, 100, 40], "alt": "original icon"},
        ]]
        review = {
            "reviewed_output_pages": [1], "text_overlap_failures": [], "clipping_failures": [],
            "unreviewed_images": 0, "untranslated_clear_image_labels": 0,
            "logo_review_complete": True, "header_footer_review_complete": True,
            "image_difference_review_complete": True, "full_render_review_complete": True,
            "icon_review_complete": True, "source_icon_provenance_complete": True,
            "icon_substitution_failures": [], "mixed_color_failures": [],
        }
        report = evaluate_evidence(
            manifest=manifest, extracted_by_page={1: "Test"},
            build_report={
                "rendered_blocks": [{"id": "p01-title", "font_size": 10, "complete": True}],
                "outside_approved_pixel_changes": 0, "source_crop_runs": [],
            },
            output_page_count=1, geometry_match=True, visual_review=review,
            residual_cjk=[], font_embedding_failures=[], automated_overlap_failures=[],
        )
        self.assertFalse(report["passed"])
        self.assertTrue(report["source_crop_provenance_failures"])


if __name__ == "__main__":
    result = unittest.main(verbosity=2, exit=False)
    print(json.dumps({"passed": result.result.wasSuccessful(), "tests": result.result.testsRun}))
    raise SystemExit(0 if result.result.wasSuccessful() else 1)
