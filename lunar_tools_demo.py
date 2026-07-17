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

from lunar_tools_art import doctor as doctor_mod
from lunar_tools_art import hardware_probes, service_probes  # noqa: F401
from lunar_tools_art.cli_config import ConfigParseError, parse_config_args
from lunar_tools_art.cli_style import make_style
from lunar_tools_art.demo_registry import DEMOS
from lunar_tools_art.service_probes import make_assets_probe

_probes_for_test = None  # tests patch this to inject probes

SUBCOMMANDS = {"list", "doctor", "run"}


def normalize_argv(argv):
    """Rewrite legacy `--demo NAME [rest]` to `run NAME [rest]`.

    No args -> list. Anything already starting with a subcommand (or -h)
    passes through untouched.
    """
    if not argv:
        return ["list"]
    if argv[0] in SUBCOMMANDS or argv[0] in ("-h", "--help"):
        return list(argv)
    if "--demo" in argv:
        argv = list(argv)
        i = argv.index("--demo")
        name = argv[i + 1]
        return ["run", name] + argv[:i] + argv[i + 2 :]
    return list(argv)


def build_parser():
    p = argparse.ArgumentParser(
        prog="lunar_tools_demo.py",
        description="Interactive audiovisual art installations.",
        epilog=(
            "examples:\n"
            "  python lunar_tools_demo.py list\n"
            "  python lunar_tools_demo.py doctor audio-mirror\n"
            "  python lunar_tools_demo.py run whispers --config duration=5\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--debug", action="store_true", help="show full tracebacks")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="show every demo with requirements and status")
    d = sub.add_parser("doctor", help="preflight checks (all, or one demo's)")
    d.add_argument("demo", nargs="?", default=None)
    r = sub.add_parser("run", help="preflight then launch a demo")
    r.add_argument("demo")
    r.add_argument(
        "--config",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="demo constructor kwargs (repeatable)",
    )
    r.add_argument("--force", action="store_true", help="skip preflight checks")
    r.add_argument("--debug", action="store_true", help="show full tracebacks")
    return p


def _resolve(name, style):
    demo = DEMOS.get(name)
    if demo is None:
        matches = difflib.get_close_matches(name, DEMOS, n=3)
        hint = f" — did you mean: {', '.join(matches)}?" if matches else ""
        print(
            style.styled(f"unknown demo '{name}'{hint}", style.BAD),
            file=sys.stderr,
        )
        print(
            "run `python lunar_tools_demo.py list` to see all demos",
            file=sys.stderr,
        )
    return demo


def _probes_for(demo):
    probes = dict(
        _probes_for_test if _probes_for_test is not None else doctor_mod.DEFAULT_PROBES
    )
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
        reqs = " ".join(
            r.capability + ("?" if r.level == "optional" else "")
            for r in d.requirements
        )
        rows.append(
            [
                style.badge("works" if d.status == "works" else "degraded"),
                d.name,
                d.description,
                reqs,
            ]
        )
    print(style.table(rows, headers=["", "demo", "description", "needs"]))
    print(
        style.styled(
            "\nstatus = headless smoke only (construction-level; not "
            "verified on hardware). `doctor <demo>` checks your machine; "
            "`run <demo>` launches. `?` marks optional capabilities.",
            style.DIM,
        )
    )
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
    from lunar_tools_art.manager import Manager  # heavyweight; import late

    module = importlib.import_module(demo.module)
    cls = getattr(module, demo.class_name)
    manager = Manager()
    if "lunar_tools_art_manager" in inspect.signature(cls.__init__).parameters:
        instance = cls(manager, **kwargs)
    else:
        instance = cls(**kwargs)
    instance.run()
    err = getattr(instance, "last_fatal_error", None)
    if err is not None:
        print(
            style.styled(f"{demo.name} ended with an error: {err}", style.BAD),
            file=sys.stderr,
        )
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
            print(
                style.styled(
                    f"\npreflight failed — fix the above, see `doctor "
                    f"{name}`, or rerun with --force",
                    style.BOLD,
                    style.BAD,
                ),
                file=sys.stderr,
            )
            return 3
    try:
        return _launch(demo, kwargs, style)
    except Exception as e:
        if debug:
            raise
        print(
            style.styled(f"{demo.name} crashed: {e}", style.BAD),
            file=sys.stderr,
        )
        print("rerun with --debug for the full traceback", file=sys.stderr)
        return 1


def main(argv=None):
    args = build_parser().parse_args(
        normalize_argv(sys.argv[1:] if argv is None else argv)
    )
    debug = getattr(args, "debug", False)
    logging.basicConfig(
        level=logging.INFO if args.command == "run" or debug else logging.WARNING,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logging.getLogger("lunar_tools_art.config").setLevel(
        logging.INFO if debug else logging.WARNING
    )
    style = make_style()
    if args.command == "list":
        return cmd_list(style)
    if args.command == "doctor":
        return cmd_doctor(args.demo, style)
    return cmd_run(
        args.demo, args.config, args.force, getattr(args, "debug", False), style
    )


if __name__ == "__main__":
    sys.exit(main())
