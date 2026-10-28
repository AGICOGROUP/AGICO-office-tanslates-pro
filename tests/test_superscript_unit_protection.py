import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from translation_quality import technical_mismatch


class SuperscriptUnitProtectionTests(unittest.TestCase):
    def test_translated_area_label_keeps_legacy_partial_token_valid(self):
        self.assertFalse(technical_mismatch('总过滤面积：96m²', 'Total filtration area：96m²', ['96m']))

    def test_translated_volume_label_keeps_legacy_partial_token_valid(self):
        self.assertFalse(technical_mismatch('储容：2m³', 'Storage capacity：2m³', ['2m']))

    def test_area_value_and_exponent_are_still_protected(self):
        for target in ('Total filtration area：95m²', 'Total filtration area：96m³', 'Total filtration area：96m'):
            with self.subTest(target=target):
                self.assertTrue(technical_mismatch('总过滤面积：96m²', target, ['96m']))

    def test_length_and_area_with_same_value_must_both_remain(self):
        source = '长度：96m；面积：96m²'
        self.assertTrue(technical_mismatch(source, 'Area：96m²', ['96m']))
        self.assertFalse(technical_mismatch(source, 'Length：96m; area：96m²', ['96m']))

    def test_model_suffix_is_not_a_superscript_unit(self):
        self.assertTrue(technical_mismatch('型号：X96m²', 'Model：Y96m²', ['X96m']))


if __name__ == '__main__':
    unittest.main()
