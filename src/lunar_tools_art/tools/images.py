"""Unified image generation: local mflux (default) plus gated cloud backends.

Backends:
  - ``fake``: a 1x1 PIL PNG; used in headless mode / tests, no dependencies.
  - ``mflux``: local Flux.1 inference via the ``mflux`` package (MLX-native,
    Apple Silicon). Imported lazily so importing this module never touches
    mflux, and so tests can inject a fake module via ``sys.modules``.
    Inference runs under ``INFERENCE_LOCK`` to bound unified-memory pressure
    alongside the LLM/STT/TTS stacks.
  - ``openai``: DALL-E via the OpenAI API. Requires ``privacy.cloud_allowed()``.
  - ``replicate``: Replicate-hosted models (SDXL, etc.) via HTTP. Requires
    ``privacy.cloud_allowed()``.

Every backend's ``generate()`` returns ``(local_png_path, metadata_dict)``,
matching the contract 14 legacy prototypes already unpack as
``image, _ = ...generate(...)``.
"""

import logging
import os
import shutil
import threading
import time
import warnings
from pathlib import Path

from .. import privacy
from ..exceptions import InferenceError
from ..inference_gate import INFERENCE_LOCK
from ..utils import create_secure_temp_file

logger = logging.getLogger(__name__)


def _flux1_class():
    """Import seam for mflux's txt2img class (patched in tests)."""
    from mflux.models.flux.variants.txt2img.flux import Flux1

    return Flux1


def _model_config(model_name):
    """Import seam for mflux's model registry (patched in tests)."""
    from mflux.models.common.config import ModelConfig

    return ModelConfig.from_name(model_name)


def _hf_snapshot_revision(repo_id: str) -> str | None:
    """Return the commit hash the local Hugging Face cache has pinned.

    Uses ``refs/main`` (what mflux/huggingface_hub resolve) rather than the
    snapshot directory name, so the value is the revision actually loaded.
    Returns ``None`` when the repo is not cached on this machine.
    """
    try:
        from huggingface_hub.constants import HF_HUB_CACHE

        repo_dir = os.path.join(HF_HUB_CACHE, "models--" + repo_id.replace("/", "--"))
        ref = os.path.join(repo_dir, "refs", "main")
        if not os.path.exists(ref):
            return None
        with open(ref, "r", encoding="utf-8") as fh:
            value = fh.read().strip()
        return value or None
    except Exception:
        return None


def _identity_digest(identity: dict | None) -> str:
    """Stable, short digest of a generation identity for cache keys."""
    import hashlib
    import json

    if not identity:
        return "noidentity"
    blob = json.dumps(identity, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def mflux_snapshot_path(model: str = "schnell") -> str | None:
    """Absolute path to the cached mflux snapshot, or None when absent."""
    try:
        from huggingface_hub.constants import HF_HUB_CACHE

        repo = _model_config(model).model_name
        rev = _hf_snapshot_revision(repo)
        if not rev:
            return None
        path = os.path.join(
            HF_HUB_CACHE, "models--" + repo.replace("/", "--"), "snapshots", rev
        )
        return path if os.path.isdir(path) else None
    except Exception:
        return None


def mflux_weights_status(identity: dict) -> tuple[bool, str]:
    """Check the identity's cached snapshot can actually serve all weights.

    A repo can be "cached" while one transformer shard is still an
    ``.incomplete`` blob — the old failure mode that made generation die at
    load time after the adapter was already fixed.
    """
    repo = identity.get("model_repo")
    revision = identity.get("model_revision")
    is_local = bool(repo and repo.startswith("local:"))
    if not repo or (not revision and not is_local):
        return False, "model repo/revision not resolved (weights not cached?)"
    try:
        from huggingface_hub.constants import HF_HUB_CACHE

        rev = revision or ""
        if is_local:
            snap = repo.split(":", 1)[1]
        else:
            snap = os.path.join(
                HF_HUB_CACHE, "models--" + repo.replace("/", "--"), "snapshots", rev
            )
        if not os.path.isdir(snap):
            label = (revision or "local")[:8]
            return False, f"snapshot {label} not present in the HF cache"
        required = set()
        for sub in ("transformer", "text_encoder", "text_encoder_2", "vae"):
            idx = os.path.join(snap, sub, "diffusion_pytorch_model.safetensors.index.json")
            if os.path.exists(idx):
                import json

                with open(idx, encoding="utf-8") as fh:
                    mapping = json.load(fh).get("weight_map", {})
                required.update(os.path.join(snap, sub, name) for name in set(mapping.values()))
        if not required:
            # Single-file/monolithic layouts: require the directory to be non-empty.
            present = [
                os.path.join(root, f)
                for root, _dirs, files in os.walk(snap)
                for f in files
            ]
            if not present:
                return False, "snapshot directory is empty"
            missing = [p for p in present if os.path.getsize(p) == 0]
        else:
            missing = [p for p in required if not os.path.exists(p) or os.path.getsize(p) == 0]
        if missing:
            names = ", ".join(sorted(os.path.basename(p) for p in missing)[:3])
            return False, f"{len(missing)} weight file(s) missing/incomplete ({names})"
        return True, f"{repo}@{rev[:8]} weights present"
    except Exception as e:
        return False, f"weight check failed: {e}"


# image_size aliases used across the 27 legacy prototypes' DALL-E/Replicate
# calls. Anything not listed here defaults to 1024x1024.
_LEGACY_IMAGE_SIZES = {
    "square_small": (512, 512),
    "square": (512, 512),
    "square_hd": (1024, 1024),
    "square_large": (1024, 1024),
    "256x256": (256, 256),
    "512x512": (512, 512),
    "1024x1024": (1024, 1024),
}


class ImageGenerator:
    """Pluggable image generator: local mflux by default, gated cloud fallback."""

    def __init__(
        self,
        backend: str = "mflux",
        model: str = "schnell",
        quantize: int = 4,
        steps: int = 4,
        guidance: float = 4.0,
        model_path: str | None = None,
        output_dir: str = "outputs/images",
        **backend_kwargs,
    ):
        self.backend = backend
        self.model = model
        self.quantize = quantize
        self.steps = steps
        self.guidance = guidance
        self.model_path = model_path
        self.output_dir = output_dir
        # Note: output_dir is NOT created here. It's created lazily, right
        # before a successful generation is written into it, so importing
        # or instantiating this class (e.g. via manager wiring in headless
        # test runs) never touches the working directory.

        if backend in ("openai", "replicate"):
            privacy.require_cloud(f"ImageGenerator(backend={backend!r})")

        self._backend_kwargs = backend_kwargs
        self._mflux_backend = None  # lazily constructed on first generate()

    def identity(self) -> dict:
        """Generation identity used for cache keys and provenance.

        Two renders are only interchangeable when the backend, model repo,
        weights revision, quantisation and sampling settings all match.
        """
        if self.backend == "mflux":
            if self._mflux_backend is None:
                self._mflux_backend = _MfluxBackend(
                    model=self.model,
                    quantize=self.quantize,
                    steps=self.steps,
                    guidance=self.guidance,
                    model_path=self.model_path,
                )
            return self._mflux_backend.identity()
        if self.backend == "fake":
            return {
                "backend": "fake",
                "model": "synthetic-1x1",
                "model_revision": None,
                "quantize": None,
                "num_inference_steps": None,
                "guidance": None,
            }
        return {
            "backend": self.backend,
            "model": self.model,
            "model_revision": None,
            "quantize": None,
            "num_inference_steps": None,
            "guidance": None,
        }

    def generate(self, prompt: str, size: tuple[int, int] = (1024, 1024), seed=None):
        start = time.time()
        if self.backend == "fake":
            path, meta = self._generate_fake(prompt, size, seed)
        elif self.backend == "mflux":
            path, meta = self._generate_mflux(prompt, size, seed)
        elif self.backend == "openai":
            path, meta = self._generate_openai(prompt, size, seed)
        elif self.backend == "replicate":
            path, meta = self._generate_replicate(prompt, size, seed)
        else:
            raise InferenceError(f"Unknown ImageGenerator backend: {self.backend!r}")

        meta.setdefault("backend", self.backend)
        meta.setdefault("seed", seed)
        identity = self.identity()
        meta.setdefault("identity", identity)
        meta.setdefault("identity_key", _identity_digest(identity))
        meta["latency_s"] = time.time() - start
        return path, meta

    def generate_async(
        self, prompt, main_queue, on_ready, size=(1024, 1024), seed=None
    ):
        """Run ``generate`` on a worker thread; post ``on_ready(path, meta)``
        to ``main_queue`` when done so the main loop consumes it safely."""

        def _worker():
            try:
                path, meta = self.generate(prompt, size=size, seed=seed)
            except Exception as e:
                logger.error(
                    f"ImageGenerator.generate_async failed: {e}", exc_info=True
                )
                return
            main_queue.post(on_ready, path, meta)

        threading.Thread(target=_worker, daemon=True).start()

    # -- output handling --------------------------------------------------

    @staticmethod
    def _cleanup(tmp_path):
        """Best-effort removal of an orphaned tmp file after a failed
        generation, so `InferenceError` never leaves a stray artifact."""
        try:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass

    def _finalize(self, tmp_path):
        """Move a successfully generated file from system temp into
        ``self.output_dir``, creating the directory lazily (only now, on
        success) rather than eagerly in ``__init__``."""
        os.makedirs(self.output_dir, exist_ok=True)
        final_path = os.path.join(self.output_dir, os.path.basename(tmp_path))
        shutil.move(tmp_path, final_path)
        return final_path

    # -- fake -----------------------------------------------------------

    def _generate_fake(self, prompt, size, seed):
        # Deterministic, dependency-free backend used in headless mode /
        # tests. Always writes to the system temp dir only — never touches
        # self.output_dir — so headless/test runs can never pollute the
        # repo working directory.
        from PIL import Image

        path = create_secure_temp_file(suffix=".png")
        Image.new("RGB", (1, 1)).save(path)
        return path, {}

    # -- mflux ------------------------------------------------------------

    def _generate_mflux(self, prompt, size, seed):
        if self._mflux_backend is None:
            self._mflux_backend = _MfluxBackend(
                model=self.model,
                quantize=self.quantize,
                steps=self.steps,
                guidance=self.guidance,
                model_path=self.model_path,
            )
        tmp_path = create_secure_temp_file(suffix=".png")
        try:
            with INFERENCE_LOCK:
                used_seed = self._mflux_backend.generate(
                    prompt, size=size, seed=seed, out_path=tmp_path
                )
        except Exception:
            self._cleanup(tmp_path)
            raise
        path = self._finalize(tmp_path)
        return path, {"seed": used_seed}

    # -- openai (DALL-E) ---------------------------------------------------

    def _generate_openai(self, prompt, size, seed):

        try:
            from openai import OpenAI
        except ImportError as e:
            raise InferenceError(f"openai package not installed: {e}") from e

        client = OpenAI()
        try:
            width, height = size
            response = client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size=f"{width}x{height}",
                n=1,
            )
            image_url = response.data[0].url
        except Exception as e:
            raise InferenceError(f"OpenAI image generation failed: {e}") from e

        tmp_path = create_secure_temp_file(suffix=".png")
        try:
            self._download_to(image_url, tmp_path)
        except Exception:
            self._cleanup(tmp_path)
            raise
        path = self._finalize(tmp_path)
        return path, {}

    # -- replicate -----------------------------------------------------

    def _generate_replicate(self, prompt, size, seed):
        try:
            import replicate
        except ImportError as e:
            raise InferenceError(f"replicate package not installed: {e}") from e

        model_ref = self._backend_kwargs.get("model_ref", "stability-ai/sdxl:latest")
        width, height = size
        try:
            output = replicate.run(
                model_ref,
                input={
                    "prompt": prompt,
                    "width": width,
                    "height": height,
                    "seed": seed,
                },
            )
            result = output[0] if isinstance(output, list) else output
        except Exception as e:
            raise InferenceError(f"Replicate image generation failed: {e}") from e

        tmp_path = create_secure_temp_file(suffix=".png")
        try:
            # replicate>=1.0 returns FileOutput objects (with .read()/.url)
            # instead of plain URL strings; handle both shapes.
            if hasattr(result, "read"):
                with open(tmp_path, "wb") as f:
                    f.write(result.read())
            else:
                image_url = getattr(result, "url", None) or str(result)
                self._download_to(image_url, tmp_path)
        except Exception:
            self._cleanup(tmp_path)
            raise
        path = self._finalize(tmp_path)
        return path, {}

    @staticmethod
    def _download_to(url, path):
        import requests

        response = requests.get(url, timeout=60)
        response.raise_for_status()
        with open(path, "wb") as f:
            f.write(response.content)


class _MfluxBackend:
    """Thin adapter over the ``mflux`` package's local Flux.1 inference API.

    Imported lazily so importing this module never touches mflux. Wrapped
    here so the rest of the codebase never imports ``mflux`` directly; this
    is the only mflux-touching surface, per the design spec's guidance to
    verify the exact import surface against the installed release (Tasks
    12/13 do on-machine verification since mflux is not installed in this
    dev environment).
    """

    def __init__(
        self,
        model: str = "schnell",
        quantize: int = 4,
        steps: int = 4,
        guidance: float = 4.0,
        model_path: str | None = None,
    ):
        self.model = model
        self.quantize = quantize
        self.steps = steps
        self.guidance = guidance
        self.model_path = str(model_path) if model_path else None
        if self.model_path is None:
            # Prefer a complete local snapshot: letting mflux resolve the repo
            # through the Hub re-enters snapshot_download and can restart a
            # multi-GB fetch even when the weights are already cached.
            candidate = mflux_snapshot_path(model)
            if candidate:
                ready, _detail = mflux_weights_status(
                    {"model_repo": f"local:{candidate}",
                     "model_revision": Path(candidate).name}
                )
                if ready:
                    self.model_path = candidate
        self._flux = None
        self._repo = None
        self._revision = None

    def _resolve_weights_identity(self):
        """Record the exact model repo + snapshot revision we generate from.

        mflux resolves a model name to a Hugging Face repo and loads the
        snapshot pinned by that repo's ``refs/main``. Cache identity must
        carry both, or an image rendered by a different model/revision can
        be served as if it were the current one.
        """
        if self._repo is not None:
            return
        if self.model_path:
            self._repo = f"local:{self.model_path}"
            parts = Path(self.model_path).parts
            self._revision = (
                parts[parts.index("snapshots") + 1] if "snapshots" in parts else None
            )
            return
        cfg = _model_config(self.model)

        self._repo = cfg.model_name
        self._revision = _hf_snapshot_revision(self._repo)

    def _load(self):
        if self._flux is not None:
            return self._flux
        try:
            # mflux >= 0.23 exposes Flux1 here; the package root no longer
            # exports Flux1/Config (that API died after 0.6).
            Flux1 = _flux1_class()
        except ImportError as e:
            raise InferenceError(
                "mflux is not installed (or its API changed again); install it "
                "or switch [image].backend"
            ) from e

        self._resolve_weights_identity()
        if self.model_path:
            # Explicit local snapshot: never touches the network or re-downloads.
            self._flux = Flux1(
                model_path=self.model_path,
                model_config=_model_config(self.model),
                quantize=self.quantize,
            )
        else:
            self._flux = Flux1.from_name(self.model, quantize=self.quantize)
        return self._flux

    def identity(self) -> dict:
        """Everything that can change the pixels for a fixed prompt/seed/size."""
        if self._repo is None:
            try:
                self._resolve_weights_identity()
            except Exception as e:  # identity must never block generation
                logger.debug(f"mflux identity resolution failed: {e}")
        return {
            "backend": "mflux",
            "model": self.model,
            "model_repo": self._repo,
            "model_revision": self._revision,
            "quantize": self.quantize,
            "num_inference_steps": self.steps,
            "guidance": self.guidance,
        }

    def generate(self, prompt, size, seed, out_path):
        flux = self._load()
        width, height = size
        use_seed = seed if seed is not None else int(time.time())
        try:
            result = flux.generate_image(
                seed=use_seed,
                prompt=prompt,
                num_inference_steps=self.steps,
                height=height,
                width=width,
                guidance=self.guidance,
            )
            result.save(out_path, overwrite=True)
        except Exception as e:
            raise InferenceError(f"mflux generation failed: {e}") from e
        return use_seed


class DeprecatedAlias:
    """Adapts a legacy prototype's call pattern onto a unified ``ImageGenerator``.

    Legacy call sites (``SDXL_TURBO``, ``Dalle3ImageGenerator``, ``SDXL_LCM``,
    ``FluxImageGenerator``) pass kwargs like ``image_size="square_hd"`` and
    ``num_inference_steps=4`` that the unified generator doesn't accept.
    This wrapper maps/drops those kwargs and forwards the rest, emitting a
    single ``DeprecationWarning`` per instance.
    """

    def __init__(self, gen: ImageGenerator, name: str):
        self._gen = gen
        self._name = name
        self._warned = False

    def generate(self, prompt: str, **legacy_kwargs):
        if not self._warned:
            warnings.warn(
                f"{self._name} is deprecated; use manager.image_gen directly",
                DeprecationWarning,
                stacklevel=2,
            )
            self._warned = True

        size = (1024, 1024)
        if "image_size" in legacy_kwargs:
            raw = legacy_kwargs.pop("image_size")
            size = _LEGACY_IMAGE_SIZES.get(raw, (1024, 1024))
        if "size" in legacy_kwargs:
            size = legacy_kwargs.pop("size")

        seed = legacy_kwargs.pop("seed", None)

        for dropped in ("num_inference_steps", "quality", "style", "response_format"):
            if dropped in legacy_kwargs:
                logger.debug(
                    f"{self._name}.generate: dropping unsupported legacy kwarg "
                    f"{dropped!r}={legacy_kwargs.pop(dropped)!r}"
                )
        for unknown in list(legacy_kwargs):
            logger.debug(
                f"{self._name}.generate: dropping unrecognized legacy kwarg {unknown!r}"
            )
            legacy_kwargs.pop(unknown)

        return self._gen.generate(prompt, size=size, seed=seed)
