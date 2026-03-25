"""Smoke tests for the AI Mirror of Truth prototype."""

import importlib
from unittest.mock import MagicMock

import numpy as np


def _import_mirror():
    """Import the hyphenated prototype module."""
    loader = importlib.machinery.SourceFileLoader(
        "ai_mirror_of_truth",
        "prototypes/ai-mirror-of-truth.py",
    )
    spec = importlib.util.spec_from_loader("ai_mirror_of_truth", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def test_mirror_of_truth_smoke():
    """Verify AiMirrorOfTruth can setup, update, and cleanup without error."""
    mod = _import_mirror()
    AiMirrorOfTruth = mod.AiMirrorOfTruth

    manager = MagicMock()
    manager.keyboard_input.is_key_pressed.return_value = True  # exit immediately
    manager.webcam.get_img.return_value = np.zeros((480, 640, 3), dtype=np.uint8)
    manager.llm_backend = MagicMock()
    manager.llm_backend.generate.return_value = (
        '{"name": "Echo", "personality_traits": ["reflective"], '
        '"speaking_style": "poetic", "visual_characteristics": "ethereal", '
        '"emotional_resonance": "mirrors feelings", '
        '"greeting_message": "I see you..."}'
    )
    manager.emotion_detector = MagicMock()
    manager.emotion_detector.detect.return_value = []
    manager.prosody_analyzer = MagicMock()
    manager.voice_client = MagicMock()
    manager.voice_client.health.return_value = {"status": "ok", "voices": ["galadriel"]}
    manager.renderer = MagicMock()

    mirror = AiMirrorOfTruth(manager)
    mirror.setup()
    mirror.update()
    mirror.cleanup()
    # Should complete without error


def test_mirror_of_truth_with_face_detected():
    """Verify update handles emotion detections correctly."""
    mod = _import_mirror()
    AiMirrorOfTruth = mod.AiMirrorOfTruth

    manager = MagicMock()
    manager.keyboard_input.is_key_pressed.return_value = False
    manager.webcam.get_img.return_value = np.zeros((480, 640, 3), dtype=np.uint8)
    manager.llm_backend = MagicMock()
    manager.emotion_detector = MagicMock()
    manager.emotion_detector.detect.return_value = [
        {"primary": "joy", "intensity": 0.8, "secondary": "surprise"}
    ]
    manager.prosody_analyzer = MagicMock()
    manager.voice_client = MagicMock()
    manager.voice_client.health.return_value = {"status": "ok", "voices": ["galadriel"]}
    manager.renderer = MagicMock()

    mirror = AiMirrorOfTruth(manager)
    mirror.setup()
    mirror.update()

    assert mirror.current_emotions["primary"] == "joy"
    assert mirror.current_emotions["face_detected"] is True
    assert len(mirror.emotion_trajectory) == 1
    assert mirror.emotion_trajectory[0] == "joy"

    mirror.cleanup()


def test_mirror_of_truth_voice_server_down():
    """Verify setup handles unavailable Afterwords server gracefully."""
    mod = _import_mirror()
    AiMirrorOfTruth = mod.AiMirrorOfTruth

    manager = MagicMock()
    manager.keyboard_input.is_key_pressed.return_value = True
    manager.webcam.get_img.return_value = np.zeros((480, 640, 3), dtype=np.uint8)
    manager.llm_backend = MagicMock()
    manager.emotion_detector = MagicMock()
    manager.emotion_detector.detect.return_value = []
    manager.prosody_analyzer = MagicMock()
    manager.voice_client = MagicMock()
    manager.voice_client.health.side_effect = ConnectionError("Server down")
    manager.renderer = MagicMock()

    mirror = AiMirrorOfTruth(manager)
    # Should not raise even though voice server is down
    mirror.setup()
    mirror.cleanup()
