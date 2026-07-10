# Prototype Status Matrix

Generated for Task 11 (prototype sweep). Status is determined by the automated
smoke matrix in `tests/test_prototype_smoke.py` (27 legacy prototypes,
construction-only bar for manual-`run()` classes, bounded update-loop for
`PrototypeBase` subclasses) plus the dedicated tests for `audio_mirror.py`
and `ai-mirror-of-truth.py`. Run with:

```bash
LUNAR_HEADLESS=1 python3 -m pytest tests/test_prototype_smoke.py -v
```

Legend:
- **works** — instantiates and runs cleanly against the headless tools layer; no known functional gaps blocking use.
- **degraded** — instantiates and runs, but a code path is known to silently no-op / fall back to a stub instead of failing (see reason).
- **needs-rework** — fails the smoke bar; requires non-trivial changes beyond this sweep's scope.

`verified-on-hardware` reflects whether the prototype has been run against real
hardware (mic/webcam/renderer/afterwords server) since the MLX-native
rework began; this sweep only validates the headless path, so it is `no`
for everything unless otherwise noted.

| Prototype | Status | Reason | Verified on hardware |
|---|---|---|---|
| acoustic-fingerprint-painter.py | needs-rework | Writes a temp WAV via the stubbed `AudioRecorder.stop_recording()` under `LUNAR_HEADLESS` and then feeds a None/invalid path into subsequent JSON parsing; pre-existing xfail carried into this sweep. | no |
| ai-dream-interpreter-prototype.py | works | Instantiates and runs cleanly. | no |
| ai-fashion-show-prototype.py | works | Instantiates and runs cleanly. | no |
| ai-mirror-of-truth.py | works | Covered by `tests/test_mirror_of_truth.py` (real emotion detection, Afterwords TTS, pluggable LLM, prosody — all headless-faked). Excluded from the generic smoke matrix (`SKIP` set) because it is a `PrototypeBase` subclass with a dedicated fixture-driven test. | no |
| apocalypse_experience.py | works | Instantiates and runs cleanly. | no |
| audio-reactive-fractal-forest.py | works | Instantiates and runs cleanly. | no |
| audio_mirror.py | works | Covered by `tests/test_audio_mirror.py` and `tests/test_audio_mirror_fsm.py`. Excluded from the generic smoke matrix (`SKIP` set) for the same reason as `ai-mirror-of-truth.py`. | no |
| augmented_audio_tours.py | degraded | `detect_position()` calls `gpt4.generate_vision(...)`, which does not exist on any `LLMBackend` implementation (vision support is deferred infra work, not part of this sweep). The call is wrapped in a broad `try/except`, so it degrades to `"unknown"` instead of crashing — construction and the smoke run both pass, but the vision feature itself is non-functional until a vision-capable backend/describe-then-generate path is added. | no |
| chat-room-narrative-quilt.py | needs-rework | References an undefined `self.l` (typo/dead code) during construction; pre-existing xfail carried into this sweep. | no |
| collaborative-canvas.py | works | Instantiates and runs cleanly; `.ip`/`.port` read/write on `ZMQPairEndpoint` supported per Task 5. | no |
| collaborative_art.py | works | Instantiates and runs cleanly; `.ip`/`.port` writes supported by `ZMQPairEndpoint` (Task 5). | no |
| cosmic-soundscape.py | needs-rework | File contains only a title comment (`# Voice-Activated Cosmic Soundscape Prototype`) — no class or implementation was ever written. | no |
| data-driven-cityscape.py | needs-rework | Requires `api_keys.openweathermap` in `settings.toml`, which is not configured in this environment; pre-existing xfail carried into this sweep. | no |
| dynamic_visuals.py | works | Instantiates and runs cleanly. | no |
| emotional-landscape-generator-prototype.py | works | Instantiates and runs cleanly. | no |
| escape_room.py | needs-rework | Calls `.strip()` directly on `gpt4.generate()`'s return value without a `None` guard; under `LUNAR_HEADLESS` the fake `Speech2Text` returns a truthy transcript, driving that code path when the LLM backend is unavailable. Pre-existing xfail carried into this sweep (stub-era code, not a test issue). | no |
| evolving-cosmic-mural-prototype.py | works | Instantiates and runs cleanly. | no |
| generative-poetry-mosaic.py | works | Instantiates and runs cleanly. | no |
| interactive-storytelling-canvas-prototype.py | works (fixed) | Fixed in this sweep: removed the `from utils import record_and_transcribe_speech` import (no top-level `utils` module exists) in favor of `self.speech2text.transcribe(duration=10)`, matching the convention used elsewhere (e.g. `speech_activated_art.py`); guarded the nonexistent `manager.glif_api` with `getattr(..., None)` (image visualization via Glif is out of scope for the current tools layer); fixed a `self.lunar_tools_manager` → `self.lunar_tools_art_manager`/`self.glif_api` typo in `visualize_story()`. | no |
| interactive_storytelling.py | works | Instantiates and runs cleanly. | no |
| neural-transfer-music-visualizer.py | needs-rework | Calls `SoundPlayer.stop_sound`, which does not exist on the tools-layer `SoundPlayer`; pre-existing xfail from the dedicated legacy `run()` test in `tests/test_lunar_tools_art.py` (construction-only smoke matrix passes). | no |
| real-time-glitch-art-lab.py | works | Instantiates and runs cleanly. | no |
| sentiment_analysis_display.py | works | Instantiates and runs cleanly. | no |
| speech_activated_art.py | works | Instantiates and runs cleanly. | no |
| temporal-art-gallery-prototype.py | works | Instantiates and runs cleanly. | no |
| time-shifted-echo-chamber.py | needs-rework | Requires `api_keys.openweathermap` in `settings.toml`, which is not configured in this environment; pre-existing xfail carried into this sweep. | no |
| virtual-cloud-chamber.py | degraded | `text2speech` unavailable in headless is caught and swallowed inside the prototype (consistent with `augmented_audio_tours.py`). | no |
| virtual_time_travel.py | needs-rework | Calls `.strip()` directly on `gpt4.generate()`'s return value without a `None` guard; same root cause as `escape_room.py`. Pre-existing xfail carried into this sweep. | no |
| whispers.py | works | Instantiates and runs cleanly. | no |

## Summary

Totals across all 29 prototypes (27 legacy + `audio_mirror.py` + `ai-mirror-of-truth.py`):

- **works**: 19
- **degraded**: 2 (`augmented_audio_tours.py`, `virtual-cloud-chamber.py`)
- **needs-rework**: 8 (`acoustic-fingerprint-painter.py`, `chat-room-narrative-quilt.py`, `cosmic-soundscape.py`, `data-driven-cityscape.py`, `escape_room.py`, `neural-transfer-music-visualizer.py`, `time-shifted-echo-chamber.py`, `virtual_time_travel.py`)

None of the `needs-rework` items regress the test suite — they are asserted via `pytest.xfail` in `tests/test_prototype_smoke.py` (and, for prototypes also covered by `tests/test_lunar_tools_art.py`, via the pre-existing `@pytest.mark.xfail` markers there) so `LUNAR_HEADLESS=1 pytest -q` is fully green.

## Shared infrastructure: emotion classifier (Task 13, code half)

`EmotionDetector` (`src/lunar_tools_art/emotion.py`) now supports a real ONNX FER+ classifier
(OpenCV DNN, 64x64 grayscale input, softmax over the 8 FER+ labels) alongside its existing Haar
cascade face detector. It takes an optional `model_path=None` kwarg (default sourced from
`settings.toml [emotion] model_path`); with no model file present, behavior is unchanged from the
prior placeholder (`has_classifier is False`, confidence `0.0`). `scripts/fetch_models.py`
downloads and SHA-256-verifies the model weights; `scripts/smoke_emotion.py` is an on-machine
webcam smoke test with an emotion-label overlay and FPS report. **Not yet run on-machine**:
`fetch_models.py` (checksum is a documented placeholder pending a human running the real
download once), `smoke_emotion.py` (webcam), and the flagship end-to-end Audio Mirror / Mirror of
Truth runs with Afterwords — all deferred to a human per Task 13 Step 5.
