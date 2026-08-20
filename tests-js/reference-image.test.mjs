import test from "node:test";
import assert from "node:assert/strict";

import { GENERATION_CAPABILITIES } from "../generation-capabilities.js";
import {
  ReferenceImageSelection,
  ReferenceImageValidationError,
  buildReferenceImageView,
  referenceImageCapabilityState,
  validateReferenceImage,
} from "../reference-image.js";

function imageFile({ name = "reference.png", type = "image/png", size = 1024 } = {}) {
  return { name, type, size };
}

const decoded = async () => ({ width: 1200, height: 800 });

for (const type of ["image/jpeg", "image/png", "image/webp"]) {
  test(`valid ${type} reference image is accepted`, async () => {
    const metadata = await validateReferenceImage(
      imageFile({ name: `studio look.final.${type.split("/")[1]}`, type }),
      { decode: decoded },
    );
    assert.equal(metadata.mimeType, type);
    assert.deepEqual([metadata.width, metadata.height], [1200, 800]);
    assert.equal(Object.isFrozen(metadata), true);
  });
}

test("unsupported MIME is rejected before decode", async () => {
  let decodedFile = false;
  await assert.rejects(
    validateReferenceImage(imageFile({ type: "image/gif" }), {
      decode: async () => { decodedFile = true; return { width: 100, height: 100 }; },
    }),
    (error) => error instanceof ReferenceImageValidationError && error.code === "unsupported_mime",
  );
  assert.equal(decodedFile, false);
});

test("zero-byte and oversized images are rejected", async () => {
  await assert.rejects(
    validateReferenceImage(imageFile({ size: 0 }), { decode: decoded }),
    (error) => error.code === "empty_file",
  );
  await assert.rejects(
    validateReferenceImage(
      imageFile({ size: GENERATION_CAPABILITIES.referenceImage.maxBytes + 1 }),
      { decode: decoded },
    ),
    (error) => error.code === "file_too_large",
  );
});

test("corrupted image decode failure is explicit", async () => {
  await assert.rejects(
    validateReferenceImage(imageFile(), {
      decode: async () => { throw new Error("decoder rejected bytes"); },
    }),
    (error) => error.code === "decode_failed" && /could not be decoded/.test(error.message),
  );
});

test("unreasonable dimensions are rejected", async () => {
  await assert.rejects(
    validateReferenceImage(imageFile(), { decode: async () => ({ width: 16, height: 800 }) }),
    (error) => error.code === "dimensions_too_small",
  );
  await assert.rejects(
    validateReferenceImage(imageFile(), { decode: async () => ({ width: 9000, height: 800 }) }),
    (error) => error.code === "dimensions_too_large",
  );
});

test("filename edge cases remain display metadata and never determine MIME", async () => {
  const metadata = await validateReferenceImage(
    imageFile({ name: "../concept.final.GIF.exe", type: "image/png" }),
    { decode: decoded },
  );
  assert.equal(metadata.name, "../concept.final.GIF.exe");
  assert.equal(metadata.mimeType, "image/png");
});

test("replace revokes the old preview and remove resets the selection", () => {
  const created = [];
  const revoked = [];
  const urls = {
    createObjectURL(file) { const url = `blob:${file.name}`; created.push(url); return url; },
    revokeObjectURL(url) { revoked.push(url); },
  };
  const selection = new ReferenceImageSelection(urls);
  const first = imageFile({ name: "first.png" });
  const second = imageFile({ name: "second.webp", type: "image/webp" });
  selection.replace(first, { name: first.name, mimeType: first.type, width: 100, height: 100 });
  const visible = buildReferenceImageView(selection);
  assert.equal(visible.previewVisible, true);
  assert.equal(visible.chooseVisible, false);
  assert.equal(visible.previewUrl, "blob:first.png");
  assert.match(visible.metadataText, /first\.png · 100×100/);
  selection.replace(second, { name: second.name, mimeType: second.type, width: 200, height: 120 });
  assert.deepEqual(created, ["blob:first.png", "blob:second.webp"]);
  assert.deepEqual(revoked, ["blob:first.png"]);
  assert.equal(selection.file, second);

  selection.clear();
  assert.deepEqual(revoked, ["blob:first.png", "blob:second.webp"]);
  assert.equal(selection.snapshot(), null);
  assert.deepEqual(buildReferenceImageView(selection), {
    previewVisible: false,
    chooseVisible: true,
    previewUrl: null,
    metadataText: "",
  });
});

test("provider capability is centralized and matches the supported UI policy", () => {
  assert.equal(GENERATION_CAPABILITIES.supportsReferenceImage, true);
  assert.equal(GENERATION_CAPABILITIES.supportsVideoInput, true);
  assert.equal(GENERATION_CAPABILITIES.supportsVideoOutput, true);
  assert.equal(GENERATION_CAPABILITIES.supportsNegativePrompt, false);
  assert.deepEqual(
    GENERATION_CAPABILITIES.referenceImage.acceptedMimeTypes,
    ["image/jpeg", "image/png", "image/webp"],
  );
});

test("unsupported provider capability disables the UI with an explicit reason", () => {
  const state = referenceImageCapabilityState({
    model: "provider-model-without-reference",
    supportsReferenceImage: false,
  });
  assert.equal(state.enabled, false);
  assert.match(state.reason, /does not currently support/);
  assert.match(state.reason, /provider-model-without-reference/);
});
