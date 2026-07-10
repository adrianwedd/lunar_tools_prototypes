import time
import warnings

import pytest


def test_generate_returns_tuple(tmp_path):
    from lunar_tools_art.tools.images import ImageGenerator

    gen = ImageGenerator(backend="fake", output_dir=str(tmp_path))
    path, meta = gen.generate("a moon garden", size=(64, 64))
    assert path.endswith(".png") and meta["backend"] == "fake"
    assert "seed" in meta and "latency_s" in meta


def test_alias_unpacking_and_legacy_kwargs(tmp_path):
    from lunar_tools_art.tools.images import DeprecatedAlias, ImageGenerator

    alias = DeprecatedAlias(
        ImageGenerator(backend="fake", output_dir=str(tmp_path)), "dalle3"
    )
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        image, _ = alias.generate(
            "p", image_size="square_hd", num_inference_steps=4, seed=7
        )
    assert image.endswith(".png")
    assert any(issubclass(x.category, DeprecationWarning) for x in w)


def test_alias_warns_once(tmp_path):
    from lunar_tools_art.tools.images import DeprecatedAlias, ImageGenerator

    alias = DeprecatedAlias(
        ImageGenerator(backend="fake", output_dir=str(tmp_path)), "sdxl_turbo"
    )
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        alias.generate("p")
        alias.generate("p")
        dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
    assert len(dep_warnings) == 1


def test_alias_maps_image_size_variants(tmp_path):
    from lunar_tools_art.tools.images import DeprecatedAlias, ImageGenerator

    captured = {}

    class Spy(ImageGenerator):
        def generate(self, prompt, size=(1024, 1024), seed=None):
            captured["size"] = size
            captured["seed"] = seed
            return super().generate(prompt, size=size, seed=seed)

    gen = Spy(backend="fake", output_dir=str(tmp_path))
    alias = DeprecatedAlias(gen, "flux")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        alias.generate("p", image_size="square_small")
    assert captured["size"] == (512, 512)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        alias.generate("p", image_size="totally_unknown")
    assert captured["size"] == (1024, 1024)


def test_generate_async_posts_to_queue(tmp_path):
    from lunar_tools_art.loop_utils import MainLoopQueue
    from lunar_tools_art.tools.images import ImageGenerator

    gen = ImageGenerator(backend="fake", output_dir=str(tmp_path))
    q, got = MainLoopQueue(), []
    gen.generate_async("p", q, lambda path, meta: got.append(path), size=(32, 32))
    for _ in range(50):
        q.drain()
        if got:
            break
        time.sleep(0.05)
    assert got and got[0].endswith(".png")


def test_cloud_backend_blocked_local_only(tmp_path, monkeypatch):
    import lunar_tools_art.privacy as privacy

    monkeypatch.setattr(privacy, "cloud_allowed", lambda cfg=None: False)
    from lunar_tools_art.exceptions import CloudDisabledError
    from lunar_tools_art.tools.images import ImageGenerator

    with pytest.raises(CloudDisabledError):
        ImageGenerator(backend="openai", output_dir=str(tmp_path))


def test_cloud_backend_allowed_constructs(tmp_path, monkeypatch):
    import lunar_tools_art.privacy as privacy

    monkeypatch.setattr(privacy, "cloud_allowed", lambda cfg=None: True)
    from lunar_tools_art.tools.images import ImageGenerator

    gen = ImageGenerator(backend="openai", output_dir=str(tmp_path))
    assert gen.backend == "openai"


def test_mflux_backend_generates_with_mocked_module(tmp_path, monkeypatch):
    import sys
    import types

    import numpy as np
    from PIL import Image

    fake_mflux = types.ModuleType("mflux")

    class FakeConfig:
        def __init__(self, num_inference_steps=4, height=1024, width=1024):
            self.num_inference_steps = num_inference_steps
            self.height = height
            self.width = width

    class FakeFlux1:
        @classmethod
        def from_name(cls, model_name, quantize=None):
            return cls()

        def generate_image(self, seed, prompt, config):
            arr = np.zeros((config.height, config.width, 3), dtype=np.uint8)
            img = Image.fromarray(arr)

            class Result:
                def save(self_inner, path):
                    img.save(path)

            return Result()

    fake_mflux.Flux1 = FakeFlux1
    fake_mflux.Config = FakeConfig
    monkeypatch.setitem(sys.modules, "mflux", fake_mflux)

    from lunar_tools_art.tools.images import ImageGenerator

    gen = ImageGenerator(
        backend="mflux", model="schnell", quantize=4, output_dir=str(tmp_path)
    )
    path, meta = gen.generate("a moon garden", size=(64, 64), seed=3)
    assert path.endswith(".png")
    assert meta["backend"] == "mflux"
    assert meta["seed"] == 3
