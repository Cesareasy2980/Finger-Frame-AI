// Dependency-free stabilized finger-frame tracking for the browser runtime.

export const PREDICTION_FRAMES = 3;
export const HOLD_FRAMES = 10;
export const RESET_FRAMES = 18;

const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
const signedArea = (points) => points.reduce((sum, point, i) => {
  const next = points[(i + 1) % points.length];
  return sum + point.x * next.y - next.x * point.y;
}, 0) / 2;
const cross = (a, b, c) =>
  (b.x - a.x) * (c.y - b.y) - (b.y - a.y) * (c.x - b.x);

function orientation(a, b, c) {
  const value = (b.y - a.y) * (c.x - b.x) - (b.x - a.x) * (c.y - b.y);
  if (Math.abs(value) < 1e-9) return 0;
  return value > 0 ? 1 : 2;
}

function segmentsIntersect(a, b, c, d) {
  const values = [orientation(a, b, c), orientation(a, b, d), orientation(c, d, a), orientation(c, d, b)];
  return !values.includes(0) && values[0] !== values[1] && values[2] !== values[3];
}

export function isSelfIntersecting(points) {
  return segmentsIntersect(points[0], points[1], points[2], points[3]) ||
    segmentsIntersect(points[1], points[2], points[3], points[0]);
}

function canonicalClockwise(points) {
  const center = {
    x: points.reduce((sum, point) => sum + point.x, 0) / 4,
    y: points.reduce((sum, point) => sum + point.y, 0) / 4,
  };
  let ordered = [...points].sort((a, b) =>
    Math.atan2(a.y - center.y, a.x - center.x) -
    Math.atan2(b.y - center.y, b.x - center.x));
  if (signedArea(ordered) < 0) ordered.reverse();
  const start = ordered.reduce((best, point, i) => {
    const score = point.x + point.y;
    const bestScore = ordered[best].x + ordered[best].y;
    return score < bestScore || (score === bestScore && point.y < ordered[best].y) ? i : best;
  }, 0);
  return [...ordered.slice(start), ...ordered.slice(0, start)];
}

function matchCyclic(candidate, reference) {
  const rotations = candidate.map((_, i) => [...candidate.slice(i), ...candidate.slice(0, i)]);
  return rotations.reduce((best, quad) => {
    const cost = quad.reduce((sum, point, i) => sum + distance(point, reference[i]) ** 2, 0);
    const bestCost = best.reduce((sum, point, i) => sum + distance(point, reference[i]) ** 2, 0);
    return cost < bestCost ? quad : best;
  });
}

function angleDelta(a, b) {
  return Math.abs(Math.atan2(Math.sin(a - b), Math.cos(a - b)));
}

export function quadGeometry(quad) {
  const center = {
    x: quad.reduce((sum, point) => sum + point.x, 0) / 4,
    y: quad.reduce((sum, point) => sum + point.y, 0) / 4,
  };
  const width = (distance(quad[0], quad[1]) + distance(quad[2], quad[3])) / 2;
  const height = (distance(quad[1], quad[2]) + distance(quad[3], quad[0])) / 2;
  return {
    center,
    width,
    height,
    area: Math.abs(signedArea(quad)),
    orientation: Math.atan2(quad[1].y - quad[0].y, quad[1].x - quad[0].x),
    aspectRatio: Math.max(width, height) / Math.max(Math.min(width, height), 1e-9),
  };
}

const emptyState = () => ({
  rawQuad: null,
  stabilizedQuad: null,
  confidence: 0,
  detectionState: "lost",
  isPredicted: false,
  dropoutFrames: 0,
  rejectionReason: null,
});

export class StabilizedFrameTracker {
  constructor(width, height) {
    this.width = width;
    this.height = height;
    this.diagonal = Math.hypot(width, height);
    this.reset(false);
  }

  reset(countReset = true) {
    if (countReset && this.corners) this.trackerResets += 1;
    this.corners = null;
    this.cornerStates = [];
    this.quadVelocity = { x: 0, y: 0 };
    this.confidence = 0;
    this.active = false;
    this.dropoutFrames = 0;
    this.frameIndex = 0;
    this.lastState = emptyState();
    this.trackerResets ??= 0;
  }

  validateAndOrder(rawQuad) {
    if (!Array.isArray(rawQuad) || rawQuad.length !== 4) return [null, "point_count"];
    const points = rawQuad.map((point) => ({ x: Number(point.x), y: Number(point.y) }));
    if (!points.every((point) => Number.isFinite(point.x) && Number.isFinite(point.y))) {
      return [null, "non_finite"];
    }
    const marginX = this.width * 0.2, marginY = this.height * 0.2;
    if (points.some(({ x, y }) =>
      x < -marginX || x > this.width + marginX || y < -marginY || y > this.height + marginY)) {
      return [null, "out_of_bounds"];
    }
    const minimumSeparation = Math.max(2, Math.min(this.width, this.height) * 0.01);
    for (let i = 0; i < 4; i++) {
      for (let j = i + 1; j < 4; j++) {
        if (distance(points[i], points[j]) < minimumSeparation) return [null, "duplicate_corner"];
      }
    }
    if (isSelfIntersecting(points)) return [null, "self_intersection"];
    let ordered = canonicalClockwise(points);
    if (ordered.some((_, i) => cross(ordered[i], ordered[(i + 1) % 4], ordered[(i + 2) % 4]) <= 1e-6)) {
      return [null, "non_convex"];
    }
    const geometry = quadGeometry(ordered);
    const minimumArea = this.width * this.height * (this.active ? 0.0005 : 0.005);
    if (geometry.area < minimumArea) return [null, "minimum_area"];
    if (geometry.aspectRatio > 8) return [null, "aspect_ratio"];
    if (Math.min(geometry.width, geometry.height) < minimumSeparation * 2) return [null, "collapsed_edge"];
    if (this.cornerStates.length) ordered = matchCyclic(ordered, this.cornerStates.map((state) => state.rawPosition));
    if (signedArea(ordered) <= 0) return [null, "invalid_winding"];
    return [ordered, null];
  }

  temporalRejection(candidate) {
    if (!this.cornerStates.length || !this.corners) return null;
    const vectors = candidate.map((point, i) => ({
      x: point.x - this.cornerStates[i].rawPosition.x,
      y: point.y - this.cornerStates[i].rawPosition.y,
    }));
    const magnitudes = vectors.map((vector) => Math.hypot(vector.x, vector.y)).sort((a, b) => b - a);
    const sorted = [...magnitudes].sort((a, b) => a - b);
    const median = (sorted[1] + sorted[2]) / 2;
    const isolatedThreshold = Math.max(10, this.diagonal * 0.06, median * 3 + 3);
    if (magnitudes[0] > isolatedThreshold && magnitudes[1] < magnitudes[0] * 0.45) {
      return "isolated_corner_jump";
    }
    const previous = quadGeometry(this.cornerStates.map((state) => state.rawPosition));
    const current = quadGeometry(candidate);
    const scaleRatio = Math.sqrt(current.area / Math.max(previous.area, 1e-9));
    if (scaleRatio < 0.55 || scaleRatio > 1.8) return "scale_jump";
    if (angleDelta(current.orientation, previous.orientation) > 70 * Math.PI / 180) return "orientation_flip";
    const centerMotion = distance(current.center, previous.center);
    const predictedCenter = {
      x: previous.center.x + this.quadVelocity.x,
      y: previous.center.y + this.quadVelocity.y,
    };
    if (centerMotion > this.diagonal * 0.45 && distance(current.center, predictedCenter) > this.diagonal * 0.25) {
      return "impossible_translation";
    }
    return null;
  }

  accept(rawQuad, candidate) {
    if (!this.cornerStates.length) {
      this.cornerStates = candidate.map((point) => ({
        rawPosition: point,
        filteredPosition: point,
        velocity: { x: 0, y: 0 },
        lastValidFrame: this.frameIndex,
        confidence: 0.65,
      }));
      this.corners = candidate;
      this.confidence = 0.65;
    } else {
      const vectors = candidate.map((point, i) => ({
        x: point.x - this.cornerStates[i].rawPosition.x,
        y: point.y - this.cornerStates[i].rawPosition.y,
      }));
      const meanVector = {
        x: vectors.reduce((sum, vector) => sum + vector.x, 0) / 4,
        y: vectors.reduce((sum, vector) => sum + vector.y, 0) / 4,
      };
      this.quadVelocity = {
        x: this.quadVelocity.x * 0.55 + meanVector.x * 0.45,
        y: this.quadVelocity.y * 0.55 + meanVector.y * 0.45,
      };
      const vectorSpread = vectors.reduce((sum, vector) => sum + distance(vector, meanVector), 0) / 4;
      const coherence = Math.max(0, 1 - vectorSpread / Math.max(Math.hypot(meanVector.x, meanVector.y), 4));
      const quadSpeed = Math.hypot(this.quadVelocity.x, this.quadVelocity.y);
      const predictionWeight = Math.max(0, Math.min(1, (quadSpeed - 0.6) / 0.8));
      this.corners = this.cornerStates.map((state, i) => {
        const rawVelocity = vectors[i];
        const velocity = {
          x: this.quadVelocity.x + (rawVelocity.x - meanVector.x) * 0.08,
          y: this.quadVelocity.y + (rawVelocity.y - meanVector.y) * 0.08,
        };
        const rawSpeedRatio = Math.min(1, Math.hypot(rawVelocity.x, rawVelocity.y) / (this.diagonal * 0.025));
        const intentionalSpeedRatio = Math.min(1, Math.max(0, quadSpeed - 0.6) / (this.diagonal * 0.01));
        let alpha = 0.08 + 0.58 * intentionalSpeedRatio + 0.12 * rawSpeedRatio;
        alpha = Math.min(0.9, alpha + coherence * rawSpeedRatio * 0.08);
        const predicted = {
          x: state.filteredPosition.x + velocity.x * predictionWeight,
          y: state.filteredPosition.y + velocity.y * predictionWeight,
        };
        const filtered = {
          x: predicted.x + (candidate[i].x - predicted.x) * alpha,
          y: predicted.y + (candidate[i].y - predicted.y) * alpha,
        };
        Object.assign(state, {
          rawPosition: candidate[i],
          filteredPosition: filtered,
          velocity,
          lastValidFrame: this.frameIndex,
          confidence: Math.min(1, state.confidence + 0.18),
        });
        return filtered;
      });
      this.confidence = Math.min(1, this.confidence + 0.18 - Math.min(this.dropoutFrames * 0.03, 0.18));
    }
    this.active = true;
    this.dropoutFrames = 0;
    return {
      rawQuad,
      stabilizedQuad: this.corners,
      confidence: this.confidence,
      detectionState: "detected",
      isPredicted: false,
      dropoutFrames: 0,
      rejectionReason: null,
    };
  }

  missing(rawQuad, reason) {
    if (!this.cornerStates.length || !this.corners) {
      this.confidence = 0;
      return { ...emptyState(), rawQuad, detectionState: reason ? "rejected" : "lost", rejectionReason: reason };
    }
    this.dropoutFrames += 1;
    let detectionState = reason ? "rejected" : "predicted";
    let isPredicted = false;
    if (this.dropoutFrames <= PREDICTION_FRAMES) {
      isPredicted = true;
      const decay = 0.75 ** (this.dropoutFrames - 1);
      const maximumStep = this.diagonal * 0.025;
      this.corners = this.cornerStates.map((state) => {
        let vx = state.velocity.x * decay, vy = state.velocity.y * decay;
        const speed = Math.hypot(vx, vy);
        if (speed > maximumStep) {
          vx *= maximumStep / speed;
          vy *= maximumStep / speed;
        }
        state.filteredPosition = { x: state.filteredPosition.x + vx, y: state.filteredPosition.y + vy };
        return state.filteredPosition;
      });
      this.confidence *= 0.82;
    } else if (this.dropoutFrames <= HOLD_FRAMES) {
      if (!reason) detectionState = "held";
      this.confidence *= 0.88;
    } else if (this.dropoutFrames < RESET_FRAMES) {
      if (!reason) detectionState = "lost";
      this.confidence *= 0.65;
    } else {
      const dropoutFrames = this.dropoutFrames;
      this.reset();
      return { ...emptyState(), rawQuad, detectionState: "reset", dropoutFrames, rejectionReason: reason };
    }
    return {
      rawQuad,
      stabilizedQuad: this.confidence > 0.01 ? this.corners : null,
      confidence: this.confidence,
      detectionState,
      isPredicted,
      dropoutFrames: this.dropoutFrames,
      rejectionReason: reason,
    };
  }

  update(rawQuad) {
    this.frameIndex += 1;
    if (rawQuad) {
      const [candidate, geometryReason] = this.validateAndOrder(rawQuad);
      const reason = candidate ? this.temporalRejection(candidate) : geometryReason;
      this.lastState = candidate && !reason
        ? this.accept(rawQuad.map((point) => ({ ...point })), candidate)
        : this.missing(rawQuad, reason || "malformed");
    } else {
      this.lastState = this.missing(null, null);
    }
    return this.lastState;
  }
}
