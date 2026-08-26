from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_skill.py"


class ValidatePowerPointSkillTests(unittest.TestCase):
    def test_validator_does_not_require_deleted_pdf_export_gate(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("office_com_pdf.ps1", source)


if __name__ == "__main__":
    unittest.main()
