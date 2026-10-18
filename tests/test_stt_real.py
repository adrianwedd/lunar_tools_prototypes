"""Opt-in real STT check (no microphone, no network once the model is cached).

Run:
  LUNAR_REAL_STT=1 LUNAR_HEADLESS=1 env -u PYTHONPATH env/bin/python \
      -m pytest -q tests/test_stt_real.py

The fixture is a local `say` rendering of a public-domain pangram, committed
under tests/fixtures. It contains no personal or visitor audio.
"""

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("LUNAR_REAL_STT") != "1",
    reason="set LUNAR_REAL_STT=1 to run real whisper transcription",
)

FIXTURE = Path(__file__).parent / "fixtures" / "speech_quick_brown_fox.wav"


def test_fixture_exists_and_is_speech_sized():
    assert FIXTURE.exists(), "committed WAV fixture missing"
    assert FIXTURE.stat().st_size > 10_000


def test_mlx_whisper_transcribes_the_fixture():
    from src.lunar_tools_art.tools.stt import Speech2Text, Transcription

    stt = Speech2Text()
    assert stt.backend == "mlx-whisper"

    result = stt.transcribe(str(FIXTURE))

    assert isinstance(result, Transcription)
    assert "quick brown fox" in str(result).lower()
    assert result.language == "en"
    assert result.confidence > 0.3
