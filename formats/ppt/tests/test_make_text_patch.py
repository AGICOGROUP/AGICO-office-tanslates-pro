from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from PIL import Image

import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from make_text_patch import make_patch  # noqa: E402


class MakeTextPatchTests(unittest.TestCase):
    def test_solid_patch_is_tight_and_lossless(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            output = root / "patch.png"
            Image.new("RGB", (100, 80), (240, 240, 235)).save(source)

            make_patch(
                source,
                output,
                (20, 30, 17, 9),
                "solid",
                fill_rgb=(246, 246, 241),
                verified_solid=True,
            )

            with Image.open(output) as patch:
                self.assertEqual(patch.size, (17, 9))
                self.assertEqual(patch.getpixel((0, 0)), (246, 246, 241))

    def test_solid_patch_requires_visual_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            Image.new("RGB", (20, 20), "white").save(source)
            with self.assertRaisesRegex(ValueError, "verified_solid"):
                make_patch(source, root / "patch.png", (1, 1, 5, 5), "solid", (255, 255, 255))

    def test_supplied_patch_must_match_source_region(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            repair = root / "repair.png"
            Image.new("RGB", (20, 20), "white").save(source)
            Image.new("RGB", (4, 4), "white").save(repair)
            with self.assertRaisesRegex(ValueError, "dimensions"):
                make_patch(
                    source,
                    root / "patch.png",
                    (1, 1, 5, 5),
                    "supplied",
                    supplied_patch=repair,
                )


if __name__ == "__main__":
    unittest.main()
