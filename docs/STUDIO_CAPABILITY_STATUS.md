# Studio Capability Report — status

**Last checked:** 2026-10-18 15:30 AEDT
**Owner:** Hermes delegation `deleg_87a2e156`, task 2 (goal: "Establish and document
the REAL Studio capability for interactive AI-art" on the M5 Ultra / 256 GB).

## Verdict

**Not delivered.** `docs/STUDIO_CAPABILITY.md` does not exist in this repository.
The delegated agent is still running and, at the time of writing, is blocked in a
polling loop around a Hugging Face weight download that had stalled.

## Evidence

- Delegation manifest: `~/.hermes/cache/delegation/live/deleg_87a2e156/manifest.json`
  (3 tasks, all `status: running`; task 2 log `task-2.log`).
- Task 2 log from 12:13 onward consists of `hf download` progress checks interleaved
  with `sleep 500–560` waits. Its last observed download state:
  `Fetching 13 files: 85%` — FLUX.1-schnell transformer shard 2 incomplete.
- HF cache at 14:40: `~/.cache/huggingface/hub/models--black-forest-labs--FLUX.1-schnell`
  held ~9.7 GB of a ~34 GB snapshot; shard
  `diffusion_pytorch_model-00002-of-00003.safetensors` (9.96 GB) was missing.
- The audit's premise that "FLUX.1-schnell weights ARE on disk"
  (`docs/HARDWARE_REALITY.md` §5) was therefore **false**: shards 1 and 3, the T5/CLIP
  encoders and the VAE were present; shard 2 was not.

## What this session did instead

1. Repaired the mflux adapter for mflux 0.23 and pinned the dependency
   (`mflux>=0.23,<0.24`).
2. Resumed the weight download from the partial cache with Xet disabled
   (`HF_HUB_DISABLE_XET=1`) after the Xet path stalled repeatedly, and ran it under a
   stall-restart watchdog.
3. Measured and verified the two installations from this repo
   (`outputs/benchmarks/benchmark.json`, `outputs/seed_surfer/verification.json`,
   `outputs/glitch_lab/verification.json`).

Those measurements are reported in `docs/HARDWARE_REALITY.md` §9 and
`docs/RUNNING.md`, so the machine capability is documented even if the delegated
agent never lands its report.

## If that agent finishes later

Its report should be reconciled against §9 before merging: the audit it was
written against (`09b4d80` / early `f320b07`) predates the adapter repair, the
registry fix and the real measurements. Do not overwrite measured numbers with
its older placeholders.
