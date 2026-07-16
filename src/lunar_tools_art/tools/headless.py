"""Deterministic fake tool implementations used when LUNAR_HEADLESS=1.

These fakes exist so unit tests (and CI) can exercise the manager/prototype
wiring without touching real hardware (camera, audio, MIDI, GL renderer) or
the network. They match the real classes' constructor/method signatures
closely enough for smoke tests, and return deterministic values.
"""

import os

import numpy as np


def headless_active() -> bool:
    """True when LUNAR_HEADLESS=1 (or any truthy value) is set in the env."""
    return os.environ.get("LUNAR_HEADLESS", "").strip() not in (
        "",
        "0",
        "false",
        "False",
    )


class FakeRenderer:
    def __init__(self, *args, **kwargs):
        self.width = kwargs.get("width")
        self.height = kwargs.get("height")

    def render(self, *args, **kwargs):
        return None

    def set_size(self, width, height):
        self.width = width
        self.height = height


class FakeWebCam:
    def __init__(self, *args, **kwargs):
        pass

    def get_img(self, *args, **kwargs):
        return np.zeros((480, 640, 3), dtype=np.uint8)


class FakeAudioRecorder:
    """Mirrors the real AudioRecorder contract: start_recording() accepts an
    optional output path, stop_recording() writes a (tiny, silent) valid WAV
    and returns its path."""

    def __init__(self, *args, **kwargs):
        self._active_path = None

    def start_recording(self, file_path=None, *args, **kwargs):
        import tempfile

        if file_path is None:
            fd, file_path = tempfile.mkstemp(suffix=".wav", prefix="fake-rec-")
            os.close(fd)
        self._active_path = file_path
        return None

    def stop_recording(self, *args, **kwargs):
        if self._active_path is None:
            return None
        import wave

        path = self._active_path
        self._active_path = None
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"\x00\x00" * 1600)  # 0.1s of silence
        return path

    def record(self, duration, file_path=None):
        """Mirrors the real blocking record(duration) -> WAV path."""
        self.start_recording(file_path)
        return self.stop_recording()


class FakeSoundPlayer:
    def __init__(self, *args, **kwargs):
        pass

    def play_sound(self, *args, **kwargs):
        return None

    def play_audio(self, *args, **kwargs):
        return None

    def stop_sound(self, *args, **kwargs):
        return None


class FakeKeyboardInput:
    def __init__(self, *args, **kwargs):
        pass

    def is_key_pressed(self, *args, **kwargs):
        return False

    def get(self, *args, **kwargs):
        return None


class FakeMidiInput:
    def __init__(self, *args, **kwargs):
        pass

    def get_latest_message(self, *args, **kwargs):
        return None

    def get(self, *args, **kwargs):
        return 0.0


class FakeSpeech2Text:
    def __init__(self, *args, **kwargs):
        pass

    def transcribe(self, path_or_array=None, *, file_path=None, duration=None):
        # Mirrors the real Speech2Text signature so headless tests catch
        # call-site drift instead of silently accepting anything.
        from .stt import Transcription

        if path_or_array is None and file_path is None and duration is None:
            raise TypeError(
                "transcribe() needs an audio path/array, file_path=, or duration="
            )
        return Transcription("hello world", confidence=1.0, language="en")


from .tts import Text2Speech as _Text2Speech  # noqa: E402


class FakeText2Speech(_Text2Speech):
    """Mirrors the Text2Speech adapter contract: generate(text, voice=None)
    writes a (tiny, silent) valid WAV and returns its path. Subclasses the
    real adapter so isinstance checks hold, but never touches a VoiceClient."""

    def __init__(self, *args, **kwargs):
        pass

    def generate(self, text, voice=None, **kwargs):
        import tempfile
        import wave

        fd, path = tempfile.mkstemp(suffix=".wav", prefix="fake-tts-")
        os.close(fd)
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"\x00\x00" * 1600)  # 0.1s of silence
        return path


class FakeZMQPairEndpoint:
    """No-op stand-in for ZMQPairEndpoint: no socket is ever opened, so
    headless Manager() construction can't bind ports or require pyzmq."""

    def __init__(self, bind=True, address="tcp://127.0.0.1:5871"):
        from urllib.parse import urlparse

        self.address = address
        parsed = urlparse(address)
        self.ip = parsed.hostname
        self.port = parsed.port

    def send(self, message):
        return None

    def send_img(self, img):
        return None

    def receive(self, timeout_ms=0):
        return None

    def receive_img(self, timeout_ms=0):
        return None

    def get_messages(self):
        return []

    def close(self):
        return None
