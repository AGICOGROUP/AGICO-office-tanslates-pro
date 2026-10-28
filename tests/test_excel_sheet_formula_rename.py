from pathlib import Path
import sys,tempfile,unittest
from zipfile import ZipFile,ZIP_DEFLATED
from lxml import etree as E
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'formats/excel/scripts'),str(ROOT/'scripts')]
import excel_native_ooxml as n

class FormulaSheetRenameTests(unittest.TestCase):
    def test_metric_exponents_change_only_quantity_units_not_model_codes(self):
        self.assertEqual('30m³ 3500cm²/g 20mg/Nm³ ModelM3 m300',
                         n.metric_exponents('30m3 3500cm2/g 20mg/Nm3 ModelM3 m300'))

    def test_changes_only_local_sheet_qualifiers_not_strings_or_external_books(self):
        source='SUM(\'旧表\'!A1:B2,旧表!C3,"旧表!A1",\'[Book.xlsx]旧表\'!D4)'
        want='SUM(\'Equipment List\'!A1:B2,\'Equipment List\'!C3,"旧表!A1",\'[Book.xlsx]旧表\'!D4)'
        self.assertEqual(want,n.rename_formula_references(source,{'旧表':'Equipment List'}))

    def test_handles_escaped_apostrophes_and_preserves_other_formula_text(self):
        self.assertEqual("'New''Name'!$A$1+Other!B2",n.rename_formula_references("'Old''Name'!$A$1+Other!B2",{"Old'Name":"New'Name"}))

    def test_writer_and_verifier_keep_formula_values_attributes_and_cells(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'source.xlsx';out=Path(d)/'out.xlsx';ns=n.NS
            parts={'[Content_Types].xml':'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
                'xl/workbook.xml':f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="旧表" sheetId="1" r:id="rId1"/><sheet name="Quote" sheetId="2" r:id="rId2"/></sheets><definedNames><definedName name="Budget">\'旧表\'!$A$1</definedName></definedNames></workbook>',
                'xl/_rels/workbook.xml.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Target="worksheets/sheet2.xml"/></Relationships>',
                'xl/worksheets/sheet1.xml':f'<worksheet xmlns="{ns}"><sheetData><row r="1"><c r="A1"><v>15</v></c></row></sheetData></worksheet>',
                'xl/worksheets/sheet2.xml':f'<worksheet xmlns="{ns}"><sheetData><row r="1"><c r="A1"><f>\'旧表\'!A1*2</f><v>30</v></c></row></sheetData></worksheet>'}
            with ZipFile(source,'w',ZIP_DEFLATED) as z:
                for k,v in parts.items():z.writestr(k,v.encode())
            manifest={'translation_units':[{'id':'name','source':'旧表','translation':'Equipment List','status':'translated'}],
                'occurrences':[{'kind':'sheet_name','sheet':'旧表','address':'@sheet','source':'旧表','translation_unit_id':'name'}], 'images':[]}
            n.apply(source,out,manifest)
            self.assertTrue(n.verify(source,out,manifest)['passed'])
            p=n.Package(out);cell=p.cells[('Quote','A1')]
            self.assertEqual("'Equipment List'!A1*2",cell.find(n.Q('f')).text)
            self.assertEqual('30',cell.find(n.Q('v')).text)
            self.assertEqual("'Equipment List'!$A$1",p.workbook.find(n.Q('definedNames'))[0].text)

if __name__=='__main__':unittest.main()
