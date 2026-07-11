import logging
import queue
import time


class LoopControl:
    def __init__(self):
        self._running = True
        self._keyboard_input = None  # Will be set by the Manager
        self.logger = logging.getLogger(__name__)

    def stop(self):
        self._running = False

    def is_running(self):
        if self._keyboard_input and self._keyboard_input.is_key_pressed("q"):
            self.logger.info("'q' pressed. Stopping loop.")
            self._running = False
        return self._running


def run_until_quit(callback, lunar_tools_art_manager, fps=30):
    loop_control = LoopControl()
    loop_control._keyboard_input = lunar_tools_art_manager.keyboard_input

    delay = 1.0 / fps

    lunar_tools_art_manager.logger.info(
        f"Starting loop at {fps} FPS. Press 'q' to quit or Ctrl+C."
    )

    main_queue = getattr(lunar_tools_art_manager, "main_queue", None)

    try:
        while loop_control.is_running():
            start_time = time.time()
            if main_queue is not None:
                main_queue.drain()
            callback()
            elapsed_time = time.time() - start_time
            sleep_time = delay - elapsed_time
            if sleep_time > 0:
                time.sleep(sleep_time)
    except KeyboardInterrupt:
        lunar_tools_art_manager.logger.info("Ctrl+C detected. Stopping loop.")
    finally:
        loop_control.stop()


class MainLoopQueue:
    """Thread-safe handoff: background threads post callables, main loop drains them."""

    def __init__(self):
        self._q = queue.Queue()

    def post(self, fn, *args):
        self._q.put((fn, args))

    def drain(self, max_items=10):
        for _ in range(max_items):
            try:
                fn, args = self._q.get_nowait()
            except queue.Empty:
                return
            try:
                fn(*args)
            except Exception:
                # One failing callback must not kill the main loop or drop
                # the remaining queued items.
                logging.getLogger(__name__).exception(
                    "MainLoopQueue callback raised; continuing drain"
                )
