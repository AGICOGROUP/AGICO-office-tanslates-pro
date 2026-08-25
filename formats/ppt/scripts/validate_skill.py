#!/usr/bin/env python3
"""Validate the PowerPoint-only Skill package contract."""

from __future__ import annotations

import json
import argparse
from pathlib import Path
import sys

from resolve_repo_glossary import resolve_glossary


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "SKILL.md",
    "agents/openai.yaml",
    "references/powerpoint-workflow.md",
    "references/pipeline-cli.md",
    "references/typography-and-fit.md",
    "references/image-text-localization.md",
    "references/manifest-schema.md",
    "references/overlay-schema.md",
    "scripts/ppt_com.ps1",
    "scripts/ppt_pipeline.py",
    "scripts/inspect_pptx_package.py",
    "scripts/pptx_ooxml.py",
    "scripts/validate_manifest.py",
    "scripts/resolve_repo_glossary.py",
)
def validate(repo_root: str | Path | None = None) -> dict:
    errors: list[str] = []
    missing = [path for path in REQUIRED if not (ROOT / path).is_file()]
    if missing:
        errors.append("missing: " + ", ".join(missing))

    resolved_repo_root = (
        Path(repo_root).resolve()
        if repo_root is not None
        else ROOT.parents[1]
    )
    office_export = resolved_repo_root / "scripts" / "office_com_pdf.ps1"
    if not office_export.is_file():
        errors.append("missing: scripts/office_com_pdf.ps1")

    skill_path = ROOT / "SKILL.md"
    if skill_path.is_file():
        skill = skill_path.read_text(encoding="utf-8")
        if "name: translate-powerpoint-professionally" not in skill:
            errors.append("wrong skill name")
        if "scripts/ppt_pipeline.py" not in skill:
            errors.append("single pipeline entry is not documented")
        if "without deduplicating" in skill:
            errors.append("legacy no-deduplication rule remains")

    glossary = resolve_glossary(repo_root)
    if not glossary["exists"]:
        errors.append("repository glossary not found: " + glossary["path"])

    return {
        "passed": not errors,
        "skill": "translate-powerpoint-professionally",
        "required_files": len(REQUIRED),
        "repository_glossary": glossary,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", help="Repository root; inferred when omitted")
    args = parser.parse_args()
    report = validate(args.repo_root)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
