import assert from "node:assert/strict";
import test from "node:test";

import {
  buildRenderPlan,
  buildTranslationUnits,
  classifyRisk,
  translationReuseKey,
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


test("macro and unsupported workbook features select strict mode", () => {
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
});


test("ordinary images do not force strict mode", () => {
  const risk = classifyRisk({
    extension: ".xlsx",
    features: { unique_image_count: 3, image_occurrence_count: 8 },
  });
  assert.deepEqual(risk, { mode: "balanced", reasons: [] });
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


test("preflight renders each visible used sheet once", () => {
  const sheets = [
    { name: "A", visible: true, used: true },
    { name: "B", visible: false, used: true },
    { name: "C", visible: true, used: false },
  ];
  const plan = buildRenderPlan({
    phase: "preflight",
    outputMode: "monolingual",
    sheets,
    changedSheets: [],
    risk: { mode: "balanced", reasons: [] },
  });
  assert.deepEqual(plan.sheets.map((sheet) => sheet.name), ["A"]);
  assert.equal(plan.fullPrintPages, false);
});


test("monolingual final render contains only changed and risk sheets", () => {
  const plan = buildRenderPlan({
    phase: "final",
    outputMode: "monolingual",
    sheets: [
      { name: "A", visible: true, used: true },
      { name: "B", visible: true, used: true },
      { name: "C", visible: true, used: true },
    ],
    changedSheets: ["B"],
    riskSheets: ["C"],
    risk: { mode: "balanced", reasons: [] },
  });
  assert.deepEqual(plan.sheets.map((sheet) => sheet.name), ["B", "C"]);
  assert.equal(plan.fullPrintPages, false);
});


test("bilingual and strict final render use all visible sheets and print pages", () => {
  const sheets = [
    { name: "A", visible: true, used: true },
    { name: "B", visible: true, used: true },
    { name: "Hidden", visible: false, used: true },
  ];
  for (const request of [
    { outputMode: "bilingual", risk: { mode: "balanced", reasons: [] } },
    { outputMode: "monolingual", risk: { mode: "strict", reasons: ["chart"] } },
  ]) {
    const plan = buildRenderPlan({
      phase: "final",
      sheets,
      changedSheets: ["A"],
      ...request,
    });
    assert.deepEqual(plan.sheets.map((sheet) => sheet.name), ["A", "B"]);
    assert.equal(plan.fullPrintPages, true);
  }
});
