"""Saved-package assertions for the two branch-review failures."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZIP_DEFLATED

from openpyxl import Workbook, load_workbook
from openpyxl.workbook.defined_name import DefinedName

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'formats/excel/scripts'), str(ROOT / 'scripts')]
import excel_native_ooxml as native
import excel_bilingual_ooxml as bilingual
from glossary import lookup_terms


def manifest_for(source, targets):
    occurrences = native.inspect(source)['occurrences']
    units = []
    for index, occurrence in enumerate(occurrences):
        source_text = occurrence['source']
        target = targets.get(source_text, source_text)
        unit = {'id': str(index), 'source': source_text, 'translation': target,
                'status': 'retain' if target == source_text else 'translated'}
        if unit['status'] == 'retain':
            unit['reason'] = 'Explicitly retained equipment identifier or existing English label'
        units.append(unit)
        occurrence['translation_unit_id'] = str(index)
    return {'translation_units': units, 'occurrences': occurrences, 'images': []}


class ExcelFidelityRegressionTests(unittest.TestCase):
    def test_chained_sheet_renames_do_not_rename_defined_names_twice(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder)/'source.xlsx', Path(folder)/'output.xlsx'
            book = Workbook()
            book.active.title = 'Alpha'
            book.active['B2'] = 15
            book.create_sheet('Beta')['B2'] = 50
            book.create_sheet('Quote')['A2'] = "='Alpha'!B2+'Beta'!B2"
            book.defined_names.add(DefinedName('InputValue', attr_text="'Alpha'!$B$2"))
            book.save(source)
            manifest = manifest_for(source, {'Alpha':'Beta', 'Beta':'Final'})
            bilingual.apply(source, output, manifest)
            result = load_workbook(output)
            self.assertEqual(result.defined_names['InputValue'].attr_text, "'Beta'!$B$3")
            self.assertEqual(result['Quote']['A3'].value, "='Beta'!B3+'Final'!B3")

    def test_reviewed_cement_terms_use_correct_preferred_meanings(self):
        report = lookup_terms(['安全阀', '火山灰', '热风炉'])
        actual = {item['source']:item['target'] for item in report['matched_entries']}
        self.assertEqual(actual, {'安全阀':'safety valve', '火山灰':'pozzolana',
                                  '热风炉':'hot gas generator'})

    def test_retained_models_are_not_rewritten_as_unit_exponents(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder)/'source.xlsx', Path(folder)/'output.xlsx'
            book = Workbook()
            examples = ['X30m3', 'AB12cm2', '30m3-A', 'MODEL/Nm3',
                        'Storage: 30m3', 'Density: 1.45t/m3',
                        'Area: 3500cm2/g', 'Dust: 20mg/Nm3', 'Flow: 30 m3/h',
                        'RM-30m3', 'MODEL/30m3', 'Range: 30-40m3/h']
            for row, value in enumerate(examples, 1):
                book.active.cell(row, 1, value)
            book.save(source)
            manifest = manifest_for(source, {})
            native.apply(source, output, manifest)
            actual = load_workbook(output).active
            wanted = ['X30m3', 'AB12cm2', '30m3-A', 'MODEL/Nm3',
                      'Storage: 30m³', 'Density: 1.45t/m³',
                      'Area: 3500cm²/g', 'Dust: 20mg/Nm³', 'Flow: 30 m³/h',
                      'RM-30m3', 'MODEL/30m3', 'Range: 30-40m³/h']
            self.assertEqual([actual.cell(row, 1).value for row in range(1, len(wanted)+1)], wanted)
            self.assertTrue(native.verify(source, output, manifest)['passed'])

    def test_bilingual_formula_renames_and_row_mapping_are_both_applied(self):
        for old, new, expected in [
            ('旧表', 'Equipment List', "'Equipment List'!B3*2"),
            ("旧'表", "Plant's Data", "'Plant''s Data'!B3*2"),
        ]:
            with self.subTest(sheet=old), tempfile.TemporaryDirectory() as folder:
                source, output = Path(folder)/'source.xlsx', Path(folder)/'output.xlsx'
                book = Workbook()
                sheet = book.active
                sheet.title = old
                sheet['A1'], sheet['B2'] = '设备', 15
                reference = "'" + old.replace("'", "''") + "'!"
                book.create_sheet('Quote')['A2'] = '=' + reference + 'B2*2'
                book.defined_names.add(DefinedName('InputValue', attr_text=reference+'$B$2'))
                book.save(source)
                manifest = manifest_for(source, {old:new, '设备':'Equipment'})
                bilingual.apply(source, output, manifest)
                result = load_workbook(output)
                self.assertEqual(result.sheetnames, [new, 'Quote'])
                self.assertEqual(result['Quote']['A3'].value, '=' + expected)
                self.assertEqual(result[new]['B3'].value, 15)
                self.assertEqual(result.defined_names['InputValue'].attr_text,
                                 "'" + new.replace("'", "''") + "'!$B$3")
                self.assertTrue(bilingual.verify(source, output, manifest)['passed'])
                # Even if the package-builder's expectation repeats a writer bug,
                # saved formulas must be checked against the original references.
                with ZipFile(output) as archive:
                    damaged = {name:archive.read(name) for name in archive.namelist()}
                tree = native.xml(damaged['xl/worksheets/sheet2.xml'])
                tree.find('.//' + native.Q('f')).text = reference + 'B3*2'
                damaged['xl/worksheets/sheet2.xml'] = native.serialize(tree)
                corrupt = Path(folder)/'corrupt.xlsx'
                with ZipFile(corrupt, 'w', ZIP_DEFLATED) as archive:
                    for name, data in damaged.items():
                        archive.writestr(name, data)
                with patch.object(bilingual, 'build', return_value=(damaged, {})):
                    report = bilingual.verify(source, corrupt, manifest)
                self.assertFalse(report['passed'], 'a repeated writer expectation must not hide stale sheet references')


if __name__ == '__main__':
    unittest.main()
