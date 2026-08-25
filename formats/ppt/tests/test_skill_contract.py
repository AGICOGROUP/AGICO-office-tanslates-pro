import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class PowerPointOnlySkillContract(unittest.TestCase):
    def test_required_skill_files_exist(self):
        required = {
            "SKILL.md",
            "agents/openai.yaml",
            "references/powerpoint-workflow.md",
            "references/pipeline-cli.md",
            "references/typography-and-fit.md",
            "references/image-text-localization.md",
            "references/manifest-schema.md",
            "scripts/ppt_com.ps1",
            "scripts/ppt_pipeline.py",
            "scripts/inspect_pptx_package.py",
            "scripts/pptx_ooxml.py",
            "scripts/make_text_patch.py",
            "scripts/validate_manifest.py",
            "scripts/validate_skill.py",
            "scripts/resolve_repo_glossary.py",
        }
        missing = sorted(path for path in required if not (ROOT / path).is_file())
        self.assertEqual([], missing)

    def test_metadata_is_powerpoint_only(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: translate-powerpoint-professionally", skill)
        self.assertIn("PowerPoint", skill)
        self.assertIn(".ppt", skill)
        self.assertIn(".pptx", skill)

    def test_single_pipeline_replaces_command_composition(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("scripts/ppt_pipeline.py", skill)
        self.assertIn("Microsoft PowerPoint", skill)
        self.assertNotIn("without deduplicating", skill)
        self.assertNotIn("Reopen and render every slide", skill)
        self.assertNotIn("use `scripts/ppt_com.ps1`", skill.lower())

    def test_embedded_image_translation_uses_two_precision_modes(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8").lower()
        image_rule = (ROOT / "references" / "image-text-localization.md").read_text(
            encoding="utf-8"
        ).lower()
        overlay_rule = (ROOT / "references" / "overlay-schema.md").read_text(
            encoding="utf-8"
        ).lower()
        manifest_rule = (ROOT / "references" / "manifest-schema.md").read_text(
            encoding="utf-8"
        ).lower()
        cli_rule = (ROOT / "references" / "pipeline-cli.md").read_text(
            encoding="utf-8"
        ).lower()

        for text in (skill, image_rule, overlay_rule, manifest_rule, cli_rule):
            self.assertIn("bilingual_below", text)
            self.assertIn("text_region_replace", text)
        self.assertIn("preserve the original image", image_rule)
        self.assertIn("immediately below", image_rule)
        self.assertIn("outside-mask", image_rule)
        self.assertIn("single-pass", image_rule)
        self.assertIn("target-language-already-present", image_rule)
        self.assertIn("skip", image_rule)
        self.assertIn("powerpoint embedded images only", skill)

    def test_deliverable_has_no_other_format_or_router_content(self):
        suffixes = {".md", ".yaml", ".json", ".py", ".ps1"}
        text = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in ROOT.rglob("*")
            if path.is_file()
            and "tests" not in path.relative_to(ROOT).parts
            and path.suffix.lower() in suffixes
        ).lower()
        forbidden = [
            ".doc",
            ".docx",
            ".xls",
            ".xlsx",
            "pdf-adapter",
            "word-adapter",
            "excel-adapter",
            "route_document",
            "routing-contract",
            "multi-format",
        ]
        found = [token for token in forbidden if token in text]
        self.assertEqual([], found)

    def test_no_samples_work_products_or_caches(self):
        forbidden_parts = {"work", "renders", "__pycache__"}
        offenders = [
            str(path.relative_to(ROOT))
            for path in ROOT.rglob("*")
            if "tests" not in path.relative_to(ROOT).parts
            and (
                forbidden_parts.intersection(path.parts)
                or path.suffix.lower() in {".ppt", ".pptx", ".pyc"}
            )
        ]
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
