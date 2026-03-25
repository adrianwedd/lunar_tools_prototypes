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
# Run a specific demo using the CLI entrypoint
python lunar_tools_demo.py --demo <demo_name>

# Examples:
python lunar_tools_demo.py --demo interactive-storytelling
python lunar_tools_demo.py --demo fractal-forest --config "{'mic_device': 'default', 'window_size': (800, 600)}"

# List available demos by running without args
python lunar_tools_demo.py --help
```

### Testing

```bash
# Run all tests (includes smoke tests for all prototypes)
pytest

# Run specific test file
pytest tests/test_lunar_tools_art.py

# Run with verbose output
pytest -v
```

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
- **Emotion Detection (`src/lunar_tools_art/emotion.py`)**: Face detection via OpenCV Haar cascade with placeholder emotion classifier. `has_classifier` property indicates when real model is available. Fallback chain planned: MLX model -> OpenCV DNN ONNX -> Haar cascade.
- **Prosody Analysis (`src/lunar_tools_art/prosody.py`)**: Voice prosody extraction via librosa — pitch, energy, pace, pauses, spectral features. Pure signal processing, no ML. Infers coarse emotion tag from prosody heuristics.
- **Voice Client (`src/lunar_tools_art/voice_client.py`)**: HTTP client for the Afterwords TTS server. Supports synthesis, voice cloning, session palette management, and cleanup.
- **Audio Mirror FSM (`src/lunar_tools_art/audio_mirror_fsm.py`)**: Pure-logic state machine for the Audio Mirror installation: IDLE -> DETECTION -> FIRST_CAPTURE -> DEEPENING -> ORACLE -> DEPARTURE.

### Key Technologies

- **AI Models**: Pluggable LLM (Claude/Ollama/Ollama Cloud/OpenRouter), DALL-E 3/SDXL/Flux for image generation
- **Audio**: Afterwords TTS server (Qwen3-TTS on MLX, voice cloning), speech recognition, real-time prosody analysis with librosa
- **Visuals**: OpenGL-based renderer, real-time image display, camera mirror with overlays
- **Input**: MIDI controllers, keyboard input, microphone, webcam
- **Monitoring**: LangSmith tracing for AI interactions, comprehensive logging

## Configuration

The system uses `settings.toml` for configuration:

- `llm.provider`: Choose between "ollama", "claude", "ollama-cloud", or "openrouter"
- `llm.ollama.model`: Specify Ollama model (default: "llama3.1:8b")
- `llm.claude.model`: Specify Claude model (default: "claude-sonnet-4-20250514")
- `afterwords.server_url`: Afterwords TTS server URL (default: "http://localhost:7860")
- `afterwords.default_voice`: Default voice for TTS (default: "galadriel")
- `emotion.confidence_threshold`: Minimum confidence for emotion detection
- `privacy.mode`: "local-only" (forces Ollama) or "cloud-llm" (allows any provider)
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
3. Run tests: `pytest -v`
4. Check for secrets: `detect-secrets scan --baseline .secrets.baseline`  # pragma: allowlist secret

## Audio Mirror & MLX Migration (March 2026)

New art installation prototypes and shared infrastructure for running on Apple Silicon:

- **Audio Mirror** (`prototypes/audio_mirror.py`): Installation that captures a viewer's voice, progressively clones it via Afterwords TTS, and speaks back personal insights in the viewer's own voice. Uses FSM-driven interaction with 6 phases.
- **Mirror of Truth Rewrite** (`prototypes/ai-mirror-of-truth.py`): Rewritten with real emotion detection, Afterwords TTS, pluggable LLM, and prosody analysis (previously all simulated).
- **Afterwords Integration**: The TTS server at `../afterwords/` has been extended with `POST /clone`, `POST /synthesize`, `DELETE /session` endpoints for runtime voice cloning.
- **Design Spec**: `docs/superpowers/specs/2026-03-25-audio-mirror-and-mlx-migration-design.md`
- **Implementation Plans**: `docs/superpowers/plans/2026-03-25-*.md`
- **59 new tests** across 7 test files covering all infrastructure and prototypes.

## Recent Security Improvements (August 2025)

- ✅ Removed hardcoded API keys from temporary files
- ✅ Implemented comprehensive pre-commit hooks for security scanning
- ✅ Enhanced PII filtering patterns to catch more sensitive data
- ✅ Fixed critical import errors across all prototypes
- ✅ Standardized exception handling with centralized decorators
- ✅ Created secure temporary file creation utilities
- ✅ Added CI/CD pipeline with automated security checks
- ⚠️ Git history cleanup still pending for complete secret removal
