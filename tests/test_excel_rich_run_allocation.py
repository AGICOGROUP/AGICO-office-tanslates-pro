from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree as E

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'formats/excel/scripts'),str(ROOT/'scripts')]
import excel_native_ooxml as native


class RichRunAllocationTests(unittest.TestCase):
    def test_unit_superscript_run_stays_on_its_exponent_after_long_translation(self):
        for source_prefix, exponent, suffix, target, expected in (
            ('储容：30m', '3', '', 'Storage capacity: 30m³', '³'),
            ('面积：96m', '2', '；工作压力：4kPa', 'Filtration area: 96m²; working pressure: 4kPa', '²'),
        ):
            with self.subTest(target=target):
                rich = E.fromstring((f'<si xmlns="{native.NS}"><r><t>{source_prefix}</t></r>'
                    f'<r><rPr><vertAlign val="superscript"/></rPr><t>{exponent}</t></r>'
                    + (f'<r><t>{suffix}</t></r>' if suffix else '') + '</si>').encode())
                class Source:
                    def rich(self, cell): return rich
                cell = E.fromstring(f'<c xmlns="{native.NS}"/>'.encode())
                native.replace_text(Source(), cell, target)
                runs = cell.find(native.Q('is')).findall(native.Q('r'))
                self.assertEqual(runs[1].find(native.Q('t')).text, expected)
                self.assertEqual(''.join(r.find(native.Q('t')).text or '' for r in runs), target)

    def test_shorter_translation_does_not_create_empty_rich_runs(self):
        # Four real formatting runs, including short Chinese/space runs before English.
        rich=E.fromstring(('<si xmlns="'+native.NS+'">'
            '<r><rPr><b/></rPr><t>编</t></r>'
            '<r><rPr><i/></rPr><t> </t></r>'
            '<r><rPr><u/></rPr><t>制</t></r>'
            '<r><rPr><sz val="11"/></rPr><t>Designed   by</t></r></si>').encode())
        class Source:
            def rich(self,cell):return rich
        for target in ('Designed by','Unit'):
            with self.subTest(target=target):
                cell=E.fromstring(('<c xmlns="'+native.NS+'" t="s"><v>0</v></c>').encode())
                native.replace_text(Source(),cell,target)
                runs=cell.find(native.Q('is')).findall(native.Q('r'))
                self.assertEqual(4,len(runs))
                self.assertEqual(target,''.join(r.find(native.Q('t')).text or '' for r in runs))
                self.assertTrue(all(r.find(native.Q('t')).text for r in runs))
                self.assertEqual([E.tostring(r.find(native.Q('rPr'))) for r in rich],
                                 [E.tostring(r.find(native.Q('rPr'))) for r in runs])


if __name__=='__main__':unittest.main()
