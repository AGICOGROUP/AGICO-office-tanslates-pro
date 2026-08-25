from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
PIPELINE_SCRIPT = ROOT / "scripts" / "ppt_pipeline.py"
sys.path.insert(0, str(ROOT / "scripts"))
from ppt_pipeline import (  # noqa: E402
    STAGES,
    build_translation_manifest,
    complete_delivery,
    first_incomplete_stage,
    mark_stage,
    new_state,
)
from validate_manifest import ManifestError, validate_manifest  # noqa: E402


def occurrence(
    item_id: str,
    *,
    text: str = "篦式冷却机",
    role: str = "body",
    context: str = "body",
    protected_tokens: list[str] | None = None,
) -> dict:
    slide_index = 1 if item_id.endswith("1") else 2
    return {
        "id": item_id,
        "kind": "ppt_paragraph",
        "source_text": text,
        "slide_index": slide_index,
        "shape_id": 2,
        "paragraph_index": 1,
        "role": role,
        "shape_name": "TextBox",
        "context_signature": context,
        "protected_tokens": protected_tokens or [],
    }


def inventory(items: list[dict]) -> dict:
    return {
        "source_file": "sample.pptx",
        "source_path": "D:/fixtures/sample.pptx",
        "source_sha256": "a" * 64,
        "occurrences": items,
        "image_groups": [],
        "risk_plan": {"route": "fast", "complex_reasons": [], "strict_reasons": []},
    }


class ManifestPreparationTests(unittest.TestCase):
    def test_same_text_and_context_reuse_one_translation_unit(self):
        manifest = build_translation_manifest(
            inventory([occurrence("item-1"), occurrence("item-2")]), "en"
        )

        self.assertEqual(2, len(manifest["occurrences"]))
        self.assertEqual(1, len(manifest["translation_units"]))
        unit_ids = {item["translation_unit_id"] for item in manifest["occurrences"]}
        self.assertEqual(1, len(unit_ids))

    def test_same_short_text_in_different_roles_stays_separate(self):
        manifest = build_translation_manifest(
            inventory(
                [
                    occurrence("item-1", text="出口", role="title", context="title"),
                    occurrence("item-2", text="出口", role="body", context="body"),
                ]
            ),
            "en",
        )

        self.assertEqual(2, len(manifest["translation_units"]))

    def test_different_protected_tokens_prevent_reuse(self):
        manifest = build_translation_manifest(
            inventory(
                [
                    occurrence("item-1", text="电机 M1", protected_tokens=["M1"]),
                    occurrence("item-2", text="电机 M2", protected_tokens=["M2"]),
                ]
            ),
            "en",
        )

        self.assertEqual(2, len(manifest["translation_units"]))

    def test_schema_v2_validator_requires_every_unit_translation(self):
        manifest = build_translation_manifest(inventory([occurrence("item-1")]), "en")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(ManifestError):
                validate_manifest(path, require_translations=True)

            manifest["translation_units"][0]["translation"] = "Grate cooler"
            path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            summary = validate_manifest(path, require_translations=True)

        self.assertEqual(1, summary["translation_units"])
        self.assertEqual(1, summary["occurrences"])

    def test_manifest_cannot_apply_while_unique_image_screening_is_pending(self):
        source_inventory = inventory([occurrence("item-1")])
        source_inventory["image_groups"] = [
            {
                "sha256": "b" * 64,
                "media_paths": ["ppt/media/image1.png"],
                "occurrences": [{"slide_index": 1, "shape_id": 3}],
                "screening_status": "pending",
            }
        ]
        manifest = build_translation_manifest(source_inventory, "en")
        manifest["translation_units"][0]["translation"] = "Grate cooler"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(ManifestError):
                validate_manifest(path, require_translations=True)

            manifest["image_groups"][0]["screening_status"] = "retain"
            manifest["image_groups"][0]["reason_code"] = "no-source-language-text"
            path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            summary = validate_manifest(path, require_translations=True)

        self.assertEqual(1, summary["image_groups"])

    def test_manifest_rejects_translation_that_drops_a_protected_token(self):
        manifest = build_translation_manifest(
            inventory([occurrence("item-1", text="Motor M1", protected_tokens=["M1"])]),
            "es",
        )
        manifest["translation_units"][0]["translation"] = "Motor principal"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ManifestError, "protected token missing"):
                validate_manifest(path, require_translations=True)

    def test_table_occurrence_requires_a_valid_cell_location(self):
        item = occurrence("item-1")
        item["kind"] = "ppt_table_cell"
        manifest = build_translation_manifest(inventory([item]), "en")
        manifest["translation_units"][0]["translation"] = "Translated"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ManifestError, "missing field: row"):
                validate_manifest(path, require_translations=True)


class PipelineStateTests(unittest.TestCase):
    def test_state_resumes_from_first_incomplete_stage(self):
        state = new_state(inventory([occurrence("item-1")]), "en")
        self.assertEqual("preflight", first_incomplete_stage(state))
        mark_stage(state, "preflight")
        mark_stage(state, "inspect")
        self.assertEqual("prepare", first_incomplete_stage(state))
        self.assertEqual(list(STAGES), list(state["stages"]))

    def test_delivery_requires_render_and_explicit_visual_review(self):
        state = new_state(inventory([occurrence("item-1")]), "en")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "translated.pptx"
            output.touch()
            with self.assertRaisesRegex(Exception, "render stage"):
                complete_delivery(state, output, visual_review_passed=True)
            mark_stage(state, "render", "office-verification.json")
            with self.assertRaisesRegex(Exception, "visual review"):
                complete_delivery(state, output, visual_review_passed=False)
            complete_delivery(state, output, visual_review_passed=True)

        self.assertTrue(state["stages"]["deliver"]["completed"])

    def test_fast_pipeline_applies_all_translations_through_single_entry(self):
        slide = """<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
        xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld><p:spTree>
        <p:sp><p:nvSpPr><p:cNvPr id="2" name="Title"/></p:nvSpPr><p:txBody><a:p>
        <a:r><a:t>篦式冷却机</a:t></a:r></a:p></p:txBody></p:sp>
        </p:spTree></p:cSld></p:sld>"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pptx"
            output = root / "output.pptx"
            job = root / "job"
            with ZipFile(source, "w", ZIP_DEFLATED) as archive:
                archive.writestr("[Content_Types].xml", "<Types/>")
                archive.writestr("ppt/slides/slide1.xml", slide)

            inspected = subprocess.run(
                [
                    sys.executable,
                    str(PIPELINE_SCRIPT),
                    "inspect",
                    "--input",
                    str(source),
                    "--job-dir",
                    str(job),
                    "--target-language",
                    "en",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(0, inspected.returncode, inspected.stderr)
            prepared = subprocess.run(
                [sys.executable, str(PIPELINE_SCRIPT), "prepare", "--job-dir", str(job)],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(3, prepared.returncode, prepared.stderr)
            manifest_path = job / "translation-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["translation_units"][0]["translation"] = "Grate cooler"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

            applied = subprocess.run(
                [
                    sys.executable,
                    str(PIPELINE_SCRIPT),
                    "apply",
                    "--input",
                    str(source),
                    "--job-dir",
                    str(job),
                    "--output",
                    str(output),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(0, applied.returncode, applied.stderr)
            verified = subprocess.run(
                [
                    sys.executable,
                    str(PIPELINE_SCRIPT),
                    "verify",
                    "--source",
                    str(source),
                    "--job-dir",
                    str(job),
                    "--output",
                    str(output),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(0, verified.returncode, verified.stderr)
            state = json.loads((job / "job-state.json").read_text(encoding="utf-8"))
            verification = json.loads((job / "verification.json").read_text(encoding="utf-8"))
            with ZipFile(output) as archive:
                translated_slide = archive.read("ppt/slides/slide1.xml").decode("utf-8")

        self.assertIn("Grate cooler", translated_slide)
        self.assertTrue(state["stages"]["apply"]["completed"])
        self.assertTrue(state["stages"]["verify"]["completed"])
        self.assertTrue(verification["passed"])
        self.assertEqual(0, state["metrics"]["powerpoint_starts"])


if __name__ == "__main__":
    unittest.main()
