"""MIDI integer-CC contract for three prototypes (issue #32, part of #35).

The real ``MidiInput.get`` signature is ``get(control: int, default: float =
0.0) -> float`` returning a normalised 0..1 value. These prototypes used to
call it with control *names* and ``val_min``/``val_max`` kwargs, which raised
TypeError every frame on real hardware — and the headless fake swallowed it,
so the smoke tests never noticed.

The fake below deliberately implements only the real signature (so any kwargs
call raises TypeError), which is what makes these tests a contract test.

Device-free evidence only: scripted MIDI + a real ``MidiInput`` with no ports.
No physical MIDI hardware is involved.
"""

import importlib.util
import logging
import os
import time

import numpy as np
import pytest
from PIL import Image

from src.lunar_tools_art.tools.input import MidiInput

PROTOTYPES_DIR = os.path.join(os.path.dirname(__file__), "..", "prototypes")


def _load_prototype_module(filename, module_name):
    """Load a hyphenated-filename prototype from its path (same pattern as
    tests/test_lunar_tools_art.py)."""
    spec = importlib.util.spec_from_file_location(
        module_name, os.path.join(PROTOTYPES_DIR, filename)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# -- fakes ------------------------------------------------------------------


class ScriptedMidi:
    """Implements exactly the real MidiInput.get contract.

    Anything other than ``get(control: int, default=0.0)`` raises TypeError,
    so ``get("A0", val_min=0, val_max=6)`` fails here exactly as it does on
    real hardware.
    """

    def __init__(self, values=None):
        self.values = dict(values or {})
        self.calls = []

    def get(self, control, default=0.0):
        if not isinstance(control, int):
            raise AssertionError(f"non-integer CC requested: {control!r}")
        self.calls.append(control)
        return self.values.get(control, default)


class ScriptedKeyboard:
    def __init__(self, presses):
        self._presses = list(presses)
        self.polls = 0

    def is_key_pressed(self, key):
        self.polls += 1
        if self._presses:
            return self._presses.pop(0)
        return False


class FakeRenderer:
    """Records frames as numpy arrays; deterministic 64x64 canvas."""

    def __init__(self, width=64, height=64):
        self.width = width
        self.height = height
        self.frames = []

    def render(self, frame):
        self.frames.append(np.array(frame))


class FakeGenerator:
    """Writes a real PNG per call and returns (path, metadata)."""

    def __init__(self, directory, name="gen"):
        self.dir = directory
        self.name = name
        self.prompts = []
        self._n = 0

    def generate(self, prompt):
        self.prompts.append(prompt)
        self._n += 1
        color = (20 * self._n % 256, 40 * self._n % 256, 60 * self._n % 256)
        path = os.path.join(self.dir, f"{self.name}_{self._n}.png")
        Image.new("RGB", (64, 64), color=color).save(path)
        return str(path), {"seed": self._n}


class FakeSpeech:
    def __init__(self):
        self.spoken = []

    def generate(self, text):
        self.spoken.append(text)


class FakeManager:
    def __init__(self, midi, directory, renderer=None):
        self.logger = logging.getLogger("test_midi_prototypes")
        self.renderer = renderer or FakeRenderer()
        self.midi_input = midi
        self.keyboard_input = ScriptedKeyboard([])
        self.sdxl_lcm = FakeGenerator(directory, "mural")
        self.dalle3 = FakeGenerator(directory, "era")
        self.text2speech = FakeSpeech()


def _dynamic_visuals():
    from prototypes.dynamic_visuals import DynamicVisualizer

    return DynamicVisualizer


def _mural():
    return _load_prototype_module(
        "evolving-cosmic-mural-prototype.py", "evolving_cosmic_mural_midi_test"
    ).EvolvingCosmicMural


# -- dynamic_visuals --------------------------------------------------------


def test_dynamic_visuals_iteration_uses_integer_cc_only(tmp_path):
    midi = ScriptedMidi({70: 0.0, 71: 0.0, 72: 0.0})
    manager = FakeManager(midi, str(tmp_path))
    visualizer = _dynamic_visuals()(manager)

    image = visualizer._step()  # would raise TypeError pre-fix

    assert isinstance(image, Image.Image)
    assert midi.calls == [70, 71, 72]
    assert len(manager.renderer.frames) == 1


def test_dynamic_visuals_cc_change_changes_the_frame(tmp_path):
    midi = ScriptedMidi({70: 0.0, 71: 0.0, 72: 0.0})
    manager = FakeManager(midi, str(tmp_path))
    visualizer = _dynamic_visuals()(manager)

    first = np.array(visualizer._step())
    midi.values[70] = 1.0  # brightness knob full up -> bigger circle
    second = np.array(visualizer._step())

    assert not np.array_equal(first, second)


def test_dynamic_visuals_scaling_is_explicit(tmp_path):
    midi = ScriptedMidi({})
    visualizer = _dynamic_visuals()(FakeManager(midi, str(tmp_path)))

    # 0..1 CC mapped to 0.5..1.5 brightness/contrast, hue straight through.
    # Missing CCs fall back to the neutral knob (0.5 -> multiplier 1.0).
    assert visualizer._read_controls() == (1.0, 1.0, 0.0)
    midi.values.update({70: 0.0, 71: 0.0, 72: 0.5})
    assert visualizer._read_controls() == (0.5, 0.5, 0.5)
    midi.values.update({70: 1.0, 71: 1.0, 72: 1.0})
    assert visualizer._read_controls() == (1.5, 1.5, 1.0)


def test_dynamic_visuals_run_loop_completes_one_iteration(tmp_path):
    midi = ScriptedMidi({70: 0.2, 71: 0.7, 72: 0.4})
    manager = FakeManager(midi, str(tmp_path))
    manager.keyboard_input = ScriptedKeyboard([False, True])
    visualizer = _dynamic_visuals()(manager, update_interval=0.0)

    visualizer.run()  # no TypeError, quits on the second poll

    assert manager.keyboard_input.polls == 2
    assert len(manager.renderer.frames) == 1


# -- virtual_time_travel ----------------------------------------------------


def test_time_travel_era_selection_from_integer_cc(tmp_path):
    midi = ScriptedMidi({70: 0.0})
    manager = FakeManager(midi, str(tmp_path))
    from prototypes.virtual_time_travel import TimeTravelExperience

    travel = TimeTravelExperience(manager)

    assert travel._step() is True
    assert travel.current_era_index == 0
    assert manager.text2speech.spoken == ["Welcome to the Ancient Egypt era."]
    assert "Ancient Egypt" in manager.dalle3.prompts[0]
    # Rendered pixels, not the generator's path string.
    assert manager.renderer.frames[-1].shape == (64, 64, 3)

    midi.values[70] = 1.0
    assert travel._step() is True
    assert travel.current_era_index == len(travel.historical_eras) - 1
    assert "Cyberpunk Future" in manager.dalle3.prompts[-1]
    assert manager.renderer.frames[-1].shape == (64, 64, 3)


def test_time_travel_same_era_does_not_regenerate(tmp_path):
    midi = ScriptedMidi({70: 0.5})
    manager = FakeManager(midi, str(tmp_path))
    from prototypes.virtual_time_travel import TimeTravelExperience

    travel = TimeTravelExperience(manager)

    assert travel._step() is True
    renders, prompts = len(manager.renderer.frames), len(manager.dalle3.prompts)
    assert travel._step() is False
    assert len(manager.renderer.frames) == renders
    assert len(manager.dalle3.prompts) == prompts


def test_time_travel_run_loop_completes_one_iteration(tmp_path):
    midi = ScriptedMidi({70: 0.0})
    manager = FakeManager(midi, str(tmp_path))
    manager.keyboard_input = ScriptedKeyboard([False, True])
    from prototypes.virtual_time_travel import TimeTravelExperience

    TimeTravelExperience(manager, loop_delay=0.0).run()

    assert manager.keyboard_input.polls == 2
    assert len(manager.dalle3.prompts) == 1


# -- evolving cosmic mural --------------------------------------------------


def test_mural_first_iteration_decodes_generated_path(tmp_path):
    midi = ScriptedMidi({})
    manager = FakeManager(midi, str(tmp_path))
    mural = _mural()(manager, blend_speed=0.0)

    mural._step(pause=False)

    assert isinstance(mural.current_image, Image.Image)
    assert mural.current_image.mode == "RGB"
    assert len(manager.sdxl_lcm.prompts) == 1
    # Modifiers are cleared after a generation (original behaviour).
    assert mural.modifiers == []
    assert midi.calls == list(range(70, 78))


def test_mural_cc_threshold_appends_modifier(tmp_path):
    midi = ScriptedMidi({})
    manager = FakeManager(midi, str(tmp_path))
    mural = _mural()(manager, blend_speed=0.0)
    mural._step(pause=False)  # first generation, resets modifiers

    mural.last_generation_time = time.time()  # not due again yet
    midi.values[73] = 0.9
    mural._step(pause=False)

    assert mural.modifiers == ["showing a planetary alignment"]
    assert mural.midi_slider_states[3] is True
    assert len(manager.sdxl_lcm.prompts) == 1  # no new image generated

    # Dropping the knob back below the threshold unlatches without appending.
    midi.values[73] = 0.0
    mural._step(pause=False)
    assert mural.modifiers == ["showing a planetary alignment"]
    assert mural.midi_slider_states[3] is False


def test_mural_cross_fade_blends_pixels_not_paths(tmp_path):
    midi = ScriptedMidi({70: 0.9})
    manager = FakeManager(midi, str(tmp_path))
    mural = _mural()(manager, blend_speed=0.0)
    mural._step(pause=False)  # image 1 (no previous image -> no blend)
    assert len(manager.renderer.frames) == 1

    # Modifiers are cleared after each generation, so release the knob and push
    # it again to latch the phrase for the next prompt (original latch design).
    mural.last_generation_time = time.time()  # no generation due yet
    midi.values[70] = 0.0
    mural._step(pause=False)
    midi.values[70] = 0.9
    mural._step(pause=False)
    assert "with a supernova explosion" in mural.modifiers

    mural.last_generation_time -= mural.generation_interval + 1
    rendered_before = len(manager.renderer.frames)
    mural._step(pause=False)  # image 2 -> 30-frame cross-fade + final render

    prompts = manager.sdxl_lcm.prompts
    assert len(prompts) == 2
    assert "with a supernova explosion" in prompts[1]

    blend_frames = manager.renderer.frames[rendered_before : rendered_before + 30]
    assert len(blend_frames) == 30
    distinct = {frame.tobytes() for frame in blend_frames}
    assert len(distinct) >= 2  # numerically different blend frames
    assert not np.array_equal(blend_frames[0], blend_frames[-1])
    assert len(manager.renderer.frames) == rendered_before + 30 + 1


def test_mural_run_loop_completes_one_iteration(tmp_path):
    midi = ScriptedMidi({70: 1.0, 71: 0.0})
    manager = FakeManager(midi, str(tmp_path))
    manager.keyboard_input = ScriptedKeyboard([False, True])
    mural = _mural()(manager, blend_speed=0.0)

    mural.run()  # no TypeError, quits on the second poll

    assert manager.keyboard_input.polls == 2
    assert len(manager.sdxl_lcm.prompts) == 1


# -- no-device fallback -----------------------------------------------------


def test_no_device_fallback_returns_defaults_and_warns_once(tmp_path, monkeypatch, caplog):
    """Real MidiInput, mido importable, zero ports: defaults + one warning."""
    import mido

    monkeypatch.setattr(mido, "get_input_names", lambda: [])

    midi = MidiInput()
    assert midi._degraded is True
    assert midi.get(70) == 0.0
    assert midi.get(71, 0.25) == 0.25

    manager = FakeManager(midi, str(tmp_path))

    with caplog.at_level(logging.WARNING, logger="src.lunar_tools_art.tools.input"):
        _dynamic_visuals()(manager)._step()
        from prototypes.virtual_time_travel import TimeTravelExperience

        TimeTravelExperience(manager)._step()
        _mural()(manager, blend_speed=0.0)._step(pause=False)

    warnings = [
        record
        for record in caplog.records
        if record.name == "src.lunar_tools_art.tools.input"
        and record.levelno == logging.WARNING
        and "No MIDI input device available" in record.getMessage()
    ]
    assert len(warnings) == 1  # warn-once across three prototypes, one instance

    # Every prototype still completed a full iteration against the defaults.
    assert len(manager.renderer.frames) >= 3
    assert manager.text2speech.spoken == ["Welcome to the Ancient Egypt era."]
    assert len(manager.sdxl_lcm.prompts) == 1


def test_old_stub_signature_really_does_raise_typeerror():
    """Guards the contract: the pre-fix call style must fail with the fake."""
    midi = ScriptedMidi({})
    legacy_call = {"control": "A0", "val_min": 0, "val_max": 6}
    with pytest.raises(TypeError):
        midi.get(**legacy_call)
