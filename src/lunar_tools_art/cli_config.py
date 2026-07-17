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
                raise ConfigParseError(f"config entry {item!r} is not KEY=VALUE")
            key, val = item.split("=", 1)
            key = key.strip()
            if known and key not in known:
                warnings.append(
                    f"unknown config key {key!r} for this demo "
                    f"(known: {', '.join(sorted(known))})"
                )
            kwargs[key] = _parse_value(val.strip())
    return kwargs, warnings
