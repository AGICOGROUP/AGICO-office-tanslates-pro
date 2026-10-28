#!/usr/bin/env node

/**
 * Resolve managed runtime executables without assuming one machine's directory layout.
 *
 * Historical installs placed each runtime one level deeper than the managed runtime does:
 *   <root>/node/bin/node.exe        (historical)
 *   <root>/node/node.exe            (managed)
 *
 * Every previous call site rebuilt that layout inline:
 *   path.resolve(path.dirname(process.execPath), "..", "..", "python", "python.exe")
 * Under the managed runtime the walk went one level too far and produced a path that does not
 * exist. spawnSync then returned an empty result and the pipeline reported the useless
 * "OOXML inspection failed: undefined". Resolution is now explicit and layout-tolerant:
 * an override, the layouts that actually occur, then PATH.
 *
 * Adapters must import this module rather than repeat layout arithmetic;
 * tests/test_skill_structure.py enforces that.
 */

import { existsSync } from "node:fs";
import os from "node:os";
import path from "node:path";

const EXECUTABLES = {
  python: process.platform === "win32" ? "python.exe" : "python",
  node: process.platform === "win32" ? "node.exe" : "node",
};

/** Each runtime's known layouts, nearest-to-managed first. */
const LAYOUTS = {
  python: [["python", "python.exe"], ["python", "bin", "python"], ["python.exe"], ["python"]],
  node: [["node", "node.exe"], ["node", "bin", "node.exe"], ["node.exe"], ["node"]],
};

function searchRoots() {
  const dir = path.dirname(process.execPath);
  const roots = [dir, "..", "../..", "../../.."].map((rel) => path.resolve(dir, rel));
  roots.push(path.join(os.homedir(), ".cache", "codex-runtimes", "codex-primary-runtime", "dependencies"));
  return [...new Set(roots)];
}

function candidates(runtime) {
  const list = [];
  for (const root of searchRoots()) {
    for (const parts of LAYOUTS[runtime] || []) list.push(path.join(root, ...parts));
  }
  return [...new Set(list)];
}

function fromEnvironmentPath(executable) {
  const entries = (process.env.PATH || "").split(path.delimiter).filter(Boolean);
  return entries.map((entry) => path.join(entry, executable)).find(existsSync) || null;
}

function resolve(runtime, envName) {
  const override = process.env[envName];
  if (override) {
    if (!existsSync(override)) throw new Error(`${envName} points at a missing executable: ${override}`);
    return override;
  }
  const executable = EXECUTABLES[runtime] || runtime;
  return candidates(runtime).find(existsSync) || fromEnvironmentPath(executable) || executable;
}

export const resolvePython = () => resolve("python", "CODEX_PYTHON");
export const resolveNode = () => resolve("node", "CODEX_NODE");

/**
 * Turn a failed spawn into an actionable message. A missing executable only sets `error`, leaving
 * stdout and stderr empty, which is what produced the bare "undefined" reports.
 */
export function spawnFailure(label, executable, result) {
  const detail = result?.error?.message || result?.stderr || result?.stdout;
  const suffix = result?.error?.code === "ENOENT" ? ` (not found: ${executable})` : "";
  return `${label}: ${detail || "the executable produced no output"}${suffix}`;
}
