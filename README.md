# Finger Frame AI

Upload a recorded video containing a two-hand finger-frame gesture, and transform
the world inside that frame into an AI-generated one.

The frame your fingers make becomes a tracked, perspective-correct window onto a
restyled version of the same clip. Your fingers stay in front of the effect, the
portal can expand into a full-screen transition and collapse back again, and the
original audio survives to the final export.

---

## Overview

Most "AI video filter" demos restyle an entire frame. Finger Frame AI restyles the
clip and then reveals it **only through the quadrilateral your hands define** —
which turns a whole-frame model output into a believable in-world portal.

Doing that convincingly is mostly a tracking and compositing problem, not a
generation problem:

- The hand quadrilateral must stay **stable** across jitter, motion blur, and brief
  detection dropouts, or the portal swims.
- The reveal must be **perspective-aware**, so tilting your hands tilts the portal.
- Your fingers must **occlude** the effect, or the portal looks pasted on top.

This repository implements all three, twice — once for the browser in JavaScript
and once offline in Python — against a shared, deterministic contract with a test
suite that runs without ever calling a paid API.

## Demo

> **No demo media ships with this repository.** The clip this project was developed
> against belongs to the upstream author and shows an identifiable person, so it is
> not redistributed here. See [`NOTICE`](NOTICE).
>
> To add your own demo clip, follow [`examples/README.md`](examples/README.md).

## Features

**Workflow**
- Recorded-video workflow — upload MP4, WebM, or MOV (15 s / 15 MiB browser limit)
- Original/final side-by-side preview
- Final video export with audio preservation
- Cancel and full project reset that revokes temporary media URLs

**Generation**
- AI video-to-video restyling via Gemini Omni Flash
- 13 style presets plus fully custom prompts (1,000 characters, kept verbatim)
- Optional reference image (JPEG/PNG/WebP) to guide palette, material, and light
- **AI Director** — turns a short idea into a stronger, *editable* prompt draft
- Free local placeholder path that needs no API key

**Tracking and compositing**
- MediaPipe hand landmark detection
- Stabilized finger-frame tracking — corner identity, teleport rejection,
  adaptive smoothing, dropout prediction, confidence decay
- Perspective-aware portal via homography
- Finger occlusion, so hands render in front of the effect
- Edge feathering for a soft portal boundary
- **Portal Crossing** — the portal expands to full screen on a confident growing gesture
- Reverse transition and multiple portal events per clip
- Lightweight motion-derived parallax (2.5D, opt-out)

## How It Works

```text
Uploaded Video
      ↓
AI Video Restyle
      ↓
Hand Landmark Detection
      ↓
Stabilized Finger-Frame Tracking
      ↓
Perspective Portal
      ↓
Finger Occlusion
      ↓
Portal Crossing / Parallax
      ↓
Audio Restoration
      ↓
Final Video
```

1. **Restyle.** The whole source clip goes to the video-to-video model with a
   deterministic prompt that demands pixel-aligned, timing-preserving output.
2. **Detect.** MediaPipe returns two hands per frame. The four portal corners are
   the index fingertip and thumb tip of each hand.
3. **Stabilize.** Raw corners are validated for geometry, matched to preserve corner
   identity, filtered with velocity-adaptive smoothing, and predicted through short
   dropouts rather than snapping or freezing.
4. **Project.** A homography maps the full generated frame onto the tracked quad, so
   the portal shows a true projective view instead of a swimming crop.
5. **Occlude.** Hand landmarks mask the fingers back over the composite.
6. **Transition.** A confident, growing frame triggers Portal Crossing to full screen;
   losing the gesture reverses it and arms the next event.
7. **Restore.** FFmpeg maps the original audio to AAC against the processed video.

## Architecture

The browser and offline paths share behavior, not a runtime. Each concern is a small,
separately tested module:

| Concern | Browser | Offline (Python) |
|---|---|---|
| Prompt composition | `prompt-builder.js` | `stylize.py` |
| Provider boundary | `gemini-request.js`, `generation-capabilities.js` | `stylize.py` |
| Reference image validation | `reference-image.js` | — |
| Stabilized tracking | `tracking.js` | `stabilized_tracker.py` |
| Perspective, occlusion, parallax | `compositing.js` | `perspective_compositor.py` |
| Portal transition | `portal-crossing.js` | `portal_crossing.py` |
| Input limits and product state | `workflow.js` | CLI validation, FFprobe checks |
| Orchestration | `app.js` | `composite.py` |

Shared transition constants and matching deterministic fixtures keep the two
Portal Crossing implementations aligned.

The browser app is fully static — no backend, no bundler, no framework. The Python
CLI is an offline mastering tool and gives exact H.264, source FPS, and deterministic
audio mapping.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Vanilla JavaScript (ES modules), Canvas 2D, MediaRecorder |
| Computer vision | MediaPipe Tasks Vision, OpenCV, NumPy |
| Generative AI | Gemini Omni Flash (video-to-video), Gemini 3.5 Flash Lite (Director) |
| Media processing | FFmpeg / FFprobe |
| Runtime | Node.js 24.x, Python 3.12 |
| Testing | `node --test`, Python `unittest` |

## Installation

Requirements: **Node.js 24.x**, **Python 3.12**, and **FFmpeg/FFprobe on `PATH`**.

```bash
git clone https://github.com/ahmedsayed1911/Finger-Frame-AI.git
```

```bash
npm install
```

The browser app alone needs nothing further. For the offline pipeline:

```bash
python -m venv .venv
```

```bash
.venv/bin/python -m pip install -r requirements-lock.txt
```

On Windows use `.venv\Scripts\python` instead of `.venv/bin/python`.

Python 3.12 is required because MediaPipe does not yet publish wheels for newer
versions.

## Configuration

The browser app takes your Gemini API key **in the UI**. It is sent only to the
Google API, stored in session storage by default, and persisted to local storage
only if you opt in. It never appears in debug output.

The Python path reads an environment variable instead. Copy the template:

```bash
cp .env.example .env
```

| Variable | Used by | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | `stylize.py` | Provider-backed generation |
| `GOOGLE_API_KEY` | `stylize.py` | Alternative accepted by `google-genai` |

**No API key is required** for the placeholder preview/export path, or for any test.

## Running Locally

```bash
npm run serve
```

Open <http://127.0.0.1:8124/>.

Build the static production directory:

```bash
npm run build
```

Offline mastering, in two steps:

```bash
.venv/bin/python stylize.py input.mp4 -o stylized.mp4
```

```bash
.venv/bin/python composite.py input.mp4 stylized.mp4 -o final.mp4 --parallax
```

## Usage

1. Upload an MP4, WebM, or MOV clip (max 15 seconds, 15 MiB).
2. Pick one of 13 style presets, or write a custom transformation.
3. Optionally add one reference image (max 8 MiB, 32–8192 px per edge).
4. Optionally run **AI Director** to draft a stronger prompt, then edit it.
5. Generate with Gemini, or use the free local placeholder.
6. Compare the original and the portal result side by side.
7. Download the final video.

Development query parameters expose the validated compatibility paths:

| Parameter | Effect |
|---|---|
| `?tracking=legacy` | Original unstabilized tracker |
| `?compositing=legacy` | Flat per-pixel blend |
| `?compositing=perspective` | Perspective without occlusion |
| `?portal=only` | Disable Portal Crossing |
| `?parallax=off` | Disable parallax |
| `?transitionProgress=0.5` | Freeze the transition for visual inspection |

## Testing

No test makes a paid generation request; the provider boundary is mocked.

```bash
npm test
```

Runs syntax checks across 22 files, the frontend contract check, and 46 unit tests.

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Runs 51 Python tests. **47 are media-independent**; the 4 in
`tests/test_offline_pipeline.py` need recorded fixtures — see
[`tests/fixtures/README.md`](tests/fixtures/README.md).

```bash
.venv/bin/python scripts/validate_final_product.py
```

Runs the full deterministic offline pipeline against local fixtures and writes
H.264 output, a Portal Crossing diagnostic, preview images, and JSON metrics to
`tests/artifacts/`. Also requires recorded fixtures.

## Project Structure

```text
.
├── index.html                    Static UI, layout, styling
├── app.js                        Browser orchestration
├── tracking.js                   Stabilized finger-frame tracking
├── compositing.js                Perspective portal, occlusion, feathering
├── portal-crossing.js            Portal Crossing state machine
├── prompt-builder.js             Deterministic prompt composition
├── gemini-request.js             Provider request boundary
├── generation-capabilities.js    Provider capability declaration
├── reference-image.js            Reference image validation
├── director.js                   AI Director request boundary
├── workflow.js                   Input limits and product state
│
├── stylize.py                    Gemini video-to-video CLI
├── composite.py                  Offline frame loop, encoding, audio mux
├── stabilized_tracker.py         Stabilized tracking (Python)
├── perspective_compositor.py     Homography compositing and occlusion
├── portal_crossing.py            Portal Crossing transition logic
│
├── tests/                        Python test suite
├── tests-js/                     JavaScript test suite
├── scripts/                      Build, lint, fixture, validation tooling
├── docs/                         Architecture and engineering evidence
└── examples/                     Demo media (not published — see README there)
```

See [docs/FINAL_PRODUCT.md](docs/FINAL_PRODUCT.md) for architecture, transition
behavior, diagnostics, and test evidence. Milestone records and a full technical
audit live alongside it in [`docs/`](docs/).

## Limitations

- Gemini Omni Flash is a **preview** surface; model, region, and account availability
  can change without notice.
- Restyling is probabilistic. There is no segmentation mask, so object-specific
  instructions ("change only the car") are guidance, not a guarantee.
- One generation configuration applies to the whole clip, even though each portal
  event carries its own metadata.
- Browser export depends on `MediaRecorder`: MP4 where H.264 encoding is available,
  WebM otherwise. Use the offline path when exact mastering matters.
- Parallax is motion-derived 2.5D, not depth reconstruction.
- Portal Crossing deliberately requires a large, confidently growing frame, so it
  will not trigger in every clip.
- Tracking requires **exactly two** fully visible hands.

## Roadmap

- Per-event generation configurations, so one clip can hold several different worlds
- Explicit object masks once provider-native mask editing is reliable
- Browser-side muxing for deterministic MP4, FPS, and audio across engines
- Calibration controls for unusual lenses and intentionally small gestures
- Monocular depth, only if a lightweight model earns its cost

## License

This repository contains work under **two different copyright situations**, and
[`NOTICE`](NOTICE) is the authoritative description of both. In short:

- The original modules listed in `NOTICE` are released under the
  [MIT License](LICENSE).
- `index.html`, `app.js`, `composite.py`, and `stylize.py` are derived from
  [sophiamyang/finger-frame-effect-ai](https://github.com/sophiamyang/finger-frame-effect-ai),
  which is published **without a license**. Those files remain under the exclusive
  copyright of their original author, and no rights to them are granted here.

Please read [`NOTICE`](NOTICE) before reusing any part of this repository.

## Author

**Ahmed Sayed**

GitHub: [@ahmedsayed1911](https://github.com/ahmedsayed1911)
