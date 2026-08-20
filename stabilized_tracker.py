"""Deterministic, dependency-free stabilization for finger-frame quads.

The legacy tracker remains in :mod:`composite`.  This module is deliberately
separate so legacy behavior stays available as a frozen regression reference.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import statistics
import time
from typing import Iterable, Sequence


Point = tuple[float, float]
Quad = tuple[Point, Point, Point, Point]

WRIST, THUMB_TIP, INDEX_TIP, MIDDLE_MCP = 0, 4, 8, 9
SPREAD_ACQUIRE, SPREAD_KEEP = 0.75, 0.2

PREDICTION_FRAMES = 3
HOLD_FRAMES = 10
RESET_FRAMES = 18


def _distance(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _signed_area(points: Sequence[Point]) -> float:
    return sum(
        p[0] * q[1] - q[0] * p[1]
        for p, q in zip(points, points[1:] + points[:1])
    ) / 2.0


def _cross(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])


def _orientation(a: Point, b: Point, c: Point) -> int:
    value = (b[1] - a[1]) * (c[0] - b[0]) - (b[0] - a[0]) * (c[1] - b[1])
    if abs(value) < 1e-9:
        return 0
    return 1 if value > 0 else 2


def _segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    o1, o2 = _orientation(a, b, c), _orientation(a, b, d)
    o3, o4 = _orientation(c, d, a), _orientation(c, d, b)
    return o1 != o2 and o3 != o4 and 0 not in (o1, o2, o3, o4)


def is_self_intersecting(points: Sequence[Point]) -> bool:
    """Return whether either pair of non-adjacent quad edges crosses."""
    return _segments_intersect(points[0], points[1], points[2], points[3]) or _segments_intersect(
        points[1], points[2], points[3], points[0]
    )


def _canonical_clockwise(points: Sequence[Point]) -> Quad:
    """Order points clockwise in image coordinates and start near top-left."""
    cx = sum(p[0] for p in points) / 4.0
    cy = sum(p[1] for p in points) / 4.0
    ordered = sorted(points, key=lambda p: math.atan2(p[1] - cy, p[0] - cx))
    # Positive shoelace area is clockwise for screen coordinates (y points down).
    if _signed_area(ordered) < 0:
        ordered.reverse()
    start = min(range(4), key=lambda i: (ordered[i][0] + ordered[i][1], ordered[i][1]))
    ordered = ordered[start:] + ordered[:start]
    return tuple(ordered)  # type: ignore[return-value]


def _match_cyclic(candidate: Quad, reference: Sequence[Point]) -> Quad:
    rotations = [candidate[i:] + candidate[:i] for i in range(4)]
    return min(
        rotations,
        key=lambda quad: sum(_distance(point, reference[i]) ** 2 for i, point in enumerate(quad)),
    )


def _angle_delta(a: float, b: float) -> float:
    return abs((a - b + math.pi) % (2 * math.pi) - math.pi)


@dataclass(frozen=True)
class QuadGeometry:
    center: Point
    width: float
    height: float
    area: float
    orientation: float
    aspect_ratio: float


def quad_geometry(quad: Sequence[Point]) -> QuadGeometry:
    center = (
        sum(point[0] for point in quad) / 4.0,
        sum(point[1] for point in quad) / 4.0,
    )
    width = (_distance(quad[0], quad[1]) + _distance(quad[2], quad[3])) / 2.0
    height = (_distance(quad[1], quad[2]) + _distance(quad[3], quad[0])) / 2.0
    shorter = max(min(width, height), 1e-9)
    return QuadGeometry(
        center=center,
        width=width,
        height=height,
        area=abs(_signed_area(quad)),
        orientation=math.atan2(quad[1][1] - quad[0][1], quad[1][0] - quad[0][0]),
        aspect_ratio=max(width, height) / shorter,
    )


@dataclass
class CornerState:
    raw_position: Point
    filtered_position: Point
    velocity: Point = (0.0, 0.0)
    last_valid_frame: int = 0
    confidence: float = 0.0


@dataclass(frozen=True)
class TrackedFrame:
    raw_quad: Quad | None
    stabilized_quad: Quad | None
    confidence: float
    detection_state: str
    is_predicted: bool
    dropout_frames: int
    rejection_reason: str | None = None


class StabilizedFrameTracker:
    """Motion-aware tracker that treats four corners as one coherent quad."""

    def __init__(self, width: int, height: int):
        self.w, self.h = width, height
        self.diagonal = math.hypot(width, height)
        self.corners: Quad | None = None
        self.corner_states: list[CornerState] = []
        self.presence = 0.0
        self.confidence = 0.0
        self.frame_active = False
        self.dropout_frames = 0
        self.frame_index = 0
        self.quad_velocity: Point = (0.0, 0.0)
        self.last_state = TrackedFrame(None, None, 0.0, "lost", False, 0)

        self.frames_processed = 0
        self.raw_detection_frames = 0
        self.raw_valid_quad_frames = 0
        self.output_quad_frames = 0
        self.predicted_frames = 0
        self.dropout_held_frames = 0
        self.rejected_updates = 0
        self.tracker_resets = 0
        self.rejection_reasons: dict[str, int] = {}
        self._movement: list[float] = []
        self._processing_seconds = 0.0

    def compute_raw_quad(self, hands: Sequence[Sequence[object]]) -> Quad | None:
        """Extract the existing two-hand fingertip quad without replacing MediaPipe."""
        if len(hands) != 2:
            return None
        info = []
        for landmarks in hands:
            pixel = lambda i: (float(landmarks[i].x) * self.w, float(landmarks[i].y) * self.h)
            index, thumb = pixel(INDEX_TIP), pixel(THUMB_TIP)
            scale = _distance(pixel(WRIST), pixel(MIDDLE_MCP)) + 1.0
            needed = SPREAD_KEEP if self.frame_active else SPREAD_ACQUIRE
            if _distance(thumb, index) < scale * needed:
                return None
            info.append((pixel(WRIST)[0], index, thumb))
        info.sort(key=lambda hand: hand[0])
        return (info[0][1], info[1][1], info[1][2], info[0][2])

    def _validate_and_order(self, raw_quad: Iterable[Point]) -> tuple[Quad | None, str | None]:
        try:
            points = tuple((float(p[0]), float(p[1])) for p in raw_quad)
        except (TypeError, ValueError, IndexError):
            return None, "malformed"
        if len(points) != 4:
            return None, "point_count"
        if not all(math.isfinite(value) for point in points for value in point):
            return None, "non_finite"
        margin_x, margin_y = self.w * 0.2, self.h * 0.2
        if any(
            x < -margin_x or x > self.w + margin_x or y < -margin_y or y > self.h + margin_y
            for x, y in points
        ):
            return None, "out_of_bounds"
        minimum_separation = max(2.0, min(self.w, self.h) * 0.01)
        if any(
            _distance(points[i], points[j]) < minimum_separation
            for i in range(4)
            for j in range(i + 1, 4)
        ):
            return None, "duplicate_corner"
        if is_self_intersecting(points):
            return None, "self_intersection"

        ordered = _canonical_clockwise(points)
        crosses = [_cross(ordered[i], ordered[(i + 1) % 4], ordered[(i + 2) % 4]) for i in range(4)]
        if min(crosses) <= 1e-6:
            return None, "non_convex"
        geometry = quad_geometry(ordered)
        minimum_area = self.w * self.h * (0.0005 if self.frame_active else 0.005)
        if geometry.area < minimum_area:
            return None, "minimum_area"
        if geometry.aspect_ratio > 8.0:
            return None, "aspect_ratio"
        if min(geometry.width, geometry.height) < minimum_separation * 2:
            return None, "collapsed_edge"

        if self.corner_states:
            ordered = _match_cyclic(ordered, [state.raw_position for state in self.corner_states])
        if _signed_area(ordered) <= 0:
            return None, "invalid_winding"
        return ordered, None

    def _temporal_rejection(self, candidate: Quad) -> str | None:
        if not self.corner_states or self.corners is None:
            return None
        previous_raw = [state.raw_position for state in self.corner_states]
        vectors = [
            (candidate[i][0] - previous_raw[i][0], candidate[i][1] - previous_raw[i][1])
            for i in range(4)
        ]
        magnitudes = [_distance((0.0, 0.0), vector) for vector in vectors]
        ordered_magnitudes = sorted(magnitudes, reverse=True)
        median_motion = statistics.median(magnitudes)
        isolated_threshold = max(10.0, self.diagonal * 0.06, median_motion * 3.0 + 3.0)
        if ordered_magnitudes[0] > isolated_threshold and ordered_magnitudes[1] < ordered_magnitudes[0] * 0.45:
            return "isolated_corner_jump"

        old_geometry = quad_geometry(previous_raw)
        new_geometry = quad_geometry(candidate)
        scale_ratio = math.sqrt(new_geometry.area / max(old_geometry.area, 1e-9))
        if scale_ratio < 0.55 or scale_ratio > 1.8:
            return "scale_jump"
        if _angle_delta(new_geometry.orientation, old_geometry.orientation) > math.radians(70):
            return "orientation_flip"

        center_motion = _distance(new_geometry.center, old_geometry.center)
        mean_velocity = (
            sum(state.velocity[0] for state in self.corner_states) / 4.0,
            sum(state.velocity[1] for state in self.corner_states) / 4.0,
        )
        predicted_center = (
            old_geometry.center[0] + mean_velocity[0],
            old_geometry.center[1] + mean_velocity[1],
        )
        residual = _distance(new_geometry.center, predicted_center)
        if center_motion > self.diagonal * 0.45 and residual > self.diagonal * 0.25:
            return "impossible_translation"
        return None

    def _accept(self, raw_quad: Quad, candidate: Quad) -> TrackedFrame:
        if not self.corner_states:
            self.corner_states = [
                CornerState(point, point, last_valid_frame=self.frame_index, confidence=0.65)
                for point in candidate
            ]
            filtered = candidate
            self.confidence = 0.65
        else:
            filtered_points: list[Point] = []
            vectors = [
                (candidate[i][0] - state.raw_position[0], candidate[i][1] - state.raw_position[1])
                for i, state in enumerate(self.corner_states)
            ]
            mean_vector = (
                sum(vector[0] for vector in vectors) / 4.0,
                sum(vector[1] for vector in vectors) / 4.0,
            )
            self.quad_velocity = (
                self.quad_velocity[0] * 0.55 + mean_vector[0] * 0.45,
                self.quad_velocity[1] * 0.55 + mean_vector[1] * 0.45,
            )
            vector_spread = sum(_distance(vector, mean_vector) for vector in vectors) / 4.0
            coherence = max(0.0, 1.0 - vector_spread / max(_distance((0.0, 0.0), mean_vector), 4.0))
            quad_speed = _distance((0.0, 0.0), self.quad_velocity)
            prediction_weight = max(0.0, min(1.0, (quad_speed - 0.6) / 0.8))

            for i, state in enumerate(self.corner_states):
                raw_velocity = vectors[i]
                local_velocity = (
                    raw_velocity[0] - mean_vector[0],
                    raw_velocity[1] - mean_vector[1],
                )
                velocity = (
                    self.quad_velocity[0] + local_velocity[0] * 0.08,
                    self.quad_velocity[1] + local_velocity[1] * 0.08,
                )
                raw_speed_ratio = min(
                    1.0,
                    _distance((0.0, 0.0), raw_velocity) / (self.diagonal * 0.025),
                )
                intentional_speed_ratio = min(
                    1.0,
                    max(0.0, quad_speed - 0.6) / (self.diagonal * 0.01),
                )
                alpha = 0.08 + 0.58 * intentional_speed_ratio + 0.12 * raw_speed_ratio
                alpha = min(0.9, alpha + coherence * raw_speed_ratio * 0.08)
                predicted = (
                    state.filtered_position[0] + velocity[0] * prediction_weight,
                    state.filtered_position[1] + velocity[1] * prediction_weight,
                )
                filtered = (
                    predicted[0] + (candidate[i][0] - predicted[0]) * alpha,
                    predicted[1] + (candidate[i][1] - predicted[1]) * alpha,
                )
                previous_filtered = state.filtered_position
                state.velocity = velocity
                state.raw_position = candidate[i]
                state.filtered_position = filtered
                state.last_valid_frame = self.frame_index
                state.confidence = min(1.0, state.confidence + 0.18)
                filtered_points.append(filtered)
                self._movement.append(_distance(previous_filtered, filtered))
            filtered = tuple(filtered_points)  # type: ignore[assignment]
            recovery_penalty = min(self.dropout_frames * 0.03, 0.18)
            self.confidence = min(1.0, self.confidence + 0.18 - recovery_penalty)

        self.corners = filtered
        self.presence = self.confidence
        self.frame_active = True
        self.dropout_frames = 0
        self.raw_valid_quad_frames += 1
        self.output_quad_frames += 1
        return TrackedFrame(raw_quad, filtered, self.confidence, "detected", False, 0)

    def _missing(self, raw_quad: Quad | None, reason: str | None, rejected: bool) -> TrackedFrame:
        if rejected:
            self.rejected_updates += 1
            assert reason is not None
            self.rejection_reasons[reason] = self.rejection_reasons.get(reason, 0) + 1
        if not self.corner_states or self.corners is None:
            self.confidence = 0.0
            self.presence = 0.0
            return TrackedFrame(raw_quad, None, 0.0, "rejected" if rejected else "lost", False, 0, reason)

        self.dropout_frames += 1
        state_name = "rejected" if rejected else "predicted"
        predicted = False
        if self.dropout_frames <= PREDICTION_FRAMES:
            predicted = True
            self.predicted_frames += 1
            decay = 0.75 ** (self.dropout_frames - 1)
            maximum_step = self.diagonal * 0.025
            next_points = []
            for state in self.corner_states:
                vx, vy = state.velocity[0] * decay, state.velocity[1] * decay
                speed = math.hypot(vx, vy)
                if speed > maximum_step:
                    scale = maximum_step / speed
                    vx, vy = vx * scale, vy * scale
                point = (state.filtered_position[0] + vx, state.filtered_position[1] + vy)
                state.filtered_position = point
                next_points.append(point)
            self.corners = tuple(next_points)  # type: ignore[assignment]
            self.confidence *= 0.82
        elif self.dropout_frames <= HOLD_FRAMES:
            if not rejected:
                state_name = "held"
            self.dropout_held_frames += 1
            self.confidence *= 0.88
        elif self.dropout_frames < RESET_FRAMES:
            if not rejected:
                state_name = "lost"
            self.confidence *= 0.65
        else:
            self.tracker_resets += 1
            self.corners = None
            self.corner_states = []
            self.frame_active = False
            self.quad_velocity = (0.0, 0.0)
            self.confidence = 0.0
            self.presence = 0.0
            self.dropout_frames = 0
            return TrackedFrame(raw_quad, None, 0.0, "reset", False, RESET_FRAMES, reason)

        self.presence = self.confidence
        output = self.corners if self.confidence > 0.01 else None
        if output is not None:
            self.output_quad_frames += 1
        return TrackedFrame(
            raw_quad,
            output,
            self.confidence,
            state_name,
            predicted,
            self.dropout_frames,
            reason,
        )

    def update_quad(self, raw_quad: Iterable[Point] | None) -> TrackedFrame:
        started = time.perf_counter()
        self.frames_processed += 1
        self.frame_index += 1
        original: Quad | None = None
        if raw_quad is not None:
            try:
                values = tuple((float(point[0]), float(point[1])) for point in raw_quad)
                if len(values) == 4:
                    original = values  # type: ignore[assignment]
            except (TypeError, ValueError, IndexError):
                original = None
            self.raw_detection_frames += 1
            candidate, reason = self._validate_and_order(raw_quad)
            if candidate is not None:
                reason = self._temporal_rejection(candidate)
            if candidate is not None and reason is None:
                state = self._accept(original or candidate, candidate)
            else:
                state = self._missing(original, reason or "malformed", True)
        else:
            state = self._missing(None, None, False)
        self.last_state = state
        self._processing_seconds += time.perf_counter() - started
        return state

    def update_state(self, hands: Sequence[Sequence[object]]) -> TrackedFrame:
        return self.update_quad(self.compute_raw_quad(hands))

    def update(self, hands: Sequence[Sequence[object]]) -> Quad | None:
        """Compatibility wrapper for callers that only consume the output quad."""
        return self.update_state(hands).stabilized_quad

    def metrics(self) -> dict[str, object]:
        success = self.raw_valid_quad_frames / self.frames_processed if self.frames_processed else 0.0
        return {
            "frames_processed": self.frames_processed,
            "raw_detection_frames": self.raw_detection_frames,
            "raw_valid_quad_frames": self.raw_valid_quad_frames,
            "output_quad_frames": self.output_quad_frames,
            "detection_success_rate": round(success, 6),
            "predicted_frames": self.predicted_frames,
            "dropout_held_frames": self.dropout_held_frames,
            "rejected_updates": self.rejected_updates,
            "rejection_reasons": dict(sorted(self.rejection_reasons.items())),
            "tracker_resets": self.tracker_resets,
            "average_mean_corner_movement_pixels": round(statistics.mean(self._movement), 6) if self._movement else 0.0,
            "median_corner_movement_pixels": round(statistics.median(self._movement), 6) if self._movement else 0.0,
            "maximum_corner_movement_pixels": round(max(self._movement), 6) if self._movement else 0.0,
            "average_processing_ms_per_frame": round(
                self._processing_seconds * 1000.0 / self.frames_processed, 6
            ) if self.frames_processed else 0.0,
            "confidence": round(self.confidence, 6),
            "detection_state": self.last_state.detection_state,
        }
