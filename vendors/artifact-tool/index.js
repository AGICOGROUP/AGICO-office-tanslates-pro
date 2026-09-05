// Local compatibility shim over exceljs for excel_pipeline.mjs.
// Implements the Workbook/SpreadsheetFile/FileBlob surface the pipeline and
// its tests use: range values/formulas, styles, row/column sizing, merges
// (merge/unmerge/copyFrom), used-range scan, and simple formula evaluation.
// This file is the tracked source of truth; C:\Users\AGICO\node_modules\@oai
// holds a junction pointing here (see AGENTS.md).

import ExcelJS from "exceljs";
import { readFile, writeFile } from "node:fs/promises";

const ARGV_PREFIX = "FF";

function columnToNumber(label) {
  return [...label].reduce((value, ch) => value * 26 + ch.toUpperCase().charCodeAt(0) - 64, 0);
}

function numberToColumn(number) {
  let value = number;
  let label = "";
  while (value > 0) {
    value -= 1;
    label = String.fromCharCode(65 + (value % 26)) + label;
    value = Math.floor(value / 26);
  }
  return label;
}

// "A1" | "$B$3:$C$5" | "3:3" | "B:B" -> {minRow,maxRow,minCol,maxCol}
// Row-only or column-only specs get null on the other axis.
function parseRange(address) {
  const clean = String(address).replace(/\$/g, "").trim();
  const parts = clean.split(":");
  const cell = /^([A-Z]+)(\d+)$/i;
  if (parts.length === 1 && cell.test(parts[0])) {
    const [, col, row] = cell.exec(parts[0]);
    const c = columnToNumber(col);
    return { minRow: Number(row), maxRow: Number(row), minCol: c, maxCol: c };
  }
  if (parts.length === 2 && cell.test(parts[0]) && cell.test(parts[1])) {
    const [, c1, r1] = cell.exec(parts[0]);
    const [, c2, r2] = cell.exec(parts[1]);
    return {
      minRow: Math.min(Number(r1), Number(r2)),
      maxRow: Math.max(Number(r1), Number(r2)),
      minCol: Math.min(columnToNumber(c1), columnToNumber(c2)),
      maxCol: Math.max(columnToNumber(c1), columnToNumber(c2)),
    };
  }
  if (parts.length === 2 && parts[0] === parts[1] && /^\d+$/.test(parts[0])) {
    return { minRow: Number(parts[0]), maxRow: Number(parts[0]), minCol: null, maxCol: null };
  }
  if (parts.length === 2 && parts[0] === parts[1] && /^[A-Za-z]+$/.test(parts[0])) {
    const c = columnToNumber(parts[0]);
    return { minRow: null, maxRow: null, minCol: c, maxCol: c };
  }
  throw new Error(`cannot parse range address: ${address}`);
}

function argbToHex(argb) {
  if (typeof argb !== "string" || argb.length < 6) return null;
  return `#${argb.slice(-6).toUpperCase()}`;
}

function hexToArgb(hex) {
  const body = String(hex).replace("#", "").toUpperCase();
  return ARGV_PREFIX + body.padStart(6, "0").slice(-6);
}

function readFill(cell) {
  const fill = cell.fill;
  if (!fill || fill.type !== "pattern" || fill.pattern !== "solid") return null;
  const color = fill.fgColor ?? fill.bgColor;
  if (!color) return null;
  if (color.argb) return argbToHex(color.argb);
  return null;
}

function writeFill(cell, hex) {
  cell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: hexToArgb(hex) } };
}

// Plain computed value of a cell. Merged slaves read as empty (exceljs would
// return the master's value through them, which broke bilingual validation).
function cellValue(sheet, cell) {
  if (cell.master !== cell) return null;
  const value = cell.value;
  if (value == null) return null;
  if (typeof value !== "object") return value;
  if (value instanceof Date) return value;
  if (value.formula !== undefined || value.sharedFormula !== undefined) {
    if (value.result != null) return value.result;
    if (typeof value.formula === "string") return evaluateFormula(sheet, value.formula);
    return null;
  }
  if (Array.isArray(value.richText)) return value.richText.map((part) => part.text).join("");
  if (value.error !== undefined) return value.error;
  if (value.hyperlink !== undefined) return value.text ?? String(value.hyperlink);
  return value;
}

function cellFormulaText(cell) {
  if (cell.master !== cell) return "";
  const value = cell.value;
  if (value != null && typeof value === "object" && typeof value.formula === "string") {
    return `=${value.formula}`;
  }
  return "";
}

// Tiny evaluator for the arithmetic + SUM/AVERAGE/MIN/MAX/COUNT subset the
// pipeline round-trips. Formulas containing string literals are not evaluated.
function evaluateFormula(sheet, formulaWithEquals) {
  const body = String(formulaWithEquals).replace(/^=/, "").replace(/\$/g, "");
  if (body.includes('"')) return null;
  try {
    let js = body.replace(
      /(SUM|AVERAGE|MIN|MAX|COUNT)\(([A-Z]+\d+):([A-Z]+\d+)\)/gi,
      (_, fn, start, end) => {
        const numbers = collectRangeNumbers(sheet, start, end);
        switch (fn.toUpperCase()) {
          case "SUM": return String(numbers.reduce((sum, x) => sum + x, 0));
          case "AVERAGE": return String(numbers.length ? numbers.reduce((s, x) => s + x, 0) / numbers.length : 0);
          case "MIN": return String(numbers.length ? Math.min(...numbers) : 0);
          case "MAX": return String(numbers.length ? Math.max(...numbers) : 0);
          default: return String(numbers.length);
        }
      },
    );
    js = js.replace(/\b([A-Z]{1,3})(\d+)\b/g, (_, col, row) => {
      const value = cellValue(sheet, sheet.ws.getRow(Number(row)).getCell(columnToNumber(col)));
      return typeof value === "number" ? String(value) : "0";
    });
    if (!/^[-0-9+*/().\s]+$/.test(js)) return null;
    const result = Function(`"use strict"; return (${js});`)();
    return typeof result === "number" && Number.isFinite(result) ? result : null;
  } catch {
    return null;
  }
}

function collectRangeNumbers(sheet, startRef, endRef) {
  const start = parseRange(startRef);
  const end = parseRange(endRef);
  const numbers = [];
  for (let row = Math.min(start.minRow, end.minRow); row <= Math.max(start.maxRow, end.maxRow); row += 1) {
    for (let col = Math.min(start.minCol, end.minCol); col <= Math.max(start.maxCol, end.maxCol); col += 1) {
      const value = cellValue(sheet, sheet.ws.getRow(row).getCell(col));
      if (typeof value === "number") numbers.push(value);
    }
  }
  return numbers;
}

class Range {
  constructor(sheet, address) {
    this.sheet = sheet;
    this.spec = parseRange(address);
    this.rowOnly = this.spec.minCol === null;
    this.colOnly = this.spec.minRow === null;
  }

  // Explicit cell ranges are never clamped: writes must create rows on
  // demand (buildBilingualWorkbook writes into a fresh empty sheet). Only
  // whole-row/whole-column specs use the live sheet dimensions.
  #rowBounds() {
    if (this.spec.minRow != null) return [this.spec.minRow, this.spec.maxRow];
    const max = this.sheet.ws.rowCount || 1;
    return [1, Math.min(this.spec.maxRow ?? max, max)];
  }

  #colBounds() {
    if (this.spec.minCol != null) return [this.spec.minCol, this.spec.maxCol];
    const max = this.sheet.ws.columnCount || 1;
    return [1, Math.min(this.spec.maxCol ?? max, max)];
  }

  #cellAt(row, col) {
    return this.sheet.ws.getRow(row).getCell(col);
  }

  get address() {
    const first = `${numberToColumn(this.spec.minCol)}${this.spec.minRow}`;
    const second = `${numberToColumn(this.spec.maxCol)}${this.spec.maxRow}`;
    return first === second ? first : `${first}:${second}`;
  }

  get values() {
    const [minRow, maxRow] = this.#rowBounds();
    const [minCol, maxCol] = this.#colBounds();
    const rows = [];
    for (let row = minRow; row <= maxRow; row += 1) {
      const line = [];
      for (let col = minCol; col <= maxCol; col += 1) line.push(cellValue(this.sheet, this.#cellAt(row, col)));
      rows.push(line);
    }
    return rows;
  }

  set values(input) {
    const [minRow] = this.#rowBounds();
    const [minCol] = this.#colBounds();
    input.forEach((line, rowOffset) => {
      line.forEach((value, colOffset) => {
        this.#cellAt(minRow + rowOffset, minCol + colOffset).value = value ?? null;
      });
    });
  }

  get formulas() {
    const [minRow, maxRow] = this.#rowBounds();
    const [minCol, maxCol] = this.#colBounds();
    const rows = [];
    for (let row = minRow; row <= maxRow; row += 1) {
      const line = [];
      for (let col = minCol; col <= maxCol; col += 1) line.push(cellFormulaText(this.#cellAt(row, col)));
      rows.push(line);
    }
    return rows;
  }

  set formulas(input) {
    const [minRow] = this.#rowBounds();
    const [minCol] = this.#colBounds();
    input.forEach((line, rowOffset) => {
      line.forEach((text, colOffset) => {
        const cell = this.#cellAt(minRow + rowOffset, minCol + colOffset);
        if (typeof text === "string" && text.startsWith("=")) {
          const body = text.slice(1);
          const result = evaluateFormula(this.sheet, body);
          cell.value = result != null ? { formula: body, result } : { formula: body };
        } else {
          cell.value = text ?? null;
        }
      });
    });
  }

  get format() {
    const range = this;
    const forEachCell = (apply) => {
      const [minRow, maxRow] = range.#rowBounds();
      const [minCol, maxCol] = range.#colBounds();
      for (let row = minRow; row <= maxRow; row += 1) {
        for (let col = minCol; col <= maxCol; col += 1) apply(range.#cellAt(row, col));
      }
    };
    const format = {};
    Object.defineProperty(format, "fill", {
      get() {
        const value = readFill(range.#cellAt(range.spec.minRow ?? 1, range.spec.minCol ?? 1));
        return { get color() { return { get value() { return value; } }; } };
      },
      set(hex) { forEachCell((cell) => writeFill(cell, hex)); },
    });
    Object.defineProperty(format, "wrapText", {
      get() { return range.#cellAt(range.spec.minRow ?? 1, range.spec.minCol ?? 1).alignment?.wrapText ?? false; },
      set(enabled) { forEachCell((cell) => { cell.alignment = { ...cell.alignment, wrapText: enabled }; }); },
    });
    Object.defineProperty(format, "rowHeight", {
      get() { return range.sheet.ws.getRow(range.spec.minRow ?? 1).height; },
      set(height) {
        const [minRow, maxRow] = range.#rowBounds();
        for (let row = minRow; row <= maxRow; row += 1) range.sheet.ws.getRow(row).height = height;
      },
    });
    Object.defineProperty(format, "columnWidth", {
      get() { return range.sheet.ws.getColumn(range.spec.minCol ?? 1).width; },
      set(width) {
        const [minCol, maxCol] = range.#colBounds();
        for (let col = minCol; col <= maxCol; col += 1) range.sheet.ws.getColumn(col).width = width;
      },
    });
    format.font = {
      get name() { return range.#cellAt(range.spec.minRow ?? 1, range.spec.minCol ?? 1).font?.name; },
      set name(value) { forEachCell((cell) => { cell.font = { ...cell.font, name: value }; }); },
      get size() { return range.#cellAt(range.spec.minRow ?? 1, range.spec.minCol ?? 1).font?.size; },
      set size(value) { forEachCell((cell) => { cell.font = { ...cell.font, size: value }; }); },
      get italic() { return range.#cellAt(range.spec.minRow ?? 1, range.spec.minCol ?? 1).font?.italic ?? false; },
      set italic(value) { forEachCell((cell) => { cell.font = { ...cell.font, italic: value }; }); },
      get bold() { return range.#cellAt(range.spec.minRow ?? 1, range.spec.minCol ?? 1).font?.bold ?? false; },
      set bold(value) { forEachCell((cell) => { cell.font = { ...cell.font, bold: value }; }); },
      get color() {
        const argb = range.#cellAt(range.spec.minRow ?? 1, range.spec.minCol ?? 1).font?.color?.argb;
        const value = argb ? argbToHex(argb) : null;
        return { get value() { return value; } };
      },
      set color(value) { forEachCell((cell) => { cell.font = { ...cell.font, color: { argb: hexToArgb(value) } }; }); },
    };
    return format;
  }

  merge() {
    if (this.rowOnly || this.colOnly) return;
    if (this.spec.minRow === this.spec.maxRow && this.spec.minCol === this.spec.maxCol) return;
    const label = this.address;
    if (this.sheet.ws._merges[label]) return;
    // exceljs slave cells become references to the master; shim-level reads
    // return null for slaves so bilingual validation sees hidden cells as empty
    this.sheet.ws.mergeCells(label);
  }

  unmerge() {
    this.sheet.ws.unMergeCells(this.address);
  }

  copyFrom(source) {
    const [minRow, maxRow] = this.#rowBounds();
    const [minCol, maxCol] = this.#colBounds();
    for (let row = minRow; row <= maxRow; row += 1) {
      for (let col = minCol; col <= maxCol; col += 1) {
        const sourceCell = source.sheet.ws.getRow(source.spec.minRow + row - minRow)
          .getCell(source.spec.minCol + col - minCol);
        const target = this.#cellAt(row, col);
        if (sourceCell.master !== sourceCell) {
          target.value = null;
          continue;
        }
        target.value = sourceCell.value == null ? null : structuredClone(sourceCell.value);
        const style = sourceCell.style;
        if (style && Object.keys(style).length) target.style = structuredClone(style);
      }
    }
  }

  clear({ applyTo } = {}) {
    if (applyTo !== "contents") throw new Error("unsupported clear scope");
    const [minRow, maxRow] = this.#rowBounds();
    const [minCol, maxCol] = this.#colBounds();
    for (let row = minRow; row <= maxRow; row += 1) {
      for (let col = minCol; col <= maxCol; col += 1) this.#cellAt(row, col).value = null;
    }
  }
}

class Sheet {
  constructor(worksheet) {
    this.ws = worksheet;
  }

  get name() { return this.ws.name; }

  getRange(address) { return new Range(this, address); }

  getUsedRange() {
    const maxRow = this.ws.rowCount || 0;
    const maxCol = this.ws.columnCount || 0;
    let minRow = null;
    let maxUsedRow = 0;
    let minCol = null;
    let maxUsedCol = 0;
    for (let row = 1; row <= maxRow; row += 1) {
      for (let col = 1; col <= maxCol; col += 1) {
        const value = cellValue(this, this.ws.getRow(row).getCell(col));
        if (value != null && value !== "") {
          if (minRow === null) minRow = row;
          maxUsedRow = row;
          if (minCol === null || col < minCol) minCol = col;
          if (col > maxUsedCol) maxUsedCol = col;
        }
      }
    }
    if (minRow === null) return null;
    const address = minRow === maxUsedRow && minCol === maxUsedCol
      ? `${numberToColumn(minCol)}${minRow}`
      : `${numberToColumn(minCol)}${minRow}:${numberToColumn(maxUsedCol)}${maxUsedRow}`;
    return this.getRange(address);
  }

  __getMergedCells() {
    return Object.values(this.ws._merges).map((dimensions) => {
      const [startAddress, endAddress] = dimensions.range.split(":");
      return { startAddress, endAddress: endAddress ?? startAddress };
    });
  }
}

export class Workbook {
  constructor(excelWorkbook) {
    this.excel = excelWorkbook;
    this.sheets = excelWorkbook.worksheets.map((worksheet) => new Sheet(worksheet));
  }

  static create() { return new Workbook(new ExcelJS.Workbook()); }

  get worksheets() {
    const book = this;
    return {
      items: book.sheets,
      add(name) {
        const sheet = new Sheet(book.excel.addWorksheet(name));
        book.sheets.push(sheet);
        return sheet;
      },
    };
  }
}

export const SpreadsheetFile = {
  async importXlsx(blob) {
    const excelWorkbook = new ExcelJS.Workbook();
    await excelWorkbook.xlsx.load(blob.buffer);
    return new Workbook(excelWorkbook);
  },
  async exportXlsx(workbook) {
    // merges live in each worksheet's _merges and the model getter emits them
    const buffer = await workbook.excel.xlsx.writeBuffer();
    return new FileBlob(Buffer.from(buffer));
  },
};

export class FileBlob {
  constructor(buffer) { this.buffer = buffer; }
  static async load(path) { return new FileBlob(await readFile(path)); }
  async save(path) { await writeFile(path, this.buffer); }
}
