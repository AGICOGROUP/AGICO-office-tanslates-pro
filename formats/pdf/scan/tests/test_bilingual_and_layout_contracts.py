from __future__ import annotations

import sys
import hashlib
import tempfile
import unittest
from pathlib import Path

from PIL import Image


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from contracts import ManifestError, validate_manifest
from build_scan import build_pdf
from verify_scan import filter_approved_bilingual_residuals
from pypdf import PdfReader


def manifest_with(block: dict) -> dict:
    return {
        "source": "fixture.pdf",
        "source_sha256": "a" * 64,
        "selected_pages": [1],
        "pages": [{
            "source_page": 1,
            "width_pt": 200,
            "height_pt": 200,
            "pixel_width": 400,
            "pixel_height": 400,
            "render_path": "page.png",
            "render_sha256": "b" * 64,
            "dpi": 144,
        }],
        "source_lines": [
            {"id": "zh-1", "page": 1, "box": [10, 10, 30, 20], "text": "烟囱", "score": 0.99},
            {"id": "en-1", "page": 1, "box": [10, 22, 45, 32], "text": "Chimney", "score": 0.99},
        ],
        "blocks": [block],
    }


def bilingual_block(unmatched: int = 0) -> dict:
    return {
        "id": "diagram-1",
        "page": 1,
        "source_line_ids": ["zh-1", "en-1"],
        "source": "烟囱 / Chimney",
        "translation": "Already bilingual; preserve exact source pixels",
        "role": "diagram_label",
        "status": "bilingual_complete",
        "action": "preserve",
        "box": [5, 5, 60, 40],
        "bilingual_evidence": {
            "clear_source_label_count": 1,
            "matched_bilingual_pair_count": 1 - unmatched,
            "unmatched_source_label_count": unmatched,
            "source_region_sha256": "c" * 64,
        },
    }


class BilingualAndLayoutContractTests(unittest.TestCase):
    def test_add_bilingual_preserves_source_pixels_and_adds_selectable_translation(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            render = root / "page.png"
            Image.new("RGB", (400, 400), "white").save(render)
            manifest = manifest_with({
                "id": "label-es",
                "page": 1,
                "source_line_ids": ["zh-1", "en-1"],
                "source": "原文 / Existing",
                "translation": "Texto profesional",
                "role": "diagram_label",
                "status": "translated",
                "action": "add_bilingual",
                "box": [80, 40, 260, 78],
                "source_preserved": True,
                "placement": "below",
                "min_font": 7,
                "max_font": 10,
            })
            manifest["target_language"] = "es"
            manifest["pages"][0]["render_path"] = str(render)
            manifest["pages"][0]["render_sha256"] = hashlib.sha256(render.read_bytes()).hexdigest()
            output = root / "bilingual.pdf"
            report = build_pdf(manifest, output)
            self.assertEqual(report["changed_pixel_count"], 0)
            self.assertEqual(report["outside_approved_pixel_changes"], 0)
            self.assertIn("Texto profesional", PdfReader(str(output)).pages[0].extract_text())

    def test_add_bilingual_rejects_translation_over_source_text(self) -> None:
        manifest = manifest_with({
            "id": "label-es",
            "page": 1,
            "source_line_ids": ["zh-1", "en-1"],
            "source": "原文 / Existing",
            "translation": "Texto profesional",
            "role": "diagram_label",
            "status": "translated",
            "action": "add_bilingual",
            "box": [10, 10, 60, 35],
            "source_preserved": True,
            "placement": "below",
        })
        manifest["target_language"] = "es"
        with self.assertRaisesRegex(ManifestError, "overlaps source text"):
            validate_manifest(manifest)

    def test_add_bilingual_requires_target_language(self) -> None:
        manifest = manifest_with({
            "id": "label-es",
            "page": 1,
            "source_line_ids": ["zh-1", "en-1"],
            "source": "原文 / Existing",
            "translation": "Texto profesional",
            "role": "diagram_label",
            "status": "translated",
            "action": "add_bilingual",
            "box": [80, 40, 260, 78],
            "source_preserved": True,
            "placement": "below",
        })
        with self.assertRaisesRegex(ManifestError, "target_language"):
            validate_manifest(manifest)

    def test_complete_bilingual_region_can_be_preserved(self) -> None:
        validate_manifest(manifest_with(bilingual_block()))

    def test_partial_bilingual_region_cannot_be_preserved(self) -> None:
        with self.assertRaisesRegex(ManifestError, "incomplete bilingual coverage"):
            validate_manifest(manifest_with(bilingual_block(unmatched=1)))

    def test_preserve_confirm_requires_preserve_action(self) -> None:
        block = bilingual_block()
        block.update({"status": "preserve_confirm", "action": "replace", "clean_box": [5, 5, 60, 40]})
        with self.assertRaisesRegex(ManifestError, "preserve_confirm.*preserve"):
            validate_manifest(manifest_with(block))

    def test_hash_bound_bilingual_region_is_exempt_from_cjk_residual(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            render = Path(name) / "page.png"
            image = Image.new("RGB", (400, 400), "white")
            image.save(render)
            block = bilingual_block()
            block["box"] = [10, 10, 60, 40]
            block["bilingual_evidence"]["source_region_sha256"] = hashlib.sha256(
                image.crop((10, 10, 60, 40)).tobytes()
            ).hexdigest()
            manifest = manifest_with(block)
            manifest["pages"][0]["render_path"] = str(render)
            residual = [{"output_page": 1, "source_page": 1, "text": "烟囱", "box": [5, 5, 30, 20], "page_pixel_width": 200, "page_pixel_height": 200, "score": 0.9}]
            self.assertEqual(filter_approved_bilingual_residuals(residual, manifest), [])

    def test_add_bilingual_source_text_is_expected_residual(self) -> None:
        manifest = manifest_with({
            "id": "label-es", "page": 1, "source_line_ids": ["zh-1", "en-1"],
            "source": "source / Existing", "translation": "Texto profesional",
            "role": "diagram_label", "status": "translated", "action": "add_bilingual",
            "box": [80, 40, 260, 78], "source_preserved": True, "placement": "below",
        })
        manifest["target_language"] = "es"
        residual = [{
            "output_page": 1, "source_page": 1, "text": "\u539f\u6587", "box": [5, 5, 20, 12],
            "page_pixel_width": 200, "page_pixel_height": 200, "score": 0.9,
        }]
        self.assertEqual(filter_approved_bilingual_residuals(residual, manifest), [])


if __name__ == "__main__":
    unittest.main()
