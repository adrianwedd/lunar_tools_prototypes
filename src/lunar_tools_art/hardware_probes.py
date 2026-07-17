"""Device-presence probes, each in a short-lived subprocess with a hard
timeout — native audio/video code can hang or segfault below Python, and
in-process try/except is not containment. Probes print a one-line summary
on success and exit 0; any other outcome is a fail with a classification.
"""

import subprocess  # nosec B404 - probes run fixed snippets via sys.executable
import sys

from . import doctor
from .doctor import CheckResult


def probe_in_subprocess(snippet, name, ok_detail, fix, timeout=5.0):
    try:
        proc = subprocess.run(  # nosec B603 - argv list, no shell, our snippet
            [sys.executable, "-c", snippet],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            name,
            "fail",
            f"probe timed out after {timeout:.0f}s (device busy or driver hang)",
            fix,
        )
    if proc.returncode == 0:
        detail = proc.stdout.strip() or ok_detail
        return CheckResult(name, "pass", detail, None)
    err = (proc.stderr or "").strip().splitlines()
    last = err[-1] if err else f"exit code {proc.returncode}"
    if "ModuleNotFoundError" in last or "ImportError" in last:
        return CheckResult(name, "fail", last, fix)
    if "permission" in last.lower() or "denied" in last.lower():
        return CheckResult(
            name,
            "fail",
            f"permission denied: {last}",
            "grant access in System Settings → Privacy & Security",
        )
    return CheckResult(name, "fail", last, fix)


_HW_FIX = "pip install -e '.[hw]'"


def probe_mic():
    return probe_in_subprocess(
        "import sounddevice as sd;"
        "n=len([d for d in sd.query_devices() if d['max_input_channels']>0]);"
        "assert n, 'no input devices';print(f'{n} input device(s)')",
        "mic",
        "input device present",
        _HW_FIX,
    )


def probe_audio_out():
    return probe_in_subprocess(
        "import sounddevice as sd;"
        "n=len([d for d in sd.query_devices() if d['max_output_channels']>0]);"
        "assert n, 'no output devices';print(f'{n} output device(s)')",
        "audio-out",
        "output device present",
        _HW_FIX,
    )


def probe_camera():
    return probe_in_subprocess(
        "import cv2;c=cv2.VideoCapture(0);ok=c.isOpened();c.release();"
        "assert ok, 'no camera at index 0';print('camera 0 opens')",
        "camera",
        "camera present",
        "pip install -e '.[vision]' and check camera permissions",
        timeout=8.0,
    )


def probe_renderer():
    return probe_in_subprocess(
        "import pyglet;"
        "w=pyglet.window.Window(width=64,height=64,visible=False);"
        "w.close();print('display available')",
        "renderer",
        "display available",
        _HW_FIX,
    )


def probe_midi():
    return probe_in_subprocess(
        "import mido;names=mido.get_input_names();"
        "print(f'{len(names)} MIDI input(s)' if names "
        "else exit('no MIDI inputs'))",
        "midi",
        "MIDI device present",
        _HW_FIX + " (and connect a MIDI controller)",
    )


doctor.DEFAULT_PROBES.update(
    {
        "mic": probe_mic,
        "audio-out": probe_audio_out,
        "camera": probe_camera,
        "renderer": probe_renderer,
        "midi": probe_midi,
    }
)
