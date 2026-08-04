from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from layout_adjustments import LayoutAdjustmentError, validate_layout_adjustment


def valid() -> dict:
    return {"page": 1, "asset_id": "image-1", "original_box": [100, 100, 300, 200], "target_box": [160, 110, 320, 190], "scale": 0.8, "trigger": "text_does_not_fit", "fit_failure": True, "approved_background_regions": [[100, 100, 300, 200]]}


class LayoutAdjustmentTests(unittest.TestCase):
    def test_valid_shift_and_uniform_shrink_passes(self) -> None:
        validate_layout_adjustment(valid(), 600, 800, [])

    def test_aspect_ratio_change_fails(self) -> None:
        item = valid(); item["target_box"] = [160, 110, 320, 210]
        with self.assertRaises(LayoutAdjustmentError): validate_layout_adjustment(item, 600, 800, [])

    def test_adjustment_before_fit_failure_fails(self) -> None:
        item = valid(); item["fit_failure"] = False
        with self.assertRaises(LayoutAdjustmentError): validate_layout_adjustment(item, 600, 800, [])

    def test_protected_overlap_fails(self) -> None:
        with self.assertRaises(LayoutAdjustmentError): validate_layout_adjustment(valid(), 600, 800, [[200, 120, 250, 150]])

    def test_original_image_containing_protected_text_fails(self) -> None:
        with self.assertRaisesRegex(LayoutAdjustmentError, "original image"):
            validate_layout_adjustment(valid(), 600, 800, [[110, 110, 140, 140]])


if __name__ == "__main__": unittest.main()
