from lunar_tools_art.demo_registry import Demo, Requirement
from lunar_tools_art.doctor import CheckResult, run_checks, verdict


def _demo(*reqs):
    return Demo(
        "t",
        "t",
        "T",
        "test demo",
        requirements=tuple(Requirement(c, lvl) for c, lvl in reqs),
    )


def ok(name):
    return lambda: CheckResult(name, "pass", "present", None)


def bad(name, fix="do the thing"):
    return lambda: CheckResult(name, "fail", "absent", fix)


def test_demo_scoped_checks_only_probe_declared_capabilities():
    calls = []
    probes = {
        "mic": lambda: (calls.append("mic"), ok("mic")())[1],
        "camera": lambda: (calls.append("camera"), ok("camera")())[1],
    }
    run_checks(_demo(("mic", "required")), probes=probes)
    assert calls == ["mic"]


def test_optional_failure_becomes_warn_not_fail():
    res = run_checks(
        _demo(("afterwords", "optional")),
        probes={"afterwords": bad("afterwords")},
    )
    (r,) = [x for x in res if x.name == "afterwords"]
    assert r.status == "warn"


def test_verdict_exit_codes():
    passing = [CheckResult("a", "pass", "", None)]
    warned = passing + [CheckResult("b", "warn", "", None)]
    failed = warned + [CheckResult("c", "fail", "", "fix it")]
    assert verdict(passing) == ("preflight passed", 0)
    assert verdict(warned)[1] == 0  # warnings don't fail preflight
    assert "preflight passed" in verdict(warned)[0]
    msg, code = verdict(failed)
    assert code == 1 and "preflight passed" not in msg


def test_probe_exception_is_a_fail_not_a_crash():
    def boom():
        raise RuntimeError("device exploded")

    (r,) = [
        x
        for x in run_checks(_demo(("midi", "required")), probes={"midi": boom})
        if x.name == "midi"
    ]
    assert r.status == "fail" and "device exploded" in r.detail


def test_full_doctor_includes_environment_checks():
    names = {r.name for r in run_checks(None, probes={})}
    assert {"python", "settings", "headless"} <= names
