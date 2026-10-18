"""Real Renderer implementation: pyglet (OpenGL) window, OpenCV fallback,
and a ``null`` backend for headless tests.

All rendering happens on the main thread. ``render()`` raises ``RuntimeError``
when called from any other thread — background work must post frames via
``MainLoopQueue`` instead of touching the renderer directly.
"""

import logging
import os
import threading

logger = logging.getLogger(__name__)


def _as_rgb_array(image):
    """Coerce a renderable input to an HxWx3 uint8 RGB array.

    Some legacy prototypes still hand the unified image generator's output
    (a PNG path) straight to the renderer, and others pass PIL images. Both
    used to crash on the real pyglet/opencv backends while the headless null
    backend silently accepted them. Decoding here makes the renderer's
    contract explicit: it only ever draws decoded RGB frames.
    """
    if isinstance(image, (str, bytes, os.PathLike)):
        import cv2
        import numpy as np

        bgr = cv2.imread(os.fspath(image), cv2.IMREAD_COLOR)
        if bgr is None:
            raise ValueError(f"Renderer could not decode image path: {image!r}")
        return bgr[..., ::-1]

    if hasattr(image, "convert") and hasattr(image, "mode") and hasattr(image, "size"):
        # PIL.Image.Image
        import numpy as np

        return np.asarray(image.convert("RGB"))

    return image


class Renderer:
    """Displays numpy HxWx3 RGB frames via pyglet, OpenCV, or nowhere (null)."""

    def __init__(self, width, height, backend="pyglet"):
        self.width = width
        self.height = height
        self.backend = backend
        self.window = None
        self.frames = []  # populated by the null backend (tests/headless)
        self.last_key = None  # set by the opencv backend each frame

        self._pyglet = None
        self._pyglet_image_cls = None

        if backend == "pyglet":
            self._init_pyglet()

    def _init_pyglet(self):
        import pyglet

        self._pyglet = pyglet
        self.window = pyglet.window.Window(
            width=self.width, height=self.height, caption="Lunar Tools Art"
        )

    def render(self, image) -> None:
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError(
                "Renderer.render() must be called from the main thread; "
                "post to manager.main_queue from background threads instead."
            )

        image = _as_rgb_array(image)

        if self.backend == "null":
            self.frames.append(image)
            return

        if self.backend == "pyglet":
            self._render_pyglet(image)
            return

        if self.backend == "opencv":
            self._render_opencv(image)
            return

        raise ValueError(f"Unknown renderer backend: {self.backend!r}")

    def _render_pyglet(self, image):
        import pyglet

        h, w = image.shape[0], image.shape[1]
        image_data = pyglet.image.ImageData(w, h, "RGB", image[::-1].tobytes())

        self.window.switch_to()
        self.window.clear()
        image_data.blit(0, 0)
        self.window.flip()
        self.window.dispatch_events()

    def _render_opencv(self, image):
        import cv2

        bgr = image[:, :, ::-1]
        cv2.imshow("Lunar Tools Art", bgr)
        # Surface the last key pressed in the window so prototypes can be
        # interactive even when pynput lacks Accessibility trust (terminal
        # agents, SSH sessions). -1 (no key) clears it, which gives natural
        # edge-triggering.
        code = cv2.waitKey(1) & 0xFF
        if code == 0xFF:
            self.last_key = None
        elif code == 32:
            self.last_key = "space"
        elif 32 < code < 127:
            self.last_key = chr(code)
        else:
            self.last_key = None

    def set_size(self, width, height):
        self.width = width
        self.height = height
        if self.backend == "pyglet" and self.window is not None:
            self.window.set_size(width, height)

    def close(self):
        if self.backend == "pyglet" and self.window is not None:
            self.window.close()
            self.window = None
        elif self.backend == "opencv":
            import cv2

            cv2.destroyWindow("Lunar Tools Art")
