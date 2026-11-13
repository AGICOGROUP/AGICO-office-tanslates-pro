import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from image_retention import RETAIN_CODES, retention_error
from translation_assets import merge_assets, pending_assets


class ImageRetentionTests(unittest.TestCase):
    def test_retention_categories_and_unreadable_are_distinct(self):
        for code in RETAIN_CODES:
            with self.subTest(code=code):
                self.assertIsNone(retention_error({"reason_code": code,
                    "reason": "Reviewed actual image"}, "skip_target"))
                self.assertIsNotNone(retention_error({"reason_code": code,
                    "reason": "Reviewed actual image"}, "skip_unclear"))
        self.assertIsNone(retention_error({"reason_code": "unreadable_text",
            "reason": "Lower-right source line is too blurred to read"}, "skip_unclear"))
        self.assertIsNotNone(retention_error({"reason_code": "unreadable_text",
            "reason": "Blurred"}, "skip_target"))

    def test_all_formats_reject_unjustified_retention_and_reopen_old_records(self):
        for fmt, field, status in (("ppt", "image_groups", "skip_target"),
                ("word", "image_reviews", "retain"), ("excel", "images", "reviewed")):
            key = "decision" if fmt == "ppt" else "status"
            for metadata in ({}, {"reason": "document_scan_left_in_source_language"},
                    {"reason": "budget exhausted", "reason_code": "budget"},
                    {"reason": "Keep seal", "reason_code": "geometry_conflict"},
                    {"reason_code": "logo_only", "reason": " "},
                    {"reason_code": ["logo_only"], "reason": "Logo"}):
                with self.subTest(fmt=fmt, metadata=metadata):
                    group = {"id": "a" * 64, "sha256": "a" * 64, key: status, **metadata}
                    manifest = {field: [copy.deepcopy(group)]}
                    self.assertEqual(1, len(pending_assets(manifest, fmt)))
                    self.assertTrue(merge_assets(manifest, [group], fmt))
                    repaired = {"id": "a" * 64, key: status,
                        "reason_code": "logo_only", "reason": "Only the company emblem"}
                    self.assertEqual([], merge_assets(manifest, [repaired], fmt))
                    self.assertEqual([], pending_assets(manifest, fmt))

    def test_update_cannot_inherit_old_retention_justification(self):
        group = {"sha256": "a" * 64, "decision": "skip_target",
                 "reason_code": "logo_only", "reason": "Only emblem"}
        manifest = {"image_groups": [group]}
        self.assertTrue(merge_assets(manifest, [{"id": "a" * 64,
            "decision": "skip_unclear"}], "ppt"))
        self.assertEqual(1, len(pending_assets(manifest, "ppt")))


if __name__ == "__main__":
    unittest.main()
