"""Deterministic interaction tests for Seed Surfer.

No hardware, no ML, no network. A fake generator writes real PNG files, so
every displayed frame passes through the same decode path as mflux output.

These tests pin the behaviours that make the dial playable:
  * identical pending/in-flight requests are deduplicated (one generation),
  * unchanged cached PNGs are decoded once (bounded frame cache),
  * space/s/a and MIDI CC21 are edge-triggered (holding does one action),
  * seed navigation repeats on a deliberate clock, not per frame,
  * the current image is preserved while an uncached neighbour generates,
  * stale results never replace the display,
  * prefetch yields to user requests and warms both neighbours,
  * a failing generator backs off instead of being hammered.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from prototypes.seed_surfer import SeedSurfer
from src.lunar_tools_art.seed_scheduler import SeedScheduler
from src.lunar_tools_art.tools.display import Renderer

PROMPT = "test cosmic scene"
SIZE = (64, 64)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeKeys:
    def __init__(self):
        self.pressed = set()

    def is_key_pressed(self, key):
        return key in self.pressed

    def hold(self, *keys):
        self.pressed.update(keys)

    def release(self, *keys):
        self.pressed.difference_update(keys)


class FakeMidi:
    """Integer-CC interface; TypeError on the legacy keyword form."""

    def __init__(self):
        self.values = {}

    def get(self, control, default=0.0):
        assert isinstance(control, int), f"MIDI control must be int, got {control!r}"
        return self.values.get(control, default)


class FakeClock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class FakeGen:
    """Writes a real 64x64 PNG (seed-dependent gradient) and counts calls."""

    def __init__(self, out_dir: Path, latency=0.0, fail_seeds=()):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.latency = latency
        self.fail_seeds = set(fail_seeds)
        self.calls = []
        self._lock = threading.Lock()

    def identity(self):
        return {"backend": "fake", "model": "fake-1", "model_revision": "rev1"}

    def generate(self, prompt, size=(64, 64), seed=None):
        with self._lock:
            self.calls.append((prompt, tuple(size), seed))
        if self.latency:
            time.sleep(self.latency)
        if seed in self.fail_seeds:
            raise RuntimeError(f"boom for seed {seed}")
        w, h = size
        yy, xx = np.mgrid[0:h, 0:w]
        arr = np.dstack(
            [
                ((xx + (seed or 0) * 7) % 256).astype(np.uint8),
                ((yy + (seed or 0) * 3) % 256).astype(np.uint8),
                np.full((h, w), 90, dtype=np.uint8),
            ]
        )
        path = self.out_dir / f"seed_{seed}_{w}x{h}.png"
        Image.fromarray(arr).save(path)
        return str(path), {"backend": "fake", "seed": seed}

    def seeds_generated(self):
        with self._lock:
            return [c[2] for c in self.calls]


class FakeManager:
    def __init__(self, gen, keys=None, midi=None, width=64, height=64):
        self.renderer = Renderer(width=width, height=height, backend="null")
        self.keyboard_input = keys or FakeKeys()
        self.midi_input = midi or FakeMidi()
        self.main_queue = None
        self.image_gen = gen
        self.logger = logging.getLogger("seed_surfer_test")


_SURFERS = []


@pytest.fixture(autouse=True)
def _stop_background_schedulers():
    yield
    while _SURFERS:
        _SURFERS.pop().scheduler.stop()


def make_surfer(tmp_path, gen, keys=None, midi=None, clock=None, **kw):
    manager = FakeManager(gen, keys, midi)
    surfer = SeedSurfer(
        manager,
        prompt=PROMPT,
        size=SIZE,
        start_seed=5,
        image_dir=str(tmp_path / "images"),
        favourites_path=tmp_path / "favourites.json",
        clock=clock,
        **kw,
    )
    surfer.scheduler.start()
    _SURFERS.append(surfer)
    return surfer, manager


def wait_until(predicate, timeout=5.0, interval=0.01):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def generate_direct(surfer, seed):
    """Populate the cache through the scheduler, without the display loop."""
    surfer.scheduler.request(PROMPT, SIZE, seed)
    entry = surfer.scheduler.wait_for(PROMPT, SIZE, seed, timeout=10)
    assert entry is not None
    return entry


@pytest.fixture
def gen(tmp_path):
    return FakeGen(tmp_path / "pngs")


# ---------------------------------------------------------------------------
# Request deduplication
# ---------------------------------------------------------------------------


def test_scheduler_identical_inflight_requests_are_deduplicated(tmp_path, gen):
    gen.latency = 0.15
    surfer, _ = make_surfer(tmp_path, gen)
    surfer.scheduler.start()
    try:
        surfer.scheduler.request(PROMPT, SIZE, 7)
        assert wait_until(lambda: gen.seeds_generated() == [7])
        for _ in range(60):  # ~1.2 s of a 20 Hz loop hitting the same seed
            surfer.scheduler.request(PROMPT, SIZE, 7)
            time.sleep(0.02)
        assert wait_until(
            lambda: surfer.scheduler.cached_entry(PROMPT, SIZE, 7) is not None
        )
        time.sleep(0.2)  # any redundant queued job would run here
        assert gen.seeds_generated() == [7]
        assert surfer.scheduler.status()["errors"] == 0
    finally:
        surfer.scheduler.stop()


def test_loop_does_not_regenerate_after_completion(tmp_path, gen):
    gen.latency = 0.05
    surfer, _ = make_surfer(tmp_path, gen)
    surfer.scheduler.start()
    try:
        for i in range(80):  # 4 s at 20 Hz, same seed
            surfer._tick(now=i * 0.05)
            time.sleep(0.01)
            if i == 20 and surfer._load_frame(5) is not None:
                break
        assert wait_until(lambda: surfer._load_frame(5) is not None)
        for i in range(20):
            surfer._tick(now=10 + i * 0.05)
        assert gen.seeds_generated().count(5) == 1
    finally:
        surfer.scheduler.stop()


def test_scheduler_request_on_cached_key_is_noop(tmp_path, gen):
    surfer, _ = make_surfer(tmp_path, gen)
    generate_direct(surfer, 3)
    before = len(gen.calls)
    for _ in range(10):
        assert surfer.scheduler.request(PROMPT, SIZE, 3) is None
    time.sleep(0.1)
    assert len(gen.calls) == before


# ---------------------------------------------------------------------------
# Decoded-frame cache
# ---------------------------------------------------------------------------


def test_cached_navigation_decodes_each_png_once(tmp_path, gen):
    surfer, manager = make_surfer(tmp_path, gen)
    generate_direct(surfer, 5)
    generate_direct(surfer, 6)
    surfer.decodes = 0
    surfer.cache_hits = 0
    surfer.cache_misses = 0

    for seed in (5, 6, 5, 6, 5, 6):
        surfer.seed = seed
        assert surfer._tick(now=0.0)
    assert surfer.decodes == 2, "each cached PNG must be decoded exactly once"
    assert surfer.cache_hits == 4
    assert gen.seeds_generated().count(5) == 1
    assert gen.seeds_generated().count(6) == 1


def test_frame_cache_is_bounded(tmp_path):
    gen = FakeGen(tmp_path / "pngs")
    surfer, _ = make_surfer(tmp_path, gen, frame_cache_size=3)
    for seed in range(1, 6):
        generate_direct(surfer, seed)
        surfer.seed = seed
        surfer._tick(now=0.0)
    assert len(surfer._frame_cache) == 3
    assert surfer.evictions == 2


def test_cached_frame_latency_is_interactive(tmp_path, gen):
    surfer, _ = make_surfer(tmp_path, gen)
    generate_direct(surfer, 5)
    surfer.seed = 5
    surfer._tick(now=0.0)  # warm
    t0 = time.perf_counter()
    for i in range(100):
        surfer._tick(now=i * 0.05)
    elapsed = time.perf_counter() - t0
    assert elapsed < 1.0, f"100 cached frames took {elapsed:.3f}s"
    assert gen.seeds_generated().count(5) == 1


# ---------------------------------------------------------------------------
# Edge-triggered controls
# ---------------------------------------------------------------------------


def test_holding_s_saves_one_favourite(tmp_path, gen):
    keys = FakeKeys()
    surfer, _ = make_surfer(tmp_path, gen, keys=keys)
    generate_direct(surfer, 5)
    keys.hold("s")
    for i in range(15):
        surfer._tick(now=i * 0.05)
    data = json.loads(surfer.favourites_path.read_text())
    assert len(data) == 1
    assert data[0]["seed"] == 5
    assert data[0]["cache_key"] and data[0]["identity_key"]


def test_holding_a_toggles_prefetch_once(tmp_path, gen):
    keys = FakeKeys()
    surfer, _ = make_surfer(tmp_path, gen, keys=keys)
    generate_direct(surfer, 5)
    assert surfer._prefetch_on is True
    keys.hold("a")
    for i in range(10):
        surfer._tick(now=i * 0.05)
    assert surfer._prefetch_on is False


def test_holding_space_jumps_once(tmp_path, gen):
    keys = FakeKeys()
    surfer, _ = make_surfer(tmp_path, gen, keys=keys)
    generate_direct(surfer, 5)
    keys.hold(" ")
    surfer._tick(now=0.0)
    after_first = surfer.seed
    assert after_first != 5
    for i in range(1, 10):
        surfer._tick(now=i * 0.05)
    assert surfer.seed == after_first, "held space must not keep jumping"


def test_midi_favourite_is_rising_edge_only(tmp_path, gen):
    midi = FakeMidi()
    surfer, _ = make_surfer(tmp_path, gen, midi=midi)
    generate_direct(surfer, 5)
    midi.values[21] = 1.0
    for i in range(12):  # held high: exactly one save
        surfer._tick(now=i * 0.05)
    assert len(json.loads(surfer.favourites_path.read_text())) == 1

    midi.values[21] = 0.0
    surfer._tick(now=1.0)  # release
    # A second press on a different seed saves a second, distinct favourite.
    generate_direct(surfer, 6)
    surfer.seed = 6
    midi.values[21] = 1.0
    surfer._tick(now=1.1)  # press again
    data = json.loads(surfer.favourites_path.read_text())
    assert [d["seed"] for d in data] == [5, 6]


def test_midi_dial_moves_one_seed_per_cc_step(tmp_path, gen):
    midi = FakeMidi()
    surfer, _ = make_surfer(tmp_path, gen, midi=midi)
    generate_direct(surfer, 5)
    midi.values[20] = 0.5
    surfer._tick(now=0.0)  # establishes baseline, no move
    assert surfer.seed == 5
    midi.values[20] = 0.6
    surfer._tick(now=0.05)
    assert surfer.seed == 6
    midi.values[20] = 0.4
    surfer._tick(now=0.10)
    assert surfer.seed == 5


# ---------------------------------------------------------------------------
# Deliberate key repeat
# ---------------------------------------------------------------------------


def test_key_repeat_uses_time_not_frames(tmp_path, gen):
    keys = FakeKeys()
    clock = FakeClock()
    surfer, _ = make_surfer(tmp_path, gen, keys=keys, clock=clock,
                            repeat_delay_s=0.3, repeat_interval_s=0.08)
    generate_direct(surfer, 10)
    surfer.seed = 10

    keys.hold("up")
    surfer._tick(now=0.0)
    assert surfer.seed == 11  # immediate press
    surfer._tick(now=0.10)
    assert surfer.seed == 11, "inside the repeat delay"
    surfer._tick(now=0.29)
    assert surfer.seed == 11, "still inside the repeat delay"
    surfer._tick(now=0.31)
    assert surfer.seed == 12, "first repeat after the delay"
    surfer._tick(now=0.35)
    assert surfer.seed == 12, "faster frames must not step faster"
    surfer._tick(now=0.40)
    assert surfer.seed == 13
    surfer._tick(now=0.50)
    assert surfer.seed == 14

    keys.release("up")
    surfer._tick(now=0.55)
    keys.hold("up")
    surfer._tick(now=0.56)
    assert surfer.seed == 15, "re-press steps immediately"


def test_dense_frames_do_not_accelerate_navigation(tmp_path, gen):
    keys = FakeKeys()
    clock = FakeClock()
    surfer, _ = make_surfer(tmp_path, gen, keys=keys, clock=clock)
    generate_direct(surfer, 10)
    surfer.seed = 10
    keys.hold("right")
    surfer._tick(now=0.0)
    assert surfer.seed == 20
    for i in range(1, 40):  # 200 Hz frames for 0.2 s
        clock.now = i * 0.005
        surfer._tick(now=clock.now)
    assert surfer.seed == 20, "held key inside the repeat delay must not repeat"
    clock.now = 0.31
    surfer._tick(now=clock.now)
    assert surfer.seed == 30


# ---------------------------------------------------------------------------
# Display while generating; stale handling
# ---------------------------------------------------------------------------


def test_uncached_neighbour_preserves_current_image(tmp_path, gen):
    surfer, manager = make_surfer(tmp_path, gen)
    generate_direct(surfer, 5)
    surfer.seed = 5
    surfer._tick(now=0.0)
    assert surfer._last_frame_seed == 5

    gen.latency = 0.4  # next seed will take a while
    surfer.seed = 6
    surfer._tick(now=0.05)

    assert surfer._last_frame_seed == 5, "last good image must stay on screen"
    assert "6" in surfer.last_status_line, surfer.last_status_line
    assert "generating" in surfer.last_status_line or "queued" in surfer.last_status_line
    shown = manager.renderer.frames[-1]
    assert shown.shape == (64, 64, 3)
    assert shown.mean() > 5, "must not blank the canvas while generating"
    # Overlay only touches the bottom band: the artwork above is preserved.
    top = shown[:40]
    assert top.std() > 5 and top.mean() > 5

    # And the status line is a generation state, not 'cached'.
    assert surfer.last_status != "cached"


def test_stale_result_is_cached_but_not_displayed(tmp_path):
    gen = FakeGen(tmp_path / "pngs", latency=0.35)
    surfer, manager = make_surfer(tmp_path, gen)
    surfer.scheduler.start()
    try:
        generate_direct(surfer, 40)  # a known base image to display
        surfer.seed = 41
        surfer._tick(now=0.0)  # starts generating 41
        assert wait_until(lambda: surfer.scheduler.status()["inflight_seed"] == 41)

        # Navigate to an uncached seed: 41 becomes stale.
        gen.latency = 0.05
        surfer.seed = 42
        surfer._tick(now=0.01)
        assert wait_until(
            lambda: surfer.scheduler.cached_entry(PROMPT, SIZE, 42) is not None
        )
        wait_until(lambda: surfer.scheduler.status()["inflight_seed"] is None)
        surfer._tick(now=0.2)
        assert surfer._last_frame_seed == 42
        assert surfer.scheduler.discarded_stale == 1
        # The stale image is still a valid cache entry, just not displayed.
        assert surfer.scheduler.cached_entry(PROMPT, SIZE, 41) is not None
        assert manager.renderer.frames  # something was drawn
    finally:
        surfer.scheduler.stop()


# ---------------------------------------------------------------------------
# Prefetch priority
# ---------------------------------------------------------------------------


def test_prefetch_yields_while_user_request_outstanding(tmp_path, gen):
    gen.latency = 0.2
    surfer, _ = make_surfer(tmp_path, gen)
    surfer.scheduler.start()
    try:
        surfer.scheduler.request(PROMPT, SIZE, 100)
        assert wait_until(lambda: surfer.scheduler.status()["inflight_seed"] == 100)
        assert surfer.scheduler.request_prefetch(PROMPT, SIZE, 101) is None
        assert surfer.scheduler.status()["prefetch_seed"] is None
    finally:
        surfer.scheduler.stop()


def test_prefetch_warms_both_neighbours_without_starvation(tmp_path, gen):
    gen.latency = 0.05
    surfer, _ = make_surfer(tmp_path, gen)
    surfer.scheduler.start()
    try:
        generate_direct(surfer, 20)
        surfer.seed = 20
        deadline = time.time() + 6
        while time.time() < deadline:
            surfer._tick(now=time.monotonic())
            if (
                surfer.scheduler.cached_entry(PROMPT, SIZE, 19) is not None
                and surfer.scheduler.cached_entry(PROMPT, SIZE, 21) is not None
            ):
                break
            time.sleep(0.02)
        assert surfer.scheduler.cached_entry(PROMPT, SIZE, 19) is not None
        assert surfer.scheduler.cached_entry(PROMPT, SIZE, 21) is not None
        assert gen.seeds_generated().count(19) == 1
        assert gen.seeds_generated().count(21) == 1
    finally:
        surfer.scheduler.stop()


# ---------------------------------------------------------------------------
# Error recovery and favourites preservation
# ---------------------------------------------------------------------------


def test_failed_generation_backs_off_then_recovers(tmp_path):
    clock = FakeClock()
    gen = FakeGen(tmp_path / "pngs", fail_seeds={77})
    surfer, manager = make_surfer(tmp_path, gen, clock=clock)
    surfer.scheduler.start()
    try:
        generate_direct(surfer, 5)
        surfer.seed = 5
        surfer._tick(now=0.0)

        surfer.seed = 77
        clock.now = 0.1
        surfer._tick(now=clock.now)
        assert wait_until(lambda: surfer.scheduler.errors == 1)
        surfer._tick(now=clock.now)  # display the backoff state
        assert "retry" in surfer.last_status
        # Backoff: 20 ticks inside one second must not retry.
        for _ in range(20):
            clock.advance(0.04)
            surfer._tick(now=clock.now)
        assert gen.seeds_generated().count(77) == 1
        assert manager.renderer.frames, "error state must still render"

        # The preserved image is still on screen.
        assert surfer._last_frame_seed == 5

        # After the backoff and a working backend, it recovers.
        gen.fail_seeds.clear()
        clock.advance(1.1)
        surfer._tick(now=clock.now)
        assert wait_until(
            lambda: surfer.scheduler.cached_entry(PROMPT, SIZE, 77) is not None
        )
        surfer._tick(now=clock.now + 0.2)
        assert surfer._last_frame_seed == 77
        assert surfer.last_status == "cached"
    finally:
        surfer.scheduler.stop()


def test_save_favourite_preserves_existing_file(tmp_path, gen):
    surfer, _ = make_surfer(tmp_path, gen)
    generate_direct(surfer, 5)
    existing = [{"seed": 1, "prompt": "old", "cache_key": "old"}]
    surfer.favourites_path.write_text(json.dumps(existing))
    surfer.seed = 5
    assert surfer.save_favourite() is True
    data = json.loads(surfer.favourites_path.read_text())
    assert data[0] == existing[0]
    assert data[-1]["seed"] == 5


def test_save_favourite_is_idempotent_per_identity(tmp_path, gen):
    surfer, _ = make_surfer(tmp_path, gen)
    generate_direct(surfer, 5)
    surfer.seed = 5
    assert surfer.save_favourite() is True
    assert surfer.save_favourite() is False
    assert len(json.loads(surfer.favourites_path.read_text())) == 1


def test_generator_returning_missing_png_is_an_error(tmp_path):
    def broken(prompt, size, seed):
        return str(tmp_path / "does-not-exist.png"), {"seed": seed}

    sched = SeedScheduler(
        broken,
        cache_index_path=tmp_path / "index.json",
    )
    sched.start()
    try:
        sched.request("p", SIZE, 1)
        assert wait_until(lambda: sched.errors == 1)
        assert sched.cached_entry("p", SIZE, 1) is None
        assert sched.status()["desired_seed"] is None
    finally:
        sched.stop()
