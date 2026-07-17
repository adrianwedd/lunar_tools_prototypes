from lunar_tools_art.hardware_probes import probe_in_subprocess


def test_success_snippet_passes():
    r = probe_in_subprocess("print('2 devices')", "mic", "ok", "fix")
    assert r.status == "pass" and "2 devices" in r.detail


def test_import_error_classified_as_missing_extra():
    r = probe_in_subprocess(
        "import not_a_real_module_xyz", "mic", "ok", "pip install -e '.[hw]'"
    )
    assert r.status == "fail"
    assert "pip install" in r.fix


def test_hang_is_killed_and_classified_as_timeout():
    r = probe_in_subprocess(
        "import time; time.sleep(60)", "camera", "ok", "fix", timeout=1.0
    )
    assert r.status == "fail" and "timed out" in r.detail


def test_native_crash_is_contained():
    r = probe_in_subprocess("import os; os._exit(139)", "camera", "ok", "fix")
    assert r.status == "fail"  # doctor process survives
