"""Reachability/config probes for services and backends. stdlib only."""

import importlib.util
import os
import urllib.request
from pathlib import Path

from . import doctor
from .doctor import CheckResult

_KEY_BY_PROVIDER = {
    "claude": "ANTHROPIC_API_KEY",
    "ollama-cloud": "OLLAMA_CLOUD_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def _get_cfg(key, default=None):
    from .config import config

    return config.get(key, default)


def _http_ok(url, timeout=3.0):
    try:
        with urllib.request.urlopen(
            url, timeout=timeout
        ) as resp:  # nosec B310 - config-sourced http(s) health check
            return resp.status < 500, f"HTTP {resp.status}"
    except Exception as e:
        return False, str(e)


def probe_llm():
    provider = _get_cfg("llm.provider", "ollama")
    if provider == "ollama":
        base = _get_cfg("llm.ollama.base_url", "http://localhost:11434")
        model = _get_cfg("llm.ollama.model", "llama3.1:8b")
        ok, detail = _http_ok(f"{base}/api/tags")
        if not ok:
            return CheckResult(
                "llm",
                "fail",
                f"ollama not reachable at {base} ({detail})",
                f"start it: `ollama serve`, then `ollama pull {model}`",
            )
        return CheckResult("llm", "pass", f"ollama at {base}", None)
    if provider == "mlx":
        ok = importlib.util.find_spec("mlx_lm") is not None
        return CheckResult(
            "llm",
            "pass" if ok else "fail",
            "mlx-lm importable" if ok else "mlx-lm missing",
            None if ok else "pip install -e '.[mlx]'",
        )
    key = _KEY_BY_PROVIDER.get(provider)
    if key and not os.environ.get(key):
        return CheckResult(
            "llm",
            "fail",
            f"provider '{provider}' needs {key} (not set)",
            f'set {key} in .env (and privacy.mode="cloud-ok")',
        )
    return CheckResult("llm", "pass", f"provider '{provider}' configured", None)


def probe_afterwords():
    url = _get_cfg("afterwords.server_url", "http://localhost:7860")
    # /health is the server's status route; the bare root 404s on FastAPI
    ok, detail = _http_ok(f"{url.rstrip('/')}/health")
    if not ok:
        return CheckResult(
            "afterwords",
            "fail",
            f"no TTS server at {url} ({detail})",
            "start the afterwords server: cd ../afterwords && python server.py",
        )
    return CheckResult("afterwords", "pass", f"server at {url}", None)


def probe_image_gen():
    backend = _get_cfg("image.backend", "mflux")
    if backend == "mflux":
        if importlib.util.find_spec("mflux") is None:
            return CheckResult(
                "image-gen", "fail", "mflux not installed",
                "pip install -e '.[mlx]'",
            )
        # Import only: never load the model in a preflight probe.
        try:
            from .tools.images import ImageGenerator, mflux_weights_status

            gen = ImageGenerator(
                backend="mflux",
                model=str(_get_cfg("image.model", "schnell")),
                quantize=int(_get_cfg("image.quantize", 4)),
            )
            identity = gen.identity()
        except Exception as e:
            return CheckResult(
                "image-gen", "fail",
                f"mflux adapter incompatible with installed mflux: {e}",
                "repair the adapter for the installed mflux API",
            )
        ready, detail = mflux_weights_status(identity)
        return CheckResult(
            "image-gen",
            "pass" if ready else "fail",
            detail,
            None if ready else "download the model weights (hf download <repo>)",
        )
    return CheckResult("image-gen", "pass", f"backend '{backend}'", None)


def probe_network():
    ok, _ = _http_ok("https://api.github.com", timeout=3.0)
    return CheckResult(
        "network",
        "pass" if ok else "fail",
        "internet reachable" if ok else "no internet",
        None if ok else "check your connection",
    )


def probe_peer():
    return CheckResult(
        "peer",
        "warn",
        "this demo needs a second process on another machine (ZMQ pair) — "
        "cannot be verified from here",
        "see docs/RUNNING.md § multi-process demos",
    )


def make_assets_probe(paths):
    def probe():
        missing = [p for p in paths if not Path(p).exists()]
        if missing:
            return CheckResult(
                "assets",
                "fail",
                "missing file(s): " + ", ".join(missing),
                "supply the file(s) or point --config at yours",
            )
        return CheckResult("assets", "pass", f"{len(paths)} asset(s) present", None)

    return probe


doctor.DEFAULT_PROBES.update(
    {
        "llm": probe_llm,
        "afterwords": probe_afterwords,
        "image-gen": probe_image_gen,
        "network": probe_network,
        "peer": probe_peer,
    }
)
