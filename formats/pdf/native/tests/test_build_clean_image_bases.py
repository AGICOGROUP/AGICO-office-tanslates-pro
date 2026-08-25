import importlib.util
from pathlib import Path
import unittest

import numpy as np


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "build_clean_image_bases.py"
)
SPEC = importlib.util.spec_from_file_location("build_clean_image_bases", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class UiGlyphCleanupTests(unittest.TestCase):
    def test_removes_dark_text_without_damaging_colored_background_or_line(self):
        image = np.full((40, 120, 3), [245, 148, 35], dtype=np.uint8)
        image[20, :] = [25, 75, 145]  # UI divider that must remain sharp.
        image[8:16, 35:39] = [15, 15, 15]
        image[8:16, 42:46] = [15, 15, 15]
        image[8:12, 35:46] = [15, 15, 15]
        original_line = image[20].copy()

        changed = MODULE.clean_region(
            image,
            {
                "box": [25, 3, 60, 20],
                "clean_box": [25, 3, 60, 20],
                "mode": "ui_glyph",
            },
        )

        self.assertGreater(changed, 0)
        self.assertTrue(np.all(image[8:16, 35:46] == [245, 148, 35]))
        self.assertTrue(np.array_equal(image[20], original_line))

    def test_removes_light_text_from_dark_ui_bar(self):
        image = np.full((30, 90, 3), [35, 80, 125], dtype=np.uint8)
        image[9:18, 30:34] = [245, 245, 245]
        image[9:18, 38:42] = [245, 245, 245]
        image[14:18, 30:42] = [245, 245, 245]

        MODULE.clean_region(
            image,
            {
                "box": [22, 4, 52, 23],
                "mode": "ui_glyph",
            },
        )

        self.assertTrue(np.all(image[9:18, 30:42] == [35, 80, 125]))

    def test_uses_border_fill_when_tight_glyph_box_is_mostly_text(self):
        image = np.full((18, 22, 3), [232, 232, 228], dtype=np.uint8)
        image[4:14, 7:15] = [22, 22, 22]

        MODULE.clean_region(
            image,
            {
                "box": [6, 3, 16, 15],
                "mode": "ui_glyph",
            },
        )

        self.assertTrue(np.all(image[4:14, 7:15] == [232, 232, 228]))


class UiTextPatchTests(unittest.TestCase):
    def test_reconstructs_gradient_rows_and_preserves_horizontal_divider(self):
        image = np.zeros((24, 60, 3), dtype=np.uint8)
        for y in range(image.shape[0]):
            for x in range(image.shape[1]):
                image[y, x] = [120 + x, 150 + y, 180]
        image[12, :] = [15, 70, 145]
        clean_baseline = image.copy()
        image[6:11, 22:38] = [10, 10, 10]
        image[13:18, 22:38] = [245, 245, 245]
        original_outside = image.copy()

        MODULE.clean_region(
            image,
            {
                "box": [20, 4, 40, 20],
                "clean_box": [20, 4, 40, 20],
                "mode": "ui_text_patch",
            },
        )

        self.assertTrue(np.array_equal(image[12, 20:40], clean_baseline[12, 20:40]))
        self.assertTrue(np.all(np.abs(
            image[6:11, 22:38].astype(int)
            - clean_baseline[6:11, 22:38].astype(int)
        ) <= 1))
        mask = np.ones(image.shape[:2], dtype=bool)
        mask[4:20, 20:40] = False
        self.assertTrue(np.array_equal(image[mask], original_outside[mask]))


class CaptionBandCleanupTests(unittest.TestCase):
    def test_solid_fill_replaces_only_approved_photo_caption_band(self):
        image = np.full((30, 60, 3), [80, 120, 160], dtype=np.uint8)
        image[18:27, 5:55] = [245, 245, 245]
        outside = image.copy()

        changed = MODULE.clean_region(
            image,
            {
                "box": [3, 16, 57, 29],
                "mode": "solid_fill",
                "fill_rgb": [14, 24, 40],
            },
        )

        self.assertGreater(changed, 0)
        self.assertTrue(np.all(image[16:29, 3:57] == [14, 24, 40]))
        mask = np.ones(image.shape[:2], dtype=bool)
        mask[16:29, 3:57] = False
        self.assertTrue(np.array_equal(image[mask], outside[mask]))


class AnchoredLineRestoreTests(unittest.TestCase):
    def test_reconnects_horizontal_line_between_opposite_anchors(self):
        image = np.full((24, 30, 3), 255, dtype=np.uint8)
        image[12, :] = [18, 18, 18]
        image[8:16, 10:14] = [35, 35, 35]
        outside = image.copy()

        MODULE.clean_region(
            image,
            {
                "box": [7, 6, 18, 18],
                "clean_box": [7, 6, 18, 18],
                "mode": "anchored_line_restore",
                "line_anchors": [
                    {"start": [7, 12], "end": [17, 12], "width": 1}
                ],
            },
        )

        self.assertTrue(np.all(image[12, 7:18] == [18, 18, 18]))
        mask = np.ones(image.shape[:2], dtype=bool)
        mask[6:18, 7:18] = False
        self.assertTrue(np.array_equal(image[mask], outside[mask]))

    def test_reconnects_diagonal_line_between_opposite_edges(self):
        image = np.full((24, 24, 3), 255, dtype=np.uint8)
        for value in range(24):
            image[value, value] = [25, 25, 25]
        image[9:14, 9:14] = [45, 45, 45]

        MODULE.clean_region(
            image,
            {
                "box": [6, 6, 18, 18],
                "mode": "anchored_line_restore",
                "line_anchors": [
                    {"start": [6, 6], "end": [17, 17], "width": 1}
                ],
            },
        )

        self.assertTrue(
            all(np.array_equal(image[value, value], [25, 25, 25]) for value in range(6, 18))
        )

    def test_rejects_anchors_that_do_not_touch_opposite_edges(self):
        image = np.full((20, 20, 3), 255, dtype=np.uint8)

        with self.assertRaisesRegex(ValueError, "opposite cleanup-box edges"):
            MODULE.clean_region(
                image,
                {
                    "box": [5, 5, 15, 15],
                    "mode": "anchored_line_restore",
                    "line_anchors": [
                        {"start": [5, 7], "end": [5, 12], "width": 1}
                    ],
                },
            )
