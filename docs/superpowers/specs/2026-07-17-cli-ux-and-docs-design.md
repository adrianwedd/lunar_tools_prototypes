# CLI UX & Documentation Rework — Design

**Date:** 2026-07-17 (rev 2, post-QA: codex/agy/hermes findings incorporated)
**Status:** Approved (Phase A now; Phase C wizard as follow-up)

## Goal

Eliminate friction for anyone who wants to run these installations — from a
stranger cold-cloning the repo to a collaborator setting up an installation on
a Mac. The CLI itself should be a work of art: output that feels like it
belongs to an art project, not a build tool.

## Problems (observed and QA-verified)

1. **The CLI cannot launch 14 of the 30 prototype files at all.** Discovery
   derives class names from filenames (`lunar_tools_demo.py:27`), but 14
   prototypes don't follow the convention (`escape_room.py` →
   `EscapeRoomGame`, `interactive_storytelling.py` → `InteractiveStoryteller`,
   etc.). Only 16 demos are currently reachable, one of which is
   `example_base_usage.py`.
2. No way to list demos: `--demo` is required and `--help` doesn't enumerate.
   README claims `--help` lists demos (false); CLAUDE.md claims running
   without args lists demos (also false).
3. Discovery imports every prototype module just to build the name map.
4. `--config` is broken, not just under-documented: the parser splits the
   whole string on `,` before value parsing, so tuple values like
   `window_size=(800,600)` can never parse; entries without `=` are silently
   dropped. The CLAUDE.md example is wrong three ways (dict syntax, a demo
   name that doesn't exist, config keys no prototype accepts).
5. No preflight; failures surface as raw tracebacks compressed to one line.
   Worse, `PrototypeBase.run()` catches exceptions, logs, and returns
   normally (`prototype_base.py:127`), so the CLI can't even see most
   failures today.
6. Nothing tells a user what each demo needs before launching it.
7. Doc drift: CLAUDE.md contradicts itself on test counts (197 vs 199).

## Phase A — registry, doctor, list, honest errors, docs

### Demo registry — `src/lunar_tools_art/demo_registry.py`

A static table (no prototype imports) with one entry per public demo:

- `name` — kebab-case CLI name
- `module` — filename stem in `prototypes/`
- `class_name` — **explicit** entry-point class (the filename convention is
  false for 14/30 files; never derive)
- `description` — one line, human voice
- `requirements` — list of `(capability, level)` where capability ∈
  `{mic, audio-out, camera, renderer, afterwords, llm, image-gen, midi,
  network, peer, assets}` and level ∈ `{required, optional}`. `optional`
  means the demo degrades gracefully without it (e.g. AI Mirror runs without
  Afterwords); doctor reports optional gaps as warnings, not failures.
  `peer` marks ZMQ demos needing a second process — doctor can only warn,
  never verify. `assets` carries a list of file paths (several demos default
  to mp3 files that don't ship in the repo).
- `config_knobs` — list of `(key, type, default, description)` for the demo's
  common `__init__` kwargs; powers `--config` validation now and the Phase C
  wizard prompts later.
- `status` — mirrors `PROTOTYPE_STATUS.md`, displayed as **"headless smoke"**
  status; it is construction-level evidence only and must never be presented
  as "verified to run on hardware".

Exclusions: `__init__.py` and `example_base_usage.py` (a docs example, not a
public demo — matching the smoke-matrix SKIP set). The cross-check test
(registry ↔ `prototypes/` files, both directions) uses this explicit
exclusion list, and additionally asserts each entry's `class_name` exists in
its module (via `ast` parse, no import).

### CLI — `lunar_tools_demo.py` rework

Subcommands `list` / `doctor` / `run`, dispatched after a small `sys.argv`
normalization pass that rewrites legacy `--demo NAME [--config ...]` into
`run NAME [--config ...]` before argparse sees it (top-level `--demo`
coexists badly with subparsers otherwise).

- **`list`** (also the no-args behavior in Phase A): a beautifully rendered
  table of demo name, description, requirement badges, and headless-smoke
  status. Reads only the registry — instant, silent, no prototype imports.
- **`doctor [demo]`**: preflight checks. Each check maps to a registry
  capability so the vocabulary is fully covered:
  - Python version / platform; extras importable — `mlx`, `hw`, **and
    `audio`** (STT); informational on Linux
  - `mic`, `camera`, `audio-out`: device-presence probes run in short-lived
    **subprocesses with hard timeouts** (native code can hang or crash below
    Python; try/except in-process is not containment), gated on the relevant
    extra importing first, distinguishing no-device / permission-denied /
    probe-timeout, always releasing handles
  - `renderer`: display availability (can a window be created — probed in a
    subprocess too)
  - `midi`: device enumeration
  - `llm`: provider-aware — Ollama endpoint reachability + configured model
    present when provider is ollama; provider-specific key set (not a generic
    "cloud key") for claude / ollama-cloud / openrouter; `mlx-lm` importable
    for mlx
  - `image-gen`: configured backend importable (`mflux` etc.)
  - `afterwords`: server reachable at `afterwords.server_url`, respecting
    the privacy gate's local-URL rule
  - `assets`: registry-declared files exist
  - privacy mode, `LUNAR_HEADLESS` state (warn if set interactively), and
    the **resolved settings.toml path** (config loads relative to CWD —
    doctor must say which file it read)
  - Doctor always probes the **real** environment; it never consults the
    headless fakes. Unit tests inject fake probe functions at the check
    layer instead.
  With a demo name: check only that demo's requirements; verdict wording is
  "preflight passed" (never "ready to run" — smoke status can't promise
  that). Exit codes: 0 all-pass, 1 required-check failed, 2 usage error;
  warnings don't affect exit code.
- **`run <name>`**: registry lookup, that demo's required checks first; on
  failure print the diagnosis (not a traceback), exit 3, hint at `doctor`.
  `--force` skips preflight. Known limitation, stated in output when
  relevant: `Manager()` still constructs every tool eagerly, so a demo can
  fail on a capability it doesn't declare; making Manager lazy is a tracked
  follow-up, out of scope here. To surface failures at all,
  `PrototypeBase.run()` gains a minimal result contract: it records the
  fatal exception and the CLI inspects it (a small, tested behavior change —
  carved out of the "don't change prototype behavior" boundary).
- **`--config`**: repeatable `--config KEY=VALUE` (preferred); the legacy
  single-string comma form remains but with a real tokenizer that respects
  parentheses, and malformed entries are rejected loudly. Keys are validated
  against the demo's `config_knobs` (unknown keys warn, typed values parse
  per the declared type).
- **`--debug`** (global flag): show full tracebacks; otherwise unrecognized
  exceptions print a one-line summary. No "see log file" promise — no file
  handler exists today and we're not adding one in Phase A.
- **`--help`** rewritten with examples per subcommand.

### CLI aesthetics — "work of art" bar

- Hand-rolled ANSI styling in `src/lunar_tools_art/cli_style.py` — **no new
  runtime dependencies**. Colors, dim/bold, box-drawing, unicode badges
  (● ○ ◐ for smoke status, ✓ ✗ ⚠ for doctor lines), a lunar-themed header.
- Degrades gracefully: `NO_COLOR`, non-TTY, `TERM=dumb` yield clean plain
  text; every glyph has an ASCII fallback.
- One visual grammar across `list`, `doctor`, `run`, and errors: same
  palette, same badge language, aligned columns.

### Documentation

- **`docs/RUNNING.md`** — per-prototype runbook: requirements (required vs
  optional), Afterwords setup, mic/camera notes, multi-process (ZMQ) demos,
  troubleshooting table keyed to doctor check names.
- **README** quickstart reworked around `list` → `doctor` → `run`. The
  "zero-hardware path" is `LUNAR_HEADLESS=1 python lunar_tools_demo.py run
  <name>` — verified during implementation against a specific named demo
  before the claim is written; no demo currently runs hardware-free without
  the headless layer.
- **CLAUDE.md** — fix the `--config` example (all three errors), the
  no-args claim, and the 197-vs-199 test-count contradiction; document the
  new subcommands.

### Testing

- Registry ↔ filesystem cross-check (with exclusion list) + `class_name`
  existence via `ast`.
- Doctor checks unit-tested with injected probe functions (pass / fail /
  timeout per check; verdict + exit-code aggregation; optional-vs-required
  levels). Subprocess probe wrappers get one integration test each that
  tolerates absent hardware (asserting classification, not presence).
- CLI: `list`, `doctor`, `run` happy/missing-requirement/`--force`, legacy
  `--demo` normalization, repeatable and legacy `--config` parsing incl.
  tuple values and malformed rejection, `--debug`, exit codes.
- Style module: `NO_COLOR`/non-TTY stripping, ASCII fallbacks.
- Existing suite stays green: `LUNAR_HEADLESS=1 pytest -q`.

## Phase C — interactive wizard (follow-up, builds on A)

Bare `python lunar_tools_demo.py` in a TTY becomes a menu: browse demos from
the registry, doctor checks run on selection, missing pieces offered as
guided fixes (or "run anyway"), prompts driven by each demo's
`config_knobs`. Non-TTY keeps plain `list` output. **Behavior change note:**
Phase A's no-args-in-TTY output is `list`; Phase C changes that to the menu —
called out in `--help` and the changelog when it lands.

## Out of scope

- Changing prototype behavior, except the minimal `PrototypeBase.run()`
  result contract above.
- Making `Manager` initialization lazy/requirement-driven (tracked
  follow-up; doctor's honesty about it is in scope).
- New runtime dependencies; file-based logging.
- Hardware *functional* verification (doctor does presence/reachability
  probes only — it answers "is it plugged in and reachable", not "does the
  installation work").
