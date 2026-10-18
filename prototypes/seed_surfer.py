"""Seed Surfer — interactive seed-space explorer.

Turn a dial (MIDI CC or keyboard +/-) to surf a fixed prompt's seed space.
The SeedScheduler does bounded latest-wins local generation (mflux on the
Studio, deterministic fake in headless test mode) with adjacent-seed
prefetch; already-rendered seeds display instantly from the PNG cache, so
the dial feels responsive even while a new image takes seconds.

Controls:
  +/- or up/down : seed step
  left/right     : jump 10 seeds (fast surf)
  space          : random seed jump
  s              : save current seed to favourites (outputs/seed_surfer/favourites.json)
  c              : clear display of "how to" help overlay state
  a              : toggle adjacent-seed prefetch
  q              : quit

Run:  env/bin/python -m prototypes.seed_surfer
Keyboard/`q` quit requires the pyglet window focus; MIDI CC20 = seed dial
(CC value maps over a 64-seed window you surf with the dial directly).
"""

from __future__ import annotations

import json
import logging
import random
import time
from pathlib import Path

import numpy as np
from PIL import Image

from src.lunar_tools_art.seed_scheduler import SeedScheduler

logger = logging.getLogger(__name__)

FAVOURITES_PATH = Path("outputs/seed_surfer/favourites.json")


class SeedSurfer:
    def __init__(
        self,
        manager,
        prompt: str = "A vast cosmic scene with galaxies, nebulae, and stars",
        size=(512, 512),
        start_seed=42,
        image_dir="outputs/seed_surfer/images",
    ):
        self.manager = manager
        self.renderer = manager.renderer
        self.keyboard = manager.keyboard_input
        self.midi = manager.midi_input
        self.logger = manager.logger or logger
        self.prompt = prompt
        self.size = tuple(size)
        self.seed = start_seed
        self.image_dir = Path(image_dir)
        self.image_dir.mkdir(parents=True, exist_ok=True)

        # The scheduler owns all generation; the manager's image_gen backend
        # is whatever config resolved (mflux locally, fake in headless).
        self.gen = manager.image_gen
        self.scheduler = SeedScheduler(
            self._generate,
            cache_index_path=self.image_dir / "index.json",
            identity=self.gen.identity,
        )
        self._current_view = None  # (seed, np_frame)
        self._pending_seed_announce = None
        self._prefetch_on = True
        self._last_cc = None

    # -- generation bridge ----------------------------------------------------

    def _generate(self, prompt, size, seed):
        """Scheduler worker call: synchronous generate, returns (path, meta)."""
        path, meta = self.gen.generate(prompt, size=size, seed=seed)
        return path, meta

    # -- display ---------------------------------------------------------------

    def _load_cached(self, seed):
        entry = self.scheduler.cached_entry(self.prompt, self.size, seed)
        if not entry:
            return None
        p = Path(entry["path"])
        if not p.exists():
            return None
        return np.array(Image.open(p).convert("RGB").resize(self.size))

    def show(self, frame):
        self.renderer.render(frame)

    def standby(self, text):
        h, w = self.renderer.height, self.renderer.width
        img = np.zeros((h, w, 3), dtype=np.uint8)
        img[:, :, 2] = 40
        self.show(img)  # full diagnostics rendered via _standby_frame below

    def _draw_dial_state(self, loading):
        """Render the seed indicator + status while generation works."""
        h, w = self.renderer.height, self.renderer.width
        img = np.zeros((h, w, 3), dtype=np.uint8)
        pulse = int(abs(np.sin(time.time() * 2)) * 60) + 20
        img[:, :, 0 if loading else 1] = pulse
        return img

    # -- favourites --------------------------------------------------------------

    def save_favourite(self):
        FAVOURITES_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = []
        if FAVOURITES_PATH.exists():
            try:
                data = json.loads(FAVOURITES_PATH.read_text())
            except Exception:
                pass
        entry = self.scheduler.cached_entry(self.prompt, self.size, self.seed)
        data.append(
            {
                "seed": self.seed,
                "prompt": self.prompt,
                "size": list(self.size),
                "identity": self.scheduler.identity(),
                "identity_key": self.scheduler.identity_key(),
                "cache_key": self.scheduler.cache_key(self.prompt, self.size, self.seed),
                "image_path": entry.get("path") if entry else None,
                "metadata": entry.get("metadata") if entry else None,
                "saved_at": time.time(),
            }
        )
        FAVOURITES_PATH.write_text(json.dumps(data, indent=2))
        self.logger.info(f"Saved favourite seed {self.seed}.")

    # -- main loop ------------------------------------------------------------------

    def run(self):
        self.logger.info(
            "Seed Surfer | +/- seed, left/right jump10, space random, "
            "s save, a prefetch toggle, q quit"
        )
        self.scheduler.start()
        try:
            self._run_loop()
        except KeyboardInterrupt:
            self.logger.info("Interrupted; exiting.")
        finally:
            self.scheduler.stop()
            self.logger.info("Seed Surfer stopped.")

    def _run_loop(self):
        while True:
            if self.manager.main_queue is not None:
                self.manager.main_queue.drain()
            if not self._handle_keys():
                return

            frame = self._load_cached(self.seed)
            if frame is not None:
                self.show(frame)
                # prefetch neighbours now that the visitor is looking at a
                # cached frame
                if self._prefetch_on:
                    for neighbour in (self.seed - 1, self.seed + 1):
                        if neighbour >= 0:
                            self.scheduler.request_prefetch(
                                self.prompt, self.size, neighbour
                            )
            else:
                # not cached yet: request it and show the dial-state frame
                self.scheduler.request(self.prompt, self.size, self.seed)
                self.show(self._draw_dial_state(loading=True))

            time.sleep(0.05)

    def _handle_keys(self) -> bool:
        """Returns False when the visitor asked to quit."""
        if self.keyboard.is_key_pressed("q"):
            return False
        step = 0
        if self.keyboard.is_key_pressed("+") or self.keyboard.is_key_pressed("up"):
            step = 1
        elif self.keyboard.is_key_pressed("-") or self.keyboard.is_key_pressed("down"):
            step = -1
        elif self.keyboard.is_key_pressed("right"):
            step = 10
        elif self.keyboard.is_key_pressed("left"):
            step = -10
        elif self.keyboard.is_key_pressed(" "):
            step = random.randint(1, 50) * random.choice((1, -1))
        if step:
            self.seed = max(0, self.seed + step)
            self.logger.info(f"Seed -> {self.seed}")
        if self.keyboard.is_key_pressed("s"):
            self.save_favourite()
        if self.keyboard.is_key_pressed("a"):
            self._prefetch_on = not self._prefetch_on
            self.logger.info(f"Prefetch {'on' if self._prefetch_on else 'off'}")
        # MIDI: CC20 is the surf dial over a 32-seed window; CC21 steps +-1 on
        # crossing.
        cc = self.midi.get(20)
        if cc is not None and cc != self._last_cc:
            if self._last_cc is not None:
                direction = 1 if cc > self._last_cc else -1
                self.seed = max(0, self.seed + direction)
                self.logger.info(f"Dial -> seed {self.seed}")
            self._last_cc = cc
        cc21 = self.midi.get(21)
        if cc21 is not None and cc21 > 0.5:
            self.save_favourite()
        return True


def main():
    from src.lunar_tools_art import Manager

    manager = Manager()
    surfer = SeedSurfer(manager)
    surfer.run()


if __name__ == "__main__":
    main()