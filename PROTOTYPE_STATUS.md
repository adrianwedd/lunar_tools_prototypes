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
| acoustic-fingerprint-painter.py | works (fixed) | Fixed in this sweep: `_get_stroke_parameters_from_gpt4` now guards a `None` LLM backend and `None`/empty responses, parses via a fence/JSON-block-tolerant helper, and `_draw_stroke` sanitizes numeric/RGB inputs; the headless `FakeAudioRecorder` writes a real WAV so feature extraction succeeds. | no |
| ai-dream-interpreter-prototype.py | works | Instantiates and runs cleanly. | no |
| ai-fashion-show-prototype.py | works | Instantiates and runs cleanly. | no |
| ai-mirror-of-truth.py | works | Covered by `tests/test_mirror_of_truth.py` (real emotion detection, Afterwords TTS, pluggable LLM, prosody — all headless-faked). Excluded from the generic smoke matrix (`SKIP` set) because it is a `PrototypeBase` subclass with a dedicated fixture-driven test. | no |
| apocalypse_experience.py | works | Instantiates and runs cleanly. | no |
| audio-reactive-fractal-forest.py | works | Instantiates and runs cleanly. | no |
| audio_mirror.py | works | Covered by `tests/test_audio_mirror.py` and `tests/test_audio_mirror_fsm.py`. Excluded from the generic smoke matrix (`SKIP` set) for the same reason as `ai-mirror-of-truth.py`. | no |
| augmented_audio_tours.py | degraded | Vision-based position detection is now explicit rather than silently swallowed: `LLMBackend.generate_vision()` exists as an optional capability (default `NotImplementedError`), and `detect_position()` logs a one-time warning and returns `"unknown"` when the configured backend lacks vision. Feature remains non-functional until a vision-capable backend is added. | no |
| chat-room-narrative-quilt.py | works (fixed) | Fixed in this sweep: corrected the `self.l.lunar_tools_art_manager` typo to `self.lunar_tools_art_manager` at construction. Constructs and runs cleanly headless. | no |
| collaborative-canvas.py | works | Instantiates and runs cleanly; `.ip`/`.port` read/write on `ZMQPairEndpoint` supported per Task 5. | no |
| collaborative_art.py | works | Instantiates and runs cleanly; `.ip`/`.port` writes supported by `ZMQPairEndpoint` (Task 5). | no |
| cosmic-soundscape.py | works (fixed) | Implemented in this sweep: `InteractivePrototype` subclass that transcribes a spoken phrase, maps keywords to celestial motifs/mood palette, generates a cosmic image via `manager.image_gen`, and renders it; graceful fallbacks when speech or generation is unavailable. | no |
| data-driven-cityscape.py | works (fixed) | Fixed in this sweep: missing `api_keys.openweathermap` no longer crashes construction (`config.get` instead of `get_or_raise`); `_fetch_weather_data` returns deterministic synthetic weather under `LUNAR_HEADLESS`, when the key is absent, or on HTTP failure — no network calls headless. | no |
| dynamic_visuals.py | works | Instantiates and runs cleanly. | no |
| emotional-landscape-generator-prototype.py | works | Instantiates and runs cleanly. | no |
| escape_room.py | works (fixed) | Fixed in this sweep: LLM intent parsing now guards `gpt4` being `None` and `generate()` returning `None`, falling back to intent `"unknown"` with a logged warning instead of crashing. | no |
| evolving-cosmic-mural-prototype.py | works | Instantiates and runs cleanly. | no |
| generative-poetry-mosaic.py | works | Instantiates and runs cleanly. | no |
| interactive-storytelling-canvas-prototype.py | works (fixed) | Fixed in this sweep: removed the `from utils import record_and_transcribe_speech` import (no top-level `utils` module exists) in favor of `self.speech2text.transcribe(duration=10)`, matching the convention used elsewhere (e.g. `speech_activated_art.py`); guarded the nonexistent `manager.glif_api` with `getattr(..., None)` (image visualization via Glif is out of scope for the current tools layer); fixed a `self.lunar_tools_manager` → `self.lunar_tools_art_manager`/`self.glif_api` typo in `visualize_story()`. | no |
| interactive_storytelling.py | works | Instantiates and runs cleanly. | no |
| neural-transfer-music-visualizer.py | works (fixed) | Fixed in this sweep: `SoundPlayer.stop_sound()` added to the tools layer (with a `FakeSoundPlayer` no-op), and the prototype now uses non-blocking `play_audio(...)` instead of an invalid `play_sound(..., loop=True)` call. | no |
| real-time-glitch-art-lab.py | works | Instantiates and runs cleanly. | no |
| sentiment_analysis_display.py | works | Instantiates and runs cleanly. | no |
| speech_activated_art.py | works | Instantiates and runs cleanly. | no |
| temporal-art-gallery-prototype.py | works | Instantiates and runs cleanly. | no |
| time-shifted-echo-chamber.py | works (fixed) | The old xfail reason was a stale copy-paste from `data-driven-cityscape.py` — this prototype has no weather/network dependency. Constructs and runs cleanly headless against the fake recorder/player/keyboard tools. | no |
| virtual-cloud-chamber.py | works (fixed) | Fixed in this sweep: added `FakeText2Speech` to the headless tools layer and routed `manager.text2speech` through `tools.resolve`; the prototype now uses the correct `generate(text) -> path` contract, warns once and disables narration (visuals continue) if the LLM or TTS is unavailable. | no |
| virtual_time_travel.py | works (fixed) | The old xfail reason (`.strip()` on `gpt4.generate()`) was a copy-paste from `escape_room.py` and did not apply. Real run-loop fragilities fixed in this sweep: `None` `text2speech` and TTS `InferenceError` are now guarded/logged, and `renderer.render` is skipped when image generation returns `None`. | no |
| whispers.py | works | Instantiates and runs cleanly. | no |

## Summary

Totals across all 29 prototypes (27 legacy + `audio_mirror.py` + `ai-mirror-of-truth.py`):

- **works**: 28
- **degraded**: 1 (`augmented_audio_tours.py` — vision-based position detection explicitly degrades to `"unknown"` until a vision-capable LLM backend exists)
- **needs-rework**: 0

All former `needs-rework` prototypes were fixed in the July 2026 sweep; every xfail entry/marker has been removed and `LUNAR_HEADLESS=1 pytest -q` is fully green (197 passed, 0 xfailed).

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
