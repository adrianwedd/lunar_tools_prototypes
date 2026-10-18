"""Seed Surfer — interactive seed-space explorer.

Turn a dial (MIDI CC or keyboard +/-) to surf a fixed prompt's seed space.
The SeedScheduler does bounded latest-wins local generation (mflux on the
Studio, deterministic fake in headless test mode) with adjacent-seed
prefetch; already-rendered seeds display instantly from a bounded decoded
frame cache, so the dial feels responsive even while a new image takes
seconds.

Controls:
  +/- or up/down : seed step (hold to repeat: 0.30 s delay, then 12.5 Hz)
  left/right     : jump 10 seeds (same deliberate repeat)
  space          : random seed jump            (edge-triggered, one per press)
  s              : save current seed to favourites (edge-triggered)
  a              : toggle adjacent-seed prefetch (edge-triggered)
  c              : toggle the controls overlay
  q              : quit

MIDI (integer CC, normalised 0..1 from MidiInput.get):
  CC20 : surf dial — each CC step moves one seed
  CC21 : save favourite — fires once when the controller crosses 0.5 upward;
         holding it down does not write repeatedly.

Run:  env/bin/python -m prototypes.seed_surfer
Keyboard/`q` quit requires the pyglet window focus; MIDI binds the first
available input port.
"""

from __future__ import annotations

import json
import logging
import math
import random
import time
from collections import OrderedDict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from src.lunar_tools_art.seed_scheduler import SeedScheduler

logger = logging.getLogger(__name__)

FAVOURITES_PATH = Path("outputs/seed_surfer/favourites.json")

# Deliberate key-repeat, independent of frame rate.
REPEAT_DELAY_S = 0.30
REPEAT_INTERVAL_S = 0.08

NAV_KEYS = {
    "+": 1,
    "up": 1,
    "-": -1,
    "down": -1,
    "right": 10,
    "left": -10,
}


class SeedSurfer:
    def __init__(
        self,
        manager,
        prompt: str = "A vast cosmic scene with galaxies, nebulae, and stars",
        size=(512, 512),
        start_seed=42,
        image_dir="outputs/seed_surfer/images",
        favourites_path=None,
        frame_cache_size: int = 24,
        frame_interval_s: float = 0.05,
        repeat_delay_s: float = REPEAT_DELAY_S,
        repeat_interval_s: float = REPEAT_INTERVAL_S,
        clock=None,
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
        self.favourites_path = Path(favourites_path or FAVOURITES_PATH)

        # The scheduler owns all generation; the manager's image_gen backend
        # is whatever config resolved (mflux locally, fake in headless).
        self.gen = manager.image_gen
        self.scheduler = SeedScheduler(
            self._generate,
            cache_index_path=self.image_dir / "index.json",
            identity=self.gen.identity,
            on_success=self._on_success,
            on_error=self._on_error,
        )

        # Display state
        self._last_frame = None  # last successfully displayed np frame
        self._last_frame_seed = None
        self._last_render_sig = None
        self.last_status = "starting"
        self.last_status_line = ""

        # Bounded decoded-frame cache: never re-decode an unchanged PNG.
        self._frame_cache: OrderedDict = OrderedDict()
        self._frame_cache_max = max(2, int(frame_cache_size))
        self.cache_hits = 0
        self.cache_misses = 0
        self.decodes = 0
        self.evictions = 0

        # Input state (edge triggers + deliberate repeat)
        self._held: dict[str, bool] = {}
        self._repeat_next: dict[str, float] = {}
        self._prefetch_on = True
        self._help_on = False
        self._last_cc20 = None
        self._cc21_fired = False

        # Error recovery: exponential backoff per selected seed, so a failing
        # backend is not hammered 20 times a second.
        self._error_until = 0.0
        self._error_count: dict[int, int] = {}
        self._last_error = None

        self.frame_interval_s = frame_interval_s
        self.repeat_delay_s = repeat_delay_s
        self.repeat_interval_s = repeat_interval_s
        self._clock = clock or time.monotonic
        self._stop = False

    # -- generation bridge ----------------------------------------------------

    def _generate(self, prompt, size, seed):
        """Scheduler worker call: synchronous generate, returns (path, meta)."""
        path, meta = self.gen.generate(prompt, size=size, seed=seed)
        return path, meta

    def _on_success(self, result):
        # Worker thread. Clear backoff only when the visitor's target landed.
        if result.get("seed") == self.seed:
            self._error_until = 0.0
            self._error_count.pop(result.get("seed"), None)
            self._last_error = None

    def _on_error(self, prompt, size, seed, error):
        # Worker thread. Back off only for the seed the visitor is waiting on;
        # a failed prefetch must not stall navigation.
        self._last_error = str(error)
        if seed != self.seed:
            self.logger.warning(f"Prefetch seed {seed} failed: {error}")
            return
        attempts = self._error_count.get(seed, 0) + 1
        self._error_count[seed] = attempts
        delay = min(8.0, 2.0 ** (attempts - 1))
        self._error_until = self._clock() + delay
        self.logger.error(
            f"Seed {seed} generation failed ({attempts}x); retrying in {delay:.0f}s"
        )

    # -- display --------------------------------------------------------------

    def _cache_key_for(self, path: Path):
        try:
            st = path.stat()
        except OSError:
            return None
        return (str(path), st.st_mtime_ns, st.st_size, self.size)

    def _load_frame(self, seed):
        """Return a display frame for ``seed`` from cache/index, or None.

        Decoding happens once per (path, mtime, size); repeated frames hit the
        bounded LRU so the dial is not paying PNG-decode cost at 20 Hz.
        """
        entry = self.scheduler.cached_entry(self.prompt, self.size, seed)
        if not entry:
            self.cache_misses += 1
            return None
        path = Path(entry["path"])
        key = self._cache_key_for(path)
        if key is None:
            self.cache_misses += 1
            return None

        cached = self._frame_cache.get(key)
        if cached is not None:
            self._frame_cache.move_to_end(key)
            self.cache_hits += 1
            return cached

        try:
            with Image.open(path) as im:
                frame = np.array(im.convert("RGB").resize(self.size))
        except (OSError, ValueError) as e:
            self.logger.warning(f"Could not decode cached seed {seed}: {e}")
            self.cache_misses += 1
            return None

        self.decodes += 1
        self.cache_misses += 1
        self._frame_cache[key] = frame
        while len(self._frame_cache) > self._frame_cache_max:
            self._frame_cache.popitem(last=False)
            self.evictions += 1
        return frame

    def _blank_frame(self):
        h, w = self.renderer.height, self.renderer.width
        img = np.zeros((h, w, 3), dtype=np.uint8)
        img[:, :, 2] = 26
        return img

    def _draw_dial_state(self, loading=True):
        """Kept for compatibility: dark standby canvas."""
        return self._blank_frame()

    def _font(self, size):
        try:
            return ImageFont.load_default(size=max(10, int(size)))
        except TypeError:  # Pillow < 10.1
            return ImageFont.load_default()

    def _compose(self, frame, selected_seed, shown_seed, state):
        """Overlay the selected/pending seed on the preserved image."""
        base = Image.fromarray(frame).convert("RGB").copy()
        w, h = base.size
        draw = ImageDraw.Draw(base)
        band_h = max(30, h // 12)
        draw.rectangle([0, h - band_h, w, h], fill=(0, 0, 0))

        if shown_seed is not None and shown_seed != selected_seed:
            line = f"showing seed {shown_seed}   |   selected seed {selected_seed} — {state}"
        else:
            line = f"seed {selected_seed}   |   {state}"
        if self._help_on:
            line += "   [+/- step · ←/→ jump · space random · s save · a prefetch · c help]"

        font = self._font(band_h * 0.42)
        self.last_status_line = line
        draw.text((12, h - band_h + band_h * 0.28), line, font=font, fill=(235, 235, 235))
        # State dot: green cached, amber pending, red error.
        colour = (80, 200, 120) if state == "cached" else (230, 170, 60)
        if state.startswith("retry") or state == "generation failed":
            colour = (220, 80, 80)
        r = max(4, band_h // 8)
        draw.ellipse([w - 3 * r, h - band_h / 2 - r, w - r, h - band_h / 2 + r], fill=colour)
        return np.array(base)

    def show(self, frame):
        self.renderer.render(frame)

    # -- favourites -----------------------------------------------------------

    def save_favourite(self):
        entry = self.scheduler.cached_entry(self.prompt, self.size, self.seed)
        cache_key = self.scheduler.cache_key(self.prompt, self.size, self.seed)
        identity_key = self.scheduler.identity_key()

        data = []
        if self.favourites_path.exists():
            try:
                data = json.loads(self.favourites_path.read_text())
                if not isinstance(data, list):
                    data = []
            except Exception as e:
                self.logger.warning(
                    f"Favourites file unreadable ({e}); starting a new list "
                    f"(existing file left as favourites.json.bak)"
                )
                try:
                    self.favourites_path.with_suffix(".json.bak").write_text(
                        self.favourites_path.read_text()
                    )
                except OSError:
                    pass
                data = []

        for existing in data:
            if (
                existing.get("cache_key") == cache_key
                and existing.get("identity_key") == identity_key
            ):
                self.logger.info(f"Seed {self.seed} is already a favourite.")
                self.last_status = "already saved"
                return False

        data.append(
            {
                "seed": self.seed,
                "prompt": self.prompt,
                "size": list(self.size),
                "identity": self.scheduler.identity(),
                "identity_key": identity_key,
                "cache_key": cache_key,
                "image_path": entry.get("path") if entry else None,
                "metadata": entry.get("metadata") if entry else None,
                "saved_at": time.time(),
            }
        )
        self.favourites_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.favourites_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(self.favourites_path)
        self.last_status = "saved favourite"
        self.logger.info(f"Saved favourite seed {self.seed}.")
        return True

    # -- input ----------------------------------------------------------------

    def _key(self, name):
        return bool(self.keyboard.is_key_pressed(name))

    def _edge(self, key, pressed):
        """True only on the frame a key transitions from released to pressed."""
        was = self._held.get(key, False)
        self._held[key] = pressed
        return pressed and not was

    def _repeat(self, key, now):
        """Deliberate key repeat: immediate, then delay, then fixed interval."""
        nxt = self._repeat_next.get(key)
        if nxt is None:
            self._repeat_next[key] = now + self.repeat_delay_s
            return True
        if now >= nxt:
            # At most one step per frame; next is scheduled from *now* so the
            # rate does not accelerate when frames are slow.
            self._repeat_next[key] = now + self.repeat_interval_s
            return True
        return False

    def _handle_keys(self, now=None) -> bool:
        """Process one frame of input. Returns False when asked to quit."""
        now = self._clock() if now is None else now

        if self._edge("q", self._key("q")):
            return False

        if self._edge(" ", self._key(" ")):
            step = random.randint(1, 50) * random.choice((1, -1))
            self.seed = max(0, self.seed + step)
            self.logger.info(f"Random jump -> seed {self.seed}")

        if self._edge("s", self._key("s")):
            self.save_favourite()

        if self._edge("a", self._key("a")):
            self._prefetch_on = not self._prefetch_on
            self.last_status = f"prefetch {'on' if self._prefetch_on else 'off'}"
            self.logger.info(f"Prefetch {'on' if self._prefetch_on else 'off'}")

        if self._edge("c", self._key("c")):
            self._help_on = not self._help_on

        # Navigation: one axis at a time, with repeat timing.
        axis, step = None, 0
        for key, delta in NAV_KEYS.items():
            if self._key(key):
                axis, step = key, delta
                break
        for key in NAV_KEYS:
            if key != axis:
                self._repeat_next.pop(key, None)
        if axis is not None and self._repeat(axis, now):
            self.seed = max(0, self.seed + step)
            self.logger.info(f"Seed -> {self.seed}")

        # MIDI dial: one step per CC change.
        cc = self.midi.get(20)
        if cc is not None:
            if self._last_cc20 is None:
                self._last_cc20 = cc
            elif cc != self._last_cc20:
                self.seed = max(0, self.seed + (1 if cc > self._last_cc20 else -1))
                self._last_cc20 = cc
                self.logger.info(f"Dial -> seed {self.seed}")

        # MIDI favourite: rising edge only; holding the control writes once.
        cc21 = self.midi.get(21)
        if cc21 is not None:
            if cc21 > 0.5 and not self._cc21_fired:
                self._cc21_fired = True
                self.save_favourite()
            elif cc21 <= 0.5:
                self._cc21_fired = False

        return True

    # -- main loop ------------------------------------------------------------

    def run(self):
        self.logger.info(
            "Seed Surfer | +/- seed, left/right jump10, space random, "
            "s save, a prefetch toggle, c help, q quit"
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
        while not self._stop and self._tick():
            time.sleep(self.frame_interval_s)

    def stop(self):
        self._stop = True

    def _request_current(self, now):
        if now < self._error_until:
            return
        # request() is idempotent: cached / queued / in-flight keys are no-ops.
        self.scheduler.request(self.prompt, self.size, self.seed)

    def _request_prefetch(self):
        if not self._prefetch_on:
            return
        for neighbour in (self.seed - 1, self.seed + 1):
            if neighbour >= 0:
                self.scheduler.request_prefetch(self.prompt, self.size, neighbour)

    def _tick(self, now=None) -> bool:
        """One interaction frame. Returns False when the visitor quits."""
        now = self._clock() if now is None else now

        if self.manager.main_queue is not None:
            try:
                self.manager.main_queue.drain()
            except Exception as e:
                self.logger.debug(f"main_queue drain failed: {e}")

        if not self._handle_keys(now):
            return False

        status = self.scheduler.status()
        frame = self._load_frame(self.seed)

        if frame is not None:
            self._last_frame = frame
            self._last_frame_seed = self.seed
            state = "cached"
            shown_seed = self.seed
            self._request_prefetch()
        else:
            self._request_current(now)
            status = self.scheduler.status()
            shown_seed = self._last_frame_seed
            base = self._last_frame if self._last_frame is not None else self._blank_frame()
            if now < self._error_until:
                remain = max(1, math.ceil(self._error_until - now))
                state = f"generation failed — retrying in {remain}s"
            elif status.get("inflight_seed") == self.seed:
                state = "generating…"
            elif status.get("pending_seed") == self.seed:
                state = "queued…"
            else:
                state = "waiting for generator…"
            frame = base

        self.last_status = state
        self._present(frame, self.seed, shown_seed, state)
        return True

    def _present(self, frame, selected_seed, shown_seed, state):
        sig = (shown_seed, selected_seed, state, self._help_on)
        if sig == self._last_render_sig:
            return  # nothing changed; save a blit per frame
        self._last_render_sig = sig
        self.show(self._compose(frame, selected_seed, shown_seed, state))


def main():
    from src.lunar_tools_art import Manager

    manager = Manager()
    surfer = SeedSurfer(manager)
    surfer.run()


if __name__ == "__main__":
    main()
