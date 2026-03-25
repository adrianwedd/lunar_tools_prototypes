# tests/test_emotion.py
from unittest.mock import patch

import numpy as np

from src.lunar_tools_art.emotion import EmotionDetector, EmotionResult


def test_emotion_result_fields():
    r = EmotionResult(
        bbox=(10, 20, 100, 100),
        emotions={"joy": 0.8, "neutral": 0.2},
        primary_emotion="joy",
        confidence=0.8,
    )
    assert r.primary_emotion == "joy"
    assert r.confidence == 0.8


def test_detect_returns_list():
    detector = EmotionDetector()
    # Black frame — no faces expected
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    results = detector.detect(frame)
    assert isinstance(results, list)


def test_detect_with_mocked_face():
    detector = EmotionDetector()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    # Mock the face cascade to return one face
    with patch.object(detector, "_face_cascade") as mock_cascade:
        mock_cascade.detectMultiScale.return_value = np.array([[100, 100, 200, 200]])
        # Mock emotion classifier to return probabilities
        with patch.object(detector, "_classify_emotion") as mock_classify:
            mock_classify.return_value = {"joy": 0.7, "neutral": 0.3}
            results = detector.detect(frame)
            assert len(results) == 1
            assert results[0].primary_emotion == "joy"


def test_detect_graceful_on_no_cascade():
    """If OpenCV cascade fails to load, detect returns empty list."""
    detector = EmotionDetector()
    detector._face_cascade = None
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    results = detector.detect(frame)
    assert results == []


def test_has_classifier_is_false_for_placeholder():
    detector = EmotionDetector()
    assert detector.has_classifier is False


def test_placeholder_confidence_is_zero():
    """Placeholder classifier should set confidence to 0.0 to signal unreliable."""
    detector = EmotionDetector()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    with patch.object(detector, "_face_cascade") as mock_cascade:
        mock_cascade.detectMultiScale.return_value = np.array([[100, 100, 200, 200]])
        results = detector.detect(frame)
        assert len(results) == 1
        assert results[0].confidence == 0.0  # placeholder = unreliable
