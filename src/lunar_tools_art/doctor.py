"""Preflight checks. Probes the real environment — never headless fakes.

Each registry capability maps to a probe callable returning a CheckResult.
Tests inject probe dicts; the real DEFAULT_PROBES are registered by the
probe modules (hardware_probes, service_probes) at import time.
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str  # pass | fail | warn
    detail: str
    fix: str | None


DEFAULT_PROBES: dict = {}  # capability -> callable() -> CheckResult


def _environment_checks() -> list:
    py_ok = sys.version_info >= (3, 10)
    results = [
        CheckResult(
            "python",
            "pass" if py_ok else "fail",
            f"{sys.version_info.major}.{sys.version_info.minor} " f"on {sys.platform}",
            None if py_ok else "install Python 3.10+",
        )
    ]
    settings = Path.cwd() / "settings.toml"
    results.append(
        CheckResult(
            "settings",
            "pass" if settings.exists() else "warn",
            (
                f"reading {settings}"
                if settings.exists()
                else f"no settings.toml in {Path.cwd()} — using built-in defaults"
            ),
            None if settings.exists() else "run from the repository root",
        )
    )
    headless = os.environ.get("LUNAR_HEADLESS") == "1"
    results.append(
        CheckResult(
            "headless",
            "warn" if headless else "pass",
            (
                "LUNAR_HEADLESS=1 — all tools are fakes; demos will not touch "
                "hardware"
                if headless
                else "real hardware mode"
            ),
            "unset LUNAR_HEADLESS to use real devices" if headless else None,
        )
    )
    return results


class _AllRequired:
    __slots__ = ("capability", "level")

    def __init__(self, capability):
        self.capability = capability
        self.level = "required"


def run_checks(demo=None, probes=None) -> list:
    probes = DEFAULT_PROBES if probes is None else probes
    results = _environment_checks()
    reqs = demo.requirements if demo else [_AllRequired(c) for c in sorted(probes)]
    for req in reqs:
        probe = probes.get(req.capability)
        if probe is None:
            continue
        try:
            r = probe()
        except Exception as e:  # probe bugs must not kill doctor
            r = CheckResult(req.capability, "fail", str(e), None)
        if req.level == "optional" and r.status == "fail":
            r = CheckResult(
                r.name,
                "warn",
                r.detail + " (optional — demo degrades gracefully)",
                r.fix,
            )
        results.append(r)
    return results


def verdict(results) -> tuple:
    fails = [r for r in results if r.status == "fail"]
    if not fails:
        return "preflight passed", 0
    return (
        f"{len(fails)} required check(s) failed — fix the items marked above",
        1,
    )
