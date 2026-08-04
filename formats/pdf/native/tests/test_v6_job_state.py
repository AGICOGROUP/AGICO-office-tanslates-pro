from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "v6_job_state.py"
SPEC = importlib.util.spec_from_file_location("v6_job_state", SCRIPT)
assert SPEC and SPEC.loader
state = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = state
SPEC.loader.exec_module(state)


class V6JobStateTests(unittest.TestCase):
    def test_job_identity_is_derived_from_original_pdf(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "sample.pdf"
            source.write_bytes(b"%PDF-source")
            job_dir = state.create_job(source, root / "jobs")
            job = state.load_job(job_dir)
            self.assertEqual(job["source"]["sha256"], state.sha256_file(source))
            self.assertTrue(job_dir.name.endswith(job["source"]["sha256"][:8]))

    def test_stage_cannot_advance_with_changed_source(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "sample.pdf"
            source.write_bytes(b"%PDF-source")
            job_dir = state.create_job(source, root / "jobs")
            manifest = job_dir / "manifest.json"
            manifest.write_text("{}", encoding="utf-8")
            state.bind_artifact(job_dir, "manifest", manifest)
            source.write_bytes(b"%PDF-changed")
            with self.assertRaisesRegex(ValueError, "source hash changed"):
                state.advance(job_dir, "native_translated", ("manifest",))

    def test_artifact_binding_rejects_replacement(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "sample.pdf"
            source.write_bytes(b"%PDF-source")
            job_dir = state.create_job(source, root / "jobs")
            artifact = job_dir / "manifest.json"
            artifact.write_text("{}", encoding="utf-8")
            state.bind_artifact(job_dir, "manifest", artifact)
            artifact.write_text('{"changed": true}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "artifact hash changed"):
                state.assert_artifacts(job_dir, ("manifest",))

    def test_stage_must_advance_exactly_one_step(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "sample.pdf"
            source.write_bytes(b"%PDF-source")
            job_dir = state.create_job(source, root / "jobs")
            with self.assertRaisesRegex(ValueError, "invalid stage transition"):
                state.advance(job_dir, "assembled", ())


if __name__ == "__main__":
    unittest.main()
