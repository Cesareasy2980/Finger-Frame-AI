import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const html = await readFile(path.join(root, "index.html"), "utf8");
const app = await readFile(path.join(root, "app.js"), "utf8");
const promptBuilder = await readFile(path.join(root, "prompt-builder.js"), "utf8");
const geminiRequest = await readFile(path.join(root, "gemini-request.js"), "utf8");
const capabilities = await readFile(path.join(root, "generation-capabilities.js"), "utf8");
const referenceImage = await readFile(path.join(root, "reference-image.js"), "utf8");
const tracking = await readFile(path.join(root, "tracking.js"), "utf8");
const compositing = await readFile(path.join(root, "compositing.js"), "utf8");
const portalCrossing = await readFile(path.join(root, "portal-crossing.js"), "utf8");
const director = await readFile(path.join(root, "director.js"), "utf8");
const workflow = await readFile(path.join(root, "workflow.js"), "utf8");

const requiredIds = [
  "gem-key",
  "style-select",
  "style-custom",
  "style-description",
  "prompt-requirement",
  "prompt-validation",
  "prompt-count",
  "reference-image",
  "reference-image-preview",
  "reference-image-thumbnail",
  "reference-image-replace",
  "reference-image-remove",
  "reference-image-error",
  "reference-capability-reason",
  "file",
  "orig",
  "sty",
  "canvas",
  "btn-generate",
  "btn-placeholder",
  "btn-play",
  "btn-export",
  "btn-cancel",
  "btn-reset",
  "btn-director",
  "original-preview",
  "progress-panel",
  "portal-crossing-toggle",
  "parallax-toggle",
  "status",
];

const missingIds = requiredIds.filter(
  (id) => !html.includes(`id="${id}"`),
);
if (missingIds.length) {
  throw new Error(`Missing frontend elements: ${missingIds.join(", ")}`);
}
if (!html.includes('<script type="module" src="app.js"></script>')) {
  throw new Error("index.html no longer loads app.js as a module");
}
if (!capabilities.includes('model: "gemini-omni-flash-preview"')) {
  throw new Error("Expected Gemini model baseline was not found");
}
if (!capabilities.includes("supportsReferenceImage: true")) {
  throw new Error("Reference-image provider capability is not enabled");
}
if (!referenceImage.includes("validateReferenceImage")) {
  throw new Error("Reference-image validation boundary was not found");
}
if (!app.includes("referenceImageSelection.replace")) {
  throw new Error("Reference-image preview/replace flow was not found");
}
if (!app.includes("referenceImageSelection.clear")) {
  throw new Error("Reference-image remove/reset flow was not found");
}
if (!app.includes("referenceImage,")) {
  throw new Error("Selected reference image does not reach the request builder");
}
if (!app.includes("referenceImageCapabilityState(GENERATION_CAPABILITIES)")) {
  throw new Error("Reference-image UI is missing provider capability gating");
}
if (!app.includes('from "./prompt-builder.js"')) {
  throw new Error("app.js does not use the centralized prompt builder");
}
if (!app.includes('from "./reference-image.js"')) {
  throw new Error("app.js does not use centralized reference-image validation");
}
if (!app.includes('from "./tracking.js"')) {
  throw new Error("app.js does not use the stabilized tracking module");
}
if (!tracking.includes("class StabilizedFrameTracker")) {
  throw new Error("Stabilized tracker module was not found");
}
if (!app.includes('from "./compositing.js"')) {
  throw new Error("app.js does not use the perspective compositing module");
}
if (!compositing.includes("class PerspectiveCanvasCompositor")) {
  throw new Error("Perspective compositor module was not found");
}
if (!portalCrossing.includes("class PortalCrossingController")) {
  throw new Error("Portal Crossing controller was not found");
}
if (!director.includes("buildDirectorRequest") || !app.includes('from "./director.js"')) {
  throw new Error("AI Director request boundary was not found");
}
if (!workflow.includes("validateVideoMetadata") || !app.includes('from "./workflow.js"')) {
  throw new Error("Workflow validation/state boundary was not found");
}
if (!app.includes("buildGeminiInteractionBody({")) {
  throw new Error("app.js does not use the tested Gemini request boundary");
}
if (!promptBuilder.includes("BASE_PRESERVATION_INSTRUCTION")) {
  throw new Error("Prompt builder is missing the preservation instruction");
}
if (!app.includes("HandLandmarker.createFromOptions")) {
  throw new Error("Expected MediaPipe Hand Landmarker baseline was not found");
}

console.log("Frontend baseline contract passed");
