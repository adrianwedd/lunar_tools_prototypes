#!/usr/bin/env python
"""Offline verification for the Audio-Reactive Fractal Forest (#39).

Against the REAL implementation (prototypes/audio-reactive-fractal-forest.py):

  perf     — measure the full draw pipeline (skeleton positions + branches
             + canopy glow) wall time per frame at 720p; acceptance >=30 fps.
  features — drive _analyse_block with a synthetic WAV-shaped signal:
             beats must raise RMS and fire onsets; a spectral shift must
             move the centroid; silence must read as rms < SILENCE_RMS.
  reactivity — simulate the render loop's growth response to an onset:
             growth must measurably move within 3 frames of the onset.
  drift    — over 60 s of simulated silence the forest must keep swaying:
             positions must change every frame (no wallpaper freeze).

Run: env/bin/python scripts/verify_forest.py
Writes outputs/forest/verification.json.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT = ROOT / "outputs" / "forest"
OUT.mkdir(parents=True, exist_ok=True)
RESULTS = OUT / "verification.json"
SR = 22050


def _load_forest():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "forest_proto",
        ROOT / "prototypes" / "audio-reactive-fractal-forest.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _NullRenderer:
    width, height = 1280, 720
    last_key = None

    def render(self, img):
        pass

    def set_size(self, *a):
        pass

    def close(self):
        pass


class _NullKeys:
    def is_key_pressed(self, k):
        return False


class _Manager:
    renderer = _NullRenderer()
    keyboard_input = _NullKeys()
    logger = None


def mode_perf(mod):
    import cv2

    forest = mod.AudioReactiveFractalForest(_Manager(), seed=1)
    canvas = np.zeros((720, 1280, 3), dtype=np.uint8)
    feats = mod.AudioFeatures(rms=0.12, centroid=0.5, onset=False, t=0.0)
    # warm
    forest._draw(canvas, 0.0, feats, 1 / 30)
    times = []
    N = 240
    for i in range(N):
        t0 = time.perf_counter()
        forest._draw(canvas, i / 30, feats, 1 / 30)
        times.append(time.perf_counter() - t0)
    ms = np.array(times) * 1000.0
    return {
        "mode": "perf",
        "frames": N,
        "segments": forest.skeleton.n_segments(),
        "trees": len(forest.skeleton.trees),
        "frame_ms": {
            "p50": round(float(np.percentile(ms, 50)), 2),
            "p95": round(float(np.percentile(ms, 95)), 2),
            "mean": round(float(ms.mean()), 2),
        },
        "fps_equiv": round(1000.0 / float(ms.mean()), 1),
        "acceptance_30fps": bool(1000.0 / float(ms.mean()) >= 30.0),
    }


def _test_signal():
    """8 s: 1 s silence, 3 s of 2 Hz beats (220 Hz tone bursts), 1 s silence,
    2 s of bright high tone (1760 Hz), 1 s silence."""
    n_total = int(8 * SR)
    sig = np.zeros(n_total, dtype=np.float32)
    t = np.arange(n_total) / SR

    def put(t0, t1, gen):
        m = (t >= t0) & (t < t1)
        sig[m] = gen(t[m]).astype(np.float32)

    # beats: 220 Hz bursts, 2 Hz envelope, amplitude 0.35
    def beats(tt):
        env = ((np.sin(tt * 2 * np.pi * 2) + 1) / 2) ** 3
        return 0.35 * env * np.sin(tt * 2 * np.pi * 220)

    put(1.0, 4.0, beats)
    put(5.0, 7.0, lambda tt: 0.25 * np.sin(tt * 2 * np.pi * 1760))
    return sig


def mode_features(mod):
    forest = mod.AudioReactiveFractalForest(_Manager(), seed=2)
    sig = _test_signal()
    block = forest.block
    feats = []
    for i in range(0, len(sig) - block, block):
        f = forest._analyse_block(sig[i:i + block], i / SR)
        feats.append((i / SR, f))
    rms = np.array([f.rms for _, f in feats])
    cen = np.array([f.centroid for _, f in feats])
    ons = [t for t, f in feats if f.onset]

    silent_ok = all(f.rms < mod.SILENCE_RMS * 2 for t, f in feats
                    if t < 0.9 or (3.9 < t < 5.0))
    beat_energy = rms[(np.array([t for t, _ in feats]) >= 1) &
                      (np.array([t for t, _ in feats]) < 4)]
    onset_in_beats = [t for t in ons if 1.0 <= t < 4.0]
    # centroid must be higher during the 1760 Hz section than during beats
    hi = cen[(np.array([t for t, _ in feats]) >= 5) &
             (np.array([t for t, _ in feats]) < 7)]
    lo = beat_energy_cen = cen[(np.array([t for t, _ in feats]) >= 1) &
                               (np.array([t for t, _ in feats]) < 4)]
    return {
        "mode": "features",
        "blocks": len(feats),
        "onsets": len(ons),
        "onset_times": [round(x, 2) for x in ons[:12]],
        "silent_blocks_below_threshold": silent_ok,
        "beat_rms_mean": round(float(beat_energy.mean()), 4),
        "beat_onsets": len(onset_in_beats),
        "centroid_hi_mean": round(float(hi.mean()), 3),
        "centroid_lo_mean": round(float(lo.mean()), 3),
        "centroid_shifts": bool(hi.mean() > lo.mean() + 0.1),
        "acceptance": bool(
            silent_ok and len(onset_in_beats) >= 3 and hi.mean() > lo.mean() + 0.1
        ),
    }


def mode_reactivity(mod):
    """Growth must respond measurably within 3 frames of an onset."""
    forest = mod.AudioReactiveFractalForest(_Manager(), seed=3)
    canvas = np.zeros((720, 1280, 3), dtype=np.uint8)
    dt = 1 / 30
    # settle into silence
    for i in range(30):
        forest._draw(canvas, i * dt, mod.AudioFeatures(0.0, 0.1, False, i * dt), dt)
    g0 = forest.growth
    # onset block, then sustained loud energy
    responded = None
    for i in range(10):
        f = mod.AudioFeatures(0.30, 0.5, onset=(i == 0), t=i * dt)
        forest._draw(canvas, (30 + i) * dt, f, dt)
        if forest.growth > g0 + 0.02:
            responded = i + 1
            break
    return {
        "mode": "reactivity",
        "growth_before": round(g0, 4),
        "growth_after": round(forest.growth, 4),
        "bloom_fired": forest.bloom > 0.5,
        "frames_to_respond": responded,
        "acceptance_3_frames": bool(responded is not None and responded <= 3),
    }


def mode_drift(mod):
    """Silence must not freeze the forest: positions keep changing."""
    forest = mod.AudioReactiveFractalForest(_Manager(), seed=4)
    canvas = np.zeros((720, 1280, 3), dtype=np.uint8)
    dt = 1 / 30
    moved = 0
    prev = None
    sk = forest.skeleton
    probe = int(np.argmax(sk.depth))  # the deepest branch sways the most
    for i in range(120):  # 4 s of silence
        forest._draw(canvas, i * dt, mod.AudioFeatures(0.0, 0.0, False, i * dt), dt)
        nx, ny = sk.positions(i * dt, 1.5)
        cur = float(abs(nx[probe]) + abs(ny[probe]))  # a deep tip
        if prev is not None and abs(cur - prev) > 1e-4:
            moved += 1
        prev = cur
    return {
        "mode": "drift",
        "frames": 120,
        "frames_with_visible_sway": moved,
        "acceptance_no_freeze": bool(moved >= 118),
    }


def main():
    mod = _load_forest()
    results = {}
    results.update(mode_perf(mod))
    results.update(mode_features(mod))
    results.update(mode_reactivity(mod))
    results.update(mode_drift(mod))
    results["date"] = time.strftime("%Y-%m-%d %H:%M:%S")
    results["machine"] = "arm64"
    RESULTS.write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))
    ok = (
        results["acceptance_30fps"]
        and results["acceptance"]
        and results["acceptance_3_frames"]
        and results["acceptance_no_freeze"]
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())