#!/usr/bin/env python3
"""Compare frozen legacy and stabilized tracking on deterministic fixtures."""

import argparse
import json
import math
from pathlib import Path
import statistics
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from composite import FrameTracker  # noqa: E402
from stabilized_tracker import StabilizedFrameTracker, quad_geometry  # noqa: E402
from tests.tracking_sequences import HEIGHT, SEQUENCES, WIDTH, quad_to_hands  # noqa: E402


def _center(quad):
    return (
        sum(point[0] for point in quad) / 4.0,
        sum(point[1] for point in quad) / 4.0,
    )


def _distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _angle_error_degrees(a, b):
    return math.degrees((a - b + math.pi) % (2 * math.pi) - math.pi)


def run_sequence(mode, sequence):
    tracker = FrameTracker(WIDTH, HEIGHT) if mode == "legacy" else StabilizedFrameTracker(WIDTH, HEIGHT)
    output_quads = []
    states = []
    for frame in sequence:
        hands = quad_to_hands(frame.raw_quad)
        if mode == "legacy":
            output = tracker.update(hands)
            states.append(None)
        else:
            state = tracker.update_state(hands)
            output = state.stabilized_quad
            states.append(state)
        output_quads.append(output)

    displacements = []
    corner_accelerations = []
    previous_corner_movements = None
    for previous, current in zip(output_quads, output_quads[1:]):
        if previous is None or current is None:
            previous_corner_movements = None
            continue
        movements = [_distance(previous[i], current[i]) for i in range(4)]
        displacements.extend(movements)
        if previous_corner_movements is not None:
            corner_accelerations.extend(
                abs(movements[i] - previous_corner_movements[i]) for i in range(4)
            )
        previous_corner_movements = movements

    center_errors = []
    area_ratios = []
    orientation_errors = []
    for frame, output in zip(sequence, output_quads):
        if output is None:
            continue
        output_geometry = quad_geometry(output)
        truth_geometry = quad_geometry(frame.truth_quad)
        center_errors.append(
            (
                output_geometry.center[0] - truth_geometry.center[0],
                output_geometry.center[1] - truth_geometry.center[1],
            )
        )
        area_ratios.append(output_geometry.area / truth_geometry.area)
        orientation_errors.append(
            _angle_error_degrees(output_geometry.orientation, truth_geometry.orientation)
        )

    mean_error = (
        statistics.mean(error[0] for error in center_errors),
        statistics.mean(error[1] for error in center_errors),
    ) if center_errors else (0.0, 0.0)
    centered_errors = [
        _distance(error, mean_error)
        for error in center_errors
    ]
    lags = [_distance(error, (0.0, 0.0)) for error in center_errors]
    raw_metrics = tracker.metrics()

    return {
        "frames": len(sequence),
        "raw_detection_frames": sum(frame.raw_quad is not None for frame in sequence),
        "valid_quad_frames": raw_metrics["raw_valid_quad_frames"],
        "visible_quad_frames": raw_metrics["output_quad_frames"],
        "held_frames": raw_metrics.get("dropout_held_frames", 0),
        "predicted_frames": raw_metrics.get("predicted_frames", 0),
        "tracker_resets": raw_metrics["tracker_resets"],
        "rejected_updates": raw_metrics.get("rejected_updates", raw_metrics.get("rejected_jumps", 0)),
        "mean_corner_displacement_px": round(statistics.mean(displacements), 6) if displacements else 0.0,
        "median_corner_displacement_px": round(statistics.median(displacements), 6) if displacements else 0.0,
        "maximum_corner_displacement_px": round(max(displacements), 6) if displacements else 0.0,
        "center_jitter_rms_px": round(math.sqrt(statistics.mean(value * value for value in centered_errors)), 6) if centered_errors else 0.0,
        "normalized_area_variance": round(statistics.pvariance(area_ratios), 10) if len(area_ratios) > 1 else 0.0,
        "orientation_variance_degrees_squared": round(statistics.pvariance(orientation_errors), 8) if len(orientation_errors) > 1 else 0.0,
        "mean_corner_acceleration_px_per_frame2": round(statistics.mean(corner_accelerations), 6) if corner_accelerations else 0.0,
        "mean_positional_lag_px": round(statistics.mean(lags), 6) if lags else 0.0,
        "maximum_positional_lag_px": round(max(lags), 6) if lags else 0.0,
    }


def benchmark(mode, sequences, repeats):
    prepared = [quad_to_hands(frame.raw_quad) for sequence in sequences for frame in sequence]
    samples = []
    for _ in range(repeats):
        tracker = FrameTracker(WIDTH, HEIGHT) if mode == "legacy" else StabilizedFrameTracker(WIDTH, HEIGHT)
        started = time.perf_counter()
        for hands in prepared:
            tracker.update(hands)
        samples.append((time.perf_counter() - started) * 1000.0 / len(prepared))
    return {
        "average_ms_per_frame": round(statistics.mean(samples), 6),
        "median_ms_per_frame": round(statistics.median(samples), 6),
        "minimum_ms_per_frame": round(min(samples), 6),
        "repetitions": repeats,
        "frames_per_repetition": len(prepared),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="tests/artifacts/milestone2_tracking_metrics.json",
        help="JSON report path",
    )
    parser.add_argument("--benchmark-repeats", type=int, default=200)
    args = parser.parse_args()

    sequences = {name: factory() for name, factory in SEQUENCES.items()}
    report = {
        "fixture_dimensions": {"width": WIDTH, "height": HEIGHT},
        "fixtures": {
            name: {
                mode: run_sequence(mode, sequence)
                for mode in ("legacy", "stabilized")
            }
            for name, sequence in sequences.items()
        },
        "performance": {
            mode: benchmark(mode, list(sequences.values()), args.benchmark_repeats)
            for mode in ("legacy", "stabilized")
        },
    }
    stationary = report["fixtures"]["stationary"]
    baseline = stationary["legacy"]["center_jitter_rms_px"]
    improved = stationary["stabilized"]["center_jitter_rms_px"]
    report["headline"] = {
        "stationary_jitter_improvement_percent": round((baseline - improved) / baseline * 100.0, 3),
        "smooth_mean_lag_px": report["fixtures"]["smooth_translation"]["stabilized"]["mean_positional_lag_px"],
        "smooth_maximum_lag_px": report["fixtures"]["smooth_translation"]["stabilized"]["maximum_positional_lag_px"],
    }

    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()

