import unittest

import numpy as np

from perspective_compositor import PerspectiveCompositor
from portal_crossing import (
    PortalCrossingController,
    TransitionState,
    expand_quad,
    portal_coverage,
    smoothstep,
)
from tests.compositing_fixtures import checkerboard, solid_pair, synthetic_hands
from tests.portal_crossing_fixtures import (
    HEIGHT,
    WIDTH,
    below_threshold_sequence,
    growing_sequence,
    noisy_threshold_sequence,
    quad_for_coverage,
    shrinking_large_sequence,
)


def run_sequence(controller, sequence, confidence=0.95):
    return [controller.update(quad, confidence, "detected", index) for index, quad in enumerate(sequence)]


class CoverageAndGeometryTests(unittest.TestCase):
    def test_visible_clipped_coverage_handles_rotation_and_offscreen(self):
        self.assertAlmostEqual(portal_coverage(quad_for_coverage(0.64), WIDTH, HEIGHT), 0.64, places=5)
        offscreen = ((-80, 20), (200, 0), (230, 175), (-60, 179))
        value = portal_coverage(offscreen, WIDTH, HEIGHT)
        self.assertGreater(value, 0.5)
        self.assertLessEqual(value, 1.0)

    def test_smoothstep_and_expansion_endpoints_are_exact(self):
        quad = quad_for_coverage(0.2)
        self.assertEqual(smoothstep(-2), 0)
        self.assertEqual(smoothstep(0), 0)
        self.assertEqual(smoothstep(1), 1)
        self.assertEqual(smoothstep(3), 1)
        self.assertEqual(expand_quad(quad, WIDTH, HEIGHT, 0), quad)
        self.assertEqual(
            expand_quad(quad, WIDTH, HEIGHT, 1),
            ((0.0, 0.0), (319.0, 0.0), (319.0, 179.0), (0.0, 179.0)),
        )


class StateMachineTests(unittest.TestCase):
    def test_inactive_visible_entering_full_ai_and_monotonic_progress(self):
        controller = PortalCrossingController(WIDTH, HEIGHT)
        snapshots = run_sequence(controller, growing_sequence())
        states = [snapshot.state for snapshot in snapshots]
        self.assertEqual(states[0], TransitionState.PORTAL_VISIBLE.value)
        self.assertIn(TransitionState.ENTERING.value, states)
        self.assertEqual(states[-1], TransitionState.FULL_AI.value)
        progress = [snapshot.progress for snapshot in snapshots if snapshot.state in {TransitionState.ENTERING.value, TransitionState.FULL_AI.value}]
        self.assertTrue(all(0 <= value <= 1 for value in progress))
        self.assertTrue(all(a <= b for a, b in zip(progress, progress[1:])))

    def test_below_threshold_noise_shrinking_and_low_confidence_do_not_enter(self):
        for sequence, confidence in (
            (below_threshold_sequence(), 0.95),
            (noisy_threshold_sequence(), 0.95),
            (shrinking_large_sequence(), 0.95),
            (growing_sequence(), 0.35),
        ):
            states = [snapshot.state for snapshot in run_sequence(PortalCrossingController(WIDTH, HEIGHT), sequence, confidence)]
            self.assertNotIn(TransitionState.ENTERING.value, states)
            self.assertNotIn(TransitionState.FULL_AI.value, states)

    def test_temporary_dropout_holds_and_prolonged_dropout_exits_safely(self):
        controller = PortalCrossingController(WIDTH, HEIGHT)
        snapshots = run_sequence(controller, growing_sequence()[:-2])
        entering = snapshots[-1]
        self.assertEqual(entering.state, TransitionState.ENTERING.value)
        held = [controller.update(None, 0.2, "predicted") for _ in range(4)]
        self.assertTrue(all(snapshot.state == TransitionState.ENTERING.value for snapshot in held))
        self.assertTrue(all(snapshot.raw_progress == entering.raw_progress for snapshot in held))
        aborted = controller.update(None, 0.1, "lost")
        self.assertEqual(aborted.state, TransitionState.INACTIVE.value)
        self.assertEqual(aborted.progress, 0)

    def test_reverse_transition_and_multiple_events_reset(self):
        controller = PortalCrossingController(WIDTH, HEIGHT)
        run_sequence(controller, growing_sequence())
        self.assertEqual(controller.state, TransitionState.FULL_AI)
        for _ in range(5):
            snapshot = controller.update(quad_for_coverage(0.20), 0.95, "detected")
        self.assertIn(controller.state, {TransitionState.EXITING, TransitionState.PORTAL_VISIBLE})
        self.assertGreater(snapshot.raw_progress, 0.0)
        previous = snapshot.raw_progress
        next_snapshot = controller.update(quad_for_coverage(0.20), 0.95, "detected")
        self.assertLess(next_snapshot.raw_progress, previous)
        self.assertLessEqual(
            previous - next_snapshot.raw_progress,
            1 / controller.config.fallback_exit_frames,
        )
        for _ in range(12):
            controller.update(None, 0.0, "lost")
        self.assertEqual(controller.state, TransitionState.INACTIVE)
        first_events = controller.event_metadata()
        self.assertEqual(len(first_events), 1)
        self.assertIsNotNone(first_events[0]["end_frame"])
        controller.update(quad_for_coverage(0.12), 0.9, "detected")
        self.assertEqual(controller.current_event.portal_id, 2)

    def test_full_ai_persists_for_large_confident_geometry(self):
        controller = PortalCrossingController(WIDTH, HEIGHT)
        run_sequence(controller, growing_sequence())
        snapshots = [controller.update(quad_for_coverage(0.92), 0.95, "detected") for _ in range(10)]
        self.assertTrue(all(snapshot.state == TransitionState.FULL_AI.value for snapshot in snapshots))
        self.assertTrue(all(snapshot.progress == 1 for snapshot in snapshots))

    def test_state_machine_is_deterministic(self):
        sequence = growing_sequence() + [None] * 16 + [quad_for_coverage(0.12)]
        runs = []
        for _ in range(2):
            controller = PortalCrossingController(WIDTH, HEIGHT)
            runs.append([
                controller.update(quad, 0.95 if quad else 0, "detected" if quad else "lost")
                for quad in sequence
            ])
        self.assertEqual(runs[0], runs[1])


class TransitionCompositeTests(unittest.TestCase):
    def test_full_screen_endpoint_matches_generated_frame_exactly(self):
        original, _ = solid_pair(WIDTH, HEIGHT)
        generated = checkerboard(WIDTH, HEIGHT)
        full_quad = ((0, 0), (319, 0), (319, 179), (0, 179))
        result = PerspectiveCompositor(WIDTH, HEIGHT, True).composite(
            original, generated, full_quad, 0, "lost", synthetic_hands(WIDTH, HEIGHT), transition_progress=1
        )
        np.testing.assert_array_equal(result.frame, generated)
        self.assertEqual(result.feather_px, 0)
        self.assertEqual(float(result.occlusion_alpha.max()), 0)

    def test_occlusion_and_feather_fade_without_endpoint_jump(self):
        original, generated = solid_pair(WIDTH, HEIGHT)
        hands = synthetic_hands(WIDTH, HEIGHT)
        source_quad = quad_for_coverage(0.52)
        early_quad = expand_quad(source_quad, WIDTH, HEIGHT, 0.2)
        late_quad = expand_quad(source_quad, WIDTH, HEIGHT, 0.999)
        compositor = PerspectiveCompositor(WIDTH, HEIGHT, True)
        early = compositor.composite(original, generated, early_quad, 1, "detected", hands, transition_progress=smoothstep(0.2))
        late = compositor.composite(original, generated, late_quad, 1, "detected", hands, transition_progress=smoothstep(0.999))
        full = compositor.composite(original, generated, ((0,0),(319,0),(319,179),(0,179)), 1, "detected", hands, transition_progress=1)
        self.assertLess(late.feather_px, early.feather_px)
        self.assertLess(float(late.occlusion_alpha.max()), float(early.occlusion_alpha.max()))
        self.assertLess(float(np.mean(np.abs(full.frame.astype(float) - late.frame.astype(float)))), 1.0)


if __name__ == "__main__":
    unittest.main()
