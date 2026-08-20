export const TransitionState = Object.freeze({
  INACTIVE: "INACTIVE",
  PORTAL_VISIBLE: "PORTAL_VISIBLE",
  ENTERING: "ENTERING",
  FULL_AI: "FULL_AI",
  EXITING: "EXITING",
});

export const PORTAL_CROSSING_CONFIG = Object.freeze({
  enabled: true,
  enterCoverageThreshold: 0.50,
  fullCoverageThreshold: 0.88,
  abortCoverageThreshold: 0.34,
  exitCoverageThreshold: 0.40,
  confidenceThreshold: 0.70,
  stableFramesRequired: 3,
  abortFramesRequired: 2,
  exitFramesRequired: 3,
  growthHistoryFrames: 5,
  minimumGrowthPerFrame: 0.006,
  dropoutGraceFrames: 4,
  inactiveResetFrames: 3,
  fallbackExitFrames: 8,
});

const clamp = (value, low = 0, high = 1) => Math.max(low, Math.min(high, value));

export function smoothstep(value) {
  const t = clamp(value);
  return t * t * (3 - 2 * t);
}

function polygonArea(points) {
  if (!points || points.length < 3) return 0;
  return Math.abs(points.reduce((sum, point, index) => {
    const next = points[(index + 1) % points.length];
    return sum + point.x * next.y - next.x * point.y;
  }, 0) / 2);
}

function clipAxis(points, axis, boundary, keepGreater) {
  if (!points.length) return [];
  const output = [];
  let previous = points[points.length - 1];
  let previousInside = keepGreater ? previous[axis] >= boundary : previous[axis] <= boundary;
  for (const current of points) {
    const currentInside = keepGreater ? current[axis] >= boundary : current[axis] <= boundary;
    if (currentInside !== previousInside) {
      const delta = current[axis] - previous[axis];
      if (Math.abs(delta) > 1e-12) {
        const ratio = (boundary - previous[axis]) / delta;
        output.push({
          x: previous.x + (current.x - previous.x) * ratio,
          y: previous.y + (current.y - previous.y) * ratio,
        });
      }
    }
    if (currentInside) output.push({ x: current.x, y: current.y });
    previous = current;
    previousInside = currentInside;
  }
  return output;
}

export function portalCoverage(quad, width, height) {
  if (!Array.isArray(quad) || quad.length !== 4 || width <= 1 || height <= 1 ||
      !quad.every((point) => Number.isFinite(point.x) && Number.isFinite(point.y))) return 0;
  let clipped = quad.map((point) => ({ x: point.x, y: point.y }));
  clipped = clipAxis(clipped, "x", 0, true);
  clipped = clipAxis(clipped, "x", width - 1, false);
  clipped = clipAxis(clipped, "y", 0, true);
  clipped = clipAxis(clipped, "y", height - 1, false);
  return clamp(polygonArea(clipped) / ((width - 1) * (height - 1)));
}

export function fullFrameQuad(width, height) {
  return [
    { x: 0, y: 0 }, { x: width - 1, y: 0 },
    { x: width - 1, y: height - 1 }, { x: 0, y: height - 1 },
  ];
}

export function expandPortalQuad(quad, width, height, rawProgress) {
  const t = smoothstep(rawProgress);
  return quad.map((point, index) => {
    const target = fullFrameQuad(width, height)[index];
    return { x: point.x + (target.x - point.x) * t, y: point.y + (target.y - point.y) * t };
  });
}

export class PortalCrossingController {
  constructor(width, height, config = PORTAL_CROSSING_CONFIG, generationMetadata = {}) {
    this.width = width;
    this.height = height;
    this.config = { ...PORTAL_CROSSING_CONFIG, ...config };
    this.generationMetadata = { ...generationMetadata };
    this.reset();
  }

  reset() {
    this.state = TransitionState.INACTIVE;
    this.rawProgress = 0;
    this.lastQuad = null;
    this.lastConfidence = 0;
    this.history = [];
    this.enterCandidateFrames = 0;
    this.abortCandidateFrames = 0;
    this.exitCandidateFrames = 0;
    this.dropoutFrames = 0;
    this.frameIndex = -1;
    this.nextPortalId = 1;
    this.currentEvent = null;
    this.events = [];
  }

  setGenerationMetadata(metadata = {}) { this.generationMetadata = { ...metadata }; }

  beginEvent() {
    if (this.currentEvent) return;
    this.currentEvent = Object.freeze({
      portalId: this.nextPortalId++,
      stylePreset: this.generationMetadata.stylePreset || null,
      customPromptPresent: !!this.generationMetadata.customPromptPresent,
      referenceImagePresent: !!this.generationMetadata.referenceImagePresent,
      startFrame: this.frameIndex,
      endFrame: null,
    });
  }

  finishEvent() {
    if (!this.currentEvent) return;
    this.events.push(Object.freeze({ ...this.currentEvent, endFrame: this.frameIndex }));
    this.currentEvent = null;
  }

  appendHistory(coverage) {
    this.history.push(coverage);
    this.history = this.history.slice(-this.config.growthHistoryFrames);
    return this.history.length < 2 ? 0 :
      (this.history.at(-1) - this.history[0]) / (this.history.length - 1);
  }

  geometryProgress(coverage) {
    return clamp((coverage - this.config.enterCoverageThreshold) /
      (this.config.fullCoverageThreshold - this.config.enterCoverageThreshold));
  }

  snapshot(coverage, growth) {
    const progress = smoothstep(this.rawProgress);
    let expandedQuad = null;
    if (this.state === TransitionState.FULL_AI) expandedQuad = fullFrameQuad(this.width, this.height);
    else if (this.lastQuad) expandedQuad = expandPortalQuad(this.lastQuad, this.width, this.height, this.rawProgress);
    return Object.freeze({
      state: this.state,
      coverage,
      rawProgress: this.rawProgress,
      progress,
      confidence: this.lastConfidence,
      expandedQuad,
      portalId: this.currentEvent?.portalId || null,
      growthPerFrame: growth,
      dropoutFrames: this.dropoutFrames,
      frameIndex: this.frameIndex,
    });
  }

  update({ quad, confidence = 0, detectionState = "detected", frameIndex, forceProgress = null }) {
    this.frameIndex = Number.isInteger(frameIndex) ? frameIndex : this.frameIndex + 1;
    const coverage = portalCoverage(quad, this.width, this.height);
    const validQuad = Array.isArray(quad) && coverage > 0;
    const reliable = validQuad && confidence >= this.config.confidenceThreshold &&
      ["detected", "legacy"].includes(detectionState);
    if (validQuad) {
      this.lastQuad = quad.map((point) => ({ x: point.x, y: point.y }));
      this.lastConfidence = clamp(confidence);
    }

    if (forceProgress !== null && Number.isFinite(forceProgress)) {
      this.beginEvent();
      this.rawProgress = clamp(forceProgress);
      this.state = this.rawProgress >= 1 ? TransitionState.FULL_AI :
        this.rawProgress <= 0 ? TransitionState.PORTAL_VISIBLE : TransitionState.ENTERING;
      return this.snapshot(coverage, 0);
    }

    if (!this.config.enabled) {
      if (validQuad) { this.beginEvent(); this.state = TransitionState.PORTAL_VISIBLE; }
      else { this.finishEvent(); this.state = TransitionState.INACTIVE; }
      this.rawProgress = 0;
      return this.snapshot(coverage, 0);
    }

    const growth = reliable ? this.appendHistory(coverage) : 0;
    if (this.state === TransitionState.INACTIVE) {
      this.rawProgress = 0;
      if (validQuad && confidence >= 0.1) {
        this.beginEvent(); this.state = TransitionState.PORTAL_VISIBLE; this.dropoutFrames = 0;
      }
      return this.snapshot(coverage, growth);
    }

    if (this.state === TransitionState.PORTAL_VISIBLE) {
      this.rawProgress = 0;
      if (!validQuad) {
        this.dropoutFrames += 1;
        if (this.dropoutFrames >= this.config.inactiveResetFrames) {
          this.finishEvent(); this.state = TransitionState.INACTIVE; this.history = [];
        }
        return this.snapshot(coverage, growth);
      }
      this.dropoutFrames = 0;
      const qualifies = reliable && coverage >= this.config.enterCoverageThreshold &&
        growth >= this.config.minimumGrowthPerFrame;
      this.enterCandidateFrames = qualifies ? this.enterCandidateFrames + 1 : 0;
      if (this.enterCandidateFrames >= this.config.stableFramesRequired) {
        this.state = TransitionState.ENTERING;
        this.rawProgress = this.geometryProgress(coverage);
        this.abortCandidateFrames = 0;
      }
      return this.snapshot(coverage, growth);
    }

    if (this.state === TransitionState.ENTERING) {
      if (reliable) {
        this.dropoutFrames = 0;
        this.abortCandidateFrames = coverage < this.config.abortCoverageThreshold ? this.abortCandidateFrames + 1 : 0;
        if (this.abortCandidateFrames >= this.config.abortFramesRequired) {
          this.state = TransitionState.PORTAL_VISIBLE; this.rawProgress = 0;
        } else {
          this.rawProgress = Math.max(this.rawProgress, this.geometryProgress(coverage));
          if (coverage >= this.config.fullCoverageThreshold || this.rawProgress >= 1) {
            this.rawProgress = 1; this.state = TransitionState.FULL_AI; this.exitCandidateFrames = 0;
          }
        }
      } else {
        this.dropoutFrames += 1;
        if (this.dropoutFrames > this.config.dropoutGraceFrames) {
          this.rawProgress = 0;
          if (validQuad) this.state = TransitionState.PORTAL_VISIBLE;
          else { this.finishEvent(); this.state = TransitionState.INACTIVE; this.history = []; }
        }
      }
      return this.snapshot(coverage, growth);
    }

    if (this.state === TransitionState.FULL_AI) {
      this.rawProgress = 1;
      if (reliable) {
        this.dropoutFrames = 0;
        this.exitCandidateFrames = coverage < this.config.exitCoverageThreshold ? this.exitCandidateFrames + 1 : 0;
      } else this.dropoutFrames += 1;
      if (this.exitCandidateFrames >= this.config.exitFramesRequired ||
          this.dropoutFrames > this.config.dropoutGraceFrames) this.state = TransitionState.EXITING;
      return this.snapshot(coverage, growth);
    }

    if (reliable) {
      this.dropoutFrames = 0;
      const target = this.geometryProgress(coverage);
      this.rawProgress = Math.max(
        target,
        this.rawProgress - 1 / this.config.fallbackExitFrames,
      );
    } else {
      this.dropoutFrames += 1;
      this.rawProgress = Math.max(0, this.rawProgress - 1 / this.config.fallbackExitFrames);
    }
    if (this.rawProgress <= 0) {
      if (validQuad) { this.state = TransitionState.PORTAL_VISIBLE; this.enterCandidateFrames = 0; }
      else { this.finishEvent(); this.state = TransitionState.INACTIVE; this.history = []; }
    }
    return this.snapshot(coverage, growth);
  }

  eventMetadata() {
    return [...this.events, ...(this.currentEvent ? [this.currentEvent] : [])].map((event) => ({ ...event }));
  }
}
