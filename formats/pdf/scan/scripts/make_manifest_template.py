from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an auditable manifest template from OCR extraction")
    parser.add_argument("--extraction", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    extraction = json.loads(Path(args.extraction).read_text(encoding="utf-8"))
    manifest = {
        "source": extraction["source"],
        "source_sha256": extraction["source_sha256"],
        "selected_pages": extraction["selected_pages"],
        "pages": extraction["pages"],
        "source_lines": extraction["source_lines"],
        "blocks": [],
    }
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "source_lines": len(manifest["source_lines"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
