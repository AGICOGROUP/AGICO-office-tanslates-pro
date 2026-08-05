from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "pdf_translation_pipeline.py"


class CompactTranslationPacketTests(unittest.TestCase):
    def test_export_omits_layout_geometry_and_round_trips_translations(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            manifest = root / "manifest.json"
            packet = root / "packet.json"
            data = {"source_sha256": "a" * 64, "pages": [{"page": 1, "blocks": [
                {"id": "b1", "source_text": "标题", "translation": "", "role": "heading-1", "bbox": [1, 2, 3, 4], "characters": [{"text": "标", "bbox": [1, 2, 2, 4]}]},
                {"id": "b2", "source_text": "正文 10 kW", "translation": "", "role": "body-10", "bbox": [5, 6, 7, 8], "protected_tokens": ["10 kW"]},
            ]}]}
            manifest.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            exported = subprocess.run([sys.executable, str(SCRIPT), "export-translation", "--manifest", str(manifest), "--output", str(packet)], capture_output=True, text=True)
            self.assertEqual(exported.returncode, 0, exported.stderr)
            payload = json.loads(packet.read_text(encoding="utf-8"))
            self.assertNotIn("bbox", json.dumps(payload))
            self.assertNotIn("characters", json.dumps(payload))
            payload["records"][0]["translation"] = "Title"
            payload["records"][1]["translation"] = "Body text 10 kW"
            packet.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            merged = subprocess.run([sys.executable, str(SCRIPT), "merge-translation", "--manifest", str(manifest), "--packet", str(packet)], capture_output=True, text=True)
            self.assertEqual(merged.returncode, 0, merged.stderr)
            result = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(result["pages"][0]["blocks"][1]["translation"], "Body text 10 kW")


if __name__ == "__main__": unittest.main()
