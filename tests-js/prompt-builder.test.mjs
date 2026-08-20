import test from "node:test";
import assert from "node:assert/strict";

import {
  BASE_PRESERVATION_INSTRUCTION,
  CUSTOM_PROMPT_MAX_LENGTH,
  DEFAULT_STYLE_ID,
  PromptValidationError,
  REFERENCE_IMAGE_GUIDANCE,
  STYLE_PRESET_IDS,
  STYLE_PRESETS,
  buildGenerationPrompt,
} from "../prompt-builder.js";

const expectedPresetIds = [
  "anime",
  "cinematic",
  "movie3d",
  "cyberpunk",
  "ancient_egypt",
  "sci_fi",
  "fantasy",
  "oil_painting",
  "cartoon",
  "realistic",
  "dark_fantasy",
  "post_apocalyptic",
  "dream_world",
  "custom",
];

test("preset IDs and default remain stable", () => {
  assert.deepEqual(STYLE_PRESET_IDS, expectedPresetIds);
  assert.equal(DEFAULT_STYLE_ID, "movie3d");
  assert.equal(STYLE_PRESETS.length, expectedPresetIds.length);
  for (const preset of STYLE_PRESETS) {
    assert.ok(preset.label);
    assert.ok(preset.description);
    assert.equal(typeof preset.prompt, "string");
    assert.equal(typeof preset.avoid, "string");
  }
});

test("Anime preset works without a custom prompt", () => {
  const prompt = buildGenerationPrompt({
    stylePresetId: "anime",
    customPrompt: "",
  });
  assert.match(prompt, /Visual style guidance:/);
  assert.match(prompt, /hand-drawn anime/i);
  assert.doesNotMatch(prompt, /Scene transformation requested by the user:/);
});

test("Cyberpunk combines style with the exact custom Cairo instruction", () => {
  const userText =
    "Transform the street into futuristic Cairo with Arabic neon signs.";
  const prompt = buildGenerationPrompt({
    stylePresetId: "cyberpunk",
    customPrompt: userText,
  });
  assert.ok(prompt.includes(userText));
  assert.match(prompt, /cyberpunk world/i);
  assert.ok(
    prompt.indexOf(userText) < prompt.indexOf("Visual style guidance:"),
    "scene intent should precede style guidance",
  );
});

test("Custom mode uses the exact trimmed user instruction", () => {
  const userText = "Transform the scene into a hand-painted dream world.";
  const prompt = buildGenerationPrompt({
    stylePresetId: "custom",
    customPrompt: `  ${userText}  `,
  });
  assert.ok(prompt.includes(userText));
  assert.doesNotMatch(prompt, /Visual style guidance:/);
  assert.doesNotMatch(prompt, /  Transform the scene/);
});

test("Custom mode rejects an empty prompt", () => {
  assert.throws(
    () => buildGenerationPrompt({ stylePresetId: "custom", customPrompt: "" }),
    (error) =>
      error instanceof PromptValidationError &&
      error.code === "custom_prompt_required",
  );
});

test("whitespace is empty for Custom and ignored for regular presets", () => {
  assert.throws(
    () => buildGenerationPrompt({ stylePresetId: "custom", customPrompt: " \n\t " }),
    (error) => error.code === "custom_prompt_required",
  );
  const anime = buildGenerationPrompt({
    stylePresetId: "anime",
    customPrompt: " \n\t ",
  });
  assert.doesNotMatch(anime, /Scene transformation requested by the user:/);
});

test("maximum length is accepted and overflow is rejected without truncation", () => {
  const maximum = "x".repeat(CUSTOM_PROMPT_MAX_LENGTH);
  const prompt = buildGenerationPrompt({
    stylePresetId: "custom",
    customPrompt: maximum,
  });
  assert.ok(prompt.includes(maximum));

  assert.throws(
    () =>
      buildGenerationPrompt({
        stylePresetId: "custom",
        customPrompt: `${maximum}x`,
      }),
    (error) => error.code === "prompt_too_long",
  );
});

test("every prompt includes the shared preservation instruction", () => {
  for (const stylePresetId of STYLE_PRESET_IDS) {
    const prompt = buildGenerationPrompt({
      stylePresetId,
      customPrompt: stylePresetId === "custom" ? "A paper-cut dream world." : "",
    });
    assert.ok(prompt.includes(BASE_PRESERVATION_INSTRUCTION));
    assert.match(prompt, /preserve the original camera motion/i);
    assert.match(prompt, /temporal sequence/i);
  }
});

test("user text is preserved verbatim except surrounding whitespace", () => {
  const userText =
    "Keep my red coat; add Cairo 2070, neon Arabic signs, rain & flying taxis!";
  const prompt = buildGenerationPrompt({
    stylePresetId: "sci_fi",
    customPrompt: `\n${userText}\n`,
  });
  assert.ok(prompt.includes(userText));
});

test("Anime plus reference image adds deterministic appearance guidance", () => {
  const prompt = buildGenerationPrompt({
    stylePresetId: "anime",
    hasReferenceImage: true,
  });
  assert.match(prompt, /hand-drawn anime/i);
  assert.ok(prompt.includes(REFERENCE_IMAGE_GUIDANCE));
  assert.match(prompt, /<IMAGE_REF_0>/);
  assert.match(prompt, /source video remains authoritative/i);
});

test("preset, exact custom text, and reference guidance compose in precedence order", () => {
  const userText = "Transform this into futuristic Cairo.";
  const prompt = buildGenerationPrompt({
    stylePresetId: "cyberpunk",
    customPrompt: userText,
    hasReferenceImage: true,
  });
  assert.ok(prompt.includes(userText));
  assert.ok(prompt.indexOf(userText) < prompt.indexOf("Visual style guidance:"));
  assert.ok(prompt.indexOf("Spatial and temporal preservation:") < prompt.indexOf("Reference image guidance:"));
});

test("Custom plus reference works while Custom validation remains active", () => {
  const prompt = buildGenerationPrompt({
    stylePresetId: "custom",
    customPrompt: "Use carved paper and soft studio light.",
    hasReferenceImage: true,
  });
  assert.match(prompt, /carved paper and soft studio light/);
  assert.match(prompt, /Reference image guidance:/);
  assert.doesNotMatch(prompt, /Visual style guidance:/);
});

test("no-reference prompt is byte-for-byte unchanged", () => {
  const implicit = buildGenerationPrompt({
    stylePresetId: "cyberpunk",
    customPrompt: "Transform this into futuristic Cairo.",
  });
  const explicit = buildGenerationPrompt({
    stylePresetId: "cyberpunk",
    customPrompt: "Transform this into futuristic Cairo.",
    hasReferenceImage: false,
  });
  assert.equal(explicit, implicit);
  assert.doesNotMatch(explicit, /Reference image guidance:/);
});
