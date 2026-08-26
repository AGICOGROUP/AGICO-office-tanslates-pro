import pathlib
import subprocess
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
        workflow = (ROOT / "references" / "powerpoint-workflow.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("scripts/ppt_pipeline.py", skill)
        self.assertIn("Microsoft PowerPoint", skill)
        self.assertIn("hidden background session", workflow)
        self.assertIn("without an external PDF conversion gate", workflow)
        self.assertNotIn("without deduplicating", skill)
        self.assertNotIn("Reopen and render every slide", skill)
        self.assertNotIn("use `scripts/ppt_com.ps1`", skill.lower())

    def test_com_forces_macro_disable_before_open(self):
        script = (ROOT / "scripts" / "ppt_com.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("AutomationSecurity = 3", script)
        self.assertLess(script.index("AutomationSecurity = 3"), script.index("Presentations.Open"))

    def test_embedded_image_translation_uses_only_three_fast_decisions(self):
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

        for text in (skill, image_rule, manifest_rule, cli_rule):
            self.assertIn("bilingual_below", text)
            for decision in ("skip_target", "skip_unclear", "overlay"):
                self.assertIn(decision, text)
            for legacy in ("manual_review", "text_region_replace", "risk_plan"):
                self.assertNotIn(legacy, text)
        self.assertIn("bilingual_below", overlay_rule)
        self.assertIn("preserve the original image", image_rule)
        self.assertIn("immediately below", image_rule)
        self.assertIn("single-pass", image_rule)
        self.assertIn("do not retry", image_rule)
        self.assertIn("powerpoint embedded images only", skill)
        self.assertIn("all readable source labels", image_rule)
        self.assertIn("partial target-language text does not skip the whole image", image_rule)
        self.assertIn("small but readable", image_rule)
        self.assertIn("selectable or copyable", image_rule)
        self.assertIn("embedded object", image_rule)
        self.assertIn("preview image", image_rule)

    def test_workflow_has_one_route_and_no_risk_tiers(self):
        text = "\n".join(
            (ROOT / path).read_text(encoding="utf-8").lower()
            for path in ("SKILL.md", "references/powerpoint-workflow.md")
        )
        for legacy in ("fast:", "complex:", "strict:", "risk escalation"):
            self.assertNotIn(legacy, text)

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
        tracked = subprocess.run(
            ["git", "ls-files", "-z", "formats/ppt"],
            cwd=ROOT.parents[1],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.split("\0")
        offenders = [
            path
            for path in tracked
            if path and "tests" not in pathlib.Path(path).parts
            and (
                forbidden_parts.intersection(pathlib.Path(path).parts)
                or pathlib.Path(path).suffix.lower() in {".ppt", ".pptx", ".pyc"}
            )
        ]
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
