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
- Manages: Speech2Text, GPT4/Ollama, Text2Speech, AudioRecorder, SoundPlayer, Renderer, WebCam, Image Generators (DALL-E, SDXL, Flux), MIDI/Keyboard input

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

### Key Technologies

- **AI Models**: GPT-4 for text generation, DALL-E 3/SDXL/Flux for image generation
- **Audio**: OpenAI TTS, speech recognition, real-time audio processing with librosa/pydub
- **Visuals**: OpenGL-based renderer, real-time image display
- **Input**: MIDI controllers, keyboard input, microphone, webcam
- **Monitoring**: LangSmith tracing for AI interactions, comprehensive logging

## Configuration

The system uses `settings.toml` for configuration:

- `llm.provider`: Choose between "gpt4" or "ollama"
- `llm.ollama.model`: Specify Ollama model (default: "deepseek-r1:1.5b")
- `renderer.width/height`: Set display dimensions
- `logging.level`: Set log level
- Environment variables override TOML settings

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

## Recent Security Improvements (August 2025)

- ✅ Removed hardcoded API keys from temporary files
- ✅ Implemented comprehensive pre-commit hooks for security scanning
- ✅ Enhanced PII filtering patterns to catch more sensitive data
- ✅ Fixed critical import errors across all prototypes
- ✅ Standardized exception handling with centralized decorators
- ✅ Created secure temporary file creation utilities
- ✅ Added CI/CD pipeline with automated security checks
- ⚠️ Git history cleanup still pending for complete secret removal
