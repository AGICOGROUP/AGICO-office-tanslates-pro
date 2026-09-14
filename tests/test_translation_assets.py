import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from translation_assets import merge_assets


class TranslationAssetsTests(unittest.TestCase):
    def test_word_localized_image_enforces_source_ratio_and_minimum_pixels(self):
        with tempfile.TemporaryDirectory() as folder:
            replacement = Path(folder) / "translated.png"
            Image.new("RGB", (200, 100), "white").save(replacement)
            manifest = {"image_reviews": [{"id": "img", "sha256": "a" * 64, "status": "pending"}]}
            good = {"id": "img", "status": "localized", "replacement_path": str(replacement),
                    "source_pixel_width": 100, "source_pixel_height": 50}
            self.assertEqual(merge_assets(manifest, [good], "word"), [])
            self.assertEqual(manifest["image_reviews"][0]["source_pixel_width"], 100)
            manifest["image_reviews"][0]["status"] = "pending"
            bad = {**good, "source_pixel_width": 101}
            self.assertTrue(merge_assets(manifest, [bad], "word"))
            self.assertEqual(manifest["image_reviews"][0]["status"], "pending")

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

    def test_native_overlay_is_rejected_and_does_not_complete_image(self):
        manifest = {"image_groups": [{"sha256": "a"*64, "decision": "pending", "overlay_ids": []}], "overlays": []}
        decision = {"id": "a"*64, "sha256": "a"*64, "decision": "overlay", "overlays": [{"id": "label", "translation": "Cooler",
                    "location": {"page_or_slide": 1, "host_shape_id": 2},
                    "source_region": {"x": 0, "y": 0, "w": .5, "h": .2}, "region": {"x": 0, "y": .2, "w": .5, "h": .2}}]}
        self.assertTrue(merge_assets(manifest, [decision], "ppt"))
        self.assertEqual(manifest["image_groups"][0]['decision'], 'pending')
        self.assertEqual(manifest['overlays'], [])
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
        self.assertIn("GPT image editing", manifest["image_groups"][0]["decision_error"])


if __name__ == "__main__":
    unittest.main()
