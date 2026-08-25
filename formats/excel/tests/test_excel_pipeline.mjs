import assert from "node:assert/strict";
import test from "node:test";

import {
  buildTranslationUnits,
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
