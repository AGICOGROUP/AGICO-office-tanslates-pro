from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ExcelSkillContractTests(unittest.TestCase):
    def test_required_files_exist(self):
        required = {
            "SKILL.md",
            "agents/openai.yaml",
            "references/excel-workflow.md",
            "references/manifest-schema.md",
            "references/image-text-localization.md",
            "references/bilingual-row-layout.md",
            "references/pipeline-cli.md",
            "scripts/route_excel_file.py",
            "scripts/excel_pipeline.mjs",
            "scripts/excel_fast_pipeline.py",
            "scripts/resolve_repo_glossary.py",
            "scripts/query_repo_glossary.py",
            "scripts/excel_com_convert.ps1",
            "scripts/excel_com_verify.ps1",
            "scripts/validate_manifest.py",
        }
        missing = sorted(path for path in required if not (ROOT / path).is_file())
        self.assertEqual([], missing)

    def test_skill_uses_compact_one_command_prepare_and_finalize_flow(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        for token in (
            "excel_fast_pipeline.py prepare",
            "translation-worklist.json",
            "excel_fast_pipeline.py finalize",
            "stage-timings.json",
        ):
            self.assertIn(token, skill)
        self.assertNotIn("Read these files completely before execution", skill)

    def test_com_verifier_opens_recalculates_and_scans_without_exporting_pdf(self):
        script = (ROOT / "scripts" / "excel_com_verify.ps1").read_text(encoding="utf-8")
        self.assertIn("AutomationSecurity = 3", script)
        self.assertLess(script.index("AutomationSecurity = 3"), script.index("$source = Get-WorkbookReport"))
        for token in (
            "SourcePath",
            "InputPath",
            "CalculateFullRebuild",
            "SpecialCells",
            "source_formula_error_count",
            "output_formula_error_count",
            "new_formula_error_count",
            "Bilingual",
        ):
            self.assertIn(token, script)
        self.assertIn("new Excel error cells", script)
        self.assertNotIn("if ($formulaErrors -gt 0 -or $valueErrors -gt 0)", script)
        self.assertNotIn("ExportAsFixedFormat", script)
        self.assertNotIn("OutputDirectory", script)
        pipeline = (ROOT / "scripts" / "excel_pipeline.mjs").read_text(encoding="utf-8")
        self.assertNotIn("errors.push(`formula-error:", pipeline)

    def test_legacy_converter_is_macro_safe_and_validates_the_xlsx_once(self):
        script = (ROOT / "scripts" / "excel_com_convert.ps1").read_text(encoding="utf-8")
        for token in (
            "AutomationSecurity = 3",
            "ReadOnly",
            "HasVBProject",
            "SaveAs",
            "51",
            "source_sha256",
            "output_sha256",
        ):
            self.assertIn(token, script)
        self.assertLess(script.index("AutomationSecurity = 3"), script.index("Workbooks.Open"))

    def test_standard_flow_has_no_baseline_or_final_visual_render_gate(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        workflow = (ROOT / "references" / "excel-workflow.md").read_text(encoding="utf-8")
        combined = (skill + "\n" + workflow).casefold()
        for phrase in (
            "do not render a source baseline",
            "new error cells",
            "explicitly requests",
            "manual-review is not deliverable",
        ):
            self.assertIn(phrase, combined)
        self.assertNotIn("visual-review", combined)
        self.assertNotIn("visual-review", (ROOT / "references" / "pipeline-cli.md").read_text(encoding="utf-8"))

    def test_skill_routes_every_job_through_risk_driven_resumable_pipeline(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        workflow = (ROOT / "references" / "excel-workflow.md").read_text(encoding="utf-8")
        combined = skill + "\n" + workflow
        for token in (
            "excel_pipeline.mjs",
            "inspect",
            "prepare",
            "apply",
            "verify",
            "office-validate",
            "job-state.json",
            "safe deduplication",
            "SHA-256",
            "strict",
        ):
            self.assertIn(token, combined)
        for obsolete in (
            "do not deduplicate repeated text",
            "Review every image",
            "render every final sheet and print area",
        ):
            self.assertNotIn(obsolete, combined)

    def test_skill_is_excel_only_and_complete(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        required = [
            "translate-excel-professionally",
            "spreadsheets:Spreadsheets",
            ".xls",
            ".xlsx",
            "macro-enabled Office files are rejected",
            "relevant-glossary.json",
            "route_excel_file.py",
            "resolve_repo_glossary.py",
            "validate_manifest.py",
            "formula",
            "image",
            "office-validate",
        ]
        missing = [token for token in required if token not in skill]
        self.assertEqual([], missing)
        self.assertNotIn("../../references/水泥专业名词中英对照.md", skill)
        self.assertNotIn("final-renders", skill)
        self.assertNotIn("skip-render", skill)
        self.assertNotIn("exports required sheets to\n   PDF", skill)

    def test_bilingual_excel_defaults_to_paired_blue_translation_rows(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        workflow = (ROOT / "references" / "excel-workflow.md").read_text(encoding="utf-8")
        layout_path = ROOT / "references" / "bilingual-row-layout.md"
        self.assertIn("references/bilingual-row-layout.md", skill)
        self.assertIn("bilingual-row-layout.md", workflow)
        self.assertTrue(layout_path.is_file())
        layout = layout_path.read_text(encoding="utf-8")
        for phrase in (
            "source row",
            "translation row",
            "#EAF2F8",
            "#1F4E78",
            "italic",
            "Do not duplicate numeric values",
            "protected identifiers",
            "formulas",
            "page breaks",
        ):
            self.assertIn(phrase, layout)

    def test_no_placeholders_or_generated_caches(self):
        placeholders = []
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(ROOT)
            if "tests" in relative.parts:
                continue
            if path.suffix.lower() in {".md", ".yaml", ".py", ".ps1"}:
                text = path.read_text(encoding="utf-8", errors="ignore")
                if "TODO" in text or "[TODO" in text:
                    placeholders.append(str(relative))
        tracked = subprocess.run(
            ["git", "ls-files", "-z", "formats/excel"],
            cwd=ROOT.parents[1],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.split("\0")
        caches = sorted(
            path for path in tracked if "__pycache__" in Path(path).parts or path.endswith(".pyc")
        )
        self.assertEqual([], placeholders)
        self.assertEqual([], caches)


if __name__ == "__main__":
    unittest.main()
