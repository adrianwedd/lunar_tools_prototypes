# MLX-Native Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Rev 2 — post triple QA (Codex, Agy, Hermes).** Key changes from Rev 1: `test_ai_services.py` is deleted in Task 0 (it tests classes Task 3 removes); privacy gate now covers cloud **LLM** backends; the shared MLX inference gate moves to Task 1 so STT/LLM/image all consume it; `Speech2Text.transcribe` returns a `str` subclass so legacy string consumers keep working; `Text2Speech` handles `VoiceClient.synthesize -> bytes | None`; `DeprecatedAlias` adapts legacy kwargs; `MainLoopQueue` lives in `loop_utils.py` and is drained by `PrototypeBase.run()`; missing deps (`httpx`, `requests`, `pytest-mock`, `responses`) declared; mflux backend is written as an adapter verified against the installed mflux API at implementation time.

**Goal:** Replace the stub tools layer with real Apple-Silicon/MLX implementations so all 29 prototypes (27 legacy + Audio Mirror + Mirror of Truth) genuinely run locally, with cloud as opt-in fallback.

**Architecture:** Keep the `LunarToolsArtManager` façade stable; rewrite `tools.py` into a `tools/` package of real implementations (pyglet display, sounddevice audio, OpenCV camera, mlx-whisper STT, Afterwords TTS adapter, mflux image gen). A privacy gate controls construction of every cloud client; a headless mode substitutes deterministic fakes; a main-loop queue keeps GUI work on the main thread; a process-wide inference gate serializes heavy MLX jobs.

**Tech Stack:** Python ≥3.10, mlx / mlx-whisper / mlx-lm / mflux, sounddevice+soundfile, pyglet, OpenCV, mido+python-rtmidi, pyzmq, pynput, httpx, Afterwords TTS server (Qwen3-TTS on MLX), pytest.

**Spec:** `docs/superpowers/specs/2026-07-10-mlx-native-rework-design.md` (Rev 2). Read it before starting.

## Global Constraints

- `requires-python = ">=3.10"`; MLX packages are macOS/Apple-Silicon-only — every MLX import must be lazy (inside methods) so CI on Linux still imports the package.
- `LUNAR_HEADLESS=1` must swap every hardware tool for a deterministic fake; CI always sets it. Unit tests must pass with **no** hardware, network, or MLX models present.
- All rendering/GUI calls on the main thread only; background work communicates via `MainLoopQueue` (Task 1), which `PrototypeBase.run()` drains every iteration (Task 6).
- `privacy.mode` (`local-only` default | `cloud-ok`; `cloud-llm` accepted alias) gates construction of **every** cloud-calling object: image backends, `Text2SpeechOpenAI`, and the `Claude`/`OllamaCloud`/`OpenRouter` LLM backends.
- Image generation contract everywhere: `generate(prompt, size=(1024,1024), seed=None) -> tuple[str, dict]` — `(local_png_path, metadata)`. Legacy aliases adapt old kwargs (`image_size=`, `num_inference_steps=`) rather than passing them through.
- `Speech2Text.transcribe()` returns a `Transcription` — a `str` subclass carrying `.text`, `.confidence`, `.language` attributes — so legacy code that treats the result as a string (e.g. `.strip()`) keeps working.
- Heavy MLX inference (STT, mlx-lm, mflux) acquires the shared `inference_gate.INFERENCE_LOCK` (Task 1).
- No silent `return None` in tools: raise `HardwareUnavailableError` / `InferenceError` / `CloudDisabledError` (Task 1), except degraded-mode reads which return `None` after a single logged warning.
- **Test constraint:** the committed unit-test suite (104 tests after Task 0 deletes `test_ai_services.py`) must pass from Task 2 onward under `LUNAR_HEADLESS=1`. Legacy *prototypes* are not under test until the Task 11 smoke matrix — transitional breakage of prototype behavior in the Task 3–10 window is acceptable; unit-test breakage is not. Run `LUNAR_HEADLESS=1 pytest -q` before every commit.
- No history rewrite, no force-push (QA confirmed `.env` was never tracked).
- Commit after every task; conventional-commit messages.

---

### Task 0: Phase-0 hygiene & working-tree triage

**Files:**
- Modify: `.gitignore` (review pending diff, keep additions)
- Delete: `tests/test_ai_services.py` (untracked; imports `GPT4`/`Ollama`, which Task 3 deletes — its failure-path coverage is superseded by per-tool tests in Tasks 4–9)
- Move: `hermes_qa_2026-06-21.md` → `docs/qa/hermes_qa_2026-06-21.md`
- Review: dirty `src/lunar_tools_art/tools.py`, `src/lunar_tools_art/prototype_base.py`, `tests/conftest.py`

**Interfaces:** Produces a clean committed baseline; no code interfaces.

- [ ] **Step 1: Inspect each pending diff** — `git diff .gitignore src/lunar_tools_art/prototype_base.py src/lunar_tools_art/tools.py tests/conftest.py`. Keep changes that are hygiene/test fixes; `git checkout --` anything that half-implements what later tasks rewrite (record the decision in the commit message).
- [ ] **Step 2: Delete `tests/test_ai_services.py`** (`rm`). It is untracked, imports soon-deleted classes, and depends on undeclared `pytest-mock`/`mocker`.
- [ ] **Step 3: Archive the QA report** — `mkdir -p docs/qa && mv hermes_qa_2026-06-21.md docs/qa/ && git add docs/qa/hermes_qa_2026-06-21.md`. Prepend: `> Correction 2026-07-10: the ".env tracked in git" blocker was refuted — .env was never committed (verified via git log --all -- .env).`
- [ ] **Step 4: Verify history is secret-free** — `git log --all --full-history -p -- '*.env' | head` (expect only `.env.example`) and `detect-secrets scan --baseline .secrets.baseline`. The `# pragma: allowlist secret` comments in `settings.toml` annotate env-var *names*, not secrets — leave them, note in commit body.
- [ ] **Step 5: Baseline check** — `LUNAR_HEADLESS=1 pytest -q`; record pass count (expected 104).
- [ ] **Step 6: Commit** — `git add -A && git commit -m "chore: phase-0 hygiene — triage working tree, drop stale AI-services test, archive corrected QA report"`.

---

### Task 1: Typed exceptions, privacy gate, inference gate, main-loop queue

**Files:**
- Modify: `src/lunar_tools_art/exceptions.py` (new classes + `ExceptionHandler` routing), `src/lunar_tools_art/loop_utils.py` (add `MainLoopQueue`)
- Create: `src/lunar_tools_art/privacy.py`, `src/lunar_tools_art/inference_gate.py`
- Test: `tests/test_privacy.py`, `tests/test_loop_queue.py`

**Interfaces:**
- Consumes: `config.get(key, default)` (`src/lunar_tools_art/config.py:81`).
- Produces:
  - `HardwareUnavailableError`, `InferenceError`, `CloudDisabledError` (subclass `LunarToolsArtError`); `HARDWARE_EXCEPTIONS` tuple exported; `ExceptionHandler.__exit__` logs `CloudDisabledError` at WARNING (config problem, not crash) and the other two at ERROR with tool context.
  - `privacy.cloud_allowed(cfg=config) -> bool`; `privacy.require_cloud(feature: str, cfg=config) -> None` raising `CloudDisabledError`.
  - `inference_gate.INFERENCE_LOCK: threading.Lock` — module-level lock; every heavy MLX call in Tasks 7–9 wraps inference in `with INFERENCE_LOCK:`.
  - `loop_utils.MainLoopQueue` with `.post(fn, *args)` (any thread) and `.drain(max_items=10)` (main thread).

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
    import logging
    with caplog.at_level(logging.WARNING):
        assert privacy.cloud_allowed(FakeConfig("cloud-llm")) is True
    assert any("deprecated" in r.message for r in caplog.records)
```

and `tests/test_loop_queue.py`:

```python
import threading
from lunar_tools_art.loop_utils import MainLoopQueue

def test_post_from_thread_drain_on_main():
    q = MainLoopQueue()
    results = []
    t = threading.Thread(target=lambda: q.post(results.append, 42))
    t.start(); t.join()
    assert results == []          # nothing ran until drained
    q.drain()
    assert results == [42]

def test_drain_respects_max_items():
    q = MainLoopQueue()
    hits = []
    for i in range(15):
        q.post(hits.append, i)
    q.drain(max_items=10)
    assert len(hits) == 10
    q.drain()
    assert len(hits) == 15
```

- [ ] **Step 2: Run** `LUNAR_HEADLESS=1 pytest tests/test_privacy.py tests/test_loop_queue.py -v` — expect FAIL (ImportError).
- [ ] **Step 3: Implement.** Append to `exceptions.py`:

```python
class HardwareUnavailableError(LunarToolsArtError):
    """A required hardware device (mic, camera, MIDI) is absent or failed to open."""

class InferenceError(LunarToolsArtError):
    """A local model (MLX, whisper, mflux) failed during load or inference."""

class CloudDisabledError(LunarToolsArtError):
    """A cloud backend was requested while privacy.mode forbids cloud egress."""

HARDWARE_EXCEPTIONS = (HardwareUnavailableError,)
```

In `ExceptionHandler.__exit__`, before the generic branch: `CloudDisabledError` → `self.logger.warning(...)`; `HardwareUnavailableError`/`InferenceError` → `self.logger.error(...)` with `self.prototype_name`. Create `privacy.py`:

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

Create `inference_gate.py`:

```python
"""Process-wide gate serializing heavy MLX inference to bound unified-memory pressure."""
import threading

INFERENCE_LOCK = threading.Lock()
```

Append `MainLoopQueue` to `loop_utils.py` (spec §3 names this file):

```python
import queue

class MainLoopQueue:
    """Thread-safe handoff: background threads post callables, main loop drains them."""

    def __init__(self):
        self._q = queue.Queue()

    def post(self, fn, *args):
        self._q.put((fn, args))

    def drain(self, max_items=10):
        for _ in range(max_items):
            try:
                fn, args = self._q.get_nowait()
            except queue.Empty:
                return
            fn(*args)
```

- [ ] **Step 4: Run** the two test files, then `LUNAR_HEADLESS=1 pytest -q` — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: typed exceptions, privacy gate, MLX inference gate, main-loop queue"`.

---

### Task 2: Packaging fix — importable on clean install

**Files:**
- Modify: `pyproject.toml`, `src/lunar_tools_art/manager.py:4`, `requirements.txt`
- Create: `src/lunar_tools_art/tracing.py`
- Delete: `src/lunar_tools/` (deprecated shim package), `lunar-art` entry point in `pyproject.toml` (points at nonexistent `lunar_tools_art:main`)
- Test: `tests/test_packaging.py`

**Interfaces:**
- Produces: `lunar_tools_art.tracing.traceable(name=...)` — uses langsmith when installed, else identity decorator. Later tasks import `from .tracing import traceable`.

- [ ] **Step 1: Failing test** `tests/test_packaging.py`:

```python
import builtins, sys

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

def test_traceable_noop_preserves_function():
    from lunar_tools_art.tracing import traceable
    @traceable(name="x")
    def f(a):
        return a + 1
    assert f(1) == 2
```

- [ ] **Step 2: Run** — expect FAIL.
- [ ] **Step 3: Implement.** `tracing.py`:

```python
"""Optional LangSmith tracing: no-op decorator when langsmith is absent."""
try:
    from langsmith import traceable  # type: ignore
except ImportError:  # pragma: no cover - exercised via test monkeypatch
    def traceable(*dargs, **dkwargs):
        def deco(fn):
            return fn
        return deco
```

(Real langsmith usage in this repo is always `traceable(name=...)`, so the kwargs-only form suffices — no bare-`@traceable` branch.) In `manager.py` replace `from langsmith import traceable` with `from .tracing import traceable`. In `pyproject.toml`:

- `requires-python = ">=3.10"`; remove `"lunar-tools"` dependency; remove the `lunar-art` script entry.
- Declare direct runtime deps current code imports: `requests`, `httpx`, `numpy`, `opencv-python`.
- Extras:

```toml
[project.optional-dependencies]
cloud = ["openai>=1.40", "anthropic>=0.40.0"]
tracing = ["langsmith>=0.1"]
mlx = ["mlx>=0.26", "mlx-whisper>=0.4", "mlx-lm>=0.24", "mflux>=0.6"]
hw = ["sounddevice>=0.5", "pyglet>=2.0", "mido>=1.3", "python-rtmidi>=1.5", "pyzmq>=26", "pynput>=1.7"]
dev = ["pytest>=8", "pytest-mock>=3.14", "responses>=0.25", "pip-tools", "pre-commit", "bandit", "detect-secrets"]
```

Move the module-level `import openai` in `tools.py` inside `Dalle3ImageGenerator.__init__`/`GPT4.__init__`. Delete `src/lunar_tools/`. Regenerate: `pip-compile --extra mlx --extra hw --extra cloud --extra tracing --extra dev --output-file=requirements.txt pyproject.toml`.
- [ ] **Step 4: Run** `LUNAR_HEADLESS=1 pytest tests/test_packaging.py -v && LUNAR_HEADLESS=1 pytest -q` — PASS.
- [ ] **Step 5: Commit** — `git commit -m "fix: package imports cleanly — optional langsmith/openai, declare httpx/requests, drop lunar-tools shim, py3.10 floor"`.

---

### Task 3: tools package skeleton + headless fakes + gated cloud construction

**Files:**
- Create: `src/lunar_tools_art/tools/__init__.py`, `src/lunar_tools_art/tools/headless.py`
- Move: `src/lunar_tools_art/tools.py` → `src/lunar_tools_art/tools/_legacy_cloud.py`; **delete** `GPT4` and `Ollama` classes (dead code; manager never imports them; their test file was removed in Task 0)
- Modify: `src/lunar_tools_art/manager.py` (use `tools.resolve`, gate cloud tools)
- Test: `tests/test_headless.py`

**Interfaces:**
- Produces:
  - `lunar_tools_art.tools` re-exporting every name the manager imports today (`Renderer, Speech2Text, Text2SpeechOpenAI, AudioRecorder, SoundPlayer, KeyboardInput, WebCam, SDXL_TURBO, Dalle3ImageGenerator, FluxImageGenerator, SDXL_LCM, ZMQPairEndpoint, MidiInput`).
  - `headless.headless_active() -> bool`; fakes `FakeRenderer, FakeWebCam, FakeAudioRecorder, FakeSoundPlayer, FakeKeyboardInput, FakeMidiInput, FakeSpeech2Text` matching real signatures with deterministic returns (`FakeWebCam.get_img()` → 480×640×3 zeros uint8; `FakeSpeech2Text.transcribe()` → the `Transcription("hello world", confidence=1.0, language="en")` type once Task 7 lands — until then a plain dict is fine because nothing consumes it headless).
  - `tools.resolve(name) -> type` — fake in headless mode, else real.
  - Manager: cloud-calling tools (`Dalle3ImageGenerator`, `SDXL_TURBO`, `SDXL_LCM`, `Text2SpeechOpenAI`) constructed **only if** `privacy.cloud_allowed()`; otherwise the attribute is `None` with one INFO log. (Task 9 replaces these attributes with `DeprecatedAlias`; this step just stops unconditional cloud construction, satisfying headless/no-network unit runs.)

- [ ] **Step 1: Failing test** `tests/test_headless.py`:

```python
import numpy as np

def test_headless_env_selects_fakes(monkeypatch):
    monkeypatch.setenv("LUNAR_HEADLESS", "1")
    from lunar_tools_art.tools import headless, resolve
    assert headless.headless_active() is True
    assert resolve("WebCam") is headless.FakeWebCam
    img = headless.FakeWebCam().get_img()
    assert isinstance(img, np.ndarray) and img.shape == (480, 640, 3)

def test_manager_headless_no_cloud(monkeypatch):
    monkeypatch.setenv("LUNAR_HEADLESS", "1")
    import lunar_tools_art.privacy as privacy
    monkeypatch.setattr(privacy, "cloud_allowed", lambda cfg=None: False)
    from lunar_tools_art.manager import LunarToolsArtManager
    m = LunarToolsArtManager()
    assert m.dalle3 is None and m.sdxl_turbo is None and m.sdxl_lcm is None
    assert m.webcam is not None
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** as specified in Interfaces. `__init__.py` core:

```python
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

Manager: `from . import tools` and `self._traceable_tool(tools.resolve("ClassName"), "ClassName", ...)`; wrap the four cloud tools in `if privacy.cloud_allowed():` (else set `None`, log once). `FluxImageGenerator` stays a stub until Task 9 replaces the `flux` attribute — acceptable per the transition-window constraint.
- [ ] **Step 4: Run** `LUNAR_HEADLESS=1 pytest -q` — full suite PASS.
- [ ] **Step 5: Commit** — `git commit -m "refactor: tools package, headless fakes, privacy-gated cloud construction; delete dead GPT4/Ollama"`.

---

### Task 4: Real audio — AudioRecorder & SoundPlayer

**Files:**
- Create: `src/lunar_tools_art/tools/audio.py`, `scripts/smoke_audio.py`
- Modify: `src/lunar_tools_art/tools/__init__.py` (re-export from `audio.py`), `src/lunar_tools_art/prototype_base.py` (`get_user_speech` uses `record()`)
- Test: `tests/test_tools_audio.py`

**Interfaces:**
- Consumes: secure temp utils from `src/lunar_tools_art/utils.py`; exceptions from Task 1.
- Produces: `AudioRecorder(output_dir=None, samplerate=16000)` — `.start_recording(file_path: str) -> None`, `.stop_recording() -> str` (path), `.record(duration: float) -> str` (blocking; used by `InteractivePrototype.get_user_speech`); `SoundPlayer()` — `.play_audio(path_or_array, samplerate=24000, blocking=False) -> None`, `.play_sound(path) -> None` (**alias — 8 prototypes call it**). No input device → `HardwareUnavailableError` on first call, warn-once + no-op after.

- [ ] **Step 1: Failing tests** `tests/test_tools_audio.py` (mock `sounddevice` before import):

```python
import sys, types
import numpy as np
import pytest

def _fake_sd(monkeypatch, devices=({"name": "Fake Mic", "max_input_channels": 1},)):
    calls = {}
    sd = types.SimpleNamespace(
        rec=lambda frames, samplerate, channels: np.zeros((frames, channels), dtype="float32"),
        wait=lambda: None,
        play=lambda data, samplerate, blocking=False: calls.setdefault("played", (data, samplerate)),
        query_devices=lambda: list(devices),
    )
    monkeypatch.setitem(sys.modules, "sounddevice", sd)
    return sd, calls

def test_record_writes_wav(tmp_path, monkeypatch):
    _fake_sd(monkeypatch)
    from lunar_tools_art.tools.audio import AudioRecorder
    path = AudioRecorder(output_dir=str(tmp_path)).record(duration=0.1)
    import soundfile as sf
    data, sr = sf.read(path)
    assert path.endswith(".wav") and sr == 16000

def test_start_stop_roundtrip(tmp_path, monkeypatch):
    _fake_sd(monkeypatch)
    from lunar_tools_art.tools.audio import AudioRecorder
    rec = AudioRecorder(output_dir=str(tmp_path))
    target = str(tmp_path / "take.wav")
    rec.start_recording(target)
    out = rec.stop_recording()
    assert out == target

def test_no_device_raises_then_degrades(tmp_path, monkeypatch, caplog):
    _fake_sd(monkeypatch, devices=())
    from lunar_tools_art.tools.audio import AudioRecorder
    from lunar_tools_art.exceptions import HardwareUnavailableError
    rec = AudioRecorder(output_dir=str(tmp_path))
    with pytest.raises(HardwareUnavailableError):
        rec.record(duration=0.1)
    assert rec.record(duration=0.1) is None  # degraded: warn-once, no-op

def test_play_sound_alias(tmp_path, monkeypatch):
    sd, calls = _fake_sd(monkeypatch)
    import soundfile as sf
    wav = str(tmp_path / "s.wav")
    sf.write(wav, np.zeros(160, dtype="float32"), 16000)
    from lunar_tools_art.tools.audio import SoundPlayer
    SoundPlayer().play_sound(wav)
    assert "played" in calls
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** `audio.py`: lazy `import sounddevice as sd` inside methods; 16 kHz mono default (Whisper-native). `record()` = `sd.rec` + `sd.wait` + `soundfile.write` to `output_dir` (secure temp when None). `start_recording`/`stop_recording` buffer via `sd.rec` started nonblocking (or `InputStream` callback) and write on stop. Device check via `query_devices()` — no input channels → raise first time, warn-once + return `None` after. `play_audio` accepts str (soundfile.read → `sd.play`) or ndarray; `play_sound = play_audio` alias with blocking=True default. Update `prototype_base.py` `get_user_speech` to `self.audio_recorder.record(duration=timeout)`. `scripts/smoke_audio.py`: record 2 s, play back, print path.
- [ ] **Step 4: Run** `LUNAR_HEADLESS=1 pytest tests/test_tools_audio.py -v && LUNAR_HEADLESS=1 pytest -q` — PASS. On-machine: `python scripts/smoke_audio.py`.
- [ ] **Step 5: Commit** — `git commit -m "feat: real sounddevice audio recorder/player with degraded mode and play_sound alias"`.

---

### Task 5: Real camera + keyboard + MIDI + ZMQ

**Files:**
- Create: `src/lunar_tools_art/tools/camera.py`, `src/lunar_tools_art/tools/input.py`, `src/lunar_tools_art/tools/net.py`, `scripts/smoke_camera.py`, `scripts/smoke_midi.py`
- Modify: `src/lunar_tools_art/tools/__init__.py` re-exports
- Test: `tests/test_tools_camera.py`, `tests/test_tools_input.py`, `tests/test_tools_net.py`

**Interfaces:**
- Produces:
  - `WebCam(cam_id=0).get_img() -> np.ndarray | None` (RGB; absent camera → warn-once + `None`).
  - `KeyboardInput(window=None)` — `.is_key_pressed(key: str) -> bool`, `.get() -> str | None`. pynput listener by default; when a pyglet `window` is passed (Task 6), hooks pyglet key handlers instead.
  - `MidiInput()` — `.get_latest_message() -> object | None`, `.get(control: int, default=0.0) -> float` (last CC value normalized 0–1; returns `default` when no device/backend, after one warning).
  - `ZMQPairEndpoint(bind: bool = True, address: str = "tcp://127.0.0.1:5871")` — `.send(str)`, `.receive(timeout_ms=0) -> str | None`, `.get_messages() -> list[str]`, `.send_img(np.ndarray)`; exposes `.ip`/`.port` attributes parsed from `address` (a legacy prototype assigns/reads them).

- [ ] **Step 1: Failing tests.** `test_tools_camera.py`: monkeypatch `cv2.VideoCapture` with a stub whose `read()` returns `(True, bgr)` where `bgr[..., 0]` is all 255 — assert returned frame has channel 2 all 255 (BGR→RGB swap) — and a stub with `isOpened() == False` → first `get_img()` warns and returns `None`. `test_tools_input.py`: construct `KeyboardInput` with injected fake listener object; simulate press "q" via its callback; assert `is_key_pressed("q") is True` and `get() == "q"`. `test_tools_net.py`: create bound + connected pair on `tcp://127.0.0.1:5871`, `send("ping")`, assert `receive(timeout_ms=1000) == "ping"`; assert `.port == 5871`. `MidiInput` with monkeypatched `mido.get_input_names()` returning `[]` → `.get(1, default=0.25) == 0.25` and exactly one warning in caplog across two calls.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** the three modules (lazy imports; degraded modes as above; `MidiInput` opens first port from `mido.get_input_names()`, polls with `port.iter_pending()` storing last message and last CC values). Smoke scripts: camera frame via `cv2.imshow` for 5 s; print MIDI messages for 5 s.
- [ ] **Step 4: Run** the three test files + full suite headless — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: real webcam, keyboard, MIDI, ZMQ tools"`.

---

### Task 6: Renderer + main-loop integration

**Files:**
- Create: `src/lunar_tools_art/tools/display.py`, `scripts/smoke_renderer.py`
- Modify: `src/lunar_tools_art/tools/__init__.py`, `src/lunar_tools_art/manager.py` (add `self.main_queue = MainLoopQueue()`), `src/lunar_tools_art/prototype_base.py` (`run()` drains queue), `src/lunar_tools_art/loop_utils.py` (`run_until_quit` drains queue)
- Test: `tests/test_tools_display.py`, extend `tests/test_prototype_base.py`

**Interfaces:**
- Consumes: `MainLoopQueue` (Task 1).
- Produces: `Renderer(width, height, backend="pyglet"|"opencv"|"null")` — `.render(image: np.ndarray) -> None`, `.set_size(w, h)`, `.close()`, `.window` (pyglet window or `None`). `render()` raises `RuntimeError` off the main thread. `backend="null"` records frames in `.frames` (tests/headless). `PrototypeBase.run()` calls `self.manager.main_queue.drain()` each loop iteration before `update()`; `run_until_quit` does the same when the manager has a `main_queue`.

- [ ] **Step 1: Failing tests** `tests/test_tools_display.py`:

```python
import threading
import numpy as np
import pytest
from lunar_tools_art.tools.display import Renderer

def _render_in_thread(r):
    box = {}
    def target():
        try:
            r.render(np.zeros((64, 64, 3), dtype="uint8"))
            box["err"] = None
        except RuntimeError as e:
            box["err"] = e
    t = threading.Thread(target=target)
    t.start(); t.join()
    return box["err"]

def test_render_off_main_thread_raises():
    r = Renderer(64, 64, backend="null")
    assert isinstance(_render_in_thread(r), RuntimeError)

def test_null_backend_records_frames():
    r = Renderer(64, 64, backend="null")
    r.render(np.zeros((64, 64, 3), dtype="uint8"))
    assert len(r.frames) == 1
```

Extend `tests/test_prototype_base.py`: a prototype whose `setup` posts `flag.append(1)` to `manager.main_queue` from a worker thread; after `run()` with immediate exit, assert the flag was drained.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.** `display.py`: main-thread check first (`threading.current_thread() is threading.main_thread()`); pyglet backend lazily creates `pyglet.window.Window`, numpy RGB → `pyglet.image.ImageData(w, h, "RGB", img[::-1].tobytes())`, blit + `window.dispatch_events()` per render; opencv backend `cv2.imshow` + `waitKey(1)`; null backend appends to `self.frames`. Wire `main_queue` into manager, `PrototypeBase.run()` loop, and `run_until_quit`. Keyboard: when Renderer backend is pyglet, manager passes `window=renderer.window` to `KeyboardInput`.
- [ ] **Step 4: Run** test files + full suite headless — PASS. On-machine: `python scripts/smoke_renderer.py` (animated gradient, ESC quits).
- [ ] **Step 5: Commit** — `git commit -m "feat: pyglet renderer with main-thread enforcement; main-loop queue drained by prototype loops"`.

---

### Task 7: Speech2Text on mlx-whisper (+ faster-whisper option)

**Files:**
- Create: `src/lunar_tools_art/tools/stt.py`, `scripts/smoke_stt.py`
- Modify: `src/lunar_tools_art/tools/__init__.py`, `src/lunar_tools_art/tools/headless.py` (FakeSpeech2Text returns a `Transcription`), `settings.toml` (`[whisper] backend = "mlx-whisper"` — keep section name)
- Test: `tests/test_tools_stt.py`

**Interfaces:**
- Consumes: `config.get("whisper.backend", "mlx-whisper")`, `config.get("whisper.model", "base.en")`, `inference_gate.INFERENCE_LOCK`.
- Produces:

```python
class Transcription(str):
    """A str (the transcript) carrying transcription metadata."""
    def __new__(cls, text: str, confidence: float = 0.0, language: str = ""):
        obj = super().__new__(cls, text)
        obj.text = str(text)
        obj.confidence = confidence
        obj.language = language
        return obj
```

`Speech2Text().transcribe(path_or_array) -> Transcription`. Legacy consumers calling `.strip()` / using it as a string keep working; new code reads `.confidence`. Confidence = clamped `exp(mean(segment avg_logprob))`. Model-load or inference failure → `InferenceError`.

- [ ] **Step 1: Failing tests** — monkeypatch a fake `mlx_whisper` module in `sys.modules` whose `transcribe()` returns `{"text": " hi there", "language": "en", "segments": [{"avg_logprob": -0.2}]}`:

```python
def test_transcribe_returns_transcription(fake_mlx_whisper):
    from lunar_tools_art.tools.stt import Speech2Text, Transcription
    result = Speech2Text().transcribe("x.wav")
    assert isinstance(result, Transcription)
    assert result.strip() == "hi there"          # legacy string usage
    assert 0 < result.confidence <= 1
    assert result.language == "en"

def test_inference_failure_raises(fake_mlx_whisper_broken):
    from lunar_tools_art.tools.stt import Speech2Text
    from lunar_tools_art.exceptions import InferenceError
    import pytest
    with pytest.raises(InferenceError):
        Speech2Text().transcribe("x.wav")
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** `stt.py`: backend dispatch on config; mlx path lazily `import mlx_whisper`, call under `INFERENCE_LOCK`: `mlx_whisper.transcribe(audio, path_or_hf_repo=f"mlx-community/whisper-{model}-mlx")`; faster-whisper path mirrors when installed. Update `FakeSpeech2Text` to return `Transcription("hello world", confidence=1.0, language="en")`. `scripts/smoke_stt.py`: record 3 s via `AudioRecorder`, print transcript + confidence.
- [ ] **Step 4: Run** tests + full suite headless — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: mlx-whisper STT returning str-compatible Transcription with confidence"`.

---

### Task 8: Text2Speech adapter, LLM privacy gating, mlx-lm backend, base-class fixes

**Files:**
- Create: `src/lunar_tools_art/tools/tts.py`
- Modify: `src/lunar_tools_art/manager.py` (text2speech wiring; expose `config`), `src/lunar_tools_art/prototype_base.py` (fix `generate_text`, `generate_image` lookups, `self.manager.config`), `src/lunar_tools_art/llm_backends.py` (privacy gate + `MLXLocalBackend`), `settings.toml` (`[llm.mlx]`)
- Test: `tests/test_tools_tts.py`, extend `tests/test_llm_backends.py`, extend `tests/test_prototype_base.py`

**Interfaces:**
- Consumes: `VoiceClient.synthesize(text, voice, emotion=None) -> bytes | None` (`voice_client.py:52` — **returns raw audio bytes, not a path**), `privacy.require_cloud`, `INFERENCE_LOCK`.
- Produces:
  - `Text2Speech(voice_client, default_voice="galadriel", output_dir=None).generate(text: str, voice: str | None = None) -> str` — calls `synthesize`, writes the returned bytes to a `.wav` in `output_dir` (secure temp default), returns the path; `synthesize` returning `None` or raising → `InferenceError` including a `voice_client.health()` snapshot.
  - `ClaudeBackend`, `OllamaCloudBackend`, `OpenRouterBackend` call `privacy.require_cloud(<name>)` first in `__init__` — `create_backend` with a cloud provider under `local-only` raises `CloudDisabledError`.
  - `MLXLocalBackend(model: str).generate(prompt, system_prompt=None) -> str | None` — lazy `from mlx_lm import load, generate`; model cached at class level (one load per process); inference under `INFERENCE_LOCK`; registered in `create_backend` for `provider = "mlx"`.
  - `AIPrototype.generate_text` calls `self.llm.generate(prompt, system_prompt=...)`, dropping unsupported kwargs (log-debug what was dropped); `self.llm = self.manager.llm_backend` (not `gpt4`); `AIPrototype.generate_image` uses `self.manager.image_gen` (added Task 9 — until then attribute may be `None`; method raises `AIServiceError` when generator missing, which is the current behavior for missing tools).
  - `manager.config` property returning the config singleton (fixes latent `prototype_base.py` AttributeError).
  - `manager.gpt4` stays as a backward-compat alias for `llm_backend` (documented in code comment).

- [ ] **Step 1: Failing tests.** `tests/test_tools_tts.py`:

```python
import pytest

class StubVC:
    def __init__(self, payload=b"RIFFfakewav"):
        self.payload = payload
        self.calls = []
    def synthesize(self, text, voice, emotion=None):
        self.calls.append((text, voice, emotion))
        return self.payload
    def health(self):
        return {"status": "down"}

def test_generate_writes_bytes_to_wav(tmp_path):
    from lunar_tools_art.tools.tts import Text2Speech
    vc = StubVC()
    t2s = Text2Speech(vc, output_dir=str(tmp_path))
    path = t2s.generate("hello")
    assert path.endswith(".wav")
    assert open(path, "rb").read() == b"RIFFfakewav"
    assert vc.calls[0][1] == "galadriel"   # default voice

def test_none_synthesis_raises(tmp_path):
    from lunar_tools_art.tools.tts import Text2Speech
    from lunar_tools_art.exceptions import InferenceError
    with pytest.raises(InferenceError):
        Text2Speech(StubVC(payload=None), output_dir=str(tmp_path)).generate("hello")
```

`test_llm_backends.py` additions: `create_backend({"provider": "claude", ...})` under monkeypatched `privacy.cloud_allowed → False` raises `CloudDisabledError`; `create_backend({"provider": "mlx", "mlx": {"model": "m"}})` with fake `mlx_lm` module returns `MLXLocalBackend`. `test_prototype_base.py` additions: `AIPrototype.generate_text` with fake `llm_backend.generate` returning "ok" → "ok", and passing `temperature=0.5` doesn't raise.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** per Interfaces. Add `settings.toml`: `[llm.mlx]\nmodel = "mlx-community/Llama-3.2-3B-Instruct-4bit"`. Manager wires `self.text2speech = Text2Speech(self.voice_client)` when `voice_client` is up, else keeps gated `Text2SpeechOpenAI`/`None`.
- [ ] **Step 4: Run** the three test files + full suite headless — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: Afterwords TTS adapter (bytes→wav), privacy-gated cloud LLMs, mlx-lm backend, base-class API fixes"`.

---

### Task 9: Unified ImageGenerator (mflux + gated cloud) with adapting aliases

**Files:**
- Create: `src/lunar_tools_art/tools/images.py`, `scripts/smoke_imagegen.py`
- Modify: `src/lunar_tools_art/manager.py` (`image_gen` + aliases replace Task-3 gated attributes), `settings.toml` (`[image]`)
- Test: `tests/test_image_generator.py`

**Interfaces:**
- Consumes: `privacy`, `INFERENCE_LOCK`, `MainLoopQueue`.
- Produces:
  - `ImageGenerator(backend="mflux", model="schnell", quantize=4, output_dir="outputs/images")`:
    - `.generate(prompt: str, size: tuple[int, int] = (1024, 1024), seed: int | None = None) -> tuple[str, dict]` — `(png_path, {"backend", "seed", "latency_s"})`
    - `.generate_async(prompt, main_queue, on_ready, size=(1024, 1024)) -> None` — worker thread runs `generate`, posts `on_ready(path, meta)` to `main_queue`
    - Backends: `fake` (PIL 1×1 png; default in headless), `mflux` (lazy import under `INFERENCE_LOCK`), `openai`, `replicate` (ported from `_legacy_cloud.py`, download result to `output_dir`; `privacy.require_cloud` in `__init__`).
  - `DeprecatedAlias(gen, name)` — `.generate(prompt, **legacy_kwargs) -> tuple[str, dict]`; warns `DeprecationWarning` once; **adapts legacy kwargs**: maps `image_size="square_small"|"square_hd"|...` → pixel sizes (`512²`, `1024²`; default `1024²` for unknown values), accepts and forwards `seed=`, silently drops `num_inference_steps=`/`quality=`/other unknowns with a debug log. This absorbs every call pattern found in the 27 prototypes, including `temporal-art-gallery-prototype.py` and `chat-room-narrative-quilt.py`.
  - Manager: `self.image_gen = ImageGenerator(**config.get("image", {}))` (backend forced to `fake` when headless); `self.dalle3/sdxl_turbo/sdxl_lcm/flux = DeprecatedAlias(self.image_gen, <name>)` — replacing the Task-3 `None`/gated attributes so aliases exist regardless of privacy mode (local mflux serves them).
  - **mflux API note:** the exact mflux import surface changes between releases. Implementation step: pin the version installed by Task 2's `pip-compile`, read its README/`--help`, and wrap it in a private `_MfluxBackend.generate()` so the adapter is the only mflux-touching code. Do not assume `from mflux import Flux1, Config` — verify first.

- [ ] **Step 1: Failing tests**:

```python
import warnings
import pytest

def test_generate_returns_tuple(tmp_path):
    from lunar_tools_art.tools.images import ImageGenerator
    gen = ImageGenerator(backend="fake", output_dir=str(tmp_path))
    path, meta = gen.generate("a moon garden", size=(64, 64))
    assert path.endswith(".png") and meta["backend"] == "fake"

def test_alias_unpacking_and_legacy_kwargs(tmp_path):
    from lunar_tools_art.tools.images import ImageGenerator, DeprecatedAlias
    alias = DeprecatedAlias(ImageGenerator(backend="fake", output_dir=str(tmp_path)), "dalle3")
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        image, _ = alias.generate("p", image_size="square_hd", num_inference_steps=4, seed=7)
    assert image.endswith(".png")
    assert any(issubclass(x.category, DeprecationWarning) for x in w)

def test_generate_async_posts_to_queue(tmp_path):
    from lunar_tools_art.tools.images import ImageGenerator
    from lunar_tools_art.loop_utils import MainLoopQueue
    import time
    gen = ImageGenerator(backend="fake", output_dir=str(tmp_path))
    q, got = MainLoopQueue(), []
    gen.generate_async("p", q, lambda path, meta: got.append(path), size=(32, 32))
    for _ in range(50):
        q.drain(); 
        if got: break
        time.sleep(0.05)
    assert got and got[0].endswith(".png")

def test_cloud_backend_blocked_local_only(tmp_path, monkeypatch):
    import lunar_tools_art.privacy as privacy
    monkeypatch.setattr(privacy, "cloud_allowed", lambda cfg=None: False)
    from lunar_tools_art.tools.images import ImageGenerator
    from lunar_tools_art.exceptions import CloudDisabledError
    with pytest.raises(CloudDisabledError):
        ImageGenerator(backend="openai", output_dir=str(tmp_path))
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** per Interfaces; add `[image]\nbackend = "mflux"\nmodel = "schnell"\nquantize = 4` to `settings.toml`; `scripts/smoke_imagegen.py` generates one real mflux image, prints path + latency — **record the latency in spec §4**.
- [ ] **Step 4: Run** tests + full suite headless — PASS. On-machine smoke.
- [ ] **Step 5: Commit** — `git commit -m "feat: unified image generator (mflux default, gated cloud, kwarg-adapting tuple aliases)"`.

---

### Task 10: Manager integration pass

**Files:**
- Modify: `src/lunar_tools_art/manager.py`
- Test: `tests/test_manager_integration.py`

**Interfaces:**
- Produces: `LunarToolsArtManager()` under `LUNAR_HEADLESS=1` yields non-None `renderer, speech2text, text2speech (or None w/o Afterwords+cloud), audio_recorder, sound_player, keyboard_input, webcam, image_gen, dalle3, sdxl_turbo, sdxl_lcm, flux, zmq_pair_endpoint, midi_input, main_queue, emotion_detector, prosody_analyzer, voice_client, config`; `llm_backend` None-or-backend per config; `gpt4 is llm_backend`; in `local-only`, no constructed object performs network calls at init.

- [ ] **Step 1: Failing test** — instantiate manager headless; assert every attribute above exists; `manager.dalle3.generate("x")` returns a 2-tuple (fake backend); `manager.config.get("privacy.mode", "local-only")` works.
- [ ] **Step 2: Run** — FAIL where wiring is incomplete.
- [ ] **Step 3: Implement** remaining wiring; extend `_traceable_tool` name table with `ImageGenerator`, `Text2Speech`.
- [ ] **Step 4: Run** `LUNAR_HEADLESS=1 pytest -q` — full suite PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: manager fully wired to real tools layer"`.

---

### Task 11: Prototype sweep — automated smoke matrix

**Files:**
- Create: `tests/test_prototype_smoke.py`, `PROTOTYPE_STATUS.md`
- Modify: individual `prototypes/*.py` as failures dictate

**Interfaces:**
- Consumes: everything above via `LunarToolsArtManager`.
- Produces: parametrized smoke test over the 27 legacy prototypes; `PROTOTYPE_STATUS.md` matrix (name | status `works`/`degraded`/`needs-rework` | reason | verified-on-hardware).

- [ ] **Step 1: Write the harness** (doubles as the failing test — most prototypes fail initially). Handle both prototype styles: `PrototypeBase` subclasses (patch `should_exit` to exit after 3 updates) and legacy manual-`run()`/`run_until_quit` classes (instantiate only; mark `needs-rework` if unrunnable non-interactively):

```python
import importlib.util, itertools, pathlib
import pytest

PROTO_DIR = pathlib.Path(__file__).parent.parent / "prototypes"
SKIP = {"__init__.py", "example_base_usage.py", "audio_mirror.py", "ai-mirror-of-truth.py"}
FILES = sorted(p for p in PROTO_DIR.glob("*.py") if p.name not in SKIP)

def load(path):
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def find_class(mod):
    candidates = [v for v in vars(mod).values()
                  if isinstance(v, type) and v.__module__ == mod.__name__
                  and (hasattr(v, "run") or hasattr(v, "update"))]
    assert candidates, f"no prototype class found in {mod.__name__}"
    return candidates[0]

@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_prototype_smoke(path, headless_manager, monkeypatch):
    mod = load(path)
    cls = find_class(mod)
    proto = cls(headless_manager)
    if hasattr(proto, "setup") and hasattr(proto, "update"):
        counter = itertools.count()
        if hasattr(proto, "should_exit"):
            monkeypatch.setattr(proto, "should_exit", lambda: next(counter) >= 3)
        proto.setup()
        for _ in range(3):
            proto.update()
        proto.cleanup()
    # legacy manual-run prototypes: construction without error is the smoke bar
```

Add a session-scoped `headless_manager` fixture to `tests/conftest.py` (sets `LUNAR_HEADLESS=1` via `monkeypatch.setenv` at session setup, returns one manager).
- [ ] **Step 2: Run** `LUNAR_HEADLESS=1 pytest tests/test_prototype_smoke.py -v`; paste the failure list into `PROTOTYPE_STATUS.md` as the starting matrix.
- [ ] **Step 3: Fix prototypes** one at a time or in small batches; commit per batch (`fix(prototypes): <names> run against real manager`). Known fixes from QA:
  - `augmented_audio_tours.py`: `gpt4.generate_vision(...)` → describe-then-`llm_backend.generate` (vision deferred; mark `degraded`).
  - `interactive-storytelling-canvas-prototype.py`: `from utils import record_and_transcribe_speech` → rewrite against `manager.audio_recorder` + `manager.speech2text` (no top-level `utils` module exists).
  - `collaborative_art.py`: `self.server.ip`/`.port` writes — supported by Task 5's `ZMQPairEndpoint` attributes.
  - Tuple unpackers and `image_size=` kwargs — handled by `DeprecatedAlias`; verify, don't rewrite.
  - Manual-loop prototypes without exit handling: adapt to `PrototypeBase` **only if trivial**, else `needs-rework` with reason.
- [ ] **Step 4: Gate** — `LUNAR_HEADLESS=1 pytest -q` fully green; every `PROTOTYPE_STATUS.md` row has a status.
- [ ] **Step 5: Commit** — `git commit -m "feat: all legacy prototypes pass smoke matrix; status matrix added"`.

---

### Task 12: On-machine verification (real hardware, one per category)

**Files:**
- Modify: `PROTOTYPE_STATUS.md` (verified column), `docs/superpowers/specs/2026-07-10-mlx-native-rework-design.md` (benchmark numbers)

**Interfaces:** none new — manual verification on the M5, not CI.

- [ ] **Step 1:** `python scripts/smoke_renderer.py && python scripts/smoke_audio.py && python scripts/smoke_camera.py && python scripts/smoke_stt.py && python scripts/smoke_imagegen.py` — all succeed; note imagegen latency.
- [ ] **Step 2:** Run one prototype per category via `python lunar_tools_demo.py --demo <name>`: image-gen-heavy (`evolving-cosmic-mural-prototype`), audio-reactive (`audio-reactive-fractal-forest`), webcam (`sentiment_analysis_display`), MIDI (`dynamic_visuals` if hardware attached, else note skipped), LLM/storytelling (`interactive_storytelling`). Each runs ≥60 s and exits cleanly on `q`/ESC.
- [ ] **Step 3:** Update `PROTOTYPE_STATUS.md` verified column + spec §4 latency note. Commit — `git commit -m "docs: on-machine verification results and mflux benchmarks"`.

---

### Task 13: Flagship verification — emotion model + Audio Mirror + Mirror of Truth

**Files:**
- Modify: `src/lunar_tools_art/emotion.py` (real ONNX classifier in the existing fallback chain), `settings.toml` (`[emotion] model_path`), `.gitignore` (`models/`), `PROTOTYPE_STATUS.md`
- Create: `tests/test_emotion_real.py`, `scripts/smoke_emotion.py`, `scripts/fetch_models.py` (downloads FER+ `emotion-ferplus-8.onnx` with checksum into `models/`)

**Interfaces:**
- Consumes: existing API — `EmotionDetector()` (no-arg today; gains optional `model_path=None` kwarg defaulting from config), `.detect(frame) -> list[EmotionResult]`, `.has_classifier` property (`emotion.py:42-47`).
- Produces: with a valid ONNX model file, `has_classifier is True` and `detect()` returns `EmotionResult`s with one of the 8 FER+ labels and real confidence; without the file, current placeholder behavior is unchanged (all existing `test_emotion.py` tests must still pass).

- [ ] **Step 1: Failing test** `tests/test_emotion_real.py` — monkeypatch `cv2.dnn.readNetFromONNX` to return a stub net whose `forward()` yields logits peaking at index 1 ("happiness" in FER+ order: neutral, happiness, surprise, sadness, anger, disgust, fear, contempt); construct `EmotionDetector(model_path=str(tmp_fake_onnx))`; assert `has_classifier is True`; feed a frame that the existing Haar path detects (or monkeypatch `detectMultiScale` to return one box) and assert `detect(frame)[0].emotion == "happiness"` with `confidence > 0.5`.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** the ONNX path (OpenCV DNN, 64×64 grayscale input, softmax over logits) inside the existing `_classify_emotion`; `fetch_models.py` downloads from the official onnx/models release URL, verifies SHA-256. Add `models/` to `.gitignore`.
- [ ] **Step 4: Run** `LUNAR_HEADLESS=1 pytest tests/test_emotion_real.py tests/test_emotion.py -v && LUNAR_HEADLESS=1 pytest -q` — PASS. On-machine: `python scripts/fetch_models.py && python scripts/smoke_emotion.py` (webcam window, emotion label overlay, report FPS).
- [ ] **Step 5: On-machine flagship runs** — start Afterwords (`cd ../afterwords && ./afterwords.sh`), `curl localhost:7860/health`; run `python lunar_tools_demo.py --demo audio-mirror` and `--demo ai-mirror-of-truth` end-to-end; record the March validation-gate numbers (TTS latency, clone quality at 5/15 s, `memory_pressure`, emotion FPS, informal WER) in spec §6.
- [ ] **Step 6: Commit** — `git commit -m "feat: real FER+ emotion classifier; flagship prototypes verified end-to-end"`.

---

### Task 14: CI, docs, and closeout

**Files:**
- Modify: `.github/workflows/ci.yml` (set `LUNAR_HEADLESS: "1"`; drop Python 3.9 from the matrix, keep 3.10/3.12; install `pip install -e ".[dev]"` on Linux — no `mlx`/`hw` extras), `CLAUDE.md` (tools architecture, headless mode, privacy gate, corrected test count and security-history finding; remove stale "59 tests" claims), `README.md` (macOS install: `pip install -e ".[mlx,hw,dev]"`)

- [ ] **Step 1:** Update CI; the Linux `pip install -e ".[dev]" && LUNAR_HEADLESS=1 pytest -q` run passing is the proof that all MLX/hardware imports are lazy.
- [ ] **Step 2:** Update `CLAUDE.md` and `README.md` to match reality.
- [ ] **Step 3:** `pre-commit run --all-files`, `bandit -r src/ prototypes/`, `detect-secrets scan --baseline .secrets.baseline` — all clean.
- [ ] **Step 4:** Commit — `git commit -m "chore: CI headless matrix (3.10/3.12), docs updated to rework reality"` and push.

---

## Self-Review Notes

- Spec coverage: Phase 0 → Task 0; Phase 1 → Tasks 1–8; Phase 2 → Task 9; Phase 3 → Tasks 10–12; Phase 4 → Task 13; config/packaging §7 → Tasks 2, 7, 9, 14; error handling §8 → Task 1 + per-tool tests.
- Type consistency: image contract `tuple[str, dict]` (Tasks 9–11); STT returns `Transcription` str-subclass (Tasks 7, 3-fakes, 8-consumers); `record(duration) -> str` consumed by `get_user_speech` (Tasks 4, 8); `MainLoopQueue` defined Task 1, drained Task 6, fed Task 9.
- Deliberately deferred: vision LLM (Task 11, `degraded`), MIDI hardware check optional (Task 12), mflux exact API resolved at implementation against the pinned version (Task 9 note).
