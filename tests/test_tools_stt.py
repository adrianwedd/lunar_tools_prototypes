import sys
import types

import pytest


def _install_fake_mlx_whisper(monkeypatch, result=None, exc=None):
    def _transcribe(audio, path_or_hf_repo=None, **kwargs):
        if exc is not None:
            raise exc
        return result

    fake = types.SimpleNamespace(transcribe=_transcribe)
    monkeypatch.setitem(sys.modules, "mlx_whisper", fake)
    return fake


@pytest.fixture
def fake_mlx_whisper(monkeypatch):
    return _install_fake_mlx_whisper(
        monkeypatch,
        result={
            "text": " hi there",
            "language": "en",
            "segments": [{"avg_logprob": -0.2}],
        },
    )


@pytest.fixture
def fake_mlx_whisper_broken(monkeypatch):
    return _install_fake_mlx_whisper(monkeypatch, exc=RuntimeError("boom"))


def _set_backend(monkeypatch, backend):
    from lunar_tools_art.tools import stt

    monkeypatch.setattr(
        stt.config,
        "get",
        lambda key, default=None: backend if key == "whisper.backend" else default,
    )


def test_transcribe_returns_transcription(fake_mlx_whisper, monkeypatch):
    _set_backend(monkeypatch, "mlx-whisper")
    from lunar_tools_art.tools.stt import Speech2Text, Transcription

    result = Speech2Text().transcribe("x.wav")
    assert isinstance(result, Transcription)
    assert result.strip() == "hi there"  # legacy string usage
    assert 0 < result.confidence <= 1
    assert result.language == "en"


def test_inference_failure_raises(fake_mlx_whisper_broken, monkeypatch):
    _set_backend(monkeypatch, "mlx-whisper")
    from lunar_tools_art.exceptions import InferenceError
    from lunar_tools_art.tools.stt import Speech2Text

    with pytest.raises(InferenceError):
        Speech2Text().transcribe("x.wav")


def test_confidence_clamped_to_unit_interval(monkeypatch):
    _set_backend(monkeypatch, "mlx-whisper")
    _install_fake_mlx_whisper(
        monkeypatch,
        result={
            "text": "hello",
            "language": "en",
            "segments": [{"avg_logprob": 5.0}],  # exp(5) > 1
        },
    )
    from lunar_tools_art.tools.stt import Speech2Text

    result = Speech2Text().transcribe("x.wav")
    assert 0 < result.confidence <= 1


def test_transcription_str_subclass_construction():
    from lunar_tools_art.tools.stt import Transcription

    t = Transcription("hello world", confidence=0.9, language="en")
    assert t == "hello world"
    assert t.text == "hello world"
    assert t.confidence == 0.9
    assert t.language == "en"


def test_unknown_backend_raises_configuration_error(monkeypatch):
    _set_backend(monkeypatch, "bogus-backend")
    from lunar_tools_art.exceptions import ConfigurationError
    from lunar_tools_art.tools.stt import Speech2Text

    with pytest.raises(ConfigurationError):
        Speech2Text().transcribe("x.wav")
