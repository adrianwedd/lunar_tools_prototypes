from unittest import mock

import lunar_tools_demo as cli
from lunar_tools_art.doctor import CheckResult


def test_normalize_legacy_demo_flag():
    assert cli.normalize_argv(["--demo", "whispers", "--config", "x=1"]) == [
        "run",
        "whispers",
        "--config",
        "x=1",
    ]


def test_normalize_leaves_subcommands_alone():
    assert cli.normalize_argv(["doctor", "whispers"]) == [
        "doctor",
        "whispers",
    ]
    assert cli.normalize_argv([]) == ["list"]


def test_list_prints_every_demo_and_exits_zero(capsys):
    assert cli.main(["list"]) == 0
    out = capsys.readouterr().out
    from lunar_tools_art.demo_registry import DEMOS

    for name in DEMOS:
        assert name in out
    assert "headless smoke" in out


def test_unknown_demo_exits_4_with_suggestion(capsys):
    assert cli.main(["run", "whisper"]) == 4  # missing trailing 's'
    err = capsys.readouterr().err
    assert "whispers" in err  # did-you-mean


def test_run_preflight_failure_exits_3_without_launching(capsys):
    fail = {"mic": lambda: CheckResult("mic", "fail", "no mic", "plug one in")}
    with (
        mock.patch.object(cli, "_probes_for_test", fail),
        mock.patch.object(cli, "_launch") as launch,
    ):
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


def test_malformed_config_exits_2(capsys):
    with mock.patch.object(cli, "_probes_for_test", {}):
        code = cli.main(["run", "whispers", "--config", "nonsense"])
    assert code == 2
