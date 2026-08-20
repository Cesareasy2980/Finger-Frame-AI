import unittest

import cv2
import numpy as np

from perspective_compositor import (
    PerspectiveCompositor,
    adaptive_feather_width,
    build_finger_occlusion_alpha,
    build_portal_alpha,
    canonical_portal_corners,
    confidence_opacity,
    validate_homography,
)
from tests.compositing_fixtures import checkerboard, solid_pair, synthetic_hands


class HomographyTests(unittest.TestCase):
    def assert_reprojects(self, quad, width=320, height=180):
        matrix, reason, mean_error, max_error = validate_homography(quad, width, height)
        self.assertIsNone(reason)
        self.assertIsNotNone(matrix)
        self.assertLess(mean_error, 1e-3)
        self.assertLess(max_error, 1e-3)
        projected = cv2.perspectiveTransform(canonical_portal_corners(width, height)[None], matrix)[0]
        np.testing.assert_allclose(projected, np.asarray(quad), atol=1e-3)

    def test_identity_homography(self):
        self.assert_reprojects(((0, 0), (319, 0), (319, 179), (0, 179)))

    def test_translation_rotation_scaling_and_trapezoid(self):
        for quad in (
            ((20, 15), (300, 15), (300, 165), (20, 165)),
            ((100, 20), (280, 80), (220, 165), (40, 105)),
            ((100, 55), (220, 55), (220, 125), (100, 125)),
            ((80, 35), (250, 55), (225, 150), (95, 140)),
        ):
            self.assert_reprojects(quad)

    def test_orientation_is_not_mirrored_or_reversed(self):
        reversed_quad = ((80, 35), (95, 140), (225, 150), (250, 55))
        matrix, reason, _, _ = validate_homography(reversed_quad, 320, 180)
        self.assertIsNone(matrix)
        self.assertEqual(reason, "invalid_winding_or_collinear")

    def test_degenerate_self_intersecting_and_tiny_quads_reject(self):
        cases = (
            (((80, 40), (240, 140), (240, 40), (80, 140)), "self_intersection"),
            (((100, 100), (200, 100), (300, 100), (50, 100)), "invalid_winding_or_collinear"),
            (((100, 100), (101, 100), (101, 101), (100, 101)), "minimum_area"),
        )
        for quad, expected in cases:
            self.assertEqual(validate_homography(quad, 320, 180)[1], expected)

    def test_partially_offscreen_quad_is_clipped_not_rejected(self):
        quad = ((-35, 25), (210, 15), (230, 150), (-25, 165))
        self.assert_reprojects(quad)


class MaskTests(unittest.TestCase):
    def test_feather_mask_has_zero_transition_and_opaque_center(self):
        quad = ((60, 35), (260, 35), (260, 145), (60, 145))
        alpha = build_portal_alpha(quad, 320, 180, 4)
        self.assertEqual(float(alpha[10, 10]), 0.0)
        self.assertGreater(float(alpha[90, 160]), 0.99)
        self.assertTrue(np.any((alpha > 0) & (alpha < 1)))

    def test_adaptive_feather_scales_with_portal_and_resolution(self):
        small = ((120, 70), (200, 70), (200, 110), (120, 110))
        large = ((30, 20), (290, 20), (290, 160), (30, 160))
        self.assertLess(adaptive_feather_width(small, 320, 180), adaptive_feather_width(large, 320, 180))
        scaled = tuple((x * 2, y * 2) for x, y in small)
        self.assertGreater(adaptive_feather_width(scaled, 640, 360), adaptive_feather_width(small, 320, 180))

    def test_occlusion_mask_is_local_and_antialiased(self):
        mask = build_finger_occlusion_alpha(synthetic_hands(320, 180), 320, 180)
        coverage = float(np.mean(mask > 0.01))
        self.assertGreater(coverage, 0.01)
        self.assertLess(coverage, 0.2)
        self.assertTrue(np.any((mask > 0) & (mask < 1)))


class CompositeTests(unittest.TestCase):
    QUAD = ((85, 35), (235, 35), (235, 145), (85, 145))

    def test_perspective_composite_and_aspect_policy_are_deterministic(self):
        original, _ = solid_pair(320, 180)
        stylized = checkerboard(320, 180)
        first = PerspectiveCompositor(320, 180, False).composite(original, stylized, self.QUAD, 1, "detected")
        second = PerspectiveCompositor(320, 180, False).composite(original, stylized, self.QUAD, 1, "detected")
        self.assertTrue(first.applied)
        np.testing.assert_array_equal(first.frame, second.frame)
        np.testing.assert_array_equal(first.warped_portal, second.warped_portal)

    def test_occlusion_restores_original_finger_pixels(self):
        original, stylized = solid_pair(320, 180)
        hands = synthetic_hands(320, 180)
        plain = PerspectiveCompositor(320, 180, False).composite(original, stylized, self.QUAD, 1, "detected", hands)
        occluded = PerspectiveCompositor(320, 180, True).composite(original, stylized, self.QUAD, 1, "detected", hands)
        overlap = (occluded.occlusion_alpha > 0.8) & (occluded.portal_alpha > 0.8)
        self.assertGreater(int(np.count_nonzero(overlap)), 20)
        plain_error = np.mean(np.abs(plain.frame[overlap].astype(float) - original[overlap].astype(float)))
        restored_error = np.mean(np.abs(occluded.frame[overlap].astype(float) - original[overlap].astype(float)))
        self.assertLess(restored_error, plain_error * 0.3)
        self.assertGreater(float(np.mean(occluded.portal_alpha > 0.9)), 0.05)

    def test_confidence_and_tracker_state_gate_portal(self):
        self.assertEqual(confidence_opacity(0.05, "detected"), 0)
        self.assertEqual(confidence_opacity(1, "reset"), 0)
        self.assertLess(confidence_opacity(0.5, "predicted"), confidence_opacity(0.5, "detected"))
        original, stylized = solid_pair(320, 180)
        result = PerspectiveCompositor(320, 180).composite(original, stylized, self.QUAD, 0.05, "detected")
        self.assertFalse(result.applied)
        np.testing.assert_array_equal(result.frame, original)

    def test_invalid_tracker_geometry_fails_safe(self):
        original, stylized = solid_pair(320, 180)
        result = PerspectiveCompositor(320, 180).composite(
            original, stylized, ((10, 10), (200, 130), (200, 10), (10, 130)), 1, "detected"
        )
        self.assertFalse(result.applied)
        np.testing.assert_array_equal(result.frame, original)
        self.assertEqual(result.compositing_state, "invalid_transform")

    def test_multiple_resolutions_and_large_portals(self):
        for width, height in ((320, 180), (640, 360), (1280, 720)):
            original, stylized = solid_pair(width, height)
            quad = ((width * .08, height * .1), (width * .92, height * .14), (width * .86, height * .9), (width * .12, height * .86))
            result = PerspectiveCompositor(width, height, False).composite(original, stylized, quad, 1, "detected")
            self.assertTrue(result.applied)
            self.assertEqual(result.frame.shape, original.shape)


if __name__ == "__main__":
    unittest.main()

