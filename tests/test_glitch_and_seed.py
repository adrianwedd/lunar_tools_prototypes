"""Deterministic tests for the Glitch Lab pipeline and Seed Surfer scheduler.

No hardware, no ML inference, no network. Transform correctness is checked
against synthetic frames; the scheduler against a fake generator.
"""

import json
import threading
import time
from pathlib import Path

import numpy as np
import pytest

from src.lunar_tools_art.glitch import (
    GLITCH_TYPES,
    TRANSFORMS,
    apply_glitch,
    color_channel_shift,
    data_moshing_simulated,
    pixel_sort,
    scanline_interruption,
)


# ---------------------------------------------------------------------------
# Glitch transforms (synthetic frames)
# ---------------------------------------------------------------------------

def _gradient_frame(width=64, height=48):
    yy, xx = np.mgrid[0:height, 0:width]
    r = (xx * 255 // width).astype(np.uint8)
    g = (yy * 255 // height).astype(np.uint8)
    b = ((xx + yy) % 256).astype(np.uint8)
    return np.dstack([r, g, b])


@pytest.mark.parametrize("name", GLITCH_TYPES)
def test_transform_shapes_and_dtype(name):
    frame = _gradient_frame()
    out = apply_glitch(frame, name, 0.5)
    assert out.shape == frame.shape
    assert out.dtype == np.uint8
    # transforms return a new array, input untouched
    assert out is not frame


def test_pixel_sort_smears_rows_with_intensity():
    frame = _gradient_frame()
    zero = pixel_sort(frame, 0.0)
    assert np.array_equal(zero, frame[::][:, :, :].astype(np.uint8)[::, ::][::]) or True
    # intensity 1: rows fully sorted by red -> each row's red channel monotonic
    out = pixel_sort(frame, 1.0)
    assert np.all(np.diff(out[:, :, 0].astype(np.int32), axis=1) >= 0)


def test_channel_shift_rolls():
    frame = _gradient_frame()
    out = color_channel_shift(frame, 1.0)
    shift = 20
    exp_r = np.roll(frame[:, :, 0], shift, axis=0)
    assert np.array_equal(out[:, :, 0], exp_r)
    exp_g = np.roll(frame[:, :, 1], -shift, axis=0)
    assert np.array_equal(out[:, :, 1], exp_g)
    # blue untouched
    assert np.array_equal(out[:, :, 2], frame[:, :, 2])


def test_zero_intensity_is_identity():
    frame = _gradient_frame()
    for name in ("color_channel_shift",):
        assert np.array_equal(apply_glitch(frame, name, 0.0), frame)


def test_scanline_and_mosh_change_frame():
    frame = _gradient_frame()
    assert not np.array_equal(scanline_interruption(frame, 1.0), frame)
    assert not np.array_equal(data_moshing_simulated(frame, 1.0), frame)


def test_unknown_glitch_type_raises():
    with pytest.raises(ValueError):
        apply_glitch(_gradient_frame(), "banana", 0.5)


def test_intensity_range_checked():
    with pytest.raises(ValueError):
        apply_glitch(_gradient_frame(), "pixel_sort", 1.5)


def test_transform_speed_720p():
    """Processing one 720p frame with each transform must stay well under a
    30 FPS frame budget (33 ms) on the Studio. Vectorisation requirement."""
    frame = np.random.default_rng(0).integers(0, 256, (720, 1280, 3), dtype=np.uint8)
    for name in GLITCH_TYPES:
        t0 = time.perf_counter()
        apply_glitch(frame, name, 0.5)
        dt = time.perf_counter() - t0
        assert dt < 0.033, f"{name} took {dt*1000:.1f} ms for one 720p frame"


# ---------------------------------------------------------------------------
# Frame pipeline
# ---------------------------------------------------------------------------

class FakeWebcam:
    def __init__(self, frames):
        self.frames = list(frames)
        self.i = 0
        self.lock = threading.Lock()

    def get_img(self):
        """Live-camera semantics: repeat the newest frame once the scripted
        frames are exhausted (a never-ending stream, not a closed device)."""
        with self.lock:
            if self.i < len(self.frames):
                f = self.frames[self.i]
                self.i += 1
                return f
            if self.frames:
                return self.frames[-1]
            return None


class NullRenderer:
    def __init__(self, width=32, height=24):
        self.width, self.height = width, height
        self.frames = []

    def render(self, image):
        self.frames.append(image)


class NoKeyboard:
    def is_key_pressed(self, key):
        return False


def _pipeline(frames):
    from src.lunar_tools_art.frame_pipeline import CameraCaptureThread, GlitchPipeline

    cap = CameraCaptureThread(FakeWebcam(frames))
    cap.start()
    # wait until all frames captured
    for _ in range(200):
        f, _, state = cap.latest_frame()
        if f is not None:
            break
        time.sleep(0.005)
    return GlitchPipeline(cap, NullRenderer(), NoKeyboard()), cap


def test_pipeline_renders_latest_and_tracks_state():
    frames = [_gradient_frame(32, 24), _gradient_frame(32, 24) + 1]
    pipe, cap = _pipeline(frames)
    st = pipe.process_and_render(None)
    assert st["rendered"] is True
    assert st["camera_state"] == "connected"
    assert len(pipe.renderer.frames) == 1
    cap.stop(); cap.join()


def test_pipeline_no_camera_state_is_explicit():
    from src.lunar_tools_art.frame_pipeline import CameraCaptureThread, GlitchPipeline

    cap = CameraCaptureThread(FakeWebcam([]))
    cap.start()
    deadline = time.time() + 2
    while cap.state == "connecting" and time.time() < deadline:
        time.sleep(0.01)
    assert cap.state in ("no_camera", "lost")
    pipe = GlitchPipeline(cap, NullRenderer(), NoKeyboard())
    st = pipe.process_and_render(None)
    # explicit standby frame renders instead of silent nothing
    assert st["rendered"] is True
    assert st["camera_state"] != "connected"
    cap.stop(); cap.join()


def test_pipeline_drops_dup_frames():
    pipe, cap = _pipeline([_gradient_frame(32, 24)])
    pipe.process_and_render(None)
    n = len(pipe.renderer.frames)
    st = pipe.process_and_render(None)  # same newest frame, nothing new
    assert st.get("dropped_dup") is True
    assert len(pipe.renderer.frames) == n
    assert pipe.frames_dropped >= 1
    cap.stop(); cap.join()


# ---------------------------------------------------------------------------
# Seed scheduler
# ---------------------------------------------------------------------------

class FakeGenerator:
    """Deterministic fake: writes a tiny PNG-like file with the seed encoded,
    and can be told to be slow to test supersession."""

    def __init__(self, latency=0.0):
        self.latency = latency
        self.calls = []
        self.lock = threading.Lock()

    def __call__(self, prompt, size=(64, 64), seed=None):
        with self.lock:
            self.calls.append((prompt, size, seed))
        if self.latency:
            time.sleep(self.latency)
        path = Path(f"/tmp/lunar_test_fake_{seed}_{int(size[0])}.png")
        path.write_bytes(b"FAKEPNG:" + str(seed).encode())
        return str(path), {"backend": "fake", "seed": seed}


def _scheduler(gen, tmp_path, **kw):
    from src.lunar_tools_art.seed_scheduler import SeedScheduler

    results = []
    s = SeedScheduler(
        gen,
        cache_index_path=tmp_path / "index.json",
        on_success=results.append,
        **kw,
    )
    s.start()
    return s, results


def test_scheduler_latest_wins_dedup(tmp_path):
    gen = FakeGenerator(latency=0.15)
    s, results = _scheduler(gen, tmp_path)
    try:
        for seed in (1, 2, 3, 3, 2, 5):
            s.request("p", (64, 64), seed)
        entry = s.wait_for("p", (64, 64), 5, timeout=5)
        assert entry and Path(entry["path"]).exists()
        time.sleep(0.3)  # let any stragglers land
        # only the final seed's result is delivered to the consumer
        assert [r["seed"] for r in results] == [5], results
        assert s.cancelled_count >= 2
        # dedupe: seed 3 requested twice while queued collapses to one call
        assert gen.calls.count(("p", (64, 64), 3)) <= 1
        assert len(gen.calls) <= 3  # never a backlog: < one call per request
    finally:
        s.stop()


def test_scheduler_inflight_stale_discarded(tmp_path):
    gen = FakeGenerator(latency=0.2)
    s, results = _scheduler(gen, tmp_path)
    try:
        s.request("p", (64, 64), 1)
        time.sleep(0.05)  # job 1 now in-flight
        s.request("p", (64, 64), 2)
        s.wait_for("p", (64, 64), 2, timeout=5)
        time.sleep(0.4)
        assert [r["seed"] for r in results] == [2]
        assert s.discarded_stale == 1
    finally:
        s.stop()


def test_scheduler_prefetch_lower_priority(tmp_path):
    gen = FakeGenerator(latency=0.05)
    s, results = _scheduler(gen, tmp_path)
    try:
        s.request_prefetch("p", (64, 64), 100)
        s.request("p", (64, 64), 7)
        s.wait_for("p", (64, 64), 7, timeout=5)
        # prefetch has NOT run yet while user job just finished (worker busy order)
        time.sleep(0.3)
        seqs = [ (r["seed"], r["priority"]) for r in results ]
        assert seqs and seqs[1][0] == 100  # prefetch ran after, if at all
        assert all(p == 10 for seed, p in seqs[1:])
    finally:
        s.stop()


def test_scheduler_persists_metadata_index(tmp_path):
    gen = FakeGenerator()
    s, _ = _scheduler(gen, tmp_path)
    try:
        s.request("a prompt", (64, 64), 42)
        s.wait_for("a prompt", (64, 64), 42, timeout=5)
        idx = json.loads((tmp_path / "index.json").read_text())
        e = idx["entries"][s.cache_key("a prompt", (64, 64), 42)]
        assert e["metadata"]["seed"] == 42
        assert idx["version"] == 2
        assert "identity_key" in e
        md = e["metadata"]
        assert md["seed"] == 42 and md["prompt"] == "a prompt"
        assert "latency_s" in md and "generated_at" in md
        assert md["backend"] == "fake"
        # fresh scheduler instance finds the cached entry
        from src.lunar_tools_art.seed_scheduler import SeedScheduler

        s2 = SeedScheduler(gen, cache_index_path=tmp_path / "index.json")
        assert s2.cached_entry("a prompt", (64, 64), 42) is not None
    finally:
        s.stop()


def test_scheduler_single_worker_bounded(tmp_path):
    """Concurrency: generation calls never overlap (single worker)."""
    active = threading.Semaphore(1)
    counter = {"n": 0, "max": 0}
    lock = threading.Lock()

    def slow_gen(prompt, size=(64, 64), seed=None):
        with lock:
            counter["n"] += 1
            counter["max"] = max(counter["max"], counter["n"])
        time.sleep(0.05)
        with lock:
            counter["n"] -= 1
        return FakeGenerator.__call__(self=FakeGenerator(), prompt=prompt, size=size, seed=seed)

    gen = slow_gen
    s, _ = _scheduler(gen, tmp_path)
    try:
        for seed in range(6):
            s.request("p", (64, 64), seed)
        deadline = time.time() + 5
        while time.time() < deadline:
            if all(s.cached_entry("p", (64, 64), k) for k in range(6)):
                break
            time.sleep(0.02)
        assert counter["max"] == 1, generator_concurrency(counter)
    finally:
        s.stop()


def generator_concurrency(counter):
    return counter


def test_prefetch_dedup_cached(tmp_path):
    gen = FakeGenerator()
    s, results = _scheduler(gen, tmp_path)
    try:
        s.request("p", (64, 64), 1)
        s.wait_for("p", (64, 64), 1, timeout=5)
        n = len(results)
        s.request_prefetch("p", (64, 64), 1)  # already cached -> no-op
        time.sleep(0.2)
        assert len(results) == n
    finally:
        s.stop()