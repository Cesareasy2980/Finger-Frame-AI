import { GENERATION_CAPABILITIES } from "./generation-capabilities.js";

export const GEMINI_MODEL = GENERATION_CAPABILITIES.model;

export function buildGeminiInteractionBody({
  videoData,
  videoMimeType = "video/mp4",
  prompt,
  referenceImage = null,
}) {
  if (typeof videoData !== "string" || !videoData) {
    throw new TypeError("Encoded video data is required.");
  }
  if (typeof prompt !== "string" || !prompt.trim()) {
    throw new TypeError("A built generation prompt is required.");
  }

  const body = {
    model: GEMINI_MODEL,
    input: [
      {
        type: "video",
        mime_type: videoMimeType || "video/mp4",
        data: videoData,
      },
      { type: "text", text: prompt },
    ],
  };

  if (!referenceImage) return body;
  if (!GENERATION_CAPABILITIES.supportsReferenceImage) {
    throw new TypeError(`Reference images are not supported by ${GEMINI_MODEL}.`);
  }
  if (typeof referenceImage.data !== "string" || !referenceImage.data) {
    throw new TypeError("Encoded reference image data is required.");
  }
  if (!GENERATION_CAPABILITIES.referenceImage.acceptedMimeTypes.includes(referenceImage.mimeType)) {
    throw new TypeError("Reference image must be JPEG, PNG, or WebP.");
  }

  body.input.splice(1, 0, {
    type: "image",
    mime_type: referenceImage.mimeType,
    data: referenceImage.data,
  });
  body.generation_config = { video_config: { task: "edit" } };
  return body;
}
