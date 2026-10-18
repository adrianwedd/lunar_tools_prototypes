# Whispers — Visual Preset Specification

Four preset moods for the Whispers movement-responsive particle aura. All
numbers are exact and directly implementable in the existing numpy/opencv
draw path (half-res `np.add.at` splat layer + `cv2.GaussianBlur` halo +
nearest-neighbour core upscale + additive composite). Each preset is a pure
parameter set; no structural code change is required to host all four.

Where a parameter maps onto a current constant, the current value is given as
`(baseline)` so deltas are unambiguous.

---

## Parameter definitions (how to read the numbers)

- **trail_alpha** — blend in the canvas persistence step:
  `canvas = src*(1-a) + prev*a` (baseline 0.55).
- **particle size range** — `[size_min, size_max]` px radius at splat time
  (baseline 1.2–3.6 px; splat footprint is `size>>1` on the half-res layer).
- **emission_scale** — multiplies the per-frame spawn budget
  `cap/FILL_TIME * dt * energy_factor` (baseline 1.0).
- **swirl_rate** — angular rate of the orbit field, rad/s (baseline 0.05);
  the tangential acceleration coefficient 0.012 scales with it
  (`accel = 0.012 * (swirl_rate/0.05) * swirl_gain`).
- **buoyancy** — upward acceleration in px/s² (baseline 1.4).
- **glow_sigma** — `cv2.GaussianBlur(glow, (0,0), sigma)` on the half-res
  layer (baseline 1.1).
- **core_gain / halo_gain** — additive weights after upscale:
  `out += core*core_gain; out += halo*halo_gain` (baseline 0.9 / 1.4).
  The splat pre-weight (baseline 0.55) is fixed at 0.55 for all presets.
- **colour mapping** — how `self._col[i] = f(source_pixel)` is derived.
- **bg_tint** — RGB tint blended into the source frame before compositing:
  `frame = frame*(1-k) + tint*k` with tint strength `k`.
- **fade_exp** — lifetime fade becomes `fade_norm ** fade_exp`
  (baseline curve was `0.06 + 0.94 * fade²`, i.e. floor 0.06, exp 2).
  Specified as `(floor, exponent)`.
- **when to use** — the mood/context the preset was tuned for.

---

## Preset 1 — “Ember Library”

*Poetic line:* Old light leaving the furniture, one spark at a time.

| Parameter | Value |
|---|---|
| trail_alpha | 0.62 |
| particle size range | 1.0 – 2.8 px |
| emission_scale | 0.75 |
| swirl_rate | 0.035 rad/s |
| buoyancy | 2.2 px/s² |
| glow_sigma | 1.3 |
| core_gain / halo_gain | 0.85 / 1.15 |
| colour mapping | Sample the source pixel, then push warmth and suppress saturation-floor: `col = clip(pixel * [1.15, 0.95, 0.72]) + [18, 4, 0]`. Dark pixels (< luminance 30) are lifted to a dim ember floor `col = max(col, [70, 28, 8])` so particles read as coals, not mud. |
| bg_tint | `(24, 14, 8)` at k = 0.10 (deep umber room tone) |
| fade_exp | (0.04, 2.4) — long dim tail, near-invisible death |
| when to use | Low-light gallery evenings, warm practical lighting, slow single visitors. The default "stately" mood; pairs with whisper audio. |

---

## Preset 2 — “Tidal Memory”

*Poetic line:* The room exhales in cyan; nothing arrives, nothing leaves.

| Parameter | Value |
|---|---|
| trail_alpha | 0.80 |
| particle size range | 0.8 – 2.0 px |
| emission_scale | 1.4 |
| swirl_rate | 0.020 rad/s |
| buoyancy | 0.5 px/s² |
| glow_sigma | 2.0 |
| core_gain / halo_gain | 0.45 / 1.8 |
| colour mapping | Desaturate the source toward luminance, then map through a cool ramp: `lum = pixel @ [0.30, 0.55, 0.15]`; `col = ramp(lum/255)` where `ramp` is a 4-stop linear interpolation over stops `(0)=[2, 12, 26], (0.35)=[10, 60, 96], (0.7)=[30, 140, 170], (1)=[120, 230, 240]` (RGB). Room colour is erased on purpose: the aura is tidal, not a mirror. |
| bg_tint | `(10, 20, 26)` at k = 0.14 (abyssal teal wash) |
| fade_exp | (0.10, 1.4) — fades early and lingers faintly |
| when to use | Bright or cluttered rooms where sampled colour would look noisy; long installations where accumulation should read as water, not dust. Big soft haloes dominate: motion smears into sheets. |

---

## Preset 3 — “Ghost Bloom”

*Poetic line:* A pale flower of light opens where you just were.

| Parameter | Value |
|---|---|
| trail_alpha | 0.48 |
| particle size range | 2.0 – 5.0 px |
| emission_scale | 0.55 |
| swirl_rate | 0.090 rad/s |
| buoyancy | -0.6 px/s² (sinks — petals fall) |
| glow_sigma | 2.6 |
| core_gain / halo_gain | 1.1 / 0.7 |
| colour mapping | Invert-and-bloom: `col = clip(255 - pixel, 0, 255) * [1.0, 0.92, 1.0]`, then blend 30% of the original pixel back (`col = 0.7*inverted + 0.3*pixel`). Dark clothing and shadow become luminous; bright windows dim — presence glows, background recedes. |
| bg_tint | `(36, 34, 42)` at k = 0.06 (cold grey-violet haze) |
| fade_exp | (0.02, 3.2) — bright newborns, sudden senescence |
| when to use | Small dark rooms, silhouette-driven staging (backlit doorways, projections). Few, large, short-lived blooms rather than an atmosphere; strongest when visitors enter and leave often. |

---

## Preset 4 — “Signal Chapel”

*Poetic line:* Every gesture is answered in stained glass and static.

| Parameter | Value |
|---|---|
| trail_alpha | 0.68 |
| particle size range | 1.4 – 3.2 px |
| emission_scale | 1.0 |
| swirl_rate | 0.140 rad/s |
| buoyancy | 1.0 px/s² |
| glow_sigma | 0.9 |
| core_gain / halo_gain | 1.35 / 0.95 |
| colour mapping | Quantise the source hue to a 6-stop stained-glass ramp: convert pixel to HSV; `h_q = floor(h/60)*60`; look up `col` from amber `[255,140,20]`, gold `[255,210,60]`, jade `[40,220,140]`, cobalt `[50,90,255]`, violet `[170,60,255]`, rose `[255,60,120]`; multiply by `s` and a soft `v^0.8` so dim pixels stay dim. Colour is the room's, but flattened to glass panes. |
| bg_tint | `(14, 10, 20)` at k = 0.08 (incense-dark violet) |
| fade_exp | (0.08, 1.8) |
| when to use | High-energy contexts: openings, parties, multiple simultaneous visitors, music in the room. Fast swirl + tight halo keeps rapidly moving crowds legible instead of smeary. |

---

## Per-state multipliers

Three motion states, derived from the existing motion-energy signal
(`energy = mean abs diff` on the 160×90 grid, with its slow EMA):

- **STILLNESS** — `energy < 1.5` sustained ≥ 3 s (calm drift)
- **GENTLE** — `1.5 ≤ energy < 8.0`, or EMA-rising but below burst (slow bloom)
- **BURST** — `energy ≥ max(8.0, 1.8 × EMA)` (sudden gesture; same trigger as
  the whisper burst, `WHISPER_BURST_FACTOR`)

All multipliers are applied to the **preset's** base values; 1.00 = no change.
Blend between states over 1.5 s (lerp all multipliers) so state changes never
pop. Multipliers apply identically to every preset.

| Multiplier | STILLNESS (calm drift) | GENTLE (slow bloom) | BURST (bright burst) |
|---|---|---|---|
| trail_alpha_scale | 1.15 (trails persist longer) | 1.00 | 0.75 (trails clear fast so the burst reads sharp) |
| emission_scale | 0.60 | 1.00 | 2.60 |
| size_scale | 0.85 (small motes) | 1.00 | 1.40 (big flaring bodies) |
| swirl_rate_scale | 0.70 (orbit nearly stalls) | 1.00 | 2.20 |
| buoyancy_scale | 0.50 (barely rising) | 1.00 | 1.80 |
| glow_sigma_scale | 1.25 (softest halos in quiet) | 1.00 | 0.70 (tight, punchy glow) |
| core_gain_scale | 0.85 | 1.00 | 1.60 |
| halo_gain_scale | 0.90 | 1.00 | 1.30 |
| brightness_floor (fade curve floor override) | 0.10 (dim, dreamy) | preset value | preset value |
| fade_exp_scale | 0.80 (die even slower) | 1.00 | 1.30 (burn out faster) |

### Why these separate cleanly

- **Calm drift** is characterised by long soft trails (high trail_alpha,
  big sigma, low core) and slow death — a still room keeps breathing as a
  faint haze. Emission still happens from camera-noise-level motion, but at
  0.6× and small sizes, so it reads as dust in light rather than activity.
- **Slow bloom** is the invisible default — the preset's own tuning, so all
  multipliers are 1.00 and the preset's character is fully expressed.
- **Bright burst** inverts the haze: emission ×2.6 with bigger particles and
  core-dominated gain (1.6× core, tighter sigma) makes a sudden gesture flash
  crystalline rather than further fogging an already-full aura; trails are
  shortened (0.75× trail_alpha) so the frame recovers within ~2 s and the next
  gesture is legible.

### Implementation notes

- Compute the state from `energy` and `_energy_ema` once per frame (already
  available); lerp a single `state_mix` vector of multipliers toward the
  target state's row with time constant ~1.5 s.
- The fade curve becomes `fade = floor + (1-floor) * fade_norm ** (fade_exp * fade_exp_scale)`.
- `bg_tint` and `colour mapping` are preset-only and deliberately do NOT vary
  by state — the room must not change its identity when a visitor waves.