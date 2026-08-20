export const CUSTOM_PROMPT_MAX_LENGTH = 1000;
export const DEFAULT_STYLE_ID = "movie3d";

export const BASE_PRESERVATION_INSTRUCTION =
  "Treat this as a visual transformation of the supplied source video. " +
  "Preserve the original camera motion, framing, field of view, shot " +
  "boundaries, subject positions and scale, temporal sequence, and overall " +
  "scene geometry as closely as the model allows. Keep source motion and " +
  "performance timing aligned, including facial expression timing, mouth " +
  "openness, blinks, and gaze; do not invent new performance. Apply the " +
  "requested transformation consistently across the full clip without " +
  "adding zooms, crops, recentering, or scene cuts.";

export const REFERENCE_IMAGE_GUIDANCE =
  "Use <IMAGE_REF_0> only as a visual appearance and art-direction reference " +
  "for palette, materials, rendering style, lighting, texture, visual language, " +
  "and character treatment where relevant. The source video remains authoritative " +
  "for composition, spatial layout, pose, object placement, motion, camera movement, " +
  "and temporal sequence. Preserve the source composition and motion; do not copy " +
  "unrelated geometry or scene structure from the reference image. Keep the referenced " +
  "visual treatment consistent throughout the full clip. Use the image as a reference " +
  "for video generation, not as a literal initial frame.";

export const STYLE_PRESETS = Object.freeze(
  [
    {
      id: "anime",
      label: "Anime",
      description: "Clean hand-drawn line art, cel shading, and vibrant color.",
      prompt:
        "Render the scene as polished hand-drawn anime with clean line art, " +
        "expressive detail, cel shading, and vibrant but coherent colors.",
      avoid: "Avoid photorealistic skin and inconsistent line weight.",
    },
    {
      id: "cinematic",
      label: "Cinematic",
      description: "Premium live-action grading, lighting, and atmosphere.",
      prompt:
        "Give the scene a premium cinematic live-action treatment with " +
        "intentional lighting, natural depth, controlled contrast, and " +
        "cohesive film color grading.",
      avoid: "Avoid changing the camera path or introducing new shots.",
    },
    {
      id: "movie3d",
      label: "3D",
      description: "The original project look: expressive stylized CGI.",
      prompt:
        "Transform the person and scene into a 3D animated movie style with " +
        "stylized CGI detail, expressive features, and soft cinematic lighting.",
      avoid: "Avoid flat 2D line art and stop-motion texture.",
    },
    {
      id: "cyberpunk",
      label: "Cyberpunk",
      description: "Neon technology, deep contrast, and a futuristic city mood.",
      prompt:
        "Transform the visual style into a detailed cyberpunk world with neon " +
        "technology, atmospheric haze, reflective surfaces, and deep cinematic contrast.",
      avoid: "Avoid illegible visual clutter and random camera effects.",
    },
    {
      id: "ancient_egypt",
      label: "Ancient Egypt",
      description: "Monumental Egyptian architecture, materials, and warm desert light.",
      prompt:
        "Transform the scene into a richly detailed Ancient Egyptian world " +
        "with historically inspired architecture, carved stone, gold accents, " +
        "textiles, and warm desert light.",
      avoid: "Avoid modern signage, modern vehicles, and unrelated fantasy motifs.",
    },
    {
      id: "sci_fi",
      label: "Sci-Fi",
      description: "Advanced technology and believable speculative design.",
      prompt:
        "Transform the scene into a sophisticated science-fiction world with " +
        "believable advanced technology, refined materials, and cinematic environmental detail.",
      avoid: "Avoid arbitrary text, logos, and visually noisy interface overlays.",
    },
    {
      id: "fantasy",
      label: "Fantasy",
      description: "Magical atmosphere, crafted environments, and storybook detail.",
      prompt:
        "Transform the scene into an immersive fantasy world with magical " +
        "atmosphere, handcrafted environmental detail, and luminous storybook color.",
      avoid: "Avoid unrelated modern props unless the user explicitly requests them.",
    },
    {
      id: "oil_painting",
      label: "Oil Painting",
      description: "Layered brushwork, canvas texture, and painterly light.",
      prompt:
        "Render the video as a richly layered oil painting with visible " +
        "brushwork, subtle canvas texture, painterly edges, and coherent light and color.",
      avoid: "Avoid watercolor washes and flat vector shapes.",
    },
    {
      id: "cartoon",
      label: "Cartoon",
      description: "Bold shapes, readable expressions, and clean graphic color.",
      prompt:
        "Transform the scene into a polished cartoon with bold readable shapes, " +
        "clean contours, appealing expressions, and consistent graphic color.",
      avoid: "Avoid photorealistic texture and unstable mixed rendering styles.",
    },
    {
      id: "realistic",
      label: "Realistic Transformation",
      description: "Photorealistic materials and lighting while retaining the source scene.",
      prompt:
        "Apply a polished photorealistic transformation with physically " +
        "plausible materials, natural lighting, and coherent fine detail while " +
        "keeping the subject recognizable.",
      avoid: "Avoid illustration, exaggerated anatomy, and artificial plastic texture.",
    },
    {
      id: "dark_fantasy",
      label: "Dark Fantasy",
      description: "Moody mythic environments, dramatic silhouettes, and restrained magic.",
      prompt:
        "Transform the scene into a refined dark-fantasy world with moody mythic architecture, " +
        "dramatic silhouettes, weathered materials, restrained supernatural detail, and cinematic low-key light.",
      avoid: "Avoid excessive gore, unreadable darkness, and unrelated horror imagery.",
    },
    {
      id: "post_apocalyptic",
      label: "Post-Apocalyptic",
      description: "Weathered environments, reclaimed materials, and dramatic natural light.",
      prompt:
        "Transform the scene into a believable post-apocalyptic environment with weathered structures, " +
        "reclaimed materials, atmospheric dust, resilient vegetation, and dramatic natural light.",
      avoid: "Avoid changing the source action or adding unrelated crowds and vehicles.",
    },
    {
      id: "dream_world",
      label: "Dream World",
      description: "Surreal color, soft atmosphere, and coherent dreamlike forms.",
      prompt:
        "Transform the scene into an elegant dream world with surreal but coherent forms, luminous color, " +
        "soft atmospheric depth, and gently uncanny visual details.",
      avoid: "Avoid chaotic geometry, strobing color, and abrupt scene changes.",
    },
    {
      id: "custom",
      label: "Custom",
      description: "Use your description as the transformation and style direction.",
      prompt: "",
      avoid: "",
    },
  ].map((preset) => Object.freeze(preset)),
);

export const STYLE_PRESET_IDS = Object.freeze(
  STYLE_PRESETS.map((preset) => preset.id),
);

export class PromptValidationError extends Error {
  constructor(message, code) {
    super(message);
    this.name = "PromptValidationError";
    this.code = code;
  }
}

export function getStylePreset(stylePresetId) {
  return STYLE_PRESETS.find((preset) => preset.id === stylePresetId) || null;
}

export function validatePromptSelection({ stylePresetId, customPrompt = "" }) {
  const preset = getStylePreset(stylePresetId);
  if (!preset) {
    throw new PromptValidationError("Choose a valid style preset.", "invalid_preset");
  }

  const trimmedCustomPrompt = String(customPrompt).trim();
  if (trimmedCustomPrompt.length > CUSTOM_PROMPT_MAX_LENGTH) {
    throw new PromptValidationError(
      `Keep your transformation description under ${CUSTOM_PROMPT_MAX_LENGTH} characters.`,
      "prompt_too_long",
    );
  }
  if (preset.id === "custom" && !trimmedCustomPrompt) {
    throw new PromptValidationError(
      "Describe the transformation you want when using the Custom style.",
      "custom_prompt_required",
    );
  }

  return { preset, customPrompt: trimmedCustomPrompt };
}

export function buildGenerationPrompt({
  stylePresetId,
  customPrompt = "",
  hasReferenceImage = false,
}) {
  const selection = validatePromptSelection({ stylePresetId, customPrompt });
  const sections = [];

  if (selection.customPrompt) {
    sections.push(
      `Scene transformation requested by the user:\n${selection.customPrompt}`,
    );
  }
  if (selection.preset.id !== "custom") {
    sections.push(`Visual style guidance:\n${selection.preset.prompt}`);
    if (selection.preset.avoid) {
      sections.push(`Avoidance guidance:\n${selection.preset.avoid}`);
    }
  }
  sections.push(
    `Spatial and temporal preservation:\n${BASE_PRESERVATION_INSTRUCTION}`,
  );
  if (hasReferenceImage) {
    sections.push(`Reference image guidance:\n${REFERENCE_IMAGE_GUIDANCE}`);
  }

  return sections.join("\n\n");
}
