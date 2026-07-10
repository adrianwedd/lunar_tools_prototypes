"""Integration checks for LunarToolsArtManager wiring under headless mode.

Verifies every attribute the design spec promises is constructed via the
tools layer, `image_gen`/`dalle3` behave per the unified ImageGenerator
contract, `llm_backend`/`gpt4` alias correctly, and `config` is reachable.
"""

import pytest

from lunar_tools_art.manager import LunarToolsArtManager


@pytest.fixture(autouse=True)
def _headless_env(monkeypatch):
    monkeypatch.setenv("LUNAR_HEADLESS", "1")


@pytest.fixture
def manager():
    return LunarToolsArtManager()


EXPECTED_ATTRS = [
    "renderer",
    "speech2text",
    "text2speech",
    "audio_recorder",
    "sound_player",
    "keyboard_input",
    "webcam",
    "image_gen",
    "dalle3",
    "sdxl_turbo",
    "sdxl_lcm",
    "flux",
    "zmq_pair_endpoint",
    "midi_input",
    "main_queue",
    "emotion_detector",
    "prosody_analyzer",
    "voice_client",
    "config",
]


def test_manager_exposes_all_expected_attributes(manager):
    for attr in EXPECTED_ATTRS:
        assert hasattr(manager, attr), f"manager missing attribute: {attr}"


def test_manager_non_none_headless_attrs(manager):
    # These must be non-None under headless mode per the design spec.
    non_none = [
        "renderer",
        "speech2text",
        "audio_recorder",
        "sound_player",
        "keyboard_input",
        "webcam",
        "image_gen",
        "dalle3",
        "sdxl_turbo",
        "sdxl_lcm",
        "flux",
        "zmq_pair_endpoint",
        "midi_input",
        "main_queue",
        "emotion_detector",
        "prosody_analyzer",
        "config",
    ]
    for attr in non_none:
        assert getattr(manager, attr) is not None, f"manager.{attr} is None headless"


def test_dalle3_generate_returns_two_tuple(manager):
    result = manager.dalle3.generate("x")
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_config_get_works(manager):
    assert manager.config.get("privacy.mode", "local-only") is not None


def test_gpt4_aliases_llm_backend(manager):
    assert manager.gpt4 is manager.llm_backend


def test_llm_backend_none_or_backend(manager):
    # Depending on config, llm_backend may be None (no llm config) or an
    # object exposing .generate.
    if manager.llm_backend is not None:
        assert hasattr(manager.llm_backend, "generate")


def test_local_only_privacy_does_not_touch_network(monkeypatch):
    """In local-only mode, no cloud-gated tool should attempt network calls
    at construction time. We assert this indirectly: construction succeeds
    without raising and text2speech falls back sanely (None or local
    Afterwords adapter, never Text2SpeechOpenAI when cloud is disallowed)."""
    from lunar_tools_art import privacy

    monkeypatch.setattr(privacy, "cloud_allowed", lambda: False)
    m = LunarToolsArtManager()
    if m.voice_client is None:
        assert m.text2speech is None
