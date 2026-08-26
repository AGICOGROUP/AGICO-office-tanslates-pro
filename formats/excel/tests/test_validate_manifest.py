from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_manifest.py"
sys.path.insert(0, str(ROOT / "scripts"))
import validate_manifest  # noqa: E402


class ManifestValidatorTests(unittest.TestCase):
    def make_v2_manifest(self):
        return {
            "schema_version": 2,
            "source_file": "sample.xlsx",
            "source_sha256": "a" * 64,
            "target_language": "en",
            "output_mode": "monolingual",
            "occurrences": [
                {
                    "id": "S1!A1",
                    "kind": "cell",
                    "sheet": "S1",
                    "address": "A1",
                    "source": "设备名称",
                    "context_key": "cell:header:equipment",
                    "protected_tokens": [],
                    "translation_unit_id": "tu-001",
                },
                {
                    "id": "S1!A8",
                    "kind": "cell",
                    "sheet": "S1",
                    "address": "A8",
                    "source": "设备名称",
                    "context_key": "cell:header:equipment",
                    "protected_tokens": [],
                    "translation_unit_id": "tu-001",
                },
            ],
            "translation_units": [
                {
                    "id": "tu-001",
                    "source": "设备名称",
                    "context_key": "cell:header:equipment",
                    "protected_tokens": [],
                    "translation": "Equipment Name",
                    "status": "translated",
                }
            ],
            "images": [],
        }

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

    def test_accepts_v2_manifest_with_two_occurrences_reusing_one_translation(self):
        report = validate_manifest.validate(self.make_v2_manifest())
        self.assertTrue(report["passed"], report["errors"])
        self.assertEqual(2, report["counts"]["occurrences"])
        self.assertEqual(1, report["counts"]["translation_units"])

    def test_v2_rejects_unknown_translation_unit(self):
        payload = self.make_v2_manifest()
        payload["occurrences"][1]["translation_unit_id"] = "missing"
        report = validate_manifest.validate(payload)
        self.assertFalse(report["passed"])
        self.assertIn("unknown translation_unit_id", " ".join(report["errors"]))

    def test_v2_rejects_duplicate_occurrence_and_mismatched_context(self):
        payload = self.make_v2_manifest()
        payload["occurrences"][1]["id"] = "S1!A1"
        payload["occurrences"][1]["context_key"] = "cell:note"
        report = validate_manifest.validate(payload)
        self.assertFalse(report["passed"])
        errors = " ".join(report["errors"])
        self.assertIn("duplicate id", errors)
        self.assertIn("context_key", errors)

    def test_v2_rejects_changed_protected_token_and_invalid_image_reason(self):
        payload = self.make_v2_manifest()
        payload["occurrences"][0]["source"] = "功率 45kW"
        payload["occurrences"][0]["protected_tokens"] = ["45kW"]
        payload["translation_units"][0].update(
            {
                "source": "功率 45kW",
                "protected_tokens": ["45kW"],
                "translation": "Power 55kW",
            }
        )
        payload["images"] = [
            {
                "id": "img-001",
                "sha256": "b" * 64,
                "occurrences": ["S1#Image1"],
                "status": "retain",
                "reason_code": "because-I-said-so",
            }
        ]
        report = validate_manifest.validate(payload)
        self.assertFalse(report["passed"])
        errors = " ".join(report["errors"])
        self.assertIn("changed protected token", errors)
        self.assertIn("reason_code", errors)

    def test_v2_rejects_unresolved_manual_image_review(self):
        payload = self.make_v2_manifest()
        payload["images"] = [
            {
                "id": "img-001",
                "sha256": "b" * 64,
                "occurrences": ["S1#Image1"],
                "status": "manual-review",
                "reason_code": "manual-review",
            }
        ]
        report = validate_manifest.validate(payload)
        self.assertFalse(report["passed"])
        self.assertIn("manual-review is not deliverable", " ".join(report["errors"]))

    def test_v2_rejects_retain_unit_when_translation_differs(self):
        payload = deepcopy(self.make_v2_manifest())
        payload["translation_units"][0].update(
            {"status": "retain", "reason": "identifier", "translation": "Changed"}
        )
        report = validate_manifest.validate(payload)
        self.assertFalse(report["passed"])
        self.assertIn("retain", " ".join(report["errors"]))
        payload = {
            "items": [{"id": 12, "source": "水泥", "translation": "Cement", "status": "translated", "protected_tokens": "15TPH"}],
            "images": [],
        }
        result = self.run_validator(payload)
        self.assertEqual(2, result.returncode)
        self.assertTrue(json.loads(result.stdout)["errors"])


if __name__ == "__main__":
    unittest.main()
