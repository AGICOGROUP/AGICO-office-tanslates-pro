from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
COM_SCRIPT = ROOT / "scripts" / "ppt_com.ps1"
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
