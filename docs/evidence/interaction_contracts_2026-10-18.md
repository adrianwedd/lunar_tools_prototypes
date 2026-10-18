# Interaction/contract repair — evidence (2026-10-18)

Scope: Seed Surfer interaction loop (Priority A), MIDI integer-CC contract
(#32 / Priority B), image path-vs-pixels sweep (#35 / Priority C).

Test command used throughout (headless, no GUI display in this session):

```
LUNAR_HEADLESS=1 env -u PYTHONPATH env/bin/python -m pytest -q
```

Baseline before work: **276 passed**. Final: **326 passed** (49 new tests,
plus one new poetry-mosaic guard test). No hardware, no network, no model
downloads in the suite.

## Priority A — Seed Surfer

Changed: `prototypes/seed_surfer.py`, `src/lunar_tools_art/seed_scheduler.py`.
Tests: `tests/test_seed_surfer_interaction.py` (21 tests, fake generator
writes real PNGs).

| Claim | Evidence |
|---|---|
| Identical requests deduplicate | 60 same-seed requests across an in-flight 150 ms generation → generator called exactly once; no call after completion |
| Cached frames are not re-decoded | six navigations across two seeds → `decodes == 2`, `cache_hits == 4`; 100 cached ticks < 1 s |
| Frame cache is bounded | 5 seeds with `frame_cache_size=3` → 3 entries, 2 evictions |
| Edge-triggered controls | holding `s` for 15 frames → 1 favourite; holding `a` → 1 toggle; holding space → 1 jump; CC21 held high → 1 save, one more only after release+press on a new seed |
| Deliberate key repeat | press steps, then no step at +0.10 s / +0.29 s, step at +0.31 s, then 0.08 s intervals; 40 frames at 200 Hz do not accelerate |
| Current image preserved while generating | last frame stays seed 5, overlay reports selected seed 6 + generating/queued state; top-of-frame pixels unchanged |
| Stale results | navigating away from an in-flight seed → `discarded_stale == 1`, stale PNG cached but never displayed |
| Prefetch priority | `request_prefetch` returns `None` while a user target is outstanding; both neighbours warm exactly once |
| Error recovery | failing generator: 1 attempt, then 20 ticks inside a 1 s window add no retry; preserved frame stays; recovers after backoff |
| Cache poisoning | generator returning a missing/empty PNG is an error, not an index entry |

Real 512×512 artwork already in `outputs/seed_surfer/images` (mflux schnell,
identity `37758e17e8b2`), loaded through the new cache path:

```
cold decode:        10.2 ms
warm cache hit:      5 µs median, 6 µs p95  (200 iterations)
generator calls:     0
```

A 3 s real-`Manager` loop run (headless fake backend, 64×64) completed seed 42
plus both neighbours in 3 generations, 20 cache hits, 1 decode.

## Priority B — MIDI (#32)

Changed: `dynamic_visuals.py` (CC70/71/72 brightness/contrast/hue),
`virtual_time_travel.py` (CC70 era), `evolving-cosmic-mural-prototype.py`
(CC70–77 modifiers). No compatibility shim; `device_name` assignment removed
(MidiInput binds the first port). Tests: `tests/test_midi_prototypes.py`
(13 tests).

- Scripted fake implements only `get(control:int, default=0.0)`, so any
  legacy named/`val_min` call raises — all three full iterations render with
  no TypeError.
- CC scaling asserted explicitly (e.g. dynamic visuals 0..1 → 0.5..1.5
  multipliers; 0 maps to 0.5, 1 to 1.5).
- Visual state changes asserted numerically (frame inequality) and by prompt
  content (era phrase, mural modifier).
- Real `MidiInput()` with mido present but zero ports: returns defaults,
  warns once, iteration still completes.
- **Not verified:** physical MIDI hardware (none connected).

## Priority C — Image contract (#35)

Changed: 13 prototypes bound generator output through
`load_generated_image()` before resize/paste/blend/send/render. Poetry mosaic
also skips a `None` LLM response instead of raising. Tests:
`tests/test_image_contracts.py` (16 tests) — fake generator writes real PNGs.

Independent end-to-end check with a real headless `Manager` (real
`DeprecatedAlias`→`ImageGenerator`, stub LLM):

```
GenerativePoetryMosaic._step("moonlight") -> True
tile: (300, 200) RGB
canvas: (1080, 1920, 3) uint8, 807 non-black pixels, max 254
```

Audited as already correct (procedural drawing or LLM-only, no generated
image path): `ai-mirror-of-truth.py`, `audio-reactive-fractal-forest.py`,
`interactive-storytelling-canvas-prototype.py`. Not swept: the remaining
prototypes outside the 13 listed in #35.

## Explicitly unverified (needs Adrian present)

- pyglet/OpenCV GUI behaviour and window focus for keyboard controls.
- Physical MIDI controller input.
- Microphone capture and live voice-driven prototypes.
- Interactive mflux generation pacing on the real 512 px backend (standalone
  mflux timings remain in `docs/evidence/seed_surfer_verification.json`).

## Integration check

`run seed-surfer` previously crashed before the loop: the launcher only
injected the manager when the constructor parameter was named
`lunar_tools_art_manager`, while SeedSurfer (and RealTimeGlitchArtLab) use
`manager`. Fixed in the launcher with regression tests. Verified:

```
LUNAR_HEADLESS=1 ./env/bin/python lunar_tools_demo.py run seed-surfer --force
→ "Seed Surfer | +/- seed, ... q quit" and the loop stayed alive until SIGTERM
```

The glitch lab entry point has the same signature and now constructs too (its
camera path remains unverified, issue #29).

## Stretch — STT (#33)

The issue's original blocker is stale: `mlx-whisper 0.4.3`, `faster-whisper
1.2.1` and `av 19.0.1` are all importable in `env/`. No code change was needed
to the STT layer.

Verified with `mlx-whisper` + `base.en` (configured default) on a committed,
non-sensitive fixture (`tests/fixtures/speech_quick_brown_fox.wav`, 2.67 s,
16 kHz mono, rendered locally with `say`):

```
text       : "the quick brown fox jumps over the lazy dog."
language   : en
confidence : 0.722
cold       : 67.08 s  (includes 143 MB one-time model download)
first call :  0.95 s  (weights load, warm cache)
warm       :  0.055 s median over 5 calls
```

A second, different sentence transcribed correctly ("Lunar tools make the
instruments playable again.", confidence 0.676) to rule out a cached result.

New: `scripts/transcribe_file.py` (documented in `docs/RUNNING.md`),
`tests/test_stt_real.py` (opt-in, `LUNAR_REAL_STT=1`).

`faster-whisper` remains unusable in this env: faster-whisper 1.2.1 calls
`av.open(..., metadata_errors="ignore")`, which PyAV 19 removed. Left as a
documented incompatibility rather than downgrading PyAV; the default backend
works.

**Not verified:** microphone capture and live voice-driven loops.
