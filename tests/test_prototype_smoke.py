"""Automated smoke matrix over every prototype in `prototypes/`.

Runs headless against the shared `headless_manager` fixture. Two prototype
styles are handled:

- `PrototypeBase` subclasses (expose `setup`/`update`/`cleanup`): run a
  bounded number of update-loop iterations via a patched `should_exit`.
- Legacy manual-`run()` prototypes: construction without error is the smoke
  bar (matching the existing `tests/test_lunar_tools_art.py` convention).

Known-broken prototypes are marked `xfail` with a reason; see
`PROTOTYPE_STATUS.md` for the full status matrix.
"""

import importlib.util
import itertools
import pathlib

import pytest

PROTO_DIR = pathlib.Path(__file__).parent.parent / "prototypes"
SKIP = {
    "__init__.py",
    "example_base_usage.py",
    "audio_mirror.py",
    "ai-mirror-of-truth.py",
}
FILES = sorted(p for p in PROTO_DIR.glob("*.py") if p.name not in SKIP)

# Known-broken prototypes (from earlier QA / this sweep). Keep in sync with
# PROTOTYPE_STATUS.md.
XFAIL_REASONS = {
    "cosmic-soundscape.py": (
        "stub file — only a title comment, no class/implementation exists; "
        "needs-rework (never implemented)"
    ),
    "acoustic-fingerprint-painter.py": (
        "writes a temp WAV via a stubbed AudioRecorder.stop_recording() and "
        "then feeds a None/invalid path into json.loads-style parsing under "
        "the headless fake recorder; needs-rework, not a test issue"
    ),
    "time-shifted-echo-chamber.py": (
        "requires api_keys.openweathermap in settings.toml which is not "
        "configured in this environment; needs-rework"
    ),
    "data-driven-cityscape.py": (
        "requires api_keys.openweathermap in settings.toml which is not "
        "configured in this environment; needs-rework"
    ),
    "chat-room-narrative-quilt.py": (
        "references undefined self.l (typo/dead code) during construction; "
        "needs-rework"
    ),
    "escape_room.py": (
        "calls .strip() directly on gpt4.generate()'s return value without a "
        "None guard; under LUNAR_HEADLESS the fake Speech2Text returns a "
        "truthy transcript, driving that code path when the LLM backend is "
        "unavailable (stub-era code, not a test issue)"
    ),
    "virtual_time_travel.py": (
        "calls .strip() directly on gpt4.generate()'s return value without a "
        "None guard; under LUNAR_HEADLESS the fake Speech2Text returns a "
        "truthy transcript, driving that code path when the LLM backend is "
        "unavailable (stub-era code, not a test issue)"
    ),
}


def load(path):
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def find_class(mod):
    """Pick the prototype's main class out of a module.

    Modules commonly define small helper classes (e.g. `Particle`) ahead of
    the main installation class, and helpers sometimes have their own
    `update()` method (particle-system style code). Prefer classes exposing
    `run()` (the manual-loop convention used across these prototypes); among
    ties, or if none has `run`, take the last class defined in the module
    (main classes are conventionally declared last).
    """
    candidates = [
        v
        for v in vars(mod).values()
        if isinstance(v, type)
        and v.__module__ == mod.__name__
        and (hasattr(v, "run") or hasattr(v, "update"))
    ]
    assert candidates, f"no prototype class found in {mod.__name__}"
    with_run = [c for c in candidates if hasattr(c, "run")]
    return (with_run or candidates)[-1]


def _xfail_id(path):
    return path.name


@pytest.mark.parametrize("path", FILES, ids=_xfail_id)
def test_prototype_smoke(path, headless_manager, monkeypatch):
    if path.name in XFAIL_REASONS:
        pytest.xfail(XFAIL_REASONS[path.name])

    mod = load(path)
    cls = find_class(mod)
    proto = cls(headless_manager)
    if hasattr(proto, "setup") and hasattr(proto, "update"):
        counter = itertools.count()
        if hasattr(proto, "should_exit"):
            monkeypatch.setattr(proto, "should_exit", lambda: next(counter) >= 3)
        proto.setup()
        for _ in range(3):
            proto.update()
        proto.cleanup()
    # legacy manual-run prototypes: construction without error is the smoke bar
