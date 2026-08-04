from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_scan import apply_page_typography_policy, build_pdf, typography_group


class PageTypographyPolicyTests(unittest.TestCase):
    def test_role_groups_are_stable(self) -> None:
        self.assertEqual(typography_group("title"), "major_title")
        self.assertEqual(typography_group("subheading"), "minor_title")
        self.assertEqual(typography_group("list_item"), "body")

    def test_page_policy_unifies_each_group(self) -> None:
        blocks = [
            {"id": "h1", "role": "title", "max_font": 18, "min_font": 11, "bold": True},
            {"id": "h2", "role": "heading", "max_font": 14, "min_font": 10, "bold": True},
            {"id": "h3", "role": "subheading", "max_font": 13, "min_font": 9, "bold": False},
            {"id": "b1", "role": "body", "max_font": 11, "min_font": 7, "bold": False},
            {"id": "b2", "role": "list_item", "max_font": 10, "min_font": 7, "bold": False},
        ]
        evidence = apply_page_typography_policy(blocks)
        bodies = [item for item in blocks if typography_group(item["role"]) == "body"]
        minors = [item for item in blocks if typography_group(item["role"]) == "minor_title"]
        self.assertEqual(len({item["max_font"] for item in bodies}), 1)
        self.assertEqual(len({item["bold"] for item in minors}), 1)
        self.assertGreaterEqual(evidence["major_title"]["font_size"], evidence["minor_title"]["font_size"])

    def test_dense_body_block_reduces_all_body_blocks_uniformly(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            render = root / "page.png"
            Image.new("RGB", (400, 400), "white").save(render)
            blocks = [
                {"id": "b1", "page": 1, "source_line_ids": ["l1"], "source": "甲", "translation": "Short body text", "role": "body", "status": "translated", "action": "replace", "box": [20, 20, 360, 80], "clean_box": [20, 20, 50, 40], "background": [255, 255, 255], "max_font": 12, "min_font": 7},
                {"id": "b2", "page": 1, "source_line_ids": ["l2"], "source": "乙", "translation": "A much longer translated body paragraph that requires wrapping across several lines inside a deliberately smaller container", "role": "list_item", "status": "translated", "action": "replace", "box": [20, 100, 240, 180], "clean_box": [20, 100, 50, 120], "background": [255, 255, 255], "max_font": 12, "min_font": 7},
            ]
            manifest = {
                "source": "fixture.pdf", "source_sha256": "a" * 64,
                "selected_pages": [1],
                "pages": [{"source_page": 1, "width_pt": 200, "height_pt": 200, "render_path": str(render), "pixel_width": 400, "pixel_height": 400, "dpi": 144}],
                "source_lines": [{"id": "l1", "page": 1, "box": [20, 20, 50, 40], "text": "甲", "score": 1}, {"id": "l2", "page": 1, "box": [20, 100, 50, 120], "text": "乙", "score": 1}],
                "blocks": blocks,
            }
            report = build_pdf(manifest, root / "out.pdf")
            sizes = {item["font_size"] for item in report["rendered_blocks"]}
            self.assertEqual(len(sizes), 1)


if __name__ == "__main__":
    unittest.main()
