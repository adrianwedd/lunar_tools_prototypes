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

## The two live installations

Both are registered demos, so `list`/`doctor`/`run` describe and preflight them.

### Seed Surfer — real local seed surfing

```bash
env -u PYTHONPATH ./env/bin/python lunar_tools_demo.py doctor seed-surfer
env -u PYTHONPATH ./env/bin/python lunar_tools_demo.py run seed-surfer
```

Controls: `+`/`up` next seed, `-`/`down` previous, `left`/`right` ±10,
`space` random jump, `s` favourite, `a` prefetch toggle, `q` quit.
MIDI CC20 is the surf dial; CC21 saves a favourite.

When a complete local FLUX snapshot exists, the adapter uses it directly
(`model_repo: local:…`) instead of resolving the repo through the Hub, so a
cached model is never silently re-downloaded.

Measured on the M5 Ultra (FLUX.1-schnell, 4-bit, 4 steps, 512²): 1.64 s warm
per new seed; a cached seed is served in ~10 µs. Favourites are written to
`outputs/seed_surfer/favourites.json` with the model identity, weights
revision, cache key and generation metadata.

Verification (real inference, no window needed):

```bash
env -u PYTHONPATH ./env/bin/python scripts/verify_seed_surfer.py --seeds 4
```

### Glitch Lab — live camera or recorded source

```bash
env -u PYTHONPATH ./env/bin/python lunar_tools_demo.py doctor real-time-glitch-art-lab
env -u PYTHONPATH ./env/bin/python lunar_tools_demo.py run real-time-glitch-art-lab
```

Controls: `1`–`4` glitch family, `up`/`down` intensity, `space` re-roll, `q` quit.

macOS camera permission is a hard boundary: the first run triggers a TCC
prompt that only the logged-in user can accept. Until it is granted the lab
renders its explicit standby state and `doctor` reports `camera` failing.
When camera access is unavailable, exercise the rest of the pipeline against
a recorded clip — this is a demonstration, **not** hardware verification:

```bash
env -u PYTHONPATH ./env/bin/python prototypes/real_time_glitch_lab.py \
  --video outputs/glitch_lab/synthetic_reference_720p.mp4 --seconds 30
env -u PYTHONPATH ./env/bin/python scripts/verify_glitch_lab.py
```

The windowed path (`pyglet`) needs a GUI login session; an SSH/agent shell
has no WindowServer screens and `doctor`'s `renderer` probe will fail with
`IndexError: list index out of range`.

## Speech to text (local, file input, no microphone)

Default backend is `mlx-whisper` with `base.en` (`settings.toml [whisper]`).
The MLX weights live in the Hugging Face cache
(`mlx-community/whisper-base.en-mlx`, 143 MB — downloaded once). Transcribe a
file straight from the terminal:

```bash
env -u PYTHONPATH ./env/bin/python scripts/transcribe_file.py \
  tests/fixtures/speech_quick_brown_fox.wav
# backend : mlx-whisper / base.en
# language: en  confidence: 0.722
# latency : 0.95s
# text    : the quick brown fox jumps over the lazy dog.
```

`--json` emits machine-readable output; `--backend`/`--model` override the
configured pair. Measured on the M5 Ultra with the committed pangram fixture
(2.67 s, 16 kHz mono): first call in a process ~0.95 s (weights load), warm
calls ~55 ms. The cold figure including the one-time download is ~67 s.

Opt-in real test (skipped by default so CI needs no model):

```bash
LUNAR_REAL_STT=1 env -u PYTHONPATH ./env/bin/python -m pytest -q tests/test_stt_real.py
```

Note: `faster-whisper` 1.2.1 is currently incompatible with the installed
PyAV 19 (`av.open() got an unexpected keyword argument 'metadata_errors'`),
so use the default `mlx-whisper` backend. Microphone capture is still a
hardware/permission problem, separate from file transcription.

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
| `renderer` | an invisible pyglet window can be created | `.[hw]` extra; launch from a GUI login session (an SSH/agent shell has no WindowServer screens) |
| `midi` | at least one MIDI input enumerates | connect a controller |
| `llm` | provider-aware: Ollama endpoint reachable, or `mlx-lm` importable, or the provider's API key set | `ollama serve` / `pip install -e '.[mlx]'` / set the key |
| `afterwords` | TTS server answers at `afterwords.server_url` | `cd ../afterwords && python server.py` |
| `image-gen` | the mflux adapter imports against the installed mflux **and** the cached model snapshot contains every weight shard | `pip install -e '.[mlx]'` / `hf download <repo>` |
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
python lunar_tools_demo.py run whispers --config duration=30 --config voice=galadriel
# no camera? feed a recorded clip through the identical motion pipeline:
python lunar_tools_demo.py run whispers --config duration=30 \
    --config video_path=outputs/glitch_lab/synthetic_reference_720p.mp4 \
    --config record_path=outputs/whispers/my_demo.mp4
```

Whispers knobs: `duration` (s), `camera_id`, `video_path`, `voice`,
`particle_cap` (default 2000), `trail_alpha`, `whisper_gap_s`,
`record_path` (mp4), `synthetic_motion` (force the procedural source).
Recorded clips play at wall-time pace regardless of render fps (a
recorded visitor unfolds in real time). On machines where pyglet finds
no screen (SSH/agent sessions) set `RENDERER__BACKEND=opencv` for the
HighGUI window.

Visual presets (keys 1–4): **Ember Library** (warm coals, stately),
**Tidal Memory** (cyan ramp, halo-sheets), **Ghost Bloom** (inverted
silhouettes that sink), **Signal Chapel** (stained-glass hues, fast
swirl). Motion states blend over ~1.5 s: stillness drifts calm and dim
(the aura never empties — an ambient breath keeps it alive), gentle
movement blooms slowly, sudden gestures burst bright (rate-limited to
one per 0.35 s). MIDI (optional): CC74 size, CC71 swirl, CC73 emission,
CC91 trails, as 0.5×–1.5× adjustments.

Sound: a procedural whisper texture (breathy formant-filtered noise)
plays continuously — intensity follows motion energy, formants follow
the gesture state, stereo pan follows the motion's horizontal centroid.
`s` mutes. Afterwords TTS whispers remain available (`voice` knob) and
never block the loop; the piece runs identically with audio absent.

Controls at the window: `c` clear aura, `m` motion overlay, `space`
whisper now, `s` sound, `1-4` preset, `h` HUD, `q` quit.

Demo (stillness → gentle → intense, real pipeline, ~23 s):
`RENDERER__BACKEND=opencv env/bin/python scripts/make_whispers_demo_v2.py`
→ `outputs/whispers/whispers_demo_v2.mp4` + preview PNG + evidence JSON.

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
- **`numpy._core._multiarray_umath` or mlx import errors** — your shell is
  exporting a `PYTHONPATH` from another interpreter (common when started from
  an agent harness). Launch with `env -u PYTHONPATH ./env/bin/python ...`.
