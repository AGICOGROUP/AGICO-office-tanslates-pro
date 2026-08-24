from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pymupdf


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "bilingual_overlay.py"
FONT = Path(r"C:\Windows\Fonts\simhei.ttf")


@unittest.skipUnless(FONT.is_file(), "SimHei is required for the CJK overlay test")
class BilingualOverlayOutputTests(unittest.TestCase):
    def test_preserves_source_geometry_and_extractable_unicode(self) -> None:
        chinese_text = chr(0x4F60) + chr(0x597D)
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "source.pdf"
            translations = temp / "translations.json"
            output = temp / "output.pdf"

            source_doc = pymupdf.open()
            source_page = source_doc.new_page(width=320, height=240)
            source_page.insert_text((36, 48), "Hello")
            source_doc.save(source)
            source_doc.close()

            translations.write_text(
                json.dumps(
                    [{"page": 0, "translation": chinese_text, "x": 36, "y": 72}],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(source),
                    "--translations",
                    str(translations),
                    "--output",
                    str(output),
                    "--font-file",
                    str(FONT),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            source_doc = pymupdf.open(source)
            output_doc = pymupdf.open(output)
            self.assertEqual(output_doc.page_count, source_doc.page_count)
            self.assertEqual(output_doc[0].rect, source_doc[0].rect)
            extracted = output_doc[0].get_text()
            self.assertIn("Hello", extracted)
            self.assertIn(chinese_text, extracted)
            output_doc.close()
            source_doc.close()


if __name__ == "__main__":
    unittest.main()
