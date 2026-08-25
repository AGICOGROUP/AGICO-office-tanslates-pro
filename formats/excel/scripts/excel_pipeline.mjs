#!/usr/bin/env node

import { createHash } from "node:crypto";


export function translationReuseKey(item) {
  const contextual = Boolean(item.context_key) && item.context_key !== "unknown";
  const base = JSON.stringify([
    item.source,
    item.kind,
    item.context_key,
    item.protected_tokens,
  ]);
  return contextual ? base : `${base}\u0000${item.id}`;
}


function translationUnitId(reuseKey) {
  return `tu-${createHash("sha256").update(reuseKey, "utf8").digest("hex").slice(0, 16)}`;
}


export function buildTranslationUnits(inputOccurrences) {
  if (!Array.isArray(inputOccurrences)) {
    throw new TypeError("occurrences must be an array");
  }

  const translationUnits = [];
  const unitsByKey = new Map();
  const occurrences = inputOccurrences.map((input) => {
    const reuseKey = translationReuseKey(input);
    let unit = unitsByKey.get(reuseKey);
    if (!unit) {
      unit = {
        id: translationUnitId(reuseKey),
        source: input.source,
        context_key: input.context_key,
        protected_tokens: [...input.protected_tokens],
        translation: "",
        status: "pending",
      };
      unitsByKey.set(reuseKey, unit);
      translationUnits.push(unit);
    }
    return { ...input, translation_unit_id: unit.id };
  });

  return { occurrences, translation_units: translationUnits };
}


export function classifyRisk(meta = {}) {
  const features = meta.features ?? {};
  const checks = [
    [meta.extension === ".xlsm" || features.has_vba, "macro"],
    [meta.unsafe_legacy_conversion, "unsafe-legacy-conversion"],
    [features.chart_count > 0, "chart"],
    [features.comment_count > 0, "comment"],
    [features.unsupported_drawing_count > 0, "unsupported-drawing"],
    [meta.repair_warning, "repair-warning"],
    [meta.formula_change, "formula-change"],
    [meta.merge_change, "merge-change"],
    [meta.protected_token_change, "protected-token-change"],
    [meta.image_uncertain, "image-uncertain"],
    [meta.state_hash_mismatch, "state-hash-mismatch"],
  ];
  const reasons = checks.filter(([condition]) => Boolean(condition)).map(([, reason]) => reason);
  return { mode: reasons.length ? "strict" : "balanced", reasons };
}


export function buildRenderPlan({
  phase,
  outputMode,
  sheets,
  changedSheets = [],
  riskSheets = [],
  risk = { mode: "balanced", reasons: [] },
}) {
  if (!Array.isArray(sheets)) {
    throw new TypeError("sheets must be an array");
  }
  const visibleUsed = sheets.filter((sheet) => sheet.visible !== false && sheet.used !== false);
  if (phase === "preflight") {
    return {
      phase,
      mode: risk.mode,
      sheets: visibleUsed,
      fullPrintPages: false,
      reasons: [...risk.reasons],
    };
  }
  if (phase !== "final") {
    throw new Error(`unsupported render phase: ${phase}`);
  }
  const fullCoverage = risk.mode === "strict" || outputMode === "bilingual";
  const selectedNames = new Set([...changedSheets, ...riskSheets]);
  return {
    phase,
    mode: risk.mode,
    sheets: fullCoverage
      ? visibleUsed
      : visibleUsed.filter((sheet) => selectedNames.has(sheet.name)),
    fullPrintPages: fullCoverage,
    reasons: [...risk.reasons],
  };
}
