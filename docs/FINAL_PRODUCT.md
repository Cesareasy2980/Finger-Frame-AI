# Final Product

Completed: 2026-08-15  
Status: demo-ready final feature sprint

## 1. Product overview

Finger Frame AI turns a short recorded finger-frame gesture into a perspective-aware portal onto a generated version of the same video. The strongest production path combines deterministic prompt construction, optional reference guidance, stabilized hand tracking, perspective projection, finger occlusion, geometry-driven full-screen Portal Crossing, lightweight parallax, staged preview, and audio-aware export.

The sprint extends the validated Milestones 0–4; legacy behavior remains directly selectable and no paid request is part of automated validation.

## 2. User workflow

```text
Upload video
  -> choose style / exact custom instruction / optional reference
  -> optionally create and edit an AI Director draft
  -> generate AI world or use local placeholder
  -> preview original and portal result side by side
  -> download the final video
```

The page presents the numbered flow from upload through download. A new upload clears old generated state. Cancel stops generation or export, and Reset Project revokes temporary media URLs and returns the app to a clean state.

## 3. Architecture

The browser and Python paths share behavior rather than an implementation runtime:

| Concern | Browser | Python/offline |
|---|---|---|
| Prompt and provider boundary | `prompt-builder.js`, `gemini-request.js` | `stylize.py` |
| Stabilized tracking | `tracking.js` | `stabilized_tracker.py` |
| Perspective/occlusion/parallax | `compositing.js` | `perspective_compositor.py` |
| Portal event/transition | `portal-crossing.js` | `portal_crossing.py` |
| Product state and limits | `workflow.js` | CLI validation and FFmpeg checks |
| Orchestration | `app.js` | `composite.py` |

Centralized transition constants and matching deterministic fixtures keep the two crossing implementations aligned.

## 4. AI generation

The established generation model remains `gemini-omni-flash-preview` through Google’s Interactions API. The request includes the source video, one deterministic text prompt, and optionally one tagged image. Both inline output data and provider file/URI output are accepted. Polling is abortable and stops after a bounded ten-minute window.

The provider is a preview surface and may be unavailable for an account or region. Automated tests mock the request boundary and never invoke paid video generation.

## 5. Style and custom prompt

Available presets are Anime, Cinematic, 3D, Cyberpunk, Ancient Egypt, Sci-Fi, Fantasy, Oil Painting, Cartoon, Realistic Transformation, Dark Fantasy, Post-Apocalyptic, Dream World, and Custom.

Custom text is retained verbatim except surrounding whitespace and has a 1,000-character limit. Every request receives the same spatial/temporal preservation instruction. An explicit custom instruction takes precedence, the selected style supplies appearance guidance, and reference guidance is last.

## 6. Reference images

Zero or one JPEG, PNG, or WebP image is supported. The limit is 8 MiB, 32×32 minimum, and 8192 pixels maximum on either edge. The browser validates MIME, non-empty size, decode success, and dimensions before selection. Replacing/removing an image revokes its old object URL.

The image guides palette, material, texture, light, and visual language; the source video remains authoritative for geometry, motion, and timing.

## 7. Tracking

The production default is `StabilizedFrameTracker`. It validates quadrilateral geometry, preserves corner identity, rejects isolated teleports, smooths adaptively, predicts through short dropouts, decays confidence, and resets after prolonged loss. The MediaPipe Hand Landmarker still supplies the same two-hand landmarks.

Use `?tracking=legacy` in the browser or `--tracking-mode legacy` offline for the frozen Milestone 0 path.

## 8. Perspective portal

The generated frame is projected into the tracked TL/TR/BR/BL quadrilateral by homography. Invalid or self-intersecting geometry fails safely. Adaptive feathering scales with portal size and resolution. Source and generated videos use the same timestamp; browser playback explicitly resynchronizes drift above 150 ms.

Compositor compatibility modes are `legacy`, `perspective`, and the default `perspective_occlusion`.

## 9. Occlusion

Finger polygons derived from the hand landmarks restore original pixels in front of the portal. Confidence and tracker state gate the effect. During Portal Crossing, occlusion influence scales by `1 - transitionProgress`, so fingers disappear continuously instead of popping at the full-screen endpoint.

## 10. Portal Crossing

`PortalCrossingController` uses visible clipped quad coverage, confidence, recent growth, and consecutive-frame hysteresis. Default thresholds are centralized:

- enter candidate at 50% visible coverage with at least 0.006 growth per frame;
- require three stable qualifying frames;
- reach full screen at 88% coverage;
- abort an incomplete entry below 34% for two frames;
- consider reverse below 40% for three frames;
- hold four unreliable frames before bounded fallback behavior.

Entering interpolates each perspective corner toward its exact full-frame corner. Smoothstep easing produces a continuous path. Feather and occlusion fade with eased progress. At progress 1, the result equals the generated frame exactly. Full-screen generated video remains timestamp-aligned with the source.

For deterministic inspection, use `?transitionProgress=0..1` or `--transition-progress 0..1`.

## 11. Multi-portal behavior

Each appearance opens a `PortalEvent` containing:

```text
portalId
stylePreset
customPromptPresent
referenceImagePresent
startFrame
endFrame
```

A prolonged disappearance closes the event, clears transition history, and returns to `INACTIVE`. A later valid frame begins a new incrementing ID with no stale progress. One generation configuration currently applies to the full source video; event-owned metadata prepares a clean extension point for per-event generation without a database.

## 12. Depth/parallax status

The implemented enhancement is a safe 2.5D illusion, not depth reconstruction. Portal center/rotation motion shifts a slightly enlarged generated layer by at most 1.5% of frame dimensions. The effect is optional, fades away at full-screen crossing, and can be disabled in the UI, with `?parallax=off`, or by omitting `--parallax` offline.

No new model or per-frame depth inference is required.

## 13. AI Director

Director Assist makes a cheap text-only `generateContent` request to `gemini-3.5-flash-lite`. It turns a short idea into one concise transformation instruction while asking the model to preserve source camera motion, composition, subjects, performance, and timing. Object-specific requests remain limited to the named object.

The draft is always inserted into the editable custom prompt field. The user reviews it before video generation; intent is never replaced silently. The manual prompt path remains fully available if Director is unavailable.

## 14. UI

The public flow has numbered actions, modern restrained styling, responsive one/two-column layouts, reference preview, feature toggles, explicit disabled states, an original/final comparison, and a clean result area. Developer diagnostics remain under `window.__fingerFrameDebug` and never include keys or binary media.

Diagnostics expose selected tracking/compositing modes, stabilized state, generation intent, safe reference metadata, transition state/progress/coverage, portal events, and feature configuration.

## 15. Export

Browser export records the canvas at 30 fps with the best supported `MediaRecorder` type, preferring H.264 MP4 and otherwise using WebM. It adds original audio tracks from `captureStream()` when supported and downloads `finger-frame-ai-output.mp4` or `.webm`.

The deterministic offline path preserves the original width, height, FPS, duration, and audio timing. FFmpeg encodes H.264/yuv420p and maps original audio to AAC when present. The validated final artifact is 320×180, 12 fps, 2.000 seconds, H.264 video plus 48 kHz mono AAC.

## 16. Limits

| Input | Policy |
|---|---|
| Browser video container/MIME | MP4, WebM, MOV (`video/mp4`, `video/webm`, `video/quicktime`) |
| Browser video size | 15 MiB maximum |
| Browser video duration | 15 seconds maximum |
| Custom prompt | 1,000 characters maximum |
| Reference image | one JPEG/PNG/WebP, 8 MiB maximum |
| Reference dimensions | 32 minimum, 8192 maximum per edge |
| Gemini polling | bounded to 600 seconds |

The offline CLI accepts any container/codecs decodable by local OpenCV/FFmpeg and is the recommended path for exact mastering.

## 17. Setup

Web requirements: Node.js 24.x and a modern browser with ES modules, WebGL/MediaPipe support, canvas capture, and MediaRecorder.

Offline requirements: Python 3.12, FFmpeg/FFprobe on `PATH`, and packages pinned in `requirements-lock.txt`.

```bash
npm install
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-lock.txt
```

Use `.venv/bin/python` instead on macOS/Linux.

## 18. Environment variables

- `GEMINI_API_KEY`: used by `stylize.py` for provider-backed generation.

The browser instead accepts a BYOK value in the UI. The key is sent only to Google’s API and is saved in session storage by default; persistent local storage is opt-in. Debug metadata never exposes it.

## 19. Run commands

```bash
npm run serve
npm run build
.venv\Scripts\python stylize.py input.mp4 -o stylized.mp4
.venv\Scripts\python composite.py input.mp4 stylized.mp4 -o final.mp4 --parallax
```

Open <http://127.0.0.1:8124/> for the browser app.

## 20. Test commands

```bash
npm test
.venv\Scripts\python -m unittest discover -s tests -v
.venv\Scripts\python scripts\validate_final_product.py
```

The final validator writes `tests/artifacts/final_demo_output.mp4`, the two-event crossing diagnostic, a preview image, and JSON performance evidence. The 2026-08-15 validation passed 46 frontend tests and 51 Python tests.

## 21. Known limitations

- Gemini Omni Flash is a preview provider surface; model/region/account availability can change.
- AI transformation and object-specific edits are probabilistic. No segmentation mask forces exact object isolation.
- One generation configuration currently covers the whole video, although each portal event owns metadata.
- Browser MediaRecorder support determines MP4 versus WebM, capture FPS, and whether source audio can be attached. Use the offline path for guaranteed mastering.
- The parallax effect is motion-derived; it is not semantic depth or 3D reconstruction.
- Portal Crossing requires a large, confidently growing frame and therefore intentionally does not trigger in every hand-frame clip.

## 22. Future improvements

- Optional user-authored per-event generation configurations.
- Explicit object masks when provider-native mask editing becomes reliable.
- Browser-side muxing for deterministic MP4/FPS/audio across engines.
- Calibration controls for unusual lenses or intentionally small crossing gestures.
- True monocular depth only if a lightweight model provides a clear quality/performance win.

No additional milestone is required for the current demo-ready product.
