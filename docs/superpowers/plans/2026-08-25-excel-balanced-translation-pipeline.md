# Excel Balanced Translation Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a resumable Excel translation pipeline that safely reuses repeated translations, avoids redundant rendering and image review, and automatically falls back to strict verification when workbook risk is high.

**Architecture:** Keep `route_excel_file.py` as the container gate. Add one public artifact-tool entry point, `excel_pipeline.mjs`, with `inspect`, `prepare`, `apply`, `verify`, and `render` commands. Translation remains a manifest-filling step performed by Codex/GPT; deterministic scripts own inventory, deduplication, mutation, state, verification, image grouping, and render planning.

**Tech Stack:** Python 3.12 standard library, JavaScript ES modules, Node.js 22+, `@oai/artifact-tool` 2.8.6+, Python `unittest`/pytest, Node `node:test`, OOXML ZIP/XML inspection.

**Spec:** `docs/superpowers/specs/2026-08-25-excel-balanced-translation-pipeline-design.md`

## Global Constraints

- Modify only `formats/excel/**` plus this plan; do not modify PDF, Word, PowerPoint, image adapters, or the shared glossary.
- Use the loader-provided Node.js, Python, and `@oai/artifact-tool`; do not install or substitute spreadsheet libraries.
- Preserve the current strict workflow as the fallback path.
- Keep `.xlsm`, VBA-bearing workbooks, unsafe legacy conversions, and unsupported complex bilingual workbooks on the strict path.
- Never overwrite the source workbook.
- Preserve formulas, numeric values, model codes, units, standards, URLs, identifiers, merges, sheet order, and source file hash.
- Implement every behavior with RED-GREEN-REFACTOR and commit each task independently.
- Use these current runtime executables for plan commands:
  - Python: `C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`
  - Node: `C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe`

## File Map

- Create `formats/excel/scripts/excel_pipeline.mjs`: the only public pipeline CLI; exports pure planning/state helpers for tests and runs artifact-tool workbook stages.
- Create `formats/excel/scripts/inspect_excel_package.py`: internal OOXML feature and image relationship inspector used by the pipeline.
- Create `formats/excel/tests/test_excel_pipeline.mjs`: Node tests for safe deduplication, state invalidation, render planning, strict escalation, inspection, mutation, and resume behavior.
- Create `formats/excel/tests/test_inspect_excel_package.py`: Python tests for OOXML feature detection, image hashing, and image occurrence grouping.
- Modify `formats/excel/scripts/validate_manifest.py`: accept legacy manifests and schema v2 two-layer manifests.
- Modify `formats/excel/tests/test_validate_manifest.py`: test v2 location coverage, translation references, protected tokens, and image groups.
- Create `formats/excel/references/pipeline-cli.md`: exact CLI, state, inventory, and resume contract.
- Modify `formats/excel/references/manifest-schema.md`: document schema v2 and legacy compatibility.
- Modify `formats/excel/references/excel-workflow.md`: replace unconditional full-cost steps with balanced/strict routing.
- Modify `formats/excel/references/image-text-localization.md`: review unique image hashes rather than each image occurrence.
- Modify `formats/excel/references/bilingual-row-layout.md`: define grid-safe fast path and strict fallback.
- Modify `formats/excel/SKILL.md`: route all Excel work through the standard pipeline and load only conditional references.
- Modify `formats/excel/tests/test_skill_contract.py`: enforce the new pipeline and prevent reintroduction of unconditional duplicate work.

---

### Task 1: Manifest v2 With Complete Location Coverage

**Files:**
- Modify: `formats/excel/scripts/validate_manifest.py`
- Modify: `formats/excel/tests/test_validate_manifest.py`
- Modify: `formats/excel/references/manifest-schema.md`

**Interfaces:**
- Consumes: legacy `{items, images}` manifests and schema v2 manifests.
- Produces: `validate(payload: Any) -> dict` with counts for `occurrences`, `translation_units`, and `images` when `schema_version == 2`.

- [ ] **Step 1: Write the failing schema v2 coverage test**

Add this test to `test_validate_manifest.py`:

```python
def test_accepts_v2_manifest_with_two_occurrences_reusing_one_translation(self):
    payload = {
        "schema_version": 2,
        "source_file": "sample.xlsx",
        "source_sha256": "a" * 64,
        "target_language": "en",
        "output_mode": "monolingual",
        "occurrences": [
            {"id": "S1!A1", "kind": "cell", "sheet": "S1", "address": "A1",
             "source": "设备名称", "context_key": "cell:header:equipment",
             "protected_tokens": [], "translation_unit_id": "tu-001"},
            {"id": "S1!A8", "kind": "cell", "sheet": "S1", "address": "A8",
             "source": "设备名称", "context_key": "cell:header:equipment",
             "protected_tokens": [], "translation_unit_id": "tu-001"},
        ],
        "translation_units": [
            {"id": "tu-001", "source": "设备名称",
             "context_key": "cell:header:equipment", "protected_tokens": [],
             "translation": "Equipment Name", "status": "translated"}
        ],
        "images": [],
    }
    report = validate_manifest.validate(payload)
    self.assertTrue(report["passed"], report["errors"])
    self.assertEqual(2, report["counts"]["occurrences"])
    self.assertEqual(1, report["counts"]["translation_units"])
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q formats\excel\tests\test_validate_manifest.py
```

Expected: FAIL because schema v2 fields are not recognized.

- [ ] **Step 3: Add failing rejection tests**

Add cases that reject an unknown `translation_unit_id`, duplicate occurrence ID, changed protected token, mismatched source/context between occurrence and translation unit, and invalid image reason code.

```python
bad = deepcopy(payload)
bad["occurrences"][1]["translation_unit_id"] = "missing"
report = validate_manifest.validate(bad)
self.assertFalse(report["passed"])
self.assertIn("unknown translation_unit_id", " ".join(report["errors"]))
```

- [ ] **Step 4: Implement the minimal v2 validator**

In `validate_manifest.py`, branch at the start of `validate`:

```python
def validate(payload: Any) -> dict:
    if isinstance(payload, dict) and payload.get("schema_version") == 2:
        return validate_v2(payload)
    return validate_legacy(payload)
```

Implement `validate_v2` with exact ID uniqueness, reference integrity, source/context/protected-token equality, translated/retain status checks, and image reason codes `no-source-text`, `logo-or-brand`, `photograph`, `localized`, and `manual-review`.

- [ ] **Step 5: Run validator tests and verify GREEN**

Run the Task 1 test command. Expected: all tests PASS.

- [ ] **Step 6: Document the exact v2 JSON shape**

Replace the primary example in `manifest-schema.md` with the tested structure and retain a final section stating that schema-less `{items, images}` manifests remain readable but new jobs must emit schema v2.

- [ ] **Step 7: Commit**

```powershell
git add -- formats/excel/scripts/validate_manifest.py formats/excel/tests/test_validate_manifest.py formats/excel/references/manifest-schema.md
git commit -m "feat(excel): add location-safe manifest v2"
```

---

### Task 2: Safe Translation Deduplication

**Files:**
- Create: `formats/excel/scripts/excel_pipeline.mjs`
- Create: `formats/excel/tests/test_excel_pipeline.mjs`

**Interfaces:**
- Consumes: `Occurrence[]` with `id`, `kind`, `source`, `context_key`, and `protected_tokens`.
- Produces: `buildTranslationUnits(occurrences) -> {occurrences, translation_units}`.

- [ ] **Step 1: Write the failing Node tests**

Create `test_excel_pipeline.mjs` with `node:test` cases proving that identical text and context reuse one unit, different contexts remain separate, and short ambiguous text with `context_key: "unknown"` remains separate.

```js
import assert from "node:assert/strict";
import test from "node:test";
import { buildTranslationUnits } from "../scripts/excel_pipeline.mjs";

test("reuses exact text only when context and protected tokens match", () => {
  const result = buildTranslationUnits([
    { id: "S1!A1", kind: "cell", source: "设备名称", context_key: "cell:header:equipment", protected_tokens: [] },
    { id: "S1!A8", kind: "cell", source: "设备名称", context_key: "cell:header:equipment", protected_tokens: [] },
    { id: "S2!C3", kind: "cell", source: "设备名称", context_key: "cell:note", protected_tokens: [] },
  ]);
  assert.equal(result.translation_units.length, 2);
  assert.equal(result.occurrences[0].translation_unit_id, result.occurrences[1].translation_unit_id);
  assert.notEqual(result.occurrences[0].translation_unit_id, result.occurrences[2].translation_unit_id);
});
```

- [ ] **Step 2: Run the Node tests and verify RED**

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' --test formats\excel\tests\test_excel_pipeline.mjs
```

Expected: FAIL because `excel_pipeline.mjs` does not exist.

- [ ] **Step 3: Implement deterministic deduplication**

Export `buildTranslationUnits`. Use a SHA-256 ID derived from exact source text, kind, context key, and the ordered protected-token array. Do not normalize meaningful newlines or punctuation. Append the occurrence ID to the key when context is missing or `unknown`.

```js
export function translationReuseKey(item) {
  const contextual = item.context_key && item.context_key !== "unknown";
  const base = JSON.stringify([item.source, item.kind, item.context_key, item.protected_tokens]);
  return contextual ? base : `${base}\u0000${item.id}`;
}
```

- [ ] **Step 4: Run Node tests and verify GREEN**

Run the Task 2 Node command. Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add -- formats/excel/scripts/excel_pipeline.mjs formats/excel/tests/test_excel_pipeline.mjs
git commit -m "feat(excel): safely reuse repeated translations"
```

---

### Task 3: OOXML Risk Inventory and Unique Image Groups

**Files:**
- Create: `formats/excel/scripts/inspect_excel_package.py`
- Create: `formats/excel/tests/test_inspect_excel_package.py`

**Interfaces:**
- Consumes: a verified `.xlsx` path and optional extraction directory.
- Produces: `inspect_package(path, extract_dir=None) -> {features, images}`.
- Image item: `{sha256, media_path, extension, occurrence_count, sheets, extracted_path}`.

- [ ] **Step 1: Write failing tests using temporary OOXML ZIP packages**

Build minimal packages inside `TemporaryDirectory` with `zipfile.ZipFile`. Test no-media output, two relationships to identical media grouped once, distinct images grouped separately, and detection of charts, comments, external links, drawings, and `xl/vbaProject.bin`.

```python
def test_groups_identical_image_bytes_once(self):
    workbook = self.make_package(
        media={"xl/media/image1.png": b"same", "xl/media/image2.png": b"same"},
        sheet_image_targets={"Sheet1": ["../media/image1.png", "../media/image2.png"]},
    )
    report = inspect_package(workbook)
    self.assertEqual(1, len(report["images"]))
    self.assertEqual(2, report["images"][0]["occurrence_count"])
```

- [ ] **Step 2: Run the Python test and verify RED**

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q formats\excel\tests\test_inspect_excel_package.py
```

Expected: FAIL because the inspector does not exist.

- [ ] **Step 3: Implement package inspection with standard library only**

Parse `[Content_Types].xml`, `xl/workbook.xml`, workbook relationships, worksheet relationships, drawing relationships, and `xl/media/*`. Hash media bytes with SHA-256, group occurrences by digest, and extract one file per digest when `extract_dir` is provided. Return Boolean/count features without mutating the workbook.

- [ ] **Step 4: Run tests and verify GREEN**

Run the Task 3 command. Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add -- formats/excel/scripts/inspect_excel_package.py formats/excel/tests/test_inspect_excel_package.py
git commit -m "feat(excel): inventory workbook risks and unique images"
```

---

### Task 4: Balanced Render Plan and Strict Escalation

**Files:**
- Modify: `formats/excel/scripts/excel_pipeline.mjs`
- Modify: `formats/excel/tests/test_excel_pipeline.mjs`

**Interfaces:**
- Produces: `classifyRisk(meta) -> {mode: "balanced"|"strict", reasons: string[]}`.
- Produces: `buildRenderPlan({phase, outputMode, sheets, changedSheets, risk}) -> RenderPlan`.

- [ ] **Step 1: Write failing risk and render tests**

Cover these exact behaviors:

- `.xlsm` or `has_vba` returns strict.
- charts, comments, unsupported drawings, file repair, or unsafe legacy conversion return strict.
- ordinary images alone do not force strict.
- preflight renders each visible used sheet once.
- monolingual final renders changed/risk sheets only.
- bilingual final renders all printed pages.

```js
test("monolingual final render contains only changed sheets", () => {
  const plan = buildRenderPlan({
    phase: "final", outputMode: "monolingual",
    sheets: [{ name: "A", visible: true }, { name: "B", visible: true }],
    changedSheets: ["B"], risk: { mode: "balanced", reasons: [] },
  });
  assert.deepEqual(plan.sheets.map((x) => x.name), ["B"]);
  assert.equal(plan.fullPrintPages, false);
});
```

- [ ] **Step 2: Run Node tests and verify RED**

Run the Task 2 Node command. Expected: FAIL on missing exports.

- [ ] **Step 3: Implement the pure planners**

Use stable reason codes: `macro`, `unsafe-legacy-conversion`, `chart`, `comment`, `unsupported-drawing`, `repair-warning`, `formula-change`, `merge-change`, `protected-token-change`, `image-uncertain`, and `state-hash-mismatch`.

- [ ] **Step 4: Run Node tests and verify GREEN**

Run the Task 2 Node command. Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add -- formats/excel/scripts/excel_pipeline.mjs formats/excel/tests/test_excel_pipeline.mjs
git commit -m "feat(excel): add risk-aware rendering plan"
```

---

### Task 5: Resumable Job State

**Files:**
- Modify: `formats/excel/scripts/excel_pipeline.mjs`
- Modify: `formats/excel/tests/test_excel_pipeline.mjs`

**Interfaces:**
- Produces: `newJobState(config)`, `completeStage(state, stage, artifactHashes)`, `invalidateFrom(state, stage)`, and `nextStage(state)`.
- Stage order: `preflight`, `inspect`, `prepare`, `translate`, `validate`, `apply`, `verify`, `render`, `deliver`.

- [ ] **Step 1: Write failing state tests**

Test ordered completion, rejection of skipped stages, resume from the first incomplete stage, downstream invalidation when a stage hash changes, and full invalidation when source hash/target language/output mode changes.

```js
test("changing prepare hash invalidates prepare and all later stages", () => {
  let state = newJobState({ sourceSha256: "a".repeat(64), targetLanguage: "en", outputMode: "monolingual" });
  state = completeStage(state, "preflight", { report: "p1" });
  state = completeStage(state, "inspect", { inventory: "i1" });
  state = completeStage(state, "prepare", { manifest: "m1" });
  state = invalidateFrom(state, "prepare");
  assert.deepEqual(state.completedStages, ["preflight", "inspect"]);
});
```

- [ ] **Step 2: Run Node tests and verify RED**

Run the Node test command. Expected: FAIL on missing state exports.

- [ ] **Step 3: Implement immutable state helpers and atomic JSON save**

Write state to a sibling temporary file, close it, then rename it to `job-state.json`. Store schema version, source hash, target language, output mode, completed stages, artifact hashes, output paths, counts, and strict reasons.

- [ ] **Step 4: Run Node tests and verify GREEN**

Run the Node test command. Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add -- formats/excel/scripts/excel_pipeline.mjs formats/excel/tests/test_excel_pipeline.mjs
git commit -m "feat(excel): resume translation jobs by verified stage"
```

---

### Task 6: Artifact-Tool Inspect, Prepare, and Monolingual Apply

**Files:**
- Modify: `formats/excel/scripts/excel_pipeline.mjs`
- Modify: `formats/excel/tests/test_excel_pipeline.mjs`

**Interfaces:**
- CLI: `inspect --input <xlsx> --job-dir <dir> --target-language <lang> --output-mode monolingual|bilingual`.
- CLI: `prepare --job-dir <dir>`.
- CLI: `apply --input <xlsx> --job-dir <dir> --output <xlsx>`.
- Produces: `inventory.json`, `manifest.json`, baseline renders, translated workbook, and updated state.

- [ ] **Step 1: Write a failing integration test that builds a real workbook**

Use artifact-tool to create `S1` with repeated text, numbers, and a formula. Invoke `inspect`, then `prepare`, fill each translation unit, invoke `apply`, reopen the output, and assert both repeated cells are translated while the number and formula remain unchanged.

```js
assert.equal(out.worksheets.getItem("S1").getRange("A2").values[0][0], "Equipment Name");
assert.equal(out.worksheets.getItem("S1").getRange("A8").values[0][0], "Equipment Name");
assert.equal(out.worksheets.getItem("S1").getRange("B2").values[0][0], 15);
assert.equal(out.worksheets.getItem("S1").getRange("C2").formulas[0][0], "=B2*2");
```

- [ ] **Step 2: Run Node tests and verify RED**

Expected: CLI stage failure because inspect/apply are not implemented.

- [ ] **Step 3: Implement `inspect`**

Import once with `FileBlob.load` and `SpreadsheetFile.importXlsx`. Get sheet records through `workbook.inspect({kind: "sheet", include: "id,name"})`, read each used range, skip formula/numeric/date/Boolean cells, create stable cell occurrences, infer a conservative context key from object kind plus nearest column header, write `inventory.json`, render one used-range preview per visible sheet, and complete only the `inspect` stage.

- [ ] **Step 4: Implement `prepare`**

Read `inventory.json`, call `buildTranslationUnits`, merge the OOXML feature/image report, write an untranslated schema v2 `manifest.json`, and complete `prepare`. Exit with code 3 and `next_stage: "translate"`; this is the intentional pause where Codex/GPT fills each `translation_units[].translation` and changes its status to `translated` or `retain`.

- [ ] **Step 5: Implement `apply`**

Validate schema v2 before mutation. Import the source once, resolve every occurrence's translation unit, write only target text cells, export once to the requested output, and update state only after the output saves successfully.

- [ ] **Step 6: Run Node integration tests and verify GREEN**

Run the Node test command. Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add -- formats/excel/scripts/excel_pipeline.mjs formats/excel/tests/test_excel_pipeline.mjs
git commit -m "feat(excel): inspect and apply translations in one workbook session"
```

---

### Task 7: Grid-Safe Blue-Row Bilingual Apply

**Files:**
- Modify: `formats/excel/scripts/excel_pipeline.mjs`
- Modify: `formats/excel/tests/test_excel_pipeline.mjs`
- Modify: `formats/excel/references/bilingual-row-layout.md`

**Interfaces:**
- Produces: `classifyBilingualGrid(meta) -> {safe: boolean, reasons: string[]}`.
- Produces: bilingual output with one source row followed by one translation row.

- [ ] **Step 1: Write failing grid-safety tests**

Accept plain cell grids with styles, merges, formulas, and print settings. Reject VBA, tables, charts, comments, unsupported drawings, external links, and uncertain image text. A rejected workbook must return strict mode without creating partial output.

- [ ] **Step 2: Write a failing bilingual workbook integration test**

Create a two-row technical table with a merged heading, identifier with leading zero, quantity, and total formula. Assert the output has exactly four paired rows, blue translation styling, blank numeric translation cells, duplicated merges, text identifier preserved as text on the source row, and a total formula mapped only to source rows.

- [ ] **Step 3: Run Node tests and verify RED**

Expected: FAIL because the bilingual builder does not exist.

- [ ] **Step 4: Implement controlled worksheet rebuild**

Because artifact-tool has no ordinary worksheet-row insertion API, create a new workbook for grid-safe bilingual workbooks. Copy source values/formulas, essential styles, dimensions, merges, freeze panes, print settings, and sheet order into doubled row coordinates. Add translation rows using fill `#EAF2F8`, font color `#1F4E78`, italic Arial, source-aligned horizontal alignment, wrap text, and paired borders. Remap formulas through an explicit old-row to new-source-row map; never copy numeric data or formulas into translation rows.

- [ ] **Step 5: Run bilingual tests and verify GREEN**

Run the Node test command. Expected: PASS and no formula errors in the reopened output.

- [ ] **Step 6: Update bilingual reference with the tested safety boundary**

State that the fast rebuild path is allowed only when `classifyBilingualGrid` passes; otherwise use strict processing. Preserve the existing blue-row visual values unchanged.

- [ ] **Step 7: Commit**

```powershell
git add -- formats/excel/scripts/excel_pipeline.mjs formats/excel/tests/test_excel_pipeline.mjs formats/excel/references/bilingual-row-layout.md
git commit -m "feat(excel): add safe blue-row bilingual pipeline"
```

---

### Task 8: Verification, Unique Image Review, and Final Rendering

**Files:**
- Modify: `formats/excel/scripts/excel_pipeline.mjs`
- Modify: `formats/excel/tests/test_excel_pipeline.mjs`
- Modify: `formats/excel/references/image-text-localization.md`

**Interfaces:**
- CLI: `verify --source <xlsx> --job-dir <dir> --output <xlsx>`.
- CLI: `render --job-dir <dir> --output <xlsx>`.
- Produces: `verification.json`, `render-plan.json`, final PNG renders, and strict escalation reasons.

- [ ] **Step 1: Write failing verification tests**

Test detection of changed formula, changed numeric value, broken merge, missing occurrence, protected-token loss, untranslated source text, incomplete bilingual pair, and output open failure. Test that clean workbooks pass.

- [ ] **Step 2: Write failing image-plan tests**

Test no-image skip, duplicate image hash reviewed once, all occurrences retained, allowed automatic reason codes, and `manual-review`/uncertain image escalation.

- [ ] **Step 3: Run tests and verify RED**

Run Python package-inspector tests and Node pipeline tests. Expected: FAIL on missing verify/render behavior.

- [ ] **Step 4: Implement verification**

Reopen source and output once each. Compare source hash, sheet order, formulas, numeric/Boolean/date values, merges, protected tokens, translation coverage, and bilingual invariants. Run feature-specific checks only when the preflight inventory reports the feature. Write stable reason codes to `verification.json`.

- [ ] **Step 5: Implement unique image review state**

Populate one image record per SHA-256 group. Store all occurrence locations, classification, reason code, and status. Skip the image stage when the package inspector returns zero images. Require deep review only for `localized` and `manual-review` groups.

- [ ] **Step 6: Implement final rendering**

Use `buildRenderPlan` and `workbook.render`. Monolingual balanced jobs render changed/risk sheets. Bilingual jobs render every changed visible sheet at full used-range coverage and retain the existing complete print-page gate; if configured print pages cannot be proven by the artifact render, record `print-page-verification-required` and upgrade that render stage to strict. Save renders under `job-dir/final-renders` and complete `render` only after all planned files exist.

- [ ] **Step 7: Run tests and verify GREEN**

Expected: all Python and Node Excel tests PASS.

- [ ] **Step 8: Commit**

```powershell
git add -- formats/excel/scripts/excel_pipeline.mjs formats/excel/tests/test_excel_pipeline.mjs formats/excel/references/image-text-localization.md
git commit -m "feat(excel): verify outputs with risk-based image and render gates"
```

---

### Task 9: Route the Skill Through the Standard Pipeline

**Files:**
- Create: `formats/excel/references/pipeline-cli.md`
- Modify: `formats/excel/SKILL.md`
- Modify: `formats/excel/references/excel-workflow.md`
- Modify: `formats/excel/tests/test_skill_contract.py`

**Interfaces:**
- Documents exact commands and when to enter balanced or strict mode.
- Ensures future agents do not recreate job-specific builders or unconditional full-cost checks.

- [ ] **Step 1: Write failing Skill contract tests**

Require `scripts/excel_pipeline.mjs`, `references/pipeline-cli.md`, the ordered commands, safe dedup language, image-hash reuse, resumable state, conditional rendering, and strict escalation. Reject the old phrases `do not deduplicate repeated text`, `Review every image`, and unconditional `render every final sheet and print area`.

- [ ] **Step 2: Run contract tests and verify RED**

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q formats\excel\tests\test_skill_contract.py
```

Expected: FAIL because the current Skill still encodes the old workflow.

- [ ] **Step 3: Write `pipeline-cli.md`**

Document exact `inspect`, `prepare`, `apply`, `verify`, and `render` commands, required files, state transitions, translation pause, resume rules, and strict reason codes. Use `work/<source-stem>-<hash-prefix>/` as the job directory.

- [ ] **Step 4: Simplify `SKILL.md` and `excel-workflow.md`**

Make the fixed pipeline the only default Excel path. Keep the non-negotiable quality gates in `SKILL.md`; move schema/state details to the new reference. Load bilingual and image references only when their observable feature is present.

- [ ] **Step 5: Run contract and full Excel tests**

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q --import-mode=importlib tests formats\excel\tests
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' --test formats\excel\tests\test_excel_pipeline.mjs
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```powershell
git add -- formats/excel/SKILL.md formats/excel/references/excel-workflow.md formats/excel/references/pipeline-cli.md formats/excel/tests/test_skill_contract.py
git commit -m "docs(excel): route translations through the balanced pipeline"
```

---

### Task 10: Real-File Benchmark and Release Gate

**Files:**
- Modify only if a verified defect is found: files already listed in Tasks 1-9.
- Do not commit: customer workbooks, renders, manifests, job state, or benchmark outputs.

**Interfaces:**
- Produces a local comparison report with baseline/optimized time, occurrence count, translation-unit count, image occurrence/group count, render count, and verification result.

- [ ] **Step 1: Record the current strict baseline**

Use three existing local samples without adding them to Git: ordinary `.xlsx`, converted `.xls` blue-row bilingual table, and a formula/merge-heavy workbook. Record total duration, translation tasks, image reviews, renders, and quality results.

- [ ] **Step 2: Run the optimized pipeline on immutable copies**

Use identical target language and output mode. Do not reuse previous translations or manifests. Store all benchmark artifacts under ignored `work/`.

- [ ] **Step 3: Compare quality invariants**

Require zero source modification, zero formula/numeric/protected-token changes, zero broken merges, complete position coverage, complete bilingual pairs, no unexpected source text, successful reopen, and clean required renders.

- [ ] **Step 4: Evaluate the performance gate**

Require at least 30% total-time reduction for the ordinary sample. For other samples, require reduced duplicate translation/image/render work without quality regression; strict fallback is acceptable when risk triggers are present.

- [ ] **Step 5: Run Skill validation and the complete Excel/root suite**

```powershell
$env:PYTHONUTF8='1'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' 'C:\Users\Administrator\.codex\skills\.system\skill-creator\scripts\quick_validate.py' 'D:\AGICO-office-tanslates-pro'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q --import-mode=importlib tests formats\excel\tests
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' --test formats\excel\tests\test_excel_pipeline.mjs
git diff --check
```

Expected: Skill valid, all tests PASS, no whitespace errors.

- [ ] **Step 6: Review scope and commit any benchmark-discovered fix separately**

Confirm `git diff --name-only` contains no PDF, Word, PowerPoint, image adapter, glossary, customer workbook, or generated artifact. If a defect required a fix, repeat its RED-GREEN cycle and commit only that fix; otherwise create no benchmark commit.
