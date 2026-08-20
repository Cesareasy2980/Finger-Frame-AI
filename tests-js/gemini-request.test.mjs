import test from "node:test";
import assert from "node:assert/strict";

import { buildGeminiInteractionBody, GEMINI_MODEL } from "../gemini-request.js";
import { buildGenerationPrompt } from "../prompt-builder.js";

test("the selected preset and custom prompt reach the Gemini text input", () => {
  const finalPrompt = buildGenerationPrompt({
    stylePresetId: "cyberpunk",
    customPrompt: "Transform the street into futuristic Cairo.",
  });
  const body = buildGeminiInteractionBody({
    videoData: "encoded-video",
    videoMimeType: "video/mp4",
    prompt: finalPrompt,
  });

  assert.equal(body.model, "gemini-omni-flash-preview");
  assert.equal(body.model, GEMINI_MODEL);
  assert.deepEqual(body.input[0], {
    type: "video",
    mime_type: "video/mp4",
    data: "encoded-video",
  });
  assert.deepEqual(body.input[1], { type: "text", text: finalPrompt });
  assert.match(body.input[1].text, /cyberpunk/i);
  assert.match(body.input[1].text, /futuristic Cairo/);
});

test("the Gemini boundary rejects missing video data or prompt", () => {
  assert.throws(
    () => buildGeminiInteractionBody({ videoData: "", prompt: "valid" }),
    /Encoded video data is required/,
  );
  assert.throws(
    () => buildGeminiInteractionBody({ videoData: "encoded", prompt: "  " }),
    /built generation prompt is required/,
  );
});

test("video-only request remains exactly compatible with Milestone 1", () => {
  assert.deepEqual(
    buildGeminiInteractionBody({
      videoData: "encoded-video",
      videoMimeType: "video/quicktime",
      prompt: "unchanged prompt",
    }),
    {
      model: "gemini-omni-flash-preview",
      input: [
        { type: "video", mime_type: "video/quicktime", data: "encoded-video" },
        { type: "text", text: "unchanged prompt" },
      ],
    },
  );
});

test("optional reference image reaches the centralized multimodal request", () => {
  const body = buildGeminiInteractionBody({
    videoData: "encoded-video",
    prompt: "Use <IMAGE_REF_0> as appearance guidance.",
    referenceImage: { data: "encoded-image", mimeType: "image/webp" },
  });

  assert.deepEqual(body.input, [
    { type: "video", mime_type: "video/mp4", data: "encoded-video" },
    { type: "image", mime_type: "image/webp", data: "encoded-image" },
    { type: "text", text: "Use <IMAGE_REF_0> as appearance guidance." },
  ]);
  assert.deepEqual(body.generation_config, { video_config: { task: "edit" } });
});

test("reference request rejects omitted data and unsupported MIME", () => {
  assert.throws(
    () => buildGeminiInteractionBody({
      videoData: "video",
      prompt: "prompt",
      referenceImage: { data: "", mimeType: "image/png" },
    }),
    /Encoded reference image data is required/,
  );
  assert.throws(
    () => buildGeminiInteractionBody({
      videoData: "video",
      prompt: "prompt",
      referenceImage: { data: "image", mimeType: "image/gif" },
    }),
    /must be JPEG, PNG, or WebP/,
  );
});
