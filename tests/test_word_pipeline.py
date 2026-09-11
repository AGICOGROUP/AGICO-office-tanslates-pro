from __future__ import annotations

import json
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
    def test_apply_rejects_original_output_before_writing(self):
        pipeline = self.load_pipeline()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_docx(root)
            original = source.read_bytes()
            manifest_path = pipeline.prepare(source, root / "job", "English")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["units"][0]["target"] = "Equipment"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "original|source"):
                pipeline.apply(manifest_path, source)
            self.assertEqual(original, source.read_bytes())

    def test_parameter_check_preserves_counts_signs_and_unit_case(self):
        pipeline = self.load_pipeline()
        damaged = [
            ("数量：2台", "Quantity: 3 units"),
            ("价格：1000美元", "Price: 9000 USD"),
            ("压力：5 MPa", "Pressure: 5 mPa"),
            ("功率：5 MW", "Power: 5 mW"),
            ("电机45kW，备用45kW", "Motor 45kW"),
            ("温度-5°C", "Temperature 5°C"),
        ]
        for source, target in damaged:
            with self.subTest(source=source, target=target):
                self.assertTrue(pipeline.parameter_mismatch(source, target))
        for source, target in [
            ("数量：2台", "Quantity: 2 units"),
            ("压力：5 MPa", "Pressure: 5 MPa"),
            ("功率10kW和10kW", "Power 10 kW and 10 kW"),
            ("电压10Kv", "Voltage 10 kV"),
        ]:
            with self.subTest(source=source, target=target):
                self.assertFalse(pipeline.parameter_mismatch(source, target))

    def test_validate_rejects_missing_or_misplaced_duplicate_occurrences(self):
        pipeline = self.load_pipeline()
        for damage in ("delete", "move", "media"):
            with self.subTest(damage=damage), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                body = '<w:p><w:r><w:t>设备</w:t></w:r></w:p>' * 2
                body += '<w:p><w:r><w:t>清单</w:t></w:r></w:p>'
                source = self.make_docx(root, body)
                manifest_path = pipeline.prepare(source, root / "job", "English")
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                for unit in manifest["units"]:
                    unit["target"] = {"设备": "Equipment", "清单": "List"}[unit["source"]]
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                output = root / "output.docx"
                pipeline.apply(manifest_path, output)
                with ZipFile(output) as archive:
                    parts = {name: archive.read(name) for name in archive.namelist()}
                document = pipeline.etree.fromstring(parts["word/document.xml"])
                paragraphs = list(document.iter(pipeline.W_P))
                if damage == "delete":
                    paragraphs[1].getparent().remove(paragraphs[1])
                elif damage == "move":
                    paragraphs[1].getparent().append(paragraphs[1])
                else:
                    parts["word/media/image1.png"] = b"changed-image"
                parts["word/document.xml"] = pipeline.etree.tostring(document)
                with ZipFile(output, "w") as archive:
                    for name, payload in parts.items():
                        archive.writestr(name, payload)
                with self.assertRaisesRegex(ValueError, "occurrence|media"):
                    pipeline.validate(output, manifest_path)

    def test_validate_accepts_older_manifest_without_occurrence_baseline(self):
        pipeline = self.load_pipeline()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_docx(root)
            manifest_path = pipeline.prepare(source, root / "job", "English")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest.pop("occurrences", None)
            manifest.pop("media_sha256", None)
            manifest["units"][0]["target"] = "Equipment"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            output = root / "output.docx"
            pipeline.apply(manifest_path, output)
            pipeline.validate(output, manifest_path)

    def test_equivalent_parameters_pass_but_real_damage_still_fails(self):
        pipeline = self.load_pipeline()
        for source_text, target_text, should_pass in [
            ("浓度10％", "Concentration 10%", True),
            ("处理量5吨/日", "Capacity 5 t/day", True),
            ("水分-0.57%", "Moisture-0.57%", True),
            ("≤10mg/m3", "≤10 mg/m3", True),
            ("功率10kW", "Power 10 kW.", True),
            ("浓度10％", "Concentration 11%", False),
            ("处理量5吨/日", "Capacity 5 kg/day", False),
            ("编号AB123", "Code AB124", False),
            ("温度850℃", "Temperature 850", False),
            ("功率10kW和20kW", "Power 10kW and 10kW", False),
            ("第一章概述", "Chapter 1 Overview", True),
            ("气体CH4", "Gas CH4 and nitrogen", True),
        ]:
            with self.subTest(source=source_text, target=target_text), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = self.make_docx(root, f'<w:p><w:r><w:t>{source_text}</w:t></w:r></w:p>')
                manifest_path = pipeline.prepare(source, root / "job", "English")
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["units"][0]["target"] = target_text
                manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
                output = root / "output.docx"
                pipeline.apply(manifest_path, output)
                if should_pass:
                    pipeline.validate(output, manifest_path)
                else:
                    with self.assertRaisesRegex(ValueError, "protected token mismatch"):
                        pipeline.validate(output, manifest_path)

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

    def test_apply_preserves_consecutive_breaks_without_requiring_an_empty_text_node(self):
        pipeline = self.load_pipeline()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_docx(
                root,
                '<w:p><w:r><w:t>First section</w:t><w:br/><w:br/><w:t>Second section</w:t></w:r></w:p>',
            )
            manifest_path = pipeline.prepare(source, root / "job", "Chinese")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["units"][0]["target"] = "第一部分\n\n第二部分"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            output = root / "translated.docx"

            pipeline.apply(manifest_path, output)

            with ZipFile(output) as archive:
                document = pipeline.etree.fromstring(archive.read("word/document.xml"))
            paragraph = next(document.iter(pipeline.W_P))
            self.assertEqual("第一部分\n\n第二部分", pipeline.paragraph_text(paragraph))

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
            {"10kV", "1.4°C", "40mm"},
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
