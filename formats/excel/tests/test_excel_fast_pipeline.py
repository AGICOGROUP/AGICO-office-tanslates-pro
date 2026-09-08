from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "excel_fast_pipeline.py"


def load_runner():
    if not SCRIPT.exists():
        raise AssertionError("Excel fast pipeline runner is missing")
    spec = importlib.util.spec_from_file_location("excel_fast_pipeline", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ExcelFastPipelineTests(unittest.TestCase):
    def test_node_environment_supplies_python_modules_and_modern_powershell(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            modules = bundle / 'node' / 'node_modules'
            modules.mkdir(parents=True)
            powershell = bundle / 'native' / 'powershell' / 'pwsh.exe'
            powershell.parent.mkdir(parents=True)
            powershell.touch()
            with patch.dict(os.environ, {}, clear=True), patch.object(runner, 'bundled_dependencies', return_value=bundle):
                env = runner.node_environment(None)
            self.assertEqual(str(modules), env['NODE_PATH'])
            self.assertEqual(runner.sys.executable, env['CODEX_PYTHON'])
            if os.name == 'nt':
                self.assertTrue(powershell.samefile(env['CODEX_POWERSHELL']))

    def test_explicit_runtime_override_is_not_silently_replaced(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / 'custom-node.exe'
            executable.touch()
            self.assertTrue(executable.samefile(runner.resolve_executable(str(executable), 'CODEX_NODE', 'node')))
            with self.assertRaises(RuntimeError):
                runner.resolve_executable(str(executable) + '.missing', 'CODEX_NODE', 'node')

    def test_esm_dependency_loads_from_node_path_without_repository_junction(self):
        runner = load_runner()
        node = runner.resolve_executable(None, 'CODEX_NODE', 'node')
        with tempfile.TemporaryDirectory() as directory:
            modules = Path(directory) / 'node_modules'
            package = modules / '@oai' / 'artifact-tool'
            package.mkdir(parents=True)
            (package / 'package.json').write_text('{"type":"module","exports":"./index.mjs"}', encoding='utf-8')
            (package / 'index.mjs').write_text('export const FileBlob = 7; export const SpreadsheetFile = 8; export const Workbook = 9;', encoding='utf-8')
            loader = (ROOT / 'scripts' / 'artifact_runtime.mjs').as_uri()
            result = subprocess.run([node, '--input-type=module', '-e',
                f'import {{Workbook}} from {__import__("json").dumps(loader)}; console.log(Workbook);'],
                env={**os.environ, 'NODE_PATH': str(modules)}, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual('9', result.stdout.strip())

    def make_manifest(self):
        return {
            "schema_version": 2,
            "target_language": "Spanish",
            "translation_units": [
                {
                    "id": "tu-pending",
                    "source": "设备名称",
                    "context_key": "cell:header",
                    "protected_tokens": [],
                    "translation": "",
                    "status": "pending",
                },
                {
                    "id": "tu-retained",
                    "source": "GGD",
                    "context_key": "cell:model",
                    "protected_tokens": [],
                    "translation": "GGD",
                    "status": "retain",
                    "reason": "identifier/model code retained",
                },
            ],
            "images": [],
        }

    def test_worklist_contains_only_pending_translation_fields(self):
        runner = load_runner()
        worklist = runner.build_worklist(self.make_manifest())

        self.assertEqual("Spanish", worklist["target_language"])
        self.assertEqual(1, worklist["pending_count"])
        self.assertEqual(
            [{
                "id": "tu-pending",
                "source": "设备名称",
                "context_key": "cell:header",
                "protected_tokens": [],
                "status": "pending",
                "translation": "",
                "reason": "",
            }],
            worklist["translation_units"],
        )

    def test_apply_worklist_updates_manifest_and_rejects_incomplete_decisions(self):
        runner = load_runner()
        manifest = self.make_manifest()
        worklist = runner.build_worklist(manifest)
        worklist["translation_units"][0].update(
            status="translated", translation="Nombre del equipo"
        )

        updated = runner.apply_worklist(deepcopy(manifest), worklist)
        self.assertEqual("translated", updated["translation_units"][0]["status"])
        self.assertEqual("Nombre del equipo", updated["translation_units"][0]["translation"])

        incomplete = runner.build_worklist(manifest)
        with self.assertRaisesRegex(ValueError, "pending decision"):
            runner.apply_worklist(deepcopy(manifest), incomplete)

    def test_apply_worklist_is_idempotent_for_finalize_retry(self):
        runner = load_runner()
        manifest = self.make_manifest()
        worklist = runner.build_worklist(manifest)
        worklist["translation_units"][0].update(
            status="translated", translation="Nombre del equipo"
        )

        first = runner.apply_worklist(deepcopy(manifest), worklist)
        second = runner.apply_worklist(deepcopy(first), worklist)
        self.assertEqual(first, second)

        changed = deepcopy(worklist)
        changed["translation_units"][0]["translation"] = "Nombre cambiado"
        with self.assertRaisesRegex(ValueError, "conflicting worklist decision"):
            runner.apply_worklist(deepcopy(first), changed)

    def test_timing_report_accumulates_phases_without_losing_previous_stages(self):
        runner = load_runner()
        report = runner.merge_timing_report(
            {"stages_ms": {"route": 12, "convert": 40}},
            {"inspect": 30, "prepare": 8},
        )
        self.assertEqual(
            {"route": 12, "convert": 40, "inspect": 30, "prepare": 8},
            report["stages_ms"],
        )
        self.assertEqual(90, report["total_ms"])

    def test_finalize_stage_plan_resumes_after_the_last_completed_gate(self):
        runner = load_runner()
        self.assertEqual(
            ["merge-decisions", "validate", "apply", "verify", "office-validate"],
            runner.finalize_stage_plan([]),
        )
        self.assertEqual(
            ["verify", "office-validate"],
            runner.finalize_stage_plan(["preflight", "inspect", "prepare", "translate", "validate", "apply"]),
        )
        self.assertEqual(
            [],
            runner.finalize_stage_plan(["apply", "verify", "office-validate"]),
        )


if __name__ == "__main__":
    unittest.main()
