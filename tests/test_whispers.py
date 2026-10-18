"""Headless tests for the Whispers installation (Issue #40).

No hardware, no ML, no network: the particle/motion engine is pure numpy
against synthetic frames and the recorded reference clip, so every test is
deterministic. These pin the behaviours the acceptance criteria depend on:

  * 60 fps @ 720p with 2000 particles (offline pipeline measurement),
  * motion energy → particle emission within 3 frames (latency criterion),
  * a still room emits nothing; movement emits (emission follows motion),
  * particles persist across frames and build the session aura,
  * whispers: synthesis on a background thread, playback non-blocking,
    never more than one per whisper_gap_s, TTS failure never kills visuals,
  * controls (c/m/space/h/q) are edge-triggered,
  * source fallback: camera → video → synthetic, named in evidence,
  * headless smoke: duration exit, null renderer, fake keyboard.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pytest

from prototypes.whispers import Whispers, _hush
from src.lunar_tools_art.tools.headless import FakeRenderer

ROOT = Path(__file__).resolve().parent.parent
CLIP = ROOT / "outputs" / "glitch_lab" / "synthetic_reference_720p.mp4"


# --------------------------------------------------------------------------- 
# Fakes
# ---------------------------------------------------------------------------


class FakeKeys:
    def __init__(self):
        self.pressed = set()
        self.renderer_last_key = None  # mirrors Renderer.last_key

    def is_key_pressed(self, key):
        return key in self.pressed


class FakeSound:
    def __init__(self):
        self.calls = []

    def play_audio(self, data, samplerate=22050, blocking=None):
        self.calls.append({"blocking": blocking, "samples": len(data),
                           "samplerate": samplerate})

    def stop_sound(self):
        pass


class FakeTTS:
    """File-writing TTS stand-in matching the Text2Speech contract."""

    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def generate(self, text, voice=None):
        self.calls.append((text, voice))
        if self.fail:
            raise RuntimeError("tts down")
        import io
        import wave

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(22050)
            wf.writeframes(b"\x00\x00" * 2205)
        path = ROOT / "outputs" / "whispers" / "_test_tts.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(buf.getvalue())
        return str(path)


class NullWebCam:
    def get_img(self):
        return None


class RecordingRenderer:
    """Headless-FakeRenderer-shaped stand-in that keeps its frames."""

    def __init__(self):
        self.width, self.height = 1280, 720
        self.frames = []
        self.last_key = None

    def render(self, image):
        self.frames.append(image)

    def set_size(self, width, height):
        self.width, self.height = width, height

    def close(self):
        pass


class Manager:
    def __init__(self, tts=None, fail_tts=False):
        self.renderer = RecordingRenderer()
        self.keyboard_input = FakeKeys()
        self.sound_player = FakeSound()
        self.text2speech = tts if tts is not None else FakeTTS(fail=fts_fail(fail_tts))
        self.webcam = None
        self.logger = None


def fts_fail(flag):
    return flag


def make_manager(fail_tts=False):
    return Manager(fail_tts=fail_tts)


# ---------------------------------------------------------------------------
# Source selection & fallback
# ---------------------------------------------------------------------------


def test_source_falls_back_to_synthetic_and_names_itself():
    w = Whispers(make_manager(), duration=0.5, seed=1)
    w.run()
    assert w.source_kind == "synthetic"
    assert "procedural" in w.source_detail
    assert w.frame_count > 0


def test_video_source_loops_and_reports_kind():
    if not CLIP.exists():
        pytest.skip("reference clip not present")
    w = Whispers(make_manager(), duration=0.5, video_path=str(CLIP), seed=1)
    w.run()
    assert w.source_kind == "video"
    assert "looped" in w.source_detail


# ---------------------------------------------------------------------------
# Motion → emission coupling (latency + selectivity)
# ---------------------------------------------------------------------------


def _motion_frames():
    """A still frame, then identical frames with a moving block."""
    still = np.zeros((90, 160, 3), dtype=np.uint8)
    still[:] = 30
    frames = []
    for x in (10, 40, 70, 100, 130):
        f = still.copy()
        f[30:50, x:x + 20] = 255
        frames.append(f)
    return frames


def test_emission_follows_motion_within_three_frames():
    w = Whispers(make_manager(), seed=2)
    w._start_t = time.time()
    frames = _motion_frames()
    gray = w._grey_grid(w._to_frame(frames[0]))
    energy0, _, _, _ = w._motion_field(gray)
    w._prev_gray = gray
    assert w._n == 0

    # feed a genuinely moving subject; emission must appear by frame 3
    emitted_by = None
    for i, f in enumerate(frames[1:] + _motion_frames()[1:], start=1):
        g = w._grey_grid(w._to_frame(f))
        energy, cells, fx, fy = w._motion_field(g)
        w._spawn(w._to_frame(f), cells, fx, fy, energy, 1 / 60)
        if w._n > 0:
            emitted_by = i
            break
        w._prev_gray = g
    assert emitted_by is not None and emitted_by <= 3, (
        f"motion→emission latency {emitted_by} frames > 3"
    )


def test_still_room_emits_nothing():
    w = Whispers(make_manager(), seed=2)
    w._start_t = time.time()
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[:] = 30
    gray = w._grey_grid(frame)
    w._prev_gray = gray  # prime
    for _ in range(30):
        g = w._grey_grid(frame)
        energy, cells, fx, fy = w._motion_field(g)
        w._spawn(frame, cells, fx, fy, energy, 1 / 60)
        w._prev_gray = g
    assert w._n == 0
    assert w.motion_energy == pytest.approx(0.0, abs=0.5)


def test_aura_persists_and_ages_out():
    """Particles live across frames (aura), then die by age and free slots."""
    w = Whispers(make_manager(), seed=3)
    w._start_t = time.time()
    frames = _motion_frames()
    # prime the differencer with the base frame, then feed real movement
    w._prev_gray = w._grey_grid(w._to_frame(frames[0]))
    counts = []
    for f in frames[1:]:
        g = w._grey_grid(w._to_frame(f))
        energy, cells, fx, fy = w._motion_field(g)
        w._spawn(w._to_frame(f), cells, fx, fy, energy, 1 / 60)
        w._update_particles(1 / 60)
        w._prev_gray = g
        counts.append(w._n)
    assert counts[-1] >= counts[0] > 0  # accumulation across frames

    # now fast-forward: everything older than PARTICLE_LIFETIME_S must die
    w._age[: w._n] += 26.0
    w._update_particles(1 / 60)
    assert w._n == 0


# ---------------------------------------------------------------------------
# Performance (offline acceptance: 60 fps @ 720p, 2000 particles)
# ---------------------------------------------------------------------------


def test_sixty_fps_at_720p_with_2000_particles():
    w = Whispers(make_manager(), particle_cap=2000, seed=4)
    w._start_t = time.time()
    rng = np.random.default_rng(5)
    n = w.particle_cap
    w._n = n
    w._px[:n] = rng.random(n) * 1280
    w._py[:n] = rng.random(n) * 720
    w._vx[:n] = rng.normal(0, 20, n)
    w._vy[:n] = rng.normal(0, 20, n)
    w._age[:n] = rng.random(n) * 10
    w._size[:n] = 1 + rng.random(n) * 2.5
    w._col[:n] = rng.random((n, 3)) * 255

    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[:] = (40, 20, 60)
    canvas = np.zeros((720, 1280, 3), dtype=np.uint8)
    gray = w._grey_grid(frame)
    w._prev_gray = gray

    times = []
    for _ in range(240):
        t0 = time.perf_counter()
        g = w._grey_grid(frame)
        energy, cells, fx, fy = w._motion_field(g)
        w._spawn(frame, cells, fx, fy, energy, 1 / 60)
        w._update_particles(1 / 60)
        w._draw_particles(canvas)
        w._prev_gray = g
        times.append(time.perf_counter() - t0)
    mean_ms = 1000 * float(np.mean(times))
    fps_equiv = 1000.0 / mean_ms
    assert fps_equiv >= 60.0, f"pipeline only reaches {fps_equiv:.1f} fps at cap"


# ---------------------------------------------------------------------------
# Whispers: background synthesis, non-blocking playback, gap, resilience
# ---------------------------------------------------------------------------


def _bursty_energy(w, level):
    return level


def test_whisper_fires_on_motion_burst_then_respects_gap():
    mgr = make_manager()
    w = Whispers(mgr, whisper_gap_s=5.0, seed=6)
    w._start_t = time.time()
    w._energy_ema = 0.5
    # quiet period, then a burst
    assert w._maybe_whisper(0.2) is False      # below abs min energy
    fired = w._maybe_whisper(9.0)               # burst > 1.8 x EMA
    assert fired is True
    assert w.whispers_attempted == 1
    # within the gap: no second whisper even on another burst
    assert w._maybe_whisper(9.0) is False
    assert w.whispers_attempted == 1
    # wait for the background thread
    deadline = time.time() + 10
    while time.time() < deadline and not w.whisper_events:
        time.sleep(0.02)
    assert w.whisper_events, "synthesis thread never finished"
    evt = w.whisper_events[0]
    assert evt.played
    assert evt.error is None
    assert mgr.sound_player.calls, "playback never happened"
    assert all(c["blocking"] is False for c in mgr.sound_player.calls), (
        "whisper playback must be non-blocking"
    )


def test_steady_motion_does_not_invite_whispers():
    """Energy merely at its own EMA level is not a burst; no whisper.

    (A whisper at t≈0 is allowed — 'someone just walked in' — so the EMA
    must be warmed to steady state before asserting silence.)
    """
    mgr = make_manager()
    w = Whispers(mgr, whisper_gap_s=0.1, seed=7)
    w._start_t = time.time()
    # warm the EMA to steady 8.0 (≈50 updates) without allowing bursts:
    for _ in range(50):
        w._energy_ema = 0.94 * w._energy_ema + 0.06 * 8.0
    # steady energy at its own EMA: never a burst
    for _ in range(5):
        assert w._maybe_whisper(8.0) is False
    # gentle drift around the EMA is not a burst either
    for e in (6.5, 9.5, 8.0, 7.0, 10.0):
        assert w._maybe_whisper(e) is False
    assert w.whispers_attempted == 0


def test_tts_failure_never_kills_visuals():
    mgr = make_manager(fail_tts=True)
    w = Whispers(mgr, whisper_gap_s=0.0, seed=8)
    w._start_t = time.time()
    w._energy_ema = 0.1
    fired = w._maybe_whisper(50.0)
    assert fired is True
    deadline = time.time() + 10
    while time.time() < deadline and not w.whisper_events:
        time.sleep(0.02)
    evt = w.whisper_events[0]
    assert evt.played is False
    assert evt.error
    # and the loop itself is unaffected:
    assert w._running is False  # never started, no crash flag set
    assert w.last_fatal_error is None


def test_hush_scales_volume_and_mixes_mono():
    import soundfile as sf

    t = np.linspace(0, 0.1, 2205, endpoint=False)
    stereo = np.stack([np.sin(2 * np.pi * 440 * t)] * 2, axis=1)
    path = ROOT / "outputs" / "whispers" / "_test_hush.wav"
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, stereo, 22050)
    samples, sr = _hush(str(path), 0.22)
    assert sr == 22050
    assert samples.ndim == 1
    peak = float(np.abs(samples).max())
    assert peak <= 1.0 and peak > 0.0
    # mono mix of identical channels: amplitude preserved before scaling
    original_peak = float(np.abs(stereo[:, 0]).max())
    assert peak == pytest.approx(original_peak * 0.22, rel=0.01)


# ---------------------------------------------------------------------------
# Controls are edge-triggered
# ---------------------------------------------------------------------------


def _armed_whispers():
    w = Whispers(make_manager(), seed=9)
    w._start_t = time.time()
    return w


def test_controls_edge_triggered():
    w = _armed_whispers()
    w._n = 100
    w._on_key("c")
    assert w._n == 0
    w._on_key("m")
    assert w._show_motion is True
    w._on_key("h")
    assert w._show_hud is True
    mgr = w.manager
    # holding via the fake keyboard must not repeat-clear (edge logic)
    w._n = 50
    mgr.keyboard_input.pressed.add("c")
    w._poll_controls()
    assert w._n == 0  # cleared once on the new edge
    w._n = 50
    w._poll_controls()  # still held: no repeated action would be visible…
    # …but n was reset deliberately; re-hold test: no edge, no clear
    mgr.keyboard_input.pressed.add("c")
    w._poll_controls()
    assert w._n == 50, "held key must not edge-fire again"
    mgr.keyboard_input.pressed.discard("c")
    w._poll_controls()
    mgr.keyboard_input.pressed.add("c")
    w._poll_controls()
    assert w._n == 0, "release-then-press must fire again"


def test_opencv_last_key_edge_detection():
    """Renderer.last_key path: same key twice = held = no re-fire."""
    w = _armed_whispers()
    w._n = 10
    w.renderer.last_key = "c"
    w._poll_controls()
    assert w._n == 0
    w._n = 10
    w.renderer.last_key = "c"  # still the same key held
    w._poll_controls()
    assert w._n == 10, "same-key repeat must not re-fire (edge only)"
    w.renderer.last_key = None
    w._poll_controls()
    w.renderer.last_key = "c"
    w._poll_controls()
    assert w._n == 0


def test_q_stops_loop():
    w = _armed_whispers()
    w._running = True
    w._on_key("q")
    assert w._running is False


# ---------------------------------------------------------------------------
# End-to-end headless smoke
# ---------------------------------------------------------------------------


def test_headless_run_smoke():
    w = Whispers(make_manager(), duration=1.0, synthetic_motion=True, seed=11)
    w._show_hud = True
    w._show_motion = True
    w.run()
    assert w.frame_count > 20
    assert w.source_kind == "synthetic"
    assert w.last_fatal_error is None
    assert len(w.manager.renderer.frames) == w.frame_count