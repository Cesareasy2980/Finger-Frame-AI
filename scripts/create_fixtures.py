#!/usr/bin/env python3
"""Recreate the deterministic Milestone 0 fixtures from the committed demo."""

from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "examples" / "final.mp4"
FIXTURES = ROOT / "tests" / "fixtures"
ORIGINAL = FIXTURES / "finger_frame_short.mp4"
STYLIZED = FIXTURES / "finger_frame_short_stylized.mp4"


def run(command):
    subprocess.run(command, cwd=ROOT, check=True)


def main():
    if not SOURCE.exists():
        sys.exit(f"Missing committed source demo: {SOURCE}")
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg must be on PATH")

    FIXTURES.mkdir(parents=True, exist_ok=True)
    run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", "0", "-t", "2", "-i", str(SOURCE),
            "-f", "lavfi", "-t", "2", "-i",
            "sine=frequency=440:sample_rate=48000",
            "-vf", "scale=320:180:flags=lanczos,fps=12",
            "-c:v", "libx264", "-preset", "slow", "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "96k", "-shortest",
            "-movflags", "+faststart", str(ORIGINAL),
        ]
    )
    run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-i", str(ORIGINAL),
            "-vf", "hue=h=140:s=1.7,eq=contrast=1.15", "-an",
            "-c:v", "libx264", "-preset", "slow", "-crf", "18",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(STYLIZED),
        ]
    )
    print(f"Created {ORIGINAL}")
    print(f"Created {STYLIZED}")


if __name__ == "__main__":
    main()
