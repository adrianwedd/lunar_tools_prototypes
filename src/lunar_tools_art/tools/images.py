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

from .. import privacy
from ..exceptions import InferenceError
from ..inference_gate import INFERENCE_LOCK
from ..utils import create_secure_temp_file

logger = logging.getLogger(__name__)

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
        output_dir: str = "outputs/images",
        **backend_kwargs,
    ):
        self.backend = backend
        self.model = model
        self.quantize = quantize
        self.output_dir = output_dir
        # Note: output_dir is NOT created here. It's created lazily, right
        # before a successful generation is written into it, so importing
        # or instantiating this class (e.g. via manager wiring in headless
        # test runs) never touches the working directory.

        if backend in ("openai", "replicate"):
            privacy.require_cloud(f"ImageGenerator(backend={backend!r})")

        self._backend_kwargs = backend_kwargs
        self._mflux_backend = None  # lazily constructed on first generate()

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
                model=self.model, quantize=self.quantize
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

    def __init__(self, model: str = "schnell", quantize: int = 4):
        self.model = model
        self.quantize = quantize
        self._flux = None

    def _load(self):
        if self._flux is not None:
            return self._flux
        try:
            from mflux import Flux1
        except ImportError as e:
            raise InferenceError(
                "mflux is not installed; install it or switch [image].backend"
            ) from e

        self._flux = Flux1.from_name(self.model, quantize=self.quantize)
        return self._flux

    def generate(self, prompt, size, seed, out_path):
        from mflux import Config

        flux = self._load()
        width, height = size
        config = Config(num_inference_steps=4, height=height, width=width)
        use_seed = seed if seed is not None else int(time.time())
        try:
            result = flux.generate_image(seed=use_seed, prompt=prompt, config=config)
            result.save(out_path)
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
