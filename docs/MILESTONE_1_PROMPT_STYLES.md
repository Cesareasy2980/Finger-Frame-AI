# Milestone 1: Custom Prompt and Style Presets

**Completed:** 2026-08-15  
**Scope:** Style selection, optional scene intent, deterministic prompt construction, and the existing Gemini request boundary.  
**Explicitly unchanged:** Hand detection/tracking, polygon geometry, masks, compositing, video timing, encoding, audio, offline fixtures, and provider/model.

## 1. Feature Overview

The browser application now separates two user decisions:

- **Style** selects the visual treatment.
- **Describe your transformation** optionally states what the scene should become.

The Custom style requires a transformation description. Every other preset works without text and can optionally be combined with scene intent.

The default remains the original project’s 3D animated-movie direction, so the basic flow is unchanged:

```text
upload video → choose style → generate
```

## 2. Style Preset Architecture

All browser preset data lives in `prompt-builder.js` as immutable `STYLE_PRESETS`. UI option labels, descriptions, prompt fragments, stable IDs, and avoidance guidance are read from this one configuration.

| Stable ID | Display name | Intent |
|---|---|---|
| `anime` | Anime | Hand-drawn line art and cel shading |
| `cinematic` | Cinematic | Premium live-action lighting and grading |
| `movie3d` | 3D | Original project’s stylized CGI look |
| `cyberpunk` | Cyberpunk | Neon technology and futuristic atmosphere |
| `ancient_egypt` | Ancient Egypt | Historically inspired architecture and materials |
| `sci_fi` | Sci-Fi | Believable advanced technology |
| `fantasy` | Fantasy | Magical, crafted environments |
| `oil_painting` | Oil Painting | Layered brushwork and canvas texture |
| `cartoon` | Cartoon | Bold shapes and clean graphic color |
| `realistic` | Realistic Transformation | Photorealistic materials and light |
| `custom` | Custom | User instruction supplies transformation/style direction |

`movie3d` remains the default and retains its old internal ID to preserve the project’s default behavior and existing saved preference.

The provider does not expose a dedicated negative-prompt field in the current contract. Optional `avoid` text is therefore included as clearly labeled guidance in the ordinary text instruction rather than sent as a separate unsupported parameter.

## 3. Prompt Builder

`buildGenerationPrompt({ stylePresetId, customPrompt })` is a pure deterministic function. It has no DOM, storage, file, network, or Gemini dependency.

The builder validates and normalizes input, then produces labeled sections in a stable order:

```text
Scene transformation requested by the user:   # only when user text exists
...

Visual style guidance:                         # all presets except Custom
...

Avoidance guidance:                            # when configured
...

Spatial and temporal preservation:             # always
...
```

### Precedence policy

1. **Preset only:** preset visual-style guidance + avoidance guidance + shared preservation instruction.
2. **Preset + custom:** exact trimmed user scene intent first, then preset style/avoidance guidance, then shared preservation instruction.
3. **Custom only:** exact trimmed user instruction + shared preservation instruction; no additional preset style is invented.

The builder trims only leading/trailing whitespace. It does not paraphrase, sanitize, truncate, or silently rewrite user text.

## 4. Base Spatial-Preservation Instructions

`BASE_PRESERVATION_INSTRUCTION` is one reusable constant in `prompt-builder.js`. Every generated prompt asks Gemini to preserve, as closely as the model allows:

- Camera motion.
- Framing and field of view.
- Shot boundaries.
- Subject position and scale.
- Temporal sequence.
- Overall geometry.
- Motion/performance timing.
- Facial expression timing, mouth openness, blinks, and gaze.
- Consistency across the full clip.

It also asks the model not to introduce zooms, crops, recentering, scene cuts, or invented performance. The wording explicitly treats these as model goals and does not claim guaranteed pixel alignment.

## 5. UI Behavior

The existing Key & Style card now contains:

```text
Style
[ preset selector ]
[ short preset description ]

Describe your transformation (optional / required)
[ textarea ]
[ validation message ]                         [ count / 1000 ]
```

- Preset options are populated from `STYLE_PRESETS`; labels are not duplicated in HTML.
- The preset description updates immediately.
- The transformation textarea is always visible so users understand that scene intent can complement a preset.
- The label shows **required** only for Custom.
- Blank/whitespace Custom text is blocked before credential or network checks.
- Inline validation and the existing status pill show a useful message.
- Non-Custom presets proceed without custom text.
- The existing `ai-style` and `ai-style-custom` local preference keys are retained.
- Unknown/removed saved preset IDs safely fall back to `movie3d`.

No upload, preview, tracking, compositing, or export UI was redesigned.

## 6. Gemini Integration

The generation handler builds the final prompt before encoding/submitting. It passes that exact string to `buildGeminiInteractionBody`, whose result is serialized into the existing `POST v1beta/interactions` call.

The following remain unchanged:

- Provider: Google Gemini Developer API.
- Model: `gemini-omni-flash-preview`.
- Inline base64 video upload.
- Video MIME handling.
- Poll interval/timeout.
- Response-shape detection.
- Base64/URI output retrieval.
- Error handling after submission.

`gemini-request.js` is a small pure boundary helper. Tests prove that the prompt returned by the builder becomes `input[1].text`, while the video remains `input[0]`. Automated tests do not call Gemini.

The Python provider path remains available and unchanged in behavior. Its explicit `-p/--prompt` option still accepts a fully assembled prompt for operator/batch use.

## 7. Validation Rules

| Rule | Behavior |
|---|---|
| Unknown preset ID | Rejected |
| Non-Custom + blank text | Valid; uses preset |
| Non-Custom + text | Valid; combines user intent and preset |
| Custom + blank/whitespace | Rejected with `custom_prompt_required` |
| Surrounding whitespace | Trimmed |
| Maximum length | 1,000 characters after trimming |
| More than 1,000 characters | Rejected with `prompt_too_long`; never truncated |
| User punctuation/casing/content | Preserved verbatim after trim |

The HTML textarea also uses `maxlength="1000"`, while the pure builder independently enforces the same contract for non-UI callers and tests.

## 8. Tests

### Frontend unit/contract tests

```powershell
npm.cmd test
```

Result:

```text
11 tests passed
0 failed
```

Coverage:

- Stable preset IDs and default ID.
- Anime preset without custom text.
- Cyberpunk plus exact Cairo instruction.
- Custom mode with valid text.
- Empty and whitespace Custom rejection.
- Whitespace ignored for normal presets.
- Exact maximum accepted and overflow rejected.
- Shared preservation instruction in every prompt.
- User text preserved without rewriting.
- Built prompt reaches the Gemini request text input.
- Missing prompt/video rejected at the pure request boundary.
- Required UI IDs, module imports, model ID, and Hand Landmarker baseline.

### Live browser validation

The source and production build were loaded locally without paid calls.

- All 11 expected preset labels rendered.
- The custom textarea rendered and remained visible.
- Empty Custom submission showed inline and status validation.
- Anime with empty custom text passed prompt validation and reached the existing missing-key gate.
- Cyberpunk displayed the correct description and optional state.
- The developer prompt helper was present in application code; pure output is covered directly by Node tests.
- Placeholder fixture preview completed at 2.0 seconds.
- No browser errors were logged; MediaPipe emitted its existing non-fatal OpenGL diagnostic warning.

### Python tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Result:

```text
13 tests passed
0 failed
```

## 9. Regression Results

Milestone 0’s offline fixture was rendered again after Milestone 1.

| Baseline property | Milestone 0 | Milestone 1 | Result |
|---|---:|---:|---|
| Frames processed | 24 | 24 | Unchanged |
| Raw valid quad frames | 24 | 24 | Unchanged |
| Output quad frames | 24 | 24 | Unchanged |
| Detection success | 1.0 | 1.0 | Unchanged |
| Average mean movement | 6.731233 px | 6.731233 px | Unchanged |
| Maximum mean jump | 16.815957 px | 16.815957 px | Unchanged |
| Dropout-held/rejected/reset | 0 / 0 / 0 | 0 / 0 / 0 | Unchanged |
| Valid/invalid polygons | 24 / 0 | 24 / 0 | Unchanged |
| Mask area min/max/avg | 0.124896 / 0.140816 / 0.133668 | Same | Unchanged |
| Output | 320×180, 12 FPS, 24 frames | Same | Unchanged |
| Duration | 2.000000 s | 2.000000 s | Unchanged |
| Audio | AAC, 48 kHz mono | Same | Unchanged |

The complete output MP4 was byte-identical:

```text
Milestone 0 SHA-256:
8A7903B7C03FC7B1EA642B7E08193B088B01B9DE0FB2D9ED6D41DD8DFFA37F0A

Milestone 1 regression SHA-256:
8A7903B7C03FC7B1EA642B7E08193B088B01B9DE0FB2D9ED6D41DD8DFFA37F0A
```

`composite.py` also retained its Milestone 0 SHA-256:

```text
BCFFE0741C0819DC2018759DA51ED34BE142672981038829985D541482E4C178
```

## 10. Developer Prompt Inspection

Two non-production inspection paths are available:

1. Pure import in Node/tests:

```javascript
import { buildGenerationPrompt } from "./prompt-builder.js";

console.log(buildGenerationPrompt({
  stylePresetId: "cyberpunk",
  customPrompt: "Transform the street into futuristic Cairo.",
}));
```

2. Browser developer console on the running application:

```javascript
window.__fingerFrameDebug.buildPrompt()
window.__fingerFrameDebug.presets
```

The hook returns data only when a developer explicitly requests it. No internal preservation text was added to the normal visible UI or automatically logged during generation.

## 11. Known Model Limitations

- Prompted spatial/temporal preservation is a request, not a guarantee. Model output can still drift.
- The current provider contract has no dedicated negative-prompt parameter; avoidance text shares the main prompt.
- More detailed custom instructions can conflict with a preset or preservation goals.
- The 1,000-character application limit does not represent the provider’s full context limit; it is a deliberate UX/reproducibility bound.
- The model is a preview endpoint, so behavior and availability may change.
- Automated tests validate request construction but cannot validate generation quality without a paid call.
- Reference images, masks, portal IDs, scene analysis, director prompts, and multi-turn editing are intentionally not implemented.

The pure input shape can later be extended by a neutral generation configuration containing fields such as `referenceImage`, `objectMask`, `portalId`, `sceneAnalysis`, or `directorPrompt`; Milestone 1 does not add unused fields.

## 12. Example Final Prompts

### Anime

```text
Visual style guidance:
Render the scene as polished hand-drawn anime with clean line art, expressive detail, cel shading, and vibrant but coherent colors.

Avoidance guidance:
Avoid photorealistic skin and inconsistent line weight.

Spatial and temporal preservation:
Treat this as a visual transformation of the supplied source video. Preserve the original camera motion, framing, field of view, shot boundaries, subject positions and scale, temporal sequence, and overall scene geometry as closely as the model allows. Keep source motion and performance timing aligned, including facial expression timing, mouth openness, blinks, and gaze; do not invent new performance. Apply the requested transformation consistently across the full clip without adding zooms, crops, recentering, or scene cuts.
```

### Cyberpunk + futuristic Cairo

```text
Scene transformation requested by the user:
Transform the street into futuristic Cairo with Arabic neon signs.

Visual style guidance:
Transform the visual style into a detailed cyberpunk world with neon technology, atmospheric haze, reflective surfaces, and deep cinematic contrast.

Avoidance guidance:
Avoid illegible visual clutter and random camera effects.

Spatial and temporal preservation:
Treat this as a visual transformation of the supplied source video. Preserve the original camera motion, framing, field of view, shot boundaries, subject positions and scale, temporal sequence, and overall scene geometry as closely as the model allows. Keep source motion and performance timing aligned, including facial expression timing, mouth openness, blinks, and gaze; do not invent new performance. Apply the requested transformation consistently across the full clip without adding zooms, crops, recentering, or scene cuts.
```

### Ancient Egypt

```text
Visual style guidance:
Transform the scene into a richly detailed Ancient Egyptian world with historically inspired architecture, carved stone, gold accents, textiles, and warm desert light.

Avoidance guidance:
Avoid modern signage, modern vehicles, and unrelated fantasy motifs.

Spatial and temporal preservation:
Treat this as a visual transformation of the supplied source video. Preserve the original camera motion, framing, field of view, shot boundaries, subject positions and scale, temporal sequence, and overall scene geometry as closely as the model allows. Keep source motion and performance timing aligned, including facial expression timing, mouth openness, blinks, and gaze; do not invent new performance. Apply the requested transformation consistently across the full clip without adding zooms, crops, recentering, or scene cuts.
```

### Custom

```text
Scene transformation requested by the user:
Transform the scene into a hand-painted dream world.

Spatial and temporal preservation:
Treat this as a visual transformation of the supplied source video. Preserve the original camera motion, framing, field of view, shot boundaries, subject positions and scale, temporal sequence, and overall scene geometry as closely as the model allows. Keep source motion and performance timing aligned, including facial expression timing, mouth openness, blinks, and gaze; do not invent new performance. Apply the requested transformation consistently across the full clip without adding zooms, crops, recentering, or scene cuts.
```

Milestone 2 has not begun.
