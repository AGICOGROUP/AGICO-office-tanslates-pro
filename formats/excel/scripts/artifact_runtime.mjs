// Resolve the official runtime package without a repository node_modules link.
import { createRequire } from "node:module";
import { homedir } from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);
const configured = (process.env.NODE_PATH || "").split(path.delimiter).filter(Boolean);
const directories = configured.length ? configured : [
  path.resolve(path.dirname(process.execPath), "..", "node_modules"),
  path.join(homedir(), ".cache", "codex-runtimes", "codex-primary-runtime", "dependencies", "node", "node_modules"),
];
let entry;
for (const directory of directories) {
  try {
    entry = createRequire(path.join(path.resolve(directory), "__runtime_resolver__.cjs")).resolve("@oai/artifact-tool");
    break;
  } catch (error) {
    if (error.code !== "MODULE_NOT_FOUND") throw error;
  }
}
if (!entry) {
  if (configured.length) throw new Error("@oai/artifact-tool was not found in NODE_PATH; pass --node-modules with the workspace runtime directory");
  entry = require.resolve("@oai/artifact-tool");
}
const runtime = await import(pathToFileURL(entry).href);
export const { FileBlob, SpreadsheetFile, Workbook } = runtime;
