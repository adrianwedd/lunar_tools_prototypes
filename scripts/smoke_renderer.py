#!/usr/bin/env python3
"""On-machine smoke test for the pyglet Renderer.

Opens a window and animates a gradient for a few seconds. Press ESC (or 'q')
in the window to quit early.

Run with a real display attached (not under LUNAR_HEADLESS):

    python scripts/smoke_renderer.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np  # noqa: E402

from lunar_tools_art.tools.display import Renderer  # noqa: E402
from lunar_tools_art.tools.input import KeyboardInput  # noqa: E402


def main():
    width, height = 640, 480
    renderer = Renderer(width, height, backend="pyglet")
    keyboard = KeyboardInput(window=renderer.window)

    print("Animating gradient for up to 10 seconds. Press ESC or 'q' to quit.")
    start = time.time()
    while time.time() - start < 10.0:
        if keyboard.is_key_pressed("escape") or keyboard.is_key_pressed("q"):
            break

        t = time.time() - start
        x = np.linspace(0, 1, width, dtype=np.float32)
        y = np.linspace(0, 1, height, dtype=np.float32)
        xv, yv = np.meshgrid(x, y)
        r = ((xv + t * 0.1) % 1.0 * 255).astype(np.uint8)
        g = ((yv + t * 0.2) % 1.0 * 255).astype(np.uint8)
        b = np.full((height, width), int((np.sin(t) * 0.5 + 0.5) * 255), dtype=np.uint8)
        frame = np.stack([r, g, b], axis=-1)

        renderer.render(frame)
        time.sleep(1 / 30)

    renderer.close()
    print("Done.")


if __name__ == "__main__":
    main()
