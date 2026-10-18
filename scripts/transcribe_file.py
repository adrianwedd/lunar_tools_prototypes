#!/usr/bin/env python3
"""Transcribe an audio file with the local STT backend (no microphone).

Example:
  env -u PYTHONPATH ./env/bin/python scripts/transcribe_file.py \
      tests/fixtures/speech_quick_brown_fox.wav

Prints the transcript, language and confidence. The model is loaded from the
Hugging Face cache; the first mlx-whisper run downloads ~143 MB once.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("audio", help="path to a WAV/MP3 file")
    ap.add_argument("--backend", default=None, help="override whisper.backend")
    ap.add_argument("--model", default=None, help="override whisper.model")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    audio = Path(args.audio)
    if not audio.exists():
        print(f"no such file: {audio}", file=sys.stderr)
        return 2

    from src.lunar_tools_art.tools.stt import Speech2Text

    s = Speech2Text()
    if args.backend:
        s.backend = args.backend
    if args.model:
        s.model = args.model
    t0 = time.perf_counter()
    result = s.transcribe(str(audio))
    latency = time.perf_counter() - t0

    payload = {
        "audio": str(audio),
        "backend": s.backend,
        "model": s.model,
        "text": str(result),
        "language": result.language,
        "confidence": round(result.confidence, 4),
        "latency_s": round(latency, 3),
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"backend : {s.backend} / {s.model}")
        print(f"language: {result.language}  confidence: {result.confidence:.3f}")
        print(f"latency : {latency:.2f}s")
        print(f"text    : {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
