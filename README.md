# Lunar Tools Prototypes

A collection of interactive audiovisual art installations built with the Lunar Tools framework, rebuilt to run natively on Apple Silicon (MLX) with a privacy-first, local-only default. The same codebase runs headless (Linux/CI) via deterministic in-repo fakes — no hardware or cloud calls required for tests.

Project site: <https://adrianwedd.github.io/lunar_tools_prototypes/>

## Features

- **Pluggable LLM backends** — Claude API, Ollama (local), Ollama Cloud, OpenRouter; selected via `settings.toml [llm]`.
- **Local-first privacy gate** — `privacy.mode = "local-only"` (the default) blocks construction of any cloud-backed LLM/TTS/image backend; set `"cloud-ok"` to allow cloud providers.
- **Voice** — speech-to-text, Afterwords TTS server (Qwen3-TTS on MLX) with runtime voice cloning, and real-time prosody analysis (librosa).
- **Vision** — webcam capture, face detection, and FER+ ONNX emotion classification with graceful fallbacks.
- **Image generation** — unified `ImageGenerator` defaulting to `mflux` (MLX-native Flux) on real hardware; legacy DALL·E/SDXL names remain as deprecated aliases.
- **Visuals & input** — OpenGL renderer, real-time image display, MIDI controllers, keyboard, microphone.
- **Headless test layer** — `LUNAR_HEADLESS=1` swaps every hardware/cloud tool for a deterministic fake (`src/lunar_tools_art/tools/headless.py`).

## Quickstart

```bash
git clone https://github.com/adrianwedd/lunar_tools_prototypes.git
cd lunar_tools_prototypes
python3 -m venv env && source env/bin/activate

# macOS (Apple Silicon): MLX models + hardware I/O + dev tools
pip install -e ".[mlx,hw,dev]"

# Linux / headless / CI: dev extras only (MLX/hardware imports are lazy)
pip install -e ".[dev]"
```

Optional API keys (only needed with `privacy.mode = "cloud-ok"`): copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY`, `OLLAMA_CLOUD_API_KEY`, `OPENROUTER_API_KEY`, etc. Never commit `.env`.

Run a demo — three commands cover everything (see [docs/RUNNING.md](docs/RUNNING.md) for the full runbook):

```bash
python lunar_tools_demo.py list                        # every demo, its requirements, status
python lunar_tools_demo.py doctor interactive-storytelling   # is this machine ready?
python lunar_tools_demo.py run interactive-storytelling
```

No hardware, no API keys? Try the headless layer — the demo runs its real logic against deterministic fakes:

```bash
LUNAR_HEADLESS=1 python lunar_tools_demo.py run whispers --force
```

The legacy `--demo <name>` form still works as an alias for `run <name>`.

## Prototype Highlights

All 29 installations live in `prototypes/`; see `PROTOTYPE_STATUS.md` for the full per-prototype status matrix (currently 28 `works`, 1 `degraded`, 0 `needs-rework` against the headless tools layer).

| Prototype | Description |
|---|---|
| `audio_mirror.py` | Flagship installation: captures a viewer's voice, progressively clones it via Afterwords TTS, and speaks back personal insights in the viewer's own voice (6-phase FSM). |
| `ai-mirror-of-truth.py` | Camera mirror with real emotion detection, prosody analysis, pluggable LLM, and Afterwords TTS. |
| `interactive_storytelling.py` | Core interactive storytelling experience: speech in, AI narrative and visuals out. |
| `acoustic-fingerprint-painter.py` | Paints abstract brushstrokes driven by each visitor's voice fingerprint. |
| `audio-reactive-fractal-forest.py` | An evolving fractal forest whose shape and colors respond to ambient audio. |
| `cosmic-soundscape.py` | Maps a spoken phrase to celestial motifs and a mood palette, then generates and renders a cosmic visual. |
| `data-driven-cityscape.py` | Generative skyline that morphs with live weather data (deterministic synthetic data when headless/offline). |
| `virtual-cloud-chamber.py` | 2D particle-track cloud chamber with AI narration. |
| `real-time-glitch-art-lab.py` | Streams live camera frames through a glitch "corruption" pipeline. |

## Repository Structure

```
.
├── prototypes/            # All art installation prototypes (29)
├── src/lunar_tools_art/   # Shared package: manager, config, base classes,
│   ├── tools/             #   per-domain hardware/cloud tools + headless fakes
│   ├── llm_backends.py    #   pluggable LLM abstraction
│   ├── emotion.py         #   face detection + FER+ emotion classifier
│   ├── prosody.py         #   voice prosody analysis
│   └── voice_client.py    #   Afterwords TTS client
├── tests/                 # Test suite (headless, deterministic)
├── scripts/               # Model fetching, hardware smoke tests
├── docs/                  # Design specs, plans, QA reports
├── lunar_tools_demo.py    # CLI entrypoint for launching demos
├── settings.toml          # Configuration (env vars override)
├── PROTOTYPE_STATUS.md    # Per-prototype smoke status matrix
└── MIGRATION_GUIDE.md     # Legacy-to-current migration notes
```

## Testing

```bash
LUNAR_HEADLESS=1 pytest -q
```

`LUNAR_HEADLESS=1` is required — it routes every tool through the in-repo fakes so no mic, webcam, MLX model, or cloud API is touched. Current baseline: **244 passed, 0 failed** (6 warnings, no xfails).

## Configuration

`settings.toml` drives everything; environment variables override (nested keys via double underscores, e.g. `LLM__PROVIDER=ollama`). Key settings: `llm.provider`, `privacy.mode`, `afterwords.server_url`, `renderer.width/height`. See `CLAUDE.md` for the full reference.

## Contributing

See `CONTRIBUTING.md`. Install pre-commit hooks (`pre-commit install`) — they run secret scanning (detect-secrets, bandit) and formatting (black, isort, ruff).

## License

See `LICENSE`.
