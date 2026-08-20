#!/usr/bin/env python3
"""Measure Milestone 3 perspective accuracy, stability, occlusion, and cost."""

import argparse
import json
from pathlib import Path
import statistics
import sys
import time

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from perspective_compositor import (  # noqa: E402
    PerspectiveCompositor,
    build_finger_occlusion_alpha,
    build_portal_alpha,
    canonical_portal_corners,
    validate_homography,
)
from stabilized_tracker import StabilizedFrameTracker  # noqa: E402
from tests.compositing_fixtures import checkerboard, solid_pair, synthetic_hands  # noqa: E402
from tests.tracking_sequences import WIDTH, HEIGHT, smooth_translation_sequence  # noqa: E402


QUADS = (
    ((0, 0), (319, 0), (319, 179), (0, 179)),
    ((20, 20), (285, 35), (270, 160), (35, 150)),
    ((85, 30), (250, 55), (225, 155), (70, 135)),
    ((-30, 25), (220, 15), (235, 155), (-20, 165)),
)


def legacy_composite(original, stylized, quad):
    mask = np.zeros(original.shape[:2], dtype=np.uint8)
    cv2.fillPoly(mask, [np.asarray(quad, dtype=np.int32)], 255)
    alpha = (mask.astype(np.float32) / 255.0)[..., None]
    return (original.astype(np.float32) * (1 - alpha) + stylized.astype(np.float32) * alpha).astype(np.uint8)


def benchmark(name, operation, repeats):
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        operation()
        samples.append((time.perf_counter() - started) * 1000.0)
    return {
        "mode": name,
        "average_ms_per_frame": round(statistics.mean(samples), 6),
        "maximum_ms_per_frame": round(max(samples), 6),
        "median_ms_per_frame": round(statistics.median(samples), 6),
        "repetitions": repeats,
    }


def accuracy_metrics():
    errors = []
    interior_errors = []
    source = canonical_portal_corners(320, 180)
    interior = np.array([[[160.0, 90.0], [80.0, 45.0], [240.0, 135.0]]], np.float32)
    for quad in QUADS:
        matrix, reason, _, _ = validate_homography(quad, 320, 180)
        if reason:
            continue
        projected = cv2.perspectiveTransform(source[None], matrix)[0]
        errors.extend(np.linalg.norm(projected - np.asarray(quad), axis=1))
        mapped = cv2.perspectiveTransform(interior, matrix)
        roundtrip = cv2.perspectiveTransform(mapped, np.linalg.inv(matrix))
        interior_errors.extend(np.linalg.norm(roundtrip - interior, axis=2).ravel())
    return {
        "mean_corner_reprojection_error_px": round(float(np.mean(errors)), 10),
        "maximum_corner_reprojection_error_px": round(float(np.max(errors)), 10),
        "mean_interior_roundtrip_error_px": round(float(np.mean(interior_errors)), 10),
        "maximum_interior_roundtrip_error_px": round(float(np.max(interior_errors)), 10),
    }


def edge_metrics():
    quad = QUADS[2]
    alpha = build_portal_alpha(quad, 320, 180, 4.0)
    transition = (alpha > 0) & (alpha < 0.999)
    center = alpha[90, 160]
    return {
        "alpha_minimum": float(alpha.min()),
        "alpha_maximum": float(alpha.max()),
        "opaque_center_alpha": round(float(center), 6),
        "transition_pixels": int(np.count_nonzero(transition)),
        "transition_fraction_of_frame": round(float(np.mean(transition)), 6),
        "outside_nonzero_pixels": int(np.count_nonzero(alpha[:10, :10])),
    }


def occlusion_metrics():
    original, stylized = solid_pair(320, 180)
    hands = synthetic_hands(320, 180)
    quad = ((85, 35), (235, 35), (235, 145), (85, 145))
    compositor = PerspectiveCompositor(320, 180, True)
    result = compositor.composite(original, stylized, quad, 1.0, "detected", hands)
    expected = build_finger_occlusion_alpha(hands, 320, 180)
    overlap = (expected > 0.5) & (result.portal_alpha > 0.5)
    restored = np.linalg.norm(result.frame.astype(float) - original.astype(float), axis=2) < 15
    portal_elsewhere = (result.portal_alpha > 0.9) & (expected < 0.01)
    stylized_elsewhere = np.linalg.norm(result.frame.astype(float) - stylized.astype(float), axis=2) < 15
    return {
        "expected_foreground_mask_area_px": int(np.count_nonzero(expected > 0.5)),
        "actual_foreground_mask_area_px": int(np.count_nonzero(result.occlusion_alpha > 0.5)),
        "foreground_portal_overlap_px": int(np.count_nonzero(overlap)),
        "restored_pixel_coverage": round(float(np.mean(restored[overlap])), 6),
        "portal_pixels_not_unintentionally_removed": round(float(np.mean(stylized_elsewhere[portal_elsewhere])), 6),
    }


def temporal_metrics():
    tracker = StabilizedFrameTracker(WIDTH, HEIGHT)
    source = canonical_portal_corners(WIDTH, HEIGHT)
    projected_centers, mask_areas, quad_centers = [], [], []
    invalid = 0
    for frame in smooth_translation_sequence():
        state = tracker.update_quad(frame.raw_quad)
        quad = state.stabilized_quad
        matrix, reason, _, _ = validate_homography(quad, WIDTH, HEIGHT)
        if reason:
            invalid += 1
            continue
        center = np.array([[[WIDTH / 2.0, HEIGHT / 2.0]]], np.float32)
        projected_centers.append(cv2.perspectiveTransform(center, matrix)[0, 0])
        quad_centers.append(np.mean(np.asarray(quad), axis=0))
        mask_areas.append(float(np.mean(build_portal_alpha(quad, WIDTH, HEIGHT, 4.0))))
    center_errors = np.linalg.norm(np.asarray(projected_centers) - np.asarray(quad_centers), axis=1)
    movements = np.linalg.norm(np.diff(np.asarray(projected_centers), axis=0), axis=1)
    return {
        "frames": len(projected_centers),
        "invalid_transform_frames": invalid,
        "mean_projected_center_to_quad_center_error_px": round(float(np.mean(center_errors)), 6),
        "maximum_projected_center_to_quad_center_error_px": round(float(np.max(center_errors)), 6),
        "mean_portal_center_movement_px": round(float(np.mean(movements)), 6),
        "portal_center_movement_variance": round(float(np.var(movements)), 8),
        "feathered_mask_area_variance": round(float(np.var(mask_areas)), 12),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="tests/artifacts/milestone3_compositing_metrics.json")
    parser.add_argument("--benchmark-repeats", type=int, default=100)
    args = parser.parse_args()
    original, stylized = solid_pair(320, 180)
    stylized = checkerboard(320, 180)
    hands = synthetic_hands(320, 180)
    quad = QUADS[2]
    perspective = PerspectiveCompositor(320, 180, False)
    occlusion = PerspectiveCompositor(320, 180, True)
    report = {
        "perspective_accuracy": accuracy_metrics(),
        "edge_quality": edge_metrics(),
        "occlusion_coverage": occlusion_metrics(),
        "temporal_stability": temporal_metrics(),
        "performance": {
            "legacy": benchmark("legacy", lambda: legacy_composite(original, stylized, quad), args.benchmark_repeats),
            "perspective": benchmark("perspective", lambda: perspective.composite(original, stylized, quad, 1, "detected"), args.benchmark_repeats),
            "perspective_occlusion": benchmark("perspective_occlusion", lambda: occlusion.composite(original, stylized, quad, 1, "detected", hands), args.benchmark_repeats),
        },
        "mapping_policy": "entire generated frame mapped from canonical full-frame plane with bilinear inverse resampling",
    }
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()

