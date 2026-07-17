# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python-based collection of interactive audiovisual art installations built with the Lunar Tools framework. The project creates immersive, AI-driven experiences that combine speech-to-text, AI text generation, audio synthesis, image generation, and real-time visual rendering for artistic installations.

## Development Commands

### Installation & Setup

```bash
# Create virtual environment
python3 -m venv env
source env/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install .  # Install the lunar_tools_art package

# Configure API keys in .env file
cp .env.example .env  # Add your OpenAI, Replicate API keys
```

### Running Prototypes

```bash
# List every demo with requirements and headless-smoke status (also the no-args behavior)
python lunar_tools_demo.py list

# Preflight checks — whole environment, or one demo's requirements
python lunar_tools_demo.py doctor
python lunar_tools_demo.py doctor audio-mirror

# Preflight then launch (--force skips preflight; --debug shows tracebacks)
python lunar_tools_demo.py run interactive-storytelling
python lunar_tools_demo.py run whispers --config duration=5 --config "window_size=(800,600)"

# Legacy alias, still supported:
python lunar_tools_demo.py --demo interactive-storytelling
```

Demo metadata (explicit entry-point class names, per-demo requirements, assets) lives in
`src/lunar_tools_art/demo_registry.py`; preflight checks in `doctor.py` +
`hardware_probes.py`/`service_probes.py`; CLI styling in `cli_style.py`. `--config` takes
repeatable `KEY=VALUE` pairs (comma-joined also works; tuples like `(800,600)` parse). See
`docs/RUNNING.md` for the full runbook.

### Testing

```bash
# Run all tests headless (deterministic in-repo fakes, no hardware/cloud calls)
LUNAR_HEADLESS=1 pytest -q

# Run specific test file
LUNAR_HEADLESS=1 pytest tests/test_lunar_tools_art.py

# Run with verbose output
LUNAR_HEADLESS=1 pytest -v
```

`LUNAR_HEADLESS=1` is required for the test suite (and for CI) — without it, tools resolve to
their real hardware/cloud-backed implementations (mic, webcam, MLX models, cloud LLM/TTS/image
APIs) instead of the fakes in `src/lunar_tools_art/tools/headless.py`. Current baseline: 244
passed, 0 failed, 6 warnings (no xfails remain).

## Architecture

### Core Components

**Manager (`src/lunar_tools_art/manager.py`)**

- Centralized initialization and management of all Lunar Tools instances
- Handles configuration via `settings.toml` and environment variables
- Provides tracing/monitoring via LangSmith for AI interactions
- Manages: Speech2Text, Text2Speech, AudioRecorder, SoundPlayer, Renderer, WebCam, Image Generators (DALL-E, SDXL, Flux), MIDI/Keyboard input
- New infrastructure: `llm_backend` (pluggable LLM), `emotion_detector`, `prosody_analyzer`, `voice_client` (Afterwords TTS)

**Configuration (`src/lunar_tools_art/config.py`)**

- TOML-based configuration with environment variable overrides
- PII filtering for logs to prevent API key leakage
- Supports nested configuration via double underscores in env vars (e.g., `LLM__PROVIDER=ollama`)

**Prototype Base Classes (`src/lunar_tools_art/prototype_base.py`)**

- **PrototypeBase**: Core functionality for all prototypes with exception handling, resource management, and graceful shutdown
- **InteractivePrototype**: Extends PrototypeBase with speech-to-text integration and user interaction helpers
- **AIPrototype**: Extends PrototypeBase with LLM integration and image generation utilities
- Provides standardized patterns for setup, update loops, and cleanup

**CLI Entry Point (`lunar_tools_demo.py`)**

- Auto-discovers all prototype classes in `prototypes/` directory
- Converts filenames to class names (e.g., `interactive-storytelling.py` → `InteractiveStorytelling`)
- Supports runtime configuration via `--config` parameter

### Prototypes Structure

All art installations are in `prototypes/` and follow a consistent pattern:

- Each prototype is a standalone Python file with a corresponding class
- Classes accept a `LunarToolsArtManager` instance in their constructor
- All have a `run()` method that starts the interactive experience
- Use keyboard input (typically ESC/Q) to exit experiences gracefully

**Shared Infrastructure (new — March 2026)**

- **LLM Backends (`src/lunar_tools_art/llm_backends.py`)**: Pluggable LLM abstraction supporting Claude API, Ollama (local), Ollama Cloud, and OpenRouter. All backends implement `.generate(prompt, system_prompt)`. Selected via `settings.toml [llm]` section.
- **Emotion Detection (`src/lunar_tools_art/emotion.py`)**: Face detection via OpenCV Haar cascade, with a FER+ ONNX emotion classifier fetched via `scripts/fetch_models.py` (on-machine verification against real hardware still pending). Fallback chain: FER+ ONNX (via OpenCV DNN) -> Haar cascade placeholder (confidence=0.0). `has_classifier` property indicates when a real model is loaded.
- **Prosody Analysis (`src/lunar_tools_art/prosody.py`)**: Voice prosody extraction via librosa — pitch, energy, pace, pauses, spectral features. Pure signal processing, no ML. Infers coarse emotion tag from prosody heuristics.
- **Voice Client (`src/lunar_tools_art/voice_client.py`)**: HTTP client for the Afterwords TTS server. Supports synthesis, voice cloning, session palette management, and cleanup.
- **Audio Mirror FSM (`src/lunar_tools_art/audio_mirror_fsm.py`)**: Pure-logic state machine for the Audio Mirror installation: IDLE -> DETECTION -> FIRST_CAPTURE -> DEEPENING -> ORACLE -> DEPARTURE.

**Tools Package (`src/lunar_tools_art/tools/`) — MLX-native rework**

- Per-domain modules — `audio.py`, `camera.py`, `display.py`, `images.py`, `input.py`, `net.py`, `stt.py`, `tts.py` — each wrapping a real hardware/cloud-backed implementation behind a lazy import, plus `headless.py` providing deterministic in-repo fakes for every one of them.
- `resolve(name)` in `tools/__init__.py` is the single entry point consumers use to obtain a tool instance: when `LUNAR_HEADLESS=1` (checked via `headless.headless_active()`) and `name` is in the `_FAKES` table, the fake is returned instead of constructing the real backend. This is what keeps `mlx`/`hw`-extras imports out of the default/Linux/CI import path — they only happen if `resolve()` actually reaches the real-backend branch.
- **STT**: `Transcription` (in `stt.py`) is a `str` subclass — callers can treat it as plain text while it also carries recognition metadata (confidence, duration, etc.) as attributes.
- **Images**: a single unified `ImageGenerator` in `images.py` replaces the old per-provider classes; it defaults to `mflux` (MLX-native Flux) on real hardware and to a fake backend under `LUNAR_HEADLESS`. The old provider-specific names (`Dalle3ImageGenerator`, `SDXL_TURBO`, etc.) remain as `DeprecatedAlias` wrappers that adapt kwargs and emit a `DeprecationWarning` pointing callers at `manager.image_gen`.
- **Privacy gate**: `privacy.mode` in `settings.toml` defaults to `"local-only"`, which blocks construction of any cloud-backed LLM/TTS/image backend (a cloud LLM provider is rejected and `llm_backend` is disabled, not silently swapped to Ollama) and rejects non-local URLs for nominally-local backends (Ollama base_url, Afterwords server_url); `"cloud-ok"` allows other providers (`"cloud-llm"` is a deprecated alias for `"cloud-ok"`). The gate is enforced at construction time in the relevant `tools/` modules, not just at call time.
- **`MainLoopQueue`**: cross-thread queue used to hand work (e.g. async STT/LLM results) back into a prototype's synchronous main loop.
- **Prototype status matrix**: `PROTOTYPE_STATUS.md` tracks per-prototype smoke status against the headless tools layer — as of the July 2026 sweep, 28 `works`, 1 `degraded` (`augmented_audio_tours.py`, pending a vision-capable LLM backend), 0 `needs-rework` (of 29 total).

### Key Technologies

- **AI Models**: Pluggable LLM (Claude/Ollama/Ollama Cloud/OpenRouter), DALL-E 3/SDXL/Flux for image generation
- **Audio**: Afterwords TTS server (Qwen3-TTS on MLX, voice cloning), speech recognition, real-time prosody analysis with librosa
- **Visuals**: OpenGL-based renderer, real-time image display, camera mirror with overlays
- **Input**: MIDI controllers, keyboard input, microphone, webcam
- **Monitoring**: LangSmith tracing for AI interactions, comprehensive logging

## Configuration

The system uses `settings.toml` for configuration:

- `llm.provider`: Choose between "ollama", "mlx", "claude", "ollama-cloud", or "openrouter"
- `llm.ollama.model`: Specify Ollama model (default: "llama3.1:8b")
- `llm.claude.model`: Specify Claude model (default: "claude-sonnet-4-20250514")
- `afterwords.server_url`: Afterwords TTS server URL (default: "http://localhost:7860")
- `afterwords.default_voice`: Default voice for TTS (default: "galadriel")
- `emotion.confidence_threshold`: Minimum confidence for emotion detection
- `privacy.mode`: "local-only" (default) or "cloud-ok" (allows cloud providers; "cloud-llm" is a deprecated alias)
- `renderer.width/height`: Set display dimensions
- `logging.level`: Set log level
- Environment variables override TOML settings
- Cloud LLM backends require API keys: `ANTHROPIC_API_KEY`, `OLLAMA_CLOUD_API_KEY`, `OPENROUTER_API_KEY`

## Common Patterns

**Creating New Prototypes:**

**Option 1: Using Base Classes (Recommended)**
1. Create new file in `prototypes/` following naming convention
2. Import appropriate base class: `PrototypeBase`, `InteractivePrototype`, or `AIPrototype`
3. Inherit from base class and implement required methods: `setup()`, `update()`, `cleanup()`
4. Use standardized configuration and error handling patterns
5. Add smoke test in `tests/test_lunar_tools_art.py`

**Option 2: Manual Implementation (Legacy)**
1. Create class with CamelCase name matching filename
2. Accept `LunarToolsArtManager` in constructor
3. Implement `run()` method with main loop and keyboard exit handling
4. Handle exceptions and resource cleanup manually

**Testing Prototypes:**

- All prototypes have smoke tests that mock keyboard input to ensure basic instantiation
- Tests verify Manager initialization and tool availability
- Use mocking for external API calls and hardware dependencies

## Security & Development Practices

**Pre-commit Hooks (`.pre-commit-config.yaml`)**

- Comprehensive security scanning with detect-secrets, bandit
- Code quality enforcement with black, isort, ruff
- Automatic trailing whitespace and YAML validation
- Run `pre-commit install` after cloning to enable hooks

**Security Infrastructure**

- **PII Filtering**: Enhanced patterns in `config.py` for API keys, tokens, emails, phone numbers
- **Secrets Detection**: `.secrets.baseline` file tracks and manages known secrets
- **Secure File Operations**: `src/lunar_tools_art/utils.py` provides secure temp file creation
- **Exception Handling**: Centralized error handling patterns in `src/lunar_tools_art/exceptions.py`

**Environment Configuration**

- Use `.env.example` as template for API key setup
- Never commit actual API keys - use environment variables
- Configuration supports nested settings via `LLM__PROVIDER=ollama` format

**Development Workflow**

1. Install pre-commit hooks: `pre-commit install`
2. Run security scan: `bandit -r src/ prototypes/`
3. Run tests: `LUNAR_HEADLESS=1 pytest -q`
4. Check for secrets: `detect-secrets scan --baseline .secrets.baseline`  # pragma: allowlist secret

## Audio Mirror & MLX-Native Rework (March–July 2026)

New art installation prototypes and a rebuilt shared tools layer for running natively on Apple
Silicon, with lazy hardware/cloud imports so the same codebase runs headless in CI:

- **Audio Mirror** (`prototypes/audio_mirror.py`): Installation that captures a viewer's voice, progressively clones it via Afterwords TTS, and speaks back personal insights in the viewer's own voice. Uses FSM-driven interaction with 6 phases.
- **Mirror of Truth Rewrite** (`prototypes/ai-mirror-of-truth.py`): Rewritten with real emotion detection, Afterwords TTS, pluggable LLM, and prosody analysis (previously all simulated).
- **Afterwords Integration**: The TTS server at `../afterwords/` has been extended with `POST /clone`, `POST /synthesize`, `DELETE /session` endpoints for runtime voice cloning.
- **`src/lunar_tools_art/tools/`**: per-domain hardware/cloud tool modules plus headless fakes — see "Tools Package" above.
- **Design Spec**: `docs/superpowers/specs/2026-03-25-audio-mirror-and-mlx-migration-design.md`
- **Implementation Plans**: `docs/superpowers/plans/2026-03-25-*.md`
- **Test suite**: `LUNAR_HEADLESS=1 pytest -q` → 244 passed, 0 failed, 6 warnings (no xfails).
- **Prototype status**: `PROTOTYPE_STATUS.md` — 28 `works`, 1 `degraded`, 0 `needs-rework` of 29.

## Security History

- ✅ Removed hardcoded API keys from temporary files
- ✅ Implemented comprehensive pre-commit hooks for security scanning
- ✅ Enhanced PII filtering patterns to catch more sensitive data
- ✅ Fixed critical import errors across all prototypes
- ✅ Standardized exception handling with centralized decorators
- ✅ Created secure temporary file creation utilities
- ✅ Added CI/CD pipeline with automated security checks
- **Corrected finding (2026-07):** an earlier QA pass (June 2026, see
  `docs/qa/hermes_qa_2026-06-21.md`) reported that `.env` had been committed to git history. That
  finding was investigated and found incorrect — `.env` has never been tracked in this repository's
  git history. No git history cleanup is required on that basis.
