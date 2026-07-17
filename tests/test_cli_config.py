import pytest

from lunar_tools_art.cli_config import ConfigParseError, parse_config_args
from lunar_tools_art.demo_registry import ConfigKnob


def test_repeatable_key_value():
    kwargs, _ = parse_config_args(["duration=5", "voice=galadriel"])
    assert kwargs == {"duration": 5, "voice": "galadriel"}


def test_legacy_comma_form_still_works():
    kwargs, _ = parse_config_args(["duration=5,rate=1.5"])
    assert kwargs == {"duration": 5, "rate": 1.5}


def test_tuple_value_survives_commas():
    kwargs, _ = parse_config_args(["window_size=(800,600),fps=30"])
    assert kwargs == {"window_size": (800, 600), "fps": 30}


def test_booleans():
    kwargs, _ = parse_config_args(["debug=true,fullscreen=False"])
    assert kwargs == {"debug": True, "fullscreen": False}


def test_entry_without_equals_is_rejected_loudly():
    with pytest.raises(ConfigParseError, match="oops"):
        parse_config_args(["duration=5,oops"])


def test_unknown_key_warns_when_knobs_declared():
    knobs = (ConfigKnob("duration", int, 5, "seconds"),)
    kwargs, warnings = parse_config_args(["duratoin=5"], knobs=knobs)
    assert "duratoin" in warnings[0]


def test_known_key_no_warning():
    knobs = (ConfigKnob("duration", int, 5, "seconds"),)
    _, warnings = parse_config_args(["duration=5"], knobs=knobs)
    assert warnings == []
