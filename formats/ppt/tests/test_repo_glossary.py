from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SKILL_ROOT = Path(__file__).resolve().parents[1]
RESOLVER = SKILL_ROOT / "scripts" / "resolve_repo_glossary.py"
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
from resolve_repo_glossary import lookup_terms  # noqa: E402


class RepositoryGlossaryResolutionTests(unittest.TestCase):
    def test_resolves_repository_root_glossary(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            glossary = repo / "references" / "水泥专业名词中英对照.md"
            glossary.parent.mkdir(parents=True)
            glossary.write_text("| 中央控制室 | Central Control Room |\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(RESOLVER), "--repo-root", str(repo)],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(0, result.returncode, result.stderr)
            report = json.loads(result.stdout)
            self.assertTrue(report["exists"])
            self.assertEqual(str(glossary.resolve()), report["path"])

    def test_fails_closed_when_repository_glossary_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            result = subprocess.run(
                [sys.executable, str(RESOLVER), "--repo-root", str(repo)],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(2, result.returncode)
            self.assertTrue(result.stdout, result.stderr)
            report = json.loads(result.stdout)
            self.assertFalse(report["exists"])
            self.assertTrue(report["path"].endswith("references\\水泥专业名词中英对照.md"))

    def test_lookup_returns_only_terms_relevant_to_current_texts(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            glossary = repo / "references" / "水泥专业名词中英对照.md"
            glossary.parent.mkdir(parents=True)
            glossary.write_text(
                "| 中文术语 | English |\n"
                "|---|---|\n"
                "| 篦式冷却机 | grate cooler |\n"
                "| 回转窑 | rotary kiln |\n"
                "| 石灰竖窑 | lime shaft kiln |\n",
                encoding="utf-8",
            )

            report = lookup_terms(
                ["篦式冷却机出口", "回转窑"], repo_root=repo
            )

        self.assertEqual(3, report["glossary_entries"])
        self.assertEqual(
            ["篦式冷却机", "回转窑"],
            [item["source"] for item in report["matched_entries"]],
        )
        self.assertNotIn("石灰竖窑", json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
