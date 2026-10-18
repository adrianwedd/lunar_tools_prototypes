"""Integration-level tests for cache identity, renderer coercion and the
recorded-video capture path used when macOS denies camera access.

No network, no ML inference. cv2 is used only to write a tiny synthetic clip.
"""

import json
import time
from pathlib import Path

import numpy as np
import pytest

from src.lunar_tools_art.seed_scheduler import SeedScheduler


class FakeGenerator:
    def __init__(self, latency=0.0):
        self.latency = latency
        self.calls = []

    def __call__(self, prompt, size=(64, 64), seed=None):
        self.calls.append((prompt, size, seed))
        if self.latency:
            time.sleep(self.latency)
        path = Path(f"/tmp/lunar_identity_test_{seed}_{size[0]}.png")
        path.write_bytes(b"FAKEPNG:" + str(seed).encode())
        return str(path), {"backend": "fake", "seed": seed}


def _scheduler(tmp_path, identity):
    results = []
    s = SeedScheduler(
        FakeGenerator(),
        cache_index_path=tmp_path / "index.json",
        on_success=results.append,
        identity=identity,
    )
    s.start()
    return s, results


def test_identity_is_part_of_cache_key_and_index(tmp_path):
    identity = {"backend": "mflux", "model": "schnell",
                "model_revision": "rev-a", "num_inference_steps": 4}
    s, _ = _scheduler(tmp_path, identity)
    try:
        s.request("p", (64, 64), 7)
        entry = s.wait_for("p", (64, 64), 7, timeout=5)
        assert entry is not None
        assert s.cached_entry("p", (64, 64), 7)["identity"]["model_revision"] == "rev-a"
        on_disk = json.loads((tmp_path / "index.json").read_text())
        stored = on_disk["entries"][s.cache_key("p", (64, 64), 7)]
        assert stored["identity_key"] == s.identity_key()
        assert stored["identity"]["model"] == "schnell"
    finally:
        s.stop()


def test_changed_model_revision_cannot_serve_stale_cache(tmp_path):
    identity = {"backend": "mflux", "model": "schnell", "model_revision": "rev-a"}
    s, _ = _scheduler(tmp_path, identity)
    try:
        s.request("p", (64, 64), 7)
        assert s.wait_for("p", (64, 64), 7, timeout=5) is not None
    finally:
        s.stop()

    identity["model_revision"] = "rev-b"  # same scheduler object, new weights
    assert s.cached_entry("p", (64, 64), 7) is None
    assert s.cache_key("p", (64, 64), 7) != f"p|64x64|7"


def test_identity_can_be_a_callable(tmp_path):
    calls = {"n": 0}

    def identity():
        calls["n"] += 1
        return {"model_revision": f"rev-{calls['n']}"}

    s, _ = _scheduler(tmp_path, identity)
    try:
        assert s.identity_key() != s.identity_key()
        assert s.cache_key("p", (8, 8), 1).count("|") == 3
    finally:
        s.stop()


def test_renderer_decodes_path_to_rgb_array(tmp_path):
    from PIL import Image

    from src.lunar_tools_art.tools.display import Renderer

    p = tmp_path / "frame.png"
    Image.new("RGB", (12, 9), (200, 10, 30)).save(p)

    r = Renderer(width=12, height=9, backend="null")
    r.render(str(p))
    frame = r.frames[-1]
    assert isinstance(frame, np.ndarray)
    assert frame.shape == (9, 12, 3)
    assert frame.dtype == np.uint8
    assert frame[0, 0].tolist() == [200, 10, 30]


def test_renderer_rejects_undecodable_path(tmp_path):
    from src.lunar_tools_art.tools.display import Renderer

    r = Renderer(width=8, height=8, backend="null")
    with pytest.raises(ValueError):
        r.render(str(tmp_path / "missing.png"))


def test_video_file_capture_delivers_frames_then_ends(tmp_path):
    cv2 = pytest.importorskip("cv2")
    from src.lunar_tools_art.frame_pipeline import CameraState, VideoFileCapture

    path = tmp_path / "clip.mp4"
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"mp4v"), 15.0, (32, 24)
    )
    assert writer.isOpened()
    for i in range(10):
        frame = np.zeros((24, 32, 3), dtype=np.uint8)
        frame[:, :, i % 3] = 40 + i * 10
        writer.write(frame)
    writer.release()

    cap = VideoFileCapture(path, target_fps=60)
    cap.start()
    deadline = time.time() + 5
    while time.time() < deadline and cap.state != CameraState.ENDED:
        time.sleep(0.02)
    cap.stop()
    cap.join()

    assert cap.state == CameraState.ENDED
    frame, age, state = cap.latest_frame()
    assert state == CameraState.ENDED
    assert frame is not None and frame.shape == (24, 32, 3)
    assert frame.dtype == np.uint8


def test_camera_pipeline_recovers_after_transient_loss(monkeypatch):
    from src.lunar_tools_art import frame_pipeline as fp

    class FlakyWebcam:
        def __init__(self):
            self.calls = 0

        def get_img(self):
            self.calls += 1
            if self.calls <= 2:
                return None
            return np.zeros((6, 8, 3), dtype=np.uint8)

    monkeypatch.setattr(fp.CameraCaptureThread, "RETRY_COOLDOWN_S", 0.02)

    class NullRenderer:
        width, height = 8, 6
        frames = []

        def render(self, image):
            self.frames.append(image)

    class NullKeys:
        def is_key_pressed(self, _key):
            return False

    renderer = NullRenderer()
    cap = fp.CameraCaptureThread(FlakyWebcam(), poll_interval=0.01)
    pipe = fp.GlitchPipeline(cap, renderer, NullKeys())
    cap.start()
    try:
        deadline = time.time() + 3
        while time.time() < deadline and cap.state != fp.CameraState.CONNECTED:
            time.sleep(0.02)
        assert cap.state == fp.CameraState.CONNECTED
        status = pipe.process_and_render(lambda f: f)
        assert status["rendered"] is True
        assert renderer.frames
    finally:
        cap.stop()
        cap.join()
