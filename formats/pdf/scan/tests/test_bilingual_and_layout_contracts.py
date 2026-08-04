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
from verify_scan import filter_approved_bilingual_residuals


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


if __name__ == "__main__":
    unittest.main()
