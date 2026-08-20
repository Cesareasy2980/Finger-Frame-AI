import { cp, mkdir, rm, access } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const output = path.join(root, "dist");

if (path.dirname(output) !== root || path.basename(output) !== "dist") {
  throw new Error(`Refusing to replace unexpected build directory: ${output}`);
}

await rm(output, { recursive: true, force: true });
await mkdir(output, { recursive: true });
await Promise.all([
  cp(path.join(root, "index.html"), path.join(output, "index.html")),
  cp(path.join(root, "app.js"), path.join(output, "app.js")),
  cp(path.join(root, "tracking.js"), path.join(output, "tracking.js")),
  cp(path.join(root, "compositing.js"), path.join(output, "compositing.js")),
  cp(path.join(root, "prompt-builder.js"), path.join(output, "prompt-builder.js")),
  cp(path.join(root, "gemini-request.js"), path.join(output, "gemini-request.js")),
  cp(path.join(root, "generation-capabilities.js"), path.join(output, "generation-capabilities.js")),
  cp(path.join(root, "reference-image.js"), path.join(output, "reference-image.js")),
  cp(path.join(root, "portal-crossing.js"), path.join(output, "portal-crossing.js")),
  cp(path.join(root, "director.js"), path.join(output, "director.js")),
  cp(path.join(root, "workflow.js"), path.join(output, "workflow.js")),
]);

// Demo media is optional and is not published by default (see examples/README.md).
const examples = path.join(root, "examples");
try {
  await access(examples);
  await cp(examples, path.join(output, "examples"), { recursive: true });
} catch {
  console.log("No examples/ directory found; skipping optional demo media");
}

console.log(`Static production build written to ${output}`);
