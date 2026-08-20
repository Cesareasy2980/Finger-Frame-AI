#!/usr/bin/env python3
"""Composite an AI-restyled video inside a tracked finger frame.

Tracks the finger-frame gesture (both hands, index + thumb "L"s) in the
original footage with MediaPipe Hand Landmarker, then reveals the stylized
video through the quad the fingers form — the same window effect as the
finger-frame-effect web app, with the dashed outline and corner dots.

The frozen Milestone 0 tracker is available as ``legacy``.  The default
``stabilized`` mode adds validated geometry, stable ordering, adaptive
per-corner filtering, coherent-quad motion checks, bounded prediction, and
confidence while retaining the same MediaPipe detector and fingertip inputs.

Usage:
    python composite.py finger-effect-raw.mp4 stylized.mp4 -o final.mp4
"""

import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

import cv2
import numpy as np

from stabilized_tracker import StabilizedFrameTracker, TrackedFrame
from perspective_compositor import PerspectiveCompositor
from portal_crossing import PortalCrossingController, TransitionState

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)
MODEL_PATH = "hand_landmarker.task"

WRIST, THUMB_TIP, INDEX_TIP, MIDDLE_MCP = 0, 4, 8, 9

# Tracking constants — mirror main.js in the web app.
MAX_LOST_FRAMES = 25
JUMP_CONFIRM_FRAMES = 2
JUMP_FRACTION = 0.3
ALPHA_MIN, ALPHA_MAX = 0.35, 0.85
ALPHA_SCALE = 0.05
PRESENCE_IN, PRESENCE_OUT = 0.12, 0.05
SPREAD_ACQUIRE, SPREAD_KEEP = 0.75, 0.2
AREA_ACQUIRE, AREA_KEEP = 0.005, 0.0005


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def lerp_pt(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def polygon_area(pts):
    a = 0.0
    for i in range(len(pts)):
        p, q = pts[i], pts[(i + 1) % len(pts)]
        a += p[0] * q[1] - q[0] * p[1]
    return abs(a / 2)


def angle_sorted(pts):
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    return sorted(pts, key=lambda p: math.atan2(p[1] - cy, p[0] - cx))


class FrameTracker:
    """Stateful quad tracker, ported from the web app's main loop."""

    def __init__(self, width, height):
        self.w, self.h = width, height
        self.corners = None
        self.presence = 0.0
        self.frame_active = False
        self.lost_frames = 0
        self.jump_frames = 0
        # Observability only: these counters do not participate in tracking.
        self.frames_processed = 0
        self.raw_valid_quad_frames = 0
        self.output_quad_frames = 0
        self.dropout_held_frames = 0
        self.rejected_jumps = 0
        self.tracker_resets = 0
        self._movement_samples = 0
        self._movement_sum = 0.0
        self._max_movement = 0.0

    def compute_quad(self, hands):
        """hands: list of landmark lists (normalized). Returns anatomical quad
        [A.index, B.index, B.thumb, A.thumb] (A = smaller wrist x) or None."""
        if len(hands) != 2:
            return None
        info = []
        for lm in hands:
            px = lambda i: (lm[i].x * self.w, lm[i].y * self.h)
            index, thumb = px(INDEX_TIP), px(THUMB_TIP)
            scale = dist(px(WRIST), px(MIDDLE_MCP)) + 1
            needed = SPREAD_KEEP if self.frame_active else SPREAD_ACQUIRE
            if dist(thumb, index) < scale * needed:
                return None
            info.append({"index": index, "thumb": thumb, "wx": px(WRIST)[0]})
        info.sort(key=lambda hd: hd["wx"])
        a, b = info
        pts = [a["index"], b["index"], b["thumb"], a["thumb"]]
        min_area = AREA_KEEP if self.frame_active else AREA_ACQUIRE
        if polygon_area(angle_sorted(pts)) < self.w * self.h * min_area:
            return None
        return pts

    def update(self, hands):
        self.frames_processed += 1
        target = self.compute_quad(hands) if hands else None

        if target:
            self.raw_valid_quad_frames += 1
            if self.corners is None:
                self.lost_frames = 0
                self.frame_active = True
                self.jump_frames = 0
                self.corners = target
                self.presence = min(1.0, self.presence + PRESENCE_IN)
            else:
                moved = sum(dist(p, c) for p, c in zip(target, self.corners)) / 4
                self._movement_samples += 1
                self._movement_sum += moved
                self._max_movement = max(self._max_movement, moved)
                if (
                    moved > self.w * JUMP_FRACTION
                    and self.jump_frames + 1 < JUMP_CONFIRM_FRAMES
                ):
                    self.jump_frames += 1
                    self.rejected_jumps += 1
                    self.lost_frames += 1
                    if self.lost_frames > MAX_LOST_FRAMES:
                        self.presence = max(0.0, self.presence - PRESENCE_OUT)
                else:
                    self.lost_frames = 0
                    self.frame_active = True
                    self.jump_frames = 0
                    alpha = min(
                        ALPHA_MAX, max(ALPHA_MIN, moved / (self.w * ALPHA_SCALE))
                    )
                    self.corners = [
                        lerp_pt(c, p, alpha) for c, p in zip(self.corners, target)
                    ]
                    self.presence = min(1.0, self.presence + PRESENCE_IN)
        elif self.corners is not None and self.lost_frames < MAX_LOST_FRAMES:
            self.lost_frames += 1
            self.dropout_held_frames += 1
            self.presence = min(1.0, self.presence + PRESENCE_IN)
        else:
            self.presence = max(0.0, self.presence - PRESENCE_OUT)
            if self.presence == 0:
                if self.corners is not None:
                    self.tracker_resets += 1
                self.corners = None
                self.frame_active = False
                self.jump_frames = 0

        output = self.corners if self.presence > 0.01 else None
        if output is not None:
            self.output_quad_frames += 1
        return output

    def metrics(self):
        """Return deterministic baseline counters without changing tracker state."""
        success = (
            self.raw_valid_quad_frames / self.frames_processed
            if self.frames_processed
            else 0.0
        )
        average_movement = (
            self._movement_sum / self._movement_samples
            if self._movement_samples
            else 0.0
        )
        return {
            "frames_processed": self.frames_processed,
            "raw_valid_quad_frames": self.raw_valid_quad_frames,
            "output_quad_frames": self.output_quad_frames,
            "detection_success_rate": round(success, 6),
            "average_mean_corner_movement_pixels": round(average_movement, 6),
            "maximum_mean_corner_jump_pixels": round(self._max_movement, 6),
            "dropout_held_frames": self.dropout_held_frames,
            "rejected_jumps": self.rejected_jumps,
            "tracker_resets": self.tracker_resets,
        }


def draw_outline(frame, quad, presence, t):
    """Dashed marching-ants outline + pulsing corner dots, like the web app."""
    overlay = frame.copy()

    # Dashed edges with a marching offset.
    dash_on, dash_off = 10.0, 8.0
    period = dash_on + dash_off
    offset = (t * 40.0) % period
    for i in range(4):
        p0 = np.array(quad[i], dtype=float)
        p1 = np.array(quad[(i + 1) % 4], dtype=float)
        seg = p1 - p0
        length = float(np.hypot(*seg))
        if length < 1:
            continue
        u = seg / length
        s = -offset
        while s < length:
            a = max(0.0, s)
            b = min(length, s + dash_on)
            if b > a:
                pa = (p0 + u * a).astype(int)
                pb = (p0 + u * b).astype(int)
                cv2.line(overlay, tuple(pa), tuple(pb), (242, 242, 242), 2, cv2.LINE_AA)
            s += period

    # Corner dots with pulse + expanding halo.
    for i, p in enumerate(quad):
        c = (int(p[0]), int(p[1]))
        r = 7 + math.sin(t * 3 + i * 1.5) * 1.5
        halo = (t * 0.8 + i * 0.25) % 1.0
        halo_val = int(255 * 0.5 * (1 - halo))
        cv2.circle(overlay, c, int(r + halo * 14), (halo_val,) * 3, 2, cv2.LINE_AA)
        cv2.circle(overlay, c, int(r), (255, 255, 255), -1, cv2.LINE_AA)
        cv2.circle(overlay, c, int(r), (60, 60, 60), 1, cv2.LINE_AA)

    cv2.addWeighted(overlay, presence, frame, 1 - presence, 0, dst=frame)


def draw_debug_tracking(frame, raw_quad, legacy_quad, stabilized_state):
    """Development-only raw/legacy/stabilized diagnostic overlay."""
    def polyline(quad, color, label):
        if quad is None:
            return
        points = np.array(quad, dtype=np.int32)
        cv2.polylines(frame, [points], True, color, 2, cv2.LINE_AA)
        anchor = tuple(points[0])
        cv2.putText(frame, label, anchor, cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)

    details = (
        "red=raw  blue=legacy  green=stable",
        f"state={stabilized_state.detection_state}  confidence={stabilized_state.confidence:.2f}",
        f"predicted={'yes' if stabilized_state.is_predicted else 'no'}  dropout={stabilized_state.dropout_frames}",
    )
    cv2.rectangle(frame, (0, 0), (frame.shape[1], 43), (0, 0, 0), -1)
    for line, detail in enumerate(details):
        cv2.putText(
            frame,
            detail,
            (5, 11 + line * 14),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.32,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
    polyline(raw_quad, (40, 40, 255), "raw")
    polyline(legacy_quad, (255, 180, 30), "legacy")
    polyline(stabilized_state.stabilized_quad, (40, 230, 40), "stabilized")


def draw_compositing_debug(original, final, quad, tracked_state, result, transition=None):
    """Build a 2x2 developer view of geometry, warp, and both alpha masks."""
    h, w = original.shape[:2]
    overview = final.copy()
    if quad is not None:
        cv2.polylines(overview, [np.asarray(quad, np.int32)], True, (40, 230, 40), 2, cv2.LINE_AA)
    cv2.rectangle(overview, (0, 0), (w, 30), (0, 0, 0), -1)
    transition_detail = ""
    if transition is not None:
        transition_detail = (
            f"  portal={transition.portal_id or '-'} {transition.state} "
            f"coverage={transition.coverage:.3f} progress={transition.progress:.3f}"
        )
    cv2.putText(
        overview,
        f"confidence={tracked_state.confidence:.2f} tracker={tracked_state.detection_state} composite={result.compositing_state}{transition_detail}",
        (5, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (255, 255, 255), 1, cv2.LINE_AA,
    )
    warped = result.warped_portal.copy()
    alpha = cv2.cvtColor(np.clip(result.portal_alpha * 255, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
    occlusion = cv2.cvtColor(np.clip(result.occlusion_alpha * 255, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
    for panel, label in ((warped, "warped portal + canonical labels"), (alpha, "portal alpha"), (occlusion, "finger occlusion alpha")):
        cv2.rectangle(panel, (0, 0), (w, 18), (0, 0, 0), -1)
        cv2.putText(panel, label, (4, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.34, (255, 255, 255), 1, cv2.LINE_AA)
    labels = (("TL", (4, 32)), ("TR", (w - 25, 32)), ("BR", (w - 25, h - 6)), ("BL", (4, h - 6)))
    for label, point in labels:
        cv2.putText(warped, label, point, cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 255, 255), 1, cv2.LINE_AA)
    return np.vstack((np.hstack((overview, warped)), np.hstack((alpha, occlusion))))


def ensure_model():
    if not os.path.exists(MODEL_PATH):
        print("Downloading hand landmarker model …")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)


def probe_media(path):
    """Read stable output metadata with ffprobe for tests and metrics."""
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-count_frames",
            "-show_entries",
            "format=duration,size,bit_rate:"
            "stream=index,codec_name,codec_type,width,height,avg_frame_rate,"
            "r_frame_rate,nb_frames,nb_read_frames,sample_rate,channels",
            "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("original", nargs="?", default="finger-effect-raw.mp4")
    ap.add_argument("stylized", nargs="?", default="stylized.mp4")
    ap.add_argument("-o", "--output", default="final.mp4")
    ap.add_argument(
        "--metrics",
        help="write tracker/compositing baseline metrics to this JSON file",
    )
    ap.add_argument(
        "--tracking-mode",
        choices=("legacy", "stabilized"),
        default="stabilized",
        help="quad tracker implementation (default: stabilized)",
    )
    ap.add_argument(
        "--debug-tracking",
        nargs="?",
        const="tracking-debug.mp4",
        metavar="OUTPUT_MP4",
        help="write a development-only raw/legacy/stabilized comparison video",
    )
    ap.add_argument(
        "--compositing-mode",
        choices=("legacy", "perspective", "perspective_occlusion"),
        default="perspective_occlusion",
        help="portal compositor (default: perspective_occlusion)",
    )
    ap.add_argument(
        "--debug-compositing",
        nargs="?",
        const="compositing-debug.mp4",
        metavar="OUTPUT_MP4",
        help="write a development-only perspective/alpha/occlusion diagnostic video",
    )
    ap.add_argument(
        "--portal-mode",
        choices=("portal_only", "portal_crossing"),
        default="portal_crossing",
        help="portal-only compatibility or geometry-driven full-screen transition",
    )
    ap.add_argument(
        "--parallax",
        action="store_true",
        help="enable the lightweight motion-derived 2.5D portal illusion",
    )
    ap.add_argument(
        "--transition-progress",
        type=float,
        metavar="0..1",
        help="developer-only forced crossing progress for deterministic inspection",
    )
    args = ap.parse_args()

    for f in (args.original, args.stylized):
        if not os.path.exists(f):
            sys.exit(f"Missing input: {f}")
    started_at = time.perf_counter()
    ensure_model()

    import mediapipe as mp
    from mediapipe.tasks import python as mp_tasks
    from mediapipe.tasks.python import vision

    cap = cv2.VideoCapture(args.original)
    sty = cv2.VideoCapture(args.stylized)
    if not cap.isOpened():
        sys.exit(f"Could not decode original video: {args.original}")
    if not sty.isOpened():
        sys.exit(f"Could not decode stylized video: {args.stylized}")
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    sty_fps = sty.get(cv2.CAP_PROP_FPS) or fps
    sty_count = int(sty.get(cv2.CAP_PROP_FRAME_COUNT))
    if w <= 0 or h <= 0:
        sys.exit(f"Invalid original video dimensions: {w}x{h}")
    if sty_count <= 0:
        sys.exit(f"Stylized video contains no decodable frames: {args.stylized}")

    landmarker = vision.HandLandmarker.create_from_options(
        vision.HandLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=MODEL_PATH),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=0.3,
            min_hand_presence_confidence=0.3,
            min_tracking_confidence=0.3,
        )
    )

    # Pipe frames straight into ffmpeg for a proper H.264 output.
    ff = subprocess.Popen(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}",
            "-r", f"{fps}", "-i", "-",
            "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
            args.output,
        ],
        stdin=subprocess.PIPE,
    )

    tracker = (
        FrameTracker(w, h)
        if args.tracking_mode == "legacy"
        else StabilizedFrameTracker(w, h)
    )
    debug_legacy = FrameTracker(w, h) if args.debug_tracking and args.tracking_mode != "legacy" else None
    debug_stabilized = (
        StabilizedFrameTracker(w, h)
        if args.debug_tracking and args.tracking_mode != "stabilized"
        else None
    )
    debug_ff = None
    if args.debug_tracking:
        debug_ff = subprocess.Popen(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}",
                "-r", f"{fps}", "-i", "-",
                "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                args.debug_tracking,
            ],
            stdin=subprocess.PIPE,
        )
    compositor = None
    if args.compositing_mode != "legacy" or args.debug_compositing:
        compositor = PerspectiveCompositor(
            w,
            h,
            use_occlusion=args.compositing_mode != "perspective",
            use_parallax=args.parallax,
        )
    portal_controller = (
        PortalCrossingController(w, h)
        if args.portal_mode == "portal_crossing" and args.compositing_mode != "legacy"
        else None
    )
    transition = None
    composite_debug_ff = None
    if args.debug_compositing:
        composite_debug_ff = subprocess.Popen(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w * 2}x{h * 2}",
                "-r", f"{fps}", "-i", "-",
                "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                args.debug_compositing,
            ],
            stdin=subprocess.PIPE,
        )
    sty_frames = []
    i = 0
    tracked = 0
    valid_polygon_frames = 0
    mask_area_ratio_series = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break

        # Cache stylized frames lazily (they're reused when fps differ).
        t = i / fps
        j = min(int(round(t * sty_fps)), max(sty_count - 1, 0))
        while len(sty_frames) <= j:
            ok_s, sf = sty.read()
            if not ok_s:
                break
            if sf.shape[:2] != (h, w):
                sf = cv2.resize(sf, (w, h))
            sty_frames.append(sf)
        sty_frame = sty_frames[min(j, len(sty_frames) - 1)] if sty_frames else None

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = landmarker.detect_for_video(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb),
            int(i * 1000 / fps),
        )
        hands = result.hand_landmarks or []
        if args.tracking_mode == "stabilized":
            tracked_state = tracker.update_state(hands)
            quad = tracked_state.stabilized_quad
        else:
            quad = tracker.update(hands)
            tracked_state = TrackedFrame(
                None,
                tuple(quad) if quad is not None else None,
                tracker.presence,
                "legacy" if quad is not None else "lost",
                False,
                tracker.lost_frames,
            )

        source_frame = frame.copy()
        composite_result = None
        if portal_controller is not None:
            transition = portal_controller.update(
                quad,
                tracked_state.confidence,
                tracked_state.detection_state,
                frame_index=i,
                force_progress=args.transition_progress,
            )
        render_quad = transition.expanded_quad if transition is not None else quad
        if render_quad is not None and sty_frame is not None:
            if args.compositing_mode == "legacy":
                # Frozen Milestone 0 branch: preserve these operations exactly.
                tracked += 1
                valid_polygon_frames += 1
                mask = np.zeros((h, w), dtype=np.uint8)
                cv2.fillPoly(mask, [np.array(render_quad, dtype=np.int32)], 255)
                mask_area_ratio_series.append(
                    {"frame": i, "ratio": round(float(np.count_nonzero(mask)) / mask.size, 6)}
                )
                m = (mask.astype(np.float32) / 255.0 * tracker.presence)[..., None]
                frame = (frame.astype(np.float32) * (1 - m) + sty_frame.astype(np.float32) * m).astype(np.uint8)
                draw_outline(frame, render_quad, tracker.presence, t)
            else:
                composite_result = compositor.composite(
                    frame,
                    sty_frame,
                    render_quad,
                    tracked_state.confidence,
                    tracked_state.detection_state,
                    hands,
                    transition_progress=transition.progress if transition is not None else 0.0,
                    parallax_quad=quad,
                )
                frame = composite_result.frame
                if composite_result.applied:
                    tracked += 1
                    valid_polygon_frames += 1
                    mask_area_ratio_series.append(
                        {"frame": i, "ratio": round(float(np.mean(composite_result.portal_alpha)), 6)}
                    )

        if args.debug_compositing:
            if composite_result is None:
                composite_result = compositor.composite(
                    source_frame,
                    sty_frame if sty_frame is not None else source_frame,
                    render_quad,
                    tracked_state.confidence,
                    tracked_state.detection_state,
                    hands,
                    transition_progress=transition.progress if transition is not None else 0.0,
                    parallax_quad=quad,
                )
            composite_debug_ff.stdin.write(
                draw_compositing_debug(source_frame, frame, render_quad, tracked_state, composite_result, transition).tobytes()
            )

        if debug_ff is not None:
            if args.tracking_mode == "legacy":
                tracked_state = debug_stabilized.update_state(hands)
                legacy_quad = quad
            else:
                legacy_quad = debug_legacy.update(hands)
            debug_frame = frame.copy()
            draw_debug_tracking(
                debug_frame,
                tracked_state.raw_quad,
                legacy_quad,
                tracked_state,
            )
            debug_ff.stdin.write(debug_frame.tobytes())

        ff.stdin.write(frame.tobytes())
        i += 1
        if i % 30 == 0:
            print(f"  frame {i}, frame visible on {tracked} frames so far")

    ff.stdin.close()
    if ff.wait() != 0:
        sys.exit("FFmpeg video encoding failed")
    if debug_ff is not None:
        debug_ff.stdin.close()
        if debug_ff.wait() != 0:
            sys.exit("FFmpeg debug video encoding failed")
    if composite_debug_ff is not None:
        composite_debug_ff.stdin.close()
        if composite_debug_ff.wait() != 0:
            sys.exit("FFmpeg compositing debug video encoding failed")
    cap.release()
    sty.release()

    # Carry over the original audio track if there is one.
    has_audio = (
        subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
             "stream=codec_type", "-of", "csv=p=0", args.original],
            capture_output=True, text=True,
        ).stdout.strip() != ""
    )
    if has_audio:
        tmp = args.output + ".mux.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", args.output,
             "-i", args.original, "-map", "0:v", "-map", "1:a",
             "-c:v", "copy", "-c:a", "aac", "-shortest", tmp],
            check=True,
        )
        os.replace(tmp, args.output)

    if args.metrics:
        ratios = [sample["ratio"] for sample in mask_area_ratio_series]
        metrics = {
            "tracking_mode": args.tracking_mode,
            "compositing_mode": args.compositing_mode,
            "portal_mode": args.portal_mode,
            "parallax_enabled": args.parallax,
            "tracker": tracker.metrics(),
            "compositing": {
                "processed_frames": i,
                "valid_polygon_frames": valid_polygon_frames,
                "invalid_polygon_frames": i - valid_polygon_frames,
                "mask_area_ratio": {
                    "minimum": min(ratios) if ratios else 0.0,
                    "maximum": max(ratios) if ratios else 0.0,
                    "average": round(sum(ratios) / len(ratios), 6) if ratios else 0.0,
                    "by_frame": mask_area_ratio_series,
                },
                "output_width": w,
                "output_height": h,
                "fps": fps,
                "processing_seconds": round(time.perf_counter() - started_at, 6),
                "perspective": compositor.metrics() if compositor is not None else None,
                "portal_crossing": {
                    "final_state": transition.state if transition is not None else TransitionState.INACTIVE.value,
                    "events": portal_controller.event_metadata() if portal_controller is not None else [],
                },
            },
            "output": probe_media(args.output),
        }
        metrics_path = Path(args.metrics)
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        metrics_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
        print(f"Metrics: {metrics_path}")

    print(f"Done: {args.output} ({i} frames, finger frame visible on {tracked})")


if __name__ == "__main__":
    main()
