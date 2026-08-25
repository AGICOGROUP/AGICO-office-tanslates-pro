from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
OFFICE_EXPORT = REPO_ROOT / "scripts" / "office_com_pdf.ps1"
POWERSHELL = shutil.which("powershell.exe")

import sys

sys.path.insert(0, str(ROOT / "scripts"))
from ppt_pipeline import build_render_plan  # noqa: E402


class RenderPlanTests(unittest.TestCase):
    def test_powerpoint_pdf_export_hides_automation_window_and_alerts(self):
        script = OFFICE_EXPORT.read_text(encoding="utf-8")

        self.assertIn("ShowWindowAsync", script)
        self.assertIn("$app.DisplayAlerts = 1", script)
        self.assertGreaterEqual(script.count("Hide-PowerPointWindow $app"), 2)
        self.assertIn("$presentation.SaveAs($outputFull, 32)", script)

    def test_fast_plan_renders_all_targets_low_and_only_risk_slides_high(self):
        inventory = {
            "slides": [{"index": 1}, {"index": 2}, {"index": 3}],
            "risk_plan": {
                "route": "fast",
                "risk_slides": [2],
                "complex_reasons": [],
                "strict_reasons": [],
            },
        }

        plan = build_render_plan(inventory, verification_passed=True)

        self.assertEqual([], plan["source_high_resolution"])
        self.assertEqual([1, 2, 3], plan["target_low_resolution"])
        self.assertEqual([2], plan["target_high_resolution"])

    def test_strict_plan_compares_all_source_and_target_slides(self):
        inventory = {
            "slides": [{"index": 1}, {"index": 2}],
            "risk_plan": {
                "route": "strict",
                "risk_slides": [1],
                "complex_reasons": [],
                "strict_reasons": ["user-request"],
            },
        }

        plan = build_render_plan(inventory, verification_passed=True)

        self.assertEqual([1, 2], plan["source_high_resolution"])
        self.assertEqual([1, 2], plan["target_high_resolution"])

    def test_failed_verification_escalates_to_strict(self):
        inventory = {
            "slides": [{"index": 1}, {"index": 2}],
            "risk_plan": {"route": "fast", "risk_slides": []},
        }

        plan = build_render_plan(inventory, verification_passed=False)

        self.assertEqual("strict", plan["mode"])
        self.assertEqual([1, 2], plan["source_high_resolution"])


def powerpoint_available() -> bool:
    if os.name != "nt" or not POWERSHELL:
        return False
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-Command", "if([type]::GetTypeFromProgID('PowerPoint.Application')){exit 0}else{exit 2}"],
        capture_output=True,
    )
    return result.returncode == 0


@unittest.skipUnless(powerpoint_available(), "Microsoft PowerPoint COM is required")
class OfficePowerPointExportTests(unittest.TestCase):
    def test_one_powerpoint_session_exports_pdf_and_thumbnails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pptx"
            pdf = root / "final.pdf"
            thumbnails = root / "thumbnails"
            create_script = (
                "$app=New-Object -ComObject PowerPoint.Application;"
                "$deck=$app.Presentations.Add();"
                "$slide=$deck.Slides.Add(1,12);"
                "$shape=$slide.Shapes.AddTextbox(1,40,40,400,80);"
                "$shape.TextFrame.TextRange.Text='Verification';"
                f"$deck.SaveAs('{source}',24);"
                "$deck.Close();$app.Quit();"
                "[Runtime.InteropServices.Marshal]::FinalReleaseComObject($shape)|Out-Null;"
                "[Runtime.InteropServices.Marshal]::FinalReleaseComObject($slide)|Out-Null;"
                "[Runtime.InteropServices.Marshal]::FinalReleaseComObject($deck)|Out-Null;"
                "[Runtime.InteropServices.Marshal]::FinalReleaseComObject($app)|Out-Null"
            )
            created = subprocess.run(
                [POWERSHELL, "-NoProfile", "-Command", create_script],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
            )
            self.assertEqual(0, created.returncode, created.stderr)
            exported = subprocess.run(
                [
                    POWERSHELL,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(OFFICE_EXPORT),
                    "-InputPath",
                    str(source),
                    "-OutputPdf",
                    str(pdf),
                    "-Application",
                    "powerpoint",
                    "-ThumbnailDirectory",
                    str(thumbnails),
                    "-HighResolutionSlides",
                    "1",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
            )
            self.assertEqual(0, exported.returncode, exported.stderr)
            report = json.loads(exported.stdout)

        self.assertTrue(report["pdf_created"])
        self.assertEqual(1, report["powerpoint_starts"])
        self.assertEqual(1, report["presentation_opens"])
        self.assertEqual(1, report["low_resolution_slides"])
        self.assertEqual(1, report["high_resolution_slides"])


if __name__ == "__main__":
    unittest.main()
