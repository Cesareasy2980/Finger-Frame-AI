import test from "node:test";
import assert from "node:assert/strict";
import { DIRECTOR_MODEL, buildDirectorRequest, extractDirectorText } from "../director.js";

test("Director uses the lightweight text model and preserves explicit intent", () => {
  assert.match(DIRECTOR_MODEL, /flash-lite/);
  const body = buildDirectorRequest({
    styleLabel: "Custom",
    userPrompt: "Turn only the car into a futuristic spaceship.",
    hasReferenceImage: false,
  });
  const prompt = body.contents[0].parts[0].text;
  assert.match(prompt, /only the car/);
  assert.match(prompt, /preserve/i);
  assert.match(prompt, /editable/i);
});

test("Director extraction handles provider candidates and rejects empty output", () => {
  assert.equal(extractDirectorText({ candidates: [{ content: { parts: [{ text: "  Ancient world  " }] } }] }), "Ancient world");
  assert.throws(() => extractDirectorText({ candidates: [] }), /returned no editable prompt/);
});
