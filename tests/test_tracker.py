import unittest
from types import SimpleNamespace

from composite import FrameTracker


def make_hand(wrist_x, index_x, thumb_x, index_y=0.2, thumb_y=0.6):
    landmarks = [SimpleNamespace(x=0.0, y=0.0) for _ in range(21)]
    landmarks[0] = SimpleNamespace(x=wrist_x, y=0.8)
    landmarks[4] = SimpleNamespace(x=thumb_x, y=thumb_y)
    landmarks[8] = SimpleNamespace(x=index_x, y=index_y)
    landmarks[9] = SimpleNamespace(x=wrist_x, y=0.4)
    return landmarks


def make_hands(offset=0.0):
    return [
        make_hand(0.2 + offset, 0.2 + offset, 0.2 + offset),
        make_hand(0.8 + offset, 0.8 + offset, 0.8 + offset),
    ]


class FrameTrackerGeometryTests(unittest.TestCase):
    def test_requires_exactly_two_hands(self):
        tracker = FrameTracker(100, 100)
        self.assertIsNone(tracker.compute_quad([]))
        self.assertIsNone(tracker.compute_quad([make_hands()[0]]))

    def test_anatomical_quad_order_is_preserved(self):
        tracker = FrameTracker(100, 100)
        quad = tracker.compute_quad(make_hands())
        self.assertEqual(
            quad,
            [(20.0, 20.0), (80.0, 20.0), (80.0, 60.0), (20.0, 60.0)],
        )

    def test_spread_gate_rejects_closed_fingers(self):
        tracker = FrameTracker(100, 100)
        hands = [
            make_hand(0.2, 0.2, 0.2, index_y=0.2, thumb_y=0.25),
            make_hand(0.8, 0.8, 0.8, index_y=0.2, thumb_y=0.25),
        ]
        self.assertIsNone(tracker.compute_quad(hands))

    def test_area_gate_rejects_too_narrow_polygon(self):
        tracker = FrameTracker(100, 100)
        hands = [
            make_hand(0.495, 0.495, 0.495),
            make_hand(0.505, 0.505, 0.505),
        ]
        self.assertIsNone(tracker.compute_quad(hands))


class FrameTrackerStateTests(unittest.TestCase):
    def test_small_motion_uses_existing_minimum_smoothing(self):
        tracker = FrameTracker(100, 100)
        initial = tracker.update(make_hands())
        moved = tracker.update(make_hands(offset=0.01))
        self.assertAlmostEqual(moved[0][0], initial[0][0] + 0.35, places=6)

    def test_first_large_jump_is_rejected_and_second_is_accepted(self):
        tracker = FrameTracker(100, 100)
        initial = tracker.update(make_hands())
        rejected = tracker.update(make_hands(offset=0.4))
        self.assertEqual(rejected, initial)
        self.assertEqual(tracker.metrics()["rejected_jumps"], 1)

        accepted = tracker.update(make_hands(offset=0.4))
        self.assertNotEqual(accepted, initial)
        self.assertEqual(tracker.metrics()["rejected_jumps"], 1)

    def test_dropout_holds_25_frames_then_fades_and_resets(self):
        tracker = FrameTracker(100, 100)
        tracker.update(make_hands())
        for _ in range(25):
            self.assertIsNotNone(tracker.update([]))
        self.assertEqual(tracker.metrics()["dropout_held_frames"], 25)

        for _ in range(30):
            if tracker.update([]) is None:
                break
        self.assertIsNone(tracker.corners)
        self.assertEqual(tracker.metrics()["tracker_resets"], 1)

    def test_metrics_count_raw_and_visible_quads(self):
        tracker = FrameTracker(100, 100)
        tracker.update(make_hands())
        tracker.update([])
        metrics = tracker.metrics()
        self.assertEqual(metrics["frames_processed"], 2)
        self.assertEqual(metrics["raw_valid_quad_frames"], 1)
        self.assertEqual(metrics["output_quad_frames"], 2)
        self.assertEqual(metrics["detection_success_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()
