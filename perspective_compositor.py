"""Perspective-aware, feathered, finger-occluding portal compositing."""

from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Sequence

import cv2
import numpy as np

from stabilized_tracker import is_self_intersecting


Point = tuple[float, float]
Quad = tuple[Point, Point, Point, Point]

WRIST, THUMB_CMC, THUMB_MCP, THUMB_IP, THUMB_TIP = 0, 1, 2, 3, 4
INDEX_MCP, INDEX_PIP, INDEX_DIP, INDEX_TIP, MIDDLE_MCP = 5, 6, 7, 8, 9


@dataclass(frozen=True)
class CompositeResult:
    frame: np.ndarray
    warped_portal: np.ndarray
    portal_alpha: np.ndarray
    occlusion_alpha: np.ndarray
    homography: np.ndarray | None
    applied: bool
    compositing_state: str
    opacity: float
    feather_px: float
    rejection_reason: str | None = None
    transition_progress: float = 0.0
    expanded_quad: Quad | None = None
    parallax_offset: Point = (0.0, 0.0)


def canonical_portal_corners(width: int, height: int) -> np.ndarray:
    """Clockwise TL/TR/BR/BL plane spanning the generated frame."""
    return np.array(
        [(0.0, 0.0), (width - 1.0, 0.0), (width - 1.0, height - 1.0), (0.0, height - 1.0)],
        dtype=np.float32,
    )


def _signed_area(quad: np.ndarray) -> float:
    x, y = quad[:, 0], quad[:, 1]
    return float((np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2.0)


def _cross(a, b, c) -> float:
    return float((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]))


def _polygon_area(quad: np.ndarray) -> float:
    return abs(_signed_area(quad))


def _edge_lengths(quad: np.ndarray) -> np.ndarray:
    return np.linalg.norm(quad - np.roll(quad, -1, axis=0), axis=1)


def confidence_opacity(confidence: float, detection_state: str) -> float:
    """Conservative opacity gate shared by tests and runtime."""
    if detection_state in {"reset", "invalid"} or confidence < 0.1:
        return 0.0
    t = float(np.clip((confidence - 0.1) / 0.55, 0.0, 1.0))
    opacity = t * t * (3.0 - 2.0 * t)
    state_factor = {
        "detected": 1.0,
        "legacy": 1.0,
        "predicted": 0.85,
        "held": 0.65,
        "rejected": 0.55,
        "lost": 0.35,
    }.get(detection_state, 0.0)
    return float(np.clip(opacity * state_factor, 0.0, 1.0))


def validate_homography(
    quad: Sequence[Point], width: int, height: int
) -> tuple[np.ndarray | None, str | None, float, float]:
    """Return validated source-to-quad H, rejection, mean/max reprojection error."""
    try:
        destination = np.asarray(quad, dtype=np.float64)
    except (TypeError, ValueError):
        return None, "malformed", math.inf, math.inf
    if destination.shape != (4, 2):
        return None, "point_count", math.inf, math.inf
    if not np.isfinite(destination).all():
        return None, "non_finite", math.inf, math.inf
    if is_self_intersecting([tuple(point) for point in destination]):
        return None, "self_intersection", math.inf, math.inf
    crosses = [_cross(destination[i], destination[(i + 1) % 4], destination[(i + 2) % 4]) for i in range(4)]
    if min(crosses) <= 1e-6:
        return None, "invalid_winding_or_collinear", math.inf, math.inf
    area = _polygon_area(destination)
    if area < max(4.0, width * height * 0.0001):
        return None, "minimum_area", math.inf, math.inf
    edges = _edge_lengths(destination)
    if edges.min() < 2.0 or edges.max() / edges.min() > 25.0:
        return None, "extreme_perspective", math.inf, math.inf

    frame_polygon = np.array([(0, 0), (width - 1, 0), (width - 1, height - 1), (0, height - 1)], np.float32)
    visible_area, _ = cv2.intersectConvexConvex(destination.astype(np.float32), frame_polygon)
    if visible_area / area < 0.02:
        return None, "mostly_offscreen", math.inf, math.inf

    source = canonical_portal_corners(width, height)
    matrix = cv2.getPerspectiveTransform(source, destination.astype(np.float32))
    if not np.isfinite(matrix).all() or abs(float(np.linalg.det(matrix))) < 1e-10:
        return None, "singular_homography", math.inf, math.inf
    if abs(matrix[2, 2]) < 1e-12:
        return None, "invalid_normalization", math.inf, math.inf
    matrix = matrix / matrix[2, 2]
    if np.linalg.cond(matrix) > 1e9:
        return None, "ill_conditioned_homography", math.inf, math.inf
    projected = cv2.perspectiveTransform(source.reshape(1, -1, 2), matrix)[0]
    errors = np.linalg.norm(projected - destination, axis=1)
    if not np.isfinite(errors).all() or float(errors.max()) > 0.5:
        return None, "reprojection_error", float(errors.mean()), float(errors.max())
    return matrix, None, float(errors.mean()), float(errors.max())


def adaptive_feather_width(quad: Sequence[Point], width: int, height: int) -> float:
    points = np.asarray(quad, dtype=np.float64)
    edges = _edge_lengths(points)
    short_side = min((edges[0] + edges[2]) / 2.0, (edges[1] + edges[3]) / 2.0)
    scale = math.sqrt((width * height) / (320.0 * 180.0))
    return float(np.clip(short_side * 0.025, 1.5 * scale, 12.0 * scale))


def build_portal_alpha(quad: Sequence[Point], width: int, height: int, feather_px: float) -> np.ndarray:
    scale = 2
    mask = np.zeros((height * scale, width * scale), dtype=np.uint8)
    points = np.round(np.asarray(quad, dtype=np.float64) * scale).astype(np.int32)
    cv2.fillConvexPoly(mask, points, 255, lineType=cv2.LINE_AA)
    inside = (mask > 0).astype(np.uint8)
    distance = cv2.distanceTransform(inside, cv2.DIST_L2, 5)
    alpha = np.clip(distance / max(feather_px * scale, 1e-6), 0.0, 1.0)
    alpha *= mask.astype(np.float32) / 255.0
    return cv2.resize(alpha, (width, height), interpolation=cv2.INTER_AREA).astype(np.float32)


def build_finger_occlusion_alpha(hands, width: int, height: int, feather_px: float = 0.8) -> np.ndarray:
    scale = 2
    mask = np.zeros((height * scale, width * scale), dtype=np.uint8)
    for landmarks in hands or []:
        if len(landmarks) <= MIDDLE_MCP:
            continue
        point = lambda index: (
            int(round(float(landmarks[index].x) * width * scale)),
            int(round(float(landmarks[index].y) * height * scale)),
        )
        wrist, middle = point(WRIST), point(MIDDLE_MCP)
        hand_scale = math.hypot(wrist[0] - middle[0], wrist[1] - middle[1]) / scale
        thickness = int(round(np.clip(hand_scale * 0.22, 5.0, min(width, height) * 0.08) * scale))
        for chain in ((INDEX_MCP, INDEX_PIP, INDEX_DIP, INDEX_TIP), (THUMB_MCP, THUMB_IP, THUMB_TIP)):
            for start, end in zip(chain, chain[1:]):
                cv2.line(mask, point(start), point(end), 255, thickness, cv2.LINE_AA)
            for joint in chain:
                cv2.circle(mask, point(joint), max(1, thickness // 2), 255, -1, cv2.LINE_AA)
    if feather_px > 0:
        sigma = feather_px * scale
        mask = cv2.GaussianBlur(mask, (0, 0), sigmaX=sigma, sigmaY=sigma)
    return cv2.resize(mask.astype(np.float32) / 255.0, (width, height), interpolation=cv2.INTER_AREA)


class PerspectiveCompositor:
    def __init__(self, width: int, height: int, use_occlusion: bool = True, use_parallax: bool = False):
        self.width, self.height = width, height
        self.use_occlusion = use_occlusion
        self.use_parallax = use_parallax
        self.last_occlusion_alpha: np.ndarray | None = None
        self.last_portal_center: np.ndarray | None = None
        self.last_portal_angle: float | None = None
        self.frames_processed = 0
        self.applied_frames = 0
        self.invalid_transform_frames = 0
        self._processing_times: list[float] = []
        self.rejection_reasons: dict[str, int] = {}

    def composite(
        self,
        original: np.ndarray,
        stylized: np.ndarray,
        quad: Sequence[Point] | None,
        confidence: float,
        detection_state: str,
        hands=None,
        transition_progress: float = 0.0,
        parallax_quad: Sequence[Point] | None = None,
    ) -> CompositeResult:
        started = time.perf_counter()
        self.frames_processed += 1
        empty = np.zeros((self.height, self.width), dtype=np.float32)
        if quad is None:
            result = CompositeResult(original.copy(), np.zeros_like(original), empty, empty, None, False, "inactive", 0.0, 0.0, "missing_quad")
            self._processing_times.append(time.perf_counter() - started)
            return result
        transition_progress = float(np.clip(transition_progress, 0.0, 1.0))
        opacity = 1.0 if transition_progress > 0.0 else confidence_opacity(confidence, detection_state)
        if opacity <= 0:
            result = CompositeResult(original.copy(), np.zeros_like(original), empty, empty, None, False, "confidence_gated", 0.0, 0.0, "low_confidence")
            self._processing_times.append(time.perf_counter() - started)
            return result

        matrix, reason, _, _ = validate_homography(quad, self.width, self.height)
        if matrix is None:
            self.invalid_transform_frames += 1
            self.rejection_reasons[reason] = self.rejection_reasons.get(reason, 0) + 1
            result = CompositeResult(original.copy(), np.zeros_like(original), empty, empty, None, False, "invalid_transform", 0.0, 0.0, reason)
            self._processing_times.append(time.perf_counter() - started)
            return result

        if stylized.shape[:2] != (self.height, self.width):
            stylized = cv2.resize(stylized, (self.width, self.height), interpolation=cv2.INTER_LINEAR)
        parallax_offset = (0.0, 0.0)
        if self.use_parallax and transition_progress < 1.0:
            motion_quad = np.asarray(parallax_quad if parallax_quad is not None else quad, dtype=np.float64)
            center = np.mean(motion_quad, axis=0)
            top = motion_quad[1] - motion_quad[0]
            angle = math.atan2(float(top[1]), float(top[0]))
            if self.last_portal_center is not None:
                movement = center - self.last_portal_center
                angle_change = angle - (self.last_portal_angle or angle)
                influence = 1.0 - transition_progress
                dx = float(np.clip(-movement[0] * 0.18, -self.width * 0.015, self.width * 0.015) * influence)
                dy = float(np.clip(-movement[1] * 0.18 + angle_change * self.height * 0.08, -self.height * 0.015, self.height * 0.015) * influence)
                parallax_offset = (dx, dy)
                zoom = 1.035
                matrix_2d = np.array(
                    [[zoom, 0.0, (1.0 - zoom) * self.width / 2.0 + dx],
                     [0.0, zoom, (1.0 - zoom) * self.height / 2.0 + dy]],
                    dtype=np.float32,
                )
                stylized = cv2.warpAffine(
                    stylized,
                    matrix_2d,
                    (self.width, self.height),
                    flags=cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_REFLECT_101,
                )
            self.last_portal_center = center
            self.last_portal_angle = angle
        warped = cv2.warpPerspective(
            stylized,
            matrix,
            (self.width, self.height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0),
        )
        feather = adaptive_feather_width(quad, self.width, self.height) * (1.0 - transition_progress)
        portal_alpha = (
            np.ones((self.height, self.width), dtype=np.float32)
            if transition_progress >= 1.0
            else build_portal_alpha(quad, self.width, self.height, feather)
        ) * opacity
        portal_alpha_3 = portal_alpha[..., None]
        output = original.astype(np.float32) * (1.0 - portal_alpha_3) + warped.astype(np.float32) * portal_alpha_3

        occlusion = empty
        if self.use_occlusion:
            if hands:
                occlusion = build_finger_occlusion_alpha(hands, self.width, self.height)
                self.last_occlusion_alpha = occlusion
            elif detection_state in {"predicted", "held", "rejected"} and self.last_occlusion_alpha is not None:
                occlusion = self.last_occlusion_alpha * min(1.0, confidence / 0.65)
            occlusion = occlusion * (1.0 - transition_progress)
            restore = (occlusion * portal_alpha)[..., None]
            output = output * (1.0 - restore) + original.astype(np.float32) * restore

        result = CompositeResult(
            np.clip(output, 0, 255).astype(np.uint8),
            warped,
            portal_alpha,
            occlusion,
            matrix,
            True,
            "perspective_occlusion" if self.use_occlusion else "perspective",
            opacity,
            feather,
            transition_progress=transition_progress,
            expanded_quad=tuple((float(point[0]), float(point[1])) for point in quad),
            parallax_offset=parallax_offset,
        )
        self.applied_frames += 1
        self._processing_times.append(time.perf_counter() - started)
        return result

    def metrics(self) -> dict[str, object]:
        values = [value * 1000.0 for value in self._processing_times]
        return {
            "frames_processed": self.frames_processed,
            "applied_frames": self.applied_frames,
            "invalid_transform_frames": self.invalid_transform_frames,
            "rejection_reasons": dict(sorted(self.rejection_reasons.items())),
            "average_processing_ms_per_frame": round(float(np.mean(values)), 6) if values else 0.0,
            "maximum_processing_ms_per_frame": round(max(values), 6) if values else 0.0,
            "occlusion_enabled": self.use_occlusion,
            "parallax_enabled": self.use_parallax,
        }
