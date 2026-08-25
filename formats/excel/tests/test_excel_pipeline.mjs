import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

import {
  buildImageReviewPlan,
  buildTranslationUnits,
  JOB_STAGES,
  classifyRisk,
  classifyBilingualGrid,
  completeStage,
  applyTranslations,
  applySafeAutofill,
  estimateTranslatedRowHeight,
  shouldWrapTranslatedText,
  findCompressibleBlankRows,
  verticalMergeRows,
  invalidateFrom,
  inspectWorkbook,
  newJobState,
  nextStage,
  prepareManifest,
  reconcileJobState,
  officeValidateOutput,
  renderOccurrenceTranslation,
  saveJobState,
  translationReuseKey,
  verifyTranslations,
} from "../scripts/excel_pipeline.mjs";


function occurrence(overrides = {}) {
  return {
    id: "S1!A1",
    kind: "cell",
    sheet: "S1",
    address: "A1",
    source: "设备名称",
    context_key: "cell:header:equipment",
    protected_tokens: [],
    ...overrides,
  };
}


test("reuses exact text only when context and protected tokens match", () => {
  const result = buildTranslationUnits([
    occurrence(),
    occurrence({ id: "S1!A8", address: "A8" }),
    occurrence({ id: "S2!C3", sheet: "S2", address: "C3", context_key: "cell:note" }),
  ]);
  assert.equal(result.translation_units.length, 2);
  assert.equal(
    result.occurrences[0].translation_unit_id,
    result.occurrences[1].translation_unit_id,
  );
  assert.notEqual(
    result.occurrences[0].translation_unit_id,
    result.occurrences[2].translation_unit_id,
  );
});


test("does not reuse context-free ambiguous text", () => {
  const result = buildTranslationUnits([
    occurrence({ id: "S1!A1", source: "出口", context_key: "unknown" }),
    occurrence({ id: "S1!A2", address: "A2", source: "出口", context_key: "unknown" }),
  ]);
  assert.equal(result.translation_units.length, 2);
});


test("does not reuse text when protected token sets differ", () => {
  const result = buildTranslationUnits([
    occurrence({ source: "功率 45kW", protected_tokens: ["45kW"] }),
    occurrence({ id: "S1!A2", address: "A2", source: "功率 45kW", protected_tokens: [] }),
  ]);
  assert.equal(result.translation_units.length, 2);
});


test("translation unit ids are deterministic and preserve occurrence order", () => {
  const input = [
    occurrence({ id: "S1!A8", address: "A8" }),
    occurrence({ id: "S1!A1", address: "A1" }),
  ];
  const first = buildTranslationUnits(input);
  const second = buildTranslationUnits(input);
  assert.deepEqual(first, second);
  assert.deepEqual(first.occurrences.map((item) => item.id), ["S1!A8", "S1!A1"]);
  assert.match(first.translation_units[0].id, /^tu-[0-9a-f]{16}$/);
});


test("reuse key preserves meaningful newlines and punctuation", () => {
  assert.notEqual(
    translationReuseKey(occurrence({ source: "设备\n名称" })),
    translationReuseKey(occurrence({ source: "设备名称" })),
  );
  assert.notEqual(
    translationReuseKey(occurrence({ source: "设备名称：" })),
    translationReuseKey(occurrence({ source: "设备名称" })),
  );
});


test("macro stays strict while ordinary charts and comments are complex", () => {
  const risk = classifyRisk({
    extension: ".xlsm",
    features: {
      has_vba: true,
      chart_count: 1,
      comment_count: 1,
      unsupported_drawing_count: 1,
    },
  });
  assert.equal(risk.mode, "strict");
  assert.deepEqual(
    risk.reasons,
    ["macro", "chart", "comment", "unsupported-drawing"],
  );

  const complex = classifyRisk({
    extension: ".xlsx",
    features: { chart_count: 1, comment_count: 1 },
  });
  assert.equal(complex.mode, "complex");
  assert.deepEqual(complex.reasons, ["chart", "comment"]);
});

test("parameter rows translate the label once and preserve the technical value", () => {
  const result = buildTranslationUnits([
    occurrence({ id: "S1!A1", source: "功率：45kW", protected_tokens: ["45kW"] }),
    occurrence({ id: "S1!A2", address: "A2", source: "功率：90kW", protected_tokens: ["90kW"] }),
  ]);
  assert.equal(result.translation_units.length, 1);
  assert.equal(result.translation_units[0].source, "功率");
  assert.deepEqual(result.occurrences[0].translation_template, {
    separator: "：", suffix: "45kW",
  });
  assert.deepEqual(result.occurrences[1].translation_template, {
    separator: "：", suffix: "90kW",
  });
  result.translation_units[0].translation = "Puissance";
  assert.equal(
    renderOccurrenceTranslation(result.occurrences[1], result.translation_units[0]),
    "Puissance：90kW",
  );
});

test("natural-language sentences are not treated as parameter rows", () => {
  const result = buildTranslationUnits([
    occurrence({ source: "备注：设备由买方提供", protected_tokens: [] }),
  ]);
  assert.equal(result.translation_units[0].source, "备注：设备由买方提供");
  assert.equal(result.occurrences[0].translation_template, undefined);
});

test("safe English autofill resolves fixed labels units and identifiers only", () => {
  const units = [
    { source: "工程名称", translation: "", status: "pending" },
    { source: "台", translation: "", status: "pending" },
    { source: "SL2405-GS03", translation: "", status: "pending" },
    { source: "挡轮形式", translation: "", status: "pending" },
  ];
  const result = applySafeAutofill(units, "en");
  assert.deepEqual(units.map(({ translation, status }) => ({ translation, status })), [
    { translation: "Project Name", status: "translated" },
    { translation: "unit", status: "translated" },
    { translation: "SL2405-GS03", status: "retain" },
    { translation: "", status: "pending" },
  ]);
  assert.deepEqual(result, { fixed: 2, retained: 1, pending: 1 });
});

test("safe autofill does not apply English labels to another target language", () => {
  const units = [{ source: "工程名称", translation: "", status: "pending" }];
  assert.deepEqual(applySafeAutofill(units, "fr"), {
    fixed: 0, retained: 0, pending: 1,
  });
  assert.equal(units[0].status, "pending");
});

test("long translated text raises only the affected row height", () => {
  assert.equal(estimateTranslatedRowHeight({
    text: "To Be Ordered with the Equipment", columnWidth: 14, currentHeight: 18,
  }), 48);
  assert.equal(estimateTranslatedRowHeight({
    text: "Unit", columnWidth: 14, currentHeight: 18,
  }), 18);
  assert.equal(estimateTranslatedRowHeight({
    text: "Main Drive Speed: 0.16~1.62 r/min", columnWidth: 32, currentHeight: 18,
  }), 18);
  assert.equal(shouldWrapTranslatedText({
    text: "Preliminary Design", columnWidth: 11.5,
  }), true);
});

test("only runs of three or more completely blank rows are compressed", () => {
  const values = [["A"], [null], [null], [null], ["B"], [null], [null]];
  const formulas = values.map(() => [""]);
  assert.deepEqual(findCompressibleBlankRows(values, formulas, 10), [11, 12, 13]);
  formulas[2][0] = "=1";
  assert.deepEqual(findCompressibleBlankRows(values, formulas, 10), []);
});

test("horizontal merges do not block blank-row compression", () => {
  assert.deepEqual(verticalMergeRows([
    { startAddress: "B54", endAddress: "D54" },
    { startAddress: "A55", endAddress: "A56" },
  ]), new Set([55, 56]));
});

test("ordinary images use the fast path", () => {
  const risk = classifyRisk({
    extension: ".xlsx",
    features: { unique_image_count: 3, image_occurrence_count: 8 },
  });
  assert.deepEqual(risk, { mode: "fast", reasons: [] });
});


test("unsafe conversion repair warning and uncertain image force strict mode", () => {
  const risk = classifyRisk({
    extension: ".xlsx",
    unsafe_legacy_conversion: true,
    repair_warning: true,
    image_uncertain: true,
    features: {},
  });
  assert.deepEqual(risk.reasons, [
    "unsafe-legacy-conversion",
    "repair-warning",
    "image-uncertain",
  ]);
});


test("final stage validates in Excel without a PDF render stage", () => {
  assert.ok(JOB_STAGES.includes("office-validate"));
  assert.ok(!JOB_STAGES.includes("render"));
});


test("job state enforces stage order and reports next stage", () => {
  let state = newJobState({
    sourceSha256: "a".repeat(64),
    targetLanguage: "en",
    outputMode: "monolingual",
  });
  assert.equal(nextStage(state), "preflight");
  assert.throws(() => completeStage(state, "inspect", { inventory: "i1" }), /expected preflight/);
  state = completeStage(state, "preflight", { report: "p1" });
  assert.equal(nextStage(state), "inspect");
  assert.deepEqual(state.completedStages, ["preflight"]);
  assert.deepEqual(state.stageArtifacts.preflight, { report: "p1" });
});


test("invalidating a stage removes it and every downstream stage", () => {
  let state = newJobState({
    sourceSha256: "a".repeat(64),
    targetLanguage: "en",
    outputMode: "monolingual",
  });
  state = completeStage(state, "preflight", { report: "p1" });
  state = completeStage(state, "inspect", { inventory: "i1" });
  state = completeStage(state, "prepare", { manifest: "m1" });
  state = invalidateFrom(state, "prepare");
  assert.deepEqual(state.completedStages, ["preflight", "inspect"]);
  assert.deepEqual(Object.keys(state.stageArtifacts), ["preflight", "inspect"]);
  assert.equal(nextStage(state), "prepare");
});


test("changed source target or output mode starts a fresh job", () => {
  let state = newJobState({
    sourceSha256: "a".repeat(64),
    targetLanguage: "en",
    outputMode: "monolingual",
  });
  state = completeStage(state, "preflight", { report: "p1" });
  for (const config of [
    { sourceSha256: "b".repeat(64), targetLanguage: "en", outputMode: "monolingual" },
    { sourceSha256: "a".repeat(64), targetLanguage: "es", outputMode: "monolingual" },
    { sourceSha256: "a".repeat(64), targetLanguage: "en", outputMode: "bilingual" },
  ]) {
    const reconciled = reconcileJobState(state, config);
    assert.deepEqual(reconciled.completedStages, []);
    assert.equal(nextStage(reconciled), "preflight");
  }
});


test("job state is saved atomically as JSON", async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "excel-job-state-"));
  try {
    const destination = path.join(directory, "job-state.json");
    const state = newJobState({
      sourceSha256: "a".repeat(64),
      targetLanguage: "en",
      outputMode: "monolingual",
    });
    await saveJobState(destination, state);
    assert.deepEqual(JSON.parse(await fs.readFile(destination, "utf8")), state);
    assert.deepEqual(await fs.readdir(directory), ["job-state.json"]);
  } finally {
    await fs.rm(directory, { recursive: true, force: true });
  }
});


test("inspect prepare and apply translate text while preserving numbers and formulas", async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "excel-pipeline-"));
  try {
    const source = path.join(directory, "source.xlsx");
    const output = path.join(directory, "translated.xlsx");
    const jobDir = path.join(directory, "job");
    const workbook = Workbook.create();
    const sheet = workbook.worksheets.add("S1");
    sheet.getRange("A1:C2").values = [
      ["项目", "数值", "计算"],
      ["设备名称", 15, null],
    ];
    sheet.getRange("C2").formulas = [["=B2*2"]];
    const sourceBlob = await SpreadsheetFile.exportXlsx(workbook);
    await sourceBlob.save(source);
    const sourceBefore = await fs.readFile(source);

    const inspected = await inspectWorkbook({
      input: source,
      "job-dir": jobDir,
      "target-language": "en",
      "output-mode": "monolingual",
    });
    assert.equal(inspected.next_stage, "prepare");

    const prepared = await prepareManifest({ "job-dir": jobDir });
    assert.equal(prepared.next_stage, "translate");
    const relevantGlossary = JSON.parse(
      await fs.readFile(path.join(jobDir, "relevant-glossary.json"), "utf8"),
    );
    assert.equal(typeof relevantGlossary.matched_entries, "number");
    const manifestPath = path.join(jobDir, "translation-manifest.json");
    const manifest = JSON.parse(await fs.readFile(manifestPath, "utf8"));
    const unit = manifest.translation_units.find((item) => item.source === "设备名称");
    assert.ok(unit, "expected a translation unit for 设备名称");
    unit.translation = "Equipment Name";
    unit.status = "translated";
    for (const pending of manifest.translation_units.filter((item) => item.status === "pending")) {
      pending.translation = pending.source;
      pending.status = "retain";
      pending.reason = "test fixture";
    }
    await fs.writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");

    const applied = await applyTranslations({
      input: source, "job-dir": jobDir, output,
    });
    assert.equal(applied.next_stage, "verify");

    const result = await SpreadsheetFile.importXlsx(await FileBlob.load(output));
    const resultSheet = result.worksheets.items.find((item) => item.name === "S1");
    assert.equal(resultSheet.getRange("A2").values[0][0], "Equipment Name");
    assert.equal(resultSheet.getRange("B2").values[0][0], 15);
    assert.equal(resultSheet.getRange("C2").formulas[0][0], "=B2*2");
    assert.deepEqual(await fs.readFile(source), sourceBefore);

    const state = JSON.parse(await fs.readFile(path.join(jobDir, "job-state.json"), "utf8"));
    assert.deepEqual(state.completedStages, [
      "preflight", "inspect", "prepare", "translate", "validate", "apply",
    ]);

    const verification = await verifyTranslations({
      source, "job-dir": jobDir, output,
    });
    assert.equal(verification.passed, true, JSON.stringify(verification));
    const verifiedState = JSON.parse(await fs.readFile(path.join(jobDir, "job-state.json"), "utf8"));
    assert.equal(verifiedState.completedStages.at(-1), "verify");
    const officeValidated = await officeValidateOutput(
      { "job-dir": jobDir, output },
      () => ({
        passed: true,
        application: "Microsoft Excel",
        worksheets: ["S1"],
        formula_error_count: 0,
        value_error_count: 0,
      }),
    );
    assert.equal(officeValidated.passed, true);
    assert.equal(officeValidated.next_stage, "deliver");
  } finally {
    await fs.rm(directory, { recursive: true, force: true });
  }
});


test("image review plan skips empty workbooks and reviews duplicate bytes once", () => {
  assert.deepEqual(buildImageReviewPlan([]), {
    skipped: true, groups: [], deep_review_ids: [], strict_reasons: [],
  });
  const plan = buildImageReviewPlan([
    {
      id: "img-a", sha256: "a".repeat(64),
      occurrences: ["S1!drawing1", "S2!drawing4"],
      status: "retain", reason_code: "logo-or-brand",
    },
    {
      id: "img-b", sha256: "b".repeat(64),
      occurrences: ["S1!drawing2"],
      status: "manual-review", reason_code: "manual-review",
    },
  ]);
  assert.equal(plan.groups.length, 2);
  assert.deepEqual(plan.deep_review_ids, ["img-b"]);
  assert.deepEqual(plan.strict_reasons, ["image-manual-review"]);
});


test("verification reports changed formulas numbers merges and missing translations", async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "excel-verify-bad-"));
  try {
    const source = path.join(directory, "source.xlsx");
    const output = path.join(directory, "translated.xlsx");
    const jobDir = path.join(directory, "job");
    const workbook = Workbook.create();
    const sheet = workbook.worksheets.add("S1");
    sheet.getRange("A1:C2").values = [["标签", 4, null], ["合并", null, null]];
    sheet.getRange("C1").formulas = [["=B1*2"]];
    sheet.getRange("A2:B2").merge();
    await (await SpreadsheetFile.exportXlsx(workbook)).save(source);
    await inspectWorkbook({
      input: source, "job-dir": jobDir, "target-language": "en",
      "output-mode": "monolingual",
    });
    await prepareManifest({ "job-dir": jobDir });
    const manifestPath = path.join(jobDir, "translation-manifest.json");
    const manifest = JSON.parse(await fs.readFile(manifestPath, "utf8"));
    for (const unit of manifest.translation_units) {
      unit.translation = `EN:${unit.source}`;
      unit.status = "translated";
    }
    await fs.writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
    await applyTranslations({ input: source, "job-dir": jobDir, output });

    const damaged = await SpreadsheetFile.importXlsx(await FileBlob.load(output));
    const damagedSheet = damaged.worksheets.items[0];
    damagedSheet.getRange("A1").values = [["wrong"]];
    damagedSheet.getRange("B1").values = [[5]];
    damagedSheet.getRange("C1").formulas = [["=B1*3"]];
    damagedSheet.getRange("A2:B2").unmerge();
    await (await SpreadsheetFile.exportXlsx(damaged)).save(output);

    const report = await verifyTranslations({ source, "job-dir": jobDir, output });
    assert.equal(report.passed, false);
    assert.ok(report.errors.includes("missing-translation:S1!A1"));
    assert.ok(report.errors.includes("non-text-change:S1!B1"));
    assert.ok(report.errors.includes("formula-change:S1!C1"));
    assert.ok(report.errors.includes("merge-change:S1"));
    const state = JSON.parse(await fs.readFile(path.join(jobDir, "job-state.json"), "utf8"));
    assert.equal(state.completedStages.at(-1), "apply");
  } finally {
    await fs.rm(directory, { recursive: true, force: true });
  }
});


test("bilingual fast path rejects complex workbook objects before mutation", () => {
  assert.deepEqual(classifyBilingualGrid({ features: {} }), { safe: true, reasons: [] });
  assert.deepEqual(classifyBilingualGrid({
    features: {
      has_vba: true,
      table_count: 1,
      chart_count: 1,
      comment_count: 1,
      external_link_count: 1,
      unsupported_drawing_count: 1,
    },
    image_uncertain: true,
  }), {
    safe: false,
    reasons: [
      "macro", "table", "chart", "comment", "external-link",
      "unsupported-drawing", "image-uncertain",
    ],
  });
});


test("bilingual apply creates paired blue rows and keeps data only on source rows", async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "excel-bilingual-"));
  try {
    const source = path.join(directory, "source.xlsx");
    const output = path.join(directory, "bilingual.xlsx");
    const jobDir = path.join(directory, "job");
    const workbook = Workbook.create();
    const sheet = workbook.worksheets.add("Data");
    sheet.getRange("A1:B1").values = [["设备表", null]];
    sheet.getRange("A1:B1").merge();
    sheet.getRange("A2:C2").values = [["001", 3, null]];
    sheet.getRange("C2").formulas = [["=B2*2"]];
    await (await SpreadsheetFile.exportXlsx(workbook)).save(source);

    await inspectWorkbook({
      input: source,
      "job-dir": jobDir,
      "target-language": "en",
      "output-mode": "bilingual",
    });
    await prepareManifest({ "job-dir": jobDir });
    const manifestPath = path.join(jobDir, "translation-manifest.json");
    const manifest = JSON.parse(await fs.readFile(manifestPath, "utf8"));
    for (const unit of manifest.translation_units) {
      unit.translation = unit.source === "设备表" ? "Equipment List" : "Identifier";
      unit.status = "translated";
    }
    await fs.writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
    await applyTranslations({ input: source, "job-dir": jobDir, output });

    const result = await SpreadsheetFile.importXlsx(await FileBlob.load(output));
    const resultSheet = result.worksheets.items.find((item) => item.name === "Data");
    assert.deepEqual(resultSheet.getRange("A1:C4").values, [
      ["设备表", null, null],
      ["Equipment List", null, null],
      ["001", 3, 6],
      ["Identifier", null, null],
    ]);
    assert.equal(resultSheet.getRange("C3").formulas[0][0], "=B3*2");
    assert.equal(resultSheet.getRange("C4").formulas[0][0], "");
    assert.deepEqual(
      resultSheet.__getMergedCells().map((merge) => `${merge.startAddress}:${merge.endAddress}`),
      ["A1:B1", "A2:B2"],
    );
    assert.equal(resultSheet.getRange("A2").format.fill.color.value, "#EAF2F8");
    assert.equal(resultSheet.getRange("A2").format.font.color.value, "#1F4E78");
    assert.equal(resultSheet.getRange("A2").format.font.italic, true);
  } finally {
    await fs.rm(directory, { recursive: true, force: true });
  }
});
