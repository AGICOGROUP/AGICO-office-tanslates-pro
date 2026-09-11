import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from translation_assets import merge_assets


class TranslationAssetsTests(unittest.TestCase):
    def test_known_image_id_can_omit_redundant_hash(self):
        digest = "a" * 64
        manifest = {"images": [{"id": "img-" + digest[:16], "sha256": digest,
                                "status": "manual-review"}]}
        decision = {"id": "img-" + digest[:16], "status": "retain"}
        self.assertEqual(merge_assets(manifest, [decision], "excel"), [])
        self.assertEqual(manifest["images"][0]["status"], "retain")
        self.assertEqual(manifest["images"][0]["sha256"], digest)

    def test_missing_hash_does_not_accept_unknown_id_or_explicit_hash_conflict(self):
        manifest = {"images": [{"id": "img-a", "sha256": "a" * 64,
                                "status": "manual-review"}]}
        for decision in ({"id": "img-unknown", "status": "retain"},
                         {"id": "img-a", "sha256": "b" * 64, "status": "retain"}):
            with self.subTest(decision=decision):
                self.assertTrue(merge_assets(manifest, [decision], "excel"))
                self.assertEqual(manifest["images"][0]["status"], "manual-review")

    def test_overlay_sets_preservation_metadata_and_skip_removes_old_shapes(self):
        manifest = {"image_groups": [{"sha256": "a"*64, "decision": "pending", "overlay_ids": []}], "overlays": []}
        decision = {"id": "a"*64, "sha256": "a"*64, "decision": "overlay", "overlays": [{"id": "label", "translation": "Cooler",
                    "location": {"page_or_slide": 1, "host_shape_id": 2},
                    "source_region": {"x": 0, "y": 0, "w": .5, "h": .2}, "region": {"x": 0, "y": .2, "w": .5, "h": .2}}]}
        self.assertFalse(merge_assets(manifest, [decision], "ppt"))
        self.assertTrue(manifest["image_groups"][0].get("preserve_source_image"))
        decision.update(decision="skip_target")
        self.assertFalse(merge_assets(manifest, [decision], "ppt"))
        self.assertEqual(manifest["image_groups"][0]["overlay_ids"], [])
        self.assertEqual(manifest["overlays"], [])

    def test_invalid_neighbor_and_incomplete_overlay_return_repair(self):
        manifest = {"image_groups": [{"sha256": "a"*64, "decision": "pending", "overlay_ids": []}], "overlays": []}
        errors = merge_assets(manifest, [None, {"id": "a"*64, "sha256": "a"*64, "decision": "overlay",
                                              "overlays": [{"id": "label", "translation": "Cooler"}]}], "ppt")
        self.assertEqual(len(errors), 2)
        self.assertEqual(manifest["image_groups"][0]["decision"], "pending")
        self.assertIn("location", manifest["image_groups"][0]["decision_error"])


if __name__ == "__main__":
    unittest.main()
