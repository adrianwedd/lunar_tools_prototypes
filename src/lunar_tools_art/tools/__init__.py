"""Tool resolution: real hardware/cloud classes, swapped for deterministic
fakes when LUNAR_HEADLESS=1 (see headless.py).
"""

from . import headless as _hl
from ._legacy_cloud import (  # noqa: F401
    SDXL_LCM,
    SDXL_TURBO,
    Dalle3ImageGenerator,
    FluxImageGenerator,
    Text2SpeechOpenAI,
)
from .audio import AudioRecorder, SoundPlayer  # noqa: F401
from .camera import WebCam  # noqa: F401
from .display import Renderer  # noqa: F401
from .input import KeyboardInput, MidiInput  # noqa: F401
from .net import ZMQPairEndpoint  # noqa: F401
from .stt import Speech2Text, Transcription  # noqa: F401

_FAKES = {
    "Renderer": _hl.FakeRenderer,
    "WebCam": _hl.FakeWebCam,
    "AudioRecorder": _hl.FakeAudioRecorder,
    "SoundPlayer": _hl.FakeSoundPlayer,
    "KeyboardInput": _hl.FakeKeyboardInput,
    "MidiInput": _hl.FakeMidiInput,
    "Speech2Text": _hl.FakeSpeech2Text,
}


def resolve(name: str):
    """Return the fake class in headless mode, else the real one."""
    if _hl.headless_active() and name in _FAKES:
        return _FAKES[name]
    return globals()[name]
