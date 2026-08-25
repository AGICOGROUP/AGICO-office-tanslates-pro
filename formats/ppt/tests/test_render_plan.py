from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PPT_COM = ROOT / "scripts" / "ppt_com.ps1"
PIPELINE = ROOT / "scripts" / "ppt_pipeline.py"
POWERSHELL = shutil.which("powershell.exe")

import sys

sys.path.insert(0, str(ROOT / "scripts"))
from ppt_pipeline import build_render_plan  # noqa: E402


class RenderPlanTests(unittest.TestCase):
    def test_internal_powerpoint_render_hides_automation_window(self):
        script = PPT_COM.read_text(encoding="utf-8")
        pipeline = PIPELINE.read_text(encoding="utf-8")

        self.assertIn("PowerPointWindowGuard", script)
        self.assertLess(
            script.index("$windowGuard.Start()"),
            script.index("New-Object -ComObject PowerPoint.Application"),
        )
        self.assertIn('"render"', script)
        self.assertIn("ppt_com.ps1", pipeline)
        self.assertIn('"-Command",', pipeline)
        self.assertIn('"render",', pipeline)
        self.assertNotIn("office_com_pdf.ps1", pipeline)
        self.assertNotIn("final.pdf", pipeline)

    def test_single_plan_renders_every_target_once_at_low_resolution(self):
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
        self.assertEqual([], plan["target_high_resolution"])
        self.assertEqual("single", plan["mode"])

    def test_source_and_high_resolution_sets_stay_empty(self):
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

        self.assertEqual([], plan["source_high_resolution"])
        self.assertEqual([], plan["target_high_resolution"])

    def test_failed_verification_does_not_expand_render_scope(self):
        inventory = {
            "slides": [{"index": 1}, {"index": 2}],
            "risk_plan": {"route": "fast", "risk_slides": []},
        }

        plan = build_render_plan(inventory, verification_passed=False)

        self.assertEqual("single", plan["mode"])
        self.assertEqual([], plan["source_high_resolution"])


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
    def test_one_powerpoint_session_renders_slides_without_pdf(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pptx"
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
                    str(PPT_COM),
                    "-Command",
                    "render",
                    "-InputPath",
                    str(source),
                    "-OutputDirectory",
                    str(thumbnails),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
            )
            self.assertEqual(0, exported.returncode, exported.stderr)
            rendered = sorted(thumbnails.glob("slide-*.png"))
            pdfs = list(root.rglob("*.pdf"))

        self.assertEqual(1, len(rendered))
        self.assertEqual([], pdfs)


if __name__ == "__main__":
    unittest.main()
