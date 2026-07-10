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
    def __init__(self, *args, **kwargs):
        pass

    def start_recording(self, *args, **kwargs):
        return None

    def stop_recording(self, *args, **kwargs):
        return None


class FakeSoundPlayer:
    def __init__(self, *args, **kwargs):
        pass

    def play_sound(self, *args, **kwargs):
        return None

    def play_audio(self, *args, **kwargs):
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

    def transcribe(self, *args, **kwargs):
        from .stt import Transcription

        return Transcription("hello world", confidence=1.0, language="en")
