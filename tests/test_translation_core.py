import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from translation_core import build_worklist, merge_decisions


class TranslationCoreTests(unittest.TestCase):
    def manifest(self):
        return {"source_sha256": "a" * 64, "target_language": "en", "units": [
            {"id": 1, "source": "功率45kW", "target": "", "context": "Main motor"},
            {"id": 2, "source": "价格1000美元", "target": ""},
            {"id": 3, "source": "设备", "target": ""},
        ]}

    def test_partial_merge_keeps_good_work_and_repairs_only_bad_units(self):
        manifest = self.manifest()
        work = build_worklist(manifest, "word")
        work["translation_units"] = work["translation_units"][:2]
        work["translation_units"][0]["translation"] = "Power 45 kW"
        work["translation_units"][1]["translation"] = "Price 9000 USD"
        merged, report = merge_decisions(manifest, work, "word")
        self.assertEqual(merged["units"][0]["target"], "Power 45 kW")
        self.assertEqual(manifest["units"][0]["target"], "")
        self.assertEqual(report["accepted"], [1])
        retry = build_worklist(merged, "word")
        self.assertEqual([u["id"] for u in retry["translation_units"]], [2, 3])
        self.assertIn("technical", retry["translation_units"][0]["error"])
        retry["translation_units"][0]["translation"] = "Price 1000 USD"
        retry["translation_units"][1]["translation"] = "Equipment"
        ready, report = merge_decisions(merged, retry, "word")
        self.assertTrue(report["ready"])
        self.assertEqual(build_worklist(ready, "word")["pending_count"], 0)

    def test_foreign_worklist_cannot_replace_decisions(self):
        manifest = self.manifest()
        work = build_worklist(manifest, "word")
        manifest["source_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "identity"):
            merge_decisions(manifest, work, "word")

    def test_stale_blank_records_do_not_undo_accepted_decisions(self):
        manifest = self.manifest()
        stale = build_worklist(manifest, "word")
        first = copy.deepcopy(stale)
        first["translation_units"] = first["translation_units"][:1]
        first["translation_units"][0]["translation"] = "Power 45 kW"
        merged, _ = merge_decisions(manifest, first, "word")
        stale["translation_units"][1]["translation"] = "Price 1000 USD"
        merged, _ = merge_decisions(merged, stale, "word")
        self.assertEqual([u["id"] for u in build_worklist(merged, "word")["translation_units"]], [3])

    def test_word_decision_trims_incidental_outer_whitespace(self):
        manifest = self.manifest()
        work = build_worklist(manifest, "word")
        work["translation_units"] = [work["translation_units"][2]]
        work["translation_units"][0]["translation"] = " Equipment "
        merged, _ = merge_decisions(manifest, work, "word")
        self.assertEqual(merged["units"][2]["target"], "Equipment")

    def test_malformed_neighbor_does_not_discard_valid_decision(self):
        manifest = self.manifest()
        work = build_worklist(manifest, "word")
        work["translation_units"] = [None, {"id": [], "translation": "invalid"}, work["translation_units"][2]]
        work["translation_units"][2]["translation"] = "Equipment"
        merged, report = merge_decisions(manifest, work, "word")
        self.assertEqual(report["accepted"], [3])
        self.assertEqual(merged["units"][2]["target"], "Equipment")

    def test_explicit_custom_tokens_survive_shared_merge(self):
        manifest = self.manifest()
        manifest["units"] = [{"id": 1, "source": "AGICO 设备", "target": "", "protected_tokens": ["AGICO"]}]
        work = build_worklist(manifest, "word")
        for target in ("Equipment", "XAGICOY Equipment", "A G I C O Equipment"):
            work["translation_units"][0]["translation"] = target
            _, report = merge_decisions(manifest, work, "word")
            self.assertFalse(report["ready"], target)
            self.assertEqual(report["pending_count"], 1)

    def test_conflicting_duplicates_rejected_while_independent_decision_survives(self):
        manifest = self.manifest()
        work = build_worklist(manifest, "word")
        work["translation_units"][0]["translation"] = "Power 45 kW"
        work["translation_units"][1]["translation"] = "Price 1000 USD"
        work["translation_units"].append(copy.deepcopy(work["translation_units"][0]))
        merged, report = merge_decisions(manifest, work, "word")
        self.assertEqual(report["accepted"], [2])
        self.assertEqual(merged["units"][0]["target"], "")

    def test_units_are_not_split_and_batches_expose_context(self):
        work = build_worklist(self.manifest(), "word", max_chars=6)
        ids = [unit_id for batch in work["batches"] for unit_id in batch["unit_ids"]]
        self.assertEqual(ids, [1, 2, 3])
        self.assertEqual(work["translation_units"][0]["context"], "Main motor")
        self.assertTrue(all(batch["characters"] <= 6 or len(batch["unit_ids"]) == 1 for batch in work["batches"]))

    def test_ppt_and_excel_share_decision_contract(self):
        for format_name, source_field in [("ppt", "source_text"), ("excel", "source")]:
            with self.subTest(format_name=format_name):
                manifest = {"source_sha256": "a"*64, "target_language": "en", "translation_units": [
                    {"id": "a", source_field: "设备", "translation": "", "status": "pending"}]}
                work = build_worklist(manifest, format_name)
                work["translation_units"][0]["translation"] = "Equipment"
                merged, report = merge_decisions(manifest, work, format_name)
                self.assertTrue(report["ready"])
                self.assertEqual(merged["translation_units"][0]["translation"], "Equipment")

    def test_technical_codes_and_word_boundaries_cannot_disappear(self):
        for source, target in [("型号AB123", "Model AB124"), ("功率\t45kW", "Power 45kW"), ("尺寸±5 mm", "Size 5 mm")]:
            manifest = self.manifest()
            manifest["units"] = [{"id": 1, "source": source, "target": ""}]
            work = build_worklist(manifest, "word")
            work["translation_units"][0]["translation"] = target
            _, report = merge_decisions(manifest, work, "word")
            self.assertFalse(report["ready"], source)

    def test_chinese_target_rejects_untranslated_english_language(self):
        manifest = {"source_sha256": "a"*64, "target_language": "zh-CN", "units": [
            {"id": 1, "source": "BASIC REQUIREMENTS", "target": ""},
            {"id": 2, "source": "WELDING", "target": ""},
            {"id": 3, "source": "ISO 9001", "target": ""},
            {"id": 4, "source": "96 m3/m2h", "target": ""},
        ]}
        work = build_worklist(manifest, "word")
        for item in work["translation_units"]:
            item["translation"] = item["source"]
        merged, report = merge_decisions(manifest, work, "word")
        self.assertEqual([item["id"] for item in report["rejected"]], [1, 2])
        self.assertEqual(merged["units"][2]["target"], "ISO 9001")
        self.assertEqual(merged["units"][3]["target"], "96 m3/m2h")

    def test_language_checks_handle_changed_spelling_short_labels_and_existing_chinese(self):
        cases = [
            ("BASIC REQUIREMENTS", "Basic requirements.", False),
            ("FANS", "FANS", False),
            ("WELDING", "WELDING。", False),
            ("DRIVE\nSAFETY", "驱动装置\nSAFETY", False),
            ("风机 ISO 9001", "风机 ISO 9001", True),
            ("ISO 9001 / ASTM A36", "ISO 9001 / ASTM A36", True),
            ("96 m3/m2h", "96 m3/m2h", True),
            ("Air Volume\t:\t2.5 (m3/min)/m2", "风量\t:\t2.5 (m3/min)/m2", True),
            ("Gearboxes\t0.15 million hours.", "齿轮箱\t0.15 million hours。", False),
            ("Fans", "风机", True),
        ]
        for source, target, expected in cases:
            with self.subTest(source=source, target=target):
                manifest = {"target_language": "zh-CN", "units": [{"id": 1, "source": source, "target": ""}]}
                work = build_worklist(manifest, "word")
                work["translation_units"][0]["translation"] = target
                _, report = merge_decisions(manifest, work, "word")
                self.assertEqual(report["ready"], expected)

    def test_retention_needs_an_explicit_reason_and_survives_resume(self):
        manifest = {"target_language": "zh-CN", "units": [{"id": 1, "source": "BEUMER", "target": ""}]}
        work = build_worklist(manifest, "word")
        item = work["translation_units"][0]
        item.update(translation="BEUMER", status="retain")
        _, report = merge_decisions(manifest, work, "word")
        self.assertFalse(report["ready"])
        item["reason"] = "Equipment manufacturer's registered brand; retain official spelling."
        merged, report = merge_decisions(manifest, work, "word")
        self.assertTrue(report["ready"])
        self.assertEqual(build_worklist(merged, "word")["pending_count"], 0)
        item.update(translation="伯曼", status="translated")
        merged, report = merge_decisions(merged, work, "word")
        self.assertTrue(report["ready"])
        self.assertNotIn("reason", merged["units"][0])

    def test_automatic_code_retention_does_not_claim_human_review(self):
        manifest = {"target_language": "zh-CN", "units": [{"id": 1, "source": "ISO 9001", "target": ""}]}
        work = build_worklist(manifest, "word")
        work["translation_units"][0]["translation"] = "ISO 9001"
        merged, report = merge_decisions(manifest, work, "word")
        self.assertTrue(report["ready"])
        self.assertNotIn("Reviewed", merged["units"][0].get("reason", ""))

    def test_all_formats_retry_only_untranslated_heading(self):
        for fmt, collection, src_key, dst_key in [
                ("word", "units", "source", "target"),
                ("excel", "translation_units", "source", "translation"),
                ("ppt", "translation_units", "source_text", "translation")]:
            with self.subTest(format=fmt):
                manifest = {"target_language": "zh-CN", collection: [
                    {"id": 1, src_key: "BASIC REQUIREMENTS", dst_key: ""},
                    {"id": 2, src_key: "Fans", dst_key: ""}]}
                work = build_worklist(manifest, fmt)
                work["translation_units"][0]["translation"] = "Basic requirements"
                work["translation_units"][1]["translation"] = "风机"
                merged, report = merge_decisions(manifest, work, fmt)
                self.assertEqual(report["accepted"], [2])
                self.assertEqual([u["id"] for u in build_worklist(merged, fmt)["translation_units"]], [1])
                self.assertEqual(merged[collection][1][dst_key], "风机")


if __name__ == "__main__":
    unittest.main()
