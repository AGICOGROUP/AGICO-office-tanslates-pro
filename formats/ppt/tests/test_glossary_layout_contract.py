from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT / "references" / "typography-and-fit.md"


class GlossaryAndLayoutContractTests(unittest.TestCase):
    def test_native_adapter_resolves_the_shared_glossary(self):
        import json, subprocess, sys
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/resolve_repo_glossary.py'),
                                 '--text', '水泥磨'],
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(Path(report['path']).resolve(),
                         (ROOT.parents[1] / 'references/水泥专业名词中英对照.md').resolve())
        self.assertTrue(any(item['source'] == '水泥磨' for item in report['matched_entries']))

    def test_peer_heading_and_body_typography_is_consistent(self):
        self.assertTrue(LAYOUT.is_file(), "typography/layout contract must be bundled")
        text = LAYOUT.read_text(encoding="utf-8").lower()
        self.assertIn("peer section headings", text)
        self.assertIn("one font size", text)
        self.assertIn("bold", text)
        self.assertIn("peer body text", text)

    def test_layout_changes_require_verified_overflow_or_collision(self):
        self.assertTrue(LAYOUT.is_file(), "typography/layout contract must be bundled")
        text = LAYOUT.read_text(encoding="utf-8").lower()
        self.assertIn("verified overflow or collision", text)
        self.assertIn("do not alter layout", text)
        self.assertIn("proportionally scale", text)
        self.assertIn("preserve aspect ratio", text)
        self.assertIn("manual review", text)


if __name__ == "__main__":
    unittest.main()
