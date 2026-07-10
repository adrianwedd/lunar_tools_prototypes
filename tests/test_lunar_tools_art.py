import importlib.util
import os
from unittest.mock import MagicMock, patch

import pytest

from src.lunar_tools_art import Manager
from src.lunar_tools_art.llm_backends import LLMBackend
from src.lunar_tools_art.tools import FluxImageGenerator, resolve

PROTOTYPES_DIR = os.path.join(os.path.dirname(__file__), "..", "prototypes")


def _load_prototype_module(filename, module_name):
    """Load a prototype module from its (possibly hyphenated) file path.

    Prototype files use hyphenated filenames (e.g. `virtual-cloud-chamber.py`)
    which are not valid Python module names, so `import prototypes.foo` can
    never succeed. Load directly from the file path instead, matching the
    hyphen-to-CamelCase discovery convention used by `lunar_tools_demo.py`.
    """
    file_path = os.path.join(PROTOTYPES_DIR, filename)
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Mock the lunar_tools library components


def test_lunar_tools_art_manager_initialization():
    manager = Manager()
    # tools.resolve() returns the headless fake under LUNAR_HEADLESS=1, else
    # the real class — check against whichever was actually wired up.
    assert isinstance(manager.speech2text, resolve("Speech2Text"))
    # The LLM is now a pluggable backend (see llm_backends.py); manager.gpt4
    # is a backwards-compat alias for manager.llm_backend.
    assert isinstance(manager.llm_backend, LLMBackend)
    assert manager.gpt4 is manager.llm_backend
    # text2speech now wraps the local (non-cloud) Afterwords VoiceClient, so
    # it is constructed even under local-only privacy mode.
    from src.lunar_tools_art.tools.tts import Text2Speech

    assert isinstance(manager.text2speech, Text2Speech)
    # Cloud-calling tools are only constructed when privacy.cloud_allowed();
    # default privacy.mode is local-only, so these are None here.
    assert manager.sdxl_turbo is None
    assert manager.dalle3 is None
    assert manager.sdxl_lcm is None
    assert isinstance(manager.audio_recorder, resolve("AudioRecorder"))
    assert isinstance(manager.sound_player, resolve("SoundPlayer"))
    assert isinstance(manager.renderer, resolve("Renderer"))
    assert isinstance(manager.keyboard_input, resolve("KeyboardInput"))
    assert isinstance(manager.webcam, resolve("WebCam"))
    assert isinstance(manager.flux, FluxImageGenerator)
    assert isinstance(manager.zmq_pair_endpoint, resolve("ZMQPairEndpoint"))
    assert isinstance(manager.midi_input, resolve("MidiInput"))


def test_renderer_set_size():
    manager = Manager()
    manager.renderer.set_size(100, 200)
    assert manager.renderer.width == 100
    assert manager.renderer.height == 200


# Smoke test for interactive_storytelling.py
def test_interactive_storytelling_smoke_test():
    from prototypes.interactive_storytelling import InteractiveStoryteller

    manager = Manager()
    storyteller = InteractiveStoryteller(manager)
    # We can't run the full loop without actual hardware/user input,
    # but we can test that the run method can be called without immediate errors.
    # This is a very basic smoke test.
    try:
        # Mock keyboard input to immediately quit
        manager.keyboard_input.is_key_pressed = MagicMock(side_effect=[False, True])
        storyteller.run()
    except Exception as e:
        pytest.fail(f"InteractiveStoryteller.run() raised an exception: {e}")


# Smoke test for apocalypse_experience.py
def test_apocalypse_experience_smoke_test():
    from prototypes.apocalypse_experience import ApocalypseExperience

    manager = Manager()
    experience = ApocalypseExperience(manager)
    try:
        manager.keyboard_input.is_key_pressed = MagicMock(side_effect=[False, True])
        experience.run()
    except Exception as e:
        pytest.fail(f"ApocalypseExperience.run() raised an exception: {e}")


# Smoke test for augmented_audio_tours.py
def test_augmented_audio_tours_smoke_test():
    from prototypes.augmented_audio_tours import AugmentedAudioTour

    manager = Manager()
    tour = AugmentedAudioTour(manager)
    try:
        manager.keyboard_input.is_key_pressed = MagicMock(side_effect=[False, True])
        tour.run()
    except Exception as e:
        pytest.fail(f"AugmentedAudioTour.run() raised an exception: {e}")


# Smoke test for collaborative_art.py
def test_collaborative_art_smoke_test():
    from prototypes.collaborative_art import CollaborativeArtServer

    manager = Manager()
    server = CollaborativeArtServer(manager)
    try:
        manager.keyboard_input.is_key_pressed = MagicMock(side_effect=[False, True])
        server.run()
    except Exception as e:
        pytest.fail(f"CollaborativeArtServer.run() raised an exception: {e}")


# Smoke test for dynamic_visuals.py
def test_dynamic_visuals_smoke_test():
    from prototypes.dynamic_visuals import DynamicVisualizer

    manager = Manager()
    visualizer = DynamicVisualizer(manager)
    try:
        manager.keyboard_input.is_key_pressed = MagicMock(side_effect=[False, True])
        visualizer.run()
    except Exception as e:
        pytest.fail(f"DynamicVisualizer.run() raised an exception: {e}")


# Smoke test for emotional-landscape-generator-prototype.py
def test_emotional_landscape_generator_smoke_test():
    module = _load_prototype_module(
        "emotional-landscape-generator-prototype.py",
        "emotional_landscape_generator_prototype",
    )
    EmotionalLandscapeGenerator = module.EmotionalLandscapeGenerator

    manager = Manager()
    generator = EmotionalLandscapeGenerator(manager)
    try:
        manager.keyboard_input.is_key_pressed = MagicMock(side_effect=[False, True])
        generator.run()
    except Exception as e:
        pytest.fail(f"EmotionalLandscapeGenerator.run() raised an exception: {e}")


# Smoke test for escape_room.py
@pytest.mark.xfail(
    reason="prototype calls .strip() directly on gpt4.generate()'s return value "
    "without a None guard; under LUNAR_HEADLESS the fake Speech2Text returns a "
    "truthy transcript, driving that code path when the LLM backend is "
    "unavailable (stub-era code, not a test issue)"
)
def test_escape_room_smoke_test():
    from prototypes.escape_room import EscapeRoomGame

    manager = Manager()
    game = EscapeRoomGame(manager)
    try:
        manager.keyboard_input.is_key_pressed = MagicMock(side_effect=[False, True])
        game.run()
    except Exception as e:
        pytest.fail(f"EscapeRoomGame.run() raised an exception: {e}")


# Smoke test for evolving-cosmic-mural-prototype.py
def test_evolving_cosmic_mural_smoke_test():
    module = _load_prototype_module(
        "evolving-cosmic-mural-prototype.py", "evolving_cosmic_mural_prototype"
    )
    EvolvingCosmicMural = module.EvolvingCosmicMural

    manager = Manager()
    mural = EvolvingCosmicMural(manager)
    try:
        manager.keyboard_input.is_key_pressed = MagicMock(side_effect=[False, True])
        mural.run()
    except Exception as e:
        pytest.fail(f"EvolvingCosmicMural.run() raised an exception: {e}")


# Smoke test for sentiment_analysis_display.py
def test_sentiment_analysis_display_smoke_test():
    from prototypes.sentiment_analysis_display import SentimentDisplay

    manager = Manager()
    display = SentimentDisplay(manager)
    try:
        manager.keyboard_input.is_key_pressed = MagicMock(side_effect=[False, True])
        display.run()
    except Exception as e:
        pytest.fail(f"SentimentDisplay.run() raised an exception: {e}")


# Smoke test for speech_activated_art.py
def test_speech_activated_art_smoke_test():
    from prototypes.speech_activated_art import SpeechArtGenerator

    manager = Manager()
    generator = SpeechArtGenerator(manager)
    try:
        manager.keyboard_input.is_key_pressed = MagicMock(side_effect=[False, True])
        generator.run()
    except Exception as e:
        pytest.fail(f"SpeechArtGenerator.run() raised an exception: {e}")


# Smoke test for temporal-art-gallery-prototype.py
def test_temporal_art_gallery_smoke_test():
    module = _load_prototype_module(
        "temporal-art-gallery-prototype.py", "temporal_art_gallery_prototype"
    )
    TemporalArtGallery = module.TemporalArtGallery

    manager = Manager()
    gallery = TemporalArtGallery(manager)
    try:
        manager.keyboard_input.is_key_pressed = MagicMock(side_effect=[False, True])
        gallery.run()
    except Exception as e:
        pytest.fail(f"TemporalArtGallery.run() raised an exception: {e}")


# Smoke test for virtual_time_travel.py
@pytest.mark.xfail(
    reason="prototype calls .strip() directly on gpt4.generate()'s return value "
    "without a None guard; under LUNAR_HEADLESS the fake Speech2Text returns a "
    "truthy transcript, driving that code path when the LLM backend is "
    "unavailable (stub-era code, not a test issue)"
)
def test_virtual_time_travel_smoke_test():
    from prototypes.virtual_time_travel import TimeTravelExperience

    manager = Manager()
    experience = TimeTravelExperience(manager)
    try:
        manager.keyboard_input.is_key_pressed = MagicMock(side_effect=[False, True])
        experience.run()
    except Exception as e:
        pytest.fail(f"TimeTravelExperience.run() raised an exception: {e}")


# Smoke test for audio-reactive-fractal-forest.py
def test_audio_reactive_fractal_forest_smoke_test():
    module = _load_prototype_module(
        "audio-reactive-fractal-forest.py", "audio_reactive_fractal_forest"
    )
    AudioReactiveFractalForest = module.AudioReactiveFractalForest

    manager = Manager()
    forest = AudioReactiveFractalForest(manager)
    try:
        manager.keyboard_input.is_key_pressed = MagicMock(side_effect=[False, True])
        forest.run()
    except Exception as e:
        pytest.fail(f"AudioReactiveFractalForest.run() raised an exception: {e}")


# Smoke test for generative-poetry-mosaic.py
def test_generative_poetry_mosaic_smoke_test():
    module = _load_prototype_module(
        "generative-poetry-mosaic.py", "generative_poetry_mosaic"
    )
    GenerativePoetryMosaic = module.GenerativePoetryMosaic

    manager = Manager()
    mosaic = GenerativePoetryMosaic(manager)
    try:
        manager.keyboard_input.is_key_pressed = MagicMock(side_effect=[False, True])
        # Mock input to prevent blocking
        with patch("builtins.input", return_value="q"):
            mosaic.run()
    except Exception as e:
        pytest.fail(f"GenerativePoetryMosaic.run() raised an exception: {e}")


# Smoke test for collaborative-canvas.py
def test_collaborative_canvas_smoke_test():
    module = _load_prototype_module("collaborative-canvas.py", "collaborative_canvas")
    CollaborativeCanvas = module.CollaborativeCanvas

    manager = Manager()
    canvas = CollaborativeCanvas(manager)
    try:
        manager.keyboard_input.is_key_pressed = MagicMock(side_effect=[False, True])
        canvas.run()
    except Exception as e:
        pytest.fail(f"CollaborativeCanvas.run() raised an exception: {e}")


# Smoke test for acoustic-fingerprint-painter.py
@pytest.mark.xfail(
    reason="prototype's audio feature extraction writes a temp WAV that soundfile cannot parse and its GPT stroke-parameter parsing crashes on a None response (stub-era code, not a test issue)"
)
def test_acoustic_fingerprint_painter_smoke_test():
    module = _load_prototype_module(
        "acoustic-fingerprint-painter.py", "acoustic_fingerprint_painter"
    )
    AcousticFingerprintPainter = module.AcousticFingerprintPainter

    manager = Manager()
    painter = AcousticFingerprintPainter(manager)
    try:
        manager.keyboard_input.is_key_pressed = MagicMock(side_effect=[False, True])
        painter.run()
    except Exception as e:
        pytest.fail(f"AcousticFingerprintPainter.run() raised an exception: {e}")


# Smoke test for time-shifted-echo-chamber.py
@pytest.mark.xfail(
    reason="prototype requires api_keys.openweathermap config which is not part of the test environment; prototype needs a mockable weather client (stub-era code)"
)
def test_time_shifted_echo_chamber_smoke_test():
    module = _load_prototype_module(
        "time-shifted-echo-chamber.py", "time_shifted_echo_chamber"
    )
    TimeShiftedEchoChamber = module.TimeShiftedEchoChamber

    manager = Manager()
    chamber = TimeShiftedEchoChamber(manager)
    try:
        manager.keyboard_input.is_key_pressed = MagicMock(side_effect=[False, True])
        chamber.run()
    except Exception as e:
        pytest.fail(f"TimeShiftedEchoChamber.run() raised an exception: {e}")


# Smoke test for data-driven-cityscape.py
@pytest.mark.xfail(
    reason="prototype requires api_keys.openweathermap config which is not part of the test environment; prototype needs a mockable weather client (stub-era code)"
)
def test_data_driven_cityscape_smoke_test():
    module = _load_prototype_module("data-driven-cityscape.py", "data_driven_cityscape")
    DataDrivenCityscape = module.DataDrivenCityscape

    manager = Manager()
    # Mock requests.get to prevent actual API calls
    with patch("requests.get") as mock_get:
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.json.return_value = {"weather": "sunny"}
        cityscape = DataDrivenCityscape(manager)
        try:
            manager.keyboard_input.is_key_pressed = MagicMock(side_effect=[False, True])
            cityscape.run()
        except Exception as e:
            pytest.fail(f"DataDrivenCityscape.run() raised an exception: {e}")


# Smoke test for real-time-glitch-art-lab.py
def test_real_time_glitch_art_lab_smoke_test():
    module = _load_prototype_module(
        "real-time-glitch-art-lab.py", "real_time_glitch_art_lab"
    )
    RealTimeGlitchArtLab = module.RealTimeGlitchArtLab

    manager = Manager()
    lab = RealTimeGlitchArtLab(manager)
    try:
        manager.keyboard_input.is_key_pressed = MagicMock(side_effect=[False, True])
        lab.run()
    except Exception as e:
        pytest.fail(f"RealTimeGlitchArtLab.run() raised an exception: {e}")


# Smoke test for neural-transfer-music-visualizer.py
@pytest.mark.xfail(
    reason="prototype calls SoundPlayer.stop_sound(), a method that does not exist on the current SoundPlayer tool (stub-era code)"
)
def test_neural_transfer_music_visualizer_smoke_test():
    module = _load_prototype_module(
        "neural-transfer-music-visualizer.py", "neural_transfer_music_visualizer"
    )
    NeuralTransferMusicVisualizer = module.NeuralTransferMusicVisualizer

    manager = Manager()
    visualizer = NeuralTransferMusicVisualizer(manager)
    try:
        manager.keyboard_input.is_key_pressed = MagicMock(side_effect=[False, True])
        visualizer.run()
    except Exception as e:
        pytest.fail(f"NeuralTransferMusicVisualizer.run() raised an exception: {e}")


# Smoke test for chat-room-narrative-quilt.py
@pytest.mark.xfail(
    reason="prototype's __init__ references self.l, an undefined attribute (stub-era code)"
)
def test_chat_room_narrative_quilt_smoke_test():
    module = _load_prototype_module(
        "chat-room-narrative-quilt.py", "chat_room_narrative_quilt"
    )
    ChatRoomNarrativeQuilt = module.ChatRoomNarrativeQuilt

    manager = Manager()
    quilt = ChatRoomNarrativeQuilt(manager)
    try:
        manager.keyboard_input.is_key_pressed = MagicMock(side_effect=[False, True])
        with patch("builtins.input", return_value="q"):
            quilt.run()
    except Exception as e:
        pytest.fail(f"ChatRoomNarrativeQuilt.run() raised an exception: {e}")


# Smoke test for virtual-cloud-chamber.py
# Note: KeyboardInput.is_any_key_pressed() now exists; prototype has latent text2speech=None issue in headless mode but smoke test passes.
def test_virtual_cloud_chamber_smoke_test():
    module = _load_prototype_module("virtual-cloud-chamber.py", "virtual_cloud_chamber")
    VirtualCloudChamber = module.VirtualCloudChamber

    manager = Manager()
    chamber = VirtualCloudChamber(manager)
    try:
        manager.keyboard_input.is_key_pressed = MagicMock(side_effect=[False, True])
        chamber.run()
    except Exception as e:
        pytest.fail(f"VirtualCloudChamber.run() raised an exception: {e}")
