import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from translation_quality import technical_mismatch


class NumeroReferenceTests(unittest.TestCase):
    def test_numero_sign_is_a_document_number_not_an_alphanumeric_model(self):
        for source, target in (
            ('Приложение №7 к ТЗ E.E5300028', 'Annex No. 7 to Technical Requirements E.E5300028'),
            ('По форме Приложения №7', 'Using the Annex No. 7 template'),
        ):
            with self.subTest(source=source):
                self.assertFalse(technical_mismatch(source, target))

    def test_changed_reference_number_and_genuine_model_still_fail(self):
        self.assertTrue(technical_mismatch('Приложение №7', 'Annex No. 8'))
        self.assertTrue(technical_mismatch('Model No7', 'Model No. 7'))


if __name__ == '__main__':
    unittest.main()
