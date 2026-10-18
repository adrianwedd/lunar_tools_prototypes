#!/usr/bin/env python
"""Windowed interactive-control verification for Whispers.

Runs the real Whispers in a real OpenCV window (RENDERER__BACKEND=opencv),
then — while it is running — sends genuine keystrokes to the focused window
via System Events (osascript) and records, from the running process itself,
whether each control actually changed the installation's behaviour:

  h       HUD toggles on (later off)
  m       motion overlay toggles on
  space   a forced whisper fires (TTS call + non-blocking playback)
  c       the aura clears (particle count drops to 0)

Writes outputs/whispers/interactive_evidence.json.
Exit 0 only if every control is confirmed from live state.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT = ROOT / "outputs" / "whispers"
CLIP = ROOT / "outputs" / "glitch_lab" / "synthetic_reference_720p.mp4"


def send_key(key):
    """Keystroke to the frontmost window (whispers must be focused)."""
    if key == "space":
        cmd = 'tell application "System Events" to keystroke " "'
    else:
        cmd = f'tell application "System Events" to keystroke "{key}"'
    r = subprocess.run(
        ["osascript", "-e", cmd], capture_output=True, text=True, timeout=10
    )
    return r.returncode == 0, r.stderr.strip()


def activate_window():
    # The OpenCV window belongs to this script's own process; keystrokes go
    # to the frontmost application, so bring our process forward first.
    subprocess.run(
        ["osascript", "-e",
         'tell application "System Events" to set frontmost of first process'
         ' whose unix id is ' + str(subprocess.Popen(['echo']).pid) + ' to true'],
        capture_output=True,
    )


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

    w = mod.Whispers(
        mgr,
        duration=60.0,
        video_path=str(CLIP),
        voice="galadriel",
        record_path=str(OUT / "interactive_demo.mp4"),
        seed=11,
    )

    import threading

    evidence = {"date": time.strftime("%Y-%m-%d %H:%M:%S"), "steps": []}

    def note(step, **kw):
        entry = {
            "step": step,
            "t": round(time.time() - t0, 1),
            "particles": int(w._n),
            "hud": bool(w._show_hud),
            "motion_overlay": bool(w._show_motion),
            "whispers_attempted": w.whispers_attempted,
            "whispers_spoken": w.whispers_spoken,
        }
        entry.update(kw)
        evidence["steps"].append(entry)
        print(json.dumps(entry))

    t0 = time.time()

    def script():
        """Drive the real UI with real keystrokes, sampling live state."""
        # let the aura build for ~10 s
        time.sleep(10.0)
        note("aura-building")

        ok, err = send_key("h")
        time.sleep(1.2)
        note("key h", sent=ok, err=err or None)

        ok, err = send_key("m")
        time.sleep(1.2)
        note("key m", sent=ok, err=err or None)

        ok, err = send_key("space")
        time.sleep(3.0)  # synthesis is async; give it time
        note("key space", sent=ok, err=err or None)

        ok, err = send_key("c")
        time.sleep(1.2)
        note("key c", sent=ok, err=err or None)

        ok, err = send_key("h")
        time.sleep(1.2)
        note("key h (off)", sent=ok, err=err or None)

        # done: quit through the real UI too
        ok, err = send_key("q")
        note("key q", sent=ok, err=err or None)

    threading.Thread(target=script, daemon=True).start()
    w.run()

    evidence["summary"] = {
        "frames": w.frame_count,
        "fps": round(w.fps, 1),
        "source_kind": w.source_kind,
        "whispers_attempted": w.whispers_attempted,
        "whispers_spoken": w.whispers_spoken,
        "last_fatal_error": w.last_fatal_error,
    }

    # verdict from recorded live state, not from hopes
    s = {e["step"]: e for e in evidence["steps"]}
    checks = {
        "hud_toggled_on": s["key h"]["hud"] is True,
        "hud_toggled_off": s["key h (off)"]["hud"] is False,
        "motion_overlay_on": s["key m"]["motion_overlay"] is True,
        "aura_cleared": s["key c"]["particles"] == 0,
        "whisper_fired": s["key space"]["whispers_attempted"]
        >= s["aura-building"]["whispers_attempted"] + 1,
        "whisper_spoken": w.whispers_spoken >= 1,
        "no_fatal": w.last_fatal_error is None,
        "q_quit": w._running is False,
    }
    evidence["checks"] = checks
    (OUT / "interactive_evidence.json").write_text(json.dumps(evidence, indent=2))
    print(json.dumps(checks, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())