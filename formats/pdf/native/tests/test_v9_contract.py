from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "SKILL.md"
ROUTING = ROOT / "references" / "image-localization-routing.md"
OPENAI_YAML = ROOT / "agents" / "openai.yaml"


class V9SkillContractTests(unittest.TestCase):
    def test_skill_links_the_image_localization_router(self):
        content = SKILL.read_text(encoding="utf-8")

        self.assertRegex(
            content,
            r"\[image-localization-routing\.md\]\(references/image-localization-routing\.md\)",
        )
        self.assertTrue(ROUTING.is_file())

    def test_router_declares_all_fail_closed_methods(self):
        content = ROUTING.read_text(encoding="utf-8")

        for method in (
            "native_edit",
            "deterministic_cleanup",
            "anchored_line_restore",
            "constrained_clean_base",
            "preserve_confirm",
        ):
            self.assertIn(f"`{method}`", content)
        self.assertIn("[CONFIRM]", content)
        self.assertIn("text-free clean base", content)
        self.assertIn("embedded PDF vector text", content)

    def test_default_prompt_requires_routing_and_structural_evidence(self):
        content = OPENAI_YAML.read_text(encoding="utf-8")

        self.assertIn("image-method routing", content)
        self.assertIn("structural-line evidence", content)
        self.assertNotRegex(content, re.compile(r"v\d+", re.IGNORECASE))


if __name__ == "__main__":
    unittest.main()
