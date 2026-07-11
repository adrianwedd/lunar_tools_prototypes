import sys
import types

import numpy as np


class _StubCapture:
    def __init__(self, opened=True):
        self._opened = opened

    def isOpened(self):
        return self._opened

    def read(self):
        bgr = np.zeros((4, 4, 3), dtype=np.uint8)
        bgr[..., 0] = 255  # blue channel full in BGR
        return True, bgr

    def release(self):
        pass


class _MidStreamFailCapture:
    """Opens fine, first read succeeds, every read after that fails."""

    def __init__(self):
        self._reads = 0

    def isOpened(self):
        return True

    def read(self):
        self._reads += 1
        if self._reads == 1:
            return True, np.zeros((4, 4, 3), dtype=np.uint8)
        return False, None

    def release(self):
        pass


def _fake_cv2(monkeypatch, capture):
    cv2 = types.SimpleNamespace(VideoCapture=lambda cam_id: capture)
    monkeypatch.setitem(sys.modules, "cv2", cv2)
    return cv2


def test_get_img_converts_bgr_to_rgb(monkeypatch):
    _fake_cv2(monkeypatch, _StubCapture(opened=True))
    from lunar_tools_art.tools.camera import WebCam

    cam = WebCam(cam_id=0)
    frame = cam.get_img()
    assert frame is not None
    assert (frame[..., 2] == 255).all()


def test_get_img_warns_once_and_returns_none(monkeypatch, caplog):
    _fake_cv2(monkeypatch, _StubCapture(opened=False))
    from lunar_tools_art.tools.camera import WebCam

    cam = WebCam(cam_id=0)
    with caplog.at_level("WARNING"):
        assert cam.get_img() is None
        assert cam.get_img() is None
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1


def test_get_img_mid_stream_failure_degrades_with_one_warning(monkeypatch, caplog):
    _fake_cv2(monkeypatch, _MidStreamFailCapture())
    from lunar_tools_art.tools.camera import WebCam

    cam = WebCam(cam_id=0)
    with caplog.at_level("WARNING"):
        first = cam.get_img()
        assert first is not None

        assert cam.get_img() is None
        assert cam.get_img() is None

    assert cam._degraded is True
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
