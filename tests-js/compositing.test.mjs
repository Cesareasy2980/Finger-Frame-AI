import assert from "node:assert/strict";
import test from "node:test";

import { canonicalPortalCorners, compositeOpacity, computeHomography, projectPoint, validatePortalQuad } from "../compositing.js";

test("browser homography preserves canonical corner orientation", () => {
  const source = canonicalPortalCorners(320, 180);
  const destination = [{x:70,y:30},{x:250,y:50},{x:225,y:155},{x:85,y:140}];
  const matrix = computeHomography(source, destination);
  source.forEach((point, i) => {
    const projected = projectPoint(matrix, point);
    assert.ok(Math.hypot(projected.x-destination[i].x, projected.y-destination[i].y) < 1e-7);
  });
});

test("browser compositor rejects bowties and reversed winding", () => {
  assert.equal(validatePortalQuad([{x:10,y:10},{x:200,y:130},{x:200,y:10},{x:10,y:130}], 320, 180), "self_intersection");
  assert.equal(validatePortalQuad([{x:10,y:10},{x:10,y:130},{x:200,y:130},{x:200,y:10}], 320, 180), "area_or_winding");
});

test("browser confidence policy fades prediction and blocks reset", () => {
  assert.equal(compositeOpacity(1, "reset"), 0);
  assert.equal(compositeOpacity(0.05, "detected"), 0);
  assert.ok(compositeOpacity(0.5, "predicted") < compositeOpacity(0.5, "detected"));
});

