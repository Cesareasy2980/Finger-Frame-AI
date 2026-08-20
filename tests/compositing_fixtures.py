"""Deterministic images and geometry for perspective-compositor tests."""

from types import SimpleNamespace

import cv2
import numpy as np


def checkerboard(width, height, cell=20):
    y, x = np.indices((height, width))
    checker = ((x // cell + y // cell) % 2) * 180 + 40
    # Draw on a contiguous uint8 image. np.indices yields int32 on Windows and
    # int64 on Linux, and cv2.putText rejects the latter, so the conversion has
    # to happen before the labels are drawn rather than after.
    image = np.ascontiguousarray(
        np.stack((checker, np.roll(checker, cell // 2, axis=1), 255 - checker), axis=2),
        dtype=np.uint8,
    )
    for label, point, color in (
        ("TL", (8, 24), (0, 0, 255)),
        ("TR", (width - 48, 24), (0, 255, 0)),
        ("BR", (width - 48, height - 10), (255, 0, 0)),
        ("BL", (8, height - 10), (0, 255, 255)),
    ):
        cv2.putText(image, label, point, cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)
    return image


def solid_pair(width, height):
    original = np.full((height, width, 3), (30, 40, 220), dtype=np.uint8)
    stylized = np.full((height, width, 3), (210, 180, 25), dtype=np.uint8)
    return original, stylized


def synthetic_hands(width, height):
    hands = []
    for side in (0.28, 0.72):
        hand = [SimpleNamespace(x=side, y=0.75) for _ in range(21)]
        hand[0] = SimpleNamespace(x=side, y=0.86)
        hand[9] = SimpleNamespace(x=side, y=0.57)
        hand[5] = SimpleNamespace(x=side, y=0.61)
        hand[6] = SimpleNamespace(x=side, y=0.48)
        hand[7] = SimpleNamespace(x=side, y=0.36)
        hand[8] = SimpleNamespace(x=side, y=0.24)
        thumb_x = side + (0.13 if side < 0.5 else -0.13)
        hand[2] = SimpleNamespace(x=side, y=0.67)
        hand[3] = SimpleNamespace(x=thumb_x, y=0.68)
        hand[4] = SimpleNamespace(x=thumb_x, y=0.68)
        hands.append(hand)
    return hands

