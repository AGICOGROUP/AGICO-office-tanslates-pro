#!/usr/bin/env node

import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const FIXED_ENGLISH_TRANSLATIONS = JSON.parse(readFileSync(
  new URL("../references/fixed-translations.en.json", import.meta.url), "utf8",
));


export const JOB_STAGES = [
  "preflight",
  "inspect",
  "prepare",
  "translate",
  "validate",
  "apply",
  "verify",
  "office-validate",
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


function parameterizedOccurrence(input) {
  const match = /^\s*([^：:\n]{1,16})([：:])\s*(.+?)\s*$/.exec(String(input.source));
  if (!match) return input;
  const [, label, separator, suffix] = match;
  const suffixHasLanguage = /[\p{Script=Han}\p{Script=Cyrillic}\p{Script=Arabic}]/u.test(suffix);
  const suffixLooksTechnical = /^(?:[+-]?\d|[A-Z]{1,8}\d)/u.test(suffix);
  if (suffixHasLanguage || !suffixLooksTechnical) return input;
  return {
    ...input,
    source: label.trim(),
    context_key: `parameter:${label.trim()}`,
    protected_tokens: [],
    original_source: input.source,
    original_protected_tokens: [...input.protected_tokens],
    translation_template: { separator, suffix },
  };
}

export function renderOccurrenceTranslation(occurrence, unit) {
  if (!occurrence.translation_template) return unit.translation;
  const { separator, suffix } = occurrence.translation_template;
  return `${unit.translation}${separator}${suffix}`;
}

function normalizedFixedSource(source) {
  return String(source).trim().replace(/\s+/gu, " ");
}

function isSafeIdentifier(source) {
  const value = String(source).trim();
  return /^[A-Z]$/u.test(value)
    || /^(?=[A-Za-z0-9./_-]*\d)[A-Za-z0-9][A-Za-z0-9./_-]*$/u.test(value);
}

export function applySafeAutofill(units, targetLanguage) {
  const english = /^(?:en|english)$/iu.test(String(targetLanguage).trim());
  let fixed = 0;
  let retained = 0;
  for (const unit of units) {
    if (unit.status !== "pending") continue;
    if (isSafeIdentifier(unit.source)) {
      unit.translation = unit.source;
      unit.status = "retain";
      unit.reason = "identifier/model code retained";
      retained += 1;
      continue;
    }
    const translation = english
      ? FIXED_ENGLISH_TRANSLATIONS[normalizedFixedSource(unit.source)] : undefined;
    if (translation) {
      unit.translation = translation;
      unit.status = "translated";
      fixed += 1;
    }
  }
  return {
    fixed,
    retained,
    pending: units.filter((unit) => unit.status === "pending").length,
  };
}

function weightedTextLength(text) {
  return [...String(text)].reduce(
    (length, character) => length + (/^[\x00-\x7F]$/u.test(character) ? 1 : 2), 0,
  );
}

function estimatedWrappedLines(text, columnWidth) {
  const width = Number.isFinite(columnWidth) ? columnWidth : 8.43;
  const capacity = Math.max(6, Math.floor(width * 1.15));
  return String(text).split(/\r?\n/u).reduce((total, line) => {
    const words = line.trim().split(/\s+/u).filter(Boolean);
    if (words.length <= 1) {
      return total + Math.max(1, Math.ceil(weightedTextLength(line) / capacity));
    }
    let lines = 1;
    let used = 0;
    for (const word of words) {
      const length = weightedTextLength(word);
      if (used === 0) {
        lines += Math.max(0, Math.ceil(length / capacity) - 1);
        used = length % capacity || Math.min(length, capacity);
      } else if (used + 1 + length <= capacity) {
        used += 1 + length;
      } else {
        lines += Math.max(1, Math.ceil(length / capacity));
        used = length % capacity || Math.min(length, capacity);
      }
    }
    return total + lines;
  }, 0);
}

export function shouldWrapTranslatedText({ text, columnWidth }) {
  return estimatedWrappedLines(text, columnWidth) > 1;
}

export function estimateTranslatedRowHeight({ text, columnWidth, currentHeight = 15 }) {
  const lines = estimatedWrappedLines(text, columnWidth);
  return Math.max(currentHeight, Math.min(60, lines * 15 + 3));
}

export function findCompressibleBlankRows(values, formulas, startRow = 1) {
  const blankRows = values.map((row, index) => {
    const formulaRow = formulas[index] ?? [];
    const width = Math.max(row?.length ?? 0, formulaRow.length);
    for (let column = 0; column < width; column += 1) {
      if (!blank(row?.[column]) || !blank(formulaRow[column])) return false;
    }
    return true;
  });
  const result = [];
  for (let index = 0; index < blankRows.length;) {
    if (!blankRows[index]) { index += 1; continue; }
    let end = index;
    while (end < blankRows.length && blankRows[end]) end += 1;
    if (end - index >= 3) {
      for (let row = index; row < end; row += 1) result.push(startRow + row);
    }
    index = end;
  }
  return result;
}

export function verticalMergeRows(merges) {
  const rows = new Set();
  for (const merge of merges ?? []) {
    const start = splitCellAddress(merge.startAddress);
    const end = splitCellAddress(merge.endAddress);
    if (start.row === end.row) continue;
    for (let row = start.row; row <= end.row; row += 1) rows.add(row);
  }
  return rows;
}

export function buildTranslationUnits(inputOccurrences) {
  if (!Array.isArray(inputOccurrences)) {
    throw new TypeError("occurrences must be an array");
  }

  const translationUnits = [];
  const unitsByKey = new Map();
  const occurrences = inputOccurrences.map((rawInput) => {
    const input = parameterizedOccurrence(rawInput);
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
  const strictChecks = [
    [meta.extension === ".xlsm" || features.has_vba, "macro"],
    [meta.unsafe_legacy_conversion, "unsafe-legacy-conversion"],
    [meta.repair_warning, "repair-warning"],
    [meta.formula_change, "formula-change"],
    [meta.merge_change, "merge-change"],
    [meta.protected_token_change, "protected-token-change"],
    [meta.state_hash_mismatch, "state-hash-mismatch"],
  ];
  const complexChecks = [
    [features.chart_count > 0, "chart"],
    [features.comment_count > 0, "comment"],
    [features.external_link_count > 0, "external-link"],
    [features.unsupported_drawing_count > 0, "unsupported-drawing"],
    [meta.image_uncertain, "image-uncertain"],
  ];
  const strictReasons = strictChecks.filter(([condition]) => Boolean(condition)).map(([, reason]) => reason);
  const complexReasons = complexChecks.filter(([condition]) => Boolean(condition)).map(([, reason]) => reason);
  const reasons = [...strictReasons, ...complexReasons];
  return { mode: strictReasons.length ? "strict" : complexReasons.length ? "complex" : "fast", reasons };
}


export function classifyBilingualGrid(meta = {}) {
  const features = meta.features ?? {};
  const checks = [
    [features.has_vba, "macro"],
    [features.table_count > 0, "table"],
    [features.chart_count > 0, "chart"],
    [features.comment_count > 0, "comment"],
    [features.external_link_count > 0, "external-link"],
    [features.unsupported_drawing_count > 0, "unsupported-drawing"],
    [meta.image_uncertain, "image-uncertain"],
  ];
  const reasons = checks.filter(([condition]) => Boolean(condition)).map(([, reason]) => reason);
  return { safe: reasons.length === 0, reasons };
}


export function buildImageReviewPlan(inputImages) {
  if (!Array.isArray(inputImages)) throw new TypeError("images must be an array");
  if (inputImages.length === 0) {
    return { skipped: true, groups: [], deep_review_ids: [], strict_reasons: [] };
  }
  const byHash = new Map();
  for (const image of inputImages) {
    const existing = byHash.get(image.sha256);
    if (!existing) {
      byHash.set(image.sha256, { ...image, occurrences: [...(image.occurrences ?? [])] });
    } else {
      existing.occurrences = [...new Set([...existing.occurrences, ...(image.occurrences ?? [])])];
      if (image.status === "manual-review") {
        existing.status = "manual-review";
        existing.reason_code = "manual-review";
      }
    }
  }
  const groups = [...byHash.values()];
  return {
    skipped: false,
    groups,
    deep_review_ids: groups
      .filter((image) => ["localized", "manual-review"].includes(image.status))
      .map((image) => image.id),
    strict_reasons: groups.some((image) => image.status === "manual-review")
      ? ["image-manual-review"] : [],
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


async function sha256File(filename) {
  return createHash("sha256").update(await fs.readFile(filename)).digest("hex");
}


async function writeJson(filename, value) {
  await fs.mkdir(path.dirname(filename), { recursive: true });
  await fs.writeFile(filename, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}


function columnNumber(label) {
  return [...label].reduce((value, character) => value * 26 + character.charCodeAt(0) - 64, 0);
}


function columnLabel(number) {
  let value = number;
  let label = "";
  while (value > 0) {
    value -= 1;
    label = String.fromCharCode(65 + (value % 26)) + label;
    value = Math.floor(value / 26);
  }
  return label;
}


function rangeOrigin(address) {
  const match = /^\$?([A-Z]+)\$?(\d+)/i.exec(address ?? "");
  if (!match) throw new Error(`cannot parse used range address: ${address}`);
  return { column: columnNumber(match[1].toUpperCase()), row: Number(match[2]) };
}


function rangeBounds(address) {
  const match = /^\$?([A-Z]+)\$?(\d+)(?::\$?([A-Z]+)\$?(\d+))?$/i.exec(address ?? "");
  if (!match) throw new Error(`cannot parse range address: ${address}`);
  return {
    startColumn: columnNumber(match[1].toUpperCase()),
    startRow: Number(match[2]),
    endColumn: columnNumber((match[3] ?? match[1]).toUpperCase()),
    endRow: Number(match[4] ?? match[2]),
  };
}


function splitCellAddress(address) {
  const match = /^\$?([A-Z]+)\$?(\d+)$/i.exec(address ?? "");
  if (!match) throw new Error(`cannot parse cell address: ${address}`);
  return { column: match[1].toUpperCase(), row: Number(match[2]) };
}


export function mapFormulaToSourceRows(formula) {
  return formula.replace(/(\$?[A-Z]{1,3})(\$?)(\d+)/g, (_, column, absolute, row) => (
    `${column}${absolute}${Number(row) * 2 - 1}`
  ));
}


function protectedTokens(text) {
  const matches = String(text).match(/(?:https?:\/\/\S+|\b[A-Z]{1,8}[-/]?\d[A-Z0-9./-]*\b|\b\d+(?:\.\d+)?\s*(?:kW|MW|V|kV|A|Hz|mm|cm|m|kg|t\/h|m³\/h)\b)/giu);
  return [...new Set(matches ?? [])];
}


function contextForCell(values, rowIndex, columnIndex) {
  for (let row = rowIndex - 1; row >= 0; row -= 1) {
    const candidate = values[row]?.[columnIndex];
    if (typeof candidate === "string" && candidate.trim()) {
      return `cell:column:${candidate.trim()}`;
    }
  }
  return "unknown";
}


async function loadState(jobDir) {
  return JSON.parse(await fs.readFile(path.join(jobDir, "job-state.json"), "utf8"));
}


function inspectOoxmlPackage(input, jobDir) {
  const bundledPython = path.resolve(path.dirname(process.execPath), "..", "..", "python", "python.exe");
  const python = process.env.CODEX_PYTHON || bundledPython;
  const script = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "inspect_excel_package.py");
  const extraction = path.join(jobDir, "images");
  const result = spawnSync(python, [script, input, "--extract-dir", extraction], {
    encoding: "utf8",
    windowsHide: true,
  });
  if (result.status !== 0) {
    throw new Error(`OOXML inspection failed: ${result.stderr || result.stdout}`);
  }
  const report = JSON.parse(result.stdout);
  const features = report.features ?? {};
  features.unsupported_drawing_count = (
    features.meaningful_drawing_count > 0
    && features.chart_count === 0
    && features.unique_image_count === 0
  ) ? features.meaningful_drawing_count : 0;
  return { ...report, features };
}

function queryRelevantGlossary(manifestPath, outputPath) {
  const bundledPython = path.resolve(path.dirname(process.execPath), "..", "..", "python", "python.exe");
  const python = process.env.CODEX_PYTHON || bundledPython;
  const scriptDir = path.dirname(fileURLToPath(import.meta.url));
  const script = path.resolve(scriptDir, "query_repo_glossary.py");
  const repoRoot = path.resolve(scriptDir, "..", "..", "..");
  const result = spawnSync(python, [
    script, "--repo-root", repoRoot, "--manifest", manifestPath, "--output", outputPath,
  ], { encoding: "utf8", windowsHide: true });
  if (result.status !== 0) {
    throw new Error(`glossary query failed: ${result.stderr || result.stdout}`);
  }
}


function parseOptions(argv) {
  const command = argv[0];
  const options = {};
  for (let index = 1; index < argv.length; index += 2) {
    const flag = argv[index];
    const value = argv[index + 1];
    if (!flag?.startsWith("--") || value === undefined) {
      throw new Error(`invalid option near ${flag ?? "end of command"}`);
    }
    options[flag.slice(2)] = value;
  }
  return { command, options };
}


function requireOptions(options, names) {
  for (const name of names) {
    if (!options[name]) throw new Error(`missing --${name}`);
  }
}


export async function inspectWorkbook(options) {
  requireOptions(options, ["input", "job-dir", "target-language", "output-mode"]);
  const input = path.resolve(options.input);
  const jobDir = path.resolve(options["job-dir"]);
  const config = {
    sourceSha256: await sha256File(input),
    targetLanguage: options["target-language"],
    outputMode: options["output-mode"],
  };
  let state;
  try {
    state = reconcileJobState(await loadState(jobDir), config);
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
    state = newJobState(config);
  }
  if (state.completedStages.length > 0) state = invalidateFrom(state, "preflight");

  const packageReport = inspectOoxmlPackage(input, jobDir);
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(input));
  const sheets = [];
  const occurrences = [];
  for (const sheet of workbook.worksheets.items) {
    const used = sheet.getUsedRange();
    if (!used?.address) {
      sheets.push({ name: sheet.name, visible: true, used: false });
      continue;
    }
    const values = used.values ?? [];
    const formulas = used.formulas ?? [];
    const origin = rangeOrigin(used.address);
    sheets.push({ name: sheet.name, visible: true, used: true, range: used.address });
    for (let row = 0; row < values.length; row += 1) {
      for (let column = 0; column < (values[row]?.length ?? 0); column += 1) {
        const source = values[row][column];
        if (typeof source !== "string" || !source.trim() || formulas[row]?.[column]) continue;
        const address = `${columnLabel(origin.column + column)}${origin.row + row}`;
        occurrences.push({
          id: `${sheet.name}!${address}`,
          kind: "cell",
          sheet: sheet.name,
          address,
          source,
          context_key: contextForCell(values, row, column),
          protected_tokens: protectedTokens(source),
        });
      }
    }
  }
  const inventory = {
    schema_version: 1,
    source_file: input,
    source_sha256: config.sourceSha256,
    target_language: config.targetLanguage,
    output_mode: config.outputMode,
    sheets,
    occurrences,
    features: packageReport.features,
    images: packageReport.images,
    image_uncertain: packageReport.features.unique_image_count > 0,
  };
  const inventoryPath = path.join(jobDir, "inventory.json");
  await writeJson(inventoryPath, inventory);
  state = completeStage(state, "preflight", { inventory: await sha256File(inventoryPath) });
  state = completeStage(state, "inspect", { inventory: await sha256File(inventoryPath) });
  state.outputPaths = { ...state.outputPaths, source: input, jobDir };
  state.counts = { ...state.counts, occurrences: occurrences.length, sheets: sheets.length };
  await saveJobState(path.join(jobDir, "job-state.json"), state);
  return { next_stage: nextStage(state), counts: state.counts };
}


export async function prepareManifest(options) {
  requireOptions(options, ["job-dir"]);
  const jobDir = path.resolve(options["job-dir"]);
  let state = await loadState(jobDir);
  if (nextStage(state) !== "prepare") throw new Error(`prepare requires stage prepare; found ${nextStage(state)}`);
  const inventory = JSON.parse(await fs.readFile(path.join(jobDir, "inventory.json"), "utf8"));
  const built = buildTranslationUnits(inventory.occurrences);
  const autofill = applySafeAutofill(built.translation_units, inventory.target_language);
  const manifest = {
    schema_version: 2,
    source_file: inventory.source_file,
    source_sha256: inventory.source_sha256,
    target_language: inventory.target_language,
    output_mode: inventory.output_mode,
    occurrences: built.occurrences,
    translation_units: built.translation_units,
    images: (inventory.images ?? []).map((image) => ({
      id: `img-${image.sha256.slice(0, 16)}`,
      sha256: image.sha256,
      occurrences: [...image.occurrences],
      status: "manual-review",
      reason_code: "manual-review",
    })),
  };
  const manifestPath = path.join(jobDir, "translation-manifest.json");
  await writeJson(manifestPath, manifest);
  const glossaryPath = path.join(jobDir, "relevant-glossary.json");
  queryRelevantGlossary(manifestPath, glossaryPath);
  state = completeStage(state, "prepare", { manifest: await sha256File(manifestPath) });
  state.counts = {
    ...state.counts,
    translationUnits: built.translation_units.length,
    pendingTranslationUnits: autofill.pending,
    fixedTranslationUnits: autofill.fixed,
    retainedTranslationUnits: autofill.retained,
  };
  await saveJobState(path.join(jobDir, "job-state.json"), state);
  return {
    next_stage: "translate",
    manifest: manifestPath,
    glossary: glossaryPath,
    pending: autofill.pending,
    autofill,
  };
}


function validateTranslatedManifest(manifest, state) {
  if (manifest.schema_version !== 2) throw new Error("manifest schema_version must be 2");
  if (manifest.source_sha256 !== state.sourceSha256) throw new Error("manifest source hash mismatch");
  const units = new Map();
  for (const unit of manifest.translation_units ?? []) {
    if (!unit.id || units.has(unit.id)) throw new Error(`missing or duplicate translation unit: ${unit.id}`);
    if (!['translated', 'retain'].includes(unit.status)) throw new Error(`translation unit ${unit.id} is pending`);
    if (typeof unit.translation !== "string" || !unit.translation.trim()) throw new Error(`translation unit ${unit.id} has no translation`);
    if (unit.status === "retain" && unit.translation !== unit.source) throw new Error(`retained unit ${unit.id} changed source`);
    for (const token of unit.protected_tokens ?? []) {
      if (!unit.translation.includes(token)) throw new Error(`translation unit ${unit.id} changed protected token ${token}`);
    }
    units.set(unit.id, unit);
  }
  for (const occurrence of manifest.occurrences ?? []) {
    const unit = units.get(occurrence.translation_unit_id);
    if (!unit) throw new Error(`occurrence ${occurrence.id} references an unknown translation unit`);
    for (const field of ["source", "context_key", "protected_tokens"]) {
      if (JSON.stringify(occurrence[field]) !== JSON.stringify(unit[field])) {
        throw new Error(`occurrence ${occurrence.id} does not match translation unit ${unit.id}`);
      }
    }
  }
  return units;
}


async function buildBilingualWorkbook(sourceWorkbook, manifest, units) {
  const outputWorkbook = Workbook.create();
  const occurrencesBySheet = new Map();
  for (const occurrence of manifest.occurrences) {
    if (occurrence.kind !== "cell") continue;
    if (!occurrencesBySheet.has(occurrence.sheet)) occurrencesBySheet.set(occurrence.sheet, []);
    occurrencesBySheet.get(occurrence.sheet).push(occurrence);
  }

  for (const source of sourceWorkbook.worksheets.items) {
    const target = outputWorkbook.worksheets.add(source.name);
    const used = source.getUsedRange();
    if (!used?.address) continue;
    const bounds = rangeBounds(used.address);
    for (let column = bounds.startColumn; column <= bounds.endColumn; column += 1) {
      const label = columnLabel(column);
      const width = source.getRange(`${label}:${label}`).format.columnWidth;
      if (typeof width === "number" && Number.isFinite(width)) {
        target.getRange(`${label}:${label}`).format.columnWidth = width;
      }
    }
    for (let row = bounds.startRow; row <= bounds.endRow; row += 1) {
      const sourceRow = row * 2 - 1;
      const translationRow = row * 2;
      const first = columnLabel(bounds.startColumn);
      const last = columnLabel(bounds.endColumn);
      const original = source.getRange(`${first}${row}:${last}${row}`);
      const sourceTarget = target.getRange(`${first}${sourceRow}:${last}${sourceRow}`);
      const translationTarget = target.getRange(`${first}${translationRow}:${last}${translationRow}`);
      sourceTarget.copyFrom(original, "all");
      translationTarget.copyFrom(original, "all");
      translationTarget.clear({ applyTo: "contents" });
      const height = original.format.rowHeight;
      if (typeof height === "number" && Number.isFinite(height)) {
        sourceTarget.format.rowHeight = height;
        translationTarget.format.rowHeight = Math.max(height, 18);
      }
      translationTarget.format.fill = "#EAF2F8";
      translationTarget.format.font.name = "Arial";
      translationTarget.format.font.color = "#1F4E78";
      translationTarget.format.font.italic = true;
      translationTarget.format.wrapText = true;
      for (let column = bounds.startColumn; column <= bounds.endColumn; column += 1) {
        const offset = column - bounds.startColumn;
        const formula = original.formulas?.[0]?.[offset];
        if (typeof formula === "string" && formula) {
          target.getRange(`${columnLabel(column)}${sourceRow}`).formulas = [[mapFormulaToSourceRows(formula)]];
        }
      }
    }

    const merges = typeof source.__getMergedCells === "function" ? source.__getMergedCells() : [];
    for (const merge of merges) {
      const start = splitCellAddress(merge.startAddress);
      const end = splitCellAddress(merge.endAddress);
      if (start.row !== end.row) {
        throw new Error(`bilingual fast path does not support vertical merge ${merge.startAddress}:${merge.endAddress}`);
      }
      const sourceRow = start.row * 2 - 1;
      const translationRow = start.row * 2;
      target.getRange(`${start.column}${sourceRow}:${end.column}${sourceRow}`).merge();
      target.getRange(`${start.column}${translationRow}:${end.column}${translationRow}`).merge();
    }

    for (const occurrence of occurrencesBySheet.get(source.name) ?? []) {
      const cell = splitCellAddress(occurrence.address);
      const translation = renderOccurrenceTranslation(
        occurrence, units.get(occurrence.translation_unit_id),
      );
      target.getRange(`${cell.column}${cell.row * 2}`).values = [[translation]];
    }
  }
  return outputWorkbook;
}

function mergedCellWidth(sheet, address) {
  const cell = splitCellAddress(address);
  let startColumn = columnNumber(cell.column);
  let endColumn = startColumn;
  let verticalMerge = false;
  for (const merge of sheet.__getMergedCells?.() ?? []) {
    const start = splitCellAddress(merge.startAddress);
    const end = splitCellAddress(merge.endAddress);
    const startNumber = columnNumber(start.column);
    const endNumber = columnNumber(end.column);
    if (cell.row >= start.row && cell.row <= end.row
      && startColumn >= startNumber && startColumn <= endNumber) {
      startColumn = startNumber;
      endColumn = endNumber;
      verticalMerge = start.row !== end.row;
      break;
    }
  }
  let width = 0;
  for (let column = startColumn; column <= endColumn; column += 1) {
    const value = sheet.getRange(`${columnLabel(column)}:${columnLabel(column)}`).format.columnWidth;
    width += Number.isFinite(value) ? value : 8.43;
  }
  return { width, verticalMerge };
}

function applyMonolingualLayoutRepairs(workbook, manifest, units) {
  const sheets = new Map(workbook.worksheets.items.map((sheet) => [sheet.name, sheet]));
  const expandedRows = new Set();
  const compressedRows = new Set();
  for (const occurrence of manifest.occurrences) {
    if (occurrence.kind !== "cell") continue;
    const sheet = sheets.get(occurrence.sheet);
    if (!sheet) continue;
    const cell = splitCellAddress(occurrence.address);
    const { width, verticalMerge } = mergedCellWidth(sheet, occurrence.address);
    if (verticalMerge) continue;
    const rowRange = sheet.getRange(`${cell.row}:${cell.row}`);
    const currentHeight = Number.isFinite(rowRange.format.rowHeight)
      ? rowRange.format.rowHeight : 15;
    const text = renderOccurrenceTranslation(
      occurrence, units.get(occurrence.translation_unit_id),
    );
    const neededHeight = estimateTranslatedRowHeight({
      text, columnWidth: width, currentHeight,
    });
    if (shouldWrapTranslatedText({ text, columnWidth: width })) {
      sheet.getRange(occurrence.address).format.wrapText = true;
    }
    if (neededHeight > currentHeight) {
      rowRange.format.rowHeight = neededHeight;
      expandedRows.add(`${sheet.name}!${cell.row}`);
    }
  }
  for (const sheet of workbook.worksheets.items) {
    const used = sheet.getUsedRange();
    if (!used?.address) continue;
    const origin = rangeOrigin(used.address);
    const mergedRows = verticalMergeRows(sheet.__getMergedCells?.() ?? []);
    for (const row of findCompressibleBlankRows(
      used.values ?? [], used.formulas ?? [], origin.row,
    )) {
      if (mergedRows.has(row)) continue;
      const rowRange = sheet.getRange(`${row}:${row}`);
      const currentHeight = Number.isFinite(rowRange.format.rowHeight)
        ? rowRange.format.rowHeight : 15;
      if (currentHeight > 8) {
        rowRange.format.rowHeight = 8;
        compressedRows.add(`${sheet.name}!${row}`);
      }
    }
  }
  return { expandedRows: expandedRows.size, compressedRows: compressedRows.size };
}


function normalizedMerges(sheet) {
  if (typeof sheet.__getMergedCells !== "function") return [];
  return sheet.__getMergedCells()
    .map((merge) => `${merge.startAddress}:${merge.endAddress}`)
    .sort();
}


function cellContent(sheet, address) {
  const range = sheet.getRange(address);
  return {
    value: range.values?.[0]?.[0],
    formula: range.formulas?.[0]?.[0],
  };
}


function blank(value) {
  return value === null || value === undefined || value === "";
}


function expectedBilingualMerges(sourceSheet, errors) {
  const expected = [];
  for (const merge of sourceSheet.__getMergedCells?.() ?? []) {
    const start = splitCellAddress(merge.startAddress);
    const end = splitCellAddress(merge.endAddress);
    if (start.row !== end.row) {
      errors.push(`unsupported-vertical-merge:${sourceSheet.name}!${merge.startAddress}:${merge.endAddress}`);
      continue;
    }
    expected.push(`${start.column}${start.row * 2 - 1}:${end.column}${end.row * 2 - 1}`);
    expected.push(`${start.column}${start.row * 2}:${end.column}${end.row * 2}`);
  }
  return expected.sort();
}


export async function verifyTranslations(options) {
  requireOptions(options, ["source", "job-dir", "output"]);
  const sourcePath = path.resolve(options.source);
  const outputPath = path.resolve(options.output);
  const jobDir = path.resolve(options["job-dir"]);
  let state = await loadState(jobDir);
  if (nextStage(state) !== "verify") throw new Error(`verify requires stage verify; found ${nextStage(state)}`);
  const errors = [];
  if (await sha256File(sourcePath) !== state.sourceSha256) errors.push("source-hash-change");
  const manifest = JSON.parse(await fs.readFile(path.join(jobDir, "translation-manifest.json"), "utf8"));
  let sourceWorkbook;
  let outputWorkbook;
  try {
    sourceWorkbook = await SpreadsheetFile.importXlsx(await FileBlob.load(sourcePath));
    outputWorkbook = await SpreadsheetFile.importXlsx(await FileBlob.load(outputPath));
  } catch (error) {
    errors.push(`output-open-failure:${error.message}`);
  }

  if (sourceWorkbook && outputWorkbook) {
    const sourceNames = sourceWorkbook.worksheets.items.map((sheet) => sheet.name);
    const outputNames = outputWorkbook.worksheets.items.map((sheet) => sheet.name);
    if (JSON.stringify(sourceNames) !== JSON.stringify(outputNames)) errors.push("sheet-order-change");
    const outputSheets = new Map(outputWorkbook.worksheets.items.map((sheet) => [sheet.name, sheet]));
    const units = new Map(manifest.translation_units.map((unit) => [unit.id, unit]));
    for (const sourceSheet of sourceWorkbook.worksheets.items) {
      const outputSheet = outputSheets.get(sourceSheet.name);
      if (!outputSheet) {
        errors.push(`missing-sheet:${sourceSheet.name}`);
        continue;
      }
      const expectedMerges = state.outputMode === "bilingual"
        ? expectedBilingualMerges(sourceSheet, errors)
        : normalizedMerges(sourceSheet);
      if (JSON.stringify(expectedMerges) !== JSON.stringify(normalizedMerges(outputSheet))) {
        errors.push(`merge-change:${sourceSheet.name}`);
      }
      const used = sourceSheet.getUsedRange();
      if (!used?.address) continue;
      const bounds = rangeBounds(used.address);
      for (let row = bounds.startRow; row <= bounds.endRow; row += 1) {
        for (let column = bounds.startColumn; column <= bounds.endColumn; column += 1) {
          const address = `${columnLabel(column)}${row}`;
          const sourceCell = cellContent(sourceSheet, address);
          const targetAddress = state.outputMode === "bilingual"
            ? `${columnLabel(column)}${row * 2 - 1}` : address;
          const outputCell = cellContent(outputSheet, targetAddress);
          if (!blank(sourceCell.formula)) {
            const expected = state.outputMode === "bilingual"
              ? mapFormulaToSourceRows(sourceCell.formula) : sourceCell.formula;
            if (outputCell.formula !== expected) errors.push(`formula-change:${sourceSheet.name}!${address}`);
          } else if (typeof sourceCell.value !== "string" && sourceCell.value !== outputCell.value) {
            errors.push(`non-text-change:${sourceSheet.name}!${address}`);
          } else if (state.outputMode === "bilingual" && typeof sourceCell.value === "string"
            && sourceCell.value !== outputCell.value) {
            errors.push(`source-text-change:${sourceSheet.name}!${address}`);
          }
          if (state.outputMode === "bilingual") {
            const translationCell = cellContent(outputSheet, `${columnLabel(column)}${row * 2}`);
            if ((typeof sourceCell.value !== "string" || !blank(sourceCell.formula))
              && (!blank(translationCell.value) || !blank(translationCell.formula))) {
              errors.push(`bilingual-nontext-duplicate:${sourceSheet.name}!${address}`);
            }
          }
        }
      }
    }
    for (const occurrence of manifest.occurrences) {
      const outputSheet = outputSheets.get(occurrence.sheet);
      if (!outputSheet) continue;
      const unit = units.get(occurrence.translation_unit_id);
      const sourceCell = splitCellAddress(occurrence.address);
      const targetAddress = state.outputMode === "bilingual"
        ? `${sourceCell.column}${sourceCell.row * 2}` : occurrence.address;
      const actual = cellContent(outputSheet, targetAddress).value;
      if (actual !== renderOccurrenceTranslation(occurrence, unit)) {
        errors.push(`missing-translation:${occurrence.id}`);
      }
      for (const token of occurrence.original_protected_tokens ?? unit.protected_tokens ?? []) {
        if (!String(actual ?? "").includes(token)) errors.push(`protected-token-change:${occurrence.id}:${token}`);
      }
    }
    for (const sheet of outputWorkbook.worksheets.items) {
      const used = sheet.getUsedRange();
      for (const row of used?.values ?? []) {
        for (const value of row) {
          if (typeof value === "string" && /^#(?:REF!|DIV\/0!|VALUE!|NAME\?|N\/A)$/.test(value)) {
            errors.push(`formula-error:${sheet.name}:${value}`);
          }
        }
      }
    }
  }

  const report = {
    passed: errors.length === 0,
    errors: [...new Set(errors)],
    source_sha256: state.sourceSha256,
    output_sha256: await sha256File(outputPath).catch(() => null),
  };
  const reportPath = path.join(jobDir, "verification.json");
  await writeJson(reportPath, report);
  if (report.passed) {
    state = completeStage(state, "verify", { report: await sha256File(reportPath) });
  } else {
    state.strictReasons = [...new Set([...state.strictReasons, ...report.errors.map((item) => item.split(":")[0])])];
  }
  await saveJobState(path.join(jobDir, "job-state.json"), state);
  return report;
}


function runExcelOfficeValidation(outputPath) {
  const script = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "excel_com_verify.ps1");
  const powershell = process.env.CODEX_POWERSHELL || "powershell.exe";
  const result = spawnSync(powershell, [
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script,
    "-InputPath", outputPath,
  ], { encoding: "utf8", windowsHide: true });
  if (result.status !== 0) {
    throw new Error(`Excel COM validation failed: ${result.stderr || result.stdout}`);
  }
  return JSON.parse(result.stdout);
}


export async function officeValidateOutput(options, officeRunner = runExcelOfficeValidation) {
  requireOptions(options, ["job-dir", "output"]);
  const jobDir = path.resolve(options["job-dir"]);
  const outputPath = path.resolve(options.output);
  let state = await loadState(jobDir);
  if (nextStage(state) !== "office-validate") {
    throw new Error(`office-validate requires stage office-validate; found ${nextStage(state)}`);
  }
  const verification = JSON.parse(await fs.readFile(path.join(jobDir, "verification.json"), "utf8"));
  if (!verification.passed) throw new Error("office-validate requires a passing verification report");
  const report = await officeRunner(outputPath);
  if (!report?.passed) throw new Error("Microsoft Excel validation did not pass");
  const reportPath = path.join(jobDir, "office-validation.json");
  await writeJson(reportPath, report);
  state = completeStage(state, "office-validate", { report: await sha256File(reportPath) });
  await saveJobState(path.join(jobDir, "job-state.json"), state);
  return { ...report, next_stage: nextStage(state) };
}


export async function applyTranslations(options) {
  requireOptions(options, ["input", "job-dir", "output"]);
  const input = path.resolve(options.input);
  const output = path.resolve(options.output);
  const jobDir = path.resolve(options["job-dir"]);
  if (input === output) throw new Error("output must not overwrite the source workbook");
  let state = await loadState(jobDir);
  if (nextStage(state) !== "translate") throw new Error(`apply requires stage translate; found ${nextStage(state)}`);
  if (await sha256File(input) !== state.sourceSha256) throw new Error("input workbook hash changed since inspection");
  const manifestPath = path.join(jobDir, "translation-manifest.json");
  const manifest = JSON.parse(await fs.readFile(manifestPath, "utf8"));
  const units = validateTranslatedManifest(manifest, state);
  state = completeStage(state, "translate", { manifest: await sha256File(manifestPath) });
  state = completeStage(state, "validate", { manifest: await sha256File(manifestPath) });

  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(input));
  const sheets = new Map(workbook.worksheets.items.map((sheet) => [sheet.name, sheet]));
  const changedSheets = new Set();
  let layoutRepairs = { expandedRows: 0, compressedRows: 0 };
  let outputWorkbook = workbook;
  if (state.outputMode === "bilingual") {
    const inventory = JSON.parse(await fs.readFile(path.join(jobDir, "inventory.json"), "utf8"));
    const safety = classifyBilingualGrid(inventory);
    if (!safety.safe) throw new Error(`bilingual strict fallback required: ${safety.reasons.join(", ")}`);
    outputWorkbook = await buildBilingualWorkbook(workbook, manifest, units);
    for (const occurrence of manifest.occurrences) changedSheets.add(occurrence.sheet);
  } else {
    for (const occurrence of manifest.occurrences) {
      if (occurrence.kind !== "cell") continue;
      const sheet = sheets.get(occurrence.sheet);
      if (!sheet) throw new Error(`worksheet not found: ${occurrence.sheet}`);
      sheet.getRange(occurrence.address).values = [[renderOccurrenceTranslation(
        occurrence, units.get(occurrence.translation_unit_id),
      )]];
      changedSheets.add(occurrence.sheet);
    }
    layoutRepairs = applyMonolingualLayoutRepairs(outputWorkbook, manifest, units);
  }
  await fs.mkdir(path.dirname(output), { recursive: true });
  const blob = await SpreadsheetFile.exportXlsx(outputWorkbook);
  await blob.save(output);
  state = completeStage(state, "apply", { output: await sha256File(output) });
  state.outputPaths = { ...state.outputPaths, output };
  state.counts = { ...state.counts, changedSheets: changedSheets.size, ...layoutRepairs };
  await saveJobState(path.join(jobDir, "job-state.json"), state);
  return { next_stage: nextStage(state), output, changed_sheets: [...changedSheets] };
}


export async function main(argv = process.argv.slice(2)) {
  const { command, options } = parseOptions(argv);
  let result;
  if (command === "inspect") result = await inspectWorkbook(options);
  else if (command === "prepare") result = await prepareManifest(options);
  else if (command === "apply") result = await applyTranslations(options);
  else if (command === "verify") result = await verifyTranslations(options);
  else if (command === "office-validate") result = await officeValidateOutput(options);
  else throw new Error("usage: excel_pipeline.mjs inspect|prepare|apply|verify|office-validate [options]");
  process.stdout.write(`${JSON.stringify(result)}\n`);
  if (command === "prepare") process.exitCode = 3;
  if (command === "verify" && !result.passed) process.exitCode = 2;
}


if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    process.stderr.write(`${error.stack ?? error.message}\n`);
    process.exitCode = 2;
  });
}
