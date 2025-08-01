import logging
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

    try:
        while loop_control.is_running():
            start_time = time.time()
            callback()
            elapsed_time = time.time() - start_time
            sleep_time = delay - elapsed_time
            if sleep_time > 0:
                time.sleep(sleep_time)
    except KeyboardInterrupt:
        lunar_tools_art_manager.logger.info("Ctrl+C detected. Stopping loop.")
    finally:
        loop_control.stop()
