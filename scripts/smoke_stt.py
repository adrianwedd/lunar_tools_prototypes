#!/usr/bin/env python3
"""On-machine smoke test for Speech2Text.

Records 3 seconds of audio from the default input device and transcribes it,
printing the transcript and confidence.

Run with real hardware attached (not under LUNAR_HEADLESS):

    python scripts/smoke_stt.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lunar_tools_art.tools.audio import AudioRecorder  # noqa: E402
from lunar_tools_art.tools.stt import Speech2Text  # noqa: E402


def main():
    recorder = AudioRecorder()
    stt = Speech2Text()

    print("Recording 3 seconds of audio...")
    path = recorder.record(duration=3.0)
    print(f"Recorded to: {path}")

    print("Transcribing...")
    result = stt.transcribe(path)
    print(f"Transcript: {result!s}")
    print(f"Confidence: {result.confidence:.3f}")
    print(f"Language: {result.language}")


if __name__ == "__main__":
    main()
