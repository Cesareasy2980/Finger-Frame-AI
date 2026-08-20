# Milestone 4: Reference Image Support

**Completed:** 2026-08-15  
**Scope:** One optional reference image used upstream during AI generation.  
**Completion state:** FULL PASS.

Tracking, perspective projection, occlusion, compositing, timing, FPS, audio handling, style IDs, and the video-only generation contract are unchanged. Milestone 5 work is not included.

## 1. Provider Capability Verification

The provider was verified before implementation rather than inferred from the older video-only path.

| Evidence | Verified contract |
|---|---|
| Official [Gemini Omni Flash guide](https://ai.google.dev/gemini-api/docs/omni) (updated 2026-07-30) | `gemini-omni-flash-preview` processes text, image, audio, and video simultaneously and returns video through the Interactions API. |
| Official [video-generation overview](https://ai.google.dev/gemini-api/docs/video) | Gemini Omni is the default video model and supports simultaneous text, image, audio, and video inputs for multi-input reasoning. |
| Uploaded-video editing example | A video/document media part plus text can produce edited video. Inline base64 video is also officially supported. |
| Image/reference examples | Image parts use `{type, data, mime_type}`; `<IMAGE_REF_N>` binds uploaded images to reference roles. |
| Task contract | `generation_config.video_config.task` accepts `edit`, used on the mixed video+image branch. |
| Installed `google-genai==2.18.1` | `client.interactions.create`, Files upload/get/download/delete methods, and generic multimodal media parts are present. |

The SDK's separate Veo `generate_videos` types restrict combining some source fields. That is a different API from Gemini Omni's Interactions API and is not used here. No provider or model switch was made.

`generation-capabilities.js` is the single small capability description. It records video input/output, reference-image, negative-prompt, image-format, size/dimension, role-tag, and transport support. The UI gates the control from `supportsReferenceImage` and shows a reason if it becomes false.

This milestone did not make a paid video-generation call. Official capability and local SDK shape were verified; deterministic tests validate the exact outgoing request boundary. The preview model remains subject to provider/region availability.

## 2. User Flow

```text
source video
  + stable style preset
  + optional exact custom instruction
  + optional single reference image
      -> deterministic prompt
      -> one centralized Gemini Interactions request
      -> generated video
      -> unchanged stabilized tracker
      -> unchanged perspective + occlusion compositor
      -> final video
```

The Key & Style card now contains **Reference image (optional)**. Choose validates and previews an image. Replace opens the same single-file selector; Remove resets the selection. Video-only generation remains available and is the default.

## 3. Supported Formats and Deterministic Validation

The browser `accept` list and independent runtime validator allow:

- JPEG (`image/jpeg`)
- PNG (`image/png`)
- WebP (`image/webp`)

Application policy:

| Check | Policy |
|---|---|
| Count | Zero or one image |
| File size | Greater than zero and at most 8 MiB |
| Decoding | Must decode with the browser image decoder |
| Minimum dimensions | 32 x 32 pixels |
| Maximum dimensions | 8192 pixels on either edge |
| MIME trust | MIME must be allowed; filename extensions never grant acceptance |

Malformed bytes, unsupported MIME, empty files, oversized files, invalid dimensions, and decode failures produce inline user-facing errors before generation. The previous valid selection remains in place if an attempted replacement is invalid.

The 8 MiB/8192-pixel application limits bound request and browser memory without creative preprocessing. The original accepted bytes are sent so palette, texture, and compression characteristics are not needlessly changed. Browser preview and decode validation request EXIF-aware orientation (`imageOrientation: "from-image"`); modern browser image preview also follows mobile-photo orientation metadata. No separate thumbnail bitmap is retained.

## 4. Preview and Resource Lifecycle

`ReferenceImageSelection` owns one file, immutable metadata, and one preview object URL.

- Choosing creates one object URL.
- Replacing revokes the previous URL before creating the next.
- Removing revokes the URL, clears file/metadata, clears the file input, and hides the preview.
- Leaving/reloading the page revokes the remaining URL.
- The preview uses `object-fit: contain`; no editor or creative transform is applied.

Base64 exists only as a generation-local value while constructing the request. The app does not retain multiple decoded full-resolution copies.

## 5. Prompt Integration and Precedence

`buildGenerationPrompt` keeps the Milestone 1 function and adds only `hasReferenceImage = false`. With false or omitted, output is byte-for-byte identical to Milestone 1.

When true, the existing sections retain their order and a final deterministic section is appended:

```text
existing user scene instruction (when present)
+ existing preset and avoidance guidance (except Custom)
+ existing spatial/temporal preservation
+ reference-image guidance
```

The reference section binds `<IMAGE_REF_0>` and asks the model to use the image for palette, materials, rendering, lighting, texture, visual language, and character treatment. It explicitly keeps the video authoritative for composition, geometry, pose, object placement, camera, motion, and time, and rejects unrelated reference geometry or literal first-frame use.

These are model instructions, not pixel-level guarantees.

## 6. Central Request Architecture

`gemini-request.js` remains the only provider payload builder.

Video-only (exact Milestone 1 shape):

```javascript
{
  model: "gemini-omni-flash-preview",
  input: [
    { type: "video", mime_type: videoMime, data: videoBase64 },
    { type: "text", text: prompt }
  ]
}
```

Video plus reference:

```javascript
{
  model: "gemini-omni-flash-preview",
  input: [
    { type: "video", mime_type: videoMime, data: videoBase64 },
    { type: "image", mime_type: referenceMime, data: referenceBase64 },
    { type: "text", text: promptWithImageRef0 }
  ],
  generation_config: { video_config: { task: "edit" } }
}
```

The neutral in-app generation intent contains `stylePresetId`, `customPrompt`, and singular `referenceImage` metadata. It does not couple the image to tracking/compositing and can later grow without implementing AI Director or multiple references now.

## 7. Upload Lifecycle, Progress, and Errors

The static BYOK app uses the existing inline transport: video and optional image remain local until Generate, are base64-encoded in the browser, then are sent together directly to Google's `v1beta/interactions` endpoint. No app server or app-owned media store exists. Because the reference is inline, there is no provider temporary image-file ID to poll or delete.

Meaningful status stages are:

```text
Preparing video
Preparing reference image       # only when selected
Generating
Processing result
Perspective compositing during preview/export
```

There are no fake percentages. Image validation/preparation errors are distinct. If Gemini rejects the mixed request or generation fails while an image is selected, the error is labeled **Reference-image generation failed**. The app never silently retries without the image.

The optional Python `stylize.py` path and the tracker/compositor fixture pipeline remain unchanged; they require no reference image.

## 8. Privacy

- The image remains local on selection and preview.
- It is uploaded to Gemini only when Generate is pressed.
- It is sent inline directly from the browser with the source video, prompt, and the user's API key.
- This application does not upload it to an application server, write it to local/session storage, or persist it in IndexedDB.
- The local object URL is revoked on remove, replace, or page unload.
- No reference binary/base64, API key, or secret header is exposed through developer metadata.
- Provider-side processing/retention is governed by the applicable Google Gemini API terms; this project makes no retention guarantee.

## 9. Developer Inspection

`window.__fingerFrameDebug.generationMetadata()` returns only:

- selected style ID;
- whether custom prompt text is present;
- whether a reference is present;
- reference MIME and dimensions;
- final built prompt;
- provider capability description.

`generationIntent()` adds safe filename/size metadata for local inspection but never returns the `File`, binary, base64, key, or headers.

## 10. Deterministic Tests

Normal automation makes no network or paid generation call.

Frontend coverage includes:

- exact video-only prompt and request regressions;
- video + image + text ordering and non-omission;
- `edit` task and all three supported image MIME values;
- missing image data/unsupported MIME rejection;
- valid JPEG, PNG, and WebP;
- zero byte, oversize, corrupt, too-small, and too-large images;
- filename edge cases;
- replace/remove object-URL revocation and state reset;
- Anime + reference;
- Cyberpunk + exact custom Cairo text + reference;
- Custom + reference;
- capability values/gating and required UI wiring;
- all previous tracking and compositor browser tests.

The rendered local page was visually inspected: the optional control is clearly labeled, fits the existing responsive card, and shows the enabled capability state. Pure state tests cover preview/replace/remove because they are deterministic and do not require a native browser file-picker dialog.

Python's existing offline and provider-shape suites remain reference-free and continue to cover baseline video/audio/tracking/compositing behavior.

## 11. Regression Results

- Frontend: 36 tests passed, 0 failed.
- Python: 41 tests passed, 0 failed.
- Static production build contains the two new modules.
- Milestone 0 legacy tracker + legacy compositor SHA-256 remains `8A7903B7C03FC7B1EA642B7E08193B088B01B9DE0FB2D9ED6D41DD8DFFA37F0A`.
- Milestone 2 tracking comparison remains within its committed thresholds.
- Milestone 3 perspective/occlusion comparison remains within its committed thresholds.
- Default real fixture remains 320x180, 12 FPS, 24 H.264 frames, 2.000000 seconds, with AAC 48 kHz mono audio.

## 12. Example Flows

### Anime + studio-like reference

Choose **Anime**, leave custom text blank, and select an original/licensed studio-lighting image. The preset supplies anime rendering; `<IMAGE_REF_0>` guides palette, materials, and light while the source video supplies camera and performance.

### Cyberpunk + futuristic city reference

Choose **Cyberpunk**, enter `Transform this into futuristic Cairo`, and select an original futuristic-city concept image. The exact user text remains first, preset guidance remains intact, and the reference section guides art direction without importing its street layout.

### Custom prompt + concept-art reference

Choose **Custom**, enter `Use carved paper forms and soft theatrical light`, and select self-created concept art. No preset style is invented; the custom instruction and image guidance combine with the shared preservation contract.

No sample image was committed for this milestone, avoiding license ambiguity.

## 13. Known Provider Limitations

- Gemini Omni Flash and the Interactions API are preview contracts and can change.
- Uploaded-video editing is unavailable in some regions.
- A prompt/reference can influence rather than guarantee palette, geometry isolation, identity, or temporal consistency.
- The provider can reject requests for safety, availability, region, size, or mixed-media reasons even when the documented shape is correct.
- Inline base64 increases request memory/size; the existing 15 MiB video limit and new 8 MiB image limit bound this path.
- Automatic generation-quality assertions require a paid call and are intentionally absent from normal automation.

## 14. Readiness for Milestone 5

Milestone 4 is complete. Generation intent, provider capability, prompt, media validation, and request construction are separated cleanly, while the compositor still consumes an ordinary generated video and has no reference-aware branch. This is ready for a separately scoped Milestone 5; no Milestone 5 feature is implemented here.
