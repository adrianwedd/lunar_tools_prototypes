import os
from unittest.mock import MagicMock, patch

import pytest

from src.lunar_tools_art import Manager
from utils import (
    generate_and_play_speech,
    record_and_transcribe_speech,
    save_response_to_file,
)


# Mock LunarTools components
@pytest.fixture
def mock_speech2text():
    mock = MagicMock()
    mock.transcribe.return_value = "test transcription"
    return mock


@pytest.fixture
def mock_text2speech():
    mock = MagicMock()
    return mock


@pytest.fixture
def mock_sound_player():
    mock = MagicMock()
    return mock


@pytest.fixture
def mock_manager():
    # Create a mock Manager instance
    manager = Manager()
    manager.speech2text = MagicMock()
    manager.gpt4 = MagicMock()
    manager.text2speech = MagicMock()
    manager.audio_recorder = MagicMock()
    manager.dalle3 = MagicMock()
    manager.renderer = MagicMock()
    manager.sound_player = MagicMock()
    manager.glif_api = MagicMock()
    manager.logger = MagicMock()
    return manager


def test_record_and_transcribe_speech(mock_speech2text):
    transcription = record_and_transcribe_speech(mock_speech2text, duration=1)
    mock_speech2text.transcribe.assert_called_once_with(duration=1)
    assert transcription == "test transcription"


def test_generate_and_play_speech(mock_text2speech, mock_sound_player):
    text = "Hello, world!"
    filename = "output_speech_test.mp3"
    generate_and_play_speech(mock_text2speech, mock_sound_player, text, filename)
    mock_text2speech.generate.assert_called_once_with(text, filename)
    mock_sound_player.play_sound.assert_called_once_with(filename)


def test_save_response_to_file(tmp_path):
    test_content = "This is a test response."
    test_prefix = "test_response"
    with patch("utils.datetime.datetime") as mock_dt:
        mock_dt.now.return_value.strftime.return_value = "20240101_120000"
        filename = save_response_to_file(test_content, test_prefix)
        expected_filename = f".output/{test_prefix}_20240101_120000.txt"
        assert filename == expected_filename
        # Check if the file was created in the .output directory
        assert os.path.exists(expected_filename)
        with open(filename) as f:
            content = f.read()
        assert content == test_content
