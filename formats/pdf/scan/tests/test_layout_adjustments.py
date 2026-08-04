from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from layout_adjustments import LayoutAdjustmentError, validate_layout_adjustment


BASE = {"page": 1, "source_box": [100, 100, 300, 200], "original_box": [100, 100, 300, 200], "target_box": [160, 110, 320, 190], "scale": 0.8, "trigger": "text_does_not_fit", "fit_failure": True, "approved_background_regions": [[100, 100, 300, 200]]}


class LayoutAdjustmentTests(unittest.TestCase):
    def test_valid_scan_layout_adjustment_passes(self) -> None:
        validate_layout_adjustment(dict(BASE), 600, 800, [])

    def test_page_escape_fails(self) -> None:
        item = dict(BASE); item["target_box"] = [500, 110, 660, 190]
        with self.assertRaises(LayoutAdjustmentError): validate_layout_adjustment(item, 600, 800, [])

    def test_different_source_crop_fails(self) -> None:
        item = dict(BASE); item["source_box"] = [110, 100, 310, 200]
        with self.assertRaisesRegex(LayoutAdjustmentError, "source_box"):
            validate_layout_adjustment(item, 600, 800, [])

    def test_original_image_containing_protected_text_fails(self) -> None:
        with self.assertRaisesRegex(LayoutAdjustmentError, "original image"):
            validate_layout_adjustment(dict(BASE), 600, 800, [[110, 110, 140, 140]])


if __name__ == "__main__": unittest.main()
