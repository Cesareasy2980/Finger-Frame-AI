export const DIRECTOR_MODEL = "gemini-3.5-flash-lite";
export const DIRECTOR_MAX_OUTPUT_LENGTH = 1000;

export function buildDirectorRequest({ styleLabel, userPrompt = "", hasReferenceImage = false }) {
  const intent = String(userPrompt).trim() || styleLabel;
  if (!intent) throw new TypeError("Choose a style or enter an idea for Director assist.");
  return {
    contents: [{
      parts: [{
        text:
          "Act as a concise video transformation director. Rewrite the user's idea into one " +
          "editable production instruction, preserving their intent exactly. Describe useful " +
          "visual environment, materials, palette, and lighting details. Explicitly preserve " +
          "source camera movement, composition, subject positions, performance, timing, and " +
          "everything the user did not ask to change. Object-specific requests must remain " +
          "limited to that object. Return only the instruction, under 700 characters.\n\n" +
          `Selected style: ${styleLabel}\n` +
          `User idea: ${intent}\n` +
          `Reference image present: ${hasReferenceImage ? "yes" : "no"}`,
      }],
    }],
  };
}

export function extractDirectorText(response) {
  const text = response?.candidates?.[0]?.content?.parts
    ?.map((part) => part?.text || "")
    .join("")
    .trim();
  if (!text) throw new Error("Director returned no editable prompt.");
  return text.slice(0, DIRECTOR_MAX_OUTPUT_LENGTH);
}

