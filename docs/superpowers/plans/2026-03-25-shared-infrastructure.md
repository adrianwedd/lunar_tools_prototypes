# Shared Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared infrastructure components (LLM backends, prosody analyzer, emotion detector, voice client) that both the Mirror of Truth rewrite and Audio Mirror prototypes depend on.

**Architecture:** Four new modules in `src/lunar_tools_art/` with clean interfaces. LLM backends abstract Claude/Ollama/OllamaCloud/OpenRouter behind a common `.generate()` interface. Prosody uses librosa (CPU, no ML). Emotion detection uses OpenCV DNN with ONNX model as initial fallback (MLX model is a validation gate — start with the fallback). Voice client wraps Afterwords HTTP API with httpx.

**Tech Stack:** Python 3.11+, httpx, librosa, opencv-python, anthropic SDK, toml config

**Important notes for implementers:**
- All `.generate()` methods return `str | None` (not just `str` as in the spec). Callers must handle `None` (meaning the LLM call failed). This is a deliberate defensive deviation from the spec.
- LLM backends use `requests` (already in requirements, simpler for sync calls). Voice client uses `httpx` (needed for multipart uploads and async-ready). This is intentional, not an inconsistency.
- When a task says "add these imports and tests to `tests/test_llm_backends.py`", put the `import` and `from` lines at the **top of the file** with the existing imports, and the test functions at the **bottom**.
- The `_classify_emotion` method in the emotion detector is a placeholder. The real ONNX/MLX model will be added in a separate plan after the validation gate benchmarks pass.

**Spec:** `docs/superpowers/specs/2026-03-25-audio-mirror-and-mlx-migration-design.md`

**Dependency chain:** This plan → Afterwords extensions (separate repo/plan) → Mirror of Truth rewrite → Audio Mirror experiment. This plan has no external blockers.

---

### Task 1: LLM Backend Abstraction — OllamaLocalBackend

**Files:**
- Create: `src/lunar_tools_art/llm_backends.py`
- Create: `tests/test_llm_backends.py`

- [ ] **Step 1: Write the failing test for LLMBackend ABC and OllamaLocalBackend**

```python
# tests/test_llm_backends.py
import os

import pytest
from unittest.mock import patch, MagicMock

from src.lunar_tools_art.llm_backends import (
    LLMBackend,
    OllamaLocalBackend,
    create_backend,
)


def test_llm_backend_is_abstract():
    with pytest.raises(TypeError):
        LLMBackend()


def test_ollama_local_generate():
    backend = OllamaLocalBackend(model="llama3.1:8b", base_url="http://localhost:11434")
    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"response": "Hello world"},
        )
        mock_post.return_value.raise_for_status = MagicMock()
        result = backend.generate("Say hello")
        assert result == "Hello world"
        mock_post.assert_called_once()
        call_json = mock_post.call_args[1]["json"]
        assert call_json["prompt"] == "Say hello"
        assert call_json["model"] == "llama3.1:8b"


def test_ollama_local_generate_with_system_prompt():
    backend = OllamaLocalBackend(model="llama3.1:8b")
    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"response": "I am an oracle."},
        )
        mock_post.return_value.raise_for_status = MagicMock()
        result = backend.generate("Who are you?", system_prompt="You are an oracle.")
        assert result == "I am an oracle."
        call_json = mock_post.call_args[1]["json"]
        assert call_json["system"] == "You are an oracle."


def test_ollama_local_returns_none_on_error():
    backend = OllamaLocalBackend(model="llama3.1:8b")
    with patch("requests.post", side_effect=Exception("Connection refused")):
        result = backend.generate("hello")
        assert result is None


def test_create_backend_ollama():
    config = {"provider": "ollama", "ollama": {"model": "llama3.1:8b", "base_url": "http://localhost:11434"}}
    backend = create_backend(config)
    assert isinstance(backend, OllamaLocalBackend)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_llm_backends.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.lunar_tools_art.llm_backends'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/lunar_tools_art/llm_backends.py
"""Pluggable LLM backend abstraction.

Supports: Ollama (local), Ollama Cloud, Claude API, OpenRouter.
All backends implement .generate(prompt, system_prompt) -> str | None.
Selected via settings.toml [llm] section.
"""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod

import requests

log = logging.getLogger(__name__)


class LLMBackend(ABC):
    @abstractmethod
    def generate(self, prompt: str, system_prompt: str | None = None) -> str | None:
        ...


class OllamaLocalBackend(LLMBackend):
    def __init__(self, model: str = "llama3.1:8b", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def generate(self, prompt: str, system_prompt: str | None = None) -> str | None:
        try:
            data: dict = {"model": self.model, "prompt": prompt, "stream": False}
            if system_prompt:
                data["system"] = system_prompt
            resp = requests.post(f"{self.base_url}/api/generate", json=data)
            resp.raise_for_status()
            return resp.json().get("response", "")
        except Exception as e:
            log.error("Ollama local generate failed: %s", e)
            return None


def create_backend(config: dict) -> LLMBackend:
    """Create an LLM backend from a config dict (the [llm] section of settings.toml)."""
    provider = config.get("provider", "ollama")
    if provider == "ollama":
        ollama_cfg = config.get("ollama", {})
        return OllamaLocalBackend(
            model=ollama_cfg.get("model", "llama3.1:8b"),
            base_url=ollama_cfg.get("base_url", "http://localhost:11434"),
        )
    raise ValueError(f"Unknown LLM provider: {provider}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_llm_backends.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/lunar_tools_art/llm_backends.py tests/test_llm_backends.py
git commit -m "feat: add LLM backend abstraction with OllamaLocalBackend"
```

---

### Task 2: LLM Backend — ClaudeBackend

**Files:**
- Modify: `src/lunar_tools_art/llm_backends.py`
- Modify: `tests/test_llm_backends.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_llm_backends.py
from src.lunar_tools_art.llm_backends import ClaudeBackend


def test_claude_generate():
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):  # pragma: allowlist secret
        backend = ClaudeBackend(model="claude-sonnet-4-20250514")
    with patch.object(backend, "_client") as mock_client:
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="Insight delivered.")]
        mock_client.messages.create.return_value = mock_msg
        result = backend.generate("Analyze this", system_prompt="You are an oracle")
        assert result == "Insight delivered."


def test_claude_returns_none_on_error():
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        backend = ClaudeBackend(model="claude-sonnet-4-20250514")
    backend._client.messages.create = MagicMock(side_effect=Exception("API error"))
    result = backend.generate("hello")
    assert result is None


def test_create_backend_claude():
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):  # pragma: allowlist secret
        config = {"provider": "claude", "claude": {"model": "claude-sonnet-4-20250514", "api_key_env": "ANTHROPIC_API_KEY"}}  # pragma: allowlist secret
        backend = create_backend(config)
        assert isinstance(backend, ClaudeBackend)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_llm_backends.py::test_claude_generate -v`
Expected: FAIL with `ImportError: cannot import name 'ClaudeBackend'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/lunar_tools_art/llm_backends.py`:

```python
class ClaudeBackend(LLMBackend):
    def __init__(self, model: str = "claude-sonnet-4-20250514", api_key_env: str = "ANTHROPIC_API_KEY"):
        import anthropic
        self.model = model
        self._client = anthropic.Anthropic(api_key=os.environ.get(api_key_env))

    def generate(self, prompt: str, system_prompt: str | None = None) -> str | None:
        try:
            kwargs: dict = {
                "model": self.model,
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system_prompt:
                kwargs["system"] = system_prompt
            msg = self._client.messages.create(**kwargs)
            return msg.content[0].text
        except Exception as e:
            log.error("Claude generate failed: %s", e)
            return None
```

Update `create_backend`:
```python
    if provider == "claude":
        claude_cfg = config.get("claude", {})
        return ClaudeBackend(
            model=claude_cfg.get("model", "claude-sonnet-4-20250514"),
            api_key_env=claude_cfg.get("api_key_env", "ANTHROPIC_API_KEY"),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_llm_backends.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/lunar_tools_art/llm_backends.py tests/test_llm_backends.py
git commit -m "feat: add ClaudeBackend to LLM abstraction"
```

---

### Task 3: LLM Backend — OllamaCloudBackend and OpenRouterBackend

**Files:**
- Modify: `src/lunar_tools_art/llm_backends.py`
- Modify: `tests/test_llm_backends.py`

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_llm_backends.py
from src.lunar_tools_art.llm_backends import OllamaCloudBackend, OpenRouterBackend


def test_ollama_cloud_generate():
    with patch.dict(os.environ, {"OLLAMA_CLOUD_API_KEY": "test-key"}):
        backend = OllamaCloudBackend(model="llama3.1:70b")
    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"choices": [{"message": {"content": "Cloud response"}}]},
        )
        mock_post.return_value.raise_for_status = MagicMock()
        result = backend.generate("hello")
        assert result == "Cloud response"


def test_openrouter_generate():
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
        backend = OpenRouterBackend(model="meta-llama/llama-3.1-8b-instruct:free")
    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"choices": [{"message": {"content": "Router response"}}]},
        )
        mock_post.return_value.raise_for_status = MagicMock()
        result = backend.generate("hello")
        assert result == "Router response"


def test_create_backend_all_providers():
    providers = {
        "ollama": OllamaLocalBackend,
        "ollama-cloud": OllamaCloudBackend,
        "openrouter": OpenRouterBackend,
    }
    for provider_name, expected_class in providers.items():
        with patch.dict(os.environ, {"OLLAMA_CLOUD_API_KEY": "k", "OPENROUTER_API_KEY": "k"}):
            config = {"provider": provider_name}
            backend = create_backend(config)
            assert isinstance(backend, expected_class), f"Failed for {provider_name}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_llm_backends.py::test_ollama_cloud_generate -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Add to `src/lunar_tools_art/llm_backends.py`:

```python
class OllamaCloudBackend(LLMBackend):
    """Ollama Cloud — OpenAI-compatible chat API with generous free tier."""

    def __init__(self, model: str = "llama3.1:70b", api_key_env: str = "OLLAMA_CLOUD_API_KEY"):
        self.model = model
        self.api_key = os.environ.get(api_key_env, "")
        self.base_url = "https://api.ollama.com/v1"

    def generate(self, prompt: str, system_prompt: str | None = None) -> str | None:
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "messages": messages},
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            log.error("Ollama Cloud generate failed: %s", e)
            return None


class OpenRouterBackend(LLMBackend):
    """OpenRouter — free-tier access to many models via OpenAI-compatible API."""

    def __init__(self, model: str = "meta-llama/llama-3.1-8b-instruct:free", api_key_env: str = "OPENROUTER_API_KEY"):
        self.model = model
        self.api_key = os.environ.get(api_key_env, "")
        self.base_url = "https://openrouter.ai/api/v1"

    def generate(self, prompt: str, system_prompt: str | None = None) -> str | None:
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "messages": messages},
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            log.error("OpenRouter generate failed: %s", e)
            return None
```

Update `create_backend` to handle `"ollama-cloud"` and `"openrouter"`.

- [ ] **Step 4: Run all LLM backend tests**

Run: `pytest tests/test_llm_backends.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/lunar_tools_art/llm_backends.py tests/test_llm_backends.py
git commit -m "feat: add OllamaCloud and OpenRouter LLM backends"
```

---

### Task 4: Prosody Analyzer

**Files:**
- Create: `src/lunar_tools_art/prosody.py`
- Create: `tests/test_prosody.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_prosody.py
import numpy as np
import pytest

from src.lunar_tools_art.prosody import ProsodyAnalyzer, ProsodyResult


def test_prosody_result_fields():
    r = ProsodyResult(
        pitch_mean=200.0,
        pitch_variance=15.0,
        energy_rms=0.5,
        pace_wps=0.0,
        pauses=[],
        spectral_centroid=1500.0,
        emotion_tag="neutral",
    )
    assert r.pitch_mean == 200.0
    assert r.emotion_tag == "neutral"


def test_analyze_sine_wave():
    """A pure 220Hz sine wave should have pitch_mean near 220."""
    sr = 22050
    duration = 2.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    audio = 0.5 * np.sin(2 * np.pi * 220 * t).astype(np.float32)

    analyzer = ProsodyAnalyzer()
    result = analyzer.analyze(audio, sr)

    assert isinstance(result, ProsodyResult)
    assert 180 < result.pitch_mean < 260  # near 220Hz
    assert result.energy_rms > 0.0
    assert result.spectral_centroid > 0.0


def test_analyze_silence():
    """Silent audio should produce low energy and neutral emotion."""
    sr = 22050
    audio = np.zeros(sr * 2, dtype=np.float32)

    analyzer = ProsodyAnalyzer()
    result = analyzer.analyze(audio, sr)

    assert result.energy_rms < 0.01
    assert result.emotion_tag == "neutral"


def test_emotion_tag_from_prosody():
    """High energy + high pitch variance → agitated."""
    sr = 22050
    # Generate noisy, energetic audio
    rng = np.random.default_rng(42)
    audio = (rng.random(sr * 2) * 2 - 1).astype(np.float32) * 0.8

    analyzer = ProsodyAnalyzer()
    result = analyzer.analyze(audio, sr)
    # Should not crash, emotion_tag should be a string
    assert isinstance(result.emotion_tag, str)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_prosody.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/lunar_tools_art/prosody.py
"""Voice prosody analysis using librosa.

Pure signal processing — no ML models. Extracts pitch, energy, pace,
pauses, and spectral features from audio. Infers a coarse emotion tag
from prosody features.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import librosa
import numpy as np


@dataclass
class PauseEvent:
    at: float  # seconds
    duration: float  # seconds


@dataclass
class ProsodyResult:
    pitch_mean: float
    pitch_variance: float
    energy_rms: float
    pace_wps: float  # 0.0 if no transcript alignment
    pauses: list[PauseEvent] = field(default_factory=list)
    spectral_centroid: float = 0.0
    emotion_tag: str = "neutral"


class ProsodyAnalyzer:
    def analyze(self, audio: np.ndarray, sr: int) -> ProsodyResult:
        # Ensure float32 mono
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        audio = audio.astype(np.float32)

        # Energy
        energy_rms = float(np.sqrt(np.mean(audio ** 2)))

        # Pitch (F0) via pyin
        f0, voiced_flag, _ = librosa.pyin(
            audio, fmin=80, fmax=600, sr=sr
        )
        voiced_f0 = f0[voiced_flag] if voiced_flag is not None else f0[~np.isnan(f0)]
        if len(voiced_f0) == 0:
            pitch_mean = 0.0
            pitch_variance = 0.0
        else:
            pitch_mean = float(np.nanmean(voiced_f0))
            pitch_variance = float(np.nanstd(voiced_f0))

        # Spectral centroid
        cent = librosa.feature.spectral_centroid(y=audio, sr=sr)
        spectral_centroid = float(np.mean(cent)) if cent.size > 0 else 0.0

        # Pause detection (energy-based)
        frame_length = int(0.025 * sr)
        hop_length = int(0.010 * sr)
        rms_frames = librosa.feature.rms(y=audio, frame_length=frame_length, hop_length=hop_length)[0]
        silence_threshold = 0.02
        pauses: list[PauseEvent] = []
        in_pause = False
        pause_start = 0.0
        for i, rms_val in enumerate(rms_frames):
            t = i * hop_length / sr
            if rms_val < silence_threshold:
                if not in_pause:
                    in_pause = True
                    pause_start = t
            else:
                if in_pause:
                    dur = t - pause_start
                    if dur > 0.3:  # only count pauses > 300ms
                        pauses.append(PauseEvent(at=pause_start, duration=dur))
                    in_pause = False

        # Emotion tag from prosody heuristics
        emotion_tag = _infer_emotion(energy_rms, pitch_mean, pitch_variance)

        return ProsodyResult(
            pitch_mean=pitch_mean,
            pitch_variance=pitch_variance,
            energy_rms=energy_rms,
            pace_wps=0.0,
            pauses=pauses,
            spectral_centroid=spectral_centroid,
            emotion_tag=emotion_tag,
        )


def _infer_emotion(energy: float, pitch_mean: float, pitch_var: float) -> str:
    """Coarse emotion from prosody. Not a classifier — a heuristic."""
    if energy < 0.01:
        return "neutral"
    if energy > 0.4 and pitch_var > 30:
        return "agitated"
    if energy > 0.3 and pitch_mean > 250:
        return "excited"
    if energy < 0.15 and pitch_mean < 180:
        return "subdued"
    if pitch_var < 10 and energy < 0.25:
        return "calm"
    return "neutral"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_prosody.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/lunar_tools_art/prosody.py tests/test_prosody.py
git commit -m "feat: add prosody analyzer with librosa-based signal processing"
```

---

### Task 5: Emotion Detector (OpenCV DNN fallback)

**Files:**
- Create: `src/lunar_tools_art/emotion.py`
- Create: `tests/test_emotion.py`

Note: This implements the OpenCV DNN ONNX fallback path from the spec's fallback chain. The MLX model path is gated on the validation benchmarks and will be added later.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_emotion.py
import numpy as np
import pytest
from unittest.mock import patch, MagicMock

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_emotion.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/lunar_tools_art/emotion.py
"""Facial emotion detection with fallback chain.

Fallback: OpenCV Haar cascade (face detection) + lightweight classifier.
Future: MLX emotion model (gated on validation benchmarks).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import cv2
import numpy as np

log = logging.getLogger(__name__)

EMOTIONS = ["anger", "contempt", "fear", "joy", "neutral", "sadness", "surprise"]


@dataclass
class EmotionResult:
    bbox: tuple[int, int, int, int]  # x, y, w, h
    emotions: dict[str, float]
    primary_emotion: str
    confidence: float


class EmotionDetector:
    def __init__(self):
        try:
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            self._face_cascade = cv2.CascadeClassifier(cascade_path)
            if self._face_cascade.empty():
                log.warning("Haar cascade failed to load")
                self._face_cascade = None
        except Exception as e:
            log.warning("Could not initialize face detector: %s", e)
            self._face_cascade = None

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
                results.append(
                    EmotionResult(
                        bbox=(int(x), int(y), int(w), int(h)),
                        emotions=emotions,
                        primary_emotion=primary,
                        confidence=emotions[primary],
                    )
                )
            return results
        except Exception as e:
            log.error("Emotion detection failed: %s", e)
            return []

    def _classify_emotion(self, face_roi: np.ndarray) -> dict[str, float]:
        """Classify emotion from face ROI.

        Current implementation: heuristic placeholder.
        To be replaced with ONNX DNN model or MLX model after validation.
        """
        # Placeholder: return neutral with high confidence
        # This will be replaced when we find a suitable ONNX/MLX model
        return {e: (0.8 if e == "neutral" else 0.03) for e in EMOTIONS}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_emotion.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/lunar_tools_art/emotion.py tests/test_emotion.py
git commit -m "feat: add emotion detector with OpenCV face detection fallback"
```

---

### Task 6: Voice Client (Afterwords HTTP wrapper)

**Files:**
- Create: `src/lunar_tools_art/voice_client.py`
- Create: `tests/test_voice_client.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_voice_client.py
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from src.lunar_tools_art.voice_client import VoiceClient, CloneResult


def test_health_returns_dict():
    client = VoiceClient(server_url="http://localhost:7860")
    with patch("httpx.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"status": "ok", "ready": True, "voices": ["galadriel"]},
        )
        result = client.health()
        assert result["status"] == "ok"
        assert "galadriel" in result["voices"]


def test_list_voices():
    client = VoiceClient()
    with patch("httpx.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"status": "ok", "voices": ["galadriel", "snape"]},
        )
        voices = client.list_voices()
        assert voices == ["galadriel", "snape"]


def test_synthesize_returns_bytes():
    client = VoiceClient()
    with patch("httpx.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            content=b"RIFF\x00\x00\x00\x00WAVEfmt ",
            headers={"content-type": "audio/wav"},
        )
        result = client.synthesize("Hello world", voice="galadriel")
        assert isinstance(result, bytes)
        assert len(result) > 0


def test_synthesize_with_emotion():
    client = VoiceClient()
    with patch("httpx.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            content=b"RIFF\x00\x00\x00\x00WAVEfmt ",
            headers={"content-type": "audio/wav"},
        )
        result = client.synthesize("I understand", voice="viewer-abc", emotion="vulnerable")
        assert isinstance(result, bytes)
        call_json = mock_post.call_args[1]["json"]
        assert call_json["emotion"] == "vulnerable"


def test_clone_voice_returns_result():
    client = VoiceClient()
    with patch("httpx.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "voice": "viewer-abc-001",
                "emotion": "neutral",
                "quality": "rough",
                "transcript_confidence": 0.85,
                "duration_s": 5.2,
                "sequence": 1,
            },
        )
        result = client.clone_voice(
            audio=b"fake-audio-data",
            session_id="abc",
            emotion="neutral",
            transcript="Hello my name is Sarah",
        )
        assert isinstance(result, CloneResult)
        assert result.quality == "rough"
        assert result.voice_name == "viewer-abc-001"


def test_cleanup_session():
    client = VoiceClient()
    with patch("httpx.delete") as mock_delete:
        mock_delete.return_value = MagicMock(status_code=200)
        client.cleanup_session("abc")
        mock_delete.assert_called_once()


def test_health_returns_none_on_error():
    client = VoiceClient()
    with patch("httpx.get", side_effect=Exception("Connection refused")):
        result = client.health()
        assert result is None


def test_synthesize_returns_none_on_non_200():
    client = VoiceClient()
    with patch("httpx.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=503, text="warming up")
        result = client.synthesize("hello", voice="galadriel")
        assert result is None


def test_synthesize_returns_none_on_connection_error():
    client = VoiceClient()
    with patch("httpx.post", side_effect=Exception("Connection refused")):
        result = client.synthesize("hello", voice="galadriel")
        assert result is None


def test_clone_voice_returns_none_on_error():
    client = VoiceClient()
    with patch("httpx.post", side_effect=Exception("Connection refused")):
        result = client.clone_voice(audio=b"data", session_id="abc", emotion="neutral")
        assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_voice_client.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/lunar_tools_art/voice_client.py
"""Client for the Afterwords TTS server.

Wraps /health, /synthesize, /clone, and /session endpoints.
Supports progressive voice palette with emotion-tagged clips.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)


@dataclass
class CloneResult:
    voice_name: str
    emotion: str
    quality: str  # "rough" | "developing" | "good"
    transcript: str
    transcript_confidence: float
    duration_s: float
    sequence: int = 0


class VoiceClient:
    def __init__(self, server_url: str = "http://localhost:7860", timeout: float = 120.0):
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout

    def health(self) -> dict | None:
        try:
            resp = httpx.get(f"{self.server_url}/health", timeout=5.0)
            return resp.json()
        except Exception as e:
            log.error("Afterwords health check failed: %s", e)
            return None

    def list_voices(self) -> list[str]:
        health = self.health()
        if health:
            return health.get("voices", [])
        return []

    def synthesize(self, text: str, voice: str, emotion: str | None = None) -> bytes | None:
        try:
            body: dict = {"text": text, "voice": voice}
            if emotion:
                body["emotion"] = emotion
            resp = httpx.post(
                f"{self.server_url}/synthesize",
                json=body,
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                return resp.content
            log.error("Synthesize failed: %s %s", resp.status_code, resp.text)
            return None
        except Exception as e:
            log.error("Synthesize request failed: %s", e)
            return None

    def clone_voice(
        self,
        audio: bytes,
        session_id: str,
        emotion: str,
        transcript: str | None = None,
    ) -> CloneResult | None:
        try:
            files = {"audio": ("recording.wav", audio, "audio/wav")}
            data: dict = {"session_id": session_id, "emotion": emotion}
            if transcript:
                data["transcript"] = transcript
            resp = httpx.post(
                f"{self.server_url}/clone",
                files=files,
                data=data,
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                j = resp.json()
                return CloneResult(
                    voice_name=j["voice"],
                    emotion=j["emotion"],
                    quality=j["quality"],
                    transcript=transcript or "",
                    transcript_confidence=j.get("transcript_confidence", 0.0),
                    duration_s=j.get("duration_s", 0.0),
                    sequence=j.get("sequence", 0),
                )
            log.error("Clone failed: %s %s", resp.status_code, resp.text)
            return None
        except Exception as e:
            log.error("Clone request failed: %s", e)
            return None

    def cleanup_session(self, session_id: str) -> None:
        try:
            httpx.delete(
                f"{self.server_url}/session/{session_id}",
                timeout=10.0,
            )
        except Exception as e:
            log.warning("Session cleanup failed: %s", e)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_voice_client.py -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/lunar_tools_art/voice_client.py tests/test_voice_client.py
git commit -m "feat: add Afterwords voice client with clone and palette support"
```

---

### Task 7: Update requirements.txt

**Files:**
- Modify: `requirements.txt`

Note: This must come before Manager wiring (Task 8) since that imports `anthropic`, `httpx`, and `cv2`.

- [ ] **Step 1: Add new dependencies**

Add to `requirements.txt`:
```
anthropic>=0.40.0
httpx>=0.27.0
opencv-python>=4.9.0
```

Note: `librosa` and `requests` are already in requirements.txt. `mlx` is not added yet — it's only needed when we implement the MLX emotion model path (gated on validation).

- [ ] **Step 2: Verify install works**

Run: `pip install -r requirements.txt`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "feat: add anthropic, httpx, opencv-python to requirements"
```

---

### Task 8: Update settings.toml and Config

**Files:**
- Modify: `settings.toml`
- Modify: `tests/test_llm_backends.py` (add config integration test)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_llm_backends.py
def test_create_backend_from_toml_config():
    """Verify create_backend works with the shape of config from settings.toml."""
    import toml

    toml_str = """
[llm]
provider = "ollama"

[llm.ollama]
model = "llama3.1:8b"
base_url = "http://localhost:11434"

[llm.claude]
model = "claude-sonnet-4-20250514"
api_key_env = "ANTHROPIC_API_KEY"
"""
    config = toml.loads(toml_str)
    backend = create_backend(config["llm"])
    assert isinstance(backend, OllamaLocalBackend)
    assert backend.model == "llama3.1:8b"
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `pytest tests/test_llm_backends.py::test_create_backend_from_toml_config -v`

- [ ] **Step 3: Update settings.toml**

```toml
[llm]
provider = "ollama"

[llm.ollama]
model = "llama3.1:8b"
base_url = "http://localhost:11434"

[llm.claude]
model = "claude-sonnet-4-20250514"
api_key_env = "ANTHROPIC_API_KEY"  # pragma: allowlist secret

[llm.ollama_cloud]
model = "llama3.1:70b"
api_key_env = "OLLAMA_CLOUD_API_KEY"  # pragma: allowlist secret

[llm.openrouter]
model = "meta-llama/llama-3.1-8b-instruct:free"
api_key_env = "OPENROUTER_API_KEY"  # pragma: allowlist secret

[afterwords]
server_url = "http://localhost:7860"
default_voice = "galadriel"

[emotion]
model = "auto"
confidence_threshold = 0.5
fallback = "haar-cascade"

[whisper]
backend = "faster-whisper"
model = "base.en"

[privacy]
mode = "local-only"
auto_delete_session = true
```

- [ ] **Step 4: Run all tests**

Run: `pytest tests/test_llm_backends.py tests/test_prosody.py tests/test_emotion.py tests/test_voice_client.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add settings.toml tests/test_llm_backends.py
git commit -m "feat: update settings.toml with LLM backends, afterwords, and privacy config"
```

---

### Task 9: Wire into Manager + update __init__.py

**Files:**
- Modify: `src/lunar_tools_art/manager.py`
- Modify: `src/lunar_tools_art/__init__.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_llm_backends.py
def test_manager_has_llm_backend():
    """Verify the Manager initializes an LLM backend from config."""
    from unittest.mock import patch
    from src.lunar_tools_art.manager import LunarToolsArtManager

    with patch("src.lunar_tools_art.manager.create_backend") as mock_create:
        mock_create.return_value = OllamaLocalBackend(model="test")
        manager = LunarToolsArtManager()
        assert hasattr(manager, "llm_backend")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_llm_backends.py::test_manager_has_llm_backend -v`
Expected: FAIL (manager doesn't import or use create_backend yet)

- [ ] **Step 3: Update manager.py**

Add to imports in `manager.py`:
```python
from .llm_backends import create_backend
from .emotion import EmotionDetector
from .prosody import ProsodyAnalyzer
from .voice_client import VoiceClient
```

Add to `__init__` method after existing tool initialization:
```python
        # New infrastructure components
        llm_config = config.get("llm", {})
        self.llm_backend = create_backend(llm_config) if llm_config else None

        self.emotion_detector = EmotionDetector()
        self.prosody_analyzer = ProsodyAnalyzer()

        afterwords_config = config.get("afterwords", {})
        server_url = afterwords_config.get("server_url", "http://localhost:7860") if afterwords_config else "http://localhost:7860"
        self.voice_client = VoiceClient(server_url=server_url)
```

Update `__init__.py` exports:
```python
from .llm_backends import LLMBackend, create_backend
from .emotion import EmotionDetector, EmotionResult
from .prosody import ProsodyAnalyzer, ProsodyResult
from .voice_client import VoiceClient, CloneResult
```

- [ ] **Step 4: Run all tests**

Run: `pytest -v`
Expected: All tests PASS (existing tests should still pass since Manager catches init errors)

- [ ] **Step 5: Commit**

```bash
git add src/lunar_tools_art/manager.py src/lunar_tools_art/__init__.py
git commit -m "feat: wire LLM backends, emotion, prosody, and voice client into Manager"
```

---

## Follow-up Plans

This plan covers the shared infrastructure only. The following plans should be written next, in order:

1. **Afterwords Server Extensions** — `POST /clone`, `POST /synthesize`, runtime voice registry, session cleanup. Implemented and tested in `../afterwords/` repo.
2. **Mirror of Truth Rewrite** — Replace simulated components with real infra from this plan. Depends on Tasks 1-9 above.
3. **Audio Mirror Experiment** — New prototype using all infrastructure. Depends on Afterwords extensions + this plan.

Each gets its own plan document.
