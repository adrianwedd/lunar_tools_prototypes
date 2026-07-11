import threading

import numpy as np

from lunar_tools_art.tools.display import Renderer


def _render_in_thread(r):
    box = {}

    def target():
        try:
            r.render(np.zeros((64, 64, 3), dtype="uint8"))
            box["err"] = None
        except RuntimeError as e:
            box["err"] = e

    t = threading.Thread(target=target)
    t.start()
    t.join()
    return box["err"]


def test_render_off_main_thread_raises():
    r = Renderer(64, 64, backend="null")
    assert isinstance(_render_in_thread(r), RuntimeError)


def test_null_backend_records_frames():
    r = Renderer(64, 64, backend="null")
    r.render(np.zeros((64, 64, 3), dtype="uint8"))
    assert len(r.frames) == 1
