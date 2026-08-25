from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"


class BilingualCliTests(unittest.TestCase):
    def test_help_commands_start_without_deprecation_warnings(self) -> None:
        for script_name in ("bilingual_overlay.py", "inspect_layout.py"):
            with self.subTest(script=script_name):
                result = subprocess.run(
                    [sys.executable, str(SCRIPT_DIR / script_name), "--help"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                output = f"{result.stdout}\n{result.stderr}".lower()
                self.assertNotIn("deprecated", output)


if __name__ == "__main__":
    unittest.main()
