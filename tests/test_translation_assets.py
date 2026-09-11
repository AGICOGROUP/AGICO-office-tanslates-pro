import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from translation_assets import merge_assets


class TranslationAssetsTests(unittest.TestCase):
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
