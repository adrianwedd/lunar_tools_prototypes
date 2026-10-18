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


def test_mflux_backend_uses_current_api(tmp_path, monkeypatch):
    """mflux >=0.23: Flux1 lives under models.flux.variants.txt2img and
    generate_image takes kwargs (no root-level Config)."""
    import numpy as np
    from PIL import Image

    calls = {}

    class FakeFlux1:
        @classmethod
        def from_name(cls, model_name, quantize=None):
            calls["model"] = model_name
            calls["quantize"] = quantize
            return cls()

        def generate_image(self, **kwargs):
            calls.update(kwargs)
            arr = np.zeros((kwargs["height"], kwargs["width"], 3), dtype=np.uint8)
            img = Image.fromarray(arr)

            class Result:
                def save(self_inner, path, overwrite=False):
                    img.save(path)

            return Result()

    class FakeConfig:
        model_name = "black-forest-labs/FLUX.1-schnell"

    from lunar_tools_art.tools import images as images_mod

    monkeypatch.setattr(images_mod, "_flux1_class", lambda: FakeFlux1)
    monkeypatch.setattr(images_mod, "_model_config", lambda name: FakeConfig())
    monkeypatch.setattr(images_mod, "_hf_snapshot_revision", lambda repo: "rev123")

    gen = images_mod.ImageGenerator(
        backend="mflux", model="schnell", quantize=4,
        steps=4, guidance=3.5, output_dir=str(tmp_path),
    )
    path, meta = gen.generate("a moon garden", size=(64, 64), seed=3)

    assert path.endswith(".png")
    assert meta["backend"] == "mflux"
    assert meta["seed"] == 3
    assert calls["model"] == "schnell" and calls["quantize"] == 4
    assert calls["num_inference_steps"] == 4
    assert calls["height"] == 64 and calls["width"] == 64
    assert calls["guidance"] == 3.5
    assert "config" not in calls  # old API must not be used
    assert meta["identity"]["model_repo"] == "black-forest-labs/FLUX.1-schnell"
    assert meta["identity"]["model_revision"] == "rev123"
    assert meta["identity"]["num_inference_steps"] == 4


def test_mflux_backend_propagates_actual_seed_when_none(tmp_path, monkeypatch):
    """seed=None should not be lost: mflux computes an actual seed at
    generation time, and it must show up in metadata rather than `None`."""
    import numpy as np
    from PIL import Image

    consumed_seeds = []

    class FakeFlux1:
        @classmethod
        def from_name(cls, model_name, quantize=None):
            return cls()

        def generate_image(self, **kwargs):
            consumed_seeds.append(kwargs["seed"])
            arr = np.zeros((kwargs["height"], kwargs["width"], 3), dtype=np.uint8)
            img = Image.fromarray(arr)

            class Result:
                def save(self_inner, path, overwrite=False):
                    img.save(path)

            return Result()

    class FakeConfig:
        model_name = "black-forest-labs/FLUX.1-schnell"

    from lunar_tools_art.tools import images as images_mod

    monkeypatch.setattr(images_mod, "_flux1_class", lambda: FakeFlux1)
    monkeypatch.setattr(images_mod, "_model_config", lambda name: FakeConfig())
    monkeypatch.setattr(images_mod, "_hf_snapshot_revision", lambda repo: "rev123")

    gen = images_mod.ImageGenerator(
        backend="mflux", model="schnell", quantize=4, output_dir=str(tmp_path)
    )
    path, meta = gen.generate("a moon garden", size=(64, 64), seed=None)
    assert path.endswith(".png")
    assert consumed_seeds and isinstance(consumed_seeds[0], int)
    assert meta["seed"] == consumed_seeds[0]


def test_identity_revision_change_changes_cache_identity(tmp_path, monkeypatch):
    from lunar_tools_art.tools import images as images_mod

    class FakeConfig:
        model_name = "black-forest-labs/FLUX.1-schnell"

    revisions = iter(["aaa", "bbb"])
    monkeypatch.setattr(images_mod, "mflux_snapshot_path", lambda model: None)
    monkeypatch.setattr(images_mod, "_model_config", lambda name: FakeConfig())
    monkeypatch.setattr(images_mod, "_hf_snapshot_revision", lambda repo: next(revisions))

    a = images_mod.ImageGenerator(backend="mflux", output_dir=str(tmp_path)).identity()
    b = images_mod.ImageGenerator(backend="mflux", output_dir=str(tmp_path)).identity()
    assert a["model_revision"] == "aaa" and b["model_revision"] == "bbb"
    assert a != b


def test_mflux_weights_status_reports_missing_snapshot():
    from lunar_tools_art.tools.images import mflux_weights_status

    ok, detail = mflux_weights_status(
        {"model_repo": "nonexistent/model-xyz", "model_revision": "deadbeef"}
    )
    assert ok is False
    assert "not present" in detail or "not resolved" in detail


def test_mflux_weights_status_requires_identity():
    from lunar_tools_art.tools.images import mflux_weights_status

    ok, detail = mflux_weights_status({"model_repo": None, "model_revision": None})
    assert ok is False
    assert "not resolved" in detail


def test_mflux_auto_uses_complete_local_snapshot(tmp_path, monkeypatch):
    """The production path must not re-enter the Hub downloader when a
    complete local snapshot exists."""
    import numpy as np
    from PIL import Image

    captured = {}

    class FakeFlux1:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def generate_image(self, **kwargs):
            img = Image.fromarray(
                np.zeros((kwargs["height"], kwargs["width"], 3), dtype=np.uint8)
            )

            class Result:
                def save(self_inner, path, overwrite=False):
                    img.save(path)

            return Result()

    class FakeConfig:
        pass

    from lunar_tools_art.tools import images as images_mod

    snapshot = tmp_path / "snapshots" / "abc123"
    snapshot.mkdir(parents=True)
    monkeypatch.setattr(images_mod, "mflux_snapshot_path", lambda model: str(snapshot))
    monkeypatch.setattr(images_mod, "mflux_weights_status", lambda ident: (True, "ok"))
    monkeypatch.setattr(images_mod, "_flux1_class", lambda: FakeFlux1)
    monkeypatch.setattr(images_mod, "_model_config", lambda name: FakeConfig())

    gen = images_mod.ImageGenerator(
        backend="mflux", model="schnell", output_dir=str(tmp_path)
    )
    gen.generate("p", size=(32, 32), seed=1)
    assert captured["model_path"] == str(snapshot)
    assert gen.identity()["model_repo"] == f"local:{snapshot}"
    assert gen.identity()["model_revision"] == "abc123"
