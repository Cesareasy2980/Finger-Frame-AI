import assert from "node:assert/strict";
import test from "node:test";

import { PREDICTION_FRAMES, RESET_FRAMES, StabilizedFrameTracker } from "../tracking.js";

const BASE = [
  { x: 140, y: 80 }, { x: 440, y: 80 },
  { x: 440, y: 280 }, { x: 140, y: 280 },
];

test("stabilized browser tracker rejects a self-intersecting quad", () => {
  const tracker = new StabilizedFrameTracker(640, 360);
  const state = tracker.update([BASE[0], BASE[2], BASE[1], BASE[3]]);
  assert.equal(state.stabilizedQuad, null);
  assert.equal(state.rejectionReason, "self_intersection");
});

test("stabilized browser tracker preserves cyclic corner identity", () => {
  const tracker = new StabilizedFrameTracker(640, 360);
  const first = tracker.update(BASE).stabilizedQuad;
  const second = tracker.update([...BASE.slice(2), ...BASE.slice(0, 2)]).stabilizedQuad;
  assert.deepEqual(first, second);
});

test("stabilized browser tracker distinguishes isolated and coherent jumps", () => {
  const isolated = new StabilizedFrameTracker(640, 360);
  isolated.update(BASE);
  const bad = BASE.map((point) => ({ ...point }));
  bad[2] = { x: 560, y: 190 };
  assert.equal(isolated.update(bad).rejectionReason, "isolated_corner_jump");

  const coherent = new StabilizedFrameTracker(640, 360);
  coherent.update(BASE);
  const moved = BASE.map(({ x, y }) => ({ x: x + 120, y }));
  assert.equal(coherent.update(moved).detectionState, "detected");
});

test("stabilized browser tracker predicts briefly and resets long dropouts", () => {
  const tracker = new StabilizedFrameTracker(640, 360);
  tracker.update(BASE);
  for (let i = 0; i < PREDICTION_FRAMES; i++) assert.equal(tracker.update(null).isPredicted, true);
  assert.equal(tracker.update(null).detectionState, "held");
  let state;
  for (let i = PREDICTION_FRAMES + 2; i <= RESET_FRAMES; i++) state = tracker.update(null);
  assert.equal(state.detectionState, "reset");
  assert.equal(state.stabilizedQuad, null);
});

