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

1. Create new file in `prototypes/` following naming convention
2. Create class with CamelCase name matching filename
3. Accept `LunarToolsArtManager` in constructor
4. Implement `run()` method with main loop and keyboard exit handling
5. Add smoke test in `tests/test_lunar_tools_art.py`

**Testing Prototypes:**

- All prototypes have smoke tests that mock keyboard input to ensure basic instantiation
- Tests verify Manager initialization and tool availability
- Use mocking for external API calls and hardware dependencies
