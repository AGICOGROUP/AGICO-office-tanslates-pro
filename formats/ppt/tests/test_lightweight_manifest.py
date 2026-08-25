from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_manifest import ManifestError, validate_manifest  # noqa: E402


def manifest_with_image(decision: str, *, overlays: list[dict] | None = None) -> dict:
    return {
        "schema_version": 2,
        "source_file": "sample.pptx",
        "source_sha256": "a" * 64,
        "source_language": "zh-CN",
        "target_language": "fr",
        "format": "powerpoint",
        "occurrences": [],
        "translation_units": [],
        "image_groups": [{
            "sha256": "b" * 64,
            "decision": decision,
            "preserve_source_image": decision == "overlay",
            "overlay_ids": ["overlay-1"] if decision == "overlay" else [],
        }],
        "overlays": overlays or [],
    }


class LightweightImageManifestTests(unittest.TestCase):
    def validate(self, data: dict) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return validate_manifest(path, require_translations=True)

    def test_skip_target_is_valid_without_overlays(self):
        summary = self.validate(manifest_with_image("skip_target"))
        self.assertEqual(1, summary["skipped_target_images"])

    def test_skip_unclear_is_valid_without_overlays(self):
        summary = self.validate(manifest_with_image("skip_unclear"))
        self.assertEqual(1, summary["skipped_unclear_images"])

    def test_overlay_requires_editable_bilingual_below_overlay(self):
        data = manifest_with_image("overlay", overlays=[{
            "id": "overlay-1",
            "kind": "office_overlay",
            "localization_mode": "bilingual_below",
        }])
        summary = self.validate(data)
        self.assertEqual(1, summary["overlay_images"])

    def test_legacy_image_decision_is_rejected(self):
        with self.assertRaisesRegex(ManifestError, "unsupported decision"):
            self.validate(manifest_with_image("manual_review"))


if __name__ == "__main__":
    unittest.main()
