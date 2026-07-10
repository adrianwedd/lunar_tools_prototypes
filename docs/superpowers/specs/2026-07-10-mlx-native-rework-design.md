# MLX-Native Rework Design

**Date:** 2026-07-10
**Status:** Rev 2 — post triple QA (Codex, Agy, Hermes)
**Author:** Adrian + Claude
**Target hardware:** Apple M5, 32 GB (Apple Silicon generally; 16 GB minimum)

---

## 1. Goal & Scope

Make the entire repository genuinely runnable on Apple Silicon, local-first via MLX, with cloud services as opt-in fallbacks.

**Key discovery motivating this rework:** most of `src/lunar_tools_art/tools.py` consists of no-op stubs — `Renderer`, `Speech2Text`, `Text2SpeechOpenAI`, `AudioRecorder`, `SoundPlayer`, `WebCam`, `KeyboardInput`, `MidiInput`, `FluxImageGenerator`, and `ZMQPairEndpoint` silently do nothing. Only `Dalle3ImageGenerator`, `SDXL_TURBO`, `SDXL_LCM`, `GPT4`, and `Ollama` contain real (cloud/HTTP) code. The 27 legacy prototypes (31 files in `prototypes/` minus `__init__.py`, `example_base_usage.py`, `audio_mirror.py`, `ai-mirror-of-truth.py`) have therefore never actually run end-to-end; they are scripts written against a phantom API. This is not a cloud-to-MLX swap — it is giving the framework a working body for the first time.

The March 2026 infrastructure (`llm_backends.py`, `voice_client.py`, `prosody.py`, `audio_mirror_fsm.py`) is real, unit-tested (113 test functions across 11 files), and local-first; it is reused, not rewritten. **Exception:** `emotion.py` face-detects for real but its emotion classifier is an explicit placeholder (`has_classifier = False`, confidence 0.0) — wiring a real classifier is in-scope work (Phase 4), not existing infra.

**Known pre-existing breakage this rework must fix (verified during QA):**

- `manager.py` imports `langsmith`, which is absent from `pyproject.toml`/`requirements.txt` — `import lunar_tools_art` fails on a clean install. Tracing becomes optional (no-op if `langsmith` missing) and the dependency is declared as an extra.
- `tools.py` imports `openai`, also undeclared.
- `AIPrototype.generate_text()` calls `self.llm.chat(...)` but backends implement `.generate(...)`; `AIPrototype` looks up `manager.dalle`/`manager.sdxl`, which don't exist (real names: `dalle3`, `sdxl_turbo`).
- `InteractivePrototype.get_user_speech()` calls `audio_recorder.record(duration=...)`, but the tool API is `start_recording`/`stop_recording`.
- `prototype_base.py` references `self.manager.config`, which the manager never exposes.
- `augmented_audio_tours.py` calls `gpt4.generate_vision(...)` — no backend implements it.
- `pyproject.toml` depends on `lunar-tools` (upstream package, unused once tools are real) and declares `requires-python = ">=3.9"`, below the MLX ecosystem floor.

**In scope**

- Repo hygiene verification and cleanup (Phase 0 — reduced after QA, see below).
- A real hardware/inference tools layer replacing stub `tools.py`, plus fixing the pre-existing API inconsistencies above.
- Unified local image generation (mflux) with opt-in cloud fallback.
- Migration/verification of all 27 legacy prototypes plus Audio Mirror and Mirror of Truth.

**Out of scope**

- New art concepts or prototypes.
- The GitHub Pages gallery site.
- Compatibility with the upstream `lunar_tools` package (the dependency is removed).

## 2. Phase 0 — Hygiene & Verification (small; no history rewrite)

QA (verified against git directly) refuted the June Hermes report's central claim: **`.env` was never tracked in git** — only `.env.example` was. The same holds for `.claude/`, `.ruff_cache/`, `.pytest_cache/`, and `.output/`. There is no key exposure in the public history, so no `git filter-repo`, no force-push, and no mandatory key rotation.

Remaining Phase 0 work:

1. **Verify, don't assume:** run `detect-secrets scan` across full history (`git log -p | detect-secrets scan --string` sweep or `trufflehog git`) and record the result in the PR. Rotating the local `GEMINI_API_KEY`/`OPENAI_API_KEY` remains optional good practice.
2. **Triage the dirty working tree deliberately** — the modified files (`tools.py`, `prototype_base.py`, `conftest.py`, `.gitignore`) are exactly the files Phase 1 rewrites. Review each diff; commit what's wanted as a baseline, discard what isn't. Decide fate of untracked `hermes_qa_2026-06-21.md` (archive under `docs/qa/`) and `tests/test_ai_services.py` (adopt into the suite or delete).
3. Audit `# pragma: allowlist secret` annotations in `settings.toml` (they mark env-var *names*, not secrets) and regenerate `.secrets.baseline`; confirm pre-commit hooks pass.

## 3. Phase 1 — Real Tools Layer

Replace stubs in `tools.py` with working implementations, preserving the class and method names the manager exposes. Split into one module per concern under `src/lunar_tools_art/tools/` (display, audio, camera, input, net, images) with re-exports so `from .tools import X` keeps working.

| Tool | Implementation | Notes |
|---|---|---|
| `Renderer` | pyglet (OpenGL) window; OpenCV `imshow` fallback | `render(image)` accepts numpy HxWx3 frames; **main-thread only** (see threading rules) |
| `AudioRecorder` / `SoundPlayer` | `sounddevice` + `soundfile` | Keeps `start_recording(file_path)`/`stop_recording()`; adds `record(duration)` so both the existing prototype call sites and `InteractivePrototype.get_user_speech()` work |
| `WebCam` | OpenCV `VideoCapture` | `get_img()` returns RGB numpy frame; missing camera → one warning, then `None` (degraded) |
| `Speech2Text` | **mlx-whisper** (default) or **faster-whisper** | Backend from existing `settings.toml [whisper]` section (no rename); `transcribe(path_or_buffer) -> {text, confidence}` |
| `Text2Speech` (new adapter class) | Wraps existing `voice_client` (Afterwords / MLX Qwen3-TTS) | Manager's `text2speech` points to it; `Text2SpeechOpenAI` retained as cloud fallback gated by privacy mode |
| `KeyboardInput` | pyglet key events when Renderer active; `pynput` fallback | Same `is_key_pressed`/`get` API |
| `MidiInput` | `mido` + `python-rtmidi` | No device → warning once, then silent zeros |
| `ZMQPairEndpoint` | real `pyzmq` PAIR socket | Small; used by networked prototypes |
| `GPT4`, `Ollama` classes | **Deleted** (already dead code — manager doesn't import them) | All LLM calls go through `llm_backends.py`; an **mlx-lm** backend is added alongside Ollama/Claude/OpenRouter |

**API-consistency fixes (same phase):** `AIPrototype.generate_text()` switches to `.generate()`; `manager.dalle`/`sdxl` lookups fixed; `self.manager.config` exposed properly; `generate_vision()` either implemented on Claude/Ollama-vision backends or the one call site (`augmented_audio_tours.py`) is rewritten — decision at implementation time, recorded in `PROTOTYPE_STATUS.md`.

**Threading rules (macOS):** all rendering and window/GUI calls happen on the main thread. Background work (image gen, TTS, STT) posts results to a thread-safe queue that the prototype's `update()` loop drains; callbacks never touch the Renderer directly. A helper in `loop_utils.py` formalizes this.

**Memory/concurrency policy:** models load lazily on first use; a process-wide inference gate serializes heavy MLX jobs (image gen vs LLM vs STT) so unified memory stays bounded; Afterwords runs as a separate process (its own memory). On 32 GB this is comfortable; the gate is what makes 16 GB viable.

**Cross-cutting:** missing hardware degrades with one warning, never crashes the loop. `LUNAR_HEADLESS=1` swaps every hardware tool for a deterministic fake; CI always runs headless. Each tool gets unit tests plus a live smoke script (`scripts/smoke_<tool>.py`).

## 4. Phase 2 — Unified Image Generation

One `ImageGenerator` with pluggable backends selected in `settings.toml [image]`:

- **`mflux`** (default): Flux.1-schnell, 4-bit quantized. Latency **estimated** at ~5–15 s per 1024² image on M5 — to be benchmarked in Phase 2 and recorded; models cached in the HF cache (~9 GB first download).
- **`replicate`**, **`openai`**: opt-in cloud fallbacks, constructed **only** when privacy mode permits cloud egress (today the manager instantiates them unconditionally — that changes).
- **Return contract:** `manager.image_gen.generate(prompt, size=...) -> (image_path, metadata)` — a 2-tuple, because 14 legacy prototypes already unpack `image, _ = ...generate(...)`. `image_path` is a local PNG path (cloud backends download the result); `metadata` is a dict (backend, seed, latency).
- Manager keeps `dalle3`, `sdxl_turbo`, `sdxl_lcm`, `flux` as **deprecated aliases** for the unified generator, returning the same 2-tuple, so legacy call sites run unmodified (deprecation warning on first use). Phase 3 also audits prototype-level renames (e.g. `collaborative_art.py`'s `self.stable_diffusion`).
- `generate_async(prompt) -> Future`-style API posting to the main-loop queue (per threading rules); no raw callbacks.

## 5. Phase 3 — Prototype Sweep

- Run every prototype's smoke test against the real manager (headless fakes in CI; real hardware locally).
- Fix per-prototype breakage: import errors, phantom method calls, exit handling.
- Hand-verify one representative prototype per tool category end-to-end on the M5: image-gen-heavy, audio-reactive, webcam-driven, MIDI-driven, LLM/storytelling.
- Record results in `PROTOTYPE_STATUS.md`: `works` / `degraded` / `needs-rework` with a one-line reason. Conceptually broken prototypes are flagged, not silently shipped.

## 6. Phase 4 — Flagship Verification

Audio Mirror and Mirror of Truth run end-to-end against a live Afterwords server (`../afterwords`): voice-clone loop, mlx-whisper STT, local LLM, and a **real emotion classifier** replacing the placeholder — MLX or ONNX (OpenCV DNN) model per the fallback chain designed in `emotion.py`; Haar cascade remains last resort.

Re-run the March spec's validation gates on the M5 and record actual numbers (TTS latency, clone quality at 5/15 s, memory pressure, emotion FPS, Whisper WER).

## 7. Configuration & Packaging

- `settings.toml`: existing `[whisper]` section keeps its name and gains `backend = "mlx-whisper"` as the new default (`faster-whisper` remains selectable); new `[image]` section (backend, model, quantization).
- `privacy.mode` gates **all** cloud egress (LLM, image, TTS): `local-only` (default) forbids cloud backends at construction time; `cloud-ok` permits them (`cloud-llm` accepted as a deprecated alias with a warning).
- `pyproject.toml`: bump `requires-python = ">=3.10"` (MLX ecosystem floor; also matches the `py310` union syntax already in use); drop the `lunar-tools` dependency; declare currently-missing imports; move cloud clients (`openai`, `replicate` usage) and `langsmith` to optional extras `[cloud]` and `[tracing]`.
- New core deps: `mlx`, `mlx-whisper`, `mflux`, `mlx-lm`, `sounddevice`, `pyglet`, `mido`, `python-rtmidi`, `pyzmq`, `pynput`; optional: `faster-whisper`. `requirements.txt` regenerated with pip-compile (current file is hand-edited despite its header — regeneration fixes that too).

## 8. Error Handling & Testing

- New typed exceptions **added to** `exceptions.py` (`HardwareUnavailableError`, `InferenceError`, `CloudDisabledError`) alongside the existing `LunarToolsArtError` family; `ExceptionHandler` wiring extended to route them. No silent `return None` in tools.
- All 113 existing test functions must pass after the packaging fix (they cannot currently run on a clean install); new unit tests per tool module; prototype smoke tests run headless in CI.
- Verification: `pytest -v`, `bandit -r src/ prototypes/`, `detect-secrets scan --baseline .secrets.baseline`, per-tool live smoke scripts on-machine.

## 9. Sequencing

Phase 0 → 1 → 2 → 3 → 4. Phase 0 is small and quick. Phases 1–2 can partially overlap (image gen is independent of audio/display). Phase 3 requires 1+2; Phase 4 requires 3 plus a running Afterwords server.

## 10. Risks

- **mflux latency** on reactive prototypes: mitigated by async generation via the main-loop queue and honest `degraded` labels; numbers are estimates until benchmarked.
- **Unified-memory contention** (mflux + LLM + STT + Afterwords): mitigated by lazy loading and the serialized inference gate; benchmark under combined load in Phase 4.
- **mlx-whisper vs faster-whisper**: config-selectable backend preserves the alternative.
- **Afterwords drift**: flagship phase pins against the current `../afterwords` API (`/clone`, `/synthesize`, `DELETE /session`); a health check precedes each run.
- **Alias behavior divergence**: legacy aliases must reproduce the tuple contract exactly; covered by dedicated alias unit tests.
