"""Live frame pipeline for the Real-Time Glitch Art Lab.

Architecture (replaces the legacy single-thread loop that did synchronous
GPT-4 calls and per-pixel PIL work between frames):

- A daemon **capture thread** owns the camera and continuously drops fresh
  frames into a slot of size 1 (bounded buffering: the processor always works
  on the newest complete frame, stale frames are never queued).
- A **processor** (any thread) takes the latest frame and applies vectorised
  glitch transforms (see ``glitch.py``).
- The **main thread** renders via ``Renderer.render()`` (pyglet requires the
  main thread) and pumps the ``MainLoopQueue`` so background producers can
  post frames/closures safely.

Camera behaviour is explicit: connection and disconnection are tracked
state, not silent wallpaper. When the camera is absent the pipeline reports
``NO_CAMERA`` and the caller decides what to display (e.g. a standby
diagnostic frame) rather than pretending video is flowing.
"""

from __future__ import annotations

import logging
import threading
import time

import numpy as np

logger = logging.getLogger(__name__)


class CameraState:
    CONNECTED = "connected"
    CONNECTING = "connecting"
    NO_CAMERA = "no_camera"
    LOST = "lost"


class CameraCaptureThread:
    """Continuously reads the newest camera frame into a single slot.

    Hardens the raw ``tools.camera.WebCam`` (which permanently degrades on
    any single failed read) with bounded retry: a dead capture is reopened
    with a cooldown, and state transitions are explicit instead of silent.
    """

    RETRY_COOLDOWN_S = 2.0

    def __init__(self, webcam, poll_interval: float = 0.0):
        self._webcam = webcam
        self._poll_interval = poll_interval
        self._lock = threading.Lock()
        self._latest: np.ndarray | None = None
        self._frame_ts = 0.0
        self._state = CameraState.CONNECTING
        self._last_fail = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- public API -------------------------------------------------------

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def latest_frame(self):
        """Return ``(frame_or_None, age_seconds, state)`` atomically."""
        with self._lock:
            return (
                self._latest,
                time.time() - self._frame_ts if self._latest is not None else None,
                self._state,
            )

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(
                target=self._run, name="glitch-capture", daemon=True
            )
            self._thread.start()

    def stop(self):
        self._stop.set()

    def join(self, timeout: float = 2.0):
        if self._thread is not None:
            self._thread.join(timeout)

    # -- internals --------------------------------------------------------

    def _run(self):
        while not self._stop.is_set():
            try:
                frame = self._webcam.get_img()
            except Exception as e:  # hardware layer may raise; keep the loop alive
                logger.warning(f"Camera get_img raised: {e}")
                frame = None

            with self._lock:
                if frame is not None:
                    self._latest = frame
                    self._frame_ts = time.time()
                    if self._state != CameraState.CONNECTED:
                        logger.info("Camera connected.")
                    self._state = CameraState.CONNECTED
                else:
                    if self._state == CameraState.CONNECTED:
                        self._state = CameraState.LOST
                        logger.warning("Camera lost; attempting periodic reconnect.")
                    elif self._state in (CameraState.CONNECTING, CameraState.LOST):
                        self._state = CameraState.NO_CAMERA

            if frame is None:
                # Back off briefly before hammering a dead device. The raw
                # WebCam releases its handle on failure, so get_img() will
                # attempt a fresh VideoCapture open each poll.
                time.sleep(self.RETRY_COOLDOWN_S)
            elif self._poll_interval:
                time.sleep(self._poll_interval)


class GlitchPipeline:
    """Glue for one installation loop: capture -> (caller transforms) -> render.

    The caller's main loop should, per iteration:
      1. ``queue.drain()`` to run callbacks posted by background threads,
      2. ``pipeline.process_and_render(transform)`` which takes the newest
         camera frame, applies ``transform(frame)``, and renders on the
         main thread. Stale-frame dropping is inherent: only the single
         newest frame is ever processed, and only when new.
    """

    def __init__(self, capture: CameraCaptureThread, renderer, keyboard_input):
        self.capture = capture
        self.renderer = renderer
        self.keyboard_input = keyboard_input
        self.frames_rendered = 0
        self.frames_dropped = 0
        self._last_rendered_key = None
        self._fps_window: list[float] = []

    def process_and_render(self, transform) -> dict:
        """Process+render one iteration. Returns status info for instrumentation.

        transform: callable(np.ndarray) -> np.ndarray, or None to pass through.
        """
        frame, age, state = self.capture.latest_frame()
        status = {
            "camera_state": state,
            "rendered": False,
            "frame_age": age,
        }
        if frame is None:
            if state != CameraState.CONNECTED:
                status["rendered"] = self._render_standby(state)
            else:
                self.frames_dropped += 1
            return status

        # Stale-frame drop: skip frames already processed (same object).
        if frame is self._last_rendered_key:
            self.frames_dropped += 1
            status["dropped_dup"] = True
            return status
        self._last_rendered_key = frame

        try:
            out = transform(frame) if transform is not None else frame
            self.renderer.render(out)
            self.frames_rendered += 1
            now = time.time()
            self._fps_window.append(now)
            if len(self._fps_window) > 120:
                del self._fps_window[:60]
            status["rendered"] = True
            status["fps"] = self.delivered_fps()
        except Exception as e:
            logger.error(f"Glitch render failed: {e}", exc_info=True)
        return status

    def _render_standby(self, state: str) -> bool:
        """Render a diagnostic standby frame when no camera video is flowing."""
        try:
            h, w = self.renderer.height, self.renderer.width
            img = np.zeros((h, w, 3), dtype=np.uint8)
            img[:, :, 2] = 30  # dim blue field
            self.renderer.render(img)
            return True
        except Exception as e:
            logger.error(f"Standby render failed: {e}")
            return False

    def delivered_fps(self):
        ts = self._fps_window
        if len(ts) < 2:
            return None
        span = ts[-1] - ts[0]
        return (len(ts) - 1) / span if span > 0 else None


def make_standby_frame(height: int, width: int, text: str) -> np.ndarray:
    """A diagnostic frame with `text` drawn centred (for no-camera states)."""
    import cv2

    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:, :, 2] = 30
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale, th = 0.8, 2
    (tw, thh), _ = cv2.getTextSize(text, font, scale, th)
    cv2.putText(
        img,
        text,
        ((width - tw) // 2, (height + thh) // 2),
        font,
        scale,
        (200, 200, 255),
        th,
        cv2.LINE_AA,
    )
    return img