from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
RESOLVER = ROOT / "scripts" / "resolve_repo_glossary.py"


class RepositoryGlossaryTests(unittest.TestCase):
    def test_resolves_repository_root_glossary(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            glossary = repo / "references" / "水泥专业名词中英对照.md"
            glossary.parent.mkdir(parents=True)
            glossary.write_text("| 中文术语 | English |\n|---|---|\n| 水泥 | Cement |\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(RESOLVER), "--repo-root", str(repo)],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(0, result.returncode, result.stderr)
            report = json.loads(result.stdout)
            self.assertTrue(report["exists"])
            self.assertTrue(report["valid"])
            self.assertEqual(str(glossary.resolve()), report["path"])

    def test_fails_closed_when_glossary_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, str(RESOLVER), "--repo-root", directory],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(2, result.returncode)
            self.assertFalse(json.loads(result.stdout)["exists"])

    def test_rejects_empty_glossary(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            glossary = repo / "references" / "水泥专业名词中英对照.md"
            glossary.parent.mkdir(parents=True)
            glossary.write_text("", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(RESOLVER), "--repo-root", str(repo)],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(2, result.returncode)
            self.assertFalse(json.loads(result.stdout)["valid"])

    def test_rejects_unrelated_markdown_table(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            glossary = repo / "references" / "水泥专业名词中英对照.md"
            glossary.parent.mkdir(parents=True)
            glossary.write_text("| Name | Value |\n|---|---|\n| foo | bar |\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(RESOLVER), "--repo-root", str(repo)],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(2, result.returncode)
            self.assertFalse(json.loads(result.stdout)["valid"])


if __name__ == "__main__":
    unittest.main()
