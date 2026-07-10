import sys
import types


class _FakeKey:
    """Mimics pynput.keyboard.KeyCode / Key with a .char attribute."""

    def __init__(self, char):
        self.char = char


class _FakeListener:
    """Injected fake standing in for pynput.keyboard.Listener."""

    def __init__(self, on_press=None, on_release=None):
        self.on_press = on_press
        self.on_release = on_release
        self.started = False

    def start(self):
        self.started = True

    def stop(self):
        self.started = False


def test_keyboard_input_tracks_press_and_get():
    from lunar_tools_art.tools.input import KeyboardInput

    kb = KeyboardInput(listener_cls=_FakeListener)
    assert kb.is_key_pressed("q") is False

    kb._listener.on_press(_FakeKey("q"))

    assert kb.is_key_pressed("q") is True
    assert kb.get() == "q"


def test_midi_no_device_returns_default_and_warns_once(monkeypatch, caplog):
    mido = types.SimpleNamespace(get_input_names=lambda: [])
    monkeypatch.setitem(sys.modules, "mido", mido)

    from lunar_tools_art.tools.input import MidiInput

    midi = MidiInput()
    with caplog.at_level("WARNING"):
        assert midi.get(1, default=0.25) == 0.25
        assert midi.get(1, default=0.25) == 0.25

    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
