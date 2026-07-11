#!/usr/bin/env python3
"""On-machine smoke test for AudioRecorder/SoundPlayer.

Records 2 seconds of audio from the default input device, plays it back
through the default output device, and prints the recorded file path.

Run with real hardware attached (not under LUNAR_HEADLESS):

    python scripts/smoke_audio.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lunar_tools_art.tools.audio import AudioRecorder, SoundPlayer  # noqa: E402


def main():
    recorder = AudioRecorder()
    player = SoundPlayer()

    print("Recording 2 seconds of audio...")
    path = recorder.record(duration=2.0)
    print(f"Recorded to: {path}")

    print("Playing back...")
    player.play_audio(path, blocking=True)
    print("Done.")


if __name__ == "__main__":
    main()
