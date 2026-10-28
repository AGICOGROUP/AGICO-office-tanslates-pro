from __future__ import annotations

import re
import sys
from pathlib import Path
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
GLOSSARY_NAME = "水泥专业名词中英对照.md"
sys.path.insert(0, str(ROOT / "scripts"))
import glossary
from glossary import parse_glossary
from translation_core import untranslated_natural_language


class RootSkillStructureTests(unittest.TestCase):
    def test_chinese_translation_allows_structural_force_units(self):
        self.assertFalse(untranslated_natural_language(
            "Floor panels on supports\t13 kN/m2",
            "直接铺设在支承件上的楼板\t13 kN/m2",
            "zh-CN",
        ))

    def test_glossary_patterns_are_compiled_once_per_lookup(self):
        entries = [{"source": "cement mill", "target": "水泥磨"},
                   {"source": "fan", "target": "风机"}]
        with mock.patch.object(glossary, "parse_glossary", return_value=entries), \
             mock.patch.object(glossary.re, "compile", wraps=glossary.re.compile) as compiler, \
             mock.patch.object(glossary, "resolve_glossary", return_value={"exists": True, "path": __file__}):
            glossary.lookup_terms(["cement mill fan"] * 20)
        self.assertEqual(compiler.call_count, len(entries))

    def test_python_caches_are_excluded_from_the_repository(self):
        ignore_file = ROOT / ".gitignore"
        self.assertTrue(ignore_file.is_file())
        patterns = set(ignore_file.read_text(encoding="utf-8").splitlines())
        self.assertIn("__pycache__/", patterns)
        self.assertIn("*.pyc", patterns)

    def test_root_skill_is_the_upload_router(self):
        skill = ROOT / "SKILL.md"
        self.assertTrue(skill.is_file())
        text = skill.read_text(encoding="utf-8")
        normalized = " ".join(text.split())
        self.assertIn("Use when", text)
        for extension in (".docx", ".xlsx", ".pptx"):
            self.assertIn(extension, text)
        self.assertIn("scripts/route_office_file.py", text)
        for adapter in (
            "formats/word/SKILL.md",
            "formats/excel/SKILL.md",
            "formats/ppt/SKILL.md",
        ):
            self.assertIn(adapter, text)
        for removed in ("formats/pdf", "formats/image", ".pdf", ".png", ".jpg", ".jpeg"):
            self.assertNotIn(removed, text)
        self.assertEqual(
            {"word", "excel", "ppt"},
            {path.name for path in (ROOT / "formats").iterdir() if path.is_dir()},
        )
        self.assertIn("Routing ends immediately", normalized)
        self.assertIn("Do not read or consider any other format adapter", normalized)
        for downstream_rule in ("Hash and preserve", "glossary", "protected tokens", "render"):
            self.assertNotIn(downstream_rule, text)

    def test_selected_office_adapters_do_not_return_to_the_root_router(self):
        for adapter in ("word", "excel", "ppt"):
            text = (ROOT / "formats" / adapter / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(adapter=adapter):
                self.assertIn("Top-level routing is complete", text)
                self.assertIn("Do not run the root Office router again", text)

    def test_root_ui_metadata_exists(self):
        metadata = ROOT / "agents" / "openai.yaml"
        self.assertTrue(metadata.is_file())
        text = metadata.read_text(encoding="utf-8")
        self.assertIn('display_name: "', text)
        self.assertIn('short_description: "', text)
        self.assertIn('$office-translate-pro', text)
        for removed in ("PDF", "PNG", "JPEG", "image"):
            self.assertNotIn(removed, text)

    def test_shared_glossary_has_one_preferred_translation_per_source(self):
        glossary = ROOT / "references" / GLOSSARY_NAME
        self.assertTrue(glossary.is_file())
        entries = parse_glossary(glossary.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(entries), 1200)
        self.assertEqual(len(entries), len({entry["source"] for entry in entries}))
        terms = {entry["source"]: entry for entry in entries}
        self.assertEqual("Vertical roller mill", terms["立磨"]["target"])
        self.assertIn("Roller Mill", terms["立磨"]["aliases"])
        self.assertTrue(terms["护套"]["context"])

    def test_translation_policy_forbids_third_party_services(self):
        policy = (ROOT / "references" / "translation-decisions.md").read_text(encoding="utf-8")
        self.assertIn("Do not send document content to third-party translation services", policy)
        self.assertIn("Use the current model's native translation capability", policy)
        self.assertIn("水泥专业名词中英对照.md", policy)
        self.assertNotIn("An external translation service may provide a draft", policy)


class WordAdapterStructureTests(unittest.TestCase):
    def test_word_adapter_encodes_the_preservation_contract(self):
        skill = ROOT / "formats" / "word" / "SKILL.md"
        self.assertTrue(skill.is_file())
        text = skill.read_text(encoding="utf-8")
        required_phrases = (
            "does not depend on another Office translation skill",
            f"../../references/{GLOSSARY_NAME}",
            "editable",
            "image text",
            "protected tokens",
            "Never overwrite",
            "Microsoft Word",
            "without an external PDF conversion or rendering gate",
        )
        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        for forbidden in (
            "documents:documents",
            "render every page",
            "complete rendered comparison",
            "ExportAsFixedFormat",
            "Inspect every final page",
            "page count",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)
        self.assertIn("word_pipeline.py", text)
        self.assertIn("optional and non-blocking", text)
        self.assertNotIn("Deliver only after that one Word-native validation passes", text)

    def test_flexible_pagination_is_word_only(self):
        wording = "Preserve the document formatting; pagination may change"
        word_skill = (ROOT / "formats" / "word" / "SKILL.md").read_text(encoding="utf-8")
        excel_skill = (ROOT / "formats" / "excel" / "SKILL.md").read_text(encoding="utf-8")
        ppt_skill = (ROOT / "formats" / "ppt" / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn(wording, word_skill)
        self.assertNotIn(wording, excel_skill)
        self.assertNotIn(wording, ppt_skill)

    def test_word_ui_metadata_exists(self):
        metadata = ROOT / "formats" / "word" / "agents" / "openai.yaml"
        self.assertTrue(metadata.is_file())
        text = metadata.read_text(encoding="utf-8")
        self.assertIn('$office-translate-pro-word', text)

class InImageMethodPolicyTests(unittest.TestCase):
    """Image text has exactly two accepted methods, and no file may re-declare one of them
    as the only one.

    The shared rule used to name ``image_edit`` as the sole method and to describe programmatic
    label drawing as retired. That excluded the deterministic erase + refill path, which measures
    far better on technical drawings (100% edge retention and 0.000% pixel change outside the label
    boxes, against 21.5% for generative editing). The policy is now a per-image selection, so a
    single-method claim anywhere in the skill is a regression.
    """

    RULE = "references/image-translation.md"
    SCRIPT = "scripts/inimage_erase_refill.py"
    MARKDOWN = ("SKILL.md", "formats/word/SKILL.md", "formats/excel/SKILL.md", "formats/ppt/SKILL.md")

    def rule_text(self):
        return (ROOT / self.RULE).read_text(encoding="utf-8")

    def test_shared_rule_offers_both_methods(self):
        text = self.rule_text()
        normalized = " ".join(text.split())
        self.assertIn("Two accepted methods", normalized)
        self.assertIn("`image_edit`", text)
        self.assertIn(self.SCRIPT.split("/")[-1], text)
        for command in ("ocr", "render", "verify", "zoom"):
            self.assertIn(f"inimage_erase_refill.py {command}", text)

    def test_shared_rule_states_the_erase_refill_limits(self):
        text = " ".join(self.rule_text().split())
        self.assertIn("Oblique or rotated labels", text)
        self.assertIn("outside_edges_retained_pct", text)

    # Archived plans under docs/ record what was believed at the time, and SKILL.patch.md is the
    # changelog that quotes the wording it forbids. Neither is an operative rule.
    SKIP_PARTS = {"__pycache__", "docs"}
    SKIP_NAMES = {"SKILL.patch.md"}
    SINGLE_METHOD_CLAIMS = ("the only method", "only gpt image editing", "as the only method")

    def operative_markdown(self):
        for path in ROOT.rglob("*.md"):
            if self.SKIP_PARTS.intersection(path.parts) or path.name in self.SKIP_NAMES:
                continue
            yield path

    def test_no_file_declares_a_single_image_method(self):
        offenders = []
        for path in self.operative_markdown():
            normalized = " ".join(
                path.read_text(encoding="utf-8", errors="replace").split()
            ).lower()
            for claim in self.SINGLE_METHOD_CLAIMS:
                if claim in normalized:
                    offenders.append(f"{path.relative_to(ROOT).as_posix()}:{claim}")
        self.assertEqual([], offenders, "image text has two selectable methods, never one")

    def test_removed_harvest_skill_is_not_referenced(self):
        """The zoom-crop step is now the bundled ``zoom`` command, not an external skill."""
        for path in self.operative_markdown():
            text = " ".join(path.read_text(encoding="utf-8", errors="replace").split())
            with self.subTest(part=path.relative_to(ROOT).as_posix()):
                self.assertNotIn("图像局部网格化放大分析", text)
                self.assertNotIn("工程图标签本地化", text)

    def test_replacement_writers_accept_either_method(self):
        rule = " ".join(self.rule_text().split())
        self.assertIn("Register the output with the same `localized` decision fields", rule)
        self.assertTrue((ROOT / self.SCRIPT).is_file())
        for name in self.MARKDOWN:
            adapter = Path(name).parent
            linked = [ROOT / name]
            if adapter != ROOT:
                linked.append(adapter / "references" / "image-text-localization.md")
            text = " ".join(
                path.read_text(encoding="utf-8", errors="replace")
                for path in linked if path.is_file()
            )
            with self.subTest(skill=name):
                # Either the adapter states the rule itself or it defers to its image reference,
                # which must then carry the link.
                self.assertIn("image-translation.md", text)


class RuntimePathContractTests(unittest.TestCase):
    """Runtimes are resolved centrally, never by re-deriving a sibling's position.

    Duplicated layout arithmetic silently produced non-existent executables: the managed runtime
    keeps Node at ``<root>/node/node.exe`` while older installs used ``<root>/node/bin/node.exe``,
    so a fixed ``parent.parent`` walk plus a hardcoded ``bin`` segment resolved to nothing and the
    failure surfaced only as an empty "inspection failed: undefined".
    """

    SHARED = {"scripts/runtime_paths.py", "scripts/runtime_paths.mjs"}
    # This file holds the banned literals in order to enforce them, and the excel fast pipeline
    # documents the historical defect in prose. Neither is a live call site.
    SELF = "tests/test_skill_structure.py"
    SOURCES = (".py", ".mjs", ".js", ".ps1")
    SKIP_DIRS = {"__pycache__", ".pytest_cache", "node_modules", ".git"}
    # Only executable-layout derivation is banned. Resolving a package directory from the
    # executable (artifact_runtime.mjs) keeps NODE_PATH and require.resolve fallbacks and is fine.
    FORBIDDEN = (
        "Path(sys.executable).resolve().parent.parent",
        "Path(sys.executable).parent.parent",
        '"node", "bin"',
        "'node', 'bin'",
        '"bin", "node.exe"',
        "'bin', 'node.exe'",
        '"python", "python.exe"',
        "'python', 'python.exe'",
        '"python", "bin"',
        "'python', 'bin'",
    )

    def sources(self):
        # Inspect maintained source, not ignored historical job scripts or customer artifacts.
        for path in (path for folder in ('scripts', 'formats', 'tests')
                     for path in (ROOT / folder).rglob('*')):
            if not path.is_file() or path.suffix not in self.SOURCES:
                continue
            if self.SKIP_DIRS.intersection(path.parts):
                continue
            relative = path.relative_to(ROOT).as_posix()
            if relative in self.SHARED or relative == self.SELF:
                continue
            yield path

    def test_no_call_site_rederives_a_sibling_runtime(self):
        offenders = []
        for path in self.sources():
            text = path.read_text(encoding="utf-8", errors="replace")
            for number, line in enumerate(text.splitlines(), start=1):
                stripped = line.strip()
                if stripped.startswith(("#", "//", "*")):
                    continue
                if any(pattern in line for pattern in self.FORBIDDEN):
                    offenders.append(f"{path.relative_to(ROOT).as_posix()}:{number}")
        self.assertEqual([], offenders, "resolve runtimes through scripts/runtime_paths.(py|mjs)")

    def test_no_machine_specific_absolute_path(self):
        pattern = re.compile(r"[A-Za-z]:[\\/]{1,2}[Uu]sers[\\/]", re.IGNORECASE)
        offenders = [
            f"{path.relative_to(ROOT).as_posix()}:{number}"
            for path in self.sources()
            for number, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
            )
            if pattern.search(line) and not line.strip().startswith(("#", "//"))
        ]
        self.assertEqual([], offenders, "derive user directories from the environment, not a path")

    def test_shared_resolvers_are_importable(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import runtime_paths

        self.assertTrue(callable(runtime_paths.resolve_executable))
        self.assertTrue((ROOT / "scripts" / "runtime_paths.mjs").is_file())
        self.assertIn("node.exe", (ROOT / "scripts" / "runtime_paths.mjs").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
