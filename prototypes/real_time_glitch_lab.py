"""Real-Time Glitch Art Lab — live webcam glitch installation.

Rewrite of the legacy prototype for smooth live performance on the Studio:
vectorised transforms (src/lunar_tools_art/glitch.py), a dedicated capture
thread, bounded frame buffering with stale-frame dropping, and main-thread
only rendering via the shared Renderer. Keyboard and MIDI controls replace
the legacy behaviour of a synchronous cloud LLM call inside the frame loop
(the LLM "glitch suggestion" path is gone; art direction is now the
visitor's hands, with optional AI suggestions arriving asynchronously if an
LLM backend is configured).

Controls:
  1-4        select glitch family (pixel_sort, channel_shift, scanline, mosh)
  up / down  intensity -/+ (0..1)
  space      re-roll random glitch + intensity
  q          quit

Run:  env/bin/python -m prototypes.real_time_glitch_art_lab
Requires a webcam; without one the installation renders an explicit
standby diagnostic state instead of silently showing wallpaper.
"""

from __future__ import annotations

import logging
import random
import time

import numpy as np

from src.lunar_tools_art.frame_pipeline import (
    CameraCaptureThread,
    CameraState,
    GlitchPipeline,
    VideoFileCapture,
    make_standby_frame,
)
from src.lunar_tools_art.glitch import GLITCH_TYPES, apply_glitch

logger = logging.getLogger(__name__)

KEY_TO_GLITCH = {
    "1": "pixel_sort",
    "2": "color_channel_shift",
    "3": "scanline_interruption",
    "4": "data_moshing_simulated",
}


class RealTimeGlitchArtLab:
    """Interactive glitch pipeline. All camera reads and transforms happen
    off the render path; the run loop is main-thread render + controls only."""

    def __init__(self, manager, loop_fps=30, video_path=None, duration=None,
                 video_loop=False):
        self.manager = manager
        self.renderer = manager.renderer
        self.keyboard = manager.keyboard_input
        self.midi = manager.midi_input
        self.logger = manager.logger or logger
        self.glitch_type = "pixel_sort"
        self.intensity = 0.5
        self._frames_since_standby = 0
        self._seen_count = 0
        self.video_path = video_path
        self.duration = duration
        self.video_loop = video_loop

        if video_path:
            # Recorded replay: proves transforms/render/recovery logic, but is
            # NOT hardware verification. The demo log says so explicitly.
            self.capture = VideoFileCapture(video_path, target_fps=loop_fps,
                                            loop=video_loop)
        else:
            self.capture = CameraCaptureThread(manager.webcam)
        self.pipeline = GlitchPipeline(self.capture, self.renderer, self.keyboard)

        self._dt_target = 1.0 / loop_fps
        self._last_midi_cc = {}
        self._midi_ready = False  # lazily probed once
        self._midi_probe_fail = 0

    # -- controls -----------------------------------------------------------

    def _handle_keys(self) -> bool:
        """Returns False when the visitor asked to quit."""
        if self.keyboard.is_key_pressed("q"):
            return False
        for key, glitch in KEY_TO_GLITCH.items():
            if self.keyboard.is_key_pressed(key):
                self.glitch_type = glitch
                self.logger.info(f"Glitch family: {glitch} (key {key})")
        if self.keyboard.is_key_pressed("up"):
            self.intensity = min(1.0, self.intensity + 0.1)
            self.logger.info(f"Intensity: {self.intensity:.2f}")
        if self.keyboard.is_key_pressed("down"):
            self.intensity = max(0.0, self.intensity - 0.1)
            self.logger.info(f"Intensity: {self.intensity:.2f}")
        if self.keyboard.is_key_pressed(" "):
            self.glitch_type = random.choice(GLITCH_TYPES)
            self.intensity = round(random.uniform(0.1, 1.0), 2)
            self.logger.info(
                f"Re-roll: {self.glitch_type} @ {self.intensity:.2f}"
            )
        return True

    def _midi_adjust(self):
        """Optional MIDI: CC20-23 pick family, CC24 sets intensity (0..1).

        mido polling is cheap and degrades to no-ops when no device is
        present (tools.input.MidiInput already handles the warn-once path).
        """
        cc = self.midi
        for idx, glitch in enumerate(GLITCH_TYPES):
            v = cc.get(20 + idx)
            if v > 0.5 and v != self._last_midi_cc.get(20 + idx):
                self.glitch_type = glitch
                self.logger.info(f"Glitch family: {glitch} (MIDI CC{20 + idx})")
            self._last_midi_cc[20 + idx] = v
        v = cc.get(24)
        if v > 0:
            self.intensity = round(min(1.0, max(0.0, v)), 2)

    # -- standby --------------------------------------------------------------

    def _transform(self, frame):
        return apply_glitch(frame, self.glitch_type, self.intensity)

    def run(self):
        self.logger.info(
            "Real-Time Glitch Art Lab | keys: 1-4 family, up/down intensity, "
            "space re-roll, q quit"
        )
        if self.video_path:
            self.logger.info(
                f"Source: recorded video {self.video_path} — DEMONSTRATION ONLY, "
                "not live camera hardware verification."
            )
        self.capture.start()
        state = None
        started = time.time()
        try:
            while True:
                if self.duration is not None and time.time() - started >= self.duration:
                    self.logger.info("Duration reached; exiting.")
                    break
                if self.manager.main_queue is not None:
                    self.manager.main_queue.drain()
                if not self._handle_keys():
                    break
                try:
                    self._midi_adjust()
                except Exception as e:
                    self._midi_probe_fail += 1
                    if self._midi_probe_fail == 1:
                        self.logger.warning(f"MIDI disabled: {e}")

                cs = self.capture.state
                if cs != state:
                    self.logger.info(f"Camera state: {cs}")
                    state = cs

                if cs == CameraState.CONNECTED:
                    # Block until the capture thread publishes a new frame
                    # instead of spinning on a timer (macOS inflates short
                    # sleeps, and a hot loop inflates the drop counter).
                    self.capture.wait_for_new(self._seen_count, timeout=0.05)
                    st = self.pipeline.process_and_render(self._transform)
                    self._seen_count = self.capture.frames_delivered
                    fps = st.get("fps")
                elif cs == CameraState.ENDED:
                    self.logger.info("Recorded source exhausted; exiting.")
                    break
                else:
                    self.renderer.render(
                        make_standby_frame(
                            self.renderer.height,
                            self.renderer.width,
                            f"GLITCH LAB — camera: {cs} — waiting...",
                        )
                    )
                    fps = None
                    self._last_rendered_reset()

                if fps and self._frames_since_standby % 120 == 0 and fps:
                    self.logger.info(f"Delivered FPS: {fps:.1f}")
                self._frames_since_standby += 1
        except KeyboardInterrupt:
            self.logger.info("Interrupted; exiting.")
        finally:
            self.capture.stop()
            self.capture.join()
            self.logger.info("Glitch Lab stopped.")

    def _last_rendered_reset(self):
        # When leaving standby, ensure the next camera frame is not treated
        # as a duplicate of a frame processed before the outage.
        self.pipeline._last_rendered_key = None


class _NullKeys:
    def is_key_pressed(self, _key):
        return False


class _NullMidi:
    def get(self, _cc):
        return 0


class _HeadlessManager:
    """Minimal manager for pipeline verification without a window or camera."""

    def __init__(self, width=1280, height=720):
        from src.lunar_tools_art.tools.display import Renderer

        self.renderer = Renderer(width=width, height=height, backend="null")
        self.keyboard_input = _NullKeys()
        self.midi_input = _NullMidi()
        self.webcam = None
        self.main_queue = None
        self.logger = logger


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", help="replay a recorded video (demo only)")
    parser.add_argument("--seconds", type=float, default=None,
                        help="stop after N seconds (default: run until quit)")
    parser.add_argument("--fps", type=float, default=30, help="capture/render pacing")
    parser.add_argument("--loop", action="store_true", help="loop the recorded video")
    parser.add_argument("--headless", action="store_true",
                        help="null renderer; measure the pipeline without a window")
    args = parser.parse_args()

    if args.headless:
        manager = _HeadlessManager()
    else:
        from src.lunar_tools_art import Manager

        manager = Manager()
    lab = RealTimeGlitchArtLab(
        manager, loop_fps=args.fps, video_path=args.video,
        duration=args.seconds, video_loop=args.loop,
    )
    lab.run()
    logger.info(
        f"Summary: rendered={lab.pipeline.frames_rendered} "
        f"dropped={lab.pipeline.frames_dropped} "
        f"delivered_fps={lab.pipeline.delivered_fps()}"
    )


if __name__ == "__main__":
    main()