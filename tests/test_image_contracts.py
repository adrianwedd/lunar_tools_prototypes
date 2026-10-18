"""Contract tests: image-generating prototypes receive pixels, not PNG paths.

Every image backend in this repo returns ``(png_path, metadata)``. Prototypes
that resize, paste, or render that value must decode it (via
``load_generated_image``) before touching it as an image. These tests use a
fake generator that writes *real* PNG files to ``tmp_path`` — no mock returns
an arbitrary string — so a regression to "treat the path as pixels" fails
here instead of silently painting a static wallpaper on a real backend.
"""

import importlib.util
import logging
import os
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

PROTOTYPES_DIR = os.path.join(os.path.dirname(__file__), "..", "prototypes")


def load_prototype(filename):
    """Load a prototype from its hyphenated file path."""
    module_name = "image_contract_" + filename.replace("-", "_").removesuffix(".py")
    path = os.path.join(PROTOTYPES_DIR, filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PngGenerator:
    """Fake unified generator: writes a real PNG and returns (path, metadata)."""

    def __init__(self, tmp_path, size=(64, 64)):
        self.tmp_path = tmp_path
        self.size = size
        self.calls = []
        self._n = 0

    def generate(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
        self._n += 1
        width, height = self.size
        pixels = np.zeros((height, width, 3), dtype=np.uint8)
        pixels[..., 0] = np.linspace(20, 235, width, dtype=np.uint8)
        pixels[..., 1] = min(40 + 15 * self._n, 255)
        pixels[..., 2] = 120
        path = self.tmp_path / f"fake-gen-{self._n:03d}.png"
        Image.fromarray(pixels, mode="RGB").save(path)
        return str(path), {"backend": "fake", "seed": 1}


class TextGenerator:
    def __init__(self, text):
        self.text = text
        self.prompts = []

    def generate(self, prompt, **kwargs):
        self.prompts.append(prompt)
        return self.text


class FakeSpeech2Text:
    def __init__(self, text="hello world"):
        self.text = text

    def transcribe(self, *args, **kwargs):
        return self.text


class RecordingRenderer:
    """Records frames and enforces the real renderer's pixel contract."""

    def __init__(self, width=640, height=480):
        self.width = width
        self.height = height
        self.frames = []

    def set_size(self, width=None, height=None, **kwargs):
        if width is not None:
            self.width = width
        if height is not None:
            self.height = height

    def render(self, image):
        assert isinstance(image, np.ndarray), (
            f"renderer.render() received {type(image).__name__}, not an ndarray"
        )
        assert image.ndim == 3, f"renderer got {image.ndim}-d array {image.shape}"
        assert image.dtype == np.uint8, f"renderer got dtype {image.dtype}"
        self.frames.append(image)


class ScriptedKeyboard:
    """Returns configured key presses; quits after N loop iterations."""

    def __init__(self, quit_after=1, presses=None):
        self.quit_after = quit_after
        self.presses = dict(presses or {})
        self._q_checks = 0

    def is_key_pressed(self, key):
        if key in ("q", "esc"):
            self._q_checks += 1
            return self._q_checks > self.quit_after
        return False

    def get(self, key, *args, **kwargs):
        return self.presses.get(key, False)


class FakeZMQEndpoint:
    def __init__(self, messages=None):
        self.ip = "127.0.0.1"
        self.port = "5556"
        self._messages = list(messages or [])
        self.sent_images = []

    def get_messages(self):
        return self._messages.pop(0) if self._messages else []

    def send_img(self, img):
        # Real send_img() reads img.shape and img.tobytes().
        assert hasattr(img, "shape"), f"send_img() received {type(img).__name__}"
        assert hasattr(img, "tobytes")
        self.sent_images.append(img)


class FakeAudioRecorder:
    def start_recording(self, *args, **kwargs):
        return None

    def stop_recording(self, *args, **kwargs):
        return None


def make_manager(
    tmp_path,
    *,
    width=640,
    height=480,
    text="line one\nline two",
    speech="hello world",
    png_size=(64, 64),
    keyboard=None,
    zmq_messages=None,
):
    manager = SimpleNamespace()
    manager.logger = logging.getLogger("test.image_contracts")
    manager.config = {}
    manager.renderer = RecordingRenderer(width, height)
    generator = PngGenerator(tmp_path, png_size)
    manager.image_gen = generator
    manager.dalle3 = generator
    manager.sdxl_turbo = generator
    manager.sdxl_lcm = generator
    manager.flux = generator
    manager.gpt4 = TextGenerator(text)
    manager.llm = manager.gpt4
    manager.speech2text = FakeSpeech2Text(speech)
    manager.text2speech = SimpleNamespace(generate=lambda *a, **k: "/tmp/fake.wav")
    manager.keyboard_input = keyboard or ScriptedKeyboard(quit_after=1)
    manager.sound_player = SimpleNamespace(
        play_sound=lambda *a, **k: None,
        play_audio=lambda *a, **k: None,
        stop_sound=lambda *a, **k: None,
    )
    manager.audio_recorder = FakeAudioRecorder()
    manager.webcam = SimpleNamespace(
        get_img=lambda: np.zeros((48, 64, 3), dtype=np.uint8)
    )
    manager.zmq_pair_endpoint = FakeZMQEndpoint(zmq_messages)
    return manager


def assert_frame(frame, shape):
    assert isinstance(frame, np.ndarray)
    assert frame.ndim == 3
    assert frame.dtype == np.uint8
    assert frame.shape == shape


# --- 1. Generative Poetry Mosaic (priority) --------------------------------


def test_poetry_mosaic_step_pastes_tile_at_grid_position(tmp_path, caplog):
    mod = load_prototype("generative-poetry-mosaic.py")
    manager = make_manager(tmp_path, width=600, height=400, text="Line one\nLine two")
    mosaic = mod.GenerativePoetryMosaic(manager)

    assert (mosaic.grid_cols, mosaic.grid_rows) == (2, 2)

    assert mosaic._step("ocean") is True

    # Prompt logic preserved: background prompt is built from the first poem line.
    assert manager.dalle3.calls[0][0] == "Abstract background image inspired by: Line one"
    assert manager.dalle3.calls[0][1] == {"image_size": "square_small"}

    assert len(mosaic.tiles) == 1
    tile = mosaic.tiles[0]
    assert isinstance(tile, Image.Image)
    assert tile.size == (300, 200)
    assert tile.mode == "RGB"

    canvas = np.asarray(mosaic.canvas)
    assert canvas.shape == (400, 600, 3)
    assert np.array_equal(canvas[:200, :300], np.asarray(tile))
    assert canvas[:200, :300].max() > 0  # decoded pixels, not a black tile
    assert canvas[200:, 300:].max() == 0  # untouched canvas stays black

    assert_frame(manager.renderer.frames[-1], (400, 600, 3))
    assert np.array_equal(manager.renderer.frames[-1], canvas)

    # Second tile goes to the next grid column, not on top of the first.
    assert mosaic._step("fire") is True
    canvas = np.asarray(mosaic.canvas)
    assert np.array_equal(canvas[:200, 300:600], np.asarray(mosaic.tiles[1]))
    assert np.array_equal(canvas[:200, :300], np.asarray(tile))


def test_poetry_mosaic_run_keeps_input_behaviour(tmp_path, monkeypatch, caplog):
    mod = load_prototype("generative-poetry-mosaic.py")
    manager = make_manager(tmp_path, width=600, height=400)
    mosaic = mod.GenerativePoetryMosaic(manager)

    answers = iter(["", "q"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    with caplog.at_level(logging.INFO, logger=manager.logger.name):
        mosaic.run()

    assert "Please enter a keyword." in caplog.text
    assert manager.dalle3.calls == []  # empty input re-prompted, never generated
    assert manager.renderer.frames == []


def test_poetry_mosaic_run_survives_generation_error(tmp_path, monkeypatch, caplog):
    mod = load_prototype("generative-poetry-mosaic.py")
    manager = make_manager(tmp_path, width=600, height=400)

    def boom(*args, **kwargs):
        raise RuntimeError("backend down")

    manager.dalle3.generate = boom
    mosaic = mod.GenerativePoetryMosaic(manager)

    answers = iter(["ocean", "q"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    with caplog.at_level(logging.ERROR, logger=manager.logger.name):
        mosaic.run()

    assert "An error occurred: backend down" in caplog.text
    assert manager.renderer.frames == []


# --- 2. AI Dream Interpreter ----------------------------------------------


def test_poetry_mosaic_none_text_response_is_skipped(tmp_path, caplog):
    """An LLM outage returns None: skip the keyword, don't traceback."""
    mod = load_prototype("generative-poetry-mosaic.py")
    manager = make_manager(tmp_path, width=600, height=400)
    manager.gpt4 = TextGenerator(None)
    mosaic = mod.GenerativePoetryMosaic(manager)
    with caplog.at_level(logging.INFO, logger=manager.logger.name):
        assert mosaic._step("ocean") is False
    assert "Could not generate poem" in caplog.text
    assert manager.dalle3.calls == []


def test_dream_interpreter_returns_pixels_not_path(tmp_path):
    mod = load_prototype("ai-dream-interpreter-prototype.py")
    manager = make_manager(tmp_path, text="a symbol of change")
    interpreter = mod.AIDreamInterpreter(manager)

    image, interpretation = interpreter.interpret_dream("I was flying")

    assert interpretation == "a symbol of change"
    assert_frame(image, (64, 64, 3))
    # run() renders exactly this object.
    manager.renderer.render(image)
    assert_frame(manager.renderer.frames[-1], (64, 64, 3))


# --- 3. AI Fashion Show ---------------------------------------------------


def test_fashion_show_renders_one_full_show_iteration(tmp_path):
    mod = load_prototype("ai-fashion-show-prototype.py")
    manager = make_manager(tmp_path)
    show = mod.AIFashionShow(manager, display_duration=0, break_duration=0)
    show.themes = ["futuristic cyberpunk"]
    show.outfits_per_theme = 1

    show.run_fashion_show()

    assert len(manager.renderer.frames) == 1
    assert_frame(manager.renderer.frames[0], (64, 64, 3))
    assert len(manager.dalle3.calls) == 1


# --- 4. Apocalypse Experience ---------------------------------------------


def test_apocalypse_experience_one_loop_iteration(tmp_path):
    mod = load_prototype("apocalypse_experience.py")
    keyboard = ScriptedKeyboard(quit_after=1, presses={"s": True})
    manager = make_manager(tmp_path, keyboard=keyboard)
    experience = mod.ApocalypseExperience(manager, loop_delay=0)

    experience.run()

    assert len(manager.renderer.frames) == 1
    assert_frame(manager.renderer.frames[0], (64, 64, 3))


# --- 5. Chat Room Narrative Quilt -----------------------------------------


def test_narrative_quilt_composites_generated_panel(tmp_path):
    mod = load_prototype("chat-room-narrative-quilt.py")
    manager = make_manager(tmp_path, width=600, height=400, text="a warm kitchen")
    quilt = mod.ChatRoomNarrativeQuilt(manager)

    quilt._process_chat_message("we talked about soup")

    assert len(quilt.patches) == 1
    patch = quilt.patches[0]
    assert isinstance(patch, Image.Image)
    assert patch.size == (300, 200)

    quilt_pixels = np.asarray(quilt.quilt_image)
    assert quilt_pixels.shape == (400, 600, 3)
    assert np.array_equal(quilt_pixels[:200, :300], np.asarray(patch))
    assert quilt_pixels[:200, :300].max() > 0

    assert_frame(manager.renderer.frames[-1], (400, 600, 3))
    assert np.array_equal(manager.renderer.frames[-1], quilt_pixels)


# --- 6. Collaborative Art -------------------------------------------------


def test_collaborative_art_sends_decoded_pixels(tmp_path):
    mod = load_prototype("collaborative_art.py")
    manager = make_manager(tmp_path, zmq_messages=["a shared sunset"])
    server = mod.CollaborativeArtServer(manager)
    server.running = True

    server.handle_client()

    assert len(manager.renderer.frames) == 1
    assert_frame(manager.renderer.frames[0], (64, 64, 3))
    assert len(manager.zmq_pair_endpoint.sent_images) == 1
    assert_frame(manager.zmq_pair_endpoint.sent_images[0], (64, 64, 3))


# --- 7. Emotional Landscape Generator -------------------------------------


def test_emotional_landscape_generates_pixels(tmp_path):
    mod = load_prototype("emotional-landscape-generator-prototype.py")
    manager = make_manager(tmp_path)
    generator = mod.EmotionalLandscapeGenerator(manager)

    landscape = generator.generate_landscape("happy")

    assert_frame(landscape, (64, 64, 3))
    manager.renderer.render(landscape)
    assert_frame(manager.renderer.frames[-1], (64, 64, 3))
    assert "sunny" in manager.dalle3.calls[0][0]


# --- 8. Escape Room -------------------------------------------------------


def test_escape_room_one_puzzle_iteration(tmp_path):
    mod = load_prototype("escape_room.py")
    keyboard = ScriptedKeyboard(quit_after=1)
    manager = make_manager(tmp_path, keyboard=keyboard, speech="open chest", text="solve_puzzle")
    game = mod.EscapeRoomGame(manager)

    game.run()

    # Initial puzzle visual + the visual for puzzle 2 after solving puzzle 1.
    assert len(manager.renderer.frames) == 2
    for frame in manager.renderer.frames:
        assert_frame(frame, (64, 64, 3))
    assert game.game_state["current_puzzle"] == 1


# --- 9. Neural Transfer Music Visualizer ----------------------------------


def test_neural_transfer_returns_decoded_frame(tmp_path):
    mod = load_prototype("neural-transfer-music-visualizer.py")
    manager = make_manager(tmp_path)
    visualizer = mod.NeuralTransferMusicVisualizer(manager)
    frame = np.zeros((48, 64, 3), dtype=np.uint8)

    stylized = visualizer._run_neural_style_transfer(frame)

    assert_frame(stylized, (64, 64, 3))
    manager.renderer.render(stylized)
    assert_frame(manager.renderer.frames[-1], (64, 64, 3))


# --- 10. Sentiment Analysis Display ---------------------------------------


def test_sentiment_display_generates_pixels(tmp_path):
    mod = load_prototype("sentiment_analysis_display.py")
    manager = make_manager(tmp_path)
    display = mod.SentimentDisplay(manager)

    image = display.generate_sentiment_visual("positive")

    assert_frame(image, (64, 64, 3))
    manager.renderer.render(image)
    assert_frame(manager.renderer.frames[-1], (64, 64, 3))
    assert "uplifting" in manager.dalle3.calls[0][0]


# --- 11. Speech Activated Art ---------------------------------------------


def test_speech_activated_art_one_loop_iteration(tmp_path):
    mod = load_prototype("speech_activated_art.py")
    keyboard = ScriptedKeyboard(quit_after=1)
    manager = make_manager(tmp_path, keyboard=keyboard)
    generator = mod.SpeechArtGenerator(manager, no_speech_delay=0, loop_delay=0)

    generator.run()

    assert len(manager.renderer.frames) == 1
    assert_frame(manager.renderer.frames[0], (64, 64, 3))


# --- 12. Temporal Art Gallery ---------------------------------------------


def test_temporal_gallery_one_loop_iteration(tmp_path):
    mod = load_prototype("temporal-art-gallery-prototype.py")
    keyboard = ScriptedKeyboard(quit_after=1)
    manager = make_manager(tmp_path, keyboard=keyboard)
    gallery = mod.TemporalArtGallery(manager, prompts=["dawn study"], check_interval=0)

    gallery.run()

    assert len(manager.renderer.frames) == 1
    assert_frame(manager.renderer.frames[0], (64, 64, 3))
    # Legacy kwargs are still forwarded to the (deprecated) flux alias.
    assert manager.flux.calls[0][1]["image_size"] == "square_hd"


# --- 13. Cosmic Soundscape -------------------------------------------------


def test_cosmic_soundscape_update_renders_pixels(tmp_path):
    mod = load_prototype("cosmic-soundscape.py")
    manager = make_manager(tmp_path, speech="a storm over the ocean of stars")
    soundscape = mod.CosmicSoundscape(manager)
    soundscape.setup()

    soundscape.update()

    assert len(manager.renderer.frames) == 1
    assert_frame(manager.renderer.frames[0], (64, 64, 3))
    prompt = manager.image_gen.calls[0][0]
    assert "plasma storm" in prompt
