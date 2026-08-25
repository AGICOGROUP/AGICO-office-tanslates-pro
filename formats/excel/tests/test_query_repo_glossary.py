import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "query_repo_glossary.py"


class QueryGlossaryTests(unittest.TestCase):
    def test_returns_only_terms_present_in_manifest_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            glossary = root / "references" / "水泥专业名词中英对照.md"
            glossary.parent.mkdir(parents=True)
            glossary.write_text(
                "| 中文术语 | English |\n|---|---|\n| 水泥 | Cement |\n| 窑尾 | Kiln inlet |\n| 风机 | Fan |\n",
                encoding="utf-8",
            )
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({
                "translation_units": [{"source": "窑尾排风机"}, {"source": "型号 X1"}],
            }, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--repo-root", str(root), "--manifest", str(manifest)],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(0, result.returncode, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(["窑尾", "风机"], [entry["source"] for entry in report["entries"]])
            self.assertEqual(2, report["matched_entries"])


if __name__ == "__main__":
    unittest.main()
