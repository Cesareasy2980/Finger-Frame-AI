import assert from "node:assert/strict";
import test from "node:test";

import {
  PortalCrossingController,
  TransitionState,
  expandPortalQuad,
  portalCoverage,
  smoothstep,
} from "../portal-crossing.js";

const WIDTH = 320, HEIGHT = 180;
function quadForCoverage(value) {
  const scale = Math.sqrt(value), cx = 159.5, cy = 89.5;
  const halfWidth = 319 * scale / 2, halfHeight = 179 * scale / 2;
  return [
    {x:cx-halfWidth,y:cy-halfHeight},{x:cx+halfWidth,y:cy-halfHeight},
    {x:cx+halfWidth,y:cy+halfHeight},{x:cx-halfWidth,y:cy+halfHeight},
  ];
}
const growth = [0.10,0.14,0.20,0.28,0.38,0.48,0.52,0.57,0.63,0.70,0.78,0.84,0.89,0.94];

test("coverage and expansion use exact full-frame geometry", () => {
  assert.ok(Math.abs(portalCoverage(quadForCoverage(.64), WIDTH, HEIGHT)-.64) < 1e-9);
  assert.equal(smoothstep(0), 0); assert.equal(smoothstep(1), 1);
  assert.deepEqual(expandPortalQuad(quadForCoverage(.2), WIDTH, HEIGHT, 1), [
    {x:0,y:0},{x:319,y:0},{x:319,y:179},{x:0,y:179},
  ]);
});

test("browser controller enters full AI monotonically", () => {
  const controller = new PortalCrossingController(WIDTH, HEIGHT);
  const snapshots = growth.map((value, frameIndex) => controller.update({quad:quadForCoverage(value),confidence:.95,detectionState:"detected",frameIndex}));
  assert.equal(snapshots[0].state, TransitionState.PORTAL_VISIBLE);
  assert.ok(snapshots.some((snapshot) => snapshot.state === TransitionState.ENTERING));
  assert.equal(snapshots.at(-1).state, TransitionState.FULL_AI);
  const progress = snapshots.filter((snapshot) => [TransitionState.ENTERING,TransitionState.FULL_AI].includes(snapshot.state)).map((snapshot) => snapshot.progress);
  assert.ok(progress.every((value,index) => index === 0 || value >= progress[index-1]));
});

test("noise, shrinking geometry, and low confidence do not trigger", () => {
  for (const [values, confidence] of [
    [[.46,.51,.48,.52,.49,.515,.485,.50],.95],
    [[.82,.78,.73,.67,.61,.56,.52],.95],
    [growth,.35],
  ]) {
    const controller = new PortalCrossingController(WIDTH, HEIGHT);
    const states = values.map((value) => controller.update({quad:quadForCoverage(value),confidence,detectionState:"detected"}).state);
    assert.ok(!states.includes(TransitionState.ENTERING));
    assert.ok(!states.includes(TransitionState.FULL_AI));
  }
});

test("dropout, reverse transition, and a second event reset safely", () => {
  const controller = new PortalCrossingController(WIDTH, HEIGHT);
  growth.forEach((value) => controller.update({quad:quadForCoverage(value),confidence:.95,detectionState:"detected"}));
  assert.equal(controller.state, TransitionState.FULL_AI);
  let reverse;
  for (let i=0;i<5;i++) reverse = controller.update({quad:quadForCoverage(.2),confidence:.95,detectionState:"detected"});
  assert.ok(reverse.rawProgress > 0);
  const reverseNext = controller.update({quad:quadForCoverage(.2),confidence:.95,detectionState:"detected"});
  assert.ok(reverseNext.rawProgress < reverse.rawProgress);
  assert.ok(reverse.rawProgress - reverseNext.rawProgress <= 1 / controller.config.fallbackExitFrames);
  for (let i=0;i<12;i++) controller.update({quad:null,confidence:0,detectionState:"lost"});
  assert.equal(controller.state, TransitionState.INACTIVE);
  assert.equal(controller.eventMetadata().length, 1);
  controller.update({quad:quadForCoverage(.12),confidence:.9,detectionState:"detected"});
  assert.equal(controller.currentEvent.portalId, 2);
});

test("developer force progress is clamped and deterministic", () => {
  const controller = new PortalCrossingController(WIDTH, HEIGHT);
  const half = controller.update({quad:quadForCoverage(.2),confidence:1,forceProgress:.5});
  assert.equal(half.state, TransitionState.ENTERING);
  assert.equal(half.progress, .5);
  const full = controller.update({quad:null,confidence:0,forceProgress:3});
  assert.equal(full.state, TransitionState.FULL_AI);
  assert.equal(full.progress, 1);
});
