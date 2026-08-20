import { globSync } from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const patterns = ["*.js", "scripts/*.mjs", "tests-js/*.test.mjs"];

const files = patterns
  .flatMap((pattern) => globSync(pattern, { cwd: root }))
  .map((file) => file.split(path.sep).join("/"))
  .sort();

if (!files.length) {
  throw new Error("Lint found no source files; check the patterns above");
}

for (const file of files) {
  const result = spawnSync(process.execPath, ["--check", file], {
    cwd: root,
    stdio: "inherit",
  });
  if (result.status !== 0) {
    throw new Error(`Syntax check failed: ${file}`);
  }
}

console.log(`Syntax check passed for ${files.length} files`);
