import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile
from PIL import Image
from docx import Document

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import word_image_replacements as images


class RasterReplacementTests(unittest.TestCase):
    def test_inline_raster_uses_media_identity_not_word_collection_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            doc = Document()
            for i, color in enumerate(('red', 'green', 'blue', 'yellow'), 1):
                image = root / f'{i}.png'
                Image.new('RGB', (40, 20), color).save(image)
                doc.add_picture(str(image))
            output = root / 'test.docx'
            doc.save(output)
            replacement = root / 'zh.png'
            Image.new('RGB', (40, 20), 'black').save(replacement)
            with ZipFile(output) as archive:
                before = {name: archive.read(name) for name in archive.namelist()}
            digest = hashlib.sha256(replacement.read_bytes()).hexdigest()
            manifest = {'image_reviews': [{'id': 'img4', 'status': 'localized',
                'replacement_path': str(replacement), 'replacement_sha256': digest,
                'media_paths': ['word/media/image4.png']}]}
            with patch.object(images, '_run_word_replacements', side_effect=AssertionError('raster replacement must not depend on Word shape indices')):
                result = images.apply_word_image_replacements(output, manifest)
            self.assertEqual(result['replaced'], 1)
            with ZipFile(output) as archive:
                self.assertEqual(archive.read('word/media/image4.png'), replacement.read_bytes())
                for name, payload in before.items():
                    if name != 'word/media/image4.png':
                        self.assertEqual(archive.read(name), payload, name)
