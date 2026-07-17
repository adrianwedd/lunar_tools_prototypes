# CLI UX Phase A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `lunar_tools_demo.py` around a static demo registry with `list`/`doctor`/`run` subcommands, subprocess-isolated hardware preflight, honest error reporting, and gorgeous terminal output — plus docs that match reality.

**Architecture:** A static registry (`demo_registry.py`) is the single source of truth for demo metadata (explicit class names — the filename convention is false for 14/30 files). A check framework (`doctor.py`) maps every registry capability to a probe; hardware probes run in short-lived subprocesses with timeouts. The CLI dispatches subcommands after normalizing legacy `--demo` argv, and styles everything through `cli_style.py` (zero new dependencies).

**Tech Stack:** Python 3.10+ stdlib only for new code (argparse, subprocess, ast, urllib). Tests: pytest with `LUNAR_HEADLESS=1`.

## Global Constraints

- No new runtime dependencies (no `rich`; hand-rolled ANSI in `cli_style.py`).
- Every test command is run as `LUNAR_HEADLESS=1 pytest ...`; full suite must stay green (199 passing baseline).
- Doctor probes the **real** environment, never the headless fakes; unit tests inject probe functions instead.
- Verdict wording: "preflight passed", never "ready to run". Status column label: "headless smoke".
- All glyphs need ASCII fallbacks; respect `NO_COLOR`, non-TTY, `TERM=dumb`.
- Exit codes — `doctor`: 0 pass, 1 required-check fail, 2 usage. `run`: 0 ok, 1 runtime failure, 2 usage, 3 preflight fail, 4 unknown demo.
- Commit after every green test cycle; pre-commit hooks (black/isort/ruff/bandit) must pass.

---

### Task 1: `cli_style.py` — styling primitives

**Files:**
- Create: `src/lunar_tools_art/cli_style.py`
- Test: `tests/test_cli_style.py`

**Interfaces:**
- Produces: `Style` class with `styled(text, *codes) -> str`, `badge(kind) -> str`, `header(title) -> str`, `table(rows, headers) -> str`, `check_line(status, name, detail, fix=None) -> str`; module-level factory `make_style(stream=sys.stdout) -> Style`. `Style.enabled` (color on/off) and `Style.unicode_ok` are decided at construction.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli_style.py
import io
import os
from unittest import mock

from lunar_tools_art.cli_style import Style, make_style


class FakeTTY(io.StringIO):
    def isatty(self):
        return True


def test_color_disabled_on_non_tty():
    s = make_style(io.StringIO())
    assert not s.enabled
    assert s.styled("moon", s.BOLD) == "moon"


def test_color_enabled_on_tty():
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("NO_COLOR", None)
        s = make_style(FakeTTY())
    assert s.enabled
    assert s.styled("moon", s.BOLD) == "\x1b[1mmoon\x1b[0m"


def test_no_color_env_wins_over_tty():
    with mock.patch.dict(os.environ, {"NO_COLOR": "1"}):
        s = make_style(FakeTTY())
    assert not s.enabled


def test_term_dumb_disables_unicode_and_color():
    with mock.patch.dict(os.environ, {"TERM": "dumb"}):
        s = make_style(FakeTTY())
    assert not s.enabled and not s.unicode_ok


def test_badges_have_ascii_fallbacks():
    uni = Style(enabled=False, unicode_ok=True)
    ascii_ = Style(enabled=False, unicode_ok=False)
    assert uni.badge("pass") == "✓" and ascii_.badge("pass") == "OK"
    assert uni.badge("fail") == "✗" and ascii_.badge("fail") == "XX"
    assert uni.badge("warn") == "⚠" and ascii_.badge("warn") == "!!"
    assert uni.badge("works") == "●" and ascii_.badge("works") == "*"
    assert uni.badge("degraded") == "◐" and ascii_.badge("degraded") == "~"


def test_table_aligns_columns_plaintext():
    s = Style(enabled=False, unicode_ok=False)
    out = s.table([["a", "bb"], ["ccc", "d"]], headers=["one", "two"])
    lines = out.splitlines()
    assert lines[0].index("two") == lines[1].index("bb") == lines[2].index("d")


def test_check_line_includes_fix_hint():
    s = Style(enabled=False, unicode_ok=False)
    line = s.check_line("fail", "afterwords", "server unreachable",
                        fix="cd ../afterwords && python server.py")
    assert "XX" in line and "afterwords" in line
    assert "cd ../afterwords" in line
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `LUNAR_HEADLESS=1 pytest tests/test_cli_style.py -v`
Expected: FAIL — `ModuleNotFoundError: lunar_tools_art.cli_style`

- [ ] **Step 3: Implement `cli_style.py`**

```python
# src/lunar_tools_art/cli_style.py
"""Hand-rolled terminal styling for the demo CLI. Zero dependencies.

One visual grammar for list/doctor/run/errors: a small palette, unicode
badges with ASCII fallbacks, aligned tables, and a lunar header. Color and
unicode degrade independently: NO_COLOR / non-TTY kill color, TERM=dumb
kills both.
"""
import os
import sys

_BADGES_UNICODE = {"pass": "✓", "fail": "✗", "warn": "⚠",
                   "works": "●", "degraded": "◐", "missing": "○"}
_BADGES_ASCII = {"pass": "OK", "fail": "XX", "warn": "!!",
                 "works": "*", "degraded": "~", "missing": "-"}


class Style:
    RESET = "0"
    BOLD = "1"
    DIM = "2"
    MOON = "38;5;153"      # pale lunar blue — headers, demo names
    OK = "38;5;114"        # soft green
    BAD = "38;5;210"       # soft red
    WARN = "38;5;222"      # soft amber

    def __init__(self, enabled: bool, unicode_ok: bool):
        self.enabled = enabled
        self.unicode_ok = unicode_ok

    def styled(self, text: str, *codes: str) -> str:
        if not self.enabled or not codes:
            return text
        return f"\x1b[{';'.join(codes)}m{text}\x1b[0m"

    def badge(self, kind: str) -> str:
        table = _BADGES_UNICODE if self.unicode_ok else _BADGES_ASCII
        return table[kind]

    def header(self, title: str) -> str:
        moon = "☾" if self.unicode_ok else ")"
        line = f"{moon} {title}"
        rule = ("─" if self.unicode_ok else "-") * len(line)
        return "\n".join([self.styled(line, self.BOLD, self.MOON),
                          self.styled(rule, self.DIM)])

    def table(self, rows, headers) -> str:
        widths = [max(len(str(c)) for c in col)
                  for col in zip(headers, *rows)]
        def fmt(cells, *codes):
            return "  ".join(
                self.styled(str(c).ljust(w), *codes)
                for c, w in zip(cells, widths)).rstrip()
        out = [fmt(headers, self.BOLD)]
        out += [fmt(r) for r in rows]
        return "\n".join(out)

    def check_line(self, status: str, name: str, detail: str,
                   fix: str | None = None) -> str:
        color = {"pass": self.OK, "fail": self.BAD, "warn": self.WARN}[status]
        line = (f"  {self.styled(self.badge(status), color)} "
                f"{self.styled(name.ljust(14), self.BOLD)} {detail}")
        if fix:
            arrow = "↳" if self.unicode_ok else ">"
            line += f"\n      {self.styled(arrow + ' ' + fix, self.DIM)}"
        return line


def make_style(stream=None) -> Style:
    stream = stream or sys.stdout
    dumb = os.environ.get("TERM") == "dumb"
    tty = hasattr(stream, "isatty") and stream.isatty()
    enabled = tty and not dumb and "NO_COLOR" not in os.environ
    return Style(enabled=enabled, unicode_ok=not dumb)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `LUNAR_HEADLESS=1 pytest tests/test_cli_style.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/lunar_tools_art/cli_style.py tests/test_cli_style.py
git commit -m "feat: terminal styling module for demo CLI (zero deps)"
```

---

### Task 2: `demo_registry.py` — schema + data + cross-check tests

**Files:**
- Create: `src/lunar_tools_art/demo_registry.py`
- Test: `tests/test_demo_registry.py`

**Interfaces:**
- Produces: `Requirement(capability: str, level: str)`, `ConfigKnob(key, type, default, description)`, `Demo(name, module, class_name, description, requirements, config_knobs, status, assets)` dataclasses; `DEMOS: dict[str, Demo]` keyed by kebab name; `CAPABILITIES` frozenset; `EXCLUDED_MODULES = {"__init__", "example_base_usage"}`.

- [ ] **Step 1: Write the failing cross-check tests**

```python
# tests/test_demo_registry.py
import ast
from pathlib import Path

from lunar_tools_art.demo_registry import (
    CAPABILITIES, DEMOS, EXCLUDED_MODULES,
)

PROTO = Path(__file__).resolve().parents[1] / "prototypes"


def _module_stems():
    return {p.stem for p in PROTO.glob("*.py")} - EXCLUDED_MODULES


def test_registry_covers_every_prototype_file():
    assert {d.module for d in DEMOS.values()} == _module_stems()


def test_no_stale_registry_entries():
    stems = _module_stems()
    for d in DEMOS.values():
        assert d.module in stems, f"{d.name} points at missing module"


def test_class_name_exists_in_module_source():
    for d in DEMOS.values():
        tree = ast.parse((PROTO / f"{d.module}.py").read_text())
        classes = {n.name for n in tree.body if isinstance(n, ast.ClassDef)}
        assert d.class_name in classes, (
            f"{d.name}: class {d.class_name} not found in {d.module}.py "
            f"(has {classes})")


def test_requirement_vocabulary_and_levels():
    for d in DEMOS.values():
        for r in d.requirements:
            assert r.capability in CAPABILITIES, (d.name, r.capability)
            assert r.level in ("required", "optional")


def test_config_knobs_match_init_params():
    for d in DEMOS.values():
        tree = ast.parse((PROTO / f"{d.module}.py").read_text())
        cls = next(n for n in tree.body
                   if isinstance(n, ast.ClassDef) and n.name == d.class_name)
        init = next((n for n in cls.body if isinstance(n, ast.FunctionDef)
                     and n.name == "__init__"), None)
        params = ({a.arg for a in init.args.args} | {a.arg for a in init.args.kwonlyargs}
                  if init else set())
        for knob in d.config_knobs:
            assert knob.key in params, (
                f"{d.name}: knob {knob.key} not an __init__ param of "
                f"{d.class_name} ({sorted(params)})")


def test_descriptions_are_single_line_and_nonempty():
    for d in DEMOS.values():
        assert d.description and "\n" not in d.description
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `LUNAR_HEADLESS=1 pytest tests/test_demo_registry.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement the registry**

Schema first:

```python
# src/lunar_tools_art/demo_registry.py
"""Static registry of every public demo. THE source of truth for the CLI.

No prototype imports happen here — listing must be instant and side-effect
free. class_name is explicit because the filename→CamelCase convention is
false for 14 of 30 prototype files.
"""
from dataclasses import dataclass, field

CAPABILITIES = frozenset({
    "mic", "audio-out", "camera", "renderer", "afterwords", "llm",
    "image-gen", "midi", "network", "peer", "assets",
})

EXCLUDED_MODULES = {"__init__", "example_base_usage"}


@dataclass(frozen=True)
class Requirement:
    capability: str
    level: str = "required"     # or "optional"


@dataclass(frozen=True)
class ConfigKnob:
    key: str
    type: type
    default: object
    description: str


@dataclass(frozen=True)
class Demo:
    name: str
    module: str
    class_name: str
    description: str
    requirements: tuple = ()
    config_knobs: tuple = ()
    status: str = "works"       # headless-smoke status from PROTOTYPE_STATUS.md
    assets: tuple = ()          # file paths the demo expects to exist


def _req(*caps, optional=()):
    return tuple(Requirement(c, "optional" if c in optional else "required")
                 for c in caps)
```

Then the data. Use this verified stem→class map (from an AST scan; do NOT
trust filenames):

| module | class_name |
|---|---|
| acoustic-fingerprint-painter | AcousticFingerprintPainter |
| ai-dream-interpreter-prototype | AIDreamInterpreter |
| ai-fashion-show-prototype | AIFashionShow |
| ai-mirror-of-truth | AiMirrorOfTruth |
| apocalypse_experience | ApocalypseExperience |
| audio-reactive-fractal-forest | AudioReactiveFractalForest |
| audio_mirror | AudioMirror |
| augmented_audio_tours | AugmentedAudioTour |
| chat-room-narrative-quilt | ChatRoomNarrativeQuilt |
| collaborative-canvas | CollaborativeCanvas |
| collaborative_art | CollaborativeArtServer |
| cosmic-soundscape | CosmicSoundscape |
| data-driven-cityscape | DataDrivenCityscape |
| dynamic_visuals | DynamicVisualizer |
| emotional-landscape-generator-prototype | EmotionalLandscapeGenerator |
| escape_room | EscapeRoomGame |
| evolving-cosmic-mural-prototype | EvolvingCosmicMural |
| generative-poetry-mosaic | GenerativePoetryMosaic |
| interactive-storytelling-canvas-prototype | InteractiveStorytellingCanvas |
| interactive_storytelling | InteractiveStoryteller |
| neural-transfer-music-visualizer | NeuralTransferMusicVisualizer |
| real-time-glitch-art-lab | RealTimeGlitchArtLab |
| sentiment_analysis_display | SentimentDisplay |
| speech_activated_art | SpeechArtGenerator |
| temporal-art-gallery-prototype | TemporalArtGallery |
| time-shifted-echo-chamber | TimeShiftedEchoChamber |
| virtual-cloud-chamber | VirtualCloudChamber |
| virtual_time_travel | TimeTravelExperience |
| whispers | Whispers |

Registry entries: for each of the 29 modules, **open the prototype source and
read its `__init__` and `run`/`update`** to set requirements, knobs, and
assets. Starting values (verify each against source while writing the entry;
the cross-check tests catch class/knob errors but requirements are judgment):

```python
DEMOS = {d.name: d for d in [
    Demo("audio-mirror", "audio_mirror", "AudioMirror",
         "Captures your voice, progressively clones it, and speaks personal insights back in your own voice.",
         _req("mic", "camera", "afterwords", "llm", "renderer", "audio-out")),
    Demo("ai-mirror-of-truth", "ai-mirror-of-truth", "AiMirrorOfTruth",
         "Camera mirror with live emotion detection, prosody analysis, and a voice that answers what it sees.",
         _req("camera", "mic", "llm", "renderer", "audio-out",
              optional=("afterwords",))),
    Demo("interactive-storytelling", "interactive_storytelling",
         "InteractiveStoryteller",
         "Speak a story seed; the room answers with narrative, imagery, and sound.",
         _req("mic", "llm", "image-gen", "renderer", "audio-out")),
    Demo("escape-room", "escape_room", "EscapeRoomGame",
         "Voice-driven escape room with AI intent parsing and audio cues.",
         _req("mic", "llm", "audio-out", "renderer", "assets"),
         assets=("correct_answer.mp3", "hint.mp3")),
    Demo("apocalypse-experience", "apocalypse_experience",
         "ApocalypseExperience",
         "Ambient end-times soundscape with reactive visuals.",
         _req("audio-out", "renderer", "assets"),
         assets=("apocalypse_ambient.mp3",)),
    Demo("dynamic-visuals", "dynamic_visuals", "DynamicVisualizer",
         "MIDI-controlled generative visuals.",
         _req("midi", "renderer")),
    Demo("collaborative-canvas", "collaborative-canvas",
         "CollaborativeCanvas",
         "Two-machine shared canvas over ZMQ.",
         _req("peer", "network", "renderer")),
    Demo("collaborative-art", "collaborative_art", "CollaborativeArtServer",
         "ZMQ server half of the collaborative art pair.",
         _req("peer", "network", "renderer")),
    Demo("data-driven-cityscape", "data-driven-cityscape",
         "DataDrivenCityscape",
         "Generative skyline that morphs with live weather (synthetic data offline).",
         _req("renderer", optional=("network",))),
    Demo("neural-transfer-music-visualizer",
         "neural-transfer-music-visualizer", "NeuralTransferMusicVisualizer",
         "Style-transfer visuals driven by a music track.",
         _req("audio-out", "renderer", "assets"),
         assets=("your_music_track.mp3",)),
    Demo("augmented-audio-tours", "augmented_audio_tours",
         "AugmentedAudioTour",
         "Location-aware audio tour (vision-based positioning pending a vision LLM).",
         _req("camera", "audio-out", "renderer", optional=("llm",)),
         status="degraded"),
    # ... one Demo(...) per remaining module from the table above, same
    # pattern: mic+llm+renderer for speech-driven pieces, +image-gen where
    # the prototype calls manager.image_gen, camera for camera pieces.
]}
```

The "..." above is a data-entry instruction, not deferred design: every
remaining module in the stem→class table gets an entry in this literal in
this step, using `_req` with judgment from its source. The test in Step 1
fails listing exactly which modules are missing — use it as the checklist.
Add `config_knobs` only for kwargs that actually exist on `__init__`
(`test_config_knobs_match_init_params` enforces this); when in doubt, leave
knobs empty.

- [ ] **Step 4: Run tests until green**

Run: `LUNAR_HEADLESS=1 pytest tests/test_demo_registry.py -v`
Expected: 6 passed (the coverage test names any module you missed)

- [ ] **Step 5: Commit**

```bash
git add src/lunar_tools_art/demo_registry.py tests/test_demo_registry.py
git commit -m "feat: static demo registry with explicit class names and requirement levels"
```

---

### Task 3: `doctor.py` — check framework (injected probes)

**Files:**
- Create: `src/lunar_tools_art/doctor.py`
- Test: `tests/test_doctor.py`

**Interfaces:**
- Consumes: `Demo`, `Requirement` from `demo_registry`; `Style` from `cli_style`.
- Produces: `CheckResult(name, status, detail, fix)` with status ∈ `{"pass","fail","warn"}`; `run_checks(demo: Demo | None, probes: dict[str, callable] | None = None) -> list[CheckResult]`; `verdict(results) -> tuple[str, int]` returning (message, exit_code); `DEFAULT_PROBES: dict[str, callable]` (filled by Tasks 4–5, starts with env checks only).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_doctor.py
from lunar_tools_art.demo_registry import Demo, Requirement
from lunar_tools_art.doctor import CheckResult, run_checks, verdict


def _demo(*reqs):
    return Demo("t", "t", "T", "test demo",
                requirements=tuple(Requirement(c, lvl) for c, lvl in reqs))


def ok(name):
    return lambda: CheckResult(name, "pass", "present", None)


def bad(name, fix="do the thing"):
    return lambda: CheckResult(name, "fail", "absent", fix)


def test_demo_scoped_checks_only_probe_declared_capabilities():
    calls = []
    probes = {"mic": lambda: (calls.append("mic"), ok("mic")())[1],
              "camera": lambda: (calls.append("camera"), ok("camera")())[1]}
    run_checks(_demo(("mic", "required")), probes=probes)
    assert calls == ["mic"]


def test_optional_failure_becomes_warn_not_fail():
    res = run_checks(_demo(("afterwords", "optional")),
                     probes={"afterwords": bad("afterwords")})
    (r,) = [x for x in res if x.name == "afterwords"]
    assert r.status == "warn"


def test_verdict_exit_codes():
    passing = [CheckResult("a", "pass", "", None)]
    warned = passing + [CheckResult("b", "warn", "", None)]
    failed = warned + [CheckResult("c", "fail", "", "fix it")]
    assert verdict(passing) == ("preflight passed", 0)
    assert verdict(warned)[1] == 0            # warnings don't fail preflight
    assert "preflight passed" in verdict(warned)[0]
    msg, code = verdict(failed)
    assert code == 1 and "preflight passed" not in msg


def test_probe_exception_is_a_fail_not_a_crash():
    def boom():
        raise RuntimeError("device exploded")
    (r,) = [x for x in run_checks(_demo(("midi", "required")),
                                  probes={"midi": boom})
            if x.name == "midi"]
    assert r.status == "fail" and "device exploded" in r.detail


def test_full_doctor_includes_environment_checks():
    names = {r.name for r in run_checks(None, probes={})}
    assert {"python", "settings", "headless"} <= names
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `LUNAR_HEADLESS=1 pytest tests/test_doctor.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement the framework**

```python
# src/lunar_tools_art/doctor.py
"""Preflight checks. Probes real hardware/services — never headless fakes.

Each registry capability maps to a probe callable returning a CheckResult.
Tests inject probe dicts; the real DEFAULT_PROBES are registered by the
probe modules (hardware_probes, service_probes).
"""
import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str          # pass | fail | warn
    detail: str
    fix: str | None


DEFAULT_PROBES: dict = {}    # capability -> callable() -> CheckResult


def _environment_checks() -> list:
    results = [CheckResult(
        "python", "pass" if sys.version_info >= (3, 10) else "fail",
        f"{sys.version_info.major}.{sys.version_info.minor} on {sys.platform}",
        None if sys.version_info >= (3, 10) else "install Python 3.10+")]
    settings = Path.cwd() / "settings.toml"
    results.append(CheckResult(
        "settings", "pass" if settings.exists() else "warn",
        f"reading {settings}" if settings.exists()
        else f"no settings.toml in {Path.cwd()} — using built-in defaults",
        None if settings.exists() else "run from the repository root"))
    headless = os.environ.get("LUNAR_HEADLESS") == "1"
    results.append(CheckResult(
        "headless", "warn" if headless else "pass",
        "LUNAR_HEADLESS=1 — all tools are fakes; demos will not touch hardware"
        if headless else "real hardware mode",
        "unset LUNAR_HEADLESS to use real devices" if headless else None))
    return results


def run_checks(demo=None, probes=None) -> list:
    probes = DEFAULT_PROBES if probes is None else probes
    results = _environment_checks()
    reqs = (demo.requirements if demo
            else [type("R", (), {"capability": c, "level": "required"})()
                  for c in sorted(probes)])
    for req in reqs:
        probe = probes.get(req.capability)
        if probe is None:
            continue
        try:
            r = probe()
        except Exception as e:              # probe bugs must not kill doctor
            r = CheckResult(req.capability, "fail", str(e), None)
        if req.level == "optional" and r.status == "fail":
            r = CheckResult(r.name, "warn",
                            r.detail + " (optional — demo degrades gracefully)",
                            r.fix)
        results.append(r)
    return results


def verdict(results) -> tuple:
    fails = [r for r in results if r.status == "fail"]
    if not fails:
        return "preflight passed", 0
    return (f"{len(fails)} required check(s) failed — "
            f"fix the items marked above", 1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `LUNAR_HEADLESS=1 pytest tests/test_doctor.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/lunar_tools_art/doctor.py tests/test_doctor.py
git commit -m "feat: doctor check framework with injectable probes and exit-code verdicts"
```

---

### Task 4: subprocess hardware probes (mic, camera, audio-out, renderer, midi)

**Files:**
- Create: `src/lunar_tools_art/hardware_probes.py`
- Test: `tests/test_hardware_probes.py`

**Interfaces:**
- Consumes: `CheckResult` from `doctor`.
- Produces: `probe_in_subprocess(snippet: str, name: str, ok_detail: str, fix: str, timeout: float = 5.0) -> CheckResult`; capability probes `probe_mic()`, `probe_camera()`, `probe_audio_out()`, `probe_renderer()`, `probe_midi()`; registers all five into `doctor.DEFAULT_PROBES` at import.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_hardware_probes.py
from lunar_tools_art.hardware_probes import probe_in_subprocess


def test_success_snippet_passes():
    r = probe_in_subprocess("print('2 devices')", "mic", "ok", "fix")
    assert r.status == "pass" and "2 devices" in r.detail


def test_import_error_classified_as_missing_extra():
    r = probe_in_subprocess("import not_a_real_module_xyz", "mic", "ok",
                            "pip install -e '.[hw]'")
    assert r.status == "fail"
    assert "pip install" in r.fix


def test_hang_is_killed_and_classified_as_timeout():
    r = probe_in_subprocess("import time; time.sleep(60)", "camera", "ok",
                            "fix", timeout=1.0)
    assert r.status == "fail" and "timed out" in r.detail


def test_native_crash_is_contained():
    r = probe_in_subprocess("import os; os._exit(139)", "camera", "ok", "fix")
    assert r.status == "fail"       # doctor process survives
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `LUNAR_HEADLESS=1 pytest tests/test_hardware_probes.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement**

```python
# src/lunar_tools_art/hardware_probes.py
"""Device-presence probes, each in a short-lived subprocess with a hard
timeout — native audio/video code can hang or segfault below Python, and
in-process try/except is not containment. Probes print a one-line summary
on success and exit 0; any other outcome is a fail with a classification.
"""
import subprocess
import sys

from . import doctor
from .doctor import CheckResult


def probe_in_subprocess(snippet, name, ok_detail, fix, timeout=5.0):
    try:
        proc = subprocess.run(
            [sys.executable, "-c", snippet],
            capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return CheckResult(name, "fail",
                           f"probe timed out after {timeout:.0f}s "
                           "(device busy or driver hang)", fix)
    if proc.returncode == 0:
        detail = proc.stdout.strip() or ok_detail
        return CheckResult(name, "pass", detail, None)
    err = (proc.stderr or "").strip().splitlines()
    last = err[-1] if err else f"exit code {proc.returncode}"
    if "ModuleNotFoundError" in last or "ImportError" in last:
        return CheckResult(name, "fail", last, fix)
    if "permission" in last.lower() or "denied" in last.lower():
        return CheckResult(name, "fail", f"permission denied: {last}",
                           "grant access in System Settings → Privacy")
    return CheckResult(name, "fail", last, fix)


_HW_FIX = "pip install -e '.[hw]'"

def probe_mic():
    return probe_in_subprocess(
        "import sounddevice as sd;"
        "n=len([d for d in sd.query_devices() if d['max_input_channels']>0]);"
        "assert n, 'no input devices';print(f'{n} input device(s)')",
        "mic", "input device present", _HW_FIX)

def probe_audio_out():
    return probe_in_subprocess(
        "import sounddevice as sd;"
        "n=len([d for d in sd.query_devices() if d['max_output_channels']>0]);"
        "assert n, 'no output devices';print(f'{n} output device(s)')",
        "audio-out", "output device present", _HW_FIX)

def probe_camera():
    return probe_in_subprocess(
        "import cv2;c=cv2.VideoCapture(0);ok=c.isOpened();c.release();"
        "assert ok, 'no camera at index 0';print('camera 0 opens')",
        "camera", "camera present", "pip install -e '.[vision]'", timeout=8.0)

def probe_renderer():
    return probe_in_subprocess(
        "import pyglet;w=pyglet.window.Window(width=64,height=64,visible=False);"
        "w.close();print('display available')",
        "renderer", "display available", _HW_FIX)

def probe_midi():
    return probe_in_subprocess(
        "import mido;names=mido.get_input_names();"
        "print(f'{len(names)} MIDI input(s)' if names else exit('no MIDI inputs'))",
        "midi", "MIDI device present", _HW_FIX)


doctor.DEFAULT_PROBES.update({
    "mic": probe_mic, "audio-out": probe_audio_out, "camera": probe_camera,
    "renderer": probe_renderer, "midi": probe_midi,
})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `LUNAR_HEADLESS=1 pytest tests/test_hardware_probes.py -v`
Expected: 4 passed (these test the wrapper's classification, not hardware presence — they pass on any machine)

- [ ] **Step 5: Commit**

```bash
git add src/lunar_tools_art/hardware_probes.py tests/test_hardware_probes.py
git commit -m "feat: subprocess-isolated hardware presence probes with timeout containment"
```

---

### Task 5: service probes (llm, afterwords, image-gen, network, peer, assets)

**Files:**
- Create: `src/lunar_tools_art/service_probes.py`
- Test: `tests/test_service_probes.py`

**Interfaces:**
- Consumes: `CheckResult`, `doctor.DEFAULT_PROBES`; `config` from `lunar_tools_art.config` (`config.get("llm.provider")`, `config.get("afterwords.server_url")`, `config.get("privacy.mode")`).
- Produces: `probe_llm()`, `probe_afterwords()`, `probe_image_gen()`, `probe_network()`, `probe_peer()`, `make_assets_probe(paths) -> callable`; `_http_ok(url, timeout) -> tuple[bool, str]` (urllib, no new deps). Registers into `DEFAULT_PROBES` (assets probe is built per-demo in the CLI, Task 7).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_service_probes.py
from unittest import mock

from lunar_tools_art import service_probes as sp


def test_llm_probe_checks_ollama_endpoint_when_provider_ollama():
    with mock.patch.object(sp, "_get_cfg",
                           side_effect=lambda k, d=None: {
                               "llm.provider": "ollama",
                               "llm.ollama.base_url": "http://localhost:11434",
                               "llm.ollama.model": "llama3.1:8b"}.get(k, d)), \
         mock.patch.object(sp, "_http_ok", return_value=(False, "refused")):
        r = sp.probe_llm()
    assert r.status == "fail" and "ollama" in r.fix.lower()


def test_llm_probe_checks_provider_specific_key_for_claude():
    with mock.patch.object(sp, "_get_cfg",
                           side_effect=lambda k, d=None:
                           {"llm.provider": "claude"}.get(k, d)), \
         mock.patch.dict("os.environ", {}, clear=True):
        r = sp.probe_llm()
    assert r.status == "fail" and "ANTHROPIC_API_KEY" in r.fix


def test_afterwords_probe_reports_url_and_fix():
    with mock.patch.object(sp, "_get_cfg",
                           side_effect=lambda k, d=None:
                           {"afterwords.server_url": "http://localhost:7860"}.get(k, d)), \
         mock.patch.object(sp, "_http_ok", return_value=(False, "refused")):
        r = sp.probe_afterwords()
    assert r.status == "fail" and "7860" in r.detail and "afterwords" in r.fix


def test_peer_probe_always_warns():
    r = sp.probe_peer()
    assert r.status == "warn" and "second process" in r.detail


def test_assets_probe_lists_missing_files(tmp_path):
    present = tmp_path / "here.mp3"
    present.write_bytes(b"x")
    probe = sp.make_assets_probe([str(present), str(tmp_path / "gone.mp3")])
    r = probe()
    assert r.status == "fail" and "gone.mp3" in r.detail
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `LUNAR_HEADLESS=1 pytest tests/test_service_probes.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement**

```python
# src/lunar_tools_art/service_probes.py
"""Reachability/config probes for services and backends. stdlib only."""
import importlib.util
import os
import urllib.request
from pathlib import Path

from . import doctor
from .doctor import CheckResult

_KEY_BY_PROVIDER = {"claude": "ANTHROPIC_API_KEY",
                    "ollama-cloud": "OLLAMA_CLOUD_API_KEY",
                    "openrouter": "OPENROUTER_API_KEY"}


def _get_cfg(key, default=None):
    from .config import config
    return config.get(key, default)


def _http_ok(url, timeout=3.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status < 500, f"HTTP {resp.status}"
    except Exception as e:
        return False, str(e)


def probe_llm():
    provider = _get_cfg("llm.provider", "ollama")
    if provider == "ollama":
        base = _get_cfg("llm.ollama.base_url", "http://localhost:11434")
        model = _get_cfg("llm.ollama.model", "llama3.1:8b")
        ok, detail = _http_ok(f"{base}/api/tags")
        if not ok:
            return CheckResult("llm", "fail",
                               f"ollama not reachable at {base} ({detail})",
                               "start it: `ollama serve`, then "
                               f"`ollama pull {model}`")
        return CheckResult("llm", "pass", f"ollama at {base}", None)
    if provider == "mlx":
        ok = importlib.util.find_spec("mlx_lm") is not None
        return CheckResult("llm", "pass" if ok else "fail",
                           "mlx-lm importable" if ok else "mlx-lm missing",
                           None if ok else "pip install -e '.[mlx]'")
    key = _KEY_BY_PROVIDER.get(provider)
    if key and not os.environ.get(key):
        return CheckResult("llm", "fail",
                           f"provider '{provider}' needs {key} (not set)",
                           f"set {key} in .env (and privacy.mode=\"cloud-ok\")")
    return CheckResult("llm", "pass", f"provider '{provider}' configured", None)


def probe_afterwords():
    url = _get_cfg("afterwords.server_url", "http://localhost:7860")
    ok, detail = _http_ok(url)
    if not ok:
        return CheckResult("afterwords", "fail",
                           f"no TTS server at {url} ({detail})",
                           "start the afterwords server: "
                           "cd ../afterwords && python server.py")
    return CheckResult("afterwords", "pass", f"server at {url}", None)


def probe_image_gen():
    backend = _get_cfg("image.backend", "mflux")
    if backend == "mflux":
        ok = importlib.util.find_spec("mflux") is not None
        return CheckResult("image-gen", "pass" if ok else "fail",
                           "mflux importable" if ok else "mflux not installed",
                           None if ok else "pip install -e '.[mlx]'")
    return CheckResult("image-gen", "pass", f"backend '{backend}'", None)


def probe_network():
    ok, _ = _http_ok("https://api.github.com", timeout=3.0)
    return CheckResult("network", "pass" if ok else "fail",
                       "internet reachable" if ok else "no internet",
                       None if ok else "check your connection")


def probe_peer():
    return CheckResult("peer", "warn",
                       "this demo needs a second process on another machine "
                       "(ZMQ pair) — cannot be verified from here",
                       "see docs/RUNNING.md § multi-process demos")


def make_assets_probe(paths):
    def probe():
        missing = [p for p in paths if not Path(p).exists()]
        if missing:
            return CheckResult("assets", "fail",
                               "missing file(s): " + ", ".join(missing),
                               "supply the file(s) or point --config at yours")
        return CheckResult("assets", "pass",
                           f"{len(paths)} asset(s) present", None)
    return probe


doctor.DEFAULT_PROBES.update({
    "llm": probe_llm, "afterwords": probe_afterwords,
    "image-gen": probe_image_gen, "network": probe_network,
    "peer": probe_peer,
})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `LUNAR_HEADLESS=1 pytest tests/test_service_probes.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/lunar_tools_art/service_probes.py tests/test_service_probes.py
git commit -m "feat: service/backend probes (provider-aware llm, afterwords, assets, peer)"
```

---

### Task 6: config argument parsing — repeatable `--config`, paren-aware tokenizer

**Files:**
- Create: `src/lunar_tools_art/cli_config.py`
- Test: `tests/test_cli_config.py`

**Interfaces:**
- Consumes: `ConfigKnob` from `demo_registry`.
- Produces: `parse_config_args(values: list[str], knobs: tuple = ()) -> tuple[dict, list[str]]` returning (kwargs, warnings); raises `ConfigParseError(msg)` on malformed input. Handles repeatable `KEY=VALUE` and legacy comma-joined strings; tuples like `window_size=(800,600)` survive.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli_config.py
import pytest

from lunar_tools_art.cli_config import ConfigParseError, parse_config_args
from lunar_tools_art.demo_registry import ConfigKnob


def test_repeatable_key_value():
    kwargs, _ = parse_config_args(["duration=5", "voice=galadriel"])
    assert kwargs == {"duration": 5, "voice": "galadriel"}


def test_legacy_comma_form_still_works():
    kwargs, _ = parse_config_args(["duration=5,rate=1.5"])
    assert kwargs == {"duration": 5, "rate": 1.5}


def test_tuple_value_survives_commas():
    kwargs, _ = parse_config_args(["window_size=(800,600),fps=30"])
    assert kwargs == {"window_size": (800, 600), "fps": 30}


def test_booleans():
    kwargs, _ = parse_config_args(["debug=true,fullscreen=False"])
    assert kwargs == {"debug": True, "fullscreen": False}


def test_entry_without_equals_is_rejected_loudly():
    with pytest.raises(ConfigParseError, match="oops"):
        parse_config_args(["duration=5,oops"])


def test_unknown_key_warns_when_knobs_declared():
    knobs = (ConfigKnob("duration", int, 5, "seconds"),)
    kwargs, warnings = parse_config_args(["duratoin=5"], knobs=knobs)
    assert "duratoin" in warnings[0]


def test_known_key_no_warning():
    knobs = (ConfigKnob("duration", int, 5, "seconds"),)
    _, warnings = parse_config_args(["duration=5"], knobs=knobs)
    assert warnings == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `LUNAR_HEADLESS=1 pytest tests/test_cli_config.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement**

```python
# src/lunar_tools_art/cli_config.py
"""--config parsing. Repeatable KEY=VALUE flags, plus the legacy
comma-joined form with a tokenizer that respects parentheses (the old
parser split on every comma, so tuple values could never parse)."""


class ConfigParseError(ValueError):
    pass


def _split_top_level(s):
    parts, depth, cur = [], 0, []
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def _parse_value(v):
    low = v.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if v.startswith("(") and v.endswith(")"):
        return tuple(_parse_value(x) for x in _split_top_level(v[1:-1]))
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    return v


def parse_config_args(values, knobs=()):
    kwargs, warnings = {}, []
    known = {k.key for k in knobs}
    for raw in values:
        for item in _split_top_level(raw):
            if "=" not in item:
                raise ConfigParseError(
                    f"config entry {item!r} is not KEY=VALUE")
            key, val = item.split("=", 1)
            key = key.strip()
            if known and key not in known:
                warnings.append(
                    f"unknown config key {key!r} for this demo "
                    f"(known: {', '.join(sorted(known))})")
            kwargs[key] = _parse_value(val.strip())
    return kwargs, warnings
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `LUNAR_HEADLESS=1 pytest tests/test_cli_config.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/lunar_tools_art/cli_config.py tests/test_cli_config.py
git commit -m "feat: paren-aware --config parser; tuples finally parse, malformed entries rejected"
```

---

### Task 7: CLI rework — argv normalization, `list` / `doctor` / `run`

**Files:**
- Rewrite: `lunar_tools_demo.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: everything above. `run` imports `prototypes/<module>.py` by path, instantiates `Demo.class_name` (passing the Manager if the constructor wants it — keep the existing `inspect.signature` check), calls `.run()`.
- Produces: `normalize_argv(argv) -> list[str]`; `main(argv=None) -> int` (returns exit code; `sys.exit(main())` at the bottom). `build_parser() -> argparse.ArgumentParser` with global `--debug` and subcommands `list`, `doctor [demo]`, `run <demo> [--config KV]... [--force]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli.py
from unittest import mock

import lunar_tools_demo as cli
from lunar_tools_art.doctor import CheckResult


def test_normalize_legacy_demo_flag():
    assert cli.normalize_argv(["--demo", "whispers", "--config", "x=1"]) == \
        ["run", "whispers", "--config", "x=1"]


def test_normalize_leaves_subcommands_alone():
    assert cli.normalize_argv(["doctor", "whispers"]) == ["doctor", "whispers"]
    assert cli.normalize_argv([]) == ["list"]


def test_list_prints_every_demo_and_exits_zero(capsys):
    assert cli.main(["list"]) == 0
    out = capsys.readouterr().out
    from lunar_tools_art.demo_registry import DEMOS
    for name in DEMOS:
        assert name in out
    assert "headless smoke" in out


def test_unknown_demo_exits_4_with_suggestion(capsys):
    assert cli.main(["run", "whisper"]) == 4      # missing trailing 's'
    err = capsys.readouterr().err
    assert "whispers" in err                      # did-you-mean


def test_run_preflight_failure_exits_3_without_launching(capsys):
    fail = {"mic": lambda: CheckResult("mic", "fail", "no mic", "plug one in")}
    with mock.patch.object(cli, "_probes_for_test", fail), \
         mock.patch.object(cli, "_launch") as launch:
        code = cli.main(["run", "whispers"])
    assert code == 3 and not launch.called
    assert "doctor" in capsys.readouterr().err


def test_run_force_skips_preflight():
    with mock.patch.object(cli, "_launch", return_value=0) as launch:
        code = cli.main(["run", "whispers", "--force"])
    assert code == 0 and launch.called


def test_doctor_all_exits_by_verdict(capsys):
    ok = {"mic": lambda: CheckResult("mic", "pass", "1 device", None)}
    with mock.patch.object(cli, "_probes_for_test", ok):
        assert cli.main(["doctor"]) == 0
    assert "preflight passed" in capsys.readouterr().out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `LUNAR_HEADLESS=1 pytest tests/test_cli.py -v`
Expected: FAIL — `normalize_argv` not defined

- [ ] **Step 3: Rewrite `lunar_tools_demo.py`**

```python
#!/usr/bin/env python3
"""Lunar Tools demo CLI: list, doctor, run."""
import argparse
import difflib
import importlib
import inspect
import logging
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "prototypes"))

from lunar_tools_art.cli_style import make_style
from lunar_tools_art.demo_registry import DEMOS
from lunar_tools_art import doctor as doctor_mod
from lunar_tools_art import hardware_probes, service_probes  # noqa: F401 (register probes)
from lunar_tools_art.cli_config import ConfigParseError, parse_config_args
from lunar_tools_art.service_probes import make_assets_probe

_probes_for_test = None       # tests patch this to inject probes

SUBCOMMANDS = {"list", "doctor", "run"}


def normalize_argv(argv):
    """Rewrite legacy `--demo NAME [rest]` to `run NAME [rest]`; no args -> list."""
    if not argv:
        return ["list"]
    if argv and argv[0] in SUBCOMMANDS:
        return list(argv)
    if "--demo" in argv:
        argv = list(argv)
        i = argv.index("--demo")
        name = argv[i + 1]
        return ["run", name] + argv[:i] + argv[i + 2:]
    return list(argv)


def build_parser():
    p = argparse.ArgumentParser(
        prog="lunar_tools_demo.py",
        description="Interactive audiovisual art installations.",
        epilog=("examples:\n"
                "  python lunar_tools_demo.py list\n"
                "  python lunar_tools_demo.py doctor audio-mirror\n"
                "  python lunar_tools_demo.py run whispers --config duration=5\n"),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--debug", action="store_true",
                   help="show full tracebacks")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="show every demo with requirements and status")
    d = sub.add_parser("doctor", help="preflight checks (all, or one demo's)")
    d.add_argument("demo", nargs="?", default=None)
    r = sub.add_parser("run", help="preflight then launch a demo")
    r.add_argument("demo")
    r.add_argument("--config", action="append", default=[],
                   metavar="KEY=VALUE", help="demo constructor kwargs (repeatable)")
    r.add_argument("--force", action="store_true", help="skip preflight")
    return p


def _resolve(name, style):
    demo = DEMOS.get(name)
    if demo is None:
        matches = difflib.get_close_matches(name, DEMOS, n=3)
        hint = f" — did you mean: {', '.join(matches)}?" if matches else ""
        print(style.styled(f"unknown demo '{name}'{hint}", style.BAD),
              file=sys.stderr)
        print("run `python lunar_tools_demo.py list` to see all demos",
              file=sys.stderr)
    return demo


def _probes_for(demo):
    probes = dict(_probes_for_test if _probes_for_test is not None
                  else doctor_mod.DEFAULT_PROBES)
    if demo is not None and demo.assets:
        probes["assets"] = make_assets_probe(demo.assets)
    return probes


def _print_checks(results, style, stream=sys.stdout):
    for r in results:
        print(style.check_line(r.status, r.name, r.detail, r.fix), file=stream)


def cmd_list(style):
    print(style.header("lunar tools — demos"))
    rows = []
    for d in sorted(DEMOS.values(), key=lambda d: d.name):
        reqs = " ".join(r.capability + ("?" if r.level == "optional" else "")
                        for r in d.requirements)
        rows.append([style.badge("works" if d.status == "works" else "degraded"),
                     d.name, d.description, reqs])
    print(style.table(rows, headers=["", "demo", "description", "needs"]))
    print(style.styled(
        "\nstatus = headless smoke only (construction-level; not verified on "
        "hardware). `doctor <demo>` checks your machine; `run <demo>` launches.",
        style.DIM))
    return 0


def cmd_doctor(name, style):
    demo = _resolve(name, style) if name else None
    if name and demo is None:
        return 4
    print(style.header(f"doctor — {name or 'environment + all capabilities'}"))
    results = doctor_mod.run_checks(demo, probes=_probes_for(demo))
    _print_checks(results, style)
    msg, code = doctor_mod.verdict(results)
    color = style.OK if code == 0 else style.BAD
    print("\n" + style.styled(msg, style.BOLD, color))
    return code


def _launch(demo, kwargs, style):
    from src.lunar_tools_art.manager import Manager   # heavyweight; import late
    module = importlib.import_module(demo.module)
    cls = getattr(module, demo.class_name)
    manager = Manager()
    if "lunar_tools_art_manager" in inspect.signature(cls.__init__).parameters:
        instance = cls(manager, **kwargs)
    else:
        instance = cls(**kwargs)
    instance.run()
    err = getattr(instance, "last_fatal_error", None)   # Task 8 contract
    if err is not None:
        print(style.styled(f"{demo.name} ended with an error: {err}",
                           style.BAD), file=sys.stderr)
        return 1
    return 0


def cmd_run(name, config_values, force, debug, style):
    demo = _resolve(name, style)
    if demo is None:
        return 4
    try:
        kwargs, warnings = parse_config_args(config_values, demo.config_knobs)
    except ConfigParseError as e:
        print(style.styled(str(e), style.BAD), file=sys.stderr)
        return 2
    for w in warnings:
        print(style.styled(w, style.WARN), file=sys.stderr)
    if not force:
        results = doctor_mod.run_checks(demo, probes=_probes_for(demo))
        msg, code = doctor_mod.verdict(results)
        if code != 0:
            _print_checks(results, style, stream=sys.stderr)
            print(style.styled(
                f"\npreflight failed — fix the above, see `doctor {name}`, "
                "or rerun with --force", style.BOLD, style.BAD),
                file=sys.stderr)
            return 3
    try:
        return _launch(demo, kwargs, style)
    except Exception as e:
        if debug:
            raise
        print(style.styled(f"{demo.name} crashed: {e}", style.BAD),
              file=sys.stderr)
        print("rerun with --debug for the full traceback", file=sys.stderr)
        return 1


def main(argv=None):
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    args = build_parser().parse_args(
        normalize_argv(sys.argv[1:] if argv is None else argv))
    style = make_style()
    if args.command == "list":
        return cmd_list(style)
    if args.command == "doctor":
        return cmd_doctor(args.demo, style)
    return cmd_run(args.demo, args.config, args.force, args.debug, style)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the new tests, then the whole suite**

Run: `LUNAR_HEADLESS=1 pytest tests/test_cli.py -v` → 7 passed
Run: `LUNAR_HEADLESS=1 pytest -q` → no regressions (old CLI tests, if any reference `--demo`, must still pass via normalization; update any that assert on removed internals like `_discover_demos`)

- [ ] **Step 5: Manual smoke of the art**

Run: `python lunar_tools_demo.py` and `python lunar_tools_demo.py doctor` in a real terminal. Verify: lunar header, aligned table, badges, colors; then `NO_COLOR=1 python lunar_tools_demo.py list` is clean plain text.

- [ ] **Step 6: Commit**

```bash
git add lunar_tools_demo.py tests/test_cli.py
git commit -m "feat: rework CLI — list/doctor/run subcommands, legacy --demo preserved, styled output"
```

---

### Task 8: `PrototypeBase.run()` result contract

**Files:**
- Modify: `src/lunar_tools_art/prototype_base.py` (the `run()` exception handler, ~line 147)
- Test: `tests/test_prototype_base_result.py`

**Interfaces:**
- Produces: `PrototypeBase.last_fatal_error: Exception | None` — set when `run()`'s catch-all absorbs an exception, `None` on clean exit. Consumed by `_launch` in Task 7 (already written against this name).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_prototype_base_result.py
from lunar_tools_art.prototype_base import PrototypeBase


class Exploding(PrototypeBase):
    def setup(self):
        raise RuntimeError("boom at setup")

    def update(self):
        pass


class Clean(PrototypeBase):
    def setup(self):
        pass

    def update(self):
        self._running = False


def _mgr():
    class M:
        main_queue = None
    return M()


def test_fatal_exception_recorded():
    p = Exploding(_mgr())
    p.run()
    assert isinstance(p.last_fatal_error, RuntimeError)
    assert "boom at setup" in str(p.last_fatal_error)


def test_clean_exit_leaves_no_error():
    p = Clean(_mgr())
    p.run()
    assert p.last_fatal_error is None
```

(Adjust the minimal-subclass constructor to whatever `PrototypeBase.__init__`
actually requires — read the class first; if it needs a fuller manager, use
the existing test fixtures in `tests/` for PrototypeBase subclasses.)

- [ ] **Step 2: Run test to verify it fails**

Run: `LUNAR_HEADLESS=1 pytest tests/test_prototype_base_result.py -v`
Expected: FAIL — `last_fatal_error` attribute missing

- [ ] **Step 3: Implement**

In `PrototypeBase.__init__`, add `self.last_fatal_error = None`. At the top
of `run()`, reset it to `None`. In the existing `except Exception as e:`
block that logs and swallows, add `self.last_fatal_error = e` before the
logging call. No other behavior changes — cleanup still runs, `run()` still
returns normally.

- [ ] **Step 4: Run test + full suite**

Run: `LUNAR_HEADLESS=1 pytest tests/test_prototype_base_result.py -v` → 2 passed
Run: `LUNAR_HEADLESS=1 pytest -q` → green

- [ ] **Step 5: Commit**

```bash
git add src/lunar_tools_art/prototype_base.py tests/test_prototype_base_result.py
git commit -m "feat: PrototypeBase records fatal exceptions so the CLI can report honest exit codes"
```

---

### Task 9: docs — RUNNING.md, README, CLAUDE.md

**Files:**
- Create: `docs/RUNNING.md`
- Modify: `README.md` (Quickstart + "Run a demo" sections), `CLAUDE.md` (Running Prototypes section, `--config` example, test counts)

**Interfaces:**
- Consumes: final CLI behavior from Task 7 (verify every command you document by running it first).

- [ ] **Step 1: Verify the zero-hardware claim before writing it**

Run: `LUNAR_HEADLESS=1 timeout 20 python lunar_tools_demo.py run whispers --force` (and try `cosmic-soundscape` if whispers doesn't exit cleanly; pick a demo that runs and exits/loops harmlessly headless). Whichever demo you verify is the one named in the docs. If a demo loops forever, note that ESC/Q or Ctrl-C exits and document that.

- [ ] **Step 2: Write `docs/RUNNING.md`**

Structure (write real content for each, sourced from the registry and the
verified commands):

```markdown
# Running the Installations

## The three commands
list / doctor / run — with real output samples pasted from your terminal.

## Zero-hardware first run
LUNAR_HEADLESS=1 python lunar_tools_demo.py run <verified-demo> --force

## What each demo needs
A table generated from demo_registry (name, description, required, optional,
assets) — paste the actual `list` output or mirror it in markdown.

## Setting up the pieces
- Microphone & camera: macOS privacy permissions, picking devices
- Afterwords TTS: clone ../afterwords, start server, default port 7860
- Ollama: install, `ollama serve`, `ollama pull llama3.1:8b`
- Cloud providers: privacy.mode="cloud-ok" + the provider-specific key
- MIDI: any class-compliant controller; doctor shows what's detected

## Multi-process demos
collaborative-canvas / collaborative-art need a peer; how to run both halves.

## Troubleshooting
A table keyed by doctor check name (mic, camera, renderer, llm, afterwords,
image-gen, assets, ...) with the failure detail the doctor prints and the fix.
```

- [ ] **Step 3: Update README.md**

Replace the "Run a demo" block with the `list` → `doctor` → `run` flow, link
`docs/RUNNING.md`, and fix the false claim that `--help` lists demos.

- [ ] **Step 4: Update CLAUDE.md**

- Replace the `--config "{'mic_device': ...}"` example (wrong syntax, wrong
  demo name, nonexistent keys) with a real one, e.g.
  `python lunar_tools_demo.py run whispers --config duration=5`.
- Fix "List available demos by running without args" → now true; say `list`.
- Reconcile the 197-vs-199 test count (use the number the suite actually
  reports after this work).
- Document the new subcommands and registry/doctor modules briefly.

- [ ] **Step 5: Verify every documented command**

Run each command exactly as written in the three docs; they must all work.

- [ ] **Step 6: Commit**

```bash
git add docs/RUNNING.md README.md CLAUDE.md
git commit -m "docs: RUNNING.md runbook; README/CLAUDE.md match the real CLI"
```

---

### Task 10: final verification

- [ ] **Step 1: Full suite**

Run: `LUNAR_HEADLESS=1 pytest -q`
Expected: all green (baseline 199 + ~35 new)

- [ ] **Step 2: Cold-clone rehearsal**

From a fresh shell in the repo root:

```bash
python lunar_tools_demo.py                      # list, styled
python lunar_tools_demo.py doctor               # full preflight, honest fixes
python lunar_tools_demo.py doctor audio-mirror  # scoped
python lunar_tools_demo.py --demo whispers --config duration=2  # legacy path
NO_COLOR=1 python lunar_tools_demo.py list      # plain text
python lunar_tools_demo.py run nope             # exit 4 + did-you-mean
```

Check each exit code with `echo $?` against the Global Constraints table.

- [ ] **Step 3: Pre-commit + push**

```bash
pre-commit run --all-files
```

Then follow the finishing-a-development-branch skill (branch → PR → merge per repo convention).
