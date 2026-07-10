"""Real pynput-backed keyboard input and mido/python-rtmidi MIDI input.

Both ``pynput`` and ``mido`` are imported lazily inside methods so importing
this module never touches OS input hooks or MIDI backends, and so tests can
inject fakes (a ``listener_cls`` for keyboard, ``sys.modules["mido"]`` for
MIDI) before real imports happen.
"""

import logging

logger = logging.getLogger(__name__)


class KeyboardInput:
    """Tracks pressed keys via a pynput listener, or pyglet key events.

    When ``window`` (a pyglet window, wired in Task 6) is passed, hooks the
    window's key press/release handlers instead of starting a pynput
    listener. ``listener_cls`` allows tests to inject a fake listener.
    """

    def __init__(self, window=None, listener_cls=None):
        self._pressed = set()
        self._last_key = None
        self._window = window
        self._listener = None

        if window is not None:
            self._hook_pyglet(window)
        else:
            if listener_cls is None:
                from pynput import keyboard

                listener_cls = keyboard.Listener
            self._listener = listener_cls(
                on_press=self._on_press, on_release=self._on_release
            )
            self._listener.start()

    @staticmethod
    def _key_str(key):
        char = getattr(key, "char", None)
        if char:
            return char
        name = getattr(key, "name", None)
        if name:
            return name
        return str(key)

    def _on_press(self, key):
        k = self._key_str(key)
        self._pressed.add(k)
        self._last_key = k

    def _on_release(self, key):
        k = self._key_str(key)
        self._pressed.discard(k)

    def _hook_pyglet(self, window):
        window.push_handlers(
            on_key_press=self._pyglet_press, on_key_release=self._pyglet_release
        )

    def _pyglet_press(self, symbol, modifiers):
        import pyglet

        k = pyglet.window.key.symbol_string(symbol).lower()
        self._pressed.add(k)
        self._last_key = k

    def _pyglet_release(self, symbol, modifiers):
        import pyglet

        k = pyglet.window.key.symbol_string(symbol).lower()
        self._pressed.discard(k)

    def is_key_pressed(self, key: str) -> bool:
        return key in self._pressed

    def get(self):
        k = self._last_key
        self._last_key = None
        return k

    def close(self):
        if self._listener is not None:
            self._listener.stop()


class MidiInput:
    """Reads CC values from the first available MIDI input port."""

    def __init__(self):
        self._degraded = False
        self._warned = False
        self._port = None
        self._last_message = None
        self._cc_values = {}
        self._try_open()

    def _try_open(self):
        import mido

        try:
            names = mido.get_input_names()
        except Exception:
            names = []

        if not names:
            self._degraded = True
            return

        try:
            self._port = mido.open_input(names[0])
        except Exception as e:
            self._degraded = True
            logger.debug(f"Failed to open MIDI port: {e}")

    def _warn_once(self):
        if not self._warned:
            logger.warning("No MIDI input device available; MidiInput degraded.")
            self._warned = True

    def _poll(self):
        if self._degraded or self._port is None:
            return
        for msg in self._port.iter_pending():
            self._last_message = msg
            if msg.type == "control_change":
                self._cc_values[msg.control] = msg.value / 127.0

    def get_latest_message(self):
        if self._degraded:
            self._warn_once()
            return None
        self._poll()
        return self._last_message

    def get(self, control: int, default: float = 0.0) -> float:
        if self._degraded:
            self._warn_once()
            return default
        self._poll()
        return self._cc_values.get(control, default)

    def close(self):
        if self._port is not None:
            self._port.close()
            self._port = None
