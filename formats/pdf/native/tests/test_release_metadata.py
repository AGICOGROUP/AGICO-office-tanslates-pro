import re
import unittest
from pathlib import Path


class ReleaseMetadataTests(unittest.TestCase):
    def test_display_name_does_not_embed_a_stale_version(self):
        skill_root = Path(__file__).resolve().parents[1]
        metadata = (skill_root / "agents" / "openai.yaml").read_text(
            encoding="utf-8"
        )
        display_line = next(
            line for line in metadata.splitlines() if "display_name:" in line
        )
        self.assertIsNone(re.search(r"\bv\d+\b", display_line, re.IGNORECASE))


if __name__ == "__main__":
    unittest.main()
