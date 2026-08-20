# Milestone 0 Baseline Validation

**Validated:** 2026-08-15  
**Scope:** Reproducibility, observability, and regression coverage only.  
**Behavior policy:** No product feature, UI, AI provider, hand detector, tracking threshold, mask rule, compositor rule, or output codec rule was intentionally changed.

## 1. Environment

### Validated runtime versions

| Component | Baseline version | Source of truth |
|---|---:|---|
| Python | 3.12.13, 64-bit | `.python-version` |
| Node.js | 24.16.0 | `.nvmrc`, `package.json` |
| npm | 11.13.0 | `package.json`, `package-lock.json` |
| FFmpeg | 8.1.2 full build with `libx264` | External executable used for validation |
| FFprobe | 8.1.2 | External executable used for validation |
| Browser MediaPipe Tasks Vision | 0.10.14 | Existing pinned CDN import in `app.js` |
| Python MediaPipe | 0.10.14 | `requirements.txt` |
| OpenCV | 4.11.0.86 (`opencv-contrib-python`) | `requirements.txt` |
| NumPy | 1.26.4 | `requirements.txt` |
| Google Gen AI SDK | 2.18.1 | `requirements.txt` |
| Gemini model | `gemini-omni-flash-preview` | Existing constants in `app.js` and `stylize.py` |
| Hand model | float16 revision 1 `hand_landmarker.task` | Existing Google model URL |

The downloaded hand model observed during validation had SHA-256:

```text
FBC2A30080C3C557093B5DDFC334698132EB341044CCEE322CCF8BCF3607CDE1
```

`requirements-lock.txt` captures the full Python resolution for CPython 3.12.13 on Windows x86-64. `requirements.txt` contains the four direct dependencies. OpenCV Contrib is pinned instead of installing both `opencv-python` and `opencv-contrib-python`: MediaPipe already requires the Contrib distribution, both expose the same `cv2` files, and installing both made the effective version dependent on installation order.

OpenCV 4.11.0.86 is the preserved baseline because that was the effective transitive runtime on the first successful pre-instrumentation pipeline run. Forcing 4.9 changed a small number of mask-edge pixels; restoring 4.11 reproduced the pre-instrumentation decoded video frames exactly.

No JavaScript runtime packages are needed by the application. The npm files provide deterministic validation/build/server commands using Node built-ins only.

## 2. Installation Commands

### Windows / PowerShell

Install or select Python 3.12.13, Node 24.16.0/npm 11.13.0, and FFmpeg 8.1.2 with `ffmpeg` and `ffprobe` on `PATH`.

```powershell
python --version
node --version
npm.cmd --version
ffmpeg -version
ffprobe -version
```

The expected first three version lines are:

```text
Python 3.12.13
v24.16.0
11.13.0
```

Create and install the fully locked Python environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip check
```

Install the no-dependency frontend tooling lock:

```powershell
npm.cmd install --ignore-scripts
```

Expected npm audit result for this baseline: zero dependency vulnerabilities because there are no installed JavaScript packages.

## 3. Frontend Validation

### Commands

```powershell
npm.cmd run lint
npm.cmd test
npm.cmd run build
npm.cmd run serve
```

The frontend is intentionally still a static application. The build copies `index.html`, `app.js`, and `examples/` to `dist/` without bundling, transforming, minifying, or changing runtime behavior.

### Results

| Validation | Result |
|---|---|
| `npm install --ignore-scripts` | PASS; lock installed, zero external packages |
| JavaScript syntax checks | PASS |
| Required DOM/model/tracker contract check | PASS |
| Static production build | PASS |
| Development server HTTP response | PASS; HTTP 200 |
| Source frontend in browser | PASS |
| Production `dist/` in browser | PASS |
| Fixture auto-load | PASS; 320×180, 2.0 s |
| MediaPipe model initialization | PASS; UI reached `Hand tracker ready.` |
| Placeholder preview | PASS; fixture played through to 2.0 s |
| Browser console | No errors; one non-fatal MediaPipe WebGL/OpenGL diagnostic warning |

There is no TypeScript or static type checker in the original architecture, so type checking is **not applicable**. `node --check` and the explicit frontend contract script provide syntax/structure validation without introducing a compiler or framework.

For an independent production-build server:

```powershell
python -m http.server 8125 --bind 127.0.0.1 --directory dist
```

Then open `http://127.0.0.1:8125/`.

## 4. Python Validation

### Installed direct dependency check

```text
mediapipe=0.10.14
cv2=4.11.0
numpy=1.26.4
google-genai=2.18.1
```

`python -m pip check` reported `No broken requirements found.`

### Validated pipeline stages

| Stage | Result | Evidence |
|---|---|---|
| Original video loading | PASS | OpenCV decoded 24 frames |
| Stylized video loading | PASS | OpenCV decoded paired fixture |
| Frame processing | PASS | 24 frames processed sequentially |
| MediaPipe hand detection | PASS | Two-hand result produced valid raw quad on all 24 fixture frames |
| Tracker operation | PASS | 24 output quad frames; metrics emitted |
| Polygon generation | PASS | 24 valid polygon frames |
| Mask generation/blend | PASS | Non-zero mask area series on all frames |
| H.264 encoding | PASS | FFmpeg produced H.264/yuv420p MP4 |
| Audio mux | PASS | Original synthetic AAC tone survived as AAC audio |
| Metrics JSON | PASS | Tracker, compositor, timing, and FFprobe metadata written |

The normal offline command remains the original two-input pipeline. `--metrics` is optional and has no effect on pixels:

```powershell
.\.venv\Scripts\python.exe composite.py `
  tests/fixtures/finger_frame_short.mp4 `
  tests/fixtures/finger_frame_short_stylized.mp4 `
  -o tests/artifacts/finger_frame_short_final.mp4 `
  --metrics tests/artifacts/baseline_metrics.json
```

An output generated after adding metrics had frame-by-frame decoded MD5 values identical to an output generated immediately before instrumentation. This establishes that the counters did not change the valid-input visual behavior.

## 5. Test Fixture Description

### Files

```text
tests/fixtures/
├── finger_frame_short.mp4
└── finger_frame_short_stylized.mp4
```

### Provenance and construction

Both fixtures are derived only from the repository’s committed `examples/final.mp4`; no external or randomly downloaded media was used.

- `finger_frame_short.mp4`: first 2 seconds, scaled to 320×180, 12 FPS, H.264/yuv420p, plus a generated 440 Hz mono AAC tone at 48 kHz for audio-preservation testing.
- `finger_frame_short_stylized.mp4`: deterministic hue/saturation/contrast transform of the short fixture, H.264/yuv420p, video-only. It substitutes for the pre-generated AI output during offline tests.

The committed example is already a finished portal composite. Therefore this fixture is suitable for repeatable detector/tracker/compositor regression, but it is not a pristine real-world “original” and cannot measure generation quality.

Recreate both fixtures:

```powershell
.\.venv\Scripts\python.exe scripts/create_fixtures.py
```

Observed SHA-256 hashes with FFmpeg 8.1.2:

```text
finger_frame_short.mp4
C07498B9D56C5352FFC67FBBA6BA1E83272F6EAE1FAEAB48607C4CD121C98217

finger_frame_short_stylized.mp4
E4BB59AA7D32B807D746B4310FB71FB7B4670D52911B62ADEB6CB1B3B7A0FA9D
```

The media bytes can vary with a different FFmpeg/libx264 build even when decoded content and metadata are equivalent. Regression assertions therefore use behavior and decoded metadata, not fixture container hashes.

## 6. Tracker Metrics

Metrics for the validated fixture pair:

| Metric | Baseline |
|---|---:|
| Frames processed | 24 |
| Raw valid quad frames | 24 |
| Visible/output quad frames | 24 |
| Detection success rate | 1.000000 |
| Average mean corner movement | 6.731233 px |
| Maximum mean corner jump | 16.815957 px |
| Dropout-held frames | 0 |
| Rejected jumps | 0 |
| Tracker resets | 0 |

Definitions:

- **Raw valid quad** means `compute_quad` passed two-hand spread and area gates on that frame.
- **Visible/output quad** includes raw detections and any stale quad retained by dropout hold/presence fade.
- Movement is the mean of the four per-corner distances between the new candidate and the previous filtered quad before smoothing.
- A rejected jump is the existing >30%-frame-width first-jump branch.

Unit tests separately exercise the 25-frame dropout hold, fade/reset, minimum-alpha smoothing, and first-jump reject/second-jump accept behavior because the clear fixture does not naturally trigger those states.

## 7. Compositing Metrics

| Metric | Baseline |
|---|---:|
| Processed frames | 24 |
| Valid polygon frames | 24 |
| Invalid polygon frames | 0 |
| Minimum mask area / frame | 0.124896 |
| Maximum mask area / frame | 0.140816 |
| Average mask area / frame | 0.133668 |
| Output dimensions | 320×180 |
| Output FPS | 12.0 |
| Observed total processing time | 1.329907 s |

`baseline_metrics.json` also contains a `{frame, ratio}` mask-area entry for every valid frame. Processing time is diagnostic and will vary by CPU, model cache state, FFmpeg build, and system load; it is not asserted as a deterministic test value.

## 8. Output Video Metadata

Validated `tests/artifacts/finger_frame_short_final.mp4`:

| Property | Value |
|---|---|
| Container | MP4 |
| Duration | 2.000000 s |
| File size | 113,605 bytes |
| Overall bitrate | 454,420 bit/s |
| Video codec | H.264 (`libx264` output) |
| Pixel format | yuv420p by encoder configuration |
| Resolution | 320×180 |
| Frame rate | 12/1 constant |
| Video frames read | 24 |
| Audio | Present |
| Audio codec | AAC |
| Audio rate/channels | 48,000 Hz, mono |

Audio validation passed: the original fixture contains the synthetic AAC tone, the stylized fixture has no audio, and the final MP4 contains AAC audio sourced from the original. This validates the existing FFprobe/FFmpeg mux path.

The existing browser export still records canvas video only and omits audio. That known behavior was intentionally not changed in Milestone 0.

## 9. Test Results

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Result on the final baseline:

```text
Ran 13 tests
OK
```

Coverage includes:

- Exact two-hand requirement.
- Anatomical corner order.
- Finger-spread and polygon-area rejection.
- Minimum-alpha smoothing behavior.
- First large-jump rejection and second-jump acceptance.
- 25-frame dropout hold and eventual tracker reset.
- Tracker metric accounting.
- Missing and undecodable input rejection.
- Real fixture MediaPipe detection and tracking.
- Mask/polygon/compositing metrics.
- H.264 MP4 metadata.
- Original-audio preservation.
- Gemini model/request structure.
- Pinned SDK client surface without network or generation.

Frontend checks:

```powershell
npm.cmd test
```

Result:

```text
Frontend baseline contract passed
```

## 10. AI Provider Readiness

The paid generation path remains optional and unchanged in provider/model intent.

Verified without network/generation:

- Environment variables accepted: `GEMINI_API_KEY` or `GOOGLE_API_KEY`.
- SDK initializes with the pinned `google-genai==2.18.1`.
- SDK exposes required `files.upload/get/download`, `interactions.create/get`, and `models.get` clients.
- Model constant remains `gemini-omni-flash-preview`.
- Python interaction input remains one uploaded document URI plus one text prompt.
- Existing output handling still accepts inline `output_video.data` or a file URI.
- Missing credentials fail before any upload/request.

An additive, non-generative connectivity check is available once a valid key is supplied:

```powershell
$env:GEMINI_API_KEY = "your-key"
.\.venv\Scripts\python.exe stylize.py --check
```

`--check` calls only `models.get` for the configured model. It does not upload a video or request generation. No connectivity check was sent during this validation because no key was present.

To run the paid path deliberately after the check:

```powershell
.\.venv\Scripts\python.exe stylize.py input.mp4 -o stylized.mp4
```

## 11. Known Blockers

1. A real paid Gemini generation was not run because no API key/account/quota was supplied.
2. The repository still lacks a pristine consented original + genuine AI-stylized fixture pair. The local pair is derived from the already-composited example.
3. Provider availability, regional restrictions, billing, and preview response behavior cannot be proven without an authorized account.
4. The MediaPipe model remains a runtime download rather than a committed artifact; its observed hash is documented above.
5. FFmpeg is an external dependency. The repository records the validated version but does not install the binary.
6. The supplied workspace has no `.git` metadata, so verification uses hashes/tests rather than commit diff/history.

## 12. Known Limitations

- The baseline deliberately retains the non-perspective hard polygon composite, no hand occlusion matte, and existing tracker thresholds.
- Browser export remains silent.
- Browser MediaPipe and Python MediaPipe use the same 0.10.14 version but separate implementations/delegates.
- The small, clear fixture’s 100% detection rate is not representative of difficult motion, occlusion, lighting, portrait framing, or hand crossing.
- MediaPipe emits non-fatal TensorFlow Lite feedback/protobuf warnings under the pinned environment.
- The lock was resolved for Windows x86-64; other operating systems should preserve direct versions but may resolve platform-specific wheels differently.
- Exact encoding bytes and processing time can vary across FFmpeg builds/hardware.
- The new input validation only improves errors for missing/undecodable media; valid-media rendering remains unchanged.

## 13. Exact Commands to Reproduce Everything

From repository root in PowerShell:

```powershell
# 1. Verify exact external runtimes.
python --version
node --version
npm.cmd --version
ffmpeg -version
ffprobe -version

# 2. Install locked environments.
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip check
npm.cmd install --ignore-scripts

# 3. Validate/build the static frontend.
npm.cmd run lint
npm.cmd test
npm.cmd run build

# 4. Recreate the local non-AI fixtures.
.\.venv\Scripts\python.exe scripts/create_fixtures.py

# 5. Run every Python regression test, including offline E2E.
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

# 6. Generate the retained baseline output and metrics.
New-Item -ItemType Directory -Force tests\artifacts | Out-Null
.\.venv\Scripts\python.exe composite.py `
  tests/fixtures/finger_frame_short.mp4 `
  tests/fixtures/finger_frame_short_stylized.mp4 `
  -o tests/artifacts/finger_frame_short_final.mp4 `
  --metrics tests/artifacts/baseline_metrics.json

# 7. Independently inspect the final output.
ffprobe -v error -count_frames `
  -show_entries "format=duration,size,bit_rate:stream=index,codec_name,codec_type,width,height,avg_frame_rate,r_frame_rate,nb_frames,nb_read_frames,sample_rate,channels" `
  -of json tests/artifacts/finger_frame_short_final.mp4

# 8. Run the source frontend.
npm.cmd run serve
# Open http://127.0.0.1:8124/?src=tests/fixtures/finger_frame_short.mp4

# 9. In a second terminal, optionally serve the production build.
python -m http.server 8125 --bind 127.0.0.1 --directory dist
# Open http://127.0.0.1:8125/

# 10. Optional safe provider connectivity check; no generation/upload.
$env:GEMINI_API_KEY = "your-key"
.\.venv\Scripts\python.exe stylize.py --check
```

Milestone 0 does not authorize or begin Milestone 1.
