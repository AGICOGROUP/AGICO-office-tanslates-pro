#!/usr/bin/env node

import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";


export const JOB_STAGES = [
  "preflight",
  "inspect",
  "prepare",
  "translate",
  "validate",
  "apply",
  "verify",
  "render",
  "deliver",
];


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


function assertJobConfig({ sourceSha256, targetLanguage, outputMode }) {
  if (typeof sourceSha256 !== "string" || sourceSha256.length !== 64) {
    throw new Error("sourceSha256 must be a 64-character digest");
  }
  if (typeof targetLanguage !== "string" || !targetLanguage.trim()) {
    throw new Error("targetLanguage must be non-empty text");
  }
  if (!["monolingual", "bilingual"].includes(outputMode)) {
    throw new Error("outputMode must be monolingual or bilingual");
  }
}


export function newJobState(config) {
  assertJobConfig(config);
  return {
    schemaVersion: 1,
    sourceSha256: config.sourceSha256,
    targetLanguage: config.targetLanguage,
    outputMode: config.outputMode,
    completedStages: [],
    stageArtifacts: {},
    outputPaths: {},
    counts: {},
    strictReasons: [],
  };
}


export function nextStage(state) {
  return JOB_STAGES[state.completedStages.length] ?? null;
}


export function completeStage(state, stage, artifactHashes = {}) {
  const expected = nextStage(state);
  if (stage !== expected) {
    throw new Error(`cannot complete ${stage}; expected ${expected ?? "no further stage"}`);
  }
  return {
    ...state,
    completedStages: [...state.completedStages, stage],
    stageArtifacts: {
      ...state.stageArtifacts,
      [stage]: { ...artifactHashes },
    },
  };
}


export function invalidateFrom(state, stage) {
  const stageIndex = JOB_STAGES.indexOf(stage);
  if (stageIndex < 0) {
    throw new Error(`unknown job stage: ${stage}`);
  }
  const completedStages = state.completedStages.filter(
    (completed) => JOB_STAGES.indexOf(completed) < stageIndex,
  );
  const stageArtifacts = Object.fromEntries(
    Object.entries(state.stageArtifacts).filter(
      ([completed]) => JOB_STAGES.indexOf(completed) < stageIndex,
    ),
  );
  return { ...state, completedStages, stageArtifacts };
}


export function reconcileJobState(state, config) {
  assertJobConfig(config);
  const matches =
    state.sourceSha256 === config.sourceSha256
    && state.targetLanguage === config.targetLanguage
    && state.outputMode === config.outputMode;
  return matches ? state : newJobState(config);
}


export async function saveJobState(destination, state) {
  const output = path.resolve(destination);
  await fs.mkdir(path.dirname(output), { recursive: true });
  const temporary = `${output}.tmp-${process.pid}-${Date.now()}`;
  try {
    await fs.writeFile(temporary, `${JSON.stringify(state, null, 2)}\n`, "utf8");
    await fs.rename(temporary, output);
  } catch (error) {
    await fs.rm(temporary, { force: true });
    throw error;
  }
}
