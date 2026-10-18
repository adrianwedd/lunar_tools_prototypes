#!/usr/bin/env python
"""Build the Whispers demo movement source + run the real installation.

Stage 1 renders a 30 s 720p "visitor" clip with a deliberate arc:
   0-8 s   stillness (empty room, faint ambient shimmer)
   8-18 s  gentle movement (a soft figure drifting slowly)
   18-27 s intense movement (fast sweeping gesture)
  27-30 s  settling back toward stillness
Stage 2 runs the REAL Whispers pipeline against that clip (windowed, opencv
renderer), recording the rendered window and the procedural audio track.
Stage 3 muxes to whispers_demo_v2.mp4 (H.264 + AAC) and writes an evidence
JSON with the measured performance (p50/p95 frame times) and the arc's
per-phase particle/energy stats.

Run:  RENDERER__BACKEND=opencv env/bin/python scripts/make_whispers_demo_v2.py
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT = ROOT / "outputs" / "whispers"
SRC_CLIP = OUT / "demo_movement_source.mp4"
RAW = OUT / "demo_v2_raw.mp4"
WAV = OUT / "demo_v2_audio.wav"
FINAL = OUT / "whispers_demo_v2.mp4"
EVIDENCE = OUT / "demo_v2_evidence.json"

W, H = 1280, 720
FPS = 30
DURATION = 30.0
N = int(DURATION * FPS)


def movement_arc(t: float):
    """Return (mode, centre_x, centre_y, radius, brightness) at time t."""
    if t < 8.0:            # stillness: nothing but a faint shimmer
        return "still", 0, 0, 0, 0.0
    if t < 18.0:           # gentle: a figure drifting at walking pace
        u = (t - 8.0) / 10.0
        return "gentle", 0.15 + 0.7 * u, 0.55 + 0.15 * np.sin(u * 6), 90, 0.55
    if t < 27.0:           # intense: abrupt gestural jerks, on/off
        u = (t - 18.0) / 9.0
        # gesture strobes: sharp on/off so each onset is a SUDDEN burst
        gate = 0.5 + 0.5 * np.sign(np.sin(u * 3 * np.pi))
        if gate < 0.5:
            return "still", 0.5, 0.5, 0, 0.0     # abrupt stop (stillness beat)
        x = 0.5 + 0.42 * np.sin(u * 18)     # fast horizontal sweeps
        y = 0.5 + 0.25 * np.cos(u * 11)
        return "sudden", x, y, 140, 0.95
    u = min(1.0, (t - 27.0) / 3.0)          # settle
    fade = 1.0 - u
    return "gentle", 0.5 + 0.2 * fade, 0.6, 90 * fade + 20, 0.5 * fade


def render_source_clip():
    import cv2

    if SRC_CLIP.exists():
        return str(SRC_CLIP)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(SRC_CLIP), fourcc, FPS, (W, H))
    gx, gy = np.meshgrid(
        np.linspace(0, 1, W, dtype=np.float32),
        np.linspace(0, 1, H, dtype=np.float32),
    )
    rng = np.random.default_rng(42)
    bg = np.stack(
        [40 + 30 * (1 - gy), 30 + 20 * gx, 60 + 40 * gy], axis=-1
    ).astype(np.uint8)  # quiet cool room: teal-blue gradient
    for i in range(N):
        t = i / FPS
        mode, cx, cy, rad, bright = movement_arc(t)
        frame = bg.copy()
        if mode != "still":
            d = np.hypot(gx - cx, gy - cy)
            blob = np.exp(-((d * W / max(rad * 2, 1)) ** 2)) * bright
            # a vertical soft figure: stretch the blob 2.2x vertically
            blob = np.roll(blob, 0, axis=1)
            blob_v = cv2.resize(
                blob, (W, H // 2), interpolation=cv2.INTER_AREA
            )
            blob_v = cv2.resize(blob_v, (W, H), interpolation=cv2.INTER_LINEAR)
            warm = np.stack([blob_v * 255, blob_v * 150, blob_v * 60], axis=-1)
            frame = np.clip(
                frame.astype(np.float32) + warm, 0, 255
            ).astype(np.uint8)
        # sensor noise: +/-2 levels (the noise floor must eat this)
        frame = np.clip(
            frame.astype(np.int16) + rng.integers(-2, 3, frame.shape),
            0, 255,
        ).astype(np.uint8)
        writer.write(frame[:, :, ::-1])
    writer.release()
    print(f"source clip: {SRC_CLIP}")
    return str(SRC_CLIP)


def run_installation(clip_path):
    from lunar_tools_art.manager import LunarToolsArtManager
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "whispers_proto", ROOT / "prototypes" / "whispers.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    mgr = LunarToolsArtManager()
    assert mgr.renderer.backend == "opencv", mgr.renderer.backend

    w = mod.Whispers(
        mgr,
        duration=DURATION,
        video_path=clip_path,
        record_path=str(RAW),
        whisper_gap_s=99.0,   # procedural texture only in this demo
        seed=42,
    )
    w._show_hud = True

    frame_times = []
    phase_log = []   # (t, mode_expected, gesture, energy, particles)
    audio_log = []   # (offset_s, stereo samples) — the REAL played clips

    # tee the real playback: wrap sound_player so every clip the
    # installation actually plays is captured with its wall-clock offset
    real_play = mgr.sound_player.play_audio
    run_start = [None]

    def tee_play(data, samplerate=None, blocking=None):
        if run_start[0] is not None:
            audio_log.append((time.time() - run_start[0], np.array(data)))
        return real_play(data, samplerate=samplerate, blocking=blocking)

    mgr.sound_player.play_audio = tee_play

    real_render = w.renderer.render

    def timed_render(canvas):
        t0 = time.perf_counter()
        real_render(canvas)
        frame_times.append(time.perf_counter() - t0)

    w.renderer.render = timed_render

    # phase sampling from inside the loop
    orig_poll = w._poll_controls
    last_sample = [0.0]

    def sampling_poll():
        orig_poll()
        now = time.time() - w._start_t
        if now - last_sample[0] >= 0.5:
            last_sample[0] = now
            mode, *_ = movement_arc(now)
            phase_log.append(
                {
                    "t": round(now, 2),
                    "arc_mode": mode,
                    "gesture": w._gesture_now,
                    "energy": round(w.motion_energy, 2),
                    "particles": int(w._n),
                    "bursts": w.bursts_fired,
                }
            )

    w._poll_controls = sampling_poll

    # note when the recorder actually opened (video timeline t=0)
    writer_open = [None]
    real_maybe_open = w._maybe_open_writer

    def timed_maybe_open(canvas):
        real_maybe_open(canvas)
        if writer_open[0] is None and w._writer is not None:
            writer_open[0] = time.time() - w._start_t

    w._maybe_open_writer = timed_maybe_open

    t0 = time.time()
    run_start[0] = t0
    w.run()
    wall = time.time() - t0
    video_offset = writer_open[0] if writer_open[0] is not None else 0.0
    return w, wall, frame_times, phase_log, audio_log, video_offset


def mux(audio_log, wall_seconds, video_offset):
    """Lay the actually-played texture clips onto a silence bed at their
    wall-clock offsets (the run was the audio performer, not this mux)."""
    import soundfile as sf

    SR = 22050
    total = int(wall_seconds * SR)
    track = np.zeros((total, 2), dtype=np.float32)
    for offset, data in audio_log:
        data = np.asarray(data, dtype=np.float32)
        if data.ndim == 1:                    # mono clip -> duplicate to stereo
            data = np.stack([data, data], axis=1)
        i0 = int((offset - video_offset) * SR)   # video timeline starts later
        if i0 < 0:
            data = data[-i0:]                    # clip the pre-video tail
            i0 = 0
        i1 = min(total, i0 + data.shape[0])
        if i1 > i0:
            track[i0:i1] += data[: i1 - i0]
    peak = float(np.abs(track).max())
    if peak > 0.9:
        track *= 0.9 / peak
    sf.write(WAV, track, SR, subtype="PCM_16")

    r = subprocess.run(
        ["ffmpeg", "-y", "-i", str(RAW), "-i", str(WAV),
         "-c:v", "libx264", "-preset", "medium", "-crf", "23",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
         "-shortest", str(FINAL)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(r.stderr[-800:])
        return False
    return True


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    clip = render_source_clip()
    w, wall, frame_times, phase_log, audio_log, video_offset = run_installation(clip)

    ft = np.array(frame_times) * 1000.0
    evidence = {
        "run": "whispers-demo-v2",
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "wall_seconds": round(wall, 2),
        "frames": w.frame_count,
        "fps_measured": round(w.fps, 1),
        "frame_time_ms": {
            "p50": round(float(np.percentile(ft, 50)), 2),
            "p95": round(float(np.percentile(ft, 95)), 2),
            "mean": round(float(ft.mean()), 2),
            "max": round(float(ft.max()), 2),
        },
        "pipeline_note": (
            "frame times measure the render call (cv2 imshow+waitKey pump "
            "included) in the windowed run; the offline pipeline "
            "(motion+spawn+update+draw) measures 4.5 ms p-mean at cap — see "
            "verification.json"
        ),
        "source_kind": w.source_kind,
        "preset": w.preset_name,
        "particles_end": int(w._n),
        "bursts_fired": w.bursts_fired,
        "texture_clips_played": w.texture_clips_played,
        "audio_clips_captured": len(audio_log),
        "whispers_tts": [w.whispers_attempted, w.whispers_spoken],
        "last_fatal_error": w.last_fatal_error,
        "phase_log": phase_log,
    }
    (EVIDENCE).write_text(json.dumps(evidence, indent=2))

    ok = mux(audio_log, wall, video_offset)
    if ok:
        evidence["demo_video"] = str(FINAL)
        (EVIDENCE).write_text(json.dumps(evidence, indent=2))

    # preview frame from the intense phase
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", "22", "-i", str(FINAL),
         "-frames:v", "1", str(OUT / "whispers_demo_v2_preview.png")],
        check=True,
    )
    print(json.dumps({k: v for k, v in evidence.items()
                      if k not in ("phase_log",)}, indent=2))
    ok = ok and w.frame_count > 200 and w.last_fatal_error is None
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())