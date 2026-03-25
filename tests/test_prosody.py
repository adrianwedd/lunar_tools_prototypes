# tests/test_prosody.py
import numpy as np

from src.lunar_tools_art.prosody import ProsodyAnalyzer, ProsodyResult


def test_prosody_result_fields():
    r = ProsodyResult(
        pitch_mean=200.0,
        pitch_variance=15.0,
        energy_rms=0.5,
        pace_wps=0.0,
        pauses=[],
        spectral_centroid=1500.0,
        emotion_tag="neutral",
    )
    assert r.pitch_mean == 200.0
    assert r.emotion_tag == "neutral"


def test_analyze_sine_wave():
    """A pure 220Hz sine wave should have pitch_mean near 220."""
    sr = 22050
    duration = 2.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    audio = 0.5 * np.sin(2 * np.pi * 220 * t).astype(np.float32)

    analyzer = ProsodyAnalyzer()
    result = analyzer.analyze(audio, sr)

    assert isinstance(result, ProsodyResult)
    assert 180 < result.pitch_mean < 260  # near 220Hz
    assert result.energy_rms > 0.0
    assert result.spectral_centroid > 0.0


def test_analyze_silence():
    """Silent audio should produce low energy and neutral emotion."""
    sr = 22050
    audio = np.zeros(sr * 2, dtype=np.float32)

    analyzer = ProsodyAnalyzer()
    result = analyzer.analyze(audio, sr)

    assert result.energy_rms < 0.01
    assert result.emotion_tag == "neutral"


def test_emotion_tag_from_prosody():
    """High energy + high pitch variance should produce a string tag."""
    sr = 22050
    rng = np.random.default_rng(42)
    audio = (rng.random(sr * 2) * 2 - 1).astype(np.float32) * 0.8

    analyzer = ProsodyAnalyzer()
    result = analyzer.analyze(audio, sr)
    assert isinstance(result.emotion_tag, str)
