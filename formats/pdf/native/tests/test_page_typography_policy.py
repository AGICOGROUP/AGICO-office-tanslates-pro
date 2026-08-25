from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from native_selectable_rebuild import (
    apply_page_typography_policy,
    promote_wrapped_heading_continuations,
    section_heading_depth,
    typography_group,
)


def block(block_id: str, role: str, size: float, bold: bool) -> dict:
    return {
        "id": block_id,
        "role": role,
        "bbox": [10, 10, 100, 30],
        "style": {"size": size, "role_size": size, "bold": bold},
    }


class PageTypographyPolicyTests(unittest.TestCase):
    def test_numbered_heading_depth_does_not_treat_decimal_measurement_as_heading(self) -> None:
        self.assertEqual(section_heading_depth("4、电控(普通集中控制)"), 1)
        self.assertEqual(section_heading_depth("4.1、普通集中控制系统"), 2)
        self.assertEqual(section_heading_depth("3.2.1 Instrumentation"), 3)
        self.assertIsNone(section_heading_depth("0.5mm彩钢板；既美观又能实现保温"))
        self.assertIsNone(section_heading_depth("1）电源及供配电系统"))

    def test_lowercase_short_line_after_numbered_heading_keeps_heading_style(self) -> None:
        page = {
            "blocks": [
                {
                    **block("heading", "heading-2-16", 16, True),
                    "bbox": [122, 100, 285, 116],
                    "source_text": "4.2、PLC自动化控制系",
                    "translation": "4.2 PLC Automation Control",
                },
                {
                    **block("continuation", "body-16", 16, False),
                    "bbox": [90, 131, 202, 147],
                    "source_text": "统（自选系统）",
                    "translation": "System (Optional)",
                    "heading_continuation": True,
                },
                {
                    **block("body", "body-16", 16, False),
                    "bbox": [122, 162, 274, 178],
                    "source_text": "1）电源及供配电系统",
                    "translation": "1) Power supply and distribution",
                },
            ]
        }

        promoted = promote_wrapped_heading_continuations(page)

        self.assertEqual(promoted, ["continuation"])
        self.assertEqual(page["blocks"][1]["role"], "heading-2-16")
        self.assertTrue(page["blocks"][1]["style"]["bold"])
        self.assertEqual(page["blocks"][2]["role"], "body-16")

    def test_roles_map_to_three_page_groups(self) -> None:
        self.assertEqual(typography_group("heading-1-18"), "major_title")
        self.assertEqual(typography_group("heading-3-12"), "minor_title")
        self.assertEqual(typography_group("body-11"), "body")

    def test_same_page_group_uses_one_size_and_weight(self) -> None:
        page = {
            "blocks": [
                block("major", "heading-1-18", 18, True),
                block("minor-1", "heading-2-14", 14, True),
                block("minor-2", "heading-3-13", 13, False),
                block("body-1", "body-11", 11, False),
                block("body-2", "body-10", 10, False),
            ]
        }
        evidence = apply_page_typography_policy(page)
        minor = [item for item in page["blocks"] if typography_group(item["role"]) == "minor_title"]
        body = [item for item in page["blocks"] if typography_group(item["role"]) == "body"]
        self.assertEqual(len({item["style"]["role_size"] for item in minor}), 1)
        self.assertEqual(len({item["style"]["bold"] for item in minor}), 1)
        self.assertEqual(len({item["style"]["role_size"] for item in body}), 1)
        self.assertTrue(evidence["major_title"]["font_size"] >= evidence["minor_title"]["font_size"])


if __name__ == "__main__":
    unittest.main()
