from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "pdf_translation_pipeline.py"
SPEC = importlib.util.spec_from_file_location("pdf_translation_pipeline_narrow", SCRIPT)
assert SPEC and SPEC.loader
pipeline = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pipeline
SPEC.loader.exec_module(pipeline)


class NarrowIndexColumnTests(unittest.TestCase):
    def test_table_row_keeps_cell_segmentation_when_serial_column_is_narrow(self):
        boxes = [
            [37.15, 254.34, 53.20, 270.09],
            [53.20, 254.34, 147.70, 270.09],
            [147.70, 254.34, 242.20, 270.09],
            [242.20, 254.34, 337.70, 270.09],
            [337.70, 254.34, 432.60, 270.09],
            [432.60, 254.34, 558.15, 270.09],
        ]
        source_parts = ["1", "Power", "High-voltage load", "10 kV", "~1000 kW", "Owner supply"]
        line = {
            "bbox": [42.6, 256.263, 542.167, 266.713],
            "segments": [
                {"cell_index": index, "text": text, "characters": []}
                for index, text in enumerate(source_parts)
            ],
        }
        cells = [{"bbox": box} for box in boxes]

        items = pipeline.table_segment_targets(
            line,
            "1 Power System High-Voltage Load 10kV ~1000kW Provided by Owner",
            cells,
        )

        self.assertEqual(6, len(items))
        self.assertEqual("1", items[0]["text"])
        self.assertLessEqual(items[0]["right"], boxes[0][2])
        self.assertIn("Owner", items[-1]["text"])


if __name__ == "__main__":
    unittest.main()
