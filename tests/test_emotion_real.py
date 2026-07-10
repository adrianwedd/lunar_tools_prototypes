# tests/test_emotion_real.py
"""Tests for the real ONNX FER+ emotion classifier path."""
from unittest.mock import patch

import numpy as np
import pytest

from src.lunar_tools_art.emotion import EmotionDetector


class _StubNet:
    """Stub cv2.dnn net whose forward() yields logits peaking at 'happiness'."""

    def setInput(self, blob):
        self._blob = blob

    def forward(self):
        # FER+ order: neutral, happiness, surprise, sadness, anger, disgust, fear, contempt
        logits = np.array([[0.1, 5.0, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1]], dtype=np.float32)
        return logits


@pytest.fixture
def tmp_fake_onnx(tmp_path):
    p = tmp_path / "emotion-ferplus-8.onnx"
    p.write_bytes(b"fake-onnx-bytes")
    return p


def test_has_classifier_true_with_model_path(tmp_fake_onnx):
    with patch("cv2.dnn.readNetFromONNX", return_value=_StubNet()) as mock_read:
        detector = EmotionDetector(model_path=str(tmp_fake_onnx))
        mock_read.assert_called_once_with(str(tmp_fake_onnx))
    assert detector.has_classifier is True


def test_detect_reports_real_emotion_and_confidence(tmp_fake_onnx):
    with patch("cv2.dnn.readNetFromONNX", return_value=_StubNet()):
        detector = EmotionDetector(model_path=str(tmp_fake_onnx))

    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    with patch.object(detector, "_face_cascade") as mock_cascade:
        mock_cascade.detectMultiScale.return_value = np.array([[100, 100, 200, 200]])
        results = detector.detect(frame)

    assert len(results) == 1
    assert results[0].primary_emotion == "happiness"
    assert results[0].confidence > 0.5


def test_missing_model_path_keeps_placeholder_behavior():
    detector = EmotionDetector(model_path=None)
    assert detector.has_classifier is False


def test_nonexistent_model_path_falls_back_to_placeholder():
    detector = EmotionDetector(model_path="/nonexistent/path/model.onnx")
    assert detector.has_classifier is False
