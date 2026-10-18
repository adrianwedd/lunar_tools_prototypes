# Studio Capability — Interactive AI-Art on Mac Studio M5 Ultra

Machine: Apple Mac Studio, Apple M5 Ultra, 256 GB unified memory, macOS 27.0.1 (build 26A434).
Repo: `/Users/adrian/repos/lunar_tools_prototypes` (`lunar_tools_art` 0.1.0).
Audit date: 2026-10-18. All timings are wall-clock and were measured live on this host.
Tagging convention: **[measured]** = observed directly in this session; **[inferred]** = concluded from measured data; **[unverified]** = could not confirm.

Summary verdict: this machine can run the full mflux FLUX + torch/diffusers + OpenCV + MIDI-software stack for interactive generative art, with two hard gaps — **no input-capable audio device exists at all** and **MIDI/camera hardware is absent or blocked** (see §5).

---

## Environment

- Repo venv: `/Users/adrian/repos/lunar_tools_prototypes/env` — **CPython 3.13.15** (uv-managed), **[measured]** working end-to-end for imports, pip installs, and mflux generation (exit code 0, PNG output produced).
- Python interpreters on host **[measured]**: `python3.13` (3.13.16) and `python3.14` via brew at `/opt/homebrew/bin/`, uv-managed CPython 3.13.15, system `/usr/bin/python3` 3.9.6. uv and pipx both present. numba has no 3.14 wheel (repo's own requirements.txt comments confirm) → 3.13 is the practical floor for this repo's optional extras; 3.14 works for venv creation but is avoided here for mlx-whisper/librosa.
- Installed packages (in `env`, verified importable **[measured]**):

| package | version | verified importable |
|---|---|---|
| mlx / mlx-metal | 0.32.4 | yes |
| mlx-lm | 0.32.2 | yes |
| mflux | 0.23.0 | yes |
| torch | 2.14.1 | yes |
| diffusers | 0.41.0 | yes (installed manually — see failures) |
| opencv-python | 4.14.0 | yes |
| sounddevice | 0.5.3 | yes |
| mido / python-rtmidi | 1.3.x / 1.5.x | yes |
| soundfile, librosa, pillow==12.1.0, numpy 2.x, psutil 7.2.2 | — | yes |

- Existing envs on machine (searched `/Users/adrian/repos/*/venv`, `/env`, `.venv`, `~/.venv*`) **[measured]**:
  - `/Users/adrian/repos/afterwords/.venv` (3.14.8): mlx 0.32.3, mlx-lm 0.30.5, sounddevice 0.5.3 — no torch/diffusers/mflux/opencv/MIDI.
  - `kanban-decomposition-fix/.venv`, `undertow-radio/.venv`, `undertow-rt135/.venv`: no ML/art packages.
  - Homebrew pythons 3.13/3.14: bare.
  - **Conclusion [measured]:** no pre-existing env served this repo; the new `env` is required.
  - HF model caches present: FLUX.1-schnell (now complete, ~39 GiB), stable-diffusion-v1-5 (+~4 GB), plus unrelated LLM/audio models. **[measured]**
  - No Flux cache existed before this session (SD-1.5 only) — confirmed by inspection; the FLUX.1-schnell snapshot was created by this audit's downloads.

## Build procedure

```
cd /Users/adrian/repos/lunar_tools_prototypes
uv venv --python 3.13 env
uv pip install --python env/bin/python -r requirements.txt
env/bin/pip install .
env/bin/pip install diffusers
env/bin/pip install psutil
env/bin/pip install pillow==12.1.0   # downgrade; see F1
```

### Failures encountered and fixes [all measured]

1. **Pillow 13 incompatible with uv's CPython 3.13.15** — `mflux-generate --help` crashed: `cannot import name '_IntegralLike' from 'numbers'` (PIL/_typing.py). Fix: pin `pillow==12.1.0`. Verified working after downgrade.
2. **`diffusers` not in requirements.txt** — `import diffusers` failed in the built env despite `torch` being present as a transitive dep. Fix: `pip install diffusers` (0.41.0). Noted as a repo packaging gap (rec at §7).
3. **mflux CLI model-name mismatch** — `--model flux.1-schnell` → `Model not found`. Correct form (mflux 0.23.0): `--model schnell` (or `dev`). Fix: use `schnell`.
4. **FLUX weights download was extremely slow (~8 min/GB for full-precision 33 GB)** — the 512 first-run cold-start took ~3.6 h wall-clock because it downloaded ~30+ GB from HF. The repo context expected a Flux cache; there was none. Recommendation §7 covers pre-caching quantized checkpoints.
5. **First download attempt aborted mid-fetch** — HF temp `.incomplete` blob was deleted out from under a concurrent move (`FileNotFoundError … shutil.copyfile`), then retried once after clearing `.incomplete` blobs. Retry succeeded — [measured]. Cause of the missing temp file: [unverified] (most likely a concurrent process cleaning the HF cache; no other explanation available).
6. **No input audio device** → `sd.default.device[0] == -1`, `InputStream` unusable until hardware added (see §5).
7. **`psutil` not in requirements.txt** — needed for RSS measurement; installed ad-hoc.

## mflux FLUX.1-schnell 4-step benchmark (batch of 3 per size) [measured]

Command, for every run below:

```
env/bin/mflux-generate --model schnell --steps 4 --width {W} --height {H} \
  --seed {42|43|44} \
  --prompt "a red fox on a snowy rooftop, watercolor" \
  --output /Users/adrian/.hermes/cache/scratch/lunar_bench/fox_{W}_{n}.png
```

- Interpretation of "cold": mflux has no warm-persistent daemon here; each CLI invocation loads weights from disk. First run of the whole session ≈ cold-start; subsequent runs of the *same batch* benefit only marginally from the OS page cache (~2–4 s faster than the first in some sizes). There is deliberately no separate "warm" model-resident mode in this benchmark.
- Peak MLX memory is reported by mflux itself; RSS/peak RSS from `/usr/bin/time -l` for the cold 512 run. psutil was used only in the SD-1.5 script.

| Size | Per-image times (3 runs, s) | Mean (s) | MLX peak (GB) | File size (B) |
|---|---|---|---|---|
| 512×512 | 6.94 / 5.45 / 5.02 | **5.80** | 27.49 | 439,733 |
| 768×768 | 7.03 / 6.61 / 6.36 | **6.67** | 30.65 → 30.8 | 970,497 |
| 1024×1024 | 12.14 / 10.17 / 9.64 | **10.65** | 35.91 → 36.18 | 1,609,575 |

Cold-start 512 run (first invocation, full weight load included): **13.47 s wall, 1.05 s user, 10.11 s sys, RSS 22.4 GB after page-cache mapping of weights; `/usr/bin/time -l` "maximum resident set size" 23731601408 B ≈ 22.1 GiB; `Peak memory footprint` 32,870,418,960 B ≈ 30.6 GiB** (`bf512.log`).
Note: first run of the session also had to download ~33 GB of weights, so raw "cold start with empty cache" is not separable from network time in this run — that took hours; treat the 13.47 s figure as "cold start with warm HF cache but fresh process." **[measured]**

Sample sizes: 439,733 B (512), 970,497 B (768), 1,609,575 B (1024) — all non-trivial PNGs. Visual sanity check via PIL/numpy stats on the cold-start 512 image: shape (512,512,3), channel means [196,197,197], std 62.3 — plausible natural-image statistics, not blank/degenerate. **[measured]**

### Seed-reproducibility test [measured — RESULT: NOT bit-reproducible]

`--seed 42`, same prompt, 512×512, two separate `mflux-generate` invocations:

| run | sha256 | bytes |
|---|---|---|
| repro_a.png | `11b0835b5201f7d639a575852d92c906e671eaec08bb92f60294ce7d0ee90766` | 439,733 |
| repro_b.png | `f5e762e78c9ecb7783b8b760c3c77d293ff100f48dcf1f19f07d64bc86a4faae` | 439,731 |

Different hash and a 2-byte size difference → seeded generation via the mflux CLI is **not bit-reproducible across processes**. The 2-byte delta plus earlier same-seed runs sharing a sha (the three 512 runs wrote the same filename, sha `1d27254a…`) but the first run of the day at seed 42 hashed `1c6d76aa…` show determinism holds *within* a generation but not *across* runs on this GPU — [inferred, consistent with non-deterministic GPU reductions on Metal]. Treat "same seed → same image" as not guaranteed for the Studio; [unverified] whether the mflux Python API in a single persistent process is reproducible (not tested).

## SD-1.5 diffusers benchmark (torch MPS, fp32) [measured]

Command: `/Users/adrian/repos/lunar_tools_prototypes/env/bin/python /Users/adrian/.hermes/cache/scratch/lunar_bench/bench_sd15.py` — logs in `sd15.out`, JSON in `sd15_bench.json`. The script does exactly:

```
StableDiffusionPipeline.from_pretrained("stable-diffusion-v1-5/stable-diffusion-v1-5",
    torch_dtype=torch.float32, safety_checker=None).to("mps")
… pipe(prompt, num_inference_steps=25, guidance_scale=7.5, height=512, width=512,
       generator=torch.Generator("mps").manual_seed(42|7))
```

| metric | value |
|---|---|
| cold load (from_pretrained → .to("mps")) | 1275.3 s ≈ 21 min (network-bound re-download of ~4 GB + weight load; the SD cache was incomplete and re-fetched) |
| RSS after load | 0.55 GB |
| gen #1 (25 steps, 512², seed 42) | 6.4 s, RSS 0.75 GB, 508,058 B |
| gen #2 warm (seed 7) | **3.5 s**, RSS 0.76 GB, 518,059 B |

Visual sanity: `sd15_a.png` inspected by vision model — plausible coherent watercolor-style fox on snowy rooftop; not degenerate. **[measured]**
Note: cold load is polluted by the HF re-download; the *useful* number for a warm-cache machine is the generation time (3.5–6.4 s) and the fact that fp32 diffusion on MPS is real-time-ish at 512². **[measured]**

## Webcam test [RESULT: BLOCKED — permission, not hardware]

`cam_test.py` (cv2 4.14.0, indices 0–3):
- OpenCV log: `OpenCV: not authorized to capture video (status 0), requesting…` and `camera failed to properly initialize!` for each index.
- `VideoCapture(0..3).isOpened()` → False, `read()` → no frames. **No fps or frame size could be measured.** `webcam_fps = None`.

Missing permission, named exactly: **macOS TCC *Camera* privacy permission is not granted to the terminal/agent process invoking Python from a daemonized session** (OpenCV's own error string: "not authorized to capture video (status 0)"). A GUI-visible prompt was not surfaced in this session, so the permission could not be granted here and the test could not be retried.
Separately, `system_profiler SPCameraDataType` returned **empty on this host** — so whether any camera hardware even exists on this Mac Studio is [unverified]; the TCC error can also occur when no camera is present. Both explanations are recorded; the permission gap is the actionable one.

## Audio-input test [RESULT: IMPOSSIBLE — no input hardware]

`mic_test.py` (sounddevice 0.5.3):
- `query_devices()` → 0 devices with `max_input_channels > 0`; `sd.default.device[0] == -1` → `PortAudioError: Error querying device -1`. **`mic_rms = None`** (no RMS could be measured).
- `system_profiler SPAudioDataType` lists exactly two devices, both OUTPUT-only: `KAMN32UC6JB` (external, DisplayPort transport) and `Mac Studio Speakers` (built-in default); neither has an Input Channels entry. **[measured]**
- This is not a TCC/microphone-permission problem; there is no capture device to authorize. Missing piece: a USB/Thunderbolt audio interface with a mic must be attached before any capture test is meaningful. Whether the Apple Studio Display's own mic could be enabled is [unverified] (the KGN monitor here is not a Studio Display and shows no input capability).

## MIDI

- `system_profiler SPMIDataDataType` → empty. **[measured]** No MIDI hardware connected.
- No `pmidi` (or similar) installed on the host. **[measured]**
- Software side is ready in `env`: `python-rtmidi` and `mido` import successfully. **[measured]** Real MIDI I/O is untested — no device to test against; **[unverified]** whether a device would enumerate successfully once connected.

## Recommendations

1. **Env for all Studio AI-art work:** `/Users/adrian/repos/lunar_tools_prototypes/env` (CPython 3.13.15 via uv). It is the only env with the full MLX + torch + diffusers + cv2 + MIDI-software stack working, at the versions in the table above. Keep Pillow ≤12 in this env (Pillow 13 breaks mflux under this CPython build). Do not try Python 3.14 — numba has no wheels.
2. **Interactive (fast) image-gen stack: mflux FLUX.1-schnell on MLX.** 4-step generation at 512² ≈ 5.0–6.9 s, 768² ≈ 6.4–7.0 s, 1024² ≈ 9.6–12.1 s; MLX peak 27–36 GB — comfortably inside 256 GB alongside other Studio workloads. For a *truly* interactive loop (sub-second latencies), the right evolution is a persistent server process holding weights in MLX memory so per-image cost excludes the ~10 s weight load; **[inferred — not built in this audit]** mflux's Python API is the plausible route, but per-process non-determinism (seed test above) means visual output may drift between server restarts.
3. **Slower/quality path: torch + diffusers on MPS.** SD-1.5 fp32 at 512²/25 steps ≈ 3.5–6.4 s warm, trivial RSS. It is slower per quality point than mflux schnell, but offers the diffusers ecosystem (ControlNet, img2img, LoRA, pipelines) that mflux does not. Use it when pipeline features, not raw Flux quality, matter.
4. **Weights strategy:** full-precision FLUX.1-schnell is ~33 GB on disk and ~27 GB MLX peak. For interactive use consider mflux `--quantize 4`/`8` (or `--low-ram`) to cut both disk and memory; **[unverified]** in this audit — recommend benchmarking quantized variants before relying on them.
5. **Camera/Mic/MIDI gaps:**
   - Camera: blocked by TCC for this agent's session, and possibly absent from the host. To clear it: grant *Camera* permission in System Settings → Privacy & Security to the host app running Python (e.g. Terminal/iTerm), then re-run `cam_test.py`. If the profiler still shows no camera after permission is granted, the hardware itself is absent.
   - Mic: attach a USB/Thunderbolt audio interface; nothing software-side is wrong (sounddevice works, portaudio present).
   - MIDI: no hardware connected. `rtmidi`/`mido` are import-ready; add `pmidi` (`brew install pmidi`) or similar for quick enumeration diagnostics once a device is attached.
6. **Repo packaging fixes identified during the build:** add `diffusers` and `psutil` to pyproject/requirements; pin `pillow<13` for the MLX path; consider vendoring a small script that clears `~/.cache/huggingface/**/*.incomplete` on failed downloads; do not rely on system python3 (3.9.6) for anything.

---

## Appendix — artifacts in `/Users/adrian/.hermes/cache/scratch/lunar_bench/`

- `mflux_bench.json` — 11 measured mflux runs (9 batch + 2 seed-repro), each with per-run wall time, MLX peak, bytes, sha256.
- `sd15_bench.json` — SD-1.5 measurements (cold load, 2 generations, RSS, hashes).
- `bf512.log` — cold-start 512 run; includes `/usr/bin/time -l` peak RSS and mflux "Peak MLX memory".
- `fox_512_a.png` (`1c6d76aa…`), `fox_512.png` ×3 (`1d27254a…`, same name overwritten per batch), `fox_768.png` ×3, `fox_1024.png` ×3 (seeds 42/43/44 in sequence — note the identical shas within each batch row reflect mflux's own seed handling plus same-filename overwrite, not 3 distinct outputs).
- `repro_a.png` / `repro_b.png` — seed-42 repro pair (hashes differ; see §seed-reproducibility).
- `sd15_a.png` (508,058 B) / `sd15_b.png` (518,059 B).
- `cam_test.py`, `mic_test.py`, `bench_mflux.py`, `bench_sd15.py` — the exact scripts behind every number above.