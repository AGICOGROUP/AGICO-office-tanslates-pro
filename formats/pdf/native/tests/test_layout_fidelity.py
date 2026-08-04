from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

from PIL import Image, ImageDraw


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "pdf_translation_pipeline.py"
)
SPEC = importlib.util.spec_from_file_location("pdf_translation_pipeline", SCRIPT)
assert SPEC and SPEC.loader
pipeline = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pipeline
SPEC.loader.exec_module(pipeline)


def char(
    text: str,
    x0: float,
    x1: float,
    *,
    top: float = 10,
    bottom: float = 20,
    font: str = "SimSun",
    size: float = 9,
    color=(0.0, 0.0, 0.0, 1.0),
):
    return {
        "text": text,
        "x0": x0,
        "x1": x1,
        "top": top,
        "bottom": bottom,
        "width": x1 - x0,
        "height": bottom - top,
        "fontname": font,
        "size": size,
        "non_stroking_color": color,
        "matrix": (1, 0, 0, 1, 0, 0),
    }


class CharacterModelTests(unittest.TestCase):
    def test_line_record_keeps_mixed_color_runs_and_character_boxes(self):
        chars = [
            char("国", 10, 19, color=(0.063, 0.554, 0.938, 0.0)),
            char("家", 19, 28, color=(0.063, 0.554, 0.938, 0.0)),
            char("|", 29, 32, font="ArialMT"),
            char("中", 33, 42, color=(0.063, 0.554, 0.938, 0.0)),
            char("国", 42, 51, color=(0.063, 0.554, 0.938, 0.0)),
        ]
        record = pipeline.line_record(
            {
                "text": "国家|中国",
                "x0": 10,
                "x1": 51,
                "top": 10,
                "bottom": 20,
                "chars": chars,
            },
            400,
        )
        self.assertIsNotNone(record)
        self.assertEqual(len(record["characters"]), 5)
        self.assertGreaterEqual(len(record["runs"]), 3)
        self.assertEqual(record["runs"][0]["color_rgb"], [239, 114, 16])
        self.assertTrue(record["characters"][2]["protected"])

    def test_different_colors_do_not_merge_into_one_style_block(self):
        left = {
            "text": "第一行",
            "bbox": [10, 10, 300, 20],
            "size": 9,
            "bold": False,
            "rotation": 0,
            "color_rgb": [0, 0, 0],
        }
        right = {
            "text": "第二行",
            "bbox": [10, 22, 300, 32],
            "size": 9,
            "bold": False,
            "rotation": 0,
            "color_rgb": [239, 114, 16],
        }
        self.assertFalse(pipeline.can_group(left, right, 400))

    def test_symbol_tokens_are_protected(self):
        for token in ("→", "◄", "►", "•", "[OK]", "μmol/mol", "70 °C"):
            self.assertTrue(pipeline.is_protected_token(token), token)


class LayoutStructureTests(unittest.TestCase):
    def test_segments_follow_table_cell_boundaries(self):
        chars = [
            char("测", 106, 115),
            char("量", 115, 124),
            char("参", 124, 133),
            char("数", 133, 142),
            char("量", 186, 195),
            char("程", 195, 204),
            char("分", 284, 293),
            char("辨", 293, 302),
            char("率", 302, 311),
        ]
        cells = [
            [100, 0, 180, 30],
            [180, 0, 280, 30],
            [280, 0, 360, 30],
        ]
        segments = pipeline.segment_characters(chars, cells)
        self.assertEqual(["测量参数", "量程", "分辨率"], [item["text"] for item in segments])
        self.assertEqual([0, 1, 2], [item["cell_index"] for item in segments])

    def test_role_font_size_is_shared_instead_of_independent(self):
        styles = [
            {"role": "heading-2", "source_size": 11.04},
            {"role": "heading-2", "source_size": 11.04},
            {"role": "body", "source_size": 9.0},
        ]
        targets = pipeline.resolve_role_font_sizes(styles, scale=2.0)
        self.assertEqual(targets[0], targets[1])
        self.assertGreater(targets[0], targets[2])

    def test_table_translation_is_split_by_unchanged_technical_tokens(self):
        parts = pipeline.semantic_table_parts(
            [
                "CO，氢气补偿",
                "0~400000 μmol/mol",
                "±2%测量值",
                "1μmol/mol",
            ],
            "CO, H₂-compensated 0 to 400,000 μmol/mol ±2% of reading 1 μmol/mol",
        )
        self.assertEqual(
            [
                "CO, H₂-compensated",
                "0 to 400,000 μmol/mol",
                "±2% of reading",
                "1 μmol/mol",
            ],
            parts,
        )

    def test_implicit_table_columns_are_recovered_from_large_text_gaps(self):
        chars = [
            char("压", 106, 115, top=100, bottom=110),
            char("差", 115, 124, top=100, bottom=110),
            char("1", 124, 129, top=100, bottom=110, font="Arial"),
            char("-", 186, 190, top=100, bottom=110, font="Arial"),
            char("4", 190, 195, top=100, bottom=110, font="Arial"),
            char("0", 195, 200, top=100, bottom=110, font="Arial"),
            char("0", 284, 289, top=100, bottom=110, font="Arial"),
            char(".", 289, 292, top=100, bottom=110, font="Arial"),
            char("0", 292, 297, top=100, bottom=110, font="Arial"),
            char("1", 297, 302, top=100, bottom=110, font="Arial"),
        ]
        records = [pipeline.character_record(item) for item in chars]
        line = {
            "bbox": [106, 100, 302, 110],
            "characters": records,
            "segments": [{"cell_index": -1, "text": "压差1", "characters": records[:3]}],
        }
        items = pipeline.table_segment_targets(
            line,
            "Differential pressure 1 -40 to 40 hPa 0.01 hPa",
            [
                {"bbox": [183, 95, 377, 115]},
                {"bbox": [282, 200, 377, 220]},
            ],
        )
        self.assertEqual(3, len(items))
        self.assertLess(items[0]["right"], items[1]["right"])
        self.assertLess(items[1]["right"], items[2]["right"])


class RenderingPolicyTests(unittest.TestCase):
    def test_preserved_prefix_is_not_repainted(self):
        source = "Country version 设定国家版本"
        translation = "Country version Sets the country version"
        plan = pipeline.plan_preserved_prefix(source, translation)
        self.assertEqual(plan["preserved_prefix"], "Country version")
        self.assertEqual(plan["text_to_draw"], "Sets the country version")

    def test_fit_policy_rejects_excessive_random_shrink(self):
        policy = pipeline.FitPolicy(minimum_role_scale=0.82)
        self.assertFalse(policy.accepts(8, 12))
        self.assertTrue(policy.accepts(10, 12))

    def test_character_cleanup_preserves_table_line(self):
        source = Image.new("RGB", (20, 20), "white")
        ImageDraw.Draw(source).line((0, 10, 19, 10), fill="black", width=1)
        output = source.copy()
        pipeline.restore_character_boxes(
            output,
            source,
            [
                {
                    "text": "中",
                    "bbox": [6, 6, 12, 14],
                }
            ],
            set(),
            1,
            1,
        )
        pipeline.restore_table_lines(
            output,
            source,
            [{"bbox": [0, 0, 19, 10]}],
            1,
            1,
        )
        self.assertTrue(all(output.getpixel((x, 10)) == (0, 0, 0) for x in range(5, 14)))


if __name__ == "__main__":
    unittest.main()
