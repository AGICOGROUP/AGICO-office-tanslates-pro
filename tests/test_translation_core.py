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


if __name__ == "__main__":
    unittest.main()
