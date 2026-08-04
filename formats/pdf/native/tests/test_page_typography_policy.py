from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from native_selectable_rebuild import apply_page_typography_policy, typography_group


def block(block_id: str, role: str, size: float, bold: bool) -> dict:
    return {
        "id": block_id,
        "role": role,
        "bbox": [10, 10, 100, 30],
        "style": {"size": size, "role_size": size, "bold": bold},
    }


class PageTypographyPolicyTests(unittest.TestCase):
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
