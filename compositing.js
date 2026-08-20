// Perspective portal compositor for the browser. Python/OpenCV is the numeric reference.

import { isSelfIntersecting, quadGeometry } from "./tracking.js";

export function canonicalPortalCorners(width, height) {
  return [
    { x: 0, y: 0 }, { x: width - 1, y: 0 },
    { x: width - 1, y: height - 1 }, { x: 0, y: height - 1 },
  ];
}

function solveLinear(matrix, vector) {
  const size = vector.length;
  const rows = matrix.map((row, i) => [...row, vector[i]]);
  for (let column = 0; column < size; column++) {
    let pivot = column;
    for (let row = column + 1; row < size; row++) {
      if (Math.abs(rows[row][column]) > Math.abs(rows[pivot][column])) pivot = row;
    }
    if (Math.abs(rows[pivot][column]) < 1e-10) return null;
    [rows[column], rows[pivot]] = [rows[pivot], rows[column]];
    const divisor = rows[column][column];
    for (let i = column; i <= size; i++) rows[column][i] /= divisor;
    for (let row = 0; row < size; row++) {
      if (row === column) continue;
      const factor = rows[row][column];
      for (let i = column; i <= size; i++) rows[row][i] -= factor * rows[column][i];
    }
  }
  return rows.map((row) => row[size]);
}

export function computeHomography(source, destination) {
  if (source?.length !== 4 || destination?.length !== 4) return null;
  const a = [], b = [];
  for (let i = 0; i < 4; i++) {
    const { x, y } = source[i], { x: u, y: v } = destination[i];
    a.push([x, y, 1, 0, 0, 0, -u * x, -u * y]); b.push(u);
    a.push([0, 0, 0, x, y, 1, -v * x, -v * y]); b.push(v);
  }
  const values = solveLinear(a, b);
  return values && values.every(Number.isFinite) ? [...values, 1] : null;
}

export function projectPoint(matrix, point) {
  const scale = matrix[6] * point.x + matrix[7] * point.y + matrix[8];
  return {
    x: (matrix[0] * point.x + matrix[1] * point.y + matrix[2]) / scale,
    y: (matrix[3] * point.x + matrix[4] * point.y + matrix[5]) / scale,
  };
}

export function compositeOpacity(confidence, state) {
  if (["reset", "invalid"].includes(state) || confidence < 0.1) return 0;
  const t = Math.max(0, Math.min(1, (confidence - 0.1) / 0.55));
  const factor = { detected: 1, legacy: 1, predicted: 0.85, held: 0.65, rejected: 0.55, lost: 0.35 }[state] || 0;
  return t * t * (3 - 2 * t) * factor;
}

export function validatePortalQuad(quad, width, height) {
  if (!Array.isArray(quad) || quad.length !== 4 || !quad.every((p) => Number.isFinite(p.x) && Number.isFinite(p.y))) {
    return "malformed";
  }
  if (isSelfIntersecting(quad)) return "self_intersection";
  const signedArea = quad.reduce((sum, p, i) => {
    const q = quad[(i + 1) % 4]; return sum + p.x * q.y - q.x * p.y;
  }, 0) / 2;
  if (signedArea <= Math.max(4, width * height * 0.0001)) return "area_or_winding";
  const geometry = quadGeometry(quad);
  if (geometry.aspectRatio > 25) return "extreme_perspective";
  return null;
}

function affineForTriangle(source, destination) {
  const [s0, s1, s2] = source, [d0, d1, d2] = destination;
  const det = s0.x * (s1.y - s2.y) + s1.x * (s2.y - s0.y) + s2.x * (s0.y - s1.y);
  if (Math.abs(det) < 1e-8) return null;
  const solve = (v0, v1, v2) => [
    (v0 * (s1.y - s2.y) + v1 * (s2.y - s0.y) + v2 * (s0.y - s1.y)) / det,
    (v0 * (s2.x - s1.x) + v1 * (s0.x - s2.x) + v2 * (s1.x - s0.x)) / det,
    (v0 * (s1.x * s2.y - s2.x * s1.y) + v1 * (s2.x * s0.y - s0.x * s2.y) + v2 * (s0.x * s1.y - s1.x * s0.y)) / det,
  ];
  const x = solve(d0.x, d1.x, d2.x), y = solve(d0.y, d1.y, d2.y);
  return [x[0], y[0], x[1], y[1], x[2], y[2]];
}

function pathQuad(context, quad) {
  context.beginPath(); context.moveTo(quad[0].x, quad[0].y);
  for (let i = 1; i < 4; i++) context.lineTo(quad[i].x, quad[i].y);
  context.closePath();
}

function makeCanvas(width, height) {
  const canvas = document.createElement("canvas");
  canvas.width = width; canvas.height = height;
  return canvas;
}

export class PerspectiveCanvasCompositor {
  constructor(width, height, useOcclusion = true, useParallax = false) {
    this.width = width; this.height = height; this.useOcclusion = useOcclusion; this.useParallax = useParallax;
    this.portal = makeCanvas(width, height);
    this.mask = makeCanvas(width, height);
    this.softMask = makeCanvas(width, height);
    this.occlusion = makeCanvas(width, height);
    this.originalLayer = makeCanvas(width, height);
    this.parallaxLayer = makeCanvas(width, height);
    this.hasOcclusionMask = false;
    this.lastPortalCenter = null;
    this.lastPortalAngle = null;
  }

  featherWidth(quad) {
    const edges = quad.map((p, i) => Math.hypot(p.x - quad[(i + 1) % 4].x, p.y - quad[(i + 1) % 4].y));
    const shortSide = Math.min((edges[0] + edges[2]) / 2, (edges[1] + edges[3]) / 2);
    const scale = Math.sqrt(this.width * this.height / (320 * 180));
    return Math.max(1.5 * scale, Math.min(12 * scale, shortSide * 0.025));
  }

  drawTriangle(context, sourceElement, sourceTriangle, destinationTriangle, filter) {
    const transform = affineForTriangle(sourceTriangle, destinationTriangle);
    if (!transform) return;
    context.save();
    context.beginPath(); context.moveTo(destinationTriangle[0].x, destinationTriangle[0].y);
    context.lineTo(destinationTriangle[1].x, destinationTriangle[1].y);
    context.lineTo(destinationTriangle[2].x, destinationTriangle[2].y); context.closePath(); context.clip();
    context.setTransform(...transform); context.filter = filter || "none";
    context.drawImage(sourceElement, 0, 0, this.width, this.height);
    context.restore();
  }

  warp(sourceElement, matrix, filter) {
    const context = this.portal.getContext("2d");
    context.setTransform(1, 0, 0, 1, 0, 0); context.clearRect(0, 0, this.width, this.height);
    const columns = 12, rows = 8;
    for (let row = 0; row < rows; row++) for (let column = 0; column < columns; column++) {
      const x0 = column * this.width / columns, x1 = (column + 1) * this.width / columns;
      const y0 = row * this.height / rows, y1 = (row + 1) * this.height / rows;
      const source = [{ x:x0,y:y0 }, { x:x1,y:y0 }, { x:x1,y:y1 }, { x:x0,y:y1 }];
      const dest = source.map((point) => projectPoint(matrix, point));
      this.drawTriangle(context, sourceElement, [source[0], source[1], source[2]], [dest[0], dest[1], dest[2]], filter);
      this.drawTriangle(context, sourceElement, [source[0], source[2], source[3]], [dest[0], dest[2], dest[3]], filter);
    }
  }

  applyPortalMask(quad, feather) {
    const mask = this.mask.getContext("2d"), soft = this.softMask.getContext("2d"), portal = this.portal.getContext("2d");
    mask.clearRect(0, 0, this.width, this.height); mask.fillStyle = "white"; pathQuad(mask, quad); mask.fill();
    soft.clearRect(0, 0, this.width, this.height); soft.filter = `blur(${feather}px)`; soft.drawImage(this.mask, 0, 0); soft.filter = "none";
    soft.globalCompositeOperation = "destination-in"; soft.drawImage(this.mask, 0, 0); soft.globalCompositeOperation = "source-over";
    portal.globalCompositeOperation = "destination-in"; portal.drawImage(this.softMask, 0, 0); portal.globalCompositeOperation = "source-over";
  }

  drawOcclusion(context, originalSource, hands, portalOpacity, trackerState, influence = 1) {
    if (!this.useOcclusion) return;
    const mask = this.occlusion.getContext("2d");
    if (hands?.length) {
      mask.clearRect(0, 0, this.width, this.height);
      mask.strokeStyle = "white"; mask.fillStyle = "white"; mask.lineCap = "round"; mask.lineJoin = "round";
      for (const landmarks of hands) {
        const point = (i) => ({ x: landmarks[i].x * this.width, y: landmarks[i].y * this.height });
        const wrist = point(0), middle = point(9);
        mask.lineWidth = Math.max(5, Math.min(Math.min(this.width, this.height) * 0.08, Math.hypot(wrist.x-middle.x, wrist.y-middle.y) * 0.22));
        for (const chain of [[5,6,7,8], [2,3,4]]) {
          mask.beginPath(); mask.moveTo(point(chain[0]).x, point(chain[0]).y);
          for (const index of chain.slice(1)) mask.lineTo(point(index).x, point(index).y);
          mask.stroke();
        }
      }
      this.hasOcclusionMask = true;
    } else if (!this.hasOcclusionMask || !["predicted", "held", "rejected"].includes(trackerState?.detectionState)) {
      return;
    }
    const layer = this.originalLayer.getContext("2d"); layer.clearRect(0, 0, this.width, this.height);
    layer.drawImage(originalSource, 0, 0, this.width, this.height);
    layer.globalCompositeOperation = "destination-in"; layer.filter = "blur(0.8px)"; layer.drawImage(this.occlusion, 0, 0); layer.filter = "none";
    layer.globalCompositeOperation = "source-over";
    const recoveryFactor = hands?.length ? 1 : Math.min(1, (trackerState?.confidence || 0) / 0.65);
    context.save(); context.globalAlpha = portalOpacity * recoveryFactor * influence; context.drawImage(this.originalLayer, 0, 0); context.restore();
  }

  prepareParallaxSource(portalSource, motionQuad, transitionProgress, filter) {
    if (!this.useParallax || transitionProgress >= 1 || !motionQuad) return { source: portalSource, filter, offset: {x:0,y:0} };
    const center = motionQuad.reduce((sum, point) => ({x:sum.x+point.x/4,y:sum.y+point.y/4}), {x:0,y:0});
    const top = {x:motionQuad[1].x-motionQuad[0].x,y:motionQuad[1].y-motionQuad[0].y};
    const angle = Math.atan2(top.y, top.x);
    let dx = 0, dy = 0;
    if (this.lastPortalCenter) {
      const influence = 1 - transitionProgress;
      dx = Math.max(-this.width*.015, Math.min(this.width*.015, -(center.x-this.lastPortalCenter.x)*.18)) * influence;
      dy = Math.max(-this.height*.015, Math.min(this.height*.015, (-(center.y-this.lastPortalCenter.y)*.18 + (angle-this.lastPortalAngle)*this.height*.08))) * influence;
    }
    this.lastPortalCenter = center; this.lastPortalAngle = angle;
    const layer = this.parallaxLayer.getContext("2d"), zoom = 1.035;
    layer.setTransform(1,0,0,1,0,0); layer.clearRect(0,0,this.width,this.height);
    layer.filter = filter || "none";
    layer.drawImage(portalSource, (1-zoom)*this.width/2+dx, (1-zoom)*this.height/2+dy, this.width*zoom, this.height*zoom);
    layer.filter = "none";
    return { source:this.parallaxLayer, filter:"none", offset:{x:dx,y:dy} };
  }

  draw({ context, portalSource, originalSource, quad, motionQuad = quad, hands, trackerState, filter = "none", transitionProgress = 0 }) {
    const reason = validatePortalQuad(quad, this.width, this.height);
    transitionProgress = Math.max(0, Math.min(1, transitionProgress || 0));
    const opacity = transitionProgress > 0 ? 1 : compositeOpacity(trackerState?.confidence || 0, trackerState?.detectionState || "invalid");
    if (reason || opacity <= 0) return { applied:false, reason:reason || "confidence_gated", opacity };
    const source = canonicalPortalCorners(this.width, this.height);
    const matrix = computeHomography(source, quad);
    if (!matrix) return { applied:false, reason:"homography_failure", opacity };
    const parallax = this.prepareParallaxSource(portalSource, motionQuad, transitionProgress, filter);
    this.warp(parallax.source, matrix, parallax.filter);
    if (transitionProgress < 1) this.applyPortalMask(quad, this.featherWidth(quad) * (1-transitionProgress));
    context.save(); context.globalAlpha = opacity; context.drawImage(this.portal, 0, 0); context.restore();
    this.drawOcclusion(context, originalSource, hands, opacity, trackerState, 1-transitionProgress);
    return { applied:true, reason:null, opacity, homography:matrix, transitionProgress, parallaxOffset:parallax.offset };
  }
}
