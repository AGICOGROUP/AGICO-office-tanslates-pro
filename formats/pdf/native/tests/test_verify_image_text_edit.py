from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_image_text_edit.py"


def run(*args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *(str(value) for value in args)],
        capture_output=True,
        text=True,
    )


class VerifyImageTextEditTests(unittest.TestCase):
    def test_writes_difference_and_alpha_overlay_evidence(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = np.full((20, 30, 3), 255, dtype=np.uint8)
            rebuilt = source.copy()
            rebuilt[6:12, 10:16] = [245, 245, 245]
            Image.fromarray(source).save(root / "source.png")
            Image.fromarray(rebuilt).save(root / "rebuilt.png")
            (root / "regions.json").write_text("[[10, 6, 16, 12]]", encoding="utf-8")

            result = run(
                root / "source.png",
                root / "rebuilt.png",
                "--regions-json",
                root / "regions.json",
                "--evidence-dir",
                root / "evidence",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["outside_region_changes"], 0)
            self.assertTrue((root / "evidence" / "difference.png").is_file())
            self.assertTrue((root / "evidence" / "alpha-overlay.png").is_file())

    def test_rejects_changed_pixel_outside_approved_regions(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = np.full((12, 12, 3), 255, dtype=np.uint8)
            rebuilt = source.copy()
            rebuilt[1, 1] = [0, 0, 0]
            Image.fromarray(source).save(root / "source.png")
            Image.fromarray(rebuilt).save(root / "rebuilt.png")
            (root / "regions.json").write_text("[[5, 5, 8, 8]]", encoding="utf-8")

            result = run(
                root / "source.png",
                root / "rebuilt.png",
                "--regions-json",
                root / "regions.json",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("outside approved text regions", result.stderr)

    def test_rejects_broken_declared_line_anchor(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = np.full((20, 24, 3), 255, dtype=np.uint8)
            source[10, :] = [20, 20, 20]
            rebuilt = source.copy()
            rebuilt[10, 8:16] = [255, 255, 255]
            Image.fromarray(source).save(root / "source.png")
            Image.fromarray(rebuilt).save(root / "rebuilt.png")
            (root / "regions.json").write_text("[[8, 8, 16, 13]]", encoding="utf-8")
            (root / "anchors.json").write_text(
                json.dumps(
                    [
                        {
                            "id": "pipe-1",
                            "start": [7, 10],
                            "end": [16, 10],
                            "width": 1,
                            "pixel_tolerance": 24,
                        }
                    ]
                ),
                encoding="utf-8",
            )

            result = run(
                root / "source.png",
                root / "rebuilt.png",
                "--regions-json",
                root / "regions.json",
                "--line-anchors-json",
                root / "anchors.json",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("declared line continuity failed: pipe-1", result.stderr)


if __name__ == "__main__":
    unittest.main()
