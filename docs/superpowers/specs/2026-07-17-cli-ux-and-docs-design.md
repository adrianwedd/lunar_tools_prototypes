# CLI UX & Documentation Rework — Design

**Date:** 2026-07-17
**Status:** Approved (Phase A now; Phase C wizard as follow-up)

## Goal

Eliminate friction for anyone who wants to run these installations — from a
stranger cold-cloning the repo to a collaborator setting up an installation on
a Mac. The CLI itself should be a work of art: output that feels like it
belongs to an art project, not a build tool.

## Problems (observed, not hypothetical)

1. No way to list demos: `--demo` is required, `--help` doesn't enumerate,
   and the README falsely claims running without args lists demos.
2. Demo discovery imports all 29 prototype modules just to build a name map
   (slow, emits noisy warnings).
3. `--config` documentation drift: CLAUDE.md shows a dict-literal example;
   the CLI parses `key=value,key=value`.
4. No preflight: missing hardware/extras/keys/Afterwords surface as raw
   tracebacks compressed into a one-line "unexpected error".
5. Nothing tells a user what each demo needs (mic, camera, Afterwords, cloud
   key) before launching it.

## Phase A — registry, doctor, list, honest errors, docs

### Demo registry — `src/lunar_tools_art/demo_registry.py`

A static table (no prototype imports) mapping each demo to:

- `name` (kebab-case, matches CLI name)
- `module` (filename stem in `prototypes/`)
- `description` (one line, human voice)
- `requirements`: subset of
  `{mic, camera, renderer, afterwords, llm, image-gen, cloud-key, midi, network}`
- `status`: mirrors `PROTOTYPE_STATUS.md` (`works` / `degraded`)

Static because requirements are not derivable from code and listing must be
instant. A test cross-checks the registry against the actual files in
`prototypes/` (both directions: no missing, no stale entries).

### CLI — `lunar_tools_demo.py` rework

Subcommand structure, with legacy `--demo NAME [--config ...]` preserved as an
alias for `run`:

- **`list`** (also the no-args behavior): a beautifully rendered table of
  demo name, description, requirement badges, and status. Reads only the
  registry — instant, silent.
- **`doctor [demo]`**: preflight checks, each printed as a pass/warn/fail line
  with the *exact fix command*:
  - Python version and platform
  - extras importable (`mlx`, `hw` groups) — informational on Linux
  - mic / camera presence (via lightweight probes, never crashing)
  - Afterwords server reachability (`afterwords.server_url`)
  - `privacy.mode` and, if `cloud-ok`, which API keys are set (never printing
    values)
  - `LUNAR_HEADLESS` state (warn if set in an interactive session)
  With a demo name: check only that demo's requirements; end with a clear
  verdict — "ready to run" or the list of missing pieces.
- **`run <name>`**: consult the registry, run that demo's doctor checks first;
  on failure print the diagnosis (not a traceback) and exit 1 with a hint to
  run `doctor`. Recognizable runtime failures are mapped to friendly messages
  (e.g. connection-refused to Afterwords → how to start it). `--config`
  keeps `key=value,...` syntax; a `--force` flag skips preflight.
- **`--help`** rewritten with examples for each subcommand.

### CLI aesthetics — "work of art" bar

- Hand-rolled ANSI styling in a small `src/lunar_tools_art/cli_style.py`
  module — **no new runtime dependencies** (no `rich`). Colors, dim/bold,
  box-drawing and unicode badges (● ○ ◐ for works/missing/degraded, ✓ ✗ ⚠ for
  doctor lines), a lunar-themed header.
- Degrades gracefully: `NO_COLOR`, non-TTY, and `TERM=dumb` all yield clean
  plain-text output; every glyph has an ASCII fallback.
- Consistent visual grammar across `list`, `doctor`, `run`, and error output:
  same palette, same badge language, aligned columns.

### Documentation

- **`docs/RUNNING.md`** — per-prototype runbook: requirements per demo,
  Afterwords setup, mic/camera configuration notes, and a troubleshooting
  table keyed to doctor check names.
- **README** quickstart reworked around `list` → `doctor` → `run`, calling out
  a zero-hardware/zero-key starter demo; all drifted claims fixed.
- **CLAUDE.md** — fix the dict-style `--config` example; document the new
  subcommands.

### Error handling

Preflight failures and recognized runtime failures print styled, actionable
diagnoses. Unrecognized exceptions still show the traceback when
`--debug`/`LOG_LEVEL=DEBUG` is set; otherwise a one-line summary plus the log
location.

### Testing

- Registry ↔ filesystem cross-check test.
- Doctor checks unit-tested against headless fakes (each check individually,
  plus verdict aggregation).
- CLI paths: `list`, `doctor`, `run` (happy + missing-requirement), legacy
  `--demo` alias, `--config` parsing.
- Style module: color stripping under `NO_COLOR`/non-TTY.
- Existing suite stays green: `LUNAR_HEADLESS=1 pytest -q`.

## Phase C — interactive wizard (follow-up, builds on A)

Bare `python lunar_tools_demo.py` in a TTY becomes a menu: browse demos from
the registry, doctor checks run automatically on selection, missing pieces
offered as guided fixes (or "run anyway"), prompts for the demo's common
config knobs. Non-TTY keeps plain `list` output. Thin by design: the wizard is
a front-end over the Phase A registry + checks.

## Out of scope

- Changing any prototype's behavior.
- New runtime dependencies.
- Hardware verification work (tracked separately).
