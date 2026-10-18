# Studio Capability Report — status

**Last checked:** 2026-10-18 16:40 AEDT

## Verdict

**DELIVERED.** `docs/STUDIO_CAPABILITY.md` (161 lines, fully measured) landed at
16:35 when the delegated capability/benchmark agent completed (duration 4.36 h,
-dominated by a stalled ~34 GB FLUX.1-schnell Xet download that was restarted
via Xet-disabled resume). This superseded status doc is retained as the
crossover record; see `docs/STUDIO_CAPABILITY.md` for the authoritative report.

## Headline measured results (full detail in docs/STUDIO_CAPABILITY.md)

- Env: `env/` = CPython 3.13.15 (uv), the only machine env with the complete
  MLX + torch/diffusers + cv2 + MIDI-software stack; keep Pillow ≤12.
- mflux FLUX.1-schnell 4-step [measured]: 512² 5.80 s mean (27.5 GB peak),
  768² 6.67 s (30.7 GB), 1024² 10.65 s (36.0 GB); cold incl. weight load 13.5 s.
- Seed reproducibility [measured]: NOT bit-reproducible across processes
  (GPU reduction non-determinism); the scheduler's cache key includes model
  identity to make served results identity-consistent regardless.
- SD-1.5 diffusers (torch MPS, fp32): measured in `sd15_bench.json`.
- Audio input: **no input-capable device exists on this host** (0 capture
  devices — not a TCC issue). Camera: TCC denied for the agent host and
  possibly no camera attached ([unverified] which). MIDI: no hardware
  connected; rtmidi/mido import-ready.
- Post-audit warm re-measure for Seed Surfer's production path:
  512² **1.64 s** warm, 1024² **5.89 s** warm (FLUX 4-bit, 4 steps) — see
  `docs/HARDWARE_REALITY.md` §9.2.

## If that agent finishes later

Its report should be reconciled against §9 before merging: the audit it was
written against (`09b4d80` / early `f320b07`) predates the adapter repair, the
registry fix and the real measurements. Do not overwrite measured numbers with
its older placeholders.
