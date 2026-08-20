"""Synthetic quads for deterministic Portal Crossing tests and diagnostics."""

from __future__ import annotations

import math


WIDTH, HEIGHT = 320, 180


def quad_for_coverage(coverage: float, width: int = WIDTH, height: int = HEIGHT, skew: float = 0.0):
    scale = math.sqrt(max(0.0, min(1.0, coverage)))
    half_w = (width - 1) * scale / 2.0
    half_h = (height - 1) * scale / 2.0
    cx, cy = (width - 1) / 2.0, (height - 1) / 2.0
    return (
        (cx - half_w + skew, cy - half_h),
        (cx + half_w + skew, cy - half_h + skew * 0.25),
        (cx + half_w - skew, cy + half_h),
        (cx - half_w - skew, cy + half_h - skew * 0.25),
    )


def growing_sequence():
    values = [0.10, 0.14, 0.20, 0.28, 0.38, 0.48, 0.52, 0.57, 0.63, 0.70, 0.78, 0.84, 0.89, 0.94]
    return [quad_for_coverage(value, skew=index * 0.05) for index, value in enumerate(values)]


def below_threshold_sequence():
    return [quad_for_coverage(value) for value in (0.08, 0.16, 0.24, 0.32, 0.40, 0.44, 0.47, 0.48)]


def noisy_threshold_sequence():
    return [quad_for_coverage(value) for value in (0.46, 0.51, 0.48, 0.52, 0.49, 0.515, 0.485, 0.50)]


def shrinking_large_sequence():
    return [quad_for_coverage(value) for value in (0.82, 0.78, 0.73, 0.67, 0.61, 0.56, 0.52)]

