import test from "node:test";
import assert from "node:assert/strict";
import {
  MAX_VIDEO_BYTES,
  WORKFLOW_STAGES,
  nextWorkflowState,
  validateVideoFile,
  validateVideoMetadata,
  workflowView,
} from "../workflow.js";

test("video limits reject unsupported, oversized, long, and undecodable input", () => {
  assert.throws(() => validateVideoFile({ type: "video/avi", size: 100 }), /Unsupported/);
  assert.throws(() => validateVideoFile({ type: "video/mp4", size: MAX_VIDEO_BYTES + 1 }), /15 MB/);
  assert.throws(() => validateVideoMetadata({ duration: 16, width: 100, height: 100 }), /15 second/);
  assert.throws(() => validateVideoMetadata({ duration: NaN, width: 0, height: 0 }), /decode/);
});

test("workflow stages are truthful ordered milestones", () => {
  assert.equal(WORKFLOW_STAGES[0], "Analyzing video");
  assert.equal(WORKFLOW_STAGES.at(-1), "Finalizing video");
  assert.equal(new Set(WORKFLOW_STAGES).size, WORKFLOW_STAGES.length);
});

test("generation, preview, export, cancellation and reset transition safely", () => {
  let state = nextWorkflowState("empty", "video_loaded");
  state = nextWorkflowState(state, "generation_started");
  assert.deepEqual(workflowView(state, true, false), {
    busy: true, canGenerate: false, canPreview: false, canExport: false, canCancel: true,
  });
  state = nextWorkflowState(state, "cancelled");
  assert.equal(state, "ready");
  state = nextWorkflowState(state, "generation_started");
  state = nextWorkflowState(state, "generation_finished");
  state = nextWorkflowState(state, "export_started");
  assert.equal(state, "exporting");
  state = nextWorkflowState(state, "export_finished");
  assert.equal(state, "generated");
  assert.equal(nextWorkflowState(state, "reset"), "empty");
});
