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
    env = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "TERM")}
    with mock.patch.dict(os.environ, env, clear=True):
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
    line = s.check_line(
        "fail",
        "afterwords",
        "server unreachable",
        fix="cd ../afterwords && python server.py",
    )
    assert "XX" in line and "afterwords" in line
    assert "cd ../afterwords" in line
