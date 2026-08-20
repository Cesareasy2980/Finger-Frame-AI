export const MAX_VIDEO_BYTES = 15 * 1024 * 1024;
export const MAX_VIDEO_DURATION_SECONDS = 15;
export const SUPPORTED_VIDEO_TYPES = Object.freeze([
  "video/mp4",
  "video/webm",
  "video/quicktime",
]);

export const WORKFLOW_STAGES = Object.freeze([
  "Analyzing video",
  "Preparing generation",
  "Uploading media",
  "Generating AI world",
  "Tracking hand frame",
  "Building portal",
  "Rendering transition",
  "Restoring audio",
  "Finalizing video",
]);

export function validateVideoFile(file) {
  if (!file) throw new Error("Choose a video first.");
  if (!SUPPORTED_VIDEO_TYPES.includes(file.type)) {
    throw new Error("Unsupported video. Choose an MP4, WebM, or MOV file.");
  }
  if (file.size <= 0) throw new Error("This video file is empty.");
  if (file.size > MAX_VIDEO_BYTES) {
    throw new Error("This video is over the 15 MB demo limit.");
  }
  return true;
}

export function validateVideoMetadata({ duration, width, height }) {
  if (!Number.isFinite(duration) || duration <= 0 || width <= 0 || height <= 0) {
    throw new Error("The browser could not decode this video.");
  }
  if (duration > MAX_VIDEO_DURATION_SECONDS) {
    throw new Error("This video is over the 15 second demo limit.");
  }
  return true;
}

export function workflowView(state, hasVideo, hasOutput) {
  const busy = ["generating", "previewing", "exporting"].includes(state);
  return Object.freeze({
    busy,
    canGenerate: hasVideo && !busy,
    canPreview: hasOutput && !busy,
    canExport: hasOutput && !busy,
    canCancel: busy,
  });
}

export function nextWorkflowState(state, event) {
  if (event === "reset") return "empty";
  if (event === "video_loaded") return "ready";
  if (event === "generation_started") return "generating";
  if (event === "generation_finished") return "generated";
  if (event === "preview_started") return "previewing";
  if (event === "preview_finished") return "generated";
  if (event === "export_started") return "exporting";
  if (event === "export_finished") return "generated";
  if (event === "cancelled" || event === "failed") {
    return state === "generating" ? "ready" : state === "empty" ? "empty" : "generated";
  }
  return state;
}
