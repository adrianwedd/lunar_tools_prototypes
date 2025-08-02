"""Tests for prototype base classes."""

import time
from unittest.mock import Mock, patch

import pytest

from src.lunar_tools_art.prototype_base import (
    AIPrototype,
    InteractivePrototype,
    PrototypeBase,
)


class MockPrototype(PrototypeBase):
    """Test implementation of PrototypeBase."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_called = False
        self.update_called = False
        self.cleanup_called = False
        self.update_count = 0

    def setup(self):
        self.setup_called = True

    def update(self):
        self.update_called = True
        self.update_count += 1

        # Stop after a few iterations to prevent infinite loop in tests
        if self.update_count >= 3:
            self.stop()

    def cleanup(self):
        self.cleanup_called = True


@pytest.fixture
def mock_manager():
    """Create a mock Manager instance."""
    manager = Mock()
    manager.renderer = Mock()
    manager.keyboard_input = Mock()
    manager.config = Mock()
    manager.config.get = Mock(return_value=None)
    return manager


@pytest.fixture
def mock_prototype(mock_manager):
    """Create a mock prototype instance."""
    return MockPrototype(mock_manager)


class TestPrototypeBase:
    """Test the base PrototypeBase class."""

    def test_initialization(self, mock_manager):
        """Test basic initialization."""
        config = {"test_param": 42, "loop_delay": 0.01}
        prototype = MockPrototype(mock_manager, **config)

        assert prototype.manager == mock_manager
        assert prototype.loop_delay == 0.01
        assert prototype.get_config("test_param") == 42
        assert prototype._running is False

    def test_run_lifecycle(self, mock_prototype):
        """Test that run() calls setup, update, and cleanup in order."""
        # Mock should_exit to return True after a few iterations
        mock_prototype.should_exit = Mock(side_effect=[False, False, False, True])

        mock_prototype.run()

        assert mock_prototype.setup_called
        assert mock_prototype.update_called
        assert mock_prototype.cleanup_called
        assert mock_prototype.update_count == 3

    def test_graceful_stop(self, mock_prototype):
        """Test graceful stopping."""
        assert mock_prototype._running is False

        # Start in background thread to test stop
        import threading

        def run_prototype():
            mock_prototype.run()

        thread = threading.Thread(target=run_prototype)
        thread.start()

        # Give it a moment to start
        time.sleep(0.1)

        # Stop it
        mock_prototype.stop()

        thread.join(timeout=1.0)
        assert not thread.is_alive()
        assert mock_prototype.cleanup_called

    def test_should_exit_default(self, mock_prototype):
        """Test default exit conditions."""
        # Mock keyboard input
        mock_prototype.keyboard_input.is_key_pressed = Mock(return_value=False)
        mock_prototype._running = True

        assert not mock_prototype.should_exit()

        # Test 'q' key
        mock_prototype.keyboard_input.is_key_pressed = Mock(
            side_effect=lambda key: key == "q"
        )
        assert mock_prototype.should_exit()

        # Test 'esc' key
        mock_prototype.keyboard_input.is_key_pressed = Mock(
            side_effect=lambda key: key == "esc"
        )
        assert mock_prototype.should_exit()

        # Test not running
        mock_prototype.keyboard_input.is_key_pressed = Mock(return_value=False)
        mock_prototype._running = False
        assert mock_prototype.should_exit()

    def test_config_management(self, mock_manager):
        """Test configuration management."""
        # Prototype-specific config
        config = {"local_param": "local_value"}
        prototype = MockPrototype(mock_manager, **config)

        # Manager global config
        mock_manager.config.get = Mock(return_value="global_value")

        # Local config takes precedence
        assert prototype.get_config("local_param") == "local_value"

        # Falls back to manager config
        assert prototype.get_config("global_param") == "global_value"

        # Uses default if not found
        assert prototype.get_config("missing_param", "default") == "default"

    def test_config_validation(self, mock_prototype):
        """Test configuration validation."""
        # Mock get_config to return None for missing keys
        mock_prototype.get_config = Mock(
            side_effect=lambda key, default=None: (
                "value" if key == "present_key" else default
            )
        )

        # Should not raise for present keys
        mock_prototype.validate_config(["present_key"])

        # Should raise for missing keys
        with pytest.raises(ValueError, match="Missing required configuration keys"):
            mock_prototype.validate_config(["missing_key"])

    def test_performance_logging(self, mock_prototype):
        """Test performance logging."""
        with patch.object(mock_prototype.logger, "debug") as mock_debug:
            with patch.object(mock_prototype.logger, "warning") as mock_warning:
                # Fast operation - should only debug log
                mock_prototype.log_performance("fast_op", 0.1)
                mock_debug.assert_called_once()
                mock_warning.assert_not_called()

                # Slow operation - should warn
                mock_prototype.log_performance("slow_op", 2.0)
                mock_warning.assert_called_once()

    def test_exception_handling(self, mock_prototype):
        """Test exception handling in run loop."""

        # Make update raise an exception
        def failing_update():
            if mock_prototype.update_count == 0:
                mock_prototype.update_count += 1
                raise ValueError("Test exception")
            mock_prototype.stop()

        mock_prototype.update = failing_update

        # Should not crash, should still call cleanup
        mock_prototype.run()
        assert mock_prototype.cleanup_called


class TestInteractivePrototype:
    """Test the InteractivePrototype class."""

    @pytest.fixture
    def interactive_manager(self, mock_manager):
        """Manager with interactive tools."""
        mock_manager.speech2text = Mock()
        mock_manager.audio_recorder = Mock()
        mock_manager.sound_player = Mock()
        return mock_manager

    def test_initialization(self, interactive_manager):
        """Test interactive prototype initialization."""
        prototype = InteractivePrototype(interactive_manager)

        assert prototype.speech2text == interactive_manager.speech2text
        assert prototype.audio_recorder == interactive_manager.audio_recorder
        assert prototype.sound_player == interactive_manager.sound_player

    def test_get_user_speech_success(self, interactive_manager):
        """Test successful speech capture."""
        prototype = InteractivePrototype(interactive_manager)

        # Mock successful audio recording and transcription
        mock_audio = b"fake_audio_data"
        interactive_manager.audio_recorder.record.return_value = mock_audio
        interactive_manager.speech2text.transcribe.return_value = "  Hello world  "

        result = prototype.get_user_speech(timeout=5.0)

        assert result == "Hello world"
        interactive_manager.audio_recorder.record.assert_called_once_with(duration=5.0)
        interactive_manager.speech2text.transcribe.assert_called_once_with(mock_audio)

    def test_get_user_speech_failure(self, interactive_manager):
        """Test speech capture failure scenarios."""
        prototype = InteractivePrototype(interactive_manager)

        # No audio recorded
        interactive_manager.audio_recorder.record.return_value = None
        result = prototype.get_user_speech()
        assert result is None

        # Audio recorded but no transcription
        interactive_manager.audio_recorder.record.return_value = b"audio"
        interactive_manager.speech2text.transcribe.return_value = None
        result = prototype.get_user_speech()
        assert result is None

        # Exception during recording
        interactive_manager.audio_recorder.record.side_effect = Exception(
            "Recording failed"
        )
        result = prototype.get_user_speech()
        assert result is None


class TestAIPrototype:
    """Test the AIPrototype class."""

    @pytest.fixture
    def ai_manager(self, mock_manager):
        """Manager with AI tools."""
        mock_manager.gpt4 = Mock()
        mock_manager.text2speech = Mock()
        mock_manager.dalle = Mock()
        mock_manager.sdxl = Mock()
        return mock_manager

    def test_initialization(self, ai_manager):
        """Test AI prototype initialization."""
        prototype = AIPrototype(ai_manager)

        assert prototype.llm == ai_manager.gpt4
        assert prototype.text2speech == ai_manager.text2speech
        assert prototype.dalle == ai_manager.dalle
        assert prototype.sdxl == ai_manager.sdxl

    def test_generate_text_success(self, ai_manager):
        """Test successful text generation."""
        prototype = AIPrototype(ai_manager)

        ai_manager.gpt4.chat.return_value = "Generated text"

        result = prototype.generate_text("Test prompt", temperature=0.7)

        assert result == "Generated text"
        ai_manager.gpt4.chat.assert_called_once_with("Test prompt", temperature=0.7)

    def test_generate_text_failure(self, ai_manager):
        """Test text generation failure."""
        prototype = AIPrototype(ai_manager)

        ai_manager.gpt4.chat.side_effect = Exception("API error")

        result = prototype.generate_text("Test prompt")

        assert result is None

    def test_generate_image_dalle(self, ai_manager):
        """Test image generation with DALL-E."""
        prototype = AIPrototype(ai_manager)

        ai_manager.dalle.generate.return_value = "/path/to/image.jpg"

        result = prototype.generate_image("Test prompt", generator="dalle")

        assert result == "/path/to/image.jpg"
        ai_manager.dalle.generate.assert_called_once_with("Test prompt")

    def test_generate_image_sdxl(self, ai_manager):
        """Test image generation with SDXL."""
        prototype = AIPrototype(ai_manager)

        ai_manager.sdxl.generate.return_value = "/path/to/image.jpg"

        result = prototype.generate_image("Test prompt", generator="sdxl")

        assert result == "/path/to/image.jpg"
        ai_manager.sdxl.generate.assert_called_once_with("Test prompt")

    def test_generate_image_unavailable_generator(self, ai_manager):
        """Test image generation with unavailable generator."""
        prototype = AIPrototype(ai_manager)

        # Remove dalle from manager
        delattr(ai_manager, "dalle")
        prototype.dalle = None

        result = prototype.generate_image("Test prompt", generator="dalle")

        assert result is None

    def test_generate_image_failure(self, ai_manager):
        """Test image generation failure."""
        prototype = AIPrototype(ai_manager)

        ai_manager.dalle.generate.side_effect = Exception("Generation failed")

        result = prototype.generate_image("Test prompt", generator="dalle")

        assert result is None
