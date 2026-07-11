import numpy as np


def test_headless_env_selects_fakes(monkeypatch):
    monkeypatch.setenv("LUNAR_HEADLESS", "1")
    from lunar_tools_art.tools import headless, resolve

    assert headless.headless_active() is True
    assert resolve("WebCam") is headless.FakeWebCam
    img = headless.FakeWebCam().get_img()
    assert isinstance(img, np.ndarray) and img.shape == (480, 640, 3)


def test_manager_headless_no_cloud(monkeypatch):
    monkeypatch.setenv("LUNAR_HEADLESS", "1")
    import lunar_tools_art.privacy as privacy

    monkeypatch.setattr(privacy, "cloud_allowed", lambda cfg=None: False)
    from lunar_tools_art.manager import LunarToolsArtManager

    m = LunarToolsArtManager()
    # Task 9: image generation is served by a unified ImageGenerator (forced
    # to the deterministic `fake` backend in headless mode); legacy aliases
    # wrap it regardless of privacy mode, so they are no longer None.
    from lunar_tools_art.tools.images import DeprecatedAlias

    assert isinstance(m.dalle3, DeprecatedAlias)
    assert isinstance(m.sdxl_turbo, DeprecatedAlias)
    assert isinstance(m.sdxl_lcm, DeprecatedAlias)
    assert m.image_gen.backend == "fake"
    assert m.webcam is not None
