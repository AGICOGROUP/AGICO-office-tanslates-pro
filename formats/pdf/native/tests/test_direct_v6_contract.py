from pathlib import Path
import unittest


SKILL = Path(__file__).resolve().parents[1] / "SKILL.md"


class DirectV6ContractTests(unittest.TestCase):
    def test_skill_declares_original_only_runner_contract(self):
        text = SKILL.read_text(encoding="utf-8")
        for required in (
            "only user-supplied artifact",
            "run_v6_job.py init",
            "run_v6_job.py resume",
            "run_v6_job.py verify",
            "stage is `verified`",
            "original image XObjects",
            "selectable PDF vector text",
            "Never use v5 or v6",
            "unreviewed_images",
            "untranslated_clear_image_labels",
            "logo_review_complete",
            "header_footer_high_resolution_review_complete",
            "text_overlap_failures",
        ):
            self.assertIn(required, text)


if __name__ == "__main__":
    unittest.main()
