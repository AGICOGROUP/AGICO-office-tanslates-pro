from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET


SKILL_ROOT = Path(__file__).parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "pptx_ooxml.py"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


SLIDE_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree>
    <p:sp>
      <p:nvSpPr><p:cNvPr id="2" name="TextBox 1"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
      <p:spPr><a:solidFill><a:srgbClr val="112233"/></a:solidFill></p:spPr>
      <p:txBody><a:bodyPr/><a:lstStyle/><a:p>
        <a:r><a:rPr lang="zh-CN" sz="2400" b="1"/><a:t>梁式</a:t></a:r>
        <a:r><a:rPr lang="zh-CN" sz="2400"/><a:t>窑</a:t></a:r>
      </a:p></p:txBody>
    </p:sp>
  </p:spTree></p:cSld>
</p:sld>
""".encode("utf-8")


class OoxmlApplyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.source = self.root / "source.pptx"
        self.output = self.root / "output.pptx"
        self.manifest = self.root / "manifest.json"
        self.relationships = b"<Relationships>unchanged</Relationships>"
        self.media = b"\x89PNG\r\nfixture"

        with zipfile.ZipFile(self.source, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
            archive.writestr("ppt/slides/slide1.xml", SLIDE_XML)
            archive.writestr("ppt/slides/slide2.xml", SLIDE_XML)
            archive.writestr("ppt/slides/_rels/slide1.xml.rels", self.relationships)
            archive.writestr("ppt/slides/_rels/slide2.xml.rels", self.relationships)
            archive.writestr("ppt/media/image1.png", self.media)

        self.manifest.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "source_file": "source.pptx",
                    "source_path": str(self.source),
                    "source_sha256": "a" * 64,
                    "source_language": "zh-CN",
                    "target_language": "en",
                    "format": "powerpoint",
                    "occurrences": [
                        {
                            "id": "slide:1/shape:2/paragraph:1",
                            "slide_index": 1,
                            "shape_id": 2,
                            "paragraph_index": 1,
                            "kind": "ppt_paragraph",
                            "source_text": "梁式窑",
                            "translation_unit_id": "tu-beam",
                            "role": "body",
                            "context_signature": "body",
                            "protected_tokens": [],
                        },
                        {
                            "id": "slide:2/shape:2/paragraph:1",
                            "slide_index": 2,
                            "shape_id": 2,
                            "paragraph_index": 1,
                            "kind": "ppt_paragraph",
                            "source_text": "梁式窑",
                            "translation_unit_id": "tu-beam",
                            "role": "body",
                            "context_signature": "body",
                            "protected_tokens": [],
                        }
                    ],
                    "translation_units": [
                        {
                            "id": "tu-beam",
                            "source_text": "梁式窑",
                            "translation": "Beam Lime Kiln",
                            "role": "body",
                            "context_signature": "body",
                            "protected_tokens": [],
                        }
                    ],
                    "image_groups": [],
                    "risk_plan": {"route": "fast", "complex_reasons": [], "strict_reasons": []},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_apply_changes_text_only_and_preserves_package_entries(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "apply",
                "--input",
                str(self.source),
                "--manifest",
                str(self.manifest),
                "--output",
                str(self.output),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            {"occurrences": 2, "translation_units": 1, "replaced": 2},
            json.loads(result.stdout),
        )

        with zipfile.ZipFile(self.source) as before, zipfile.ZipFile(self.output) as after:
            self.assertEqual(before.namelist(), after.namelist())
            self.assertEqual(
                after.read("ppt/slides/_rels/slide1.xml.rels"), self.relationships
            )
            self.assertEqual(after.read("ppt/media/image1.png"), self.media)
            xml = after.read("ppt/slides/slide1.xml")
            xml2 = after.read("ppt/slides/slide2.xml")
            original_xml = before.read("ppt/slides/slide1.xml")

        mask = lambda payload: re.sub(
            rb"(<a:t(?:\s[^>]*)?>).*?(</a:t>)", rb"\1__TEXT__\2", payload
        )
        self.assertEqual(
            mask(xml),
            mask(original_xml),
            "OOXML mutation must leave every byte outside <a:t> text unchanged",
        )
        self.assertEqual(mask(xml2), mask(original_xml))

        root = ET.fromstring(xml)
        text_nodes = root.findall(f".//{{{A_NS}}}t")
        self.assertEqual("".join(node.text or "" for node in text_nodes), "Beam Lime Kiln")
        second_root = ET.fromstring(xml2)
        self.assertEqual(
            "".join(node.text or "" for node in second_root.findall(f".//{{{A_NS}}}t")),
            "Beam Lime Kiln",
        )
        self.assertEqual(
            root.find(f".//{{{A_NS}}}rPr").attrib,
            {"lang": "zh-CN", "sz": "2400", "b": "1"},
        )
        self.assertEqual(
            root.find(f".//{{{A_NS}}}solidFill/{{{A_NS}}}srgbClr").attrib["val"],
            "112233",
        )

    def test_apply_removes_negative_character_spacing_and_preserves_boundary_spaces(self):
        with zipfile.ZipFile(self.source, "r") as archive:
            entries = [(item, archive.read(item.filename)) for item in archive.infolist()]
        with zipfile.ZipFile(self.source, "w", zipfile.ZIP_DEFLATED) as archive:
            for item, payload in entries:
                if item.filename.startswith("ppt/slides/slide"):
                    payload = payload.replace(b'lang="zh-CN" sz="2400" b="1"', b'lang="zh-CN" sz="2400" b="1" spc="-800"')
                archive.writestr(item, payload)
        manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
        manifest["translation_units"][0]["translation"] = " Beam Lime Kiln "
        self.manifest.write_text(json.dumps(manifest), encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(SCRIPT), "apply", "--input", str(self.source), "--manifest", str(self.manifest), "--output", str(self.output)],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        with zipfile.ZipFile(self.output) as archive:
            root = ET.fromstring(archive.read("ppt/slides/slide1.xml"))
        first_run = root.find(f".//{{{A_NS}}}r")
        first_text = first_run.find(f"{{{A_NS}}}t")
        self.assertNotIn("spc", first_run.find(f"{{{A_NS}}}rPr").attrib)
        self.assertEqual(first_text.attrib["{http://www.w3.org/XML/1998/namespace}space"], "preserve")
        self.assertEqual(first_text.text, " Beam Lime Kiln ")


if __name__ == "__main__":
    unittest.main()
