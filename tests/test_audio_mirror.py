from unittest.mock import MagicMock

import numpy as np


def test_audio_mirror_smoke():
    """Basic setup/update/cleanup cycle."""
    from prototypes.audio_mirror import AudioMirror

    manager = MagicMock()
    manager.keyboard_input.is_key_pressed.return_value = False
    manager.webcam.get_img.return_value = np.zeros((480, 640, 3), dtype=np.uint8)
    manager.llm_backend = MagicMock()
    manager.emotion_detector = MagicMock()
    manager.emotion_detector.detect.return_value = []
    manager.prosody_analyzer = MagicMock()
    manager.voice_client = MagicMock()
    manager.voice_client.health.return_value = {
        "status": "ok",
        "ready": True,
        "voices": ["galadriel"],
    }
    manager.renderer = MagicMock()
    manager.audio_recorder = MagicMock()
    manager.speech2text = MagicMock()

    mirror = AudioMirror(manager)
    mirror.setup()
    mirror.update()  # IDLE, no face -> stays idle
    mirror.cleanup()


def test_audio_mirror_face_triggers_detection():
    """Face detection transitions FSM to DETECTION."""
    from prototypes.audio_mirror import AudioMirror
    from src.lunar_tools_art.emotion import EmotionResult

    manager = MagicMock()
    manager.keyboard_input.is_key_pressed.return_value = False
    manager.webcam.get_img.return_value = np.zeros((480, 640, 3), dtype=np.uint8)
    manager.emotion_detector.detect.return_value = [
        EmotionResult(
            bbox=(100, 100, 200, 200),
            emotions={"neutral": 0.8},
            primary_emotion="neutral",
            confidence=0.0,
        )
    ]
    manager.voice_client = MagicMock()
    manager.voice_client.health.return_value = {
        "status": "ok",
        "ready": True,
        "voices": ["galadriel"],
    }
    manager.voice_client.synthesize.return_value = b"fake-wav"
    manager.renderer = MagicMock()

    mirror = AudioMirror(manager)
    mirror.setup()
    mirror.update()
    assert mirror.fsm.state == "DETECTION"
    mirror.cleanup()


def test_audio_mirror_cleanup_calls_session():
    """Cleanup sends DELETE /session to Afterwords."""
    from prototypes.audio_mirror import AudioMirror

    manager = MagicMock()
    manager.keyboard_input.is_key_pressed.return_value = False
    manager.webcam.get_img.return_value = np.zeros((480, 640, 3), dtype=np.uint8)
    manager.emotion_detector.detect.return_value = []
    manager.voice_client = MagicMock()
    manager.voice_client.health.return_value = {
        "status": "ok",
        "ready": True,
        "voices": ["galadriel"],
    }
    manager.renderer = MagicMock()

    mirror = AudioMirror(manager)
    mirror.setup()
    # Simulate active session
    mirror.fsm.on_face_detected()
    mirror.cleanup()
    manager.voice_client.cleanup_session.assert_called_once_with(mirror.session_id)
