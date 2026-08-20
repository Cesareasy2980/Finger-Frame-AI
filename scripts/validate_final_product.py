#!/usr/bin/env python3
"""Create deterministic final-sprint diagnostics and exercise the offline product path."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from perspective_compositor import PerspectiveCompositor  # noqa: E402
from portal_crossing import PortalCrossingController, TransitionState  # noqa: E402
from tests.compositing_fixtures import synthetic_hands  # noqa: E402


WIDTH, HEIGHT, FPS = 640, 360, 30


def quad_for_coverage(coverage: float, phase: float = 0.0):
    scale = float(np.sqrt(max(0.0, min(1.0, coverage))))
    half_w = (WIDTH - 1) * scale / 2
    half_h = (HEIGHT - 1) * scale / 2
    cx = (WIDTH - 1) / 2 + np.sin(phase) * 12
    cy = (HEIGHT - 1) / 2 + np.cos(phase * 0.7) * 6
    skew = np.sin(phase * 1.3) * 12
    return (
        (cx - half_w + skew, cy - half_h),
        (cx + half_w + skew, cy - half_h + 5),
        (cx + half_w - skew, cy + half_h),
        (cx - half_w - skew, cy + half_h - 5),
    )


def event_sequence():
    event = [0.10] * 5 + [0.25, 0.38, 0.49, 0.54, 0.60, 0.70, 0.82, 0.91]
    event += [0.92] * 10 + [0.70, 0.52, 0.35, 0.25] + [0.20] * 10
    return event + [None] * 14 + event + [None] * 14


def make_scene(frame_index: int):
    x = np.linspace(0, 1, WIDTH, dtype=np.float32)[None, :]
    y = np.linspace(0, 1, HEIGHT, dtype=np.float32)[:, None]
    original = np.empty((HEIGHT, WIDTH, 3), np.uint8)
    original[:, :, 0] = np.clip(35 + 50 * y, 0, 255)
    original[:, :, 1] = np.clip(45 + 35 * x, 0, 255)
    original[:, :, 2] = np.clip(70 + 25 * (1 - y), 0, 255)
    cv2.rectangle(original, (0, 240), (WIDTH, HEIGHT), (30, 55, 35), -1)
    cv2.circle(original, (90 + frame_index * 3 % 540, 230), 28, (80, 120, 230), -1)

    generated = np.empty_like(original)
    generated[:, :, 0] = np.clip(150 + 90 * x, 0, 255)
    generated[:, :, 1] = np.clip(40 + 100 * y, 0, 255)
    generated[:, :, 2] = np.clip(140 + 90 * (1 - x), 0, 255)
    for offset in range(-HEIGHT, WIDTH, 48):
        cv2.line(generated, (offset + frame_index * 2, 0), (offset + HEIGHT + frame_index * 2, HEIGHT), (255, 190, 90), 3)
    cv2.putText(generated, "AI WORLD", (215, 185), cv2.FONT_HERSHEY_DUPLEX, 1.0, (255, 255, 255), 2, cv2.LINE_AA)
    return original, generated


def create_debug_video(output: Path, preview: Path, metrics_path: Path):
    output.parent.mkdir(parents=True, exist_ok=True)
    controller = PortalCrossingController(
        WIDTH,
        HEIGHT,
        generation_metadata={
            "stylePreset": "dream_world",
            "customPromptPresent": True,
            "referenceImagePresent": False,
        },
    )
    compositor = PerspectiveCompositor(WIDTH, HEIGHT, use_occlusion=True, use_parallax=True)
    sequence = event_sequence()
    transition_timings = []
    compositing_timings = []
    states = set()
    full_endpoint_error = None
    with tempfile.TemporaryDirectory(prefix="finger-frame-final-") as temp_dir:
        intermediate = Path(temp_dir) / "debug.mp4"
        writer = cv2.VideoWriter(str(intermediate), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (WIDTH, HEIGHT))
        if not writer.isOpened():
            raise RuntimeError("OpenCV could not create the diagnostic video")
        for index, coverage in enumerate(sequence):
            original, generated = make_scene(index)
            quad = quad_for_coverage(coverage, index / 12) if coverage is not None else None
            transition_started = time.perf_counter()
            snapshot = controller.update(
                quad,
                0.96 if quad else 0.0,
                "detected" if quad else "lost",
                index,
            )
            transition_timings.append((time.perf_counter() - transition_started) * 1000)
            states.add(snapshot.state)
            if snapshot.expanded_quad is not None:
                compositing_started = time.perf_counter()
                result = compositor.composite(
                    original,
                    generated,
                    snapshot.expanded_quad,
                    snapshot.confidence,
                    "detected" if quad else "lost",
                    synthetic_hands(WIDTH, HEIGHT),
                    transition_progress=snapshot.progress,
                    parallax_quad=quad,
                )
                compositing_timings.append((time.perf_counter() - compositing_started) * 1000)
                frame = result.frame
                if snapshot.state == TransitionState.FULL_AI.value:
                    full_endpoint_error = float(np.abs(frame.astype(np.int16) - generated.astype(np.int16)).mean())
            else:
                frame = original.copy()
            if quad is not None:
                cv2.polylines(frame, [np.asarray(quad, np.int32)], True, (80, 255, 255), 2, cv2.LINE_AA)
            cv2.rectangle(frame, (8, 8), (405, 78), (6, 8, 14), -1)
            cv2.putText(frame, f"Portal {snapshot.portal_id or '-'}  {snapshot.state}", (18, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.putText(frame, f"coverage {snapshot.coverage:.3f}  progress {snapshot.progress:.3f}  confidence {snapshot.confidence:.2f}", (18, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (150, 220, 255), 1, cv2.LINE_AA)
            cv2.putText(frame, "parallax on | occlusion fades with crossing", (18, 73), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (190, 190, 210), 1, cv2.LINE_AA)
            writer.write(frame)
            if index == len(sequence) // 2 - 8:
                cv2.imwrite(str(preview), frame)
        writer.release()
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error", "-i", str(intermediate),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output),
        ], check=True)

    events = controller.event_metadata()
    if len(events) != 2 or any(event["end_frame"] is None for event in events):
        raise RuntimeError(f"Expected two completed portal events, got {events}")
    required_states = {state.value for state in TransitionState}
    if not required_states.issubset(states):
        raise RuntimeError(f"Diagnostic did not cover all transition states: {sorted(states)}")
    metrics = {
        "frames": len(sequence),
        "fps": FPS,
        "resolution": [WIDTH, HEIGHT],
        "states_covered": sorted(states),
        "events": events,
        "full_endpoint_mean_absolute_error": full_endpoint_error,
        "transition_state_ms": {
            "mean": float(np.mean(transition_timings)),
            "p95": float(np.percentile(transition_timings, 95)),
            "max": float(np.max(transition_timings)),
        },
        "transition_compositing_ms": {
            "mean": float(np.mean(compositing_timings)),
            "p95": float(np.percentile(compositing_timings, 95)),
            "max": float(np.max(compositing_timings)),
        },
        "parallax": "lightweight motion-derived 2.5D illusion",
    }
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")


def run_offline_demo(output: Path, metrics: Path):
    subprocess.run([
        sys.executable,
        str(ROOT / "composite.py"),
        str(ROOT / "tests/fixtures/finger_frame_short.mp4"),
        str(ROOT / "tests/fixtures/finger_frame_short_stylized.mp4"),
        "-o", str(output),
        "--portal-mode", "portal_crossing",
        "--parallax",
        "--metrics", str(metrics),
    ], cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, default=ROOT / "tests/artifacts")
    args = parser.parse_args()
    artifacts = args.artifacts.resolve()
    create_debug_video(
        artifacts / "milestone5_portal_crossing_debug.mp4",
        artifacts / "milestone5_portal_crossing_debug_preview.png",
        artifacts / "milestone5_portal_crossing_metrics.json",
    )
    run_offline_demo(
        artifacts / "final_demo_output.mp4",
        artifacts / "final_demo_metrics.json",
    )
    print(f"Final product artifacts written to {artifacts}")


if __name__ == "__main__":
    main()
