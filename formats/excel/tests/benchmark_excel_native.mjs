// Reproduce with bundled Node; comparison baseline is an explicit Git revision.
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";
import { performance } from "node:perf_hooks";

const scriptDir = fileURLToPath(new URL("../scripts/", import.meta.url));
const revision = process.argv[2] || "3e433e27fe43cb6b3f6895bfb03e16d875b69db9";
const directory = await fs.mkdtemp(path.join(os.tmpdir(), "excel-native-benchmark-"));
const baselinePath = path.join(scriptDir, `.benchmark-baseline-${process.pid}.mjs`);
const python = process.env.CODEX_PYTHON || path.resolve(path.dirname(process.execPath), "..", "..", "python", "python.exe");
const run = (cmd, args, options = {}) => {
  const result = spawnSync(cmd, args, { encoding: "utf8", windowsHide: true, maxBuffer: 16 * 1024 * 1024, ...options });
  if (result.status !== 0) throw new Error(result.stderr || result.stdout || result.error?.message);
  return result.stdout;
};
try {
  await fs.writeFile(baselinePath, run("git", ["show", `${revision}:formats/excel/scripts/excel_pipeline.mjs`], { cwd: path.resolve(scriptDir, "../../..") }));
  const source = path.join(directory, "source.xlsx");
  run(python, ["-c", `from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
import sys
w=Workbook();s=w.active;s.title='Equipment'
s.column_dimensions['A'].width=18;s.column_dimensions['E'].width=24
for r in range(1,1001):
 s.append(['设备名称',r,r*2,'=B%d+C%d'%(r,r),'设备安装和运行说明','MCC'])
 s.cell(r,1).font=Font(name='Arial',bold=True)
 s.cell(r,5).alignment=Alignment(wrap_text=True)
 if r%2==0:s.cell(r,5).fill=PatternFill('solid',fgColor='EAF2F8')
w.save(sys.argv[1])`, source]);
  const baseline = await import(pathToFileURL(baselinePath).href);
  const native = await import(new URL("../scripts/excel_pipeline.mjs", import.meta.url));
  const results = [];
  for (const [name, pipeline] of [["baseline", baseline], ["native", native]]) {
    const jobDir = path.join(directory, name);
    const output = path.join(directory, `${name}.xlsx`);
    let start = performance.now();
    await pipeline.inspectWorkbook({ input: source, "job-dir": jobDir, "target-language": "en", "output-mode": "monolingual" });
    const inspect_ms = performance.now() - start;
    await pipeline.prepareManifest({ "job-dir": jobDir });
    const manifestPath = path.join(jobDir, "translation-manifest.json");
    const manifest = JSON.parse(await fs.readFile(manifestPath, "utf8"));
    for (const unit of manifest.translation_units) {
      unit.translation = unit.source === "设备安装和运行说明" ? "Equipment installation and operating instructions" : unit.source === "设备名称" ? "Equipment name" : unit.source;
      unit.status = unit.source === unit.translation ? "retain" : "translated";
    }
    await fs.writeFile(manifestPath, JSON.stringify(manifest));
    start = performance.now();
    await pipeline.applyTranslations({ input: source, output, "job-dir": jobDir });
    const apply_ms = performance.now() - start;
    start = performance.now();
    const report = await pipeline.verifyTranslations({ source, output, "job-dir": jobDir });
    const verify_ms = performance.now() - start;
    if (!report.passed) throw new Error(JSON.stringify(report));
    results.push({ name, inspect_ms, apply_ms, verify_ms, processing_ms: inspect_ms + apply_ms + verify_ms });
  }
  const report = { tested_at: new Date().toISOString(), host: { platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version }, baseline_revision: revision, rows: 1000, cells: 6000, text_cells: 3000, formula_cells: 1000,
    notes: "Actual production inspect/apply/verify. Excludes preparation, translation decisions and Office validation. Single run; same generated workbook and decisions. Runtime modules already loaded; native apply includes pre-replacement verification.", results };
  if (process.argv[3]) await fs.writeFile(process.argv[3], JSON.stringify(report, null, 2) + "\n");
  process.stdout.write(JSON.stringify(report, null, 2) + "\n");
} finally {
  await fs.unlink(baselinePath).catch(() => {});
  await fs.rm(directory, { recursive: true, force: true });
}
