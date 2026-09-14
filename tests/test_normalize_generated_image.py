import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from normalize_generated_image import normalize, verify


class NormalizeGeneratedImageTests(unittest.TestCase):
    def test_pads_up_to_exact_source_ratio_without_cropping_or_downsampling(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            generated, output = root/'generated.png', root/'output.png'
            Image.new('RGB', (1536, 1024), 'white').save(generated)
            self.assertEqual(normalize(413, 265, generated, output), (1652, 1060))
            self.assertEqual(verify(413, 265, output), (1652, 1060))

    def test_rejects_lower_resolution_and_wrong_ratio(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'bad.png'
            Image.new('RGB', (412, 265), 'white').save(path)
            with self.assertRaisesRegex(ValueError, 'smaller'):
                verify(413, 265, path)
            Image.new('RGB', (826, 531), 'white').save(path)
            with self.assertRaisesRegex(ValueError, 'aspect ratio'):
                verify(413, 265, path)


if __name__ == '__main__':
    unittest.main()
