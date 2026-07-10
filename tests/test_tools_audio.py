import sys
import types

import numpy as np
import pytest


class _FakePortAudioError(Exception):
    pass


def _fake_sd(monkeypatch, devices=({"name": "Fake Mic", "max_input_channels": 1},)):
    calls = {}
    sd = types.SimpleNamespace(
        rec=lambda frames, samplerate, channels: np.zeros(
            (frames, channels), dtype="float32"
        ),
        wait=lambda: None,
        play=lambda data, samplerate, blocking=False: calls.setdefault(
            "played", (data, samplerate)
        ),
        query_devices=lambda: list(devices),
        PortAudioError=_FakePortAudioError,
    )
    monkeypatch.setitem(sys.modules, "sounddevice", sd)
    return sd, calls


def test_record_writes_wav(tmp_path, monkeypatch):
    _fake_sd(monkeypatch)
    from lunar_tools_art.tools.audio import AudioRecorder

    path = AudioRecorder(output_dir=str(tmp_path)).record(duration=0.1)
    import soundfile as sf

    data, sr = sf.read(path)
    assert path.endswith(".wav") and sr == 16000


def test_start_stop_roundtrip(tmp_path, monkeypatch):
    _fake_sd(monkeypatch)
    from lunar_tools_art.tools.audio import AudioRecorder

    rec = AudioRecorder(output_dir=str(tmp_path))
    target = str(tmp_path / "take.wav")
    rec.start_recording(target)
    out = rec.stop_recording()
    assert out == target


def test_no_device_raises_then_degrades(tmp_path, monkeypatch, caplog):
    _fake_sd(monkeypatch, devices=())
    from lunar_tools_art.exceptions import HardwareUnavailableError
    from lunar_tools_art.tools.audio import AudioRecorder

    rec = AudioRecorder(output_dir=str(tmp_path))
    with pytest.raises(HardwareUnavailableError):
        rec.record(duration=0.1)
    assert rec.record(duration=0.1) is None  # degraded: warn-once, no-op


def test_play_sound_alias(tmp_path, monkeypatch):
    sd, calls = _fake_sd(monkeypatch)
    import soundfile as sf

    wav = str(tmp_path / "s.wav")
    sf.write(wav, np.zeros(160, dtype="float32"), 16000)

    from lunar_tools_art.tools.audio import SoundPlayer

    SoundPlayer().play_sound(wav)
    assert "played" in calls


def test_play_audio_raises_then_degrades(monkeypatch):
    from lunar_tools_art.exceptions import HardwareUnavailableError
    from lunar_tools_art.tools.audio import SoundPlayer

    def _raise_play(data, samplerate, blocking=False):
        raise _FakePortAudioError("no output device")

    sd = types.SimpleNamespace(
        play=_raise_play,
        PortAudioError=_FakePortAudioError,
    )
    monkeypatch.setitem(sys.modules, "sounddevice", sd)

    player = SoundPlayer()
    data = np.zeros(160, dtype="float32")

    with pytest.raises(HardwareUnavailableError):
        player.play_audio(data, samplerate=16000)

    assert (
        player.play_audio(data, samplerate=16000) is None
    )  # degraded: warn-once, no-op
