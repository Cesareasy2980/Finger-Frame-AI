export const GENERATION_CAPABILITIES = Object.freeze({
  provider: "Google Gemini Interactions API",
  model: "gemini-omni-flash-preview",
  supportsReferenceImage: true,
  supportsVideoInput: true,
  supportsVideoOutput: true,
  supportsNegativePrompt: false,
  referenceImage: Object.freeze({
    maxCount: 1,
    acceptedMimeTypes: Object.freeze([
      "image/jpeg",
      "image/png",
      "image/webp",
    ]),
    maxBytes: 8 * 1024 * 1024,
    minDimension: 32,
    maxDimension: 8192,
    roleTag: "<IMAGE_REF_0>",
    transport: "inline-base64",
  }),
  verifiedAgainst: Object.freeze({
    sdk: "google-genai==2.18.1",
    documentation: "https://ai.google.dev/gemini-api/docs/omni",
    verifiedOn: "2026-08-15",
  }),
});

