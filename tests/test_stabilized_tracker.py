import unittest

from composite import FrameTracker
from stabilized_tracker import (
    HOLD_FRAMES,
    PREDICTION_FRAMES,
    RESET_FRAMES,
    StabilizedFrameTracker,
)
from tests.tracking_sequences import (
    HEIGHT,
    WIDTH,
    rapid_translation_sequence,
    short_dropout_sequence,
    smooth_translation_sequence,
    stationary_sequence,
    quad_to_hands,
)


BASE = ((140.0, 80.0), (440.0, 80.0), (440.0, 280.0), (140.0, 280.0))


def center(quad):
    return (sum(p[0] for p in quad) / 4, sum(p[1] for p in quad) / 4)


class StabilizedGeometryTests(unittest.TestCase):
    def test_corner_order_stays_clockwise_and_identity_stable(self):
        tracker = StabilizedFrameTracker(WIDTH, HEIGHT)
        first = tracker.update_quad(BASE).stabilized_quad
        cyclic = BASE[2:] + BASE[:2]
        second = tracker.update_quad(cyclic).stabilized_quad
        self.assertEqual(first, second)

    def test_invalid_values_and_out_of_bounds_are_rejected(self):
        for quad in (
            ((float("nan"), 1), (2, 1), (2, 4), (1, 4)),
            ((-500, 20), (200, 20), (200, 200), (20, 200)),
            ((100, 100), (100, 100), (300, 240), (100, 240)),
        ):
            tracker = StabilizedFrameTracker(WIDTH, HEIGHT)
            state = tracker.update_quad(quad)
            self.assertIsNone(state.stabilized_quad)
            self.assertEqual(state.detection_state, "rejected")

    def test_self_intersection_is_rejected(self):
        tracker = StabilizedFrameTracker(WIDTH, HEIGHT)
        bowtie = (BASE[0], BASE[2], BASE[1], BASE[3])
        state = tracker.update_quad(bowtie)
        self.assertIsNone(state.stabilized_quad)
        self.assertEqual(state.rejection_reason, "self_intersection")

    def test_minimum_area_and_extreme_aspect_are_rejected(self):
        tracker = StabilizedFrameTracker(WIDTH, HEIGHT)
        tiny = ((100, 100), (110, 100), (110, 105), (100, 105))
        self.assertEqual(tracker.update_quad(tiny).rejection_reason, "minimum_area")
        tracker = StabilizedFrameTracker(WIDTH, HEIGHT)
        extreme = ((30, 100), (600, 100), (600, 120), (30, 120))
        self.assertEqual(tracker.update_quad(extreme).rejection_reason, "aspect_ratio")


class StabilizedMotionTests(unittest.TestCase):
    def test_stationary_jitter_improves_over_frozen_legacy_tracker(self):
        legacy = FrameTracker(WIDTH, HEIGHT)
        stabilized = StabilizedFrameTracker(WIDTH, HEIGHT)
        legacy_centers, stabilized_centers = [], []
        for frame in stationary_sequence():
            legacy_centers.append(center(legacy.update(quad_to_hands(frame.raw_quad))))
            stabilized_centers.append(center(stabilized.update_quad(frame.raw_quad).stabilized_quad))

        def total_motion(points):
            return sum(
                abs(points[i][0] - points[i - 1][0]) + abs(points[i][1] - points[i - 1][1])
                for i in range(1, len(points))
            )

        self.assertLess(total_motion(stabilized_centers), total_motion(legacy_centers))

    def test_stationary_filter_reduces_jitter(self):
        sequence = stationary_sequence()
        tracker = StabilizedFrameTracker(WIDTH, HEIGHT)
        raw_centers, filtered_centers = [], []
        for frame in sequence:
            state = tracker.update_quad(frame.raw_quad)
            raw_centers.append(center(frame.raw_quad))
            filtered_centers.append(center(state.stabilized_quad))
        raw_motion = sum(
            abs(raw_centers[i][0] - raw_centers[i - 1][0]) + abs(raw_centers[i][1] - raw_centers[i - 1][1])
            for i in range(1, len(raw_centers))
        )
        filtered_motion = sum(
            abs(filtered_centers[i][0] - filtered_centers[i - 1][0]) + abs(filtered_centers[i][1] - filtered_centers[i - 1][1])
            for i in range(1, len(filtered_centers))
        )
        self.assertLess(filtered_motion, raw_motion * 0.7)

    def test_smooth_translation_is_continuous_with_bounded_lag(self):
        tracker = StabilizedFrameTracker(WIDTH, HEIGHT)
        lags = []
        for frame in smooth_translation_sequence():
            state = tracker.update_quad(frame.raw_quad)
            self.assertIsNotNone(state.stabilized_quad)
            actual, truth = center(state.stabilized_quad), center(frame.truth_quad)
            lags.append(abs(actual[0] - truth[0]))
        self.assertLess(sum(lags) / len(lags), 12.0)
        self.assertLess(max(lags), 16.0)

    def test_rapid_full_quad_translation_is_accepted(self):
        tracker = StabilizedFrameTracker(WIDTH, HEIGHT)
        lags = []
        for frame in rapid_translation_sequence():
            state = tracker.update_quad(frame.raw_quad)
            self.assertEqual(state.detection_state, "detected")
            lags.append(abs(center(state.stabilized_quad)[0] - center(frame.truth_quad)[0]))
        self.assertEqual(tracker.metrics()["rejected_updates"], 0)
        self.assertLess(max(lags), 12.0)

    def test_isolated_corner_jump_is_rejected(self):
        tracker = StabilizedFrameTracker(WIDTH, HEIGHT)
        accepted = tracker.update_quad(BASE)
        jumped = list(BASE)
        jumped[2] = (jumped[2][0] + 120, jumped[2][1] - 90)
        rejected = tracker.update_quad(jumped)
        self.assertEqual(rejected.detection_state, "rejected")
        self.assertEqual(rejected.rejection_reason, "isolated_corner_jump")
        self.assertNotEqual(rejected.stabilized_quad, tuple(jumped))
        self.assertEqual(tracker.metrics()["rejected_updates"], 1)

    def test_large_coherent_translation_is_not_treated_as_corner_error(self):
        tracker = StabilizedFrameTracker(WIDTH, HEIGHT)
        tracker.update_quad(BASE)
        moved = tuple((x + 120, y) for x, y in BASE)
        state = tracker.update_quad(moved)
        self.assertEqual(state.detection_state, "detected")
        self.assertEqual(tracker.metrics()["rejected_updates"], 0)


class StabilizedDropoutTests(unittest.TestCase):
    def test_short_dropout_predicts_and_recovers_confidence(self):
        tracker = StabilizedFrameTracker(WIDTH, HEIGHT)
        for frame in short_dropout_sequence()[:18]:
            state = tracker.update_quad(frame.raw_quad)
        before = state.confidence
        first = tracker.update_quad(None)
        second = tracker.update_quad(None)
        self.assertTrue(first.is_predicted)
        self.assertTrue(second.is_predicted)
        self.assertLess(second.confidence, before)
        recovered = tracker.update_quad(short_dropout_sequence()[20].raw_quad)
        self.assertEqual(recovered.detection_state, "detected")
        self.assertGreater(recovered.confidence, second.confidence)

    def test_prediction_times_out_then_holds(self):
        tracker = StabilizedFrameTracker(WIDTH, HEIGHT)
        tracker.update_quad(BASE)
        for _ in range(PREDICTION_FRAMES):
            self.assertTrue(tracker.update_quad(None).is_predicted)
        held = tracker.update_quad(None)
        self.assertFalse(held.is_predicted)
        self.assertEqual(held.detection_state, "held")
        self.assertEqual(held.dropout_frames, PREDICTION_FRAMES + 1)
        self.assertLessEqual(PREDICTION_FRAMES, HOLD_FRAMES)

    def test_long_dropout_resets_without_stale_output(self):
        tracker = StabilizedFrameTracker(WIDTH, HEIGHT)
        tracker.update_quad(BASE)
        for _ in range(RESET_FRAMES - 1):
            state = tracker.update_quad(None)
        self.assertNotEqual(state.detection_state, "reset")
        reset = tracker.update_quad(None)
        self.assertEqual(reset.detection_state, "reset")
        self.assertIsNone(reset.stabilized_quad)
        self.assertEqual(reset.confidence, 0.0)
        self.assertEqual(tracker.metrics()["tracker_resets"], 1)

    def test_output_is_deterministic(self):
        sequence = smooth_translation_sequence()
        outputs = []
        for _ in range(2):
            tracker = StabilizedFrameTracker(WIDTH, HEIGHT)
            outputs.append([tracker.update_quad(frame.raw_quad) for frame in sequence])
        self.assertEqual(outputs[0], outputs[1])


if __name__ == "__main__":
    unittest.main()
