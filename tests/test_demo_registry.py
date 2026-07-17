import ast
from pathlib import Path

from lunar_tools_art.demo_registry import (
    CAPABILITIES,
    DEMOS,
    EXCLUDED_MODULES,
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
            f"(has {classes})"
        )


def test_requirement_vocabulary_and_levels():
    for d in DEMOS.values():
        for r in d.requirements:
            assert r.capability in CAPABILITIES, (d.name, r.capability)
            assert r.level in ("required", "optional")


def test_config_knobs_match_init_params():
    for d in DEMOS.values():
        tree = ast.parse((PROTO / f"{d.module}.py").read_text())
        cls = next(
            n
            for n in tree.body
            if isinstance(n, ast.ClassDef) and n.name == d.class_name
        )
        init = next(
            (
                n
                for n in cls.body
                if isinstance(n, ast.FunctionDef) and n.name == "__init__"
            ),
            None,
        )
        params = (
            {a.arg for a in init.args.args} | {a.arg for a in init.args.kwonlyargs}
            if init
            else set()
        )
        for knob in d.config_knobs:
            assert knob.key in params, (
                f"{d.name}: knob {knob.key} not an __init__ param of "
                f"{d.class_name} ({sorted(params)})"
            )


def test_descriptions_are_single_line_and_nonempty():
    for d in DEMOS.values():
        assert d.description and "\n" not in d.description


def test_assets_demos_declare_assets_capability():
    for d in DEMOS.values():
        caps = {r.capability for r in d.requirements}
        assert bool(d.assets) == ("assets" in caps), d.name
