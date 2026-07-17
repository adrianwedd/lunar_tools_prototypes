# Running the Installations

Everything starts from three commands:

```bash
python lunar_tools_demo.py list             # what exists, what each needs
python lunar_tools_demo.py doctor [demo]    # is this machine ready?
python lunar_tools_demo.py run <demo>       # preflight, then launch
```

Running with no arguments shows the `list`. The legacy form
`python lunar_tools_demo.py --demo <name>` still works and is equivalent to
`run <name>`.

## Zero-hardware first run

No mic, camera, GPU, server, or API key required — the headless layer swaps
every hardware/cloud tool for a deterministic fake:

```bash
LUNAR_HEADLESS=1 python lunar_tools_demo.py run whispers --force
```

The demo runs its real logic against fake devices; press `Ctrl-C` to stop
(on real hardware, `q`/`ESC` in the render window). `--force` skips
preflight, which is what you want headless — the doctor intentionally probes
real hardware only.

## Reading the `list` output

- `●` works / `◐` degraded — **headless smoke status**: the prototype
  constructs and runs against the fake tool layer. It is *not* a promise the
  demo has been verified on real hardware.
- The `needs` column shows capabilities; a trailing `?` marks optional ones —
  the demo degrades gracefully without them (doctor reports them as
  warnings, not failures).

## What the doctor checks

| check | what it does | typical fix it prints |
|---|---|---|
| `python` | version ≥ 3.10 | install Python 3.10+ |
| `settings` | which `settings.toml` was actually loaded (cwd-relative) | run from the repository root |
| `headless` | warns if `LUNAR_HEADLESS=1` is set interactively | unset it to use real devices |
| `mic` / `audio-out` | input/output device present (subprocess probe, 5s timeout) | `pip install -e '.[hw]'`, plug in / grant permission |
| `camera` | camera 0 opens and is released (8s timeout) | `.[vision]` extra + macOS camera permission |
| `renderer` | an invisible pyglet window can be created | `.[hw]` extra; on Linux, a display/X server |
| `midi` | at least one MIDI input enumerates | connect a controller |
| `llm` | provider-aware: Ollama endpoint reachable, or `mlx-lm` importable, or the provider's API key set | `ollama serve` / `pip install -e '.[mlx]'` / set the key |
| `afterwords` | TTS server answers at `afterwords.server_url` | `cd ../afterwords && python server.py` |
| `image-gen` | configured backend (default `mflux`) is importable | `pip install -e '.[mlx]'` |
| `assets` | demo's expected files (e.g. mp3s) exist | supply the file or point `--config` at yours |
| `peer` | always a warning — ZMQ demos need a second process it cannot see | see below |

Hardware probes run in short-lived subprocesses with hard timeouts, so a
hung driver or native crash can't take the doctor down; a timeout is
reported as "device busy or driver hang".

Exit codes: `doctor` — 0 pass, 1 a required check failed. `run` — 0 clean,
1 the demo crashed (or ended with a recorded fatal error), 2 bad usage/
`--config`, 3 preflight failed, 4 unknown demo.

## Passing configuration

```bash
python lunar_tools_demo.py run whispers --config duration=5 --config voice=galadriel
python lunar_tools_demo.py run whispers --config "window_size=(800,600),fps=30"
```

`--config` is repeatable; the single-string comma form also works, and
tuple values with commas parse correctly. Malformed entries (no `=`) are
rejected with an error rather than silently dropped.

## Setting up the pieces

- **Microphone & camera (macOS):** the first probe/run triggers the system
  permission dialog — grant access under System Settings → Privacy &
  Security. The doctor distinguishes "no device" from "permission denied".
- **Afterwords TTS:** clone the [afterwords](../../afterwords) repo next to
  this one, start `python server.py` (default `http://localhost:7860`,
  configurable via `afterwords.server_url` in `settings.toml`). Needed for
  voice-cloning demos (`audio-mirror`); optional for demos marked
  `afterwords?`.
- **Ollama (default LLM):** `brew install ollama && ollama serve`, then
  `ollama pull llama3.1:8b`. Alternatives (`mlx`, `claude`, `ollama-cloud`,
  `openrouter`) are selected in `settings.toml [llm]`; cloud providers also
  need `privacy.mode = "cloud-ok"` and the provider's API key in `.env`.
- **Image generation:** defaults to `mflux` (MLX-native Flux) —
  `pip install -e '.[mlx]'` on Apple Silicon.
- **MIDI:** any class-compliant controller; `doctor` shows how many inputs
  it sees.

## Multi-process demos

`collaborative-canvas` and `collaborative-art` are a ZMQ pair: start
`collaborative-art` (the server half) on one machine/terminal first, then
`collaborative-canvas` pointed at it. The doctor can only warn about this —
it cannot verify the peer exists.

## Troubleshooting

Every failed doctor line prints its own fix command — start there. Beyond
that:

- **`run` fails preflight but you disagree** — `--force` launches anyway.
- **A demo dies instantly with no useful message** — rerun with `--debug`
  for the full traceback.
- **Everything "passes" but the demo does nothing** — check you aren't
  running with `LUNAR_HEADLESS=1` (the doctor warns about this).
- **`settings` check warns** — you're not in the repo root, so the demo is
  running on built-in defaults instead of `settings.toml`.
- **Missing mp3 assets** (`escape-room`, `apocalypse-experience`,
  `neural-transfer-music-visualizer`, `augmented-audio-tours`) — these files
  are not shipped in the repo; provide your own or reconfigure the paths.
