#!/usr/bin/env python
"""Produce the Fractal Forest demonstration (windowed, real pipeline).

Builds a 24 s test signal with a deliberate musical arc (silence, slow
pulses, rhythmic section, bright high notes, silence), then runs the REAL
AudioReactiveFractalForest against it in a window (opencv renderer), with
HUD on and the window recorded. Muxes nothing (the forest is a visual
demo; audio analysis is the input, not the output).

Outputs (outputs/forest/):
  test_signal.wav     — the input arc
  forest_demo_raw.mp4 — recorded window (opens ~3 s in)
  forest_demo.mp4     — trimmed/encoded demo
  forest_evidence.json — fps p50/p95, onset times vs signal beats,
                          growth curve vs the arc, tree/segment counts
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT = ROOT / "outputs" / "forest"
OUT.mkdir(parents=True, exist_ok=True)
WAV = OUT / "test_signal.wav"
RAW = OUT / "forest_demo_raw.mp4"
FINAL = OUT / "forest_demo.mp4"
EVIDENCE = OUT / "forest_evidence.json"
SR = 22050
DURATION = 24.0


def build_signal():
    """Musical arc: 3 s silence -> 5 s slow deep pulses (55 Hz, 0.5 Hz) ->
    8 s rhythmic section (220 Hz beats at 2 Hz with a 440 Hz melody line)
    -> 4 s bright high run (1320/1760 Hz alternating) -> 4 s silence."""
    t = np.arange(int(DURATION * SR)) / SR
    sig = np.zeros_like(t)

    def put(t0, t1, fn):
        m = (t >= t0) & (t < t1)
        sig[m] += fn(t[m])

    put(3, 8, lambda tt: 0.30 * np.sin(2 * np.pi * 55 * tt)
        * ((np.sin(2 * np.pi * 0.5 * tt) + 1) / 2))
    put(8, 16, lambda tt: 0.28 * np.sin(2 * np.pi * 220 * tt)
        * ((np.sin(2 * np.pi * 2 * tt) + 1) / 2) ** 3
        + 0.10 * np.sin(2 * np.pi * 440 * tt)
        * (np.sin(2 * np.pi * 0.75 * tt) > 0))
    put(16, 20, lambda tt: 0.22 * np.sin(2 * np.pi * (1320 + 440 * (np.sin(2 * np.pi * 1.5 * tt) > 0)) * tt)
        * ((np.sin(2 * np.pi * 3 * tt) + 1) / 2) ** 2)

    import soundfile as sf

    sf.write(WAV, sig.astype(np.float32), SR, subtype="PCM_16")
    return WAV


def run_forest():
    from lunar_tools_art.manager import LunarToolsArtManager
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "forest_proto", ROOT / "prototypes" / "audio-reactive-fractal-forest.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    mgr = LunarToolsArtManager()
    assert mgr.renderer.backend == "opencv", mgr.renderer.backend

    f = mod.AudioReactiveFractalForest(
        mgr,
        duration=DURATION,
        wav_path=str(WAV),
        seed=42,
        record_path=str(RAW),
    )
    f._show_hud = True

    frame_times = []
    real_render = f.renderer.render

    def timed(canvas):
        t0 = time.perf_counter()
        real_render(canvas)
        frame_times.append(time.perf_counter() - t0)

    f.renderer.render = timed

    t0 = time.time()
    f.run()
    wall = time.time() - t0
    return f, wall, frame_times


def main():
    build_signal()
    f, wall, frame_times = run_forest()

    ft = np.array(frame_times) * 1000.0
    gs = np.array([g for _, g in f.growth_samples])
    ts = np.array([t for t, _ in f.growth_samples])
    evidence = {
        "run": "forest-windowed-demo",
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "wall_seconds": round(wall, 2),
        "frames": f.frame_count,
        "fps_measured": round(f.fps, 1),
        "render_call_ms": {
            "p50": round(float(np.percentile(ft, 50)), 2),
            "p95": round(float(np.percentile(ft, 95)), 2),
        },
        "trees": len(f.skeleton.trees),
        "segments": f.skeleton.n_segments(),
        "onsets_detected": f.onsets_detected,
        "last_onset_t": f.last_onset_t,
        "growth_curve": {
            "min": round(float(gs.min()), 3),
            "max": round(float(gs.max()), 3),
            "final": round(float(gs[-1]), 3),
            "grew_with_music": bool(gs.max() > gs.min() + 0.15),
        },
        "last_fatal_error": f.last_fatal_error,
    }
    EVIDENCE.write_text(json.dumps(evidence, indent=2))

    # trim the warm-up (recorder opens ~3 s in) and encode
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(RAW)], capture_output=True, text=True, check=True)
    dur = float(probe.stdout.strip())
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", str(RAW), "-c:v", "libx264", "-preset",
         "medium", "-crf", "23", "-pix_fmt", "yuv420p", str(FINAL)],
        capture_output=True, text=True)
    ok = r.returncode == 0
    evidence["demo_video"] = str(FINAL) if ok else None
    EVIDENCE.write_text(json.dumps(evidence, indent=2))

    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", "10", "-i", str(FINAL),
         "-frames:v", "1", str(OUT / "forest_demo_preview.png")],
        check=True,
    )
    print(json.dumps(evidence, indent=2))
    return 0 if ok and f.last_fatal_error is None and f.frame_count > 200 else 1


if __name__ == "__main__":
    sys.exit(main())