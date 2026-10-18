#!/usr/bin/env python
"""Produce the Whispers demonstration video (final, performance-scripted).

A real windowed run of the real implementation: motion from the recorded
reference clip, particles, whispers from the live Afterwords server, HUD
on, and a scripted performance that exercises the interactive behaviours
(hud, motion overlay, aura clear, forced whisper) through the exact
functions the keyboard controls call — because the Studio session has no
Accessibility trust, genuine OS keystrokes cannot be injected here (the
key path is verified by the headless edge-trigger tests and remains
available to a human at the window).

Timeline (40 s):
   0-8 s   aura builds from the clip's motion; HUD on from the start
   8 s     motion overlay on (see the differencer's view)
  13 s     overlay off; whisper forced; aura keeps growing
  20 s     aura cleared; the room begins again
  27 s     whisper forced again
  33 s     HUD off; the piece runs quiet
  40 s     duration exit

Outputs: outputs/whispers/whispers_demo.mp4 (muxed, H.264+AAC),
demo_evidence.json (includes the performance timeline).
"""

import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT = ROOT / "outputs" / "whispers"
CLIP = ROOT / "outputs" / "glitch_lab" / "synthetic_reference_720p.mp4"
VOICE = "galadriel"
DURATION_S = 40.0

TIMELINE = [
    (8.0, "overlay_on"),
    (13.0, "overlay_off"),
    (13.5, "whisper"),
    (20.0, "clear"),
    (27.0, "whisper"),
    (33.0, "hud_off"),
]


def main():
    from lunar_tools_art.manager import LunarToolsArtManager
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "whispers_proto", ROOT / "prototypes" / "whispers.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    mgr = LunarToolsArtManager()
    assert mgr.renderer.backend == "opencv", mgr.renderer.backend
    assert mgr.text2speech is not None, "Afterwords TTS unavailable"

    w = mod.Whispers(
        mgr,
        duration=DURATION_S,
        video_path=str(CLIP),
        voice=VOICE,
        record_path=str(OUT / "demo_raw.mp4"),
        whisper_gap_s=4.0,
        seed=42,
    )
    w._show_hud = True

    performed = []

    def perform():
        t0 = time.time()
        for at, action in TIMELINE:
            wait = t0 + at - time.time()
            if wait > 0:
                time.sleep(wait)
            before = int(w._n)
            if action == "overlay_on":
                w._show_motion = True
            elif action == "overlay_off":
                w._show_motion = False
            elif action == "whisper":
                w._force_whisper()
            elif action == "clear":
                w._clear_aura()
            elif action == "hud_off":
                w._show_hud = False
            performed.append(
                {
                    "t": at,
                    "action": action,
                    "particles_before": before,
                    "particles_after": int(w._n),
                }
            )

    threading.Thread(target=perform, daemon=True).start()

    t0 = time.time()
    w.run()
    wall = time.time() - t0

    deadline = time.time() + 30
    while time.time() < deadline and w.whispers_spoken < 2:
        time.sleep(0.2)

    events = [e.as_dict() for e in w.whisper_events]
    import soundfile as sf

    for e in events:
        if e["path"]:
            try:
                data, sr = sf.read(e["path"])
                e["duration_s"] = round(len(data) / sr, 2)
            except Exception:
                e["duration_s"] = None
        e["offset_s"] = round(e.pop("t") - t0, 2)

    evidence = {
        "run": "windowed-demo-final",
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "wall_seconds": round(wall, 2),
        "frames": w.frame_count,
        "fps_measured": round(w.fps, 1),
        "source_kind": w.source_kind,
        "source_detail": w.source_detail,
        "particles_alive_end": w._n,
        "whispers_attempted": w.whispers_attempted,
        "whispers_spoken": w.whispers_spoken,
        "performance_timeline": performed,
        "whisper_events": events,
        "last_fatal_error": w.last_fatal_error,
        "note": (
            "state changes in this demo are performance-scripted through the "
            "same functions the keyboard controls call; this session cannot "
            "inject genuine OS keystrokes (no Accessibility trust). Key "
            "handling is verified headlessly in tests/test_whispers.py."
        ),
    }
    (OUT / "demo_evidence.json").write_text(json.dumps(evidence, indent=2))
    print(json.dumps(evidence, indent=2))
    ok = (
        w.frame_count > 100
        and w.last_fatal_error is None
        and w.whispers_spoken >= 1
        and any(p["action"] == "clear" and p["particles_before"] > 0
                for p in performed)
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())