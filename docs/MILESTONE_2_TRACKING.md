# Milestone 2: Finger Frame Tracking Stabilization & Robustness

**Completed:** 2026-08-15  
**Scope:** Four-corner tracking geometry only.  
**Default:** `stabilized`, with the frozen Milestone 0 tracker still selectable as `legacy`.

Gemini, prompt/style behavior, MediaPipe Hand Landmarker, video timing, audio handling, the hard polygon mask, and the compositing algorithm were not redesigned. Only the quad supplied to the existing compositor changes in stabilized mode.

## 1. Existing Tracker Architecture

The detector architecture remains:

```text
MediaPipe Hand Landmarker (VIDEO mode, exactly two hands)
  -> wrist / index tip / thumb tip / middle MCP landmarks
  -> wrist-x hand ordering
  -> [left index, right index, right thumb, left thumb]
  -> custom temporal tracker
  -> existing polygon compositor
```

`composite.FrameTracker` is the preserved Milestone 0 implementation. Its existing tests remain unchanged and directly import that class. The browser's `updateTracker` function is likewise retained as the legacy path.

Legacy behavior:

- Acquisition/keep finger-spread thresholds: `0.75x` / `0.20x` wrist-to-middle-MCP scale.
- Acquisition/keep area thresholds: `0.5%` / `0.05%` of the image.
- Filter: one shared adaptive EMA alpha, `clamp(mean movement / (width * 0.05), 0.35, 0.85)`.
- Jump rejection: reject the first frame above `30%` of frame width, then accept a second large jump without proving the two candidates agree.
- Dropout: hold frozen geometry for 25 frames while increasing presence, then fade by `0.05` per processed frame until reset.

## 2. Identified Weaknesses

Jitter originates in MediaPipe fingertip landmark noise and the legacy filter's minimum alpha of `0.35`, which passes at least 35% of every small displacement. The legacy alpha is based on the mean movement of all four corners, so an isolated error can also weaken filtering for the three good corners.

The tracker had no explicit finite/bounds, duplicate-point, convexity, self-intersection, winding, aspect-ratio, orientation, or scale validation. The area check used an angle-sorted copy but returned the original anatomical order, so a bowtie could still reach the mask. Wrist-x ordering could swap identities when hands crossed.

The four corners were interpolated independently after one mean-displacement decision. No per-corner velocity or last-valid state existed, and the quad had no center/scale/orientation motion model. The one-frame teleport rule could reject coherent motion or confirm two unrelated outliers. Missing detections froze a fully visible stale quad for up to 25 frames. Landmark confidence was not used: the current result path exposes landmark coordinates to this layer, while MediaPipe applies its configured `0.3` detection/presence/tracking thresholds internally.

## 3. Stabilization Design

`stabilized_tracker.py` and `tracking.js` implement the same lightweight design without new dependencies:

1. Reuse the existing two-hand fingertip candidate.
2. Validate raw geometry before temporal acceptance.
3. Establish clockwise initial order and match cyclic corner identity to the previous valid frame.
4. Measure whole-quad center, dimensions, area, orientation, scale, and coherent translation.
5. Reject isolated/impossible changes.
6. Apply a velocity-aware predictor/filter with individual corner state.
7. Predict briefly through dropouts, then hold/fade/reset with explicit confidence.

Python exposes `update_state(hands)` for structured use and keeps `update(hands)` as a quad-only compatibility wrapper.

## 4. Geometry Validation

A candidate is rejected with an explicit reason when any check fails:

| Check | Threshold / rule |
|---|---|
| Point count | Exactly four |
| Coordinates | Numeric and finite |
| Bounds | No farther than 20% of frame width/height outside the image |
| Separation | Every pair at least `max(2 px, 1% of smaller frame dimension)` apart |
| Topology | No non-adjacent edge intersection; strictly convex |
| Area | Existing `0.5%` acquire / `0.05%` keep thresholds |
| Aspect ratio | At most `8:1` using opposite-edge averages |
| Edge collapse | Width and height each at least twice minimum corner separation |
| Winding | Positive shoelace winding in image coordinates |
| Inter-frame scale | Accepted scale ratio `0.55` through `1.8` |
| Inter-frame orientation | Change no greater than `70 degrees` |
| Extreme translation | Reject above 45% of frame diagonal when prediction residual also exceeds 25% |

Rejection reasons are counted in metrics; invalid geometry is not silently passed to the compositor.

## 5. Corner Ordering

The first valid candidate is centroid-angle sorted clockwise in image coordinates and rotated to begin at the point nearest the top-left (`min(x + y)`). Subsequent valid candidates retain clockwise winding and select the cyclic rotation with the lowest squared distance to the prior raw corner identities.

This prevents ordinary wrist-order changes and cyclic detector ambiguity from reassigning all four corners. A self-intersecting candidate is rejected rather than repaired invisibly.

## 6. Temporal Filter and Per-Corner State

Each corner stores:

```text
rawPosition
filteredPosition
velocity
lastValidFrame
confidence
```

The whole quad also stores an EMA translation velocity:

```text
quadVelocity = 0.55 * previousVelocity + 0.45 * observedCenterMotion
```

Local corner velocity is the whole-quad velocity plus 8% of that corner's deviation from coherent translation. Mostly stationary motion uses an alpha near `0.08`; deliberate motion raises alpha from whole-object speed, raw corner speed, and translation coherence, capped at `0.90`. A gated motion prediction is blended in once the whole-quad speed exceeds `0.6 px/frame`, reaching full weight at `1.4 px/frame`.

This is an adaptive EMA with a small alpha-beta-style velocity term. It was chosen over a Kalman or ML tracker because it is deterministic, dependency-free, understandable in both JavaScript and Python, and materially cheaper than MediaPipe inference.

## 7. Jump Rejection and Whole-Quad Motion

Corner displacement vectors are evaluated together. An isolated corner update is rejected when its displacement exceeds:

```text
max(10 px, 6% of frame diagonal, 3 * median corner movement + 3 px)
```

and the second-largest displacement is below 45% of the largest. The same displacement applied coherently to all four corners is accepted unless it violates the extreme-translation rule. Scale and orientation checks additionally reject quad collapse, expansion, or flipping that point-wise filtering alone would miss.

Rejected updates enter the same bounded uncertainty path as missing detections and retain an explicit `rejected` state/reason.

## 8. Dropout Handling and Prediction

Thresholds are measured in processed frames:

| Dropout length | Behavior |
|---|---|
| 1-3 frames | Constant-velocity prediction with `0.75^(gap-1)` decay; each step capped at 2.5% of frame diagonal; confidence multiplied by `0.82` |
| 4-10 frames | Hold the latest predicted quad; no more extrapolation; confidence multiplied by `0.88` |
| 11-17 frames | State becomes `lost`; held geometry fades as confidence is multiplied by `0.65` |
| 18 frames | Clear all geometry/velocity and emit `reset` |

Successful detection raises confidence by `0.18`, with a recovery penalty of up to `0.18` based on the preceding gap. Initial confidence is `0.65`. Output becomes invisible below `0.01`, so low-confidence stale geometry can disappear before the hard reset while internal state remains available for safe recovery.

## 9. Structured Confidence/State Output

The Python `TrackedFrame` and equivalent browser object expose:

```text
rawQuad
stabilizedQuad
confidence          # 0.0 to 1.0
detectionState      # detected, predicted, held, lost, rejected, reset
isPredicted
dropoutFrames
rejectionReason
```

Confidence currently reflects validated detection continuity, temporal consistency, and dropout/rejection history. Per-landmark confidence is not supplied by the current application result boundary; adding it later does not require changing this interface.

## 10. Legacy vs Stabilized Modes

Offline CLI:

```powershell
.\.venv\Scripts\python.exe composite.py input.mp4 stylized.mp4 `
  --tracking-mode legacy -o legacy.mp4

.\.venv\Scripts\python.exe composite.py input.mp4 stylized.mp4 `
  --tracking-mode stabilized -o stabilized.mp4
```

Browser development switch:

```text
http://127.0.0.1:8124/?tracking=legacy
http://127.0.0.1:8124/                     # stabilized default
```

The normal UI has no new tracker control.

## 11. Fixtures and Test Matrix

The existing 320x180, 12 FPS, 24-frame MediaPipe video fixture remains. `tests/tracking_sequences.py` adds deterministic 640x360 landmark-sequence fixtures:

| Fixture | Frames | Purpose |
|---|---:|---|
| Stationary | 80 | Repeatable independent fingertip noise; direct jitter measurement |
| Smooth translation | 70 | 2.2 px/frame translation plus noise; lag and continuity |
| Short dropout | 45 | 1.5 px/frame translation with two missing frames |
| Rapid translation | 30 | 10.5 px/frame coherent motion plus noise |

Unit tests also inject cyclic order changes, non-finite/out-of-bounds/duplicate points, tiny/extreme/self-intersecting polygons, a single-corner jump, a 120 px coherent translation, and 18-frame dropout/reset sequences. Running the same input twice must produce identical `TrackedFrame` objects.

## 12. Quantitative Metrics

Reproduce the full report:

```powershell
.\.venv\Scripts\python.exe scripts\compare_tracking.py --benchmark-repeats 200
```

Machine-readable results are retained in `tests/artifacts/milestone2_tracking_metrics.json`.

### Stationary fixture

| Metric | Legacy | Stabilized | Result |
|---|---:|---:|---|
| Raw / valid / visible frames | 80 / 80 / 80 | 80 / 80 / 80 | Continuity unchanged |
| Mean corner displacement | 0.959228 px | 0.320929 px | 66.543% lower |
| Median corner displacement | 1.001465 px | 0.305927 px | 69.452% lower |
| Maximum corner displacement | 1.510910 px | 0.979026 px | 35.203% lower |
| Center jitter RMS | 0.360546 px | 0.266885 px | **25.978% lower** |
| Normalized area variance | 0.000022234 | 0.0000075355 | 66.108% lower |
| Orientation variance | 0.01899887 deg2 | 0.00586713 deg2 | 69.118% lower |
| Mean corner acceleration | 0.426029 px/frame2 | 0.185066 px/frame2 | 56.561% lower |

### Motion and dropout fixtures

| Fixture / metric | Legacy | Stabilized |
|---|---:|---:|
| Smooth mean / max positional lag | 3.928027 / 4.357425 px | **0.512236 / 2.738557 px** |
| Smooth center jitter RMS | 0.827646 px | 0.673081 px |
| Smooth visible / rejected / reset | 70 / 0 / 0 | 70 / 0 / 0 |
| Dropout raw / valid / visible | 43 / 43 / 45 | 43 / 43 / 45 |
| Dropout held / predicted | 2 / 0 | 0 / 2 |
| Dropout mean / max lag | 2.851534 / 5.950496 px | **0.773225 / 2.107382 px** |
| Rapid mean / max lag | 7.525278 / 8.517989 px | **0.540225 / 2.770030 px** |
| Rapid valid / visible / rejected | 30 / 30 / 0 | 30 / 30 / 0 |

The rapid-motion fixture exposes a tradeoff: normalized area variance rose from `0.0000194907` to `0.0000361977`, and orientation variance rose from `0.01800215` to `0.03276588 deg2`. This is not claimed as an improvement. Rapid center jitter still fell from `1.580894 px` to `0.757600 px`, all updates remained valid/visible, no deliberate motion was rejected, and lag was substantially lower. Future tuning should constrain relative-corner noise during high-speed motion without increasing translation lag.

### Real MediaPipe video fixture

| Metric | Legacy | Stabilized |
|---|---:|---:|
| Processed / raw valid / visible | 24 / 24 / 24 | 24 / 24 / 24 |
| Detection success | 1.0 | 1.0 |
| Average measured corner movement | 6.731233 px | 5.130282 px |
| Maximum measured movement | 16.815957 px mean-quad jump | 15.168666 px individual corner |
| Predicted / held / rejected / reset | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |
| Valid / invalid composite polygons | 24 / 0 | 24 / 0 |

The legacy maximum uses its historical mean-quad metric while the stabilized maximum is per-corner, so those two maxima are included for observability but are not a strict like-for-like improvement claim.

## 13. Performance

The deterministic benchmark processed all 225 fixture frames in each of 200 fresh-tracker repetitions (45,000 updates per mode), excluding MediaPipe inference:

| Mode | Average | Median | Minimum |
|---|---:|---:|---:|
| Legacy | 0.004736 ms/frame | 0.004679 | 0.004406 |
| Stabilized | 0.037762 ms/frame | 0.037469 | 0.035095 |

Stabilization adds about `0.0330 ms/frame` in this environment. It remains lightweight relative to hand-landmark inference.

## 14. Visual Debug Comparison

The debug command overlays raw (red), legacy (blue), and stabilized (green) quads plus state, confidence, prediction status, and dropout count. It is separate from the production UI:

```powershell
.\.venv\Scripts\python.exe composite.py `
  tests\fixtures\finger_frame_short.mp4 `
  tests\fixtures\finger_frame_short_stylized.mp4 `
  -o tests\artifacts\milestone2_stabilized.mp4 `
  --tracking-mode stabilized `
  --debug-tracking tests\artifacts\milestone2_tracking_debug.mp4
```

Passing `--debug-tracking` without a path writes `tracking-debug.mp4`.

## 15. Regression Results

- Python: 27 tests passed, 0 failed (13 existing Milestone 0/1 tests plus 14 stabilized-tracker/comparison tests).
- Frontend: 15 tests passed, 0 failed (11 prompt/Gemini tests plus 4 browser-tracker tests).
- Static production build completed and includes `tracking.js`.
- Live local browser checks loaded both stabilized and `?tracking=legacy` routes with no console errors; stabilized placeholder preview reached the fixture's 2.0-second endpoint at 320x180.
- Offline stabilized fixture: 320x180, 12 FPS, 24 H.264 frames, 2.000000 seconds, AAC 48 kHz mono.
- Offline legacy mode reproduced 24/24 raw/visible frames and the exact Milestone 0 tracker/mask metrics.
- The legacy output remained byte-identical to Milestone 0: SHA-256 `8A7903B7C03FC7B1EA642B7E08193B088B01B9DE0FB2D9ED6D41DD8DFFA37F0A`.
- Prompt builder, preset/custom validation, Gemini request boundary/model, duration, FPS, frame count, and audio contracts passed unchanged.

Because stabilized tracking improved the primary stationary-jitter measure, kept all expected valid/visible frames, reduced lag in both motion fixtures, preserved the output contracts, and passed the real fixture, it is the production default. Legacy remains directly selectable for regression and difficult-footage fallback.

## 16. Known Limitations and Milestone 3 Interface

- Deterministic fixtures model landmark trajectories; only the existing short video exercises real MediaPipe inference. Difficult lighting, motion blur, portrait video, hand crossing, occlusion, and extreme camera roll need broader consented footage.
- Corner matching is cyclic and geometry-based, not a physical handedness/3D hand model. Very large rotations or prolonged ambiguous crossings can still lose semantic identity.
- Thresholds are frame-based and not normalized to timestamp/FPS. The CLI preserves source FPS, but dropout time therefore varies with FPS.
- The internal confidence is heuristic because per-landmark confidence is not exposed at the current boundary.
- High-speed relative-corner area/orientation variance remains a measured tradeoff described above.
- Prediction is forward-only; offline smoothing does not use future frames.
- Perspective warping, feathering, hand occlusion masks, and depth are intentionally deferred.

Milestone 3 can consume `stabilizedQuad`, `rawQuad`, `confidence`, `detectionState`, and `isPredicted` directly. The four-point output is validated, clockwise, and identity-stable enough to form the input boundary for a future homography, while confidence/state can gate masking and recovery. No Milestone 3 compositing was implemented here.
