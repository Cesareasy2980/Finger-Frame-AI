"""Small deterministic landmark-sequence fixtures for tracker regression tests."""

from dataclasses import dataclass
import math
from types import SimpleNamespace


WIDTH, HEIGHT = 640, 360


@dataclass(frozen=True)
class SequenceFrame:
    raw_quad: tuple[tuple[float, float], ...] | None
    truth_quad: tuple[tuple[float, float], ...]


def _quad(left, top, right, bottom):
    return ((left, top), (right, top), (right, bottom), (left, bottom))


def _offset(quad, dx, dy):
    return tuple((x + dx, y + dy) for x, y in quad)


def _noisy(quad, frame, amplitude=2.0):
    return tuple(
        (
            x + math.sin(frame * 1.73 + corner * 0.91) * amplitude,
            y + math.cos(frame * 1.31 + corner * 1.17) * amplitude,
        )
        for corner, (x, y) in enumerate(quad)
    )


def stationary_sequence():
    truth = _quad(180, 80, 460, 280)
    return [SequenceFrame(_noisy(truth, frame, 2.4), truth) for frame in range(80)]


def smooth_translation_sequence():
    base = _quad(120, 90, 360, 260)
    frames = []
    for frame in range(70):
        truth = _offset(base, frame * 2.2, math.sin(frame / 12) * 3.0)
        frames.append(SequenceFrame(_noisy(truth, frame, 1.6), truth))
    return frames


def short_dropout_sequence():
    base = _quad(130, 85, 370, 255)
    frames = []
    for frame in range(45):
        truth = _offset(base, frame * 1.5, 0)
        raw = None if frame in (18, 19) else _noisy(truth, frame, 1.2)
        frames.append(SequenceFrame(raw, truth))
    return frames


def rapid_translation_sequence():
    base = _quad(80, 95, 280, 250)
    frames = []
    for frame in range(30):
        truth = _offset(base, frame * 10.5, 0)
        frames.append(SequenceFrame(_noisy(truth, frame, 1.0), truth))
    return frames


def quad_to_hands(quad):
    """Convert the semantic quad into the existing two-hand landmark contract."""
    if quad is None:
        return []
    landmarks = []
    for wrist_x, index, thumb in (
        (0.2, quad[0], quad[3]),
        (0.8, quad[1], quad[2]),
    ):
        hand = [SimpleNamespace(x=0.0, y=0.0) for _ in range(21)]
        hand[0] = SimpleNamespace(x=wrist_x, y=0.88)
        hand[4] = SimpleNamespace(x=thumb[0] / WIDTH, y=thumb[1] / HEIGHT)
        hand[8] = SimpleNamespace(x=index[0] / WIDTH, y=index[1] / HEIGHT)
        hand[9] = SimpleNamespace(x=wrist_x, y=0.48)
        landmarks.append(hand)
    return landmarks


SEQUENCES = {
    "stationary": stationary_sequence,
    "smooth_translation": smooth_translation_sequence,
    "short_dropout": short_dropout_sequence,
    "rapid_translation": rapid_translation_sequence,
}

