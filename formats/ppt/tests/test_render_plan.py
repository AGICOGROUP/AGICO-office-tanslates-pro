from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
from argparse import Namespace


ROOT = Path(__file__).resolve().parents[1]
PPT_COM = ROOT / "scripts" / "ppt_com.ps1"
PIPELINE = ROOT / "scripts" / "ppt_pipeline.py"
POWERSHELL = shutil.which("powershell.exe")

import sys

sys.path.insert(0, str(ROOT / "scripts"))
from ppt_pipeline import (build_render_plan, run_powerpoint_render, command_render,
                          command_deliver, new_state, sha256_file)  # noqa: E402
from ppt_test_support import powerpoint_com_tests_enabled  # noqa: E402


class RenderPlanTests(unittest.TestCase):
    def test_render_environment_failures_allow_warned_delivery_but_not_known_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output.pptx"
            output.write_bytes(b"statically verified presentation")
            state = new_state({"source_file": "source.pptx", "source_sha256": "a" * 64}, "en")
            (root / "job-state.json").write_text(json.dumps(state), encoding="utf-8")
            (root / "verification.json").write_text(json.dumps({"passed": True, "output_sha256": sha256_file(output)}), encoding="utf-8")
            (root / "render-plan.json").write_text(json.dumps({"target_low_resolution": [1]}), encoding="utf-8")
            args = Namespace(output=output, job_dir=root, visual_review_passed=False)
            with mock.patch("ppt_pipeline.shutil.which", return_value=None):
                self.assertEqual(0, command_render(args))
            self.assertEqual(0, command_deliver(args))
            report = json.loads((root / "office-verification.json").read_text(encoding="utf-8"))
            self.assertEqual("unavailable", report["target"]["status"])
            # A partial render still needs visual review of the pages that exist.
            state = json.loads((root / "job-state.json").read_text(encoding="utf-8"))
            state["render_warning"]["slides_rendered"] = 1
            (root / "job-state.json").write_text(json.dumps(state), encoding="utf-8")
            with self.assertRaisesRegex(Exception, "visual review"):
                command_deliver(args)
            args.visual_review_passed = True
            self.assertEqual(0, command_deliver(args))
            output.write_bytes(b"changed file")
            with self.assertRaisesRegex(Exception, "unchanged output"):
                command_deliver(args)
            with mock.patch("ppt_pipeline.shutil.which", return_value="powershell.exe"), mock.patch(
                "ppt_pipeline.subprocess.run", side_effect=subprocess.TimeoutExpired("render", 60)
            ):
                self.assertEqual("unavailable", run_powerpoint_render(output, root / "thumbs", [1])["status"])
            with mock.patch("ppt_pipeline.shutil.which", return_value="powershell.exe"), mock.patch(
                "ppt_pipeline.subprocess.run", return_value=subprocess.CompletedProcess([], 2, "", "cannot open presentation")
            ):
                with self.assertRaisesRegex(Exception, "cannot open"):
                    run_powerpoint_render(output, root / "thumbs", [1])
            (root / "verification.json").write_text(json.dumps({"passed": False}), encoding="utf-8")
            with self.assertRaisesRegex(Exception, "structural verification failed"):
                command_render(args)

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


@unittest.skipUnless(
    powerpoint_com_tests_enabled(),
    "Set AGICO_RUN_POWERPOINT_COM_TESTS=1 to run Microsoft PowerPoint COM tests",
)
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
