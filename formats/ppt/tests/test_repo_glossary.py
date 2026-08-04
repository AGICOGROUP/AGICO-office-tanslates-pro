from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SKILL_ROOT = Path(__file__).resolve().parents[1]
RESOLVER = SKILL_ROOT / "scripts" / "resolve_repo_glossary.py"


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


if __name__ == "__main__":
    unittest.main()
