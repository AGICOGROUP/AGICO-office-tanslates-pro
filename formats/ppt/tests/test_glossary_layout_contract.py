from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT / "references" / "typography-and-fit.md"


class GlossaryAndLayoutContractTests(unittest.TestCase):
    def test_skill_requires_supplied_translation_before_model_preference(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8").lower()
        self.assertIn("../../references/水泥专业名词中英对照.md", skill)
        self.assertIn("exact full phrase", skill)
        self.assertIn("longest listed term", skill)
        self.assertIn("before model preference", skill)

    def test_peer_heading_and_body_typography_is_consistent(self):
        self.assertTrue(LAYOUT.is_file(), "typography/layout contract must be bundled")
        text = LAYOUT.read_text(encoding="utf-8").lower()
        self.assertIn("peer section headings", text)
        self.assertIn("one font size", text)
        self.assertIn("bold", text)
        self.assertIn("peer body text", text)

    def test_layout_changes_require_verified_overflow_or_collision(self):
        self.assertTrue(LAYOUT.is_file(), "typography/layout contract must be bundled")
        text = LAYOUT.read_text(encoding="utf-8").lower()
        self.assertIn("verified overflow or collision", text)
        self.assertIn("do not alter layout", text)
        self.assertIn("proportionally scale", text)
        self.assertIn("preserve aspect ratio", text)
        self.assertIn("manual review", text)


if __name__ == "__main__":
    unittest.main()
