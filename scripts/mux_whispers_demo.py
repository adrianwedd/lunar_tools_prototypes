#!/usr/bin/env python
"""Mux the Whispers demo: demo_raw.mp4 + whisper clips -> whispers_demo.mp4.

Whisper offsets come from demo_evidence.json (wall-clock seconds from run
start); the recorder opened ~3 s in (after the fps warm-up window), so
each offset shifts by the recorder's actual start time, recovered from the
video duration vs wall time.
"""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "outputs/whispers")
EV = OUT / "demo_evidence.json"
RAW = OUT / "demo_raw.mp4"
WAV = OUT / "demo_whispers.wav"
FINAL = OUT / "whispers_demo.mp4"
HUSH = 0.22
SR = 24000
WARMUP_S = 3.0  # recorder opens after the fps warm-up window


def main():
    ev = json.loads(EV.read_text())

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(RAW)],
        capture_output=True, text=True, check=True,
    )
    video_dur = float(probe.stdout.strip())
    wall = ev["wall_seconds"]

    # timeline: video covers wall [WARMUP_S, WARMUP_S + video_dur)
    total = int(video_dur * SR)
    track = np.zeros(total, dtype=np.float32)
    placed = 0
    for e in ev["whisper_events"]:
        if not e.get("path") or not e.get("played"):
            continue
        data, sr = sf.read(e["path"])
        if data.ndim > 1:
            data = data.mean(axis=1)
        data = np.asarray(data, dtype=np.float32) * HUSH
        t_in_video = e["offset_s"] - WARMUP_S
        if t_in_video < 0:
            continue
        i0 = int(t_in_video * SR)
        i1 = min(total, i0 + len(data))
        if i1 <= i0:
            continue
        track[i0:i1] += data[: i1 - i0]
        placed += 1
        print(f"placed @ {t_in_video:6.2f}s: {e['text'][:40]}")
    sf.write(WAV, track, SR, subtype="PCM_16")
    print(f"{placed} whisper clips placed; track {len(track)/SR:.1f}s")

    r = subprocess.run(
        ["ffmpeg", "-y", "-i", str(RAW), "-i", str(WAV),
         "-c:v", "libx264", "-preset", "medium", "-crf", "23",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
         "-shortest", str(FINAL)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(r.stderr[-1200:])
        return 1
    print(f"wrote {FINAL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())