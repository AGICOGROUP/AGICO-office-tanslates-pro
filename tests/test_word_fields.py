"""Dynamic Word fields remain immutable while surrounding prose is translated."""
import sys
import unittest
from pathlib import Path
from lxml import etree
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "formats/word/scripts"))
from word_pipeline import paragraph_text, replace_paragraph_text
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

class WordFieldTests(unittest.TestCase):
    def test_complex_field_cache_survives_translation(self):
        p = etree.fromstring((
            '<w:p xmlns:w="' + W[1:-1] + '"><w:r><w:t>Page </w:t></w:r>'
            '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            '<w:r><w:instrText> PAGE </w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
            '<w:r><w:t>1</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r>'
            '<w:r><w:t> total</w:t></w:r></w:p>').encode())
        source = paragraph_text(p)
        self.assertEqual(source, "Page {{FIELD1}} total")
        replace_paragraph_text(p, source, "页码 {{FIELD1}} 合计")
        self.assertEqual(paragraph_text(p), "页码 {{FIELD1}} 合计")
        self.assertEqual(p.find(".//" + W + "instrText").text, " PAGE ")
        self.assertIn("1", [n.text for n in p.iter(W + "t")])

    def test_simple_field_preserves_instruction_and_result(self):
        p = etree.fromstring((
            '<w:p xmlns:w="' + W[1:-1] + '"><w:r><w:t>Date </w:t></w:r>'
            '<w:fldSimple w:instr="DATE"><w:r><w:t>08 November 2026</w:t></w:r>'
            '</w:fldSimple></w:p>').encode())
        field = p.find(W + "fldSimple")
        before = etree.tostring(field)
        replace_paragraph_text(p, paragraph_text(p), "日期 {{FIELD1}}")
        self.assertEqual(etree.tostring(field), before)

    def test_removed_field_is_rejected(self):
        p = etree.fromstring((
            '<w:p xmlns:w="' + W[1:-1] + '"><w:r><w:t>Page </w:t></w:r>'
            '<w:fldSimple w:instr="PAGE"><w:r><w:t>1</w:t></w:r>'
            '</w:fldSimple></w:p>').encode())
        with self.assertRaises(ValueError):
            replace_paragraph_text(p, paragraph_text(p), "页码 1")

if __name__ == "__main__":
    unittest.main()
