import { GENERATION_CAPABILITIES } from "./generation-capabilities.js";

const POLICY = GENERATION_CAPABILITIES.referenceImage;

export class ReferenceImageValidationError extends Error {
  constructor(message, code) {
    super(message);
    this.name = "ReferenceImageValidationError";
    this.code = code;
  }
}

export async function decodeReferenceImage(file) {
  if (typeof createImageBitmap !== "function") {
    throw new ReferenceImageValidationError(
      "This browser cannot decode reference images.",
      "decoder_unavailable",
    );
  }
  try {
    const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
    const dimensions = { width: bitmap.width, height: bitmap.height };
    bitmap.close();
    return dimensions;
  } catch {
    throw new ReferenceImageValidationError(
      "That file could not be decoded as an image. Try another JPEG, PNG, or WebP file.",
      "decode_failed",
    );
  }
}

export async function validateReferenceImage(file, { decode = decodeReferenceImage } = {}) {
  if (!file) {
    throw new ReferenceImageValidationError("Choose a reference image first.", "missing_file");
  }
  if (!POLICY.acceptedMimeTypes.includes(file.type)) {
    throw new ReferenceImageValidationError(
      "Use a JPEG, PNG, or WebP reference image.",
      "unsupported_mime",
    );
  }
  if (!Number.isFinite(file.size) || file.size <= 0) {
    throw new ReferenceImageValidationError(
      "The selected image is empty.",
      "empty_file",
    );
  }
  if (file.size > POLICY.maxBytes) {
    throw new ReferenceImageValidationError(
      `Keep the reference image under ${POLICY.maxBytes / (1024 * 1024)} MB.`,
      "file_too_large",
    );
  }

  let dimensions;
  try {
    dimensions = await decode(file);
  } catch (error) {
    if (error instanceof ReferenceImageValidationError) throw error;
    throw new ReferenceImageValidationError(
      "That file could not be decoded as an image. Try another JPEG, PNG, or WebP file.",
      "decode_failed",
    );
  }
  const width = Number(dimensions?.width);
  const height = Number(dimensions?.height);
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
    throw new ReferenceImageValidationError(
      "That file does not contain valid image dimensions.",
      "invalid_dimensions",
    );
  }
  if (width < POLICY.minDimension || height < POLICY.minDimension) {
    throw new ReferenceImageValidationError(
      `Reference images must be at least ${POLICY.minDimension}×${POLICY.minDimension} pixels.`,
      "dimensions_too_small",
    );
  }
  if (width > POLICY.maxDimension || height > POLICY.maxDimension) {
    throw new ReferenceImageValidationError(
      `Reference images must be no larger than ${POLICY.maxDimension} pixels on either edge.`,
      "dimensions_too_large",
    );
  }

  return Object.freeze({
    name: String(file.name || "reference image"),
    mimeType: file.type,
    size: file.size,
    width,
    height,
  });
}

export class ReferenceImageSelection {
  constructor(urlApi = URL) {
    this.urlApi = urlApi;
    this.file = null;
    this.metadata = null;
    this.previewUrl = null;
  }

  replace(file, metadata) {
    this.clear();
    this.file = file;
    this.metadata = metadata;
    this.previewUrl = this.urlApi.createObjectURL(file);
    return this.snapshot();
  }

  clear() {
    if (this.previewUrl) this.urlApi.revokeObjectURL(this.previewUrl);
    this.file = null;
    this.metadata = null;
    this.previewUrl = null;
  }

  snapshot() {
    return this.file
      ? Object.freeze({ file: this.file, metadata: this.metadata, previewUrl: this.previewUrl })
      : null;
  }
}

export function buildReferenceImageView(selection) {
  const selected = selection?.snapshot?.() || null;
  if (!selected) {
    return Object.freeze({
      previewVisible: false,
      chooseVisible: true,
      previewUrl: null,
      metadataText: "",
    });
  }
  const meta = selected.metadata;
  return Object.freeze({
    previewVisible: true,
    chooseVisible: false,
    previewUrl: selected.previewUrl,
    metadataText:
      `${meta.name} · ${meta.width}×${meta.height} · ${(meta.size / (1024 * 1024)).toFixed(2)} MB`,
  });
}

export function referenceImageCapabilityState(capabilities = GENERATION_CAPABILITIES) {
  const enabled = !!capabilities.supportsReferenceImage;
  return Object.freeze({
    enabled,
    reason: enabled
      ? ""
      : `${capabilities.model} does not currently support a reference image with video editing.`,
  });
}
