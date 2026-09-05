from __future__ import annotations

import json
import re
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "formats" / "word" / "scripts" / "word_pipeline.py"
WORD_COM = ROOT / "formats" / "word" / "scripts" / "word_com.ps1"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


class WordPipelineContractTests(unittest.TestCase):
    def test_prepare_emits_compact_batches_and_merge_preserves_pipeline_output(self):
        pipeline = self.load_pipeline()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_docx(root, '<w:p><w:r><w:t>功率75kW</w:t></w:r></w:p>')
            manifest = pipeline.prepare(source, root / 'job', 'en')
            index = json.loads((root / 'job' / 'translation-worklist.json').read_text(encoding='utf-8'))
            response = root / 'response.json'
            response.write_text(json.dumps({'job_id': index['job_id'], 'translations': [
                {'id': 1, 'translation': 'Power 75 kW'}]}), encoding='utf-8')
            args = type('Args', (), {'command': 'merge', 'job_dir': root / 'job', 'responses': response})()
            self.assertEqual(pipeline.run_translation_command(args), 0)
            output = root / 'translated.docx'
            pipeline.apply(manifest, output)
            pipeline.validate(output, manifest)

    def load_pipeline(self):
        spec = importlib.util.spec_from_file_location("word_pipeline_test_module", PIPELINE)
        module = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(PIPELINE.parent))
        try:
            spec.loader.exec_module(module)
        finally:
            sys.path.pop(0)
        return module

    def make_docx(self, root: Path, body: str | None = None, content_types: str = "<Types/>") -> Path:
        path = root / "source.docx"
        body = body or '<w:p><w:r><w:t>设备</w:t></w:r></w:p>'
        xml = f'<w:document xmlns:w="{W_NS}" xmlns:custom="urn:keep-me"><w:body>{body}</w:body></w:document>'
        with ZipFile(path, "w") as archive:
            archive.writestr("[Content_Types].xml", content_types)
            archive.writestr("word/document.xml", xml)
            archive.writestr("word/media/image1.png", b"keep")
        return path

    def test_rejects_macro_enabled_word_input(self):
        pipeline = self.load_pipeline()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.docm"
            source.write_bytes(b"macro-enabled-placeholder")
            with self.assertRaisesRegex(ValueError, "only .doc and .docx"):
                pipeline.prepare(source, Path(directory) / "job", "English")

    def test_rejects_macro_package_renamed_to_docx(self):
        pipeline = self.load_pipeline()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_docx(root)
            with ZipFile(source, "a") as archive:
                archive.writestr("word/vbaProject.bin", b"macro")

            with self.assertRaisesRegex(ValueError, "macro-enabled Word package"):
                pipeline.prepare(source, root / "job", "English")

    def test_rejects_macro_content_type_renamed_to_docx(self):
        pipeline = self.load_pipeline()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_docx(
                root,
                content_types='<Types><Override ContentType="application/vnd.ms-word.document.macroEnabled.main+xml"/></Types>',
            )

            with self.assertRaisesRegex(ValueError, "macro-enabled Word package"):
                pipeline.prepare(source, root / "job", "English")

    def test_prepare_rejects_chart_text_instead_of_silently_omitting_it(self):
        pipeline = self.load_pipeline()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "chart.docx"
            document = f'<w:document xmlns:w="{W_NS}"><w:body><w:p><w:r><w:t>Body</w:t></w:r></w:p></w:body></w:document>'
            chart = '<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart"><c:v>Sales</c:v></c:chartSpace>'
            with ZipFile(source, "w") as archive:
                archive.writestr("[Content_Types].xml", "<Types/>")
                archive.writestr("word/document.xml", document)
                archive.writestr("word/charts/chart1.xml", chart)

            with self.assertRaisesRegex(ValueError, "unsupported editable chart text"):
                pipeline.prepare(source, root / "job", "English")

    def test_com_forces_macro_disable_before_open(self):
        script = WORD_COM.read_text(encoding="utf-8-sig")
        self.assertIn("AutomationSecurity = 3", script)
        self.assertLess(script.index("AutomationSecurity = 3"), script.index("Documents.Open"))

    def test_prepare_creates_complete_translation_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_docx(root)
            job = root / "job"
            result = subprocess.run(
                [sys.executable, str(PIPELINE), "prepare", str(source), "--job-dir", str(job), "--target-language", "English"],
                capture_output=True, text=True, encoding="utf-8"
            )
            self.assertEqual(0, result.returncode, result.stderr)
            manifest = json.loads((job / "translation-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("设备", manifest["units"][0]["source"])
            self.assertEqual("", manifest["units"][0]["target"])

    def test_apply_uses_manifest_and_preserves_package_parts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_docx(root)
            job = root / "job"
            subprocess.run([sys.executable, str(PIPELINE), "prepare", str(source), "--job-dir", str(job), "--target-language", "English"], check=True)
            manifest_path = job / "translation-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["units"][0]["target"] = "Equipment"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            output = root / "translated.docx"
            result = subprocess.run([sys.executable, str(PIPELINE), "apply", str(manifest_path), "--output", str(output)], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(0, result.returncode, result.stderr)
            with ZipFile(output) as archive:
                self.assertEqual(b"keep", archive.read("word/media/image1.png"))
                xml = archive.read("word/document.xml")
            self.assertIn(b"Equipment", xml)
            self.assertIn(b"urn:keep-me", xml)

    def test_apply_covers_paragraphs_with_tabs_and_preserves_the_tab_node(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_docx(
                root,
                '<w:p><w:r><w:t>第一章</w:t><w:tab/><w:t>- 1 -</w:t></w:r></w:p>',
            )
            job = root / "job"
            subprocess.run([sys.executable, str(PIPELINE), "prepare", str(source), "--job-dir", str(job), "--target-language", "English"], check=True)
            manifest_path = job / "translation-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual("第一章\t- 1 -", manifest["units"][0]["source"])
            manifest["units"][0]["target"] = "Chapter 1\t- 1 -"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            output = root / "translated.docx"
            result = subprocess.run([sys.executable, str(PIPELINE), "apply", str(manifest_path), "--output", str(output)], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(0, result.returncode, result.stderr)
            with ZipFile(output) as archive:
                xml = archive.read("word/document.xml")
            self.assertIn(b"Chapter 1", xml)
            self.assertIn(b"<w:tab", xml)
            apply_report = json.loads((job / "apply-report.json").read_text(encoding="utf-8"))
            self.assertEqual(1, apply_report["applied_occurrences"])
            self.assertEqual([], apply_report["unmatched_unit_ids"])

    def test_apply_distributes_translation_across_existing_formatted_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_docx(
                root,
                '<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>设备</w:t></w:r>'
                '<w:r><w:rPr><w:i/></w:rPr><w:t>清单</w:t></w:r></w:p>',
            )
            job = root / "job"
            subprocess.run([sys.executable, str(PIPELINE), "prepare", str(source), "--job-dir", str(job), "--target-language", "English"], check=True)
            manifest_path = job / "translation-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["units"][0]["target"] = "Equipment List"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            output = root / "translated.docx"
            subprocess.run([sys.executable, str(PIPELINE), "apply", str(manifest_path), "--output", str(output)], check=True)
            with ZipFile(output) as archive:
                xml = archive.read("word/document.xml").decode("utf-8")
            self.assertIn("<w:b", xml)
            self.assertIn("<w:i", xml)
            self.assertNotIn("<w:t></w:t>", xml)
            self.assertIn("Equipment", xml)
            self.assertIn(" List", xml)

    def test_apply_does_not_assign_translation_words_to_whitespace_only_runs(self):
        pipeline = self.load_pipeline()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_docx(
                root,
                '<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>二</w:t></w:r>'
                '<w:r><w:rPr><w:b/></w:rPr><w:t>、</w:t></w:r>'
                '<w:r><w:rPr/><w:t xml:space="preserve"> </w:t></w:r>'
                '<w:r><w:rPr><w:b/></w:rPr><w:t>干燥方案参数及计算</w:t></w:r></w:p>',
            )
            job = root / "job"
            manifest_path = pipeline.prepare(source, job, "English")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["units"][0]["target"] = "II. Drying Process Parameters and Calculations"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            output = root / "translated.docx"

            pipeline.apply(manifest_path, output)

            with ZipFile(output) as archive:
                document = pipeline.etree.fromstring(archive.read("word/document.xml"))
            runs = document.xpath("//w:p/w:r", namespaces={"w": W_NS})
            translated_runs = [
                ("".join(run.xpath(".//w:t/text()", namespaces={"w": W_NS})),
                 bool(run.xpath("./w:rPr/w:b", namespaces={"w": W_NS})))
                for run in runs
            ]
            self.assertEqual("II. Drying Process Parameters and Calculations", "".join(text for text, _ in translated_runs))
            self.assertTrue(all(is_bold for text, is_bold in translated_runs if text))

    def test_apply_preserves_visible_spaces_and_removes_cjk_width_compression(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_docx(
                root,
                '<w:p><w:r><w:rPr><w:spacing w:val="-84"/><w:w w:val="70"/>'
                '<w:fitText w:val="900"/></w:rPr><w:t>公司</w:t></w:r>'
                '<w:r><w:rPr><w:spacing w:val="-44"/></w:rPr><w:t>简介</w:t></w:r></w:p>',
            )
            job = root / "job"
            subprocess.run(
                [sys.executable, str(PIPELINE), "prepare", str(source), "--job-dir", str(job), "--target-language", "English"],
                check=True,
            )
            manifest_path = job / "translation-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["units"][0]["target"] = "Company Profile"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            output = root / "translated.docx"

            subprocess.run(
                [sys.executable, str(PIPELINE), "apply", str(manifest_path), "--output", str(output)],
                check=True,
            )

            with ZipFile(output) as archive:
                xml = archive.read("word/document.xml").decode("utf-8")
            self.assertIn('xml:space="preserve"> Profile</w:t>', xml)
            self.assertNotIn("<w:spacing", xml)
            self.assertNotIn("<w:w ", xml)
            self.assertNotIn("<w:fitText", xml)

    def test_static_validation_rejects_invisible_spaces_or_compressed_latin_text(self):
        pipeline = self.load_pipeline()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_docx(root, '<w:p><w:r><w:t>公司简介</w:t></w:r></w:p>')
            job = root / "job"
            manifest_path = pipeline.prepare(source, job, "English")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["units"][0]["target"] = "Company Profile"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            candidate = root / "bad.docx"
            bad_body = (
                '<w:p><w:r><w:rPr><w:spacing w:val="-84"/></w:rPr><w:t>Company</w:t></w:r>'
                '<w:r><w:t> Profile</w:t></w:r></w:p>'
            )
            xml = f'<w:document xmlns:w="{W_NS}"><w:body>{bad_body}</w:body></w:document>'
            with ZipFile(candidate, "w") as archive:
                archive.writestr("[Content_Types].xml", "<Types/>")
                archive.writestr("word/document.xml", xml)
                archive.writestr("word/media/image1.png", b"keep")

            with self.assertRaisesRegex(ValueError, "unsafe translated text layout"):
                pipeline.validate(candidate, manifest_path)

    def test_failed_apply_does_not_overwrite_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_docx(root, '<w:p><w:r><w:t>章节</w:t><w:tab/><w:t>1</w:t></w:r></w:p>')
            job = root / "job"
            subprocess.run([sys.executable, str(PIPELINE), "prepare", str(source), "--job-dir", str(job), "--target-language", "English"], check=True)
            manifest_path = job / "translation-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["units"][0]["target"] = "Chapter 1"  # Missing the protected tab: apply must fail.
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            output = root / "translated.docx"
            output.write_bytes(b"existing-valid-output")
            result = subprocess.run([sys.executable, str(PIPELINE), "apply", str(manifest_path), "--output", str(output)], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(2, result.returncode)
            self.assertEqual(b"existing-valid-output", output.read_bytes())

    def test_identity_translation_preserves_run_text_exactly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_docx(
                root,
                '<w:p><w:r><w:t xml:space="preserve"> 设备</w:t></w:r>'
                '<w:r><w:t xml:space="preserve">清单 </w:t></w:r></w:p>',
            )
            job = root / "job"
            subprocess.run([sys.executable, str(PIPELINE), "prepare", str(source), "--job-dir", str(job), "--target-language", "English"], check=True)
            manifest_path = job / "translation-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["units"][0]["target"] = manifest["units"][0]["source"]
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            output = root / "translated.docx"
            subprocess.run([sys.executable, str(PIPELINE), "apply", str(manifest_path), "--output", str(output)], check=True)
            with ZipFile(source) as before, ZipFile(output) as after:
                before_xml = before.read("word/document.xml").decode("utf-8")
                after_xml = after.read("word/document.xml").decode("utf-8")
            self.assertIn("> 设备<", before_xml)
            self.assertIn("> 设备<", after_xml)
            self.assertIn(">清单 <", before_xml)
            self.assertIn(">清单 <", after_xml)

    def test_static_validation_rejects_changed_source_and_missing_targets(self):
        text = PIPELINE.read_text(encoding="utf-8")
        self.assertIn("source file hash changed", text)
        self.assertIn("missing target text", text)
        self.assertIn("protected token mismatch", text)

    def test_prepare_normalizes_adjacent_tab_separators_so_apply_succeeds(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_docx(
                root,
                '<w:p><w:r><w:t>规格</w:t><w:tab/><w:tab/><w:t>E2-1S</w:t></w:r></w:p>',
            )
            job = root / "job"
            result = subprocess.run(
                [sys.executable, str(PIPELINE), "prepare", str(source), "--job-dir", str(job), "--target-language", "English"],
                capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(0, result.returncode, result.stderr)
            manifest_path = job / "translation-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual("规格\t\tE2-1S", manifest["units"][0]["source"])
            manifest["units"][0]["target"] = "Specification\t\tE2-1S"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            output = root / "translated.docx"
            applied = subprocess.run(
                [sys.executable, str(PIPELINE), "apply", str(manifest_path), "--output", str(output)],
                capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(0, applied.returncode, applied.stderr)
            validated = subprocess.run(
                [sys.executable, str(PIPELINE), "validate", str(output), "--manifest", str(manifest_path)],
                capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(0, validated.returncode, validated.stderr)
            with ZipFile(output) as archive:
                xml = archive.read("word/document.xml").decode("utf-8")
            self.assertIn("Specification", xml)

    def test_word_native_check_output_is_decoded_as_utf8(self):
        script = WORD_COM.read_text(encoding="utf-8-sig")
        self.assertIn("OutputEncoding", script)
        pipeline_text = PIPELINE.read_text(encoding="utf-8")
        self.assertIn('encoding="utf-8", errors="replace"', pipeline_text)

    def test_apply_adapts_target_language_layout_devices(self):
        pipeline = self.load_pipeline()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.docx"
            body = (
                '<w:p><w:pPr><w:spacing w:line="360" w:lineRule="exact"/></w:pPr>'
                '<w:r><w:t>设计方案</w:t></w:r></w:p>'
                '<w:p><w:r><w:t>Waste Receiving</w:t></w:r>'
                '<w:r><w:rPr><w:rFonts w:ascii="Wingdings" w:hAnsi="Wingdings" w:eastAsia="Wingdings"/></w:rPr>'
                '<w:t> System</w:t></w:r></w:p>'
                '<w:p><w:r><w:drawing>'
                '<wp:anchor><wp:extent cx="720000" cy="3600000"/>'
                '<wp:positionH relativeFrom="margin"><wp:posOffset>1800000</wp:posOffset></wp:positionH>'
                '<a:graphic><a:graphicData uri="http://schemas.microsoft.com/office/word/2010/wordprocessingShape">'
                '<wps:wsp><wps:spPr><a:xfrm><a:off x="1800000" y="0"/><a:ext cx="720000" cy="3600000"/></a:xfrm></wps:spPr>'
                '<wps:txbx><w:txbxContent><w:p><w:r><w:t>设计方案</w:t></w:r></w:p></w:txbxContent></wps:txbx>'
                '<wps:bodyPr vert="eaVert"/></wps:wsp>'
                '</a:graphicData></a:graphic></wp:anchor>'
                '</w:drawing></w:r></w:p>'
            )
            xml = (
                '<w:document '
                'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
                'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
                'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
                'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape">'
                f'<w:body>{body}</w:body></w:document>'
            )
            with ZipFile(source, "w") as archive:
                archive.writestr("[Content_Types].xml", "<Types/>")
                archive.writestr("word/document.xml", xml)
                archive.writestr(
                    "word/numbering.xml",
                    '<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                    '<w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0">'
                    '<w:lvlText w:val="第%1章"/></w:lvl></w:abstractNum></w:numbering>',
                )
            job = root / "job"
            manifest_path = pipeline.prepare(source, job, "English")
            self.assertIn(
                "第%1章",
                json.loads(manifest_path.read_text(encoding="utf-8")).get("layout", {}).get("cjk_numbering_lvltext", []),
                "prepare should inventory CJK numbering counters",
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for unit in manifest["units"]:
                unit["target"] = "Design Proposal"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            output = root / "translated.docx"
            pipeline.apply(manifest_path, output)

            with ZipFile(output) as archive:
                document = archive.read("word/document.xml").decode("utf-8")
                numbering = archive.read("word/numbering.xml").decode("utf-8")
            # The vertical anchored box is text-container-like, so it is unwrapped
            # into the body flow (removing the anchor, the vert flow and the
            # portrait extents along with it) before the vertical-layout fix
            # would even apply.
            self.assertNotIn("<wp:anchor>", document)
            self.assertNotIn('vert="eaVert"', document)
            self.assertNotIn('cx="720000"', document)
            self.assertNotIn('w:lineRule="exact"', document)
            self.assertNotIn('Wingdings', document)
            self.assertIn("Chapter %1", numbering)
            self.assertNotIn("第", numbering)

    def test_apply_keeps_vertical_layout_for_cjk_targets(self):
        pipeline = self.load_pipeline()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.docx"
            body = (
                '<w:p><w:pPr><w:spacing w:line="360" w:lineRule="exact"/></w:pPr>'
                '<w:r><w:t>项目方案</w:t></w:r></w:p>'
            )
            xml = (
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                f'<w:body>{body}</w:body></w:document>'
            )
            with ZipFile(source, "w") as archive:
                archive.writestr("[Content_Types].xml", "<Types/>")
                archive.writestr("word/document.xml", xml)
            job = root / "job"
            manifest_path = pipeline.prepare(source, job, "zh-CN")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["units"][0]["target"] = "项目方案"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            output = root / "translated.docx"
            pipeline.apply(manifest_path, output)
            with ZipFile(output) as archive:
                document = archive.read("word/document.xml").decode("utf-8")
            self.assertIn('w:lineRule="exact"', document)

    def test_apply_unwraps_anchored_text_boxes_into_body_flow(self):
        pipeline = self.load_pipeline()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.docx"
            body = (
                '<w:p><w:r><w:t>正文内容</w:t></w:r></w:p>'
                '<w:p><w:r><w:drawing>'
                '<wp:anchor><wp:extent cx="3600000" cy="720000"/>'
                '<a:graphic><a:graphicData uri="http://schemas.microsoft.com/office/word/2010/wordprocessingShape">'
                '<wps:wsp><wps:txbx><w:txbxContent>'
                '<w:p><w:r><w:t>设计方案</w:t></w:r></w:p>'
                '</w:txbxContent></wps:txbx><wps:bodyPr/></wps:wsp>'
                '</a:graphicData></a:graphic></wp:anchor>'
                '</w:drawing></w:r></w:p>'
            )
            xml = (
                '<w:document '
                'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
                'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
                'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
                'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape">'
                f'<w:body>{body}</w:body></w:document>'
            )
            with ZipFile(source, "w") as archive:
                archive.writestr("[Content_Types].xml", "<Types/>")
                archive.writestr("word/document.xml", xml)
            job = root / "job"
            manifest_path = pipeline.prepare(source, job, "English")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            targets = {"正文内容": "Body content", "设计方案": "Design Proposal"}
            for unit in manifest["units"]:
                unit["target"] = targets[unit["source"]]
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            output = root / "translated.docx"
            pipeline.apply(manifest_path, output)

            with ZipFile(output) as archive:
                document = archive.read("word/document.xml").decode("utf-8")
            self.assertNotIn("<wp:anchor>", document)
            self.assertNotIn("<w:txbxContent>", document)
            self.assertIn("Body content", document)
            self.assertIn("Design Proposal", document)
            self.assertLess(document.find("Body content"), document.find("Design Proposal"))

    def test_apply_preserves_image_bearing_floating_objects(self):
        pipeline = self.load_pipeline()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.docx"
            body = (
                '<w:p><w:r><w:drawing><wp:anchor>'
                '<a:graphic><a:graphicData><a:blip r:embed="rId5"/>'
                '<wps:wsp><wps:txbx><w:txbxContent>'
                '<w:p><w:r><w:t>图注</w:t></w:r></w:p>'
                '</w:txbxContent></wps:txbx></wps:wsp>'
                '</a:graphicData></a:graphic></wp:anchor></w:drawing></w:r></w:p>'
            )
            xml = (
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
                'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
                'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
                'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape">'
                f'<w:body>{body}</w:body></w:document>'
            )
            rels = (
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                'Target="media/image1.png"/></Relationships>'
            )
            with ZipFile(source, "w") as archive:
                archive.writestr("[Content_Types].xml", "<Types/>")
                archive.writestr("word/document.xml", xml)
                archive.writestr("word/_rels/document.xml.rels", rels)
                archive.writestr("word/media/image1.png", b"keep")
            job = root / "job"
            manifest_path = pipeline.prepare(source, job, "English")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["units"][0]["target"] = "Figure note"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            output = root / "translated.docx"
            pipeline.apply(manifest_path, output)

            with ZipFile(output) as archive:
                document = archive.read("word/document.xml").decode("utf-8")
            self.assertIn('r:embed="rId5"', document)
            self.assertIn("<wp:anchor>", document)
            self.assertEqual(["word/media/image1.png"], pipeline.analyze(output)["referenced_media"])

    def test_validate_rejects_orphaned_media_even_when_media_count_matches(self):
        pipeline = self.load_pipeline()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.docx"
            xml = (
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
                'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<w:body><w:p><w:r><w:t>设备</w:t></w:r><w:r><w:drawing>'
                '<a:blip r:embed="rId5"/></w:drawing></w:r></w:p></w:body></w:document>'
            )
            rels = (
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                'Target="media/image1.png"/></Relationships>'
            )
            with ZipFile(source, "w") as archive:
                archive.writestr("[Content_Types].xml", "<Types/>")
                archive.writestr("word/document.xml", xml)
                archive.writestr("word/_rels/document.xml.rels", rels)
                archive.writestr("word/media/image1.png", b"keep")
            job = root / "job"
            manifest_path = pipeline.prepare(source, job, "English")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["units"][0]["target"] = "Equipment"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            candidate = root / "candidate.docx"
            with ZipFile(source) as src, ZipFile(candidate, "w") as dst:
                for info in src.infolist():
                    data = src.read(info.filename)
                    if info.filename == "word/document.xml":
                        data = data.replace(b'<a:blip r:embed="rId5"/>', b'<a:blip/>').replace("设备".encode(), b"Equipment")
                    dst.writestr(info, data)
            with self.assertRaisesRegex(ValueError, "referenced media"):
                pipeline.validate(candidate, manifest_path)

    def test_localize_images_changes_only_approved_png_region_and_keeps_reference(self):
        from io import BytesIO
        from PIL import Image

        pipeline = self.load_pipeline()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.docx"
            image = Image.new("RGB", (120, 60), "white")
            image.paste((255, 0, 0), (0, 0, 20, 20))
            image_bytes = BytesIO(); image.save(image_bytes, format="PNG")
            xml = (
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
                'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<w:body><w:p><w:r><w:drawing><a:blip r:embed="rId5"/></w:drawing></w:r></w:p></w:body></w:document>'
            )
            rels = (
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                'Target="media/image1.png"/></Relationships>'
            )
            with ZipFile(source, "w") as archive:
                archive.writestr("[Content_Types].xml", "<Types/>")
                archive.writestr("word/document.xml", xml)
                archive.writestr("word/_rels/document.xml.rels", rels)
                archive.writestr("word/media/image1.png", image_bytes.getvalue())
            plan = root / "plan.json"
            plan.write_text(json.dumps({"images": [{"media": "word/media/image1.png", "size": [120, 60], "overlays": [
                {"x": 30, "y": 20, "width": 80, "height": 20, "text": "Equipment", "font_size": 14}
            ]}]}), encoding="utf-8")
            output = root / "localized.docx"
            pipeline.localize_images(source, plan, output)
            with ZipFile(output) as archive:
                localized = Image.open(BytesIO(archive.read("word/media/image1.png"))).convert("RGB")
            self.assertEqual((120, 60), localized.size)
            self.assertEqual((255, 0, 0), localized.getpixel((5, 5)))
            self.assertEqual(["word/media/image1.png"], pipeline.analyze(output)["referenced_media"])

    def test_apply_clears_vertical_strip_indents_and_fits_short_cjk_titles(self):
        pipeline = self.load_pipeline()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.docx"
            body = (
                '<w:p><w:pPr>'
                '<w:spacing w:before="330" w:line="177" w:lineRule="auto"/>'
                '<w:ind w:left="4841" w:right="5209" w:firstLine="0"/>'
                '<w:jc w:val="both"/>'
                '</w:pPr><w:r><w:rPr><w:sz w:val="72"/></w:rPr><w:t>设计方案</w:t></w:r></w:p>'
            )
            xml = (
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                f'<w:body>{body}'
                '<w:sectPr><w:pgSz w:w="3000" w:h="5000"/>'
                '<w:pgMar w:left="850" w:right="283" w:top="720" w:bottom="720"/></w:sectPr>'
                '</w:body></w:document>'
            )
            with ZipFile(source, "w") as archive:
                archive.writestr("[Content_Types].xml", "<Types/>")
                archive.writestr("word/document.xml", xml)
            job = root / "job"
            manifest_path = pipeline.prepare(source, job, "English")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["units"][0]["target"] = "Design Proposal"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            output = root / "translated.docx"
            pipeline.apply(manifest_path, output)
            with ZipFile(output) as archive:
                document = archive.read("word/document.xml").decode("utf-8")

            self.assertNotIn('w:left="4841"', document)
            self.assertNotIn('w:right="5209"', document)
            size = re.search(r'<w:sz w:val="(\d+)"/>', document)
            self.assertIsNotNone(size)
            self.assertEqual(40, int(size.group(1)))

    def test_word_native_check_failure_is_warning_not_delivery_blocker(self):
        pipeline = self.load_pipeline()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_docx(root)
            job = root / "job"
            manifest_path = pipeline.prepare(source, job, "English")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["units"][0]["target"] = "Equipment"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            output = root / "translated.docx"
            pipeline.apply(manifest_path, output)

            with mock.patch.object(
                pipeline.subprocess,
                "run",
                side_effect=subprocess.CalledProcessError(1, ["powershell"]),
            ):
                pipeline.validate(output, manifest_path, word_native=True)

            qa = json.loads((job / "qa-report.json").read_text(encoding="utf-8"))
            self.assertTrue(qa["passed"])
            self.assertEqual("warning", qa["word"]["status"])
            self.assertIn("optional Word-native check failed", qa["warnings"][0])

    def test_static_validation_skips_word_native_check_by_default(self):
        pipeline = self.load_pipeline()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_docx(root)
            job = root / "job"
            manifest_path = pipeline.prepare(source, job, "English")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["units"][0]["target"] = "Equipment"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            output = root / "translated.docx"
            pipeline.apply(manifest_path, output)

            with mock.patch.object(pipeline.subprocess, "run") as run:
                pipeline.validate(output, manifest_path)

            run.assert_not_called()
            qa = json.loads((job / "qa-report.json").read_text(encoding="utf-8"))
            self.assertTrue(qa["passed"])
            self.assertEqual("skipped", qa["word"]["status"])

    def test_protected_token_normalization_accepts_equivalent_office_notation(self):
        pipeline = self.load_pipeline()
        self.assertEqual(
            {"10kv", "1.4°c", "40mm"},
            pipeline.normalize_protected_tokens(["10Kv", "10 kV", "1,4 ℃", "40 mm"]),
        )

    def test_com_contract_uses_visible_legacy_conversion_and_single_content_page_measure(self):
        text = WORD_COM.read_text(encoding="utf-8")
        self.assertIn("$word.Visible = $true", text)
        self.assertIn("SaveAs2", text)
        self.assertNotIn("ComputeStatistics", text)
        self.assertIn("Content.Information(4)", text)

    def test_pipeline_bypasses_local_powershell_script_policy(self):
        text = PIPELINE.read_text(encoding="utf-8")
        self.assertIn('"-ExecutionPolicy", "Bypass"', text)


if __name__ == "__main__":
    unittest.main()
