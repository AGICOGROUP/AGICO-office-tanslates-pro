from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_v6_job import _validate_image_localization_review


def bilingual_review(unmatched: int = 0) -> dict:
    return {
        "complete": True,
        "reviewed_image_ids": ["image-1"],
        "images": [
            {
                "id": "image-1",
                "asset_type": "raster_structured",
                "method": "preserve_bilingual",
                "contains_source_text": True,
                "expected_label_count": 2,
                "translated_label_count": 0,
                "preserved_label_count": 2,
                "confirm_count": 0,
                "bilingual_complete": unmatched == 0,
                "clear_source_label_count": 2,
                "matched_bilingual_pair_count": 2 - unmatched,
                "unmatched_source_label_count": unmatched,
                "original_asset_preserved": True,
                "structural_review_complete": True,
                "labels": [
                    {"id": "zh-1", "source_text": "烟囱", "status": "bilingual_present", "method": "preserve_bilingual"},
                    {"id": "zh-2", "source_text": "除尘器", "status": "bilingual_present", "method": "preserve_bilingual"},
                ],
            }
        ],
        "confirm_items": [],
    }


class BilingualImagePolicyTests(unittest.TestCase):
    def test_complete_bilingual_image_is_preserved_without_vector_metadata(self) -> None:
        _validate_image_localization_review(
            bilingual_review(), {"images": []}, {"image-1"}
        )

    def test_partial_bilingual_image_cannot_skip_translation(self) -> None:
        with self.assertRaisesRegex(ValueError, "incomplete bilingual coverage"):
            _validate_image_localization_review(
                bilingual_review(unmatched=1), {"images": []}, {"image-1"}
            )


if __name__ == "__main__":
    unittest.main()
