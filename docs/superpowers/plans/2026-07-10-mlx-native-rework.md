# MLX-Native Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the stub tools layer with real Apple-Silicon/MLX implementations so all 29 prototypes (27 legacy + Audio Mirror + Mirror of Truth) genuinely run locally, with cloud as opt-in fallback.

**Architecture:** Keep the `LunarToolsArtManager` façade stable; rewrite `tools.py` into a `tools/` package of real implementations (pyglet display, sounddevice audio, OpenCV camera, mlx-whisper STT, Afterwords TTS adapter, mflux image gen). A privacy gate controls cloud construction; a headless mode substitutes deterministic fakes; a main-loop queue keeps GUI work on the main thread.

**Tech Stack:** Python ≥3.10, mlx / mlx-whisper / mlx-lm / mflux, sounddevice+soundfile, pyglet, OpenCV, mido+python-rtmidi, pyzmq, pynput, Afterwords TTS server (Qwen3-TTS on MLX), pytest.

**Spec:** `docs/superpowers/specs/2026-07-10-mlx-native-rework-design.md` (Rev 2). Read it before starting.

## Global Constraints

- `requires-python = ">=3.10"`; MLX packages are macOS/Apple-Silicon-only — every MLX import must be lazy (inside methods) so CI on Linux still imports the package.
- `LUNAR_HEADLESS=1` must swap every hardware tool for a deterministic fake; CI always sets it. Unit tests must pass with **no** hardware, network, or MLX models present.
- All rendering/GUI calls on the main thread only; background work communicates via `MainLoopQueue` (Task 6).
- `privacy.mode` (`local-only` default | `cloud-ok`; `cloud-llm` accepted alias) gates construction of every cloud-calling object.
- Image generation contract everywhere: `generate(prompt, size=(1024,1024)) -> tuple[str, dict]` — `(local_png_path, metadata)`.
- No silent `return None` in tools: raise `HardwareUnavailableError` / `InferenceError` / `CloudDisabledError` (Task 1), except degraded-mode reads which return `None` after a single logged warning.
- Existing 113 tests must keep passing from Task 2 onward. Run `pytest -q` before every commit.
- No history rewrite, no force-push (QA confirmed `.env` was never tracked).
- Commit after every task; conventional-commit messages.

---

### Task 0: Phase-0 hygiene & working-tree triage

**Files:**
- Modify: `.gitignore` (review pending diff, keep additions)
- Move: `hermes_qa_2026-06-21.md` → `docs/qa/hermes_qa_2026-06-21.md`
- Review: dirty `src/lunar_tools_art/tools.py`, `src/lunar_tools_art/prototype_base.py`, `tests/conftest.py`, untracked `tests/test_ai_services.py`

**Interfaces:** Produces a clean committed baseline; no code interfaces.

- [ ] **Step 1: Inspect each pending diff** — `git diff .gitignore src/lunar_tools_art/prototype_base.py src/lunar_tools_art/tools.py tests/conftest.py`. Keep changes that are hygiene/test fixes; `git checkout --` anything that half-implements what later tasks rewrite (record the decision in the commit message).
- [ ] **Step 2: Adopt or drop `tests/test_ai_services.py`** — run `LUNAR_HEADLESS=1 pytest tests/test_ai_services.py -q`. If it passes against current code, `git add` it; if it tests not-yet-existing behavior, delete it (the rework adds its own tests).
- [ ] **Step 3: Archive the QA report** — `mkdir -p docs/qa && git mv` is not possible (untracked); `mv hermes_qa_2026-06-21.md docs/qa/ && git add docs/qa/hermes_qa_2026-06-21.md`. Append a one-line correction note at the top: `> Correction 2026-07-10: the ".env tracked in git" blocker was refuted — .env was never committed (verified via git log --all -- .env).`
- [ ] **Step 4: Verify history is secret-free** — run `git log --all --full-history --source -p -- '*.env' | head` (expect only `.env.example`) and `detect-secrets scan --baseline .secrets.baseline`. Audit `# pragma: allowlist secret` comments in `settings.toml`: they annotate env-var *names*; leave them but note in commit body.
- [ ] **Step 5: Commit** — `git add -A && git commit -m "chore: phase-0 hygiene — triage working tree, archive corrected QA report, verify history clean"`.

---

### Task 1: Typed exceptions + privacy gate

**Files:**
- Modify: `src/lunar_tools_art/exceptions.py`
- Create: `src/lunar_tools_art/privacy.py`
- Test: `tests/test_privacy.py`, extend `tests/test_utils.py`-style pattern in new `tests/test_exceptions_new.py`

**Interfaces:**
- Consumes: `config.get(key, default)` from `src/lunar_tools_art/config.py:81`.
- Produces: `HardwareUnavailableError`, `InferenceError`, `CloudDisabledError` (all subclass `LunarToolsArtError`); `privacy.cloud_allowed(cfg=config) -> bool`; `privacy.require_cloud(feature: str)` raising `CloudDisabledError`.

- [ ] **Step 1: Write failing tests** in `tests/test_privacy.py`:

```python
import pytest
from lunar_tools_art.exceptions import (
    CloudDisabledError, HardwareUnavailableError, InferenceError, LunarToolsArtError,
)
from lunar_tools_art import privacy


class FakeConfig:
    def __init__(self, mode):
        self._mode = mode
    def get(self, key, default=None):
        return self._mode if key == "privacy.mode" else default


def test_new_exceptions_subclass_base():
    for exc in (CloudDisabledError, HardwareUnavailableError, InferenceError):
        assert issubclass(exc, LunarToolsArtError)

def test_local_only_blocks_cloud():
    assert privacy.cloud_allowed(FakeConfig("local-only")) is False
    with pytest.raises(CloudDisabledError):
        privacy.require_cloud("dalle3", FakeConfig("local-only"))

def test_cloud_ok_allows():
    assert privacy.cloud_allowed(FakeConfig("cloud-ok")) is True

def test_cloud_llm_alias_allows_with_warning(caplog):
    assert privacy.cloud_allowed(FakeConfig("cloud-llm")) is True
    assert any("deprecated" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run** `LUNAR_HEADLESS=1 pytest tests/test_privacy.py -v` — expect FAIL (ImportError).
- [ ] **Step 3: Implement.** Append to `exceptions.py`:

```python
class HardwareUnavailableError(LunarToolsArtError):
    """A required hardware device (mic, camera, MIDI) is absent or failed to open."""

class InferenceError(LunarToolsArtError):
    """A local model (MLX, whisper, mflux) failed during load or inference."""

class CloudDisabledError(LunarToolsArtError):
    """A cloud backend was requested while privacy.mode forbids cloud egress."""
```

Create `src/lunar_tools_art/privacy.py`:

```python
"""Single gate for all cloud egress decisions (LLM, image gen, TTS)."""
import logging

from .config import config as _default_config
from .exceptions import CloudDisabledError

logger = logging.getLogger(__name__)
_CLOUD_MODES = {"cloud-ok", "cloud-llm"}


def cloud_allowed(cfg=_default_config) -> bool:
    mode = cfg.get("privacy.mode", "local-only")
    if mode == "cloud-llm":
        logger.warning("privacy.mode='cloud-llm' is deprecated; use 'cloud-ok'")
    return mode in _CLOUD_MODES


def require_cloud(feature: str, cfg=_default_config) -> None:
    if not cloud_allowed(cfg):
        raise CloudDisabledError(
            f"{feature} requires cloud egress but privacy.mode is 'local-only'"
        )
```

- [ ] **Step 4: Run** `LUNAR_HEADLESS=1 pytest tests/test_privacy.py -v` — expect PASS; then `pytest -q` for regressions.
- [ ] **Step 5: Commit** — `git commit -m "feat: typed hardware/inference/cloud exceptions and privacy gate"`.

---

### Task 2: Packaging fix — importable on clean install

**Files:**
- Modify: `pyproject.toml`, `src/lunar_tools_art/manager.py:4`, `src/lunar_tools_art/tools.py:3` (import site only, full rewrite comes later), `requirements.txt`
- Test: `tests/test_packaging.py`

**Interfaces:**
- Produces: `lunar_tools_art.tracing.traceable(name=...)` — decorator that uses langsmith when installed, else identity. Later tasks import `from .tracing import traceable`.

- [ ] **Step 1: Failing test** `tests/test_packaging.py`:

```python
import builtins, importlib, sys
import pytest

def test_import_without_langsmith(monkeypatch):
    real_import = builtins.__import__
    def block(name, *a, **k):
        if name.startswith("langsmith"):
            raise ImportError("blocked")
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", block)
    for mod in [m for m in list(sys.modules) if m.startswith("lunar_tools_art")]:
        del sys.modules[mod]
    import lunar_tools_art.manager  # must not raise
    assert lunar_tools_art.manager is not None
```

- [ ] **Step 2: Run** — expect FAIL (`ImportError: blocked` propagates or langsmith missing).
- [ ] **Step 3: Implement.** Create `src/lunar_tools_art/tracing.py`:

```python
"""Optional LangSmith tracing: no-op decorator when langsmith is absent."""
try:
    from langsmith import traceable  # type: ignore
except ImportError:  # pragma: no cover - exercised via test monkeypatch
    def traceable(*dargs, **dkwargs):
        def deco(fn):
            return fn
        if dargs and callable(dargs[0]):
            return dargs[0]
        return deco
```

In `manager.py` replace `from langsmith import traceable` with `from .tracing import traceable`. In `pyproject.toml`: bump `requires-python = ">=3.10"`; remove `"lunar-tools"`; add missing runtime deps that current code imports (`requests`, `numpy` already present via librosa but declare directly); add extras:

```toml
[project.optional-dependencies]
cloud = ["openai>=1.40", "anthropic>=0.40.0"]
tracing = ["langsmith>=0.1"]
mlx = ["mlx>=0.26", "mlx-whisper>=0.4", "mlx-lm>=0.24", "mflux>=0.6"]
audio = ["sounddevice>=0.5", "pyglet>=2.0", "mido>=1.3", "python-rtmidi>=1.5", "pyzmq>=26", "pynput>=1.7"]
```

Move the module-level `import openai` in `tools.py` inside the classes that use it (`Dalle3ImageGenerator.__init__`, `GPT4.__init__`). Regenerate `requirements.txt`: `pip-compile --extra mlx --extra audio --extra cloud --extra tracing --output-file=requirements.txt pyproject.toml`.
- [ ] **Step 4: Run** `LUNAR_HEADLESS=1 pytest tests/test_packaging.py -v` then `pytest -q` — PASS.
- [ ] **Step 5: Commit** — `git commit -m "fix: package imports cleanly — optional langsmith/openai, drop lunar-tools, py3.10 floor"`.

---### Task 3: tools package skeleton + headless fakes

**Files:**
- Create: `src/lunar_tools_art/tools/__init__.py`, `src/lunar_tools_art/tools/headless.py`
- Move: current `src/lunar_tools_art/tools.py` → `src/lunar_tools_art/tools/_legacy_cloud.py` (keeps `Dalle3ImageGenerator`, `SDXL_TURBO`, `SDXL_LCM`, `Text2SpeechOpenAI`; **delete** `GPT4` and `Ollama` classes — dead code)
- Test: `tests/test_headless.py`

**Interfaces:**
- Produces: `lunar_tools_art.tools` package re-exporting every public name the manager imports today (`Renderer, Speech2Text, Text2SpeechOpenAI, AudioRecorder, SoundPlayer, KeyboardInput, WebCam, SDXL_TURBO, Dalle3ImageGenerator, FluxImageGenerator, SDXL_LCM, ZMQPairEndpoint, MidiInput`); `headless_active() -> bool` (True when `LUNAR_HEADLESS=1`); fake classes `FakeRenderer, FakeWebCam, FakeAudioRecorder, FakeSoundPlayer, FakeKeyboardInput, FakeMidiInput, FakeSpeech2Text` with the same method signatures returning deterministic values (`FakeWebCam.get_img()` → 480×640×3 zeros; `FakeSpeech2Text.transcribe()` → `{"text": "hello world", "confidence": 1.0}`).
- `__init__.py` selects real vs fake per class at import of the *manager* (a `resolve(name)` helper), so `from .tools import X` stays valid.

- [ ] **Step 1: Failing test** `tests/test_headless.py`:

```python
import numpy as np

def test_headless_env_selects_fakes(monkeypatch):
    monkeypatch.setenv("LUNAR_HEADLESS", "1")
    from lunar_tools_art.tools import headless
    assert headless.headless_active() is True
    cam = headless.FakeWebCam()
    img = cam.get_img()
    assert isinstance(img, np.ndarray) and img.shape == (480, 640, 3)
    stt = headless.FakeSpeech2Text()
    assert stt.transcribe("x.wav") == {"text": "hello world", "confidence": 1.0}
```

- [ ] **Step 2: Run** — FAIL (module missing).
- [ ] **Step 3: Implement** the package: `headless.py` with `headless_active()` reading `os.environ.get("LUNAR_HEADLESS") == "1"` and the fakes; `__init__.py` re-exports legacy classes from `_legacy_cloud.py` for now (real replacements arrive Tasks 4–8) plus `resolve(name)`:

```python
import os
from . import headless as _hl
from ._legacy_cloud import (  # noqa: F401
    Renderer, Speech2Text, Text2SpeechOpenAI, AudioRecorder, SoundPlayer,
    KeyboardInput, WebCam, SDXL_TURBO, Dalle3ImageGenerator,
    FluxImageGenerator, SDXL_LCM, ZMQPairEndpoint, MidiInput,
)

_FAKES = {
    "Renderer": _hl.FakeRenderer, "WebCam": _hl.FakeWebCam,
    "AudioRecorder": _hl.FakeAudioRecorder, "SoundPlayer": _hl.FakeSoundPlayer,
    "KeyboardInput": _hl.FakeKeyboardInput, "MidiInput": _hl.FakeMidiInput,
    "Speech2Text": _hl.FakeSpeech2Text,
}

def resolve(name: str):
    """Return the fake class in headless mode, else the real one."""
    if _hl.headless_active() and name in _FAKES:
        return _FAKES[name]
    return globals()[name]
```

Manager change (in `manager.py`): every `self.x = self._traceable_tool(ClassName, "ClassName", ...)` becomes `self._traceable_tool(tools.resolve("ClassName"), "ClassName", ...)` via `from . import tools`.
- [ ] **Step 4: Run** `LUNAR_HEADLESS=1 pytest -q` — full suite PASS.
- [ ] **Step 5: Commit** — `git commit -m "refactor: tools package with headless fakes; delete dead GPT4/Ollama classes"`.

---

### Task 4: Real audio — AudioRecorder & SoundPlayer

**Files:**
- Create: `src/lunar_tools_art/tools/audio.py`, `scripts/smoke_audio.py`
- Modify: `src/lunar_tools_art/tools/__init__.py` (re-export from `audio.py` instead of legacy), `src/lunar_tools_art/prototype_base.py` (`get_user_speech` uses `record()`)
- Test: `tests/test_tools_audio.py`

**Interfaces:**
- Consumes: `create_secure_temp_file` from `src/lunar_tools_art/utils.py`; exceptions from Task 1.
- Produces: `AudioRecorder.start_recording(file_path: str) -> None`, `.stop_recording() -> str` (returns file path), `.record(duration: float) -> str` (blocking convenience — this is what `InteractivePrototype.get_user_speech()` calls); `SoundPlayer.play_audio(path_or_array, samplerate: int = 24000, blocking: bool = False) -> None`, `.play_sound(path) -> None` (alias). Missing input device → `HardwareUnavailableError` on first call, subsequent calls log-once and return `None`/no-op.

- [ ] **Step 1: Failing tests** `tests/test_tools_audio.py` (mock `sounddevice`):

```python
import sys, types
import numpy as np
import pytest

@pytest.fixture
def fake_sd(monkeypatch):
    sd = types.SimpleNamespace(
        rec=lambda frames, samplerate, channels: np.zeros((frames, channels), dtype="float32"),
        wait=lambda: None, play=lambda data, samplerate: None,
        InputStream=None, query_devices=lambda: [{"name": "Fake Mic", "max_input_channels": 1}],
    )
    monkeypatch.setitem(sys.modules, "sounddevice", sd)
    return sd

def test_record_writes_wav(tmp_path, fake_sd, monkeypatch):
    from lunar_tools_art.tools.audio import AudioRecorder
    rec = AudioRecorder(output_dir=str(tmp_path))
    path = rec.record(duration=0.1)
    assert path.endswith(".wav")
    import soundfile as sf
    data, sr = sf.read(path)
    assert sr == 16000

def test_no_device_raises(monkeypatch, tmp_path):
    import sys, types
    sd = types.SimpleNamespace(query_devices=lambda: [], rec=None, wait=None, play=None)
    monkeypatch.setitem(sys.modules, "sounddevice", sd)
    from lunar_tools_art.tools.audio import AudioRecorder
    from lunar_tools_art.exceptions import HardwareUnavailableError
    rec = AudioRecorder(output_dir=str(tmp_path))
    with pytest.raises(HardwareUnavailableError):
        rec.record(duration=0.1)
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** `audio.py`: lazy `import sounddevice as sd` inside methods; 16 kHz mono default (Whisper-native); `record()` = `sd.rec` + `sd.wait` + `soundfile.write` to a secure temp file in `output_dir`; `start_recording`/`stop_recording` via `sd.InputStream` callback appending to a buffer; device presence checked with `query_devices()` (no input channels → raise `HardwareUnavailableError` first time, warn-once after). `SoundPlayer.play_audio` accepts str path (`soundfile.read` then `sd.play`) or ndarray. Update `prototype_base.py:274` `get_user_speech` to call `self.audio_recorder.record(duration=timeout)`. Write `scripts/smoke_audio.py` (records 2 s, plays it back, prints path).
- [ ] **Step 4: Run** `LUNAR_HEADLESS=1 pytest tests/test_tools_audio.py -v && pytest -q` — PASS. On-machine: `python scripts/smoke_audio.py`.
- [ ] **Step 5: Commit** — `git commit -m "feat: real sounddevice audio recorder/player with degraded mode"`.

---

### Task 5: Real camera + keyboard + MIDI + ZMQ

**Files:**
- Create: `src/lunar_tools_art/tools/camera.py`, `src/lunar_tools_art/tools/input.py`, `src/lunar_tools_art/tools/net.py`, `scripts/smoke_camera.py`, `scripts/smoke_midi.py`
- Modify: `src/lunar_tools_art/tools/__init__.py` re-exports
- Test: `tests/test_tools_camera.py`, `tests/test_tools_input.py`, `tests/test_tools_net.py`

**Interfaces:**
- Produces: `WebCam(cam_id=0).get_img() -> np.ndarray | None` (RGB; warn-once + `None` when absent); `KeyboardInput().is_key_pressed(key: str) -> bool`, `.get() -> str | None` (pynput listener storing last/pressed keys; pyglet path arrives with Renderer in Task 6 via constructor arg `window=`); `MidiInput().get_latest_message() -> mido.Message | None`, `.get(control: int, default=0.0) -> float` (returns `default` when no device — preserves current silent behavior); `ZMQPairEndpoint(bind: bool, address: str)` with `send(str)`, `receive(timeout_ms=0) -> str | None`, `get_messages() -> list[str]`, `send_img(np.ndarray)`.

- [ ] **Step 1: Failing tests** — `test_tools_camera.py` mocks `cv2.VideoCapture` (returns a stub whose `.read()` yields `(True, bgr_frame)`; assert RGB conversion by checking channel swap); `test_tools_input.py` instantiates `KeyboardInput` with an injected fake listener and asserts `is_key_pressed("q")` after simulating a press; `test_tools_net.py` creates a bound+connected `ZMQPairEndpoint` pair over `tcp://127.0.0.1:0`… use `ipc://` or a fixed high port `tcp://127.0.0.1:5871`, sends "ping", asserts `receive(timeout_ms=1000) == "ping"`.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** the three modules (lazy imports; degraded modes as specified; `MidiInput` opens the first available input port via `mido.get_input_names()`). Smoke scripts show a camera frame via `cv2.imshow` and print MIDI messages for 5 s.
- [ ] **Step 4: Run** `LUNAR_HEADLESS=1 pytest tests/test_tools_camera.py tests/test_tools_input.py tests/test_tools_net.py -v && pytest -q` — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: real webcam, keyboard, MIDI, ZMQ tools"`.

---

### Task 6: Renderer + MainLoopQueue (main-thread rule)

**Files:**
- Create: `src/lunar_tools_art/tools/display.py`, `src/lunar_tools_art/loop_queue.py`, `scripts/smoke_renderer.py`
- Modify: `src/lunar_tools_art/tools/__init__.py`
- Test: `tests/test_loop_queue.py`, `tests/test_tools_display.py`

**Interfaces:**
- Produces: `Renderer(width, height, backend="pyglet"|"opencv")` with `.render(image: np.ndarray) -> None`, `.set_size(w, h)`, `.close()`, `.window` (pyglet window or None), asserting `threading.main_thread()` — calling from another thread raises `RuntimeError`; `MainLoopQueue().post(fn, *args)` (any thread) and `.drain(max_items=10)` (main thread, called from prototype `update()`); manager gains `self.main_queue = MainLoopQueue()`.

- [ ] **Step 1: Failing tests**:

```python
# tests/test_loop_queue.py
import threading
from lunar_tools_art.loop_queue import MainLoopQueue

def test_post_from_thread_drain_on_main():
    q = MainLoopQueue()
    results = []
    t = threading.Thread(target=lambda: q.post(results.append, 42))
    t.start(); t.join()
    assert results == []          # nothing ran yet
    q.drain()
    assert results == [42]

# tests/test_tools_display.py
def test_render_off_main_thread_raises():
    import numpy as np, threading, pytest
    from lunar_tools_art.tools.display import Renderer
    r = Renderer(64, 64, backend="null")   # test backend: no window
    err = []
    t = threading.Thread(target=lambda: err.append(_try(r)))
    def _try(r):
        try:
            r.render(np.zeros((64, 64, 3), dtype="uint8")); return None
        except RuntimeError as e: return e
    t.start(); t.join()
    assert isinstance(err[0], RuntimeError)
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.** `MainLoopQueue` wraps `queue.Queue`; `drain` pops up to `max_items` `(fn, args)` and calls them. `Renderer`: `backend="pyglet"` lazily creates a `pyglet.window.Window`, converts numpy RGB → `pyglet.image.ImageData`, blits on `render()` + dispatches events; `backend="opencv"` uses `cv2.imshow`; `backend="null"` records frames (for tests). Main-thread check at top of `render()`. When Renderer is pyglet, it exposes `window` so `KeyboardInput(window=...)` can hook pyglet key handlers.
- [ ] **Step 4: Run** `LUNAR_HEADLESS=1 pytest tests/test_loop_queue.py tests/test_tools_display.py -v && pytest -q` — PASS. On-machine: `python scripts/smoke_renderer.py` (animated gradient window, ESC quits).
- [ ] **Step 5: Commit** — `git commit -m "feat: pyglet renderer with main-thread enforcement and main-loop queue"`.

---

### Task 7: Speech2Text on mlx-whisper (+ faster-whisper option)

**Files:**
- Create: `src/lunar_tools_art/tools/stt.py`, `scripts/smoke_stt.py`
- Modify: `src/lunar_tools_art/tools/__init__.py`, `settings.toml` (`[whisper] backend = "mlx-whisper"`, keep section name)
- Test: `tests/test_tools_stt.py`

**Interfaces:**
- Consumes: `config.get("whisper.backend", "mlx-whisper")`, `config.get("whisper.model", "base.en")`.
- Produces: `Speech2Text().transcribe(path_or_array) -> dict` with keys `text: str`, `confidence: float` (mean of segment `avg_logprob` mapped via `exp`, clamped 0–1), `language: str`. Model load failure → `InferenceError`.

- [ ] **Step 1: Failing test** — monkeypatch a fake `mlx_whisper` module in `sys.modules` whose `transcribe()` returns `{"text": " hi there", "language": "en", "segments": [{"avg_logprob": -0.2}]}`; assert result `{"text": "hi there", ...}` stripped, `0 < confidence <= 1`; second test: fake module raising on transcribe → `InferenceError`.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** `stt.py`: backend dispatch on config; mlx path `import mlx_whisper` lazily, `mlx_whisper.transcribe(audio, path_or_hf_repo=f"mlx-community/whisper-{model}-mlx")`; faster-whisper path mirrors it when installed. `scripts/smoke_stt.py` records 3 s via `AudioRecorder` and prints the transcript.
- [ ] **Step 4: Run** `LUNAR_HEADLESS=1 pytest tests/test_tools_stt.py -v && pytest -q` — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: mlx-whisper speech-to-text with confidence and backend selection"`.

---

### Task 8: Text2Speech adapter over Afterwords + LLM fixes

**Files:**
- Create: `src/lunar_tools_art/tools/tts.py`
- Modify: `src/lunar_tools_art/manager.py` (text2speech wiring, expose `self.config`), `src/lunar_tools_art/prototype_base.py:307-330` (fix `dalle`/`sdxl` lookups → `image_gen`; `self.llm.chat(...)` → `self.llm.generate(...)`), `src/lunar_tools_art/llm_backends.py` (add `MLXLocalBackend`)
- Test: `tests/test_tools_tts.py`, extend `tests/test_llm_backends.py`

**Interfaces:**
- Consumes: `VoiceClient.synthesize(text, voice, ...) -> path` (`voice_client.py:52`), `privacy.require_cloud`, `create_backend(config)`.
- Produces: `Text2Speech(voice_client, default_voice="galadriel").generate(text: str, voice: str | None = None) -> str` (wav path; Afterwords unreachable → `InferenceError` with the health-check detail); `MLXLocalBackend(model: str).generate(prompt, system_prompt=None) -> str | None` registered in `create_backend` for `provider = "mlx"`; `manager.text2speech` is a `Text2Speech`; `Text2SpeechOpenAI` constructed only if `privacy.cloud_allowed()`; `manager.config` property returning the config singleton.

- [ ] **Step 1: Failing tests** — `Text2Speech` with a stub voice_client (records call args, returns "/tmp/x.wav") asserting delegation and default voice; stub raising `requests.ConnectionError` → `InferenceError`. `create_backend({"provider": "mlx", "mlx": {"model": "mlx-community/Llama-3.2-3B-Instruct-4bit"}})` returns `MLXLocalBackend` (monkeypatch `mlx_lm` import). `AIPrototype.generate_text` test: fake manager with `llm_backend.generate` returning "ok" — asserts no `AttributeError`.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.** `MLXLocalBackend` lazily `from mlx_lm import load, generate`; cache the loaded model at class level (single load per process — memory policy). Manager: build `Text2Speech(self.voice_client)` as `self.text2speech`; keep OpenAI TTS behind the privacy gate. Fix `prototype_base.py` phantom APIs; add `settings.toml` `[llm.mlx] model = "mlx-community/Llama-3.2-3B-Instruct-4bit"`.
- [ ] **Step 4: Run** `LUNAR_HEADLESS=1 pytest tests/test_tools_tts.py tests/test_llm_backends.py -v && pytest -q` — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: Afterwords TTS adapter, mlx-lm backend, fix phantom prototype-base APIs"`.

---

### Task 9: Unified ImageGenerator (mflux + gated cloud) with tuple contract

**Files:**
- Create: `src/lunar_tools_art/tools/images.py`, `scripts/smoke_imagegen.py`
- Modify: `src/lunar_tools_art/manager.py` (add `image_gen` + deprecated aliases; stop unconditional cloud construction), `settings.toml` (`[image]` section)
- Test: `tests/test_image_generator.py`

**Interfaces:**
- Consumes: `privacy.cloud_allowed`, `MainLoopQueue`, exceptions.
- Produces: `ImageGenerator(backend="mflux", model="schnell", quantize=4, output_dir="outputs/images")`:
  - `.generate(prompt: str, size: tuple[int, int] = (1024, 1024), seed: int | None = None) -> tuple[str, dict]` — `(png_path, {"backend", "seed", "latency_s"})`
  - `.generate_async(prompt, main_queue, on_ready, size=(1024,1024)) -> None` — worker thread runs `generate`, posts `on_ready(path, meta)` to `main_queue`
  - Cloud backends (`"openai"`, `"replicate"`) call `privacy.require_cloud()` in `__init__` and download results to `output_dir` so the tuple contract is uniform.
- Manager: `self.image_gen = ImageGenerator(**config.get("image", {}))`; `self.dalle3 = self.sdxl_turbo = self.sdxl_lcm = self.flux = _DeprecatedAlias(self.image_gen, name)` where `_DeprecatedAlias.generate(*a, **k)` warns once (`DeprecationWarning` + log) and returns the same tuple.

- [ ] **Step 1: Failing tests**:

```python
import warnings
import pytest

def test_generate_returns_tuple(monkeypatch, tmp_path):
    from lunar_tools_art.tools.images import ImageGenerator
    gen = ImageGenerator(backend="fake", output_dir=str(tmp_path))  # test backend writes a 1x1 png
    path, meta = gen.generate("a moon garden", size=(64, 64))
    assert path.endswith(".png") and meta["backend"] == "fake"

def test_legacy_alias_unpacking(tmp_path):
    from lunar_tools_art.tools.images import ImageGenerator, DeprecatedAlias
    gen = ImageGenerator(backend="fake", output_dir=str(tmp_path))
    alias = DeprecatedAlias(gen, "dalle3")
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        image, _ = alias.generate("prompt")     # the 14-prototype pattern
    assert image.endswith(".png")
    assert any(issubclass(x.category, DeprecationWarning) for x in w)

def test_cloud_backend_blocked_local_only(tmp_path):
    from lunar_tools_art.tools.images import ImageGenerator
    from lunar_tools_art.exceptions import CloudDisabledError
    with pytest.raises(CloudDisabledError):
        ImageGenerator(backend="openai", output_dir=str(tmp_path))
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** `images.py` with backends: `fake` (PIL 1×1 png — used by tests and headless), `mflux` (lazy `from mflux import Flux1, Config`; load once per process behind a `threading.Lock` inference gate shared via module global `_INFERENCE_LOCK` — also exported for STT/LLM to reuse), `openai`, `replicate` (port real code from `_legacy_cloud.py`, add result download, wrap in the gate check). Record latency in `meta`. Wire manager. Add `[image]\nbackend = "mflux"\nmodel = "schnell"\nquantize = 4` to `settings.toml`. `scripts/smoke_imagegen.py` generates one image and prints path + latency — **record the measured latency in the spec's Phase-2 benchmark note**.
- [ ] **Step 4: Run** `LUNAR_HEADLESS=1 pytest tests/test_image_generator.py -v && pytest -q` — PASS. On-machine smoke.
- [ ] **Step 5: Commit** — `git commit -m "feat: unified image generator (mflux default, gated cloud, tuple-compatible aliases)"`.

---

### Task 10: Manager integration pass

**Files:**
- Modify: `src/lunar_tools_art/manager.py`
- Test: `tests/test_manager_integration.py`

**Interfaces:**
- Produces: `LunarToolsArtManager()` constructed under `LUNAR_HEADLESS=1` yields non-None `renderer, speech2text, text2speech, audio_recorder, sound_player, keyboard_input, webcam, image_gen, zmq_pair_endpoint, midi_input, main_queue, llm_backend (or None w/o config), emotion_detector, prosody_analyzer, voice_client`; deprecated aliases present; no cloud objects constructed in `local-only`.

- [ ] **Step 1: Failing test** — instantiate manager headless; assert every attribute above; assert `manager.dalle3.generate` exists; monkeypatch privacy to `local-only` and assert no attribute is an OpenAI/Replicate-backed instance (check a `is_cloud` flag on classes).
- [ ] **Step 2: Run** — FAIL where wiring is incomplete.
- [ ] **Step 3: Implement** remaining wiring; delete now-unused code paths in `_traceable_tool` name table (add `ImageGenerator`, `Text2Speech` entries).
- [ ] **Step 4: Run** `LUNAR_HEADLESS=1 pytest -q` — full suite PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: manager fully wired to real tools layer"`.

---

### Task 11: Prototype sweep — automated smoke matrix

**Files:**
- Create: `tests/test_prototype_smoke.py`, `PROTOTYPE_STATUS.md`
- Modify: individual `prototypes/*.py` as failures dictate (import errors, phantom methods, `stable_diffusion`-style local renames, exit handling)

**Interfaces:**
- Consumes: everything above via `LunarToolsArtManager`.
- Produces: a parametrized smoke test that, for each of the 27 legacy prototypes, (a) imports the module, (b) instantiates its class with a headless manager, (c) runs ≤3 `update()` iterations with `should_exit` forced True after; `PROTOTYPE_STATUS.md` table (name | status `works`/`degraded`/`needs-rework` | reason).

- [ ] **Step 1: Write the harness** (it doubles as the failing test — most prototypes will fail initially):

```python
import importlib.util, pathlib, pytest

PROTO_DIR = pathlib.Path(__file__).parent.parent / "prototypes"
SKIP = {"__init__.py", "example_base_usage.py", "audio_mirror.py", "ai-mirror-of-truth.py"}
FILES = sorted(p for p in PROTO_DIR.glob("*.py") if p.name not in SKIP)

def load(path):
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_prototype_smoke(path, headless_manager):   # headless_manager fixture in conftest
    mod = load(path)
    cls = next(v for v in vars(mod).values()
               if isinstance(v, type) and hasattr(v, "run") and v.__module__ == mod.__name__)
    proto = cls(headless_manager)
    if hasattr(proto, "setup"):
        proto.setup()
        for _ in range(3):
            proto.update()
        proto.cleanup()
```

Add `headless_manager` fixture to `tests/conftest.py` (sets `LUNAR_HEADLESS=1`, returns a session-scoped manager).
- [ ] **Step 2: Run** `LUNAR_HEADLESS=1 pytest tests/test_prototype_smoke.py -v` — collect the failure list; paste it into `PROTOTYPE_STATUS.md` as the starting matrix.
- [ ] **Step 3: Fix prototypes one at a time** — commit per prototype or per small batch (`fix(prototypes): <name> runs against real manager`). Known required fixes from QA: `augmented_audio_tours.py` `generate_vision` call (rewrite to `llm_backend.generate` on the transcribed description — vision deferred, mark `degraded`); `collaborative_art.py` `self.stable_diffusion` alias (fine — aliases return tuples); tuple unpackers work via aliases; legacy manual-loop prototypes lacking exit handling get the `PrototypeBase` pattern **only if trivially adaptable**, else mark `needs-rework`.
- [ ] **Step 4: Gate** — `LUNAR_HEADLESS=1 pytest -q` fully green; every row in `PROTOTYPE_STATUS.md` has a status; no row blank.
- [ ] **Step 5: Commit** — `git commit -m "feat: all legacy prototypes pass smoke matrix; status matrix added"`.

---

### Task 12: On-machine verification (real hardware, one per category)

**Files:**
- Modify: `PROTOTYPE_STATUS.md` (verified column), `docs/superpowers/specs/2026-07-10-mlx-native-rework-design.md` (benchmark numbers)

**Interfaces:** none new — this is a manual verification task run by Adrian/agent on the M5, not in CI.

- [ ] **Step 1:** `python scripts/smoke_renderer.py && python scripts/smoke_audio.py && python scripts/smoke_camera.py && python scripts/smoke_stt.py && python scripts/smoke_imagegen.py` — all succeed; note imagegen latency.
- [ ] **Step 2:** Run one prototype per category via `python lunar_tools_demo.py --demo <name>`: image-gen-heavy (`evolving-cosmic-mural-prototype`), audio-reactive (`audio-reactive-fractal-forest`), webcam (`ai-mirror-of-truth` deferred to Task 13; use `sentiment_analysis_display` or another webcam one per matrix), MIDI (`dynamic_visuals` if MIDI hardware attached, else skip with note), LLM/storytelling (`interactive_storytelling`). Each runs ≥60 s and exits cleanly on `q`/ESC.
- [ ] **Step 3:** Update `PROTOTYPE_STATUS.md` verified column + spec §4 latency note. Commit — `git commit -m "docs: on-machine verification results and mflux benchmarks"`.

---

### Task 13: Flagship verification — emotion model + Audio Mirror + Mirror of Truth

**Files:**
- Modify: `src/lunar_tools_art/emotion.py` (real classifier), `settings.toml` (`[emotion] model` path), `PROTOTYPE_STATUS.md`
- Create: `tests/test_emotion_real.py`, `scripts/smoke_emotion.py`
- Download: FER+ ONNX emotion model (`emotion-ferplus-8.onnx`) to `models/` (gitignored; download script `scripts/fetch_models.py`)

**Interfaces:**
- Consumes: existing `EmotionDetector` API (`detect(frame) -> EmotionResult`), fallback chain design already in `emotion.py`.
- Produces: `EmotionDetector.has_classifier == True` when the ONNX model file exists; `detect()` returns one of the 8 FER+ labels with real confidence; absent model → current placeholder behavior unchanged (tests in `test_emotion.py` must still pass).

- [ ] **Step 1: Failing test** `tests/test_emotion_real.py` — construct `EmotionDetector(model_path=<tmp fake onnx>)` with monkeypatched `cv2.dnn.readNetFromONNX` returning a stub net whose `forward()` yields a logits vector peaking at index 3 (happiness); assert `has_classifier is True` and `detect(face_frame).emotion == "happiness"` with `confidence > 0.5`.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** the ONNX path in `emotion.py` (OpenCV DNN, 64×64 grayscale input per FER+, softmax over logits) + `scripts/fetch_models.py` (downloads from the official onnx/models URL with checksum). Add `models/` to `.gitignore`.
- [ ] **Step 4: Run** `LUNAR_HEADLESS=1 pytest tests/test_emotion_real.py tests/test_emotion.py -v && pytest -q` — PASS. On-machine: `python scripts/smoke_emotion.py` (webcam window with emotion label overlay, report FPS).
- [ ] **Step 5: On-machine flagship runs** — start Afterwords (`cd ../afterwords && ./afterwords.sh`), verify `curl localhost:7860/health`; run `python lunar_tools_demo.py --demo audio-mirror` and `--demo ai-mirror-of-truth` end-to-end; record the March validation-gate numbers (TTS latency, clone quality 5/15 s, `memory_pressure` output, emotion FPS, informal WER) in the spec §6.
- [ ] **Step 6: Commit** — `git commit -m "feat: real FER+ emotion classifier; flagship prototypes verified end-to-end"`.

---

### Task 14: CI, docs, and closeout

**Files:**
- Modify: `.github/workflows/ci.yml` (set `LUNAR_HEADLESS: "1"`, Python 3.10/3.12 matrix, install without `[mlx]`/`[audio]` extras on Linux), `CLAUDE.md` (correct test counts, tools architecture, remove stale "59 tests"/security-blocker claims), `README.md` (install: `pip install -e ".[mlx,audio]"` on macOS)
- Test: CI run itself

- [ ] **Step 1:** Update CI workflow; ensure `pip install -e .` (no extras) + `pytest -q` passes on Linux runner (all MLX/hardware imports are lazy — this is the proof).
- [ ] **Step 2:** Update `CLAUDE.md` and `README.md` to match reality (tools package, headless mode, privacy gate, image backend config, corrected history-audit finding).
- [ ] **Step 3:** `pre-commit run --all-files` clean; `bandit -r src/ prototypes/` clean; `detect-secrets scan --baseline .secrets.baseline` clean.
- [ ] **Step 4:** Commit — `git commit -m "chore: CI headless matrix, docs updated to rework reality"` and push.

---

## Self-Review Notes

- Spec coverage: Phase 0 → Task 0; Phase 1 → Tasks 1–8; Phase 2 → Task 9; Phase 3 → Tasks 10–12; Phase 4 → Task 13; config/packaging §7 → Tasks 2, 7, 9; error handling §8 → Task 1 + per-tool tests; CI/testing → Tasks 3, 11, 14.
- Type consistency: image contract is `tuple[str, dict]` in Tasks 9–11; STT returns `{"text", "confidence", "language"}` in Tasks 7–8; `record(duration) -> str` consumed by `get_user_speech` (Tasks 4, 8).
- Known deferred items are explicit: vision LLM (Task 11 marks `degraded`), MIDI hardware verification optional (Task 12).
