# Repository Technical Audit

> [!NOTE]
> **Historical snapshot.** This audit was taken on the pre-release codebase
> (then named `finger-frame-effect-ai-main`) and is kept as a record of the
> engineering review that shaped the release. It is not a description of the
> current repository. Findings that have since been addressed include the
> absence of a test suite — the released code ships Python and JavaScript
> suites under `tests/` and `tests-js/`, run in CI on every push.

**Repository:** `finger-frame-effect-ai-main`  
**Audit date:** 2026-08-15  
**Scope:** Architecture, implementation trace, local runtime checks, risks, reuse decisions, and future-feature feasibility.  
**Change policy:** Audit only. No application source, configuration, dependency, prompt, or behavior was changed. This report is the only added file.

## 1. Executive Summary

This repository is a compact prototype with two implementations of the same conceptual workflow:

1. A static, browser-only application in `index.html` and `app.js`.
2. A two-command Python CLI in `stylize.py` and `composite.py`.

There is no application backend, database, job queue, authentication layer, project build system, or test suite. The browser application is served as static files and calls Google’s Gemini API directly with a user-supplied key. The Python scripts call the same cloud model through `google-genai`, then process video locally with MediaPipe, OpenCV, NumPy, FFmpeg, and FFprobe.

The repository does **not** transform only the portal region with AI. It sends the whole source clip to the native video-to-video model, receives a whole-frame stylized clip, and reveals that clip through a tracked four-point polygon. The visual alignment depends almost entirely on Gemini following a long “strict pixel-aligned edit” prompt. The compositor does not estimate or apply a homography, does not feather the mask, and does not segment hands for foreground occlusion.

Finger-frame detection is deliberately simple: MediaPipe Hand Landmarker must return exactly two hands; the four corners are the index fingertip and thumb tip from each hand. The hands are ordered by wrist x-coordinate, not by handedness. A stateful filter adds gesture spread/area hysteresis, velocity-adaptive exponential smoothing, one-frame teleport rejection, a 25-frame dropout hold, and a gradual presence fade. This is a useful prototype baseline, but it is not robust world-space tracking and will jitter, lag, hold stale geometry, or reorder under difficult poses.

The browser fallback path was exercised successfully with the committed sample: page load, sample load, prompt control, missing-key error, placeholder preview, MediaPipe initialization, responsive layout, and MP4 export all worked. The paid cloud-generation branch was not invoked because no API key was supplied. The Python CLI could not be executed end-to-end because the declared Python dependencies are not installed and the repository contains only a final example, not matching original/stylized inputs. The default local Python is 3.14.6, while current MediaPipe Python package metadata lists support only through Python 3.12; a Python 3.12 runtime is available locally and is the safest choice.

Overall status: the web prototype is runnable, while complete AI and Python verification is blocked by credentials and missing local packages/assets. The strongest reusable piece is the small, explicit tracking state machine; it should be retained as a regression baseline, then improved behind a track-data interface.

## 2. Repository Architecture

### 2.1 Important tree

```text
finger-frame-effect-ai-main/
├── index.html                 Static UI, CSS, controls, canvas/video elements
├── app.js                     Entire browser application:
│                              upload, Gemini REST call, tracking, rendering,
│                              preview, and MediaRecorder export
├── stylize.py                 Python Gemini video-to-video CLI
├── composite.py               Python hand tracking, masking, rendering,
│                              H.264 encoding, and original-audio muxing
├── requirements.txt           Four unpinned/lower-bounded Python dependencies
├── README.md                  Product description and run instructions
├── .gitignore                 Ignores user media, model, environment, and output files
└── examples/
    ├── final.mp4              Committed final demonstration (1280×720, ~7.92 s)
    └── final.gif              Reduced demonstration (560×315, ~7.91 s)
```

There is no `.git` directory in the supplied workspace copy, so commit history and a normal `git diff`/`git status` audit are unavailable.

### 2.2 Entry points

- Browser entry point: `index.html`, which loads `app.js` as an ES module.
- Python AI entry point: `stylize.py:main()`.
- Python compositing entry point: `composite.py:main()`.
- Development server: any static server; the README uses `python3 -m http.server 8124`.

### 2.3 Frontend architecture

The frontend is a single static page with inline CSS and no framework, bundler, package manager, service worker, or module graph beyond one remote ES import.

- `index.html` owns layout, responsive styles, form fields, hidden `<video>` elements, the output `<canvas>`, and control buttons.
- `app.js` owns all state in module-level variables: selected file, tracker/model instance, AI/placeholder mode, tracker state, playback, and recorder state.
- Browser computer-vision code is loaded at runtime from jsDelivr: `@mediapipe/tasks-vision@0.10.14`.
- The MediaPipe WASM bundle comes from jsDelivr and the hand model comes from Google Cloud Storage.
- The browser sends requests directly to `https://generativelanguage.googleapis.com/v1beta`.
- Browser persistence is limited to API key/style preferences in `localStorage` or `sessionStorage`.

### 2.4 Backend architecture

There is no backend. Static hosting serves the frontend. Consequently:

- API credentials are entered and used in the browser.
- Video bytes travel directly from the browser to Google when AI generation is requested.
- There is no server-side validation, quota control, audit trail, job durability, storage lifecycle, retry queue, or secret vault.
- Processing state disappears on refresh.

The Python CLI is an offline operator tool, not an HTTP backend.

### 2.5 Video, AI, utility, and configuration modules

| Area | File / symbols | Responsibility |
|---|---|---|
| Browser video input | `app.js:loadVideo`, `drawPoster` | Blob URL, metadata, canvas sizing, poster frame |
| Browser AI | `prompt`, `fileToBase64`, `gemFetch`, `findOutputVideo`, generate click handler | Prompt construction, inline upload, Interactions API polling, output retrieval |
| Browser tracking | `initLandmarker`, `computeQuad`, `updateTracker` | MediaPipe initialization, gesture gates, corner tracking |
| Browser composite | `quadPath`, `drawWindow`, `drawOutline`, `loop` | Polygon clip, alpha reveal, decorations, playback sync |
| Browser export | `playThrough`, export click handler | Canvas capture, codec choice, MediaRecorder, download |
| Python AI | `stylize.py:main` | File API upload, Interactions API request/poll/download |
| Python tracking | `FrameTracker.compute_quad`, `FrameTracker.update` | Python port of browser tracking logic |
| Python composite | `draw_outline`, `composite.py:main` | Mask, blend, sequential frame rendering |
| Python encode/audio | `subprocess.Popen`, FFprobe/FFmpeg calls | H.264 output and original-audio mux |
| Configuration | constants in `app.js`, `stylize.py`, `composite.py` | URLs, model id, prompts, thresholds, codec parameters |

No `.env` template, JSON/YAML configuration, `package.json`, `pyproject.toml`, lock file, CI workflow, Dockerfile, or test configuration exists.

### 2.6 Temporary/output behavior

- Browser input and AI output use in-memory Blob/Object URLs; URLs are not revoked.
- Browser export accumulates all MediaRecorder chunks in memory before download.
- `composite.py` downloads `hand_landmarker.task` into the current working directory if absent.
- `composite.py` writes the requested output directly, then temporarily uses `<output>.mux.mp4` when audio is present and atomically replaces the first output.
- `stylize.py` uploads a source file to Google’s File API and does not explicitly delete the remote file afterward.
- `.gitignore` excludes `.env`, `.venv`, `*.task`, common user media/output formats, logs, and caches, with explicit exceptions for the committed examples.

## 3. Current End-to-End Pipeline

### 3.1 Browser path

```text
User selects/drops a video
    ↓  app.js:loadVideo
Blob URL + metadata load; canvas set to source dimensions
    ↓  app.js:initLandmarker (asynchronous)
MediaPipe WASM + float16 Hand Landmarker loaded, GPU delegate requested
    ↓  user chooses one of two branches
    ├─ AI branch
    │    ↓  fileToBase64
    │  Entire source video converted to base64 in memory
    │    ↓  gemFetch POST v1beta/interactions
    │  Gemini Omni Flash receives whole video + style/alignment prompt
    │    ↓  polling/findOutputVideo
    │  Whole-frame stylized video returned as base64 or URI
    │
    └─ Placeholder branch
         Original video reused with a canvas hue/saturation/contrast filter
    ↓  playThrough + loop, once per animation frame/new video time
Original frame drawn full-canvas
    ↓  HandLandmarker.detectForVideo
Two hands detected; four fingertip corners computed
    ↓  updateTracker
Gesture gates + smoothing + jump rejection + dropout hold/presence fade
    ↓  drawWindow
Canvas clips to the tracked polygon; full-frame stylized video is drawn through it
    ↓  drawOutline
Dashed border, pulsing corner dots, and fading presence are rendered
    ↓  Preview OR Export
Canvas captureStream(30) → MediaRecorder → MP4 when supported, else WebM
```

Important browser details:

- Upload validation is minimal. The file picker accepts `video/*`, but MIME validity, codec support, duration, dimensions, and decoding errors are not handled explicitly.
- The 15 MB size check happens only when the AI button is clicked. Large videos can still be loaded and processed through the placeholder path.
- Hand model loading is started but not awaited by the upload flow; users can enable preview before the tracker is ready. Rendering safely skips detection until `landmarker` becomes non-null.
- The AI and original `<video>` elements play separately. `loop()` seeks the stylized video only if drift exceeds 0.15 seconds.
- Browser export captures the canvas video track only. It does **not** preserve original audio.

### 3.2 Python path

```text
Original video
    ↓  stylize.py
Credential/input existence checks
    ↓  google-genai File API upload
Remote file processing poll
    ↓  Interactions API: gemini-omni-flash-preview
Whole-video native video-to-video edit
    ↓  response/output-file poll and download
Stylized video
    ↓  composite.py
Open original + stylized streams with OpenCV
    ↓  MediaPipe Hand Landmarker in VIDEO mode
Detect two hands for each original frame
    ↓  FrameTracker.compute_quad / update
Four fingertip corners + stateful filtering
    ↓  fillPoly mask + straight alpha blend
Reveal corresponding full-frame stylized pixels inside polygon
    ↓  draw_outline
Decorative portal outline
    ↓  raw BGR frame pipe to FFmpeg
H.264/yuv420p MP4 at original dimensions/FPS
    ↓  FFprobe + second FFmpeg pass when source has audio
Original audio transcoded to AAC and muxed with -shortest
```

The Python path is sequential. It does not extract individual image files. Frames are decoded in a loop and sent to FFmpeg through stdin.

## 4. Finger Frame Detection

### 4.1 Detector and model

- Library: MediaPipe Tasks Vision Hand Landmarker.
- Browser package: `@mediapipe/tasks-vision@0.10.14` from jsDelivr (`app.js:1-9`).
- Model: Google’s `hand_landmarker.task`, float16 revision 1.
- Browser configuration: `runningMode: "VIDEO"`, `numHands: 2`, and detection/presence/tracking confidence thresholds of `0.3`; GPU delegate requested (`app.js:initLandmarker`).
- Python configuration: equivalent VIDEO mode, two hands, and 0.3 thresholds (`composite.py:215-224`), with no explicit GPU delegate; it therefore uses MediaPipe’s available/default local execution path.

MediaPipe supplies per-frame hand landmarks and also performs its own video-mode tracking between detections. The repository adds a second custom temporal filter over the four derived corners.

### 4.2 Landmarks and corner construction

The only landmarks used are:

- `0`: wrist, used for left-to-right ordering and hand scale.
- `4`: thumb tip, used as a portal corner.
- `8`: index-finger tip, used as a portal corner.
- `9`: middle-finger MCP, used with the wrist to estimate hand scale.

`computeQuad` / `FrameTracker.compute_quad` requires exactly two landmark lists. For each hand it computes:

```text
index = landmark 8 in pixel coordinates
thumb = landmark 4 in pixel coordinates
scale = distance(wrist 0, middle MCP 9) + 1 pixel
```

The hands are sorted by wrist x-coordinate. With `A` as the smaller wrist x and `B` as the larger, the returned anatomical corner sequence is:

```text
[A.index, B.index, B.thumb, A.thumb]
```

This sequence is deliberately not replaced with a convex hull. If the anatomical edges cross, the returned polygon is a bowtie. An angle-sorted copy is used only to calculate the area gate.

### 4.3 Gesture validity gates

Both hands are required. A hand is rejected if thumb-to-index distance is too small relative to wrist-to-middle-MCP scale:

- Acquire threshold: `0.75 × hand scale`.
- Keep threshold after activation: `0.20 × hand scale`.

The candidate is also rejected if the angle-sorted four-point area is below:

- Acquire threshold: `0.5%` of the frame area.
- Keep threshold after activation: `0.05%` of the frame area.

This hysteresis makes entry intentional and continued tracking permissive. It also allows poor/closed geometry to persist after activation.

### 4.4 Orientation handling

There is no explicit device-orientation, EXIF rotation, handedness, palm-facing, mirror, or roll normalization. The detector receives decoded display coordinates and the two hands are assigned solely by wrist x-position. Consequences include:

- Crossing hands can swap their A/B identity.
- A near-vertical arrangement can reorder unpredictably when wrists pass in x.
- Mirrored video still works geometrically, but semantic left/right identity is not retained.
- No corner-consistency matching is performed against the previous frame.

### 4.5 Perspective handling

Detection produces a 2D four-point polygon only. Landmark z coordinates are ignored. There is no camera calibration, plane fitting, pose estimation, homography, or perspective transform. A skewed quadrilateral can follow fingertips, but it is merely a clip boundary.

## 5. Tracking

Tracking is frame-by-frame/animation-frame detection in MediaPipe VIDEO mode plus a custom state machine (`app.js:updateTracker`; `composite.py:FrameTracker.update`).

### 5.1 Smoothing

When a valid target follows an existing quad, mean corner displacement is calculated. Each corner is linearly interpolated toward its new target with:

```text
alpha = clamp(mean_displacement / (frame_width × 0.05), 0.35, 0.85)
```

Small movements still accept 35% of the new position; large movements accept up to 85%. This reduces jitter while trying not to lag fast motion. It is a first-order exponential filter, not a Kalman/One-Euro filter, and is not normalized for FPS.

### 5.2 Teleport rejection

A target whose mean displacement is more than `30%` of frame width is rejected once. If another large jump immediately follows, it is accepted because `JUMP_CONFIRM_FRAMES = 2`.

The implementation counts consecutive jump frames, but it does not verify that the two new targets agree with each other. Two unrelated outliers can therefore confirm a teleport.

### 5.3 Dropout behavior

When detection fails after acquisition:

- Existing corners are frozen for up to 25 processed frames.
- During that hold, `presence` increases toward 1 rather than decaying.
- After 25 lost frames, presence fades by `0.05` per frame.
- At zero presence, corners and active state are cleared.

At 30 FPS this is roughly 0.83 seconds of frozen geometry followed by up to 0.67 seconds of fade. The actual duration changes with decoded/processed FPS. There is no velocity prediction, optical-flow continuation, confidence weighting, or backward/offline correction.

### 5.4 Detection failure and jitter assessment

- Before first valid acquisition: no portal is drawn.
- Short failure: the last quad remains fully visible and stationary.
- Long failure: the stale quad fades, then clears.
- Reacquisition while active uses the permissive keep gates.
- Jitter is reduced but not eliminated. Landmark noise of several pixels passes through the minimum 0.35 alpha.
- Fast motion can lag by one or more frames, then jump.
- Hand identity/corner swaps are not explicitly handled.
- Web playback processes only when `orig.currentTime` changes; Python processes every decoded frame.

The tracker is reasonable for a controlled front-facing gesture but not yet production-grade for crossing hands, occlusion, motion blur, changing orientation, or camera movement.

## 6. Masking & Compositing

### 6.1 Browser compositor

`drawWindow(q)` creates a canvas path from the four anatomical corners, clips to it, sets `globalAlpha = presence`, and draws either:

- the entire stylized video frame at `(0, 0, canvas.width, canvas.height)`, or
- the entire original frame with hue rotation, saturation, and contrast filters in placeholder mode.

The original frame was already drawn as the canvas background. The portal therefore reveals corresponding screen-space pixels from the stylized frame.

### 6.2 Python compositor

For each frame, `composite.py`:

1. Creates a zero-valued single-channel mask.
2. Calls `cv2.fillPoly` with integer quad coordinates.
3. Converts the mask to `[0,1]` and multiplies by tracker presence.
4. Applies a straight per-pixel blend between original and same-sized stylized frames.
5. Draws the outline and corner effects.

### 6.3 Capability assessment

| Capability | Current behavior |
|---|---|
| Polygon mask | Yes, four fingertip points |
| Perspective transform/homography | No |
| Alpha blending | Yes, uniform portal presence |
| Feathering | No |
| Edge smoothing | Canvas/OpenCV antialiasing only for outline; mask edge itself is hard |
| Occlusion mask | No |
| Fingers kept in front | Not guaranteed; only pixels outside the polygon remain original |
| Motion following | Quad follows tracked fingertips with smoothing/hold |
| Generated-content alignment | Assumed from full-frame AI result and prompt |
| Output dimensions | Original dimensions; stylized video is stretched/resized to match if needed |

This is **not perspective-aware compositing**. A quadrilateral clip can look perspective-shaped, but the content inside is not warped into the quad. The approach is closer to a screen-space reveal or animated mask than a portal surface attached to the hands.

Foreground fingers are not segmented. Because the polygon boundary uses fingertip centers and anatomical edges, parts of fingers can be overwritten if they lie inside the polygon. There is no hand-depth or matte pass to restore them over the generated layer.

## 7. AI Generation

### 7.1 Provider/model inventory

There is one real AI generation provider and one non-AI fallback.

| Item | Details |
|---|---|
| Provider | Google Gemini Developer API |
| Model | `gemini-omni-flash-preview` |
| Location | Cloud |
| API | Preview `v1beta/interactions` / `google-genai` Interactions API |
| Input | Entire source video plus text prompt |
| Output | Entire stylized video |
| Modality | Native video-to-video editing |
| Browser call | `app.js` generate handler, `gemFetch` |
| Python call | `stylize.py:main`, `client.interactions.create` |
| Authentication | Browser BYOK field; Python `GEMINI_API_KEY` or `GOOGLE_API_KEY` |
| Fallback | Local canvas hue shift; not an AI model |

There are no alternative AI providers or fallback cloud models.

As of the audit date, Google’s official [Gemini Omni Flash model page](https://ai.google.dev/gemini-api/docs/models/gemini-omni-flash) identifies the model as preview, accepts text/image/video input, limits video editing input to 10 seconds, and produces 3–10 second video at 720p/24 FPS. The project itself does not encode these duration/FPS constraints in validation. Google’s [Omni documentation](https://ai.google.dev/gemini-api/docs/omni) also documents regional/content limitations, lack of a dedicated negative-prompt setting, and URI delivery for larger output. These are provider facts, not guarantees made by the repository.

### 7.2 Prompts

Browser presets in `app.js:STYLES`:

- 3D animated movie.
- Hand-drawn anime.
- Claymation.
- Watercolor.

The browser also already exposes a custom prompt textarea. `prompt()` takes the custom text or preset and always appends a long, hardcoded alignment suffix requiring unchanged camera, geometry, position, facial expression, mouth openness, blinking, gaze, timing, clothing colors, and background.

`stylize.py` has only the 3D animated default prompt. `-p/--prompt` completely replaces that default; unlike the browser, it does **not** automatically append the alignment suffix to a custom CLI prompt.

There is no dedicated negative prompt, seed, strength, guidance, reference image, aspect-ratio, resolution, duration, safety, or number-of-outputs control in this repository.

### 7.3 Request/output handling

Browser:

- Converts the entire source file to base64, inflating memory by roughly one third before JSON overhead.
- Rejects files over approximately 15 MB for AI submission.
- Polls pending interactions every five seconds for up to 600 seconds.
- Searches several possible preview-response shapes for an output video.
- Supports inline base64 or URI output, then loads the result into a hidden video element.

Python:

- Uploads through the File API instead of inlining.
- Polls uploaded-file processing without a timeout.
- Polls the interaction for up to 900 seconds.
- Supports inline data or URI/file download.
- Does not request `response_format: {delivery: "uri"}` explicitly.
- Does not delete the uploaded or generated remote files.

### 7.4 Resolution, FPS, duration, cost, and limitations

- Repository UI guidance: “a few seconds of 720p” and under 15 MB.
- Repository-enforced duration: none.
- Provider’s current documented editing input maximum: 10 seconds.
- Provider’s current documented output: 720p, 24 FPS, 3–10 seconds.
- Browser export: canvas source dimensions, requested capture rate 30 FPS, 10 Mbps; actual MediaRecorder timing is browser-dependent.
- Python final export: original dimensions and original reported FPS.
- Cost is not numerically documented in the repository. It only states that generation is billed per video. As of the audit date, Google’s official [Gemini API pricing page](https://ai.google.dev/gemini-api/docs/pricing) lists Omni Flash Preview on the paid tier at an effective approximate output price of USD $0.10 per second of 720p video, in addition to input token billing. Pricing can change and must be rechecked before budgeting.
- The preview model/API may change response shape, availability, rate limits, regional support, and behavior.

### 7.5 Reference and iterative support

The current project supplies only one video plus text. It does not pass images, previous interaction IDs, or multiple media references. The underlying provider currently documents image input and conversational editing, but those capabilities are not integrated here.

## 8. Temporal Consistency

AI generation occurs once per full clip through a native video model. It is not per-frame generation, keyframe stylization, or independent image-to-image processing. This is the project’s main defense against flicker, identity changes, and motion inconsistency.

Additional safeguards are prompt-only:

- Strict requests to preserve framing, coordinates, motion, expression, blink, gaze, and timing.
- Whole-video input gives the model temporal context.

There is no post-generation temporal consistency measurement or correction:

- No optical-flow comparison between original and stylized clips.
- No landmark/feature alignment scoring.
- No color stabilization.
- No identity embedding check.
- No bad-frame detection or regeneration.
- No keyframe anchors or temporal latent reuse controlled by the repository.
- No frame interpolation or retiming.

Consequences:

- Native video generation should flicker less than independent per-frame stylization.
- Prompt compliance is probabilistic; geometry drift, expression changes, camera reframing, object deformation, and color shifts can still occur.
- Any model drift is highly visible at the hard portal boundary because corresponding source/stylized pixels no longer line up.
- Browser dual-video playback can add temporal misalignment up to the 0.15-second correction threshold plus seek latency.
- Python maps frames by rounded timestamp; repeated/dropped stylized frames can occur when FPS differs.

## 9. Video Pipeline

### 9.1 Decode and frame handling

| Concern | Browser | Python |
|---|---|---|
| Decode | Native HTMLVideoElement/browser codecs | `cv2.VideoCapture` |
| Frame scheduling | `requestAnimationFrame`, only on changed video time | Sequential `cap.read()` loop |
| Frame extraction files | None | None |
| Computer vision | MediaPipe JS/WASM, GPU requested | MediaPipe Python, default local delegate |
| Resize | Canvas draw stretches to source canvas | `cv2.resize` stylized frames to source W×H |
| Parallelism | Browser rendering/model internals only | Application loop is single-threaded/sequential |

Supported input codecs are not enumerated. Browser support depends on the browser/OS. Python support depends on the OpenCV build and its FFmpeg/media backend. The `accept="video/*"` attribute is only a picker hint.

### 9.2 FPS and synchronization

- Browser source playback uses media timestamps, but export requests a fixed 30 FPS canvas stream regardless of source FPS.
- The committed MP4 demonstrates browser-recorder timing variability: 136 decoded frames over ~7.92 seconds (about 17.2 average FPS) even though the stream’s nominal rate metadata is unusual.
- Python reads source FPS (or defaults to 30) and encodes at that rate.
- Python selects a stylized frame with `round(source_time × stylized_fps)`.
- Browser seeks the stylized element if drift is greater than 0.15 seconds; otherwise independent playback continues.

### 9.3 Encoding and audio

Browser:

- Codec preference order: H.264 MP4 baseline string, generic MP4, VP9 WebM, generic WebM.
- Bitrate request: 10 Mbps.
- Output: `finger-frame-ai.mp4` or `.webm`.
- Audio: absent because only `canvas.captureStream(30)` is recorded.

Python:

- Video: FFmpeg `libx264`, CRF 18, `yuv420p`, MP4.
- Audio: FFprobe checks the original; if present, a second FFmpeg pass maps the processed video and original audio, copies video, transcodes audio to AAC, and uses `-shortest`.
- Generated-video audio is ignored; original audio is the intended final soundtrack.

### 9.4 Duration mismatch behavior

- Browser does not validate that original and stylized durations match. If the stylized video ends early, portal behavior depends on the ended video’s last drawable frame and seek behavior.
- Python repeats the last successfully cached stylized frame when the requested timestamp is beyond the stylized stream. A longer stylized video is truncated by the original-frame loop.
- Both resize mismatched dimensions without preserving aspect ratio, so an aspect-ratio mismatch is stretched.

### 9.5 Temporary storage and memory risk

Browser memory can contain the original Blob, base64 string, JSON request, stylized Blob, decoded video buffers, canvas, and every export chunk simultaneously. A 15 MB compressed upload can therefore consume far more than 15 MB.

Python keeps every stylized frame read so far in `sty_frames` and never discards it. One 1280×720 BGR frame is about 2.64 MiB; 240 cached frames are roughly 633 MiB before decoder and process overhead. Longer/high-resolution videos can exhaust memory. Original frames are streamed one at a time, and encoded frames are piped directly to FFmpeg.

### 9.6 CPU/GPU

- AI generation is cloud-side.
- Browser MediaPipe requests GPU delegation; exact VRAM needs are not documented.
- Python does not configure CUDA/GPU. MediaPipe, OpenCV work, NumPy blending, and `libx264` encoding are CPU-oriented in this code.
- No batching, multiprocessing, async frame pipeline, or hardware encoder is used.

## 10. UI / UX

### 10.1 Current controls

- Password-style Gemini API key field.
- “Remember on this device” checkbox.
- Four style presets plus a custom-prompt mode.
- Drag/drop and click-to-select upload zone.
- Generate AI video button.
- Keyless placeholder button.
- Preview button.
- Export button.
- Canvas preview and compact text status/spinner.

### 10.2 Progress and errors

- Status messages cover encoding, submission, poll time/status, output wait/download, readiness, preview, and export.
- Errors from the Gemini branch are caught and shown in the status pill, with details truncated in `gemFetch`.
- Missing key and >15 MB inputs receive readable messages.
- Hand-tracker initialization has no `try/catch`, timeout, retry button, or fallback message. A failed CDN/model load can leave “Loading hand tracker…” indefinitely.
- There is no percentage/ETA, job identifier, structured error panel, diagnostics copy button, or retry of failed network requests.

### 10.3 Preview/export behavior

- The user cannot pause or scrub in the UI; the underlying video elements are hidden.
- Clicking Preview starts from the beginning.
- Export plays the full video in real time and disables Preview/Export until completion.
- There is no cancel button for generation, polling, playback, or export.
- Export downloads automatically; there is no filename/codec/resolution choice.
- Browser export silently omits audio.

### 10.4 Persistence and responsiveness

- API key persists in `localStorage` only when requested; otherwise it uses `sessionStorage`.
- Selected style and custom prompt always persist in `localStorage`.
- Uploaded video, generated output, progress, tracker state, and completed export do not survive refresh.
- There is no IndexedDB/cache recovery or resumable job.
- CSS includes a breakpoint below 560 px that changes the two-column key/style form to one column. A live 390×844 check showed no horizontal page overflow and a responsive canvas.

### 10.5 Accessibility observations

- Buttons have understandable visible names, and file selection uses a label.
- The API key/style captions are `<div>` elements rather than associated `<label>` elements.
- Status is not an `aria-live` region.
- The canvas has no textual equivalent for tracking/result state.
- Keyboard cancel/pause controls are absent.

## 11. Dependencies

### 11.1 Inventory by category

| Category | Dependency | Declaration/use |
|---|---|---|
| AI / cloud | `google-genai>=1.0` | Python Gemini client |
| AI / CV | MediaPipe hand landmarker model | Remote `.task` model, downloaded at runtime |
| Computer vision | `mediapipe>=0.10.14` | Python hand detection/tracking |
| Computer vision | `@mediapipe/tasks-vision@0.10.14` | Browser remote ES module/WASM |
| Video processing | `opencv-python>=4.9` | Python decode, resize, masks, drawing |
| Video processing | FFmpeg/FFprobe external executables | H.264 encoding and audio inspection/mux |
| Numeric utility | `numpy>=1.26` | Masks, coordinates, blending |
| Frontend | Native HTML/CSS/JS, Canvas, MediaRecorder | No package manager |
| Backend | None | — |

### 11.2 Version/reproducibility assessment

- Python requirements specify only lower bounds. They are neither exact pins nor bounded ranges and have no lock file or hashes.
- Browser MediaPipe is pinned to 0.10.14, but it is fetched live from a third-party CDN.
- The hand model URL pins float16 revision 1.
- The cloud model is a named preview endpoint; behavior can change without a repository update.
- No transitive dependency versions are captured.
- No explicit Python version is declared.
- FFmpeg is required but neither version-checked nor provisioned.

No declared package is known from repository evidence to be deprecated. The Gemini model is **preview**, which is a stability concern rather than a deprecation. No vulnerability scanner/lockfile exists, and the dependencies were not installed during this audit, so a meaningful CVE scan was not possible.

### 11.3 Compatibility and weight

- Current `google-genai` package metadata requires Python 3.10 or newer.
- Current MediaPipe package metadata lists Python 3.9–3.12. The machine’s default Python 3.14 is therefore not a safe target; use the available Python 3.12 runtime.
- MediaPipe, OpenCV, and NumPy are comparatively heavy binary dependencies.
- Loose minimum versions can eventually admit incompatible major/transitive combinations. No specific conflict was proven because resolution/install was intentionally not performed.

## 12. Environment Requirements

### 12.1 Browser application

Required:

- A modern browser with ES modules, Canvas 2D, WebAssembly, HTML video, Blob URLs, Fetch, and MediaRecorder for export.
- A local/static HTTP server; opening from `file://` is not the intended path.
- Internet access to jsDelivr, Google’s MediaPipe model storage, and—only for AI generation—the Gemini API.
- A paid-tier-capable Gemini API key for the real AI branch.
- Browser codec support for the uploaded source and at least one MediaRecorder output type.

Not required:

- Node.js/npm.
- A local GPU with specified VRAM. The browser requests GPU acceleration, but no requirement is documented.
- Local FFmpeg for browser use, unless converting a WebM export afterward.

### 12.2 Python CLI

Required:

- Recommended Python: 3.12 for current MediaPipe compatibility. Repository minimum/maximum is otherwise unspecified.
- Packages from `requirements.txt`.
- FFmpeg and FFprobe on `PATH` for `composite.py`.
- Internet access for package installation, hand-model download on first run, source-video upload, and Gemini output retrieval.
- `GEMINI_API_KEY` or `GOOGLE_API_KEY` for `stylize.py`.
- Sufficient RAM for the entire decoded stylized clip due to the cache design.

CUDA, CUDA toolkit version, and GPU VRAM are not required or configured by the Python code. Windows, macOS, and Linux are not explicitly gated, but shell examples in the README are POSIX-style and need translation on Windows.

### 12.3 Observed audit machine

- Windows / PowerShell.
- Default Python: 3.14.6.
- Additional Python available: 3.12.13 and 3.11.15.
- Node: 24.16.0 (not needed by the app).
- FFmpeg: 8.1.2 with `libx264` available.
- Declared Python packages: not installed in the checked Python 3.12 environment.

## 13. Local Run Instructions

These instructions preserve the original architecture.

### 13.1 Web app on Windows

From the repository directory:

```powershell
py -3.12 -m http.server 8124
```

Open:

```text
http://localhost:8124/
```

For the committed final example, the development query hook can load it directly:

```text
http://localhost:8124/?src=examples/final.mp4
```

Notes:

- The example is already a final composite, so it demonstrates loading/tracking/placeholder/export, not the original-to-AI transformation.
- Enter a Gemini key only if accepting the provider’s billing/privacy terms.
- Real AI editing should use a source clip no longer than the provider’s current 10-second editing limit; the UI itself does not enforce duration.

### 13.2 Python CLI on Windows

Create an isolated Python 3.12 environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Verify external video tools:

```powershell
ffmpeg -version
ffprobe -version
```

Set the key for the current PowerShell session:

```powershell
$env:GEMINI_API_KEY = "your-key-here"
```

Restyle a source video:

```powershell
.\.venv\Scripts\python.exe stylize.py input.mp4 -o stylized.mp4
```

Composite it:

```powershell
.\.venv\Scripts\python.exe composite.py input.mp4 stylized.mp4 -o final.mp4
```

For a custom CLI prompt, remember that `-p` replaces the entire default prompt. Include alignment instructions yourself:

```powershell
.\.venv\Scripts\python.exe stylize.py input.mp4 -o stylized.mp4 -p "Your style request plus explicit camera, geometry, timing, and expression preservation requirements."
```

### 13.3 Known run ambiguities/breakages

- The repository does not declare a Python version.
- README virtual-environment commands use POSIX `.venv/bin/...` paths, not Windows paths.
- `composite.py --help` imports OpenCV before argument parsing, so even help fails when dependencies are absent.
- No original/stylized sample pair is committed; only the final output is available.
- No provider account, API key, quota, or regional availability is supplied by the repository.

## 14. Test Results

No source or dependency changes were made to obtain these results.

| Check | Command/action | Result |
|---|---|---|
| Repository inventory | Recursive file listing | PASS; seven project files plus two examples, no hidden build/test config |
| Git state | `git status --short --branch` | BLOCKED; supplied directory has no `.git` metadata |
| Static HTTP serving | Python 3.12 `-m http.server 8124`; HTTP GET | PASS; `index.html` returned 200 |
| JavaScript syntax | `node --check app.js` | PASS |
| Python syntax | In-memory `ast.parse` of both scripts | PASS |
| Stylize CLI parser | Python 3.12 `stylize.py --help` | PASS; late SDK import permits help without dependency |
| Composite CLI parser | Python 3.12 `composite.py --help` | BLOCKED; `ModuleNotFoundError: cv2` before parser runs |
| Declared Python deps | Metadata/import inspection | BLOCKED; MediaPipe, OpenCV, NumPy, and google-genai not installed |
| Frontend initial UI | In-app browser at localhost | PASS; rendered controls, no initial errors |
| Sample load | `?src=examples/final.mp4` | PASS; 1280×720, ~7.92 seconds, canvas matched dimensions |
| Missing-key path | Click Generate without key | PASS; readable key/placeholder message |
| Custom prompt control | Select custom and enter text | PASS; textarea became visible and accepted input |
| Placeholder preview | Activate placeholder and Preview | PASS; source played and processing loop ran |
| MediaPipe runtime | Remote JS/WASM/model initialization during browser test | PASS with one non-fatal WebGL/OpenGL warning; no error was logged |
| Browser export | Placeholder Export | PASS by application result; status reported `Exported finger-frame-ai.mp4.` |
| Responsive layout | 390×844 temporary viewport | PASS; single-column form and no horizontal document overflow |
| Example media inspection | FFprobe | PASS; MP4 H.264 Baseline/yuv420p, 1280×720, 7.920633 s, no audio; GIF 560×315, 7.91 s |
| Real Gemini generation | Not invoked | BLOCKED; no user API key/paid quota supplied |
| Python end-to-end | Not invoked | BLOCKED; dependencies, API key, and original/stylized fixture pair absent |
| Unit/integration tests | Search for test files/config | NOT PRESENT |
| Lint/type checks | Search for configs/scripts | NOT PRESENT |
| Build | Search for build/package manifests | NOT APPLICABLE; static files have no build step |

The browser export event arrived later than the automation’s 20-second wait, but the application completed and explicitly reported a successful MP4 export immediately afterward. This illustrates that real-time processing/export can take longer than source duration on the audit machine.

## 15. Technical Debt

### Critical

No issue was classified Critical for this prototype in isolation. Before operating as a public multi-user paid service, the lack of server-side controls and privacy lifecycle would need a new threat/risk review.

### High

1. **Compositing is not perspective- or occlusion-aware.** A hard polygon reveals corresponding screen-space pixels; fingers can be overwritten and generated geometry does not behave like a surface.
2. **Alignment is probabilistic and unverified.** The portal seam depends on a preview model obeying prompt prose. No automatic registration or quality gate exists.
3. **Browser export drops audio.** This silently changes a common and valuable part of the user’s input.
4. **Long/high-resolution clips can exhaust memory.** Browser base64/chunk accumulation and Python’s unbounded decoded stylized-frame cache are the primary risks.
5. **Direct BYOK plus third-party runtime code expands credential exposure.** A remote module executes on the same origin as a browser-stored API key and uploaded video; there is no CSP/SRI protection.
6. **Preview API contract and lifecycle are fragile.** The browser compensates for multiple response shapes; neither path has robust cancellation, idempotency, structured retries, or remote-file cleanup.

### Medium

1. Wrist-x ordering can swap hand identity and corners.
2. Simple smoothing leaves jitter and lag; no offline/bidirectional stabilization exists.
3. Dropout hold freezes stale portal geometry at full presence for 25 frames.
4. One subsequent outlier can “confirm” a teleport without spatial agreement.
5. No hand foreground matte, confidence-based edge treatment, or motion blur handling.
6. Browser original/stylized playback is loosely synchronized and duration mismatch is unvalidated.
7. Browser export forces a nominal 30 FPS and depends on real-time rendering performance.
8. Stylized dimension mismatches are stretched rather than letterboxed/cropped with an explicit policy.
9. Upload validation does not cover duration, codec, decode errors, dimensions, or model limits.
10. Browser and Python tracking implementations duplicate logic and can drift over time.
11. No tests, fixtures, CI, lockfiles, dependency hashes, or reproducible environment definition.
12. Tracker/model initialization errors are not surfaced to the UI.
13. Remote uploads/output files and browser Object URLs lack explicit cleanup.
14. Python upload processing can poll forever and does not handle explicit FAILED state cleanly.

### Low

1. UI form labels/status accessibility can be improved.
2. No pause, scrub, cancel, retry, or custom export settings.
3. The footer phrase “runs entirely in your browser” can be read as implying AI is local, although generation is cloud-side.
4. README Windows commands are incomplete.
5. `composite.py --help` unnecessarily requires OpenCV.
6. Tracker constants are hardcoded and lack calibration/debug visualization.
7. Object URLs are not revoked and recorder/download URLs are not cleaned up.

## 16. Security / Privacy Concerns

### 16.1 API key handling

- The browser key is stored in session storage by default and local storage when “Remember” is checked.
- Any script executing in the same origin can read those storage values. The page imports MediaPipe code directly from jsDelivr and has no Content Security Policy or Subresource Integrity declaration.
- The key is sent in the `x-goog-api-key` request header directly to Google.
- The key can be exposed in browser debugging/session state and has no client-side quota restriction.
- A production design should prefer short-lived scoped credentials or a controlled job service; if BYOK remains, the UI must state the exposure and encourage restricted keys.

### 16.2 Video privacy/lifecycle

- The real AI branch uploads the whole source video to Google. It is not local inference.
- Python File API uploads are not explicitly deleted.
- Provider retention/training/region terms are not linked or summarized in the app.
- Uploaded videos may contain biometric data (faces and hands), minors, locations, voices, or confidential surroundings.
- Browser export drops audio, but the source audio still travels to the cloud as part of the uploaded video unless the provider/API strips it.
- `.gitignore` reduces accidental commits of common personal video formats, which is a good safeguard, but it is not a retention policy.

### 16.3 Web/supply-chain posture

- No CSP, SRI, dependency vendoring, lockfile, or automated vulnerability scan.
- Static direct API calls rely on provider CORS behavior.
- Error details and raw API responses are written to the browser console; those may contain identifiers/URIs.
- No file content validation protects against malformed media beyond browser/decoder behavior.
- No backend means there is also no repository-owned central store or server breach surface; that simplicity is beneficial for the prototype.

## 17. Reusable Components

| Component | Decision | Rationale |
|---|---|---|
| Hand detection | **Keep but improve** | MediaPipe is suitable and lightweight; add handedness/confidence/orientation logic and tests |
| Tracking state machine | **Keep but improve** | Clear baseline with useful hysteresis/dropout behavior; replace smoothing/identity matching behind same interface |
| Browser video loading | **Keep but improve** | Minimal and functional; add validation, error states, cleanup, cancellation |
| Python video decode/encode | **Keep but improve** | Streaming original frames and FFmpeg output are sound; remove stylized-frame cache and validate timestamps |
| AI generation | **Keep but improve** | Native clip-level model is appropriate for temporal consistency; add provider adapter, limits, retries, lifecycle, versioning |
| Prompt alignment suffix | **Keep but improve** | Useful intent and easy baseline; version it and verify alignment rather than trusting prose |
| Mask generation | **Replace** | Hard fill is inadequate for realistic edges/foreground hands |
| Compositing | **Replace** | Needs homography/portal coordinate system, occlusion matte, feathering, and color/edge treatment |
| Portal outline | **Keep as-is** initially | Self-contained visual treatment; can remain optional above a better compositor |
| UI | **Keep but improve** | Small, understandable flow and responsive base; add validation, recovery, progress, cancel, and audio disclosure |
| Backend | **Add when productionizing** | None exists; not needed for local BYOK prototype, needed for durable/controlled jobs and secrets |
| Storage | **Replace/add by deployment mode** | In-memory is fine for tiny clips; larger/durable workflows need scoped temporary object storage and deletion policy |
| Configuration | **Replace** | Hardcoded duplicated constants should become validated shared configuration/versioned presets |
| Placeholder effect | **Keep as-is** | Valuable free smoke test and development fallback |

## 18. Feature Feasibility Matrix

| Feature | Difficulty | Reusable current modules | New components | Main risks |
|---|---|---|---|---|
| A. Custom Prompt | **Easy** (already partially implemented) | Browser `style-custom` + `prompt()`; CLI `-p` | Validation, prompt versioning, length/safety UI, ensure CLI suffix composition | Unsafe/ambiguous prompts; alignment suffix conflicts; provider safety blocks |
| B. More Style Presets | **Easy** | `STYLES`, select control, prompt suffix | Preset schema, thumbnails/examples, versioned prompt tests | Prompt drift; misleading preview; maintenance across model versions |
| C. Reference Image | **Medium** | File/base64 path, Gemini interaction abstraction concept | Second upload control, image validation/crop, multipart input schema, reference-strength semantics, privacy copy | Style vs identity ambiguity; input limits; memory; regional/content restrictions |
| D. Better Hand Tracking | **Hard** | MediaPipe landmarks and current state machine | Handedness/identity assignment, confidence model, One-Euro/Kalman filter, optical flow, offline forward/backward smoothing, track QA/debug view | Occlusion, swaps, blur, latency, over-smoothing, device/FPS variance |
| E. Perspective-Aware Portal | **Hard** | Four-corner track, frame renderer | Canonical portal texture, homography, stable corner ordering, feathered alpha, hand matte/occlusion, GPU shader or optimized warp | Degenerate/self-crossing quads, seam artifacts, warped faces, performance |
| F. Depth / 3D Portal | **Research-level** | Portal track and future homography | Monocular/video depth, camera motion/pose, layered scene or 3D representation, parallax renderer, disocclusion/inpainting | Scale ambiguity, temporal depth flicker, missing geometry, compute cost |
| G. Portal Crossing | **Hard** | Full-frame stylized result, portal track, renderer | Portal lifecycle/state machine, screen-coverage trigger, stabilized expansion, transition compositor, audio transition, editorial controls | Tracking loss near full screen, continuity at handoff, motion sickness, model alignment |
| H. Multiple Portals | **Hard** | Detector/tracker concept, prompt presets | Gesture episode segmentation, multiple track IDs, per-event prompt/assets, timeline/job orchestration, cache/storage | Ambiguous event boundaries, API cost, overlapping portals, UI complexity |
| I. Object-Specific Transformation | **Research-level** | Video model call and future tracking timeline | Promptable segmentation, object tracking, video inpainting/edit masks, occlusion/depth reasoning, identity preservation QA | Mask drift, object deformation, inconsistent edits, unsupported provider controls |
| J. AI Director | **Medium** | Existing source video and prompt pipeline | Representative-frame sampler, vision/LLM scene analysis, structured prompt planner, user approval/edit step, safety/cost controls | Hallucinated scene details, prompt overreach, latency, privacy, reproducibility |
| K. Iterative Editing | **Hard** | Gemini Interactions API/provider capability, prompt UI | Persist interaction/job IDs, conversation state, asset/version history, rollback, compare UI, cost tracking | Cumulative drift, provider retention, escalating cost, state expiry, irreversible quality loss |

### 18.1 Feature-specific notes

#### A/B — prompt and presets

Custom prompt is already present in the browser, so Milestone 1 is refinement rather than a greenfield feature. The CLI’s prompt replacement behavior should be normalized with the browser. Presets should be data-driven rather than duplicated UI strings and prompt fragments.

#### C — reference image

The current model/provider supports image inputs, but the project must define whether the image controls style, identity, composition, or a combination. Style reference should be clearly separated from “preserve this person/object” semantics.

#### D — tracking

The highest-value structural change is a two-pass pipeline: analyze and save raw landmarks/tracks first, then stabilize and render. Offline smoothing can use future frames and interpolate short gaps, which live-only logic cannot.

#### E/F — portal geometry

A perspective portal needs a canonical 2D content plane and homography. A depth portal is a different class of system requiring scene geometry and parallax; it should not be treated as a small extension to `fillPoly`.

#### G/H — transitions and multiple events

Both need a timeline model. Treat “portal active” as an event with start, acquisition, stable, expansion/crossing, full-screen, and exit states. Multiple portals then become multiple event/assets on that timeline rather than nested conditionals in the render loop.

#### I — object editing

This is primarily a segmentation/tracking/video-inpainting problem, not just a prompt feature. Provider support for spatial masks or a separate mask-aware model will likely be required.

#### J/K — direction and editing

The provider’s conversational editing capability makes iterative editing architecturally plausible, but the current code discards interaction state. AI Director can be introduced earlier as a user-approved prompt suggestion layer; iterative re-editing needs durable versioned assets and should remain later.

## 19. Recommended Architecture Evolution

Preserve the current prototype as a baseline, then separate the pipeline into explicit artifacts and interfaces:

```text
Ingest / Validate
    ↓
Source Asset + Normalized Media Metadata
    ↓
Analysis Pass
    ├─ raw hand landmarks/confidence
    ├─ stable hand identities
    └─ portal-event candidates
    ↓
Versioned Track JSON
    ↓
Generation Provider Adapter
    ├─ prompt/preset version
    ├─ source/reference assets
    ├─ model/version/limits
    └─ generation job/result metadata
    ↓
Generated Asset + Alignment QA
    ↓
Compositor
    ├─ stabilized quad/homography
    ├─ portal texture
    ├─ hand occlusion matte
    ├─ edge/feather/color treatment
    └─ transition state
    ↓
Encoder / Audio Mux
    ↓
Final Asset + diagnostics
```

### 19.1 Key architectural recommendations

1. **Create a versioned track interchange.** Store per-frame timestamps, raw landmarks, handedness/confidence, filtered corners, presence, and event IDs. Both browser and Python paths can consume/produce it.
2. **Move to analyze-then-render for quality workflows.** This enables bidirectional smoothing, gap interpolation, manual correction, reproducible renders, and fast compositor iteration without rerunning detection.
3. **Wrap the AI provider.** Centralize model id, limits, request/response normalization, retries, cancellation, URI delivery, cost metadata, and cleanup. Do not spread preview-shape handling across UI code.
4. **Version prompts and presets.** Record the exact preset, alignment suffix, model, and parameters with every output.
5. **Add alignment QA before compositing.** Compare landmarks/features/flow between original and stylized video; warn or retry when deviation crosses thresholds.
6. **Define a portal coordinate system.** Render generated content to a canonical rectangle and map it through a homography, rather than clipping a full-screen layer.
7. **Add foreground occlusion.** Generate a temporally stable hand/arm mask and composite hands above portal content.
8. **Stream/cache bounded data.** Use timestamped seeks or a small frame ring buffer; never retain the entire decoded stylized video without an explicit memory budget.
9. **Choose deployment modes explicitly.** Keep local BYOK for the open-source demo. Add an optional backend worker/job queue/object-store path for production-scale clips, durable jobs, protected credentials, and deletion policies.
10. **Build regression fixtures before algorithm changes.** Include consented short source/stylized pairs covering successful gesture, crossing, dropout, vertical orientation, blur, portrait video, audio, and FPS mismatch.

## 20. Recommended Development Roadmap

The proposed roadmap is directionally sound, but three changes are recommended:

- Custom prompt already exists, so Milestone 1 should harden and unify it rather than implement it from scratch.
- Establish reproducible tests/fixtures and a track-data contract before changing tracking or compositing.
- Move AI Director earlier than depth/object editing; keep Depth and Object-Specific Transformation as separate research tracks.

### Milestone 0 — Reproduce and freeze the baseline

- Run web placeholder and paid AI paths with a consented source fixture.
- Create original/stylized/final golden fixtures with audio.
- Record model/prompt/output metadata.
- Add smoke tests for loading, tracker initialization, detection, composite, export, and CLI.
- Pin Python/runtime dependencies in a lock strategy without changing behavior.
- Document provider limits and privacy.

**Exit:** Original behavior is reproducible on a supported environment and measurable.

### Milestone 1 — Harden prompts, presets, validation, and provider integration

- Unify browser/CLI prompt assembly.
- Expand data-driven presets.
- Validate 10-second provider duration, file size, MIME/codec, dimensions, and aspect ratio.
- Add cancellation, structured errors, retry/backoff, URI delivery, and cleanup.
- Show expected paid-provider usage/cost and audio behavior.

**Exit:** Existing generation is reliable and understandable; no geometry change yet.

### Milestone 2 — Track artifact and stabilization

- Add raw landmark/confidence export and stable hand identity.
- Add One-Euro/Kalman baseline, optical-flow short-gap support, and offline forward/backward smoothing.
- Add track QA and optional correction/debug overlay.
- Make thresholds timestamp/FPS-aware.

**Exit:** Stable, inspectable per-frame quad tracks on regression fixtures.

### Milestone 3 — Masking, homography, and occlusion

- Introduce canonical portal coordinates and homography.
- Reject/repair degenerate or self-intersecting quads.
- Add feathered edges and temporally stable hand/arm foreground mattes.
- Add alignment and seam-quality metrics.

**Exit:** Portal behaves like a tracked planar surface and preserves foreground hands.

### Milestone 4 — Reference image support

- Add style-reference upload and clear semantics.
- Normalize/crop/validate image input.
- Record reference provenance and provider constraints.
- Add visual comparison tests.

**Exit:** Repeatable, user-controlled style reference without destabilizing alignment.

### Milestone 5 — Temporal/alignment quality system

- Measure feature/landmark/flow deviation.
- Add color stabilization and failure thresholds.
- Support regeneration/retry or user warning on misaligned output.
- Improve timestamp/FPS/duration reconciliation.

**Exit:** Temporal quality is measured rather than inferred from prompt compliance.

### Milestone 6 — Portal Crossing

- Implement portal lifecycle/timeline states.
- Add stabilized screen-fill transition and full-frame handoff.
- Preserve/transition audio intentionally.
- Add user timing controls and failure fallback.

**Exit:** Controlled normal-world → portal → full AI-world transition.

### Milestone 7 — Multiple portal events

- Segment multiple gesture episodes.
- Attach prompt/reference/generated assets to event IDs.
- Add timeline UI, caching, and cost preview.
- Define overlap/conflict rules.

**Exit:** Multiple independent, editable portal events in one video.

### Milestone 8 — AI Director and iterative editing

- Add user-approved scene analysis/prompt suggestions.
- Persist interaction IDs and versioned outputs.
- Add compare, rollback, cost, and drift warnings.

**Exit:** Directed and conversational edits remain reproducible and reversible.

### Milestone 9A — Depth / 3D Portal research track

- Benchmark temporal depth and camera/pose approaches.
- Prototype layered parallax and disocclusion handling.
- Proceed to product milestone only if quality/performance gates are met.

### Milestone 9B — Object-Specific Transformation research track

- Benchmark promptable video segmentation/tracking.
- Evaluate provider mask-conditioned video editing or separate inpainting models.
- Define identity/geometry stability tests.

Depth and object editing should not block the core 2D portal roadmap and should not be bundled into one delivery milestone.

## 21. Immediate Next Step

Complete Milestone 0 with a **consented, redistributable original/stylized/final fixture triplet** (including audio) and record one successful paid Gemini run unchanged. Then add tests around the current tracker/compositor outputs before improving them.

This is the safest next action because the supplied repository includes only a final demo, the paid path could not be exercised without credentials, and there is currently no baseline that can prove future tracking/compositing changes preserve or improve behavior.

---

## Audit Status

```text
AUDIT STATUS:
Repository: finger-frame-effect-ai-main
Original project modified: NO (only REPOSITORY_AUDIT.md added)
Original project runnable: PARTIAL
Tests: No repository test suite; static syntax/UI/placeholder/export checks passed; paid AI and Python E2E blocked
Current AI provider: Google Gemini Developer API — gemini-omni-flash-preview
Finger tracking approach: MediaPipe Hand Landmarker + two-hand fingertip quad + custom hysteresis/smoothing/dropout state machine
Generation approach: Native whole-clip video-to-video restyle, then screen-space polygon reveal
Main blocker: No API key/paid generation verification; Python dependencies and source fixture pair are absent
Biggest technical weakness: Hard, non-perspective, non-occlusion-aware compositing whose alignment relies on prompt compliance
Best component to reuse: The explicit FrameTracker/updateTracker state machine as a tested baseline
First recommended implementation milestone: Milestone 0 — reproducible fixture, paid-path baseline, and regression tests without behavior changes
```
