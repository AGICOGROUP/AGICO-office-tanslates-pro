from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_manifest.py"


class ManifestValidatorTests(unittest.TestCase):
    def run_validator(self, payload):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(VALIDATOR), str(path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

    def test_accepts_complete_manifest(self):
        payload = {
            "items": [
                {"id": "Sheet1!A1", "source": "水泥", "translation": "Cement", "status": "translated", "protected_tokens": []},
                {"id": "Sheet1!A2", "source": "ZKRM 15TPH", "translation": "ZKRM 15TPH", "status": "retain", "reason": "model code", "protected_tokens": ["ZKRM", "15TPH"]},
            ],
            "images": [{"id": "Sheet1#Image1", "status": "reviewed", "reason": "no text"}],
        }
        result = self.run_validator(payload)
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertTrue(json.loads(result.stdout)["passed"])

    def test_rejects_pending_or_token_damaging_manifest(self):
        payload = {
            "items": [
                {"id": "Sheet1!A1", "source": "功率 45kW", "translation": "Power 55kW", "status": "translated", "protected_tokens": ["45kW"]},
                {"id": "Sheet1!A2", "source": "备注", "translation": "", "status": "pending", "protected_tokens": []},
            ],
            "images": [],
        }
        result = self.run_validator(payload)
        self.assertEqual(2, result.returncode)
        report = json.loads(result.stdout)
        self.assertFalse(report["passed"])
        self.assertGreaterEqual(len(report["errors"]), 2)

    def test_rejects_retain_when_translation_differs_from_source(self):
        payload = {
            "items": [{"id": "Sheet1!A1", "source": "ZKRM", "translation": "Changed", "status": "retain", "reason": "model code", "protected_tokens": []}],
            "images": [],
        }
        result = self.run_validator(payload)
        self.assertEqual(2, result.returncode)
        self.assertIn("retain", result.stdout)

    def test_rejects_non_object_manifest_and_bad_protected_token_type(self):
        result = self.run_validator([])
        self.assertEqual(2, result.returncode)
        self.assertTrue(json.loads(result.stdout)["errors"])
        payload = {
            "items": [{"id": 12, "source": "水泥", "translation": "Cement", "status": "translated", "protected_tokens": "15TPH"}],
            "images": [],
        }
        result = self.run_validator(payload)
        self.assertEqual(2, result.returncode)
        self.assertTrue(json.loads(result.stdout)["errors"])


if __name__ == "__main__":
    unittest.main()
