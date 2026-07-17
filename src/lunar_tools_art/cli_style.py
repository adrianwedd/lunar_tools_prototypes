"""Hand-rolled terminal styling for the demo CLI. Zero dependencies.

One visual grammar for list/doctor/run/errors: a small palette, unicode
badges with ASCII fallbacks, aligned tables, and a lunar header. Color and
unicode degrade independently: NO_COLOR / non-TTY kill color, TERM=dumb
kills both.
"""

import os
import sys

_BADGES_UNICODE = {
    "pass": "✓",  # nosec B105 - check-status badge, not a password
    "fail": "✗",
    "warn": "⚠",
    "works": "●",
    "degraded": "◐",
    "missing": "○",
}
_BADGES_ASCII = {
    "pass": "OK",  # nosec B105 - check-status badge, not a password
    "fail": "XX",
    "warn": "!!",
    "works": "*",
    "degraded": "~",
    "missing": "-",
}


class Style:
    RESET = "0"
    BOLD = "1"
    DIM = "2"
    MOON = "38;5;153"  # pale lunar blue — headers, demo names
    OK = "38;5;114"  # soft green
    BAD = "38;5;210"  # soft red
    WARN = "38;5;222"  # soft amber

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
        return "\n".join(
            [
                self.styled(line, self.BOLD, self.MOON),
                self.styled(rule, self.DIM),
            ]
        )

    def table(self, rows, headers) -> str:
        widths = [
            max(len(str(c)) for c in col) for col in zip(headers, *rows, strict=False)
        ]

        def fmt(cells, *codes):
            return "  ".join(
                self.styled(str(c).ljust(w), *codes)
                for c, w in zip(cells, widths, strict=False)
            ).rstrip()

        out = [fmt(headers, self.BOLD)]
        out += [fmt(r) for r in rows]
        return "\n".join(out)

    def check_line(
        self, status: str, name: str, detail: str, fix: str | None = None
    ) -> str:
        color = {"pass": self.OK, "fail": self.BAD, "warn": self.WARN}[status]
        line = (
            f"  {self.styled(self.badge(status), color)} "
            f"{self.styled(name.ljust(14), self.BOLD)} {detail}"
        )
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
