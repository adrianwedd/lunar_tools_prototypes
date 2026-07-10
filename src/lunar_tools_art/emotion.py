# src/lunar_tools_art/emotion.py
"""Facial emotion detection with fallback chain.

Fallback: OpenCV Haar cascade (face detection) + lightweight classifier.
Future: MLX emotion model (gated on validation benchmarks).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import cv2
import numpy as np

from .config import config

log = logging.getLogger(__name__)

EMOTIONS = ["anger", "contempt", "fear", "joy", "neutral", "sadness", "surprise"]

# FER+ model output order (onnx/models emotion-ferplus-8.onnx).
FERPLUS_LABELS = [
    "neutral",
    "happiness",
    "surprise",
    "sadness",
    "anger",
    "disgust",
    "fear",
    "contempt",
]


@dataclass
class EmotionResult:
    bbox: tuple[int, int, int, int]  # x, y, w, h
    emotions: dict[str, float]
    primary_emotion: str
    confidence: float


class EmotionDetector:
    def __init__(self, model_path: str | None = None):
        self._has_classifier = False
        self._placeholder_warned = False
        self._net = None
        try:
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            self._face_cascade = cv2.CascadeClassifier(cascade_path)
            if self._face_cascade.empty():
                log.warning("Haar cascade failed to load")
                self._face_cascade = None
        except Exception as e:
            log.warning(f"Could not initialize face detector: {e}")
            self._face_cascade = None

        if model_path is None:
            model_path = config.get("emotion.model_path")
        self._load_classifier(model_path)

    def _load_classifier(self, model_path: str | None) -> None:
        if not model_path:
            return
        if not os.path.isfile(model_path):
            log.warning(f"Emotion model path does not exist: {model_path}")
            return
        try:
            self._net = cv2.dnn.readNetFromONNX(model_path)
            self._has_classifier = True
            log.info(f"Loaded FER+ ONNX emotion classifier from {model_path}")
        except Exception as e:
            log.warning(f"Could not load ONNX emotion classifier: {e}")
            self._net = None
            self._has_classifier = False

    @property
    def has_classifier(self) -> bool:
        """True if a real emotion classifier is loaded (not the placeholder)."""
        return self._has_classifier

    def detect(self, frame: np.ndarray) -> list[EmotionResult]:
        if self._face_cascade is None:
            return []

        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
            faces = self._face_cascade.detectMultiScale(gray, 1.1, 4, minSize=(60, 60))

            results = []
            for x, y, w, h in faces:
                emotions = self._classify_emotion(gray[y : y + h, x : x + w])
                primary = max(emotions, key=emotions.get)
                # Placeholder classifier: confidence is 0.0 to signal unreliable
                confidence = emotions[primary] if self._has_classifier else 0.0
                results.append(
                    EmotionResult(
                        bbox=(int(x), int(y), int(w), int(h)),
                        emotions=emotions,
                        primary_emotion=primary,
                        confidence=confidence,
                    )
                )
            return results
        except Exception as e:
            log.error(f"Emotion detection failed: {e}")
            return []

    def _classify_emotion(self, face_roi: np.ndarray) -> dict[str, float]:
        """Classify emotion from face ROI.

        Fallback chain: ONNX FER+ DNN model (if loaded) -> placeholder
        returning neutral with confidence=0.
        """
        if self._has_classifier and self._net is not None:
            try:
                return self._classify_emotion_onnx(face_roi)
            except Exception as e:
                log.error(f"ONNX emotion classification failed, using placeholder: {e}")

        if not self._placeholder_warned:
            log.warning(
                "EmotionDetector using placeholder classifier — emotions are not real. "
                "Replace with ONNX/MLX model for actual emotion detection."
            )
            self._placeholder_warned = True
        return {e: (0.8 if e == "neutral" else 0.03) for e in EMOTIONS}

    def _classify_emotion_onnx(self, face_roi: np.ndarray) -> dict[str, float]:
        """Run the ONNX FER+ model on a 64x64 grayscale face ROI."""
        resized = cv2.resize(face_roi, (64, 64))
        blob = cv2.dnn.blobFromImage(resized, scalefactor=1.0, size=(64, 64))
        self._net.setInput(blob)
        logits = self._net.forward()
        logits = np.asarray(logits).reshape(-1)
        exp = np.exp(logits - np.max(logits))
        probs = exp / exp.sum()
        return {label: float(prob) for label, prob in zip(FERPLUS_LABELS, probs)}
