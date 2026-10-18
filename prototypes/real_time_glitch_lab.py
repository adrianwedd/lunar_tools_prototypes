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

    def __init__(self, manager, loop_fps=30):
        self.manager = manager
        self.renderer = manager.renderer
        self.keyboard = manager.keyboard_input
        self.midi = manager.midi_input
        self.logger = manager.logger or logger
        self.glitch_type = "pixel_sort"
        self.intensity = 0.5
        self._frames_since_standby = 0

        cam = manager.webcam
        self.capture = CameraCaptureThread(cam)
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
                self.logger.info(f"Glitch family: {glitch}")
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
        self.capture.start()
        state = None
        try:
            while True:
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
                    st = self.pipeline.process_and_render(self._transform)
                    fps = st.get("fps")
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

                time.sleep(self._dt_target * 0.25)  # paced by render cost mostly
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


def main():
    from src.lunar_tools_art import Manager

    manager = Manager()
    lab = RealTimeGlitchArtLab(manager)
    lab.run()


if __name__ == "__main__":
    main()