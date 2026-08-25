# PPT Balanced Translation Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current command-by-command PPT workflow with one resumable, risk-driven pipeline that extracts once, safely deduplicates translations, writes once, and uses Microsoft PowerPoint as the final authority.

**Architecture:** `ppt_pipeline.py` is the only production entry point. Pure Python performs `.pptx` preflight, OOXML inventory, manifest preparation, fast-path mutation, structural verification, state recovery, image hashing, and render planning; PowerPoint COM remains an internal adapter for `.ppt` conversion, complex mutation, final reopen, and official PDF export.

**Tech Stack:** Python 3.12 standard library, PowerPoint OOXML/ZIP, PowerShell 5.1 COM automation, Microsoft PowerPoint, pytest/unittest.

**Spec:** `docs/superpowers/specs/2026-08-25-ppt-balanced-translation-pipeline-design.md`

## Global Constraints

- Use replacement mode: one production pipeline, no parallel legacy/v2 user-facing workflows.
- Preserve the immutable source and always write a separate output.
- Do not read historical translations unless the user explicitly requests reuse.
- Do not install, discover, configure, or invoke LibreOffice automatically.
- Standard `.pptx` uses OOXML until final Microsoft PowerPoint verification.
- Translation deduplication never removes an occurrence or its verification obligation.
- Keep existing image-mask, engineering-line, protected-token, and editable-text quality gates.

---

### Task 1: One-pass OOXML inspection and risk classification

**Files:**
- Create: `formats/ppt/scripts/inspect_pptx_package.py`
- Create: `formats/ppt/tests/test_inspect_pptx_package.py`

**Interfaces:**
- Produces: `inspect_package(input_path: Path) -> dict`
- Produces inventory keys: `slides`, `occurrences`, `image_groups`, `risk_plan`, `source_sha256`, `metrics`

- [ ] **Step 1: Write failing tests for one-pass extraction**

```python
def test_inspect_extracts_occurrences_and_groups_duplicate_images(tmp_path):
    deck = build_fixture(tmp_path, repeated_text=True, duplicate_image=True)
    report = inspect_package(deck)
    assert len(report["occurrences"]) == 2
    assert len(report["image_groups"]) == 1
    assert len(report["image_groups"][0]["occurrences"]) == 2

def test_plain_text_box_does_not_make_deck_complex(tmp_path):
    report = inspect_package(build_fixture(tmp_path, plain_text=True))
    assert report["risk_plan"]["route"] == "fast"
```

- [ ] **Step 2: Run tests and confirm missing-module failure**

Run: `python -m pytest -q formats/ppt/tests/test_inspect_pptx_package.py`

- [ ] **Step 3: Implement the minimal package scanner**

```python
def inspect_package(input_path: Path) -> dict:
    source_hash = sha256_file(input_path)
    with ZipFile(input_path) as package:
        occurrences = extract_text_occurrences(package)
        image_groups = group_images_by_sha256(package)
        risk_plan = classify_risk(package, occurrences, image_groups)
    return build_inventory(source_hash, occurrences, image_groups, risk_plan)
```

- [ ] **Step 4: Run the new inspection tests**

- [ ] **Step 5: Commit**

```powershell
git add formats/ppt/scripts/inspect_pptx_package.py formats/ppt/tests/test_inspect_pptx_package.py
git commit -m "feat(ppt): inspect presentations in one OOXML pass"
```

### Task 2: Schema-v2 manifest, safe deduplication, and resumable state

**Files:**
- Create: `formats/ppt/scripts/ppt_pipeline.py`
- Modify: `formats/ppt/scripts/validate_manifest.py`
- Create: `formats/ppt/tests/test_ppt_pipeline.py`
- Modify: `formats/ppt/tests/test_skill_contract.py`

**Interfaces:**
- Produces CLI commands: `inspect`, `prepare`, `apply`, `verify`, `render`
- Produces: `safe_reuse_key(occurrence: dict, target_language: str) -> str`
- Produces: `build_translation_manifest(inventory: dict, target_language: str) -> dict`
- Produces: `job-state.json`, `inventory.json`, `translation-manifest.json`

- [ ] **Step 1: Write failing tests for safe reuse and invalidation**

```python
def test_same_text_and_context_reuses_one_unit():
    manifest = build_translation_manifest(inventory_with_safe_repeat(), "en")
    assert len(manifest["occurrences"]) == 2
    assert len(manifest["translation_units"]) == 1

def test_same_short_text_in_different_roles_stays_separate():
    manifest = build_translation_manifest(inventory_with_ambiguous_repeat(), "en")
    assert len(manifest["translation_units"]) == 2
```

- [ ] **Step 2: Run tests and confirm schema-v1 behavior fails them**

- [ ] **Step 3: Implement the pipeline state machine and schema-v2 builder**

```python
STAGES = ("preflight", "inspect", "prepare", "translate", "validate", "apply", "verify", "render", "deliver")

def safe_reuse_key(item: dict, target_language: str) -> str:
    payload = [item["source_text"], target_language, item["role"], item["context_signature"], item["protected_tokens"]]
    return sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
```

- [ ] **Step 4: Replace the validator contract with schema v2**

- [ ] **Step 5: Run pipeline and manifest tests**

- [ ] **Step 6: Commit**

```powershell
git add formats/ppt/scripts/ppt_pipeline.py formats/ppt/scripts/validate_manifest.py formats/ppt/tests/test_ppt_pipeline.py formats/ppt/tests/test_skill_contract.py
git commit -m "feat(ppt): add resumable deduplicated pipeline"
```

### Task 3: Relevant-term glossary lookup

**Files:**
- Modify: `formats/ppt/scripts/resolve_repo_glossary.py`
- Modify: `formats/ppt/tests/test_repo_glossary.py`

**Interfaces:**
- Produces: `lookup_terms(texts: list[str], repo_root: Path | None = None) -> dict`
- CLI accepts repeated `--text` and optional `--texts-json`

- [ ] **Step 1: Write failing tests for exact and longest contained matches**

```python
def test_lookup_returns_only_relevant_terms(tmp_path):
    result = lookup_terms(["Rotary kiln drive system"], repo_root=tmp_path)
    assert result["matched_entries"]
    assert all(entry["source"] in "Rotary kiln drive system" for entry in result["matched_entries"])
```

- [ ] **Step 2: Implement one glossary parse and task-local matching**

- [ ] **Step 3: Run glossary tests and commit**

```powershell
git add formats/ppt/scripts/resolve_repo_glossary.py formats/ppt/tests/test_repo_glossary.py
git commit -m "feat(ppt): retrieve only relevant glossary terms"
```

### Task 4: One-write OOXML and optimized complex COM mutation

**Files:**
- Modify: `formats/ppt/scripts/pptx_ooxml.py`
- Modify: `formats/ppt/scripts/ppt_com.ps1`
- Modify: `formats/ppt/tests/test_pptx_ooxml.py`
- Create: `formats/ppt/tests/test_com_pipeline_contract.py`

**Interfaces:**
- `pptx_ooxml.py apply` consumes schema-v2 occurrences plus translation units.
- COM mutation indexes shapes once per slide and calls fit once per changed shape.

- [ ] **Step 1: Write failing tests for schema-v2 apply and one-fit-per-shape contract**

```python
def test_apply_resolves_many_occurrences_from_one_translation_unit(self):
    summary = apply_manifest(self.input, self.manifest_v2, self.output)
    assert summary == {"occurrences": 2, "translation_units": 1, "replaced": 2}
```

- [ ] **Step 2: Extend OOXML apply without retaining a separate schema-v1 production path**

- [ ] **Step 3: Replace COM per-target lookup with per-slide shape indexing**

- [ ] **Step 4: Move overflow fitting after all paragraphs in a shape are written**

- [ ] **Step 5: Run OOXML and COM contract tests**

- [ ] **Step 6: Commit**

```powershell
git add formats/ppt/scripts/pptx_ooxml.py formats/ppt/scripts/ppt_com.ps1 formats/ppt/tests/test_pptx_ooxml.py formats/ppt/tests/test_com_pipeline_contract.py
git commit -m "perf(ppt): write translations once per presentation"
```

### Task 5: Microsoft PowerPoint verification and risk-driven rendering

**Files:**
- Create: `scripts/office_com_pdf.ps1`
- Modify: `formats/ppt/scripts/ppt_pipeline.py`
- Create: `formats/ppt/tests/test_render_plan.py`
- Modify: `tests/test_skill_structure.py`

**Interfaces:**
- `office_com_pdf.ps1 -Application powerpoint` opens the final file and exports one official PDF.
- Produces: `verification.json`, `render-plan.json`, `final.pdf`, `final-renders/`

- [ ] **Step 1: Write failing tests for fast, complex, and strict render plans**

```python
def test_fast_plan_uses_final_thumbnail_overview_only():
    plan = build_render_plan(fast_inventory(), verification_passed=True)
    assert plan["source_pages"] == []
    assert plan["target_low_resolution"] == "all"
    assert plan["target_high_resolution"] == []
```

- [ ] **Step 2: Port the reviewed PowerPoint PDF export implementation**

- [ ] **Step 3: Implement deterministic verification and strict escalation**

- [ ] **Step 4: Render all final slides at low resolution and only risk slides at high resolution**

- [ ] **Step 5: Run render-plan and root contract tests**

- [ ] **Step 6: Commit**

```powershell
git add scripts/office_com_pdf.ps1 formats/ppt/scripts/ppt_pipeline.py formats/ppt/tests/test_render_plan.py tests/test_skill_structure.py
git commit -m "feat(ppt): verify with Microsoft PowerPoint by risk"
```

### Task 6: Replace old PPT instructions with the single pipeline

**Files:**
- Modify: `formats/ppt/SKILL.md`
- Modify: `formats/ppt/references/powerpoint-workflow.md`
- Create: `formats/ppt/references/pipeline-cli.md`
- Modify: `formats/ppt/references/manifest-schema.md`
- Modify: `formats/ppt/references/image-text-localization.md`
- Modify: `formats/ppt/scripts/validate_skill.py`
- Modify: `formats/ppt/tests/test_glossary_layout_contract.py`
- Modify: `formats/ppt/tests/test_skill_contract.py`

**Interfaces:**
- The only documented production entry is `python scripts/ppt_pipeline.py <stage> ...`.
- `ppt_com.ps1` and `pptx_ooxml.py` are internal adapters called by the pipeline.

- [ ] **Step 1: Write failing contract tests rejecting the old command-composition workflow**

```python
def test_skill_exposes_only_the_pipeline_entry():
    text = SKILL.read_text(encoding="utf-8")
    assert "scripts/ppt_pipeline.py" in text
    assert "without deduplicating" not in text
    assert "render every slide at 2x" not in text
```

- [ ] **Step 2: Replace, not append to, PPT instructions and references**

- [ ] **Step 3: Document exact commands, artifacts, exits, and resume rules**

- [ ] **Step 4: Run all PPT contract tests and commit**

```powershell
git add formats/ppt/SKILL.md formats/ppt/references formats/ppt/scripts/validate_skill.py formats/ppt/tests
git commit -m "docs(ppt): replace legacy workflow with balanced pipeline"
```

### Task 7: Full regression and performance gate

**Files:**
- Modify only files required by failures proven during this task.

**Interfaces:**
- Produces a non-committed benchmark report containing stage durations, COM starts, presentation opens, full-deck passes, occurrence count, translation-unit count, and image dedup ratio.

- [ ] **Step 1: Run all PPT tests**

Run: `python -m pytest -q --import-mode=importlib formats/ppt/tests`

- [ ] **Step 2: Run root routing and structure tests**

Run: `python -m pytest -q --import-mode=importlib tests`

- [ ] **Step 3: Run Skill validation**

Run: `python C:/Users/Administrator/.codex/skills/.system/skill-creator/scripts/quick_validate.py D:/AGICO-office-tanslates-pro`

- [ ] **Step 4: Benchmark one ordinary, one table-heavy, and one complex local PPT without reading or reusing historical translations**

- [ ] **Step 5: Confirm acceptance gates**

Expected: ordinary `.pptx` has no source full render, one final Office export, at most one post-translation PowerPoint start, 100% occurrence coverage, and at least 30% end-to-end improvement against the recorded baseline.

- [ ] **Step 6: Commit any verified final adjustments**

If no adjustment is required, create no commit. If a failing regression test proves an adjustment is required, stage only the exact implementation and test files changed for that failure, then commit with `test(ppt): enforce balanced pipeline performance gates`.
