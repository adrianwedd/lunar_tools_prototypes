#!/usr/bin/env python3
"""Verify the Glitch Lab pipeline without pretending to verify the camera.

What this proves:
  * frames are delivered from a recorded source through the capture thread,
  * all four glitch families transform real frames,
  * keyboard handling changes family/intensity,
  * the renderer accepts decoded RGB frames (not paths),
  * delivered FPS on this machine.

What it does NOT prove: that the physical camera works. macOS camera
authorisation is a separate TCC boundary, probed and reported here.

Usage:
  env -u PYTHONPATH env/bin/python scripts/verify_glitch_lab.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CLIP = ROOT / "outputs/glitch_lab/synthetic_reference_720p.mp4"
OUT = ROOT / "outputs/glitch_lab"


class SequenceKeys:
    """Deterministic keyboard stub: consume one scripted key per poll."""

    def __init__(self, sequence):
        self.sequence = list(sequence)

    def is_key_pressed(self, key):
        if self.sequence and self.sequence[0] == key:
            self.sequence.pop(0)
            return True
        return False


class NullMidi:
    def get(self, _cc):
        return 0


def probe_camera():
    """Attempt one real camera open; record the concrete outcome."""
    import cv2

    started = time.time()
    cap = cv2.VideoCapture(0)
    opened = cap.isOpened()
    frame = None
    if opened:
        ok, frame = cap.read()
        opened = bool(ok and frame is not None)
    cap.release()
    return {
        "attempted": True,
        "opened_and_delivered_frame": opened,
        "elapsed_s": round(time.time() - started, 3),
        "note": (
            "macOS TCC denied capture in this session (OpenCV logged "
            "'not authorized to capture video (status 0)'); approval requires "
            "the logged-in user to accept the system prompt for the calling "
            "binary. No frames were obtained."
            if not opened
            else "Camera opened and delivered a frame."
        ),
    }


def main():
    import cv2

    from src.lunar_tools_art.glitch import apply_glitch, GLITCH_TYPES
    from src.lunar_tools_art.tools.display import Renderer

    OUT.mkdir(parents=True, exist_ok=True)
    assert CLIP.exists(), f"recorded clip missing: {CLIP}"

    # -- real frames from the recorded source, one per glitch family ---------
    cap = cv2.VideoCapture(str(CLIP))
    ok, bgr = cap.read()
    assert ok, "could not read the recorded clip"
    frame = bgr[..., ::-1].copy()
    cap.release()

    family_stats = {}
    for name in GLITCH_TYPES:
        out = apply_glitch(frame, name, 0.8)
        Path(OUT / f"{name}_frame.png").write_bytes(
            cv2.imencode(".png", out[..., ::-1])[1].tobytes()
        )
        family_stats[name] = {
            "shape": list(out.shape),
            "changed_pixels_vs_source": float(
                np.mean(np.any(out != frame, axis=2))
            ),
            "output_sha256": __import__("hashlib").sha256(out.tobytes()).hexdigest(),
        }

    # -- pipeline run: capture thread -> transform -> null renderer ----------
    from prototypes.real_time_glitch_lab import RealTimeGlitchArtLab

    class HeadlessManager:
        def __init__(self):
            self.renderer = Renderer(width=1280, height=720, backend="null")
            self.keyboard_input = SequenceKeys([])
            self.midi_input = NullMidi()
            self.webcam = None
            self.main_queue = None
            import logging

            self.logger = logging.getLogger("verify_glitch")

    logging_ready = __import__("logging").basicConfig(
        level=__import__("logging").INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    lab = RealTimeGlitchArtLab(
        HeadlessManager(), loop_fps=30, video_path=str(CLIP), duration=4.0
    )
    lab.run()
    run_stats = {
        "frames_rendered": lab.pipeline.frames_rendered,
        "frames_dropped": lab.pipeline.frames_dropped,
        "delivered_fps": lab.pipeline.delivered_fps(),
        "camera_state_final": lab.capture.state,
    }

    # -- keyboard logic (not hardware) ---------------------------------------
    class KeyManager(HeadlessManager):
        def __init__(self):
            super().__init__()
            self.keyboard_input = SequenceKeys(["2", "up", "up"])

    km = KeyManager()
    lab2 = RealTimeGlitchArtLab(km, loop_fps=30, video_path=str(CLIP))
    before = (lab2.glitch_type, lab2.intensity)
    lab2._handle_keys()
    after = (lab2.glitch_type, lab2.intensity)
    keyboard_stats = {
        "before": list(before),
        "after": list(after),
        "family_changed": before[0] != after[0],
        "intensity_increased": after[1] > before[1],
    }

    # -- camera boundary ------------------------------------------------------
    camera = probe_camera()

    summary = {
        "generated_at": time.time(),
        "recorded_clip": str(CLIP.relative_to(ROOT)),
        "recorded_clip_resolution": list(frame.shape),
        "glitch_families": family_stats,
        "pipeline": run_stats,
        "keyboard_logic": keyboard_stats,
        "camera_hardware": camera,
        "hardware_verified": camera["opened_and_delivered_frame"],
        "evidence_kind": "recorded-video pipeline verification, not camera hardware",
    }
    (OUT / "verification.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
