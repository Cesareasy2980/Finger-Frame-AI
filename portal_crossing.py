"""Deterministic geometry-driven portal crossing and event lifecycle."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Sequence

import numpy as np


Point = tuple[float, float]
Quad = tuple[Point, Point, Point, Point]


class TransitionState(str, Enum):
    INACTIVE = "INACTIVE"
    PORTAL_VISIBLE = "PORTAL_VISIBLE"
    ENTERING = "ENTERING"
    FULL_AI = "FULL_AI"
    EXITING = "EXITING"


@dataclass(frozen=True)
class PortalCrossingConfig:
    enabled: bool = True
    enter_coverage_threshold: float = 0.50
    full_coverage_threshold: float = 0.88
    abort_coverage_threshold: float = 0.34
    exit_coverage_threshold: float = 0.40
    confidence_threshold: float = 0.70
    stable_frames_required: int = 3
    abort_frames_required: int = 2
    exit_frames_required: int = 3
    growth_history_frames: int = 5
    minimum_growth_per_frame: float = 0.006
    dropout_grace_frames: int = 4
    inactive_reset_frames: int = 3
    fallback_exit_frames: int = 8


DEFAULT_PORTAL_CROSSING_CONFIG = PortalCrossingConfig()


@dataclass(frozen=True)
class PortalEvent:
    portal_id: int
    start_frame: int
    end_frame: int | None
    style_preset: str | None = None
    custom_prompt_present: bool = False
    reference_image_present: bool = False


@dataclass(frozen=True)
class TransitionSnapshot:
    state: str
    coverage: float
    raw_progress: float
    progress: float
    confidence: float
    expanded_quad: Quad | None
    portal_id: int | None
    growth_per_frame: float
    dropout_frames: int
    frame_index: int


def smoothstep(value: float) -> float:
    value = float(np.clip(value, 0.0, 1.0))
    return value * value * (3.0 - 2.0 * value)


def _polygon_area(points: Sequence[Point]) -> float:
    if len(points) < 3:
        return 0.0
    array = np.asarray(points, dtype=np.float64)
    return abs(float(np.dot(array[:, 0], np.roll(array[:, 1], -1)) - np.dot(array[:, 1], np.roll(array[:, 0], -1))) / 2.0)


def _clip_axis(points: list[Point], axis: int, boundary: float, keep_greater: bool) -> list[Point]:
    if not points:
        return []
    output: list[Point] = []
    previous = points[-1]
    previous_inside = previous[axis] >= boundary if keep_greater else previous[axis] <= boundary
    for current in points:
        current_inside = current[axis] >= boundary if keep_greater else current[axis] <= boundary
        if current_inside != previous_inside:
            delta = current[axis] - previous[axis]
            if abs(delta) > 1e-12:
                ratio = (boundary - previous[axis]) / delta
                intersection = (
                    previous[0] + (current[0] - previous[0]) * ratio,
                    previous[1] + (current[1] - previous[1]) * ratio,
                )
                output.append(intersection)
        if current_inside:
            output.append(current)
        previous, previous_inside = current, current_inside
    return output


def portal_coverage(quad: Sequence[Point] | None, width: int, height: int) -> float:
    """Visible quad area divided by the exact full-frame polygon area."""
    if quad is None or width <= 1 or height <= 1:
        return 0.0
    try:
        points = [(float(point[0]), float(point[1])) for point in quad]
    except (TypeError, ValueError, IndexError):
        return 0.0
    if len(points) != 4 or not np.isfinite(points).all():
        return 0.0
    points = _clip_axis(points, 0, 0.0, True)
    points = _clip_axis(points, 0, width - 1.0, False)
    points = _clip_axis(points, 1, 0.0, True)
    points = _clip_axis(points, 1, height - 1.0, False)
    frame_area = float((width - 1) * (height - 1))
    return float(np.clip(_polygon_area(points) / frame_area, 0.0, 1.0))


def expand_quad(quad: Sequence[Point], width: int, height: int, progress: float) -> Quad:
    t = smoothstep(progress)
    source = np.asarray(quad, dtype=np.float64)
    full = np.asarray(
        ((0.0, 0.0), (width - 1.0, 0.0), (width - 1.0, height - 1.0), (0.0, height - 1.0)),
        dtype=np.float64,
    )
    expanded = source * (1.0 - t) + full * t
    return tuple((float(point[0]), float(point[1])) for point in expanded)  # type: ignore[return-value]


class PortalCrossingController:
    def __init__(
        self,
        width: int,
        height: int,
        config: PortalCrossingConfig = DEFAULT_PORTAL_CROSSING_CONFIG,
        generation_metadata: dict | None = None,
    ):
        self.width, self.height = width, height
        self.config = config
        self.generation_metadata = dict(generation_metadata or {})
        self.reset()

    def reset(self) -> None:
        self.state = TransitionState.INACTIVE
        self.raw_progress = 0.0
        self.last_quad: Quad | None = None
        self.last_confidence = 0.0
        self.history: list[float] = []
        self.enter_candidate_frames = 0
        self.abort_candidate_frames = 0
        self.exit_candidate_frames = 0
        self.dropout_frames = 0
        self.frame_index = -1
        self.next_portal_id = 1
        self.current_event: PortalEvent | None = None
        self.events: list[PortalEvent] = []

    def _begin_event(self) -> None:
        if self.current_event is not None:
            return
        self.current_event = PortalEvent(
            portal_id=self.next_portal_id,
            start_frame=self.frame_index,
            end_frame=None,
            style_preset=self.generation_metadata.get("stylePreset"),
            custom_prompt_present=bool(self.generation_metadata.get("customPromptPresent")),
            reference_image_present=bool(self.generation_metadata.get("referenceImagePresent")),
        )
        self.next_portal_id += 1

    def _finish_event(self) -> None:
        if self.current_event is None:
            return
        finished = PortalEvent(**{**asdict(self.current_event), "end_frame": self.frame_index})
        self.events.append(finished)
        self.current_event = None

    def _append_history(self, coverage: float) -> float:
        self.history.append(coverage)
        self.history = self.history[-self.config.growth_history_frames :]
        if len(self.history) < 2:
            return 0.0
        return (self.history[-1] - self.history[0]) / (len(self.history) - 1)

    def _geometry_progress(self, coverage: float) -> float:
        span = self.config.full_coverage_threshold - self.config.enter_coverage_threshold
        return float(np.clip((coverage - self.config.enter_coverage_threshold) / span, 0.0, 1.0))

    def _snapshot(self, coverage: float, growth: float) -> TransitionSnapshot:
        progress = smoothstep(self.raw_progress)
        if self.state == TransitionState.FULL_AI:
            expanded = expand_quad(
                self.last_quad or tuple(map(tuple, np.asarray(((0, 0), (self.width - 1, 0), (self.width - 1, self.height - 1), (0, self.height - 1))))),
                self.width,
                self.height,
                1.0,
            )
        elif self.last_quad is not None:
            expanded = expand_quad(self.last_quad, self.width, self.height, self.raw_progress)
        else:
            expanded = None
        return TransitionSnapshot(
            state=self.state.value,
            coverage=coverage,
            raw_progress=self.raw_progress,
            progress=progress,
            confidence=self.last_confidence,
            expanded_quad=expanded,
            portal_id=self.current_event.portal_id if self.current_event else None,
            growth_per_frame=growth,
            dropout_frames=self.dropout_frames,
            frame_index=self.frame_index,
        )

    def update(
        self,
        quad: Sequence[Point] | None,
        confidence: float,
        detection_state: str = "detected",
        frame_index: int | None = None,
        force_progress: float | None = None,
    ) -> TransitionSnapshot:
        self.frame_index = self.frame_index + 1 if frame_index is None else int(frame_index)
        coverage = portal_coverage(quad, self.width, self.height)
        valid_quad = quad is not None and coverage > 0.0
        reliable = (
            valid_quad
            and confidence >= self.config.confidence_threshold
            and detection_state in {"detected", "legacy"}
        )
        if valid_quad:
            self.last_quad = tuple((float(point[0]), float(point[1])) for point in quad)  # type: ignore[assignment]
            self.last_confidence = float(np.clip(confidence, 0.0, 1.0))

        if force_progress is not None:
            self._begin_event()
            self.raw_progress = float(np.clip(force_progress, 0.0, 1.0))
            self.state = TransitionState.FULL_AI if self.raw_progress >= 1.0 else (
                TransitionState.PORTAL_VISIBLE if self.raw_progress <= 0.0 else TransitionState.ENTERING
            )
            return self._snapshot(coverage, 0.0)

        if not self.config.enabled:
            if valid_quad:
                self._begin_event()
                self.state = TransitionState.PORTAL_VISIBLE
            else:
                self._finish_event()
                self.state = TransitionState.INACTIVE
            self.raw_progress = 0.0
            return self._snapshot(coverage, 0.0)

        growth = self._append_history(coverage) if reliable else 0.0

        if self.state == TransitionState.INACTIVE:
            self.raw_progress = 0.0
            if valid_quad and confidence >= 0.1:
                self._begin_event()
                self.state = TransitionState.PORTAL_VISIBLE
                self.dropout_frames = 0
            return self._snapshot(coverage, growth)

        if self.state == TransitionState.PORTAL_VISIBLE:
            self.raw_progress = 0.0
            if not valid_quad:
                self.dropout_frames += 1
                if self.dropout_frames >= self.config.inactive_reset_frames:
                    self._finish_event()
                    self.state = TransitionState.INACTIVE
                    self.history.clear()
                return self._snapshot(coverage, growth)
            self.dropout_frames = 0
            qualifies = reliable and coverage >= self.config.enter_coverage_threshold and growth >= self.config.minimum_growth_per_frame
            self.enter_candidate_frames = self.enter_candidate_frames + 1 if qualifies else 0
            if self.enter_candidate_frames >= self.config.stable_frames_required:
                self.state = TransitionState.ENTERING
                self.raw_progress = self._geometry_progress(coverage)
                self.abort_candidate_frames = 0
            return self._snapshot(coverage, growth)

        if self.state == TransitionState.ENTERING:
            if reliable:
                self.dropout_frames = 0
                self.abort_candidate_frames = (
                    self.abort_candidate_frames + 1
                    if coverage < self.config.abort_coverage_threshold
                    else 0
                )
                if self.abort_candidate_frames >= self.config.abort_frames_required:
                    self.state = TransitionState.PORTAL_VISIBLE
                    self.raw_progress = 0.0
                else:
                    self.raw_progress = max(self.raw_progress, self._geometry_progress(coverage))
                    if coverage >= self.config.full_coverage_threshold or self.raw_progress >= 1.0:
                        self.raw_progress = 1.0
                        self.state = TransitionState.FULL_AI
                        self.exit_candidate_frames = 0
            else:
                self.dropout_frames += 1
                if self.dropout_frames > self.config.dropout_grace_frames:
                    self.raw_progress = 0.0
                    if valid_quad:
                        self.state = TransitionState.PORTAL_VISIBLE
                    else:
                        self._finish_event()
                        self.state = TransitionState.INACTIVE
                        self.history.clear()
            return self._snapshot(coverage, growth)

        if self.state == TransitionState.FULL_AI:
            self.raw_progress = 1.0
            if reliable:
                self.dropout_frames = 0
                self.exit_candidate_frames = (
                    self.exit_candidate_frames + 1
                    if coverage < self.config.exit_coverage_threshold
                    else 0
                )
            else:
                self.dropout_frames += 1
            if (
                self.exit_candidate_frames >= self.config.exit_frames_required
                or self.dropout_frames > self.config.dropout_grace_frames
            ):
                self.state = TransitionState.EXITING
            return self._snapshot(coverage, growth)

        # EXITING: geometry drives a decreasing progress; prolonged loss uses a
        # bounded fallback so a completed event cannot remain stuck full-screen.
        if reliable:
            self.dropout_frames = 0
            target = self._geometry_progress(coverage)
            self.raw_progress = max(
                target,
                self.raw_progress - 1.0 / self.config.fallback_exit_frames,
            )
        else:
            self.dropout_frames += 1
            self.raw_progress = max(0.0, self.raw_progress - 1.0 / self.config.fallback_exit_frames)
        if self.raw_progress <= 0.0:
            if valid_quad:
                self.state = TransitionState.PORTAL_VISIBLE
                self.enter_candidate_frames = 0
            else:
                self._finish_event()
                self.state = TransitionState.INACTIVE
                self.history.clear()
        return self._snapshot(coverage, growth)

    def event_metadata(self) -> list[dict]:
        values = [asdict(event) for event in self.events]
        if self.current_event is not None:
            values.append(asdict(self.current_event))
        return values
