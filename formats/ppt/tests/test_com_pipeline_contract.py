from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
COM_SCRIPT = ROOT / "scripts" / "ppt_com.ps1"
PIPELINE_SCRIPT = ROOT / "scripts" / "ppt_pipeline.py"
POWERSHELL = shutil.which("powershell.exe")


def powerpoint_available() -> bool:
    if os.name != "nt" or not POWERSHELL:
        return False
    result = subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-Command",
            "if([type]::GetTypeFromProgID('PowerPoint.Application')){exit 0}else{exit 2}",
        ],
        capture_output=True,
    )
    return result.returncode == 0


@unittest.skipUnless(powerpoint_available(), "Microsoft PowerPoint COM is required")
class PowerPointComPipelineContractTests(unittest.TestCase):
    def test_com_window_guard_starts_before_powerpoint(self):
        script = (ROOT / "scripts" / "ppt_com.ps1").read_text(encoding="utf-8")
        self.assertIn("PowerPointWindowGuard", script)
        self.assertLess(
            script.index("$windowGuard.Start()"),
            script.index("New-Object -ComObject PowerPoint.Application"),
        )

    def test_apply_command_adds_image_overlays_before_its_single_save(self):
        script = COM_SCRIPT.read_text(encoding="utf-8-sig")
        apply_block = script.split('"apply" {', 1)[1].split('"apply-overlays" {', 1)[0]
        self.assertIn("Apply-OverlayManifest $presentation $ManifestPath", apply_block)
        self.assertEqual(1, apply_block.count("$presentation.Save()"))

    def test_inspect_converts_legacy_ppt_inside_the_pipeline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "legacy.ppt"
            job = root / "job"
            create_script = (
                "$app=New-Object -ComObject PowerPoint.Application;"
                "$deck=$app.Presentations.Add();"
                "$slide=$deck.Slides.Add(1,12);"
                "$shape=$slide.Shapes.AddTextbox(1,40,40,400,80);"
                "$shape.TextFrame.TextRange.Text='篦式冷却机';"
                f"$deck.SaveAs('{source}',1);"
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
            inspected = subprocess.run(
                [
                    sys.executable,
                    str(PIPELINE_SCRIPT),
                    "inspect",
                    "--input",
                    str(source),
                    "--job-dir",
                    str(job),
                    "--target-language",
                    "en",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
            )
            self.assertEqual(0, inspected.returncode, inspected.stderr)
            inventory = json.loads((job / "inventory.json").read_text(encoding="utf-8"))
            state = json.loads((job / "job-state.json").read_text(encoding="utf-8"))

        self.assertEqual("legacy.ppt", inventory["source_file"])
        self.assertTrue(inventory["working_source_path"].endswith("working-source.pptx"))
        self.assertEqual(1, state["metrics"]["powerpoint_starts"])

    def test_apply_consumes_schema_v2_and_writes_translation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pptx"
            output = root / "output.pptx"
            manifest = root / "manifest.json"
            extracted = root / "extracted.json"
            create_script = (
                "$app=New-Object -ComObject PowerPoint.Application;"
                "$deck=$app.Presentations.Add();"
                "$slide=$deck.Slides.Add(1,12);"
                "$shape=$slide.Shapes.AddTextbox(1,40,40,400,80);"
                "$shape.TextFrame.TextRange.Text=('篦式冷却机'+[char]13+'重复标题');"
                "$id=[int]$shape.Id;"
                f"$deck.SaveAs('{source}',24);"
                "$deck.Close();$app.Quit();"
                "[Runtime.InteropServices.Marshal]::FinalReleaseComObject($shape)|Out-Null;"
                "[Runtime.InteropServices.Marshal]::FinalReleaseComObject($slide)|Out-Null;"
                "[Runtime.InteropServices.Marshal]::FinalReleaseComObject($deck)|Out-Null;"
                "[Runtime.InteropServices.Marshal]::FinalReleaseComObject($app)|Out-Null;"
                "$id"
            )
            created = subprocess.run(
                [POWERSHELL, "-NoProfile", "-Command", create_script],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
            )
            self.assertEqual(0, created.returncode, created.stderr)
            deadline = time.monotonic() + 5
            while not source.is_file() and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(source.is_file(), "PowerPoint did not finish saving the test deck")
            shape_id = int(created.stdout.strip().splitlines()[-1])
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "source_file": source.name,
                        "source_path": str(source),
                        "source_sha256": "a" * 64,
                        "source_language": "zh-CN",
                        "target_language": "en",
                        "format": "powerpoint",
                        "occurrences": [
                            {
                                "id": f"ppt/slide:1/shape:{shape_id}/paragraph:1",
                                "kind": "ppt_paragraph",
                                "source_text": "篦式冷却机",
                                "translation_unit_id": "tu-cooler",
                                "slide_index": 1,
                                "shape_id": shape_id,
                                "paragraph_index": 1,
                                "role": "body",
                                "context_signature": "body",
                                "protected_tokens": [],
                            },
                            {
                                "id": f"ppt/slide:1/shape:{shape_id}/paragraph:2",
                                "kind": "ppt_paragraph",
                                "source_text": "重复标题",
                                "translation_unit_id": "tu-title",
                                "slide_index": 1,
                                "shape_id": shape_id,
                                "paragraph_index": 2,
                                "role": "body",
                                "context_signature": "body",
                                "protected_tokens": [],
                            }
                        ],
                        "translation_units": [
                            {
                                "id": "tu-cooler",
                                "source_text": "篦式冷却机",
                                "translation": "Grate cooler",
                                "role": "body",
                                "context_signature": "body",
                                "protected_tokens": [],
                            },
                            {
                                "id": "tu-title",
                                "source_text": "重复标题",
                                "translation": "Repeated heading",
                                "role": "body",
                                "context_signature": "body",
                                "protected_tokens": [],
                            }
                        ],
                        "image_groups": [],
                        "risk_plan": {"route": "complex", "complex_reasons": ["integration-test"], "strict_reasons": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            applied = subprocess.run(
                [
                    POWERSHELL,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(COM_SCRIPT),
                    "-Command",
                    "apply",
                    "-InputPath",
                    str(source),
                    "-OutputPath",
                    str(output),
                    "-ManifestPath",
                    str(manifest),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
            )
            self.assertEqual(0, applied.returncode, applied.stderr)
            apply_report = json.loads(applied.stdout)
            self.assertEqual(2, apply_report["occurrences"])
            self.assertEqual(1, apply_report["slides_indexed"])
            self.assertEqual(1, apply_report["fit_operations"])

            inspected = subprocess.run(
                [
                    POWERSHELL,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(COM_SCRIPT),
                    "-Command",
                    "extract",
                    "-InputPath",
                    str(output),
                    "-OutputPath",
                    str(extracted),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
            )
            self.assertEqual(0, inspected.returncode, inspected.stderr)
            report = json.loads(extracted.read_text(encoding="utf-8-sig"))

        self.assertEqual(
            ["Grate cooler", "Repeated heading"],
            [item["source_text_normalized"] for item in report["items"]],
        )


if __name__ == "__main__":
    unittest.main()
