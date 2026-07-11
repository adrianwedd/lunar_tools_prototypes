"""Real OpenCV-backed webcam.

``cv2`` is imported lazily inside methods so importing this module never
touches the camera stack, and so tests can monkeypatch
``sys.modules["cv2"]`` before it is imported here.
"""

import logging

logger = logging.getLogger(__name__)


class WebCam:
    """Wraps ``cv2.VideoCapture``, returning RGB frames."""

    def __init__(self, cam_id: int = 0):
        self.cam_id = cam_id
        self._degraded = False
        self._cap = None

    def _ensure_capture(self):
        if self._cap is not None:
            return self._cap

        import cv2

        cap = cv2.VideoCapture(self.cam_id)
        if not cap.isOpened():
            self._degraded = True
            logger.warning(f"Camera {self.cam_id} unavailable; WebCam degraded.")
            return None

        self._cap = cap
        return self._cap

    def get_img(self):
        """Return an RGB numpy frame, or ``None`` if no camera is available."""
        if self._degraded:
            return None

        cap = self._ensure_capture()
        if cap is None:
            return None

        ok, frame_bgr = cap.read()
        if not ok or frame_bgr is None:
            self._degraded = True
            logger.warning(
                f"Camera {self.cam_id} read failed mid-stream; WebCam degraded."
            )
            self.release()  # free the OS camera handle; we'll never read again
            return None

        return frame_bgr[..., ::-1]

    def release(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None
