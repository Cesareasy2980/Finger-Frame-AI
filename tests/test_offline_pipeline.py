import json
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT / "tests" / "fixtures" / "finger_frame_short.mp4"
STYLIZED = ROOT / "tests" / "fixtures" / "finger_frame_short_stylized.mp4"


class OfflinePipelineTests(unittest.TestCase):
    def test_missing_input_is_rejected(self):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "composite.py"),
                str(ROOT / "tests" / "fixtures" / "missing.mp4"),
                str(STYLIZED),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing input", result.stdout + result.stderr)

    def test_existing_but_invalid_video_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="finger-frame-invalid-") as temp:
            invalid = Path(temp) / "invalid.mp4"
            invalid.write_bytes(b"not a video")
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "composite.py"),
                    str(invalid),
                    str(STYLIZED),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Could not decode original video", result.stdout + result.stderr)

    def test_fixture_pair_runs_end_to_end_with_audio_and_metrics(self):
        self.assertTrue(ORIGINAL.exists())
        self.assertTrue(STYLIZED.exists())
        with tempfile.TemporaryDirectory(prefix="finger-frame-baseline-") as temp:
            output = Path(temp) / "final.mp4"
            metrics_path = Path(temp) / "metrics.json"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "composite.py"),
                    str(ORIGINAL),
                    str(STYLIZED),
                    "-o",
                    str(output),
                    "--metrics",
                    str(metrics_path),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))

            self.assertTrue(output.exists())
            self.assertGreater(output.stat().st_size, 0)
            self.assertEqual(metrics["tracker"]["frames_processed"], 24)
            self.assertEqual(metrics["tracker"]["raw_valid_quad_frames"], 24)
            self.assertEqual(metrics["tracker"]["output_quad_frames"], 24)
            self.assertEqual(metrics["compositing"]["valid_polygon_frames"], 24)
            self.assertEqual(metrics["compositing"]["invalid_polygon_frames"], 0)
            self.assertEqual(metrics["compositing"]["output_width"], 320)
            self.assertEqual(metrics["compositing"]["output_height"], 180)
            self.assertEqual(metrics["compositing"]["fps"], 12.0)
            self.assertEqual(metrics["compositing_mode"], "perspective_occlusion")
            self.assertEqual(metrics["compositing"]["perspective"]["applied_frames"], 24)
            self.assertEqual(metrics["compositing"]["perspective"]["invalid_transform_frames"], 0)

            streams = metrics["output"]["streams"]
            video = next(stream for stream in streams if stream["codec_type"] == "video")
            audio = next(stream for stream in streams if stream["codec_type"] == "audio")
            self.assertEqual(video["codec_name"], "h264")
            self.assertEqual(video["nb_read_frames"], "24")
            self.assertEqual(audio["codec_name"], "aac")
            self.assertEqual(audio["sample_rate"], "48000")
            self.assertAlmostEqual(
                float(metrics["output"]["format"]["duration"]), 2.0, places=2
            )

    def test_legacy_compositor_reproduces_milestone_zero_bytes(self):
        with tempfile.TemporaryDirectory(prefix="finger-frame-legacy-") as temp:
            output = Path(temp) / "legacy.mp4"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "composite.py"),
                    str(ORIGINAL),
                    str(STYLIZED),
                    "-o",
                    str(output),
                    "--tracking-mode",
                    "legacy",
                    "--compositing-mode",
                    "legacy",
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            digest = hashlib.sha256(output.read_bytes()).hexdigest().upper()
            self.assertEqual(
                digest,
                "8A7903B7C03FC7B1EA642B7E08193B088B01B9DE0FB2D9ED6D41DD8DFFA37F0A",
            )


if __name__ == "__main__":
    unittest.main()
