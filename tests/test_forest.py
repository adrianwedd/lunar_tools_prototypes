"""Deterministic headless tests for the Audio-Reactive Fractal Forest (#39).

No hardware, no network, no LLM. Pins:
  * the WAV block source loops and is InputStream-shaped;
  * feature extraction: RMS, centroid shift, onset detection on beats,
    silence reads below the threshold;
  * the reader thread feeds features without blocking the render loop;
  * growth responds within 3 frames of an onset;
  * silence recedes growth slowly and never freezes sway;
  * the skeleton is bounded (segment count) and deterministic per seed;
  * headless run(): duration exit, no fatal error.
"""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path

import numpy as np
import pytest

from tests.test_whispers import Manager, make_manager

# the prototype module has hyphens in its filename; load it directly
_spec = importlib.util.spec_from_file_location(
    "forest_proto",
    Path(__file__).resolve().parent.parent
    / "prototypes" / "audio-reactive-fractal-forest.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

AudioFeatures = _mod.AudioFeatures
AudioReactiveFractalForest = _mod.AudioReactiveFractalForest
ForestSkeleton = _mod.ForestSkeleton
WavBlockSource = _mod.WavBlockSource

SR = 22050


def _forest(seed=5, **kw):
    f = AudioReactiveFractalForest(make_manager(), seed=seed, **kw)
    f._start_t = time.time()
    return f


def _tone(freq, dur, amp=0.3, sr=SR):
    t = np.arange(int(dur * sr)) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


# ---------------------------------------------------------------------------
# WAV block source
# ---------------------------------------------------------------------------


def test_wav_source_loops_and_shapes(tmp_path):
    import soundfile as sf

    wav = tmp_path / "t.wav"
    sf.write(wav, _tone(220, 1.0), SR)
    src = WavBlockSource(str(wav), block=1024, sr=SR)
    blocks = [src.read() for _ in range(int(SR / 1024) + 5)]
    assert all(b.shape == (1024,) and b.dtype == np.float32 for b in blocks)
    # after looping, content repeats
    assert np.allclose(blocks[0], blocks[-5], atol=1e-4)


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------


def test_features_on_beats_and_silence():
    f = _forest(seed=2)
    silent = np.zeros(f.block, dtype=np.float32)
    r = f._analyse_block(silent, 0.0)
    assert r.rms == pytest.approx(0.0, abs=1e-6)
    assert r.onset is False

    # warm the median with quiet, then a loud beat must onset
    for _ in range(10):
        f._analyse_block(silent * 0.001, 0.0)
    beat = _tone(220, f.block / SR, amp=0.4)[:f.block]
    r = f._analyse_block(beat, 0.0)
    assert r.onset is True
    assert r.rms > 0.2


def test_centroid_separates_low_and_high_tones():
    f = _forest(seed=3)
    low = _tone(220, f.block / SR, amp=0.3)[:f.block]
    high = _tone(1760, f.block / SR, amp=0.3)[:f.block]
    c_low = f._analyse_block(low, 0.0).centroid
    c_high = f._analyse_block(high, 0.0).centroid
    assert c_high > c_low + 0.1


# ---------------------------------------------------------------------------
# Skeleton
# ---------------------------------------------------------------------------


def test_skeleton_bounded_and_deterministic():
    a = ForestSkeleton(seed=7)
    b = ForestSkeleton(seed=7)
    c = ForestSkeleton(seed=8)
    assert a.n_segments() == b.n_segments()
    assert np.array_equal(a.x0, b.x0)
    assert a.n_segments() != c.n_segments() or not np.array_equal(a.x0, c.x0)
    assert a.n_segments() < 20000, "skeleton must stay bounded"
    assert len(a.trees) <= 14


# ---------------------------------------------------------------------------
# Reactivity & drift
# ---------------------------------------------------------------------------


def test_growth_responds_within_three_frames():
    f = _forest(seed=4)
    canvas = np.zeros((720, 1280, 3), dtype=np.uint8)
    dt = 1 / 30
    for i in range(30):  # settle into silence
        f._draw(canvas, i * dt, AudioFeatures(0.0, 0.1, False, i * dt), dt)
    g0 = f.growth
    responded = None
    for i in range(6):
        f._draw(canvas, (30 + i) * dt,
                AudioFeatures(0.30, 0.5, onset=(i == 0), t=i * dt), dt)
        if f.growth > g0 + 0.02:
            responded = i + 1
            break
    assert responded is not None and responded <= 3
    assert f.onsets_detected == 1


def test_silence_recedes_but_never_freezes():
    f = _forest(seed=6)
    canvas = np.zeros((720, 1280, 3), dtype=np.uint8)
    dt = 1 / 30
    for i in range(30):
        f._draw(canvas, i * dt, AudioFeatures(0.30, 0.5, False, i * dt), dt)
    g_loud = f.growth
    prev = None
    moved = 0
    sk = f.skeleton
    probe = int(np.argmax(sk.depth))
    for i in range(150):  # 5 s of silence
        f._draw(canvas, (30 + i) * dt, AudioFeatures(0.0, 0.0, False, 0), dt)
        nx, ny = sk.positions((30 + i) * dt, 1.5)
        cur = float(abs(nx[probe]) + abs(ny[probe]))
        if prev is not None and abs(cur - prev) > 1e-4:
            moved += 1
        prev = cur
    assert f.growth < g_loud          # recedes
    assert f.growth > 0.05           # but the forest never disappears
    assert moved >= 145              # and keeps swaying (no wallpaper freeze)


# ---------------------------------------------------------------------------
# Headless run
# ---------------------------------------------------------------------------


def test_headless_run_duration_exit(tmp_path):
    import soundfile as sf

    wav = tmp_path / "loop.wav"
    t = np.arange(int(2 * SR)) / SR
    env = ((np.sin(t * 2 * np.pi * 2) + 1) / 2) ** 3
    sf.write(wav, (0.3 * env * np.sin(2 * np.pi * 220 * t)).astype(np.float32), SR)

    f = AudioReactiveFractalForest(
        make_manager(), duration=2.0, wav_path=str(wav), seed=9
    )
    f.run()
    assert f.frame_count > 40
    assert f.last_fatal_error is None
    assert f.onsets_detected >= 1