#!/usr/bin/env python3
"""Verify Seed Surfer against a real local mflux backend.

Proves, with real inference:
  * different seeds produce different images,
  * a repeated seed is served from cache without another generation,
  * the cache key carries model identity/revision/settings (a revision change
    cannot serve a stale image),
  * favourites record identity + generation metadata,
  * scheduling is bounded latest-wins under rapid input,
  * keyboard controls update state responsively.

Usage:
  env -u PYTHONPATH env/bin/python scripts/verify_seed_surfer.py --seeds 4
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "outputs/seed_surfer"
PROMPT = "A vast cosmic scene with galaxies, nebulae and stars, painterly"


class NullKeys:
    def __init__(self, sequence=()):
        self.sequence = list(sequence)

    def is_key_pressed(self, key):
        if self.sequence and self.sequence[0] == key:
            self.sequence.pop(0)
            return True
        return False


class NullMidi:
    def get(self, _cc):
        return 0


class HeadlessManager:
    def __init__(self, image_gen, keys=None):
        from src.lunar_tools_art.tools.display import Renderer

        self.renderer = Renderer(width=512, height=512, backend="null")
        self.keyboard_input = NullKeys(keys or [])
        self.midi_input = NullMidi()
        self.main_queue = None
        self.image_gen = image_gen
        import logging

        self.logger = logging.getLogger("verify_seed_surfer")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=4)
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--steps", type=int, default=4)
    ap.add_argument("--seed-start", type=int, default=42)
    ap.add_argument("--backend", default="mflux", choices=("mflux", "fake"))
    args = ap.parse_args()

    from src.lunar_tools_art.tools.images import ImageGenerator, mflux_snapshot_path
    from prototypes.seed_surfer import SeedSurfer

    OUT.mkdir(parents=True, exist_ok=True)
    gen = ImageGenerator(
        backend=args.backend, model="schnell", quantize=4, steps=args.steps,
        model_path=mflux_snapshot_path("schnell") if args.backend == "mflux" else None,
        output_dir=str(OUT / "images"),
    )
    identity = gen.identity()
    print(json.dumps({"identity": identity}, indent=2))

    manager = HeadlessManager(gen)
    surfer = SeedSurfer(
        manager, prompt=PROMPT, size=(args.size, args.size),
        start_seed=args.seed_start,
        image_dir=str(OUT / "images"),
    )
    surfer.scheduler.start()
    try:
        results = []
        for i in range(args.seeds):
            seed = args.seed_start + i
            t0 = time.time()
            surfer.scheduler.request(PROMPT, surfer.size, seed)
            entry = surfer.scheduler.wait_for(PROMPT, surfer.size, seed, timeout=600)
            dt = time.time() - t0
            assert entry, f"no result for seed {seed}"
            p = Path(entry["path"])
            min_bytes = 10_000 if args.backend == "mflux" else 50
            assert p.exists() and p.stat().st_size >= min_bytes, "image looks empty"
            results.append({
                "seed": seed,
                "path": str(p.relative_to(ROOT)) if str(p).startswith(str(ROOT)) else str(p),
                "latency_s": round(dt, 3),
                "sha256": sha(p),
                "bytes": p.stat().st_size,
                "identity_key": entry.get("identity_key"),
            })
            print(f"seed {seed}: {dt:.2f}s {p.stat().st_size} bytes")

        # cache hit: same seed, same identity, no new lookup cost
        t0 = time.time()
        entry = surfer.scheduler.cached_entry(PROMPT, surfer.size, args.seed_start)
        cache_lookup_s = time.time() - t0
        assert entry is not None

        # identity guard: pretend the model revision changed
        saved_identity = surfer.scheduler._identity
        spoofed = dict(identity, model_revision="different-revision-for-test")
        surfer.scheduler._identity = spoofed
        stale = surfer.scheduler.cached_entry(PROMPT, surfer.size, args.seed_start)
        surfer.scheduler._identity = saved_identity
        identity_guard = {
            "cached_entry_after_revision_change": stale,
            "stale_cache_blocked": stale is None,
        }

        # favourites carry identity + metadata
        surfer.seed = args.seed_start
        surfer.save_favourite()
        fav_path = Path("outputs/seed_surfer/favourites.json")
        fav_data = json.loads(fav_path.read_text())
        favourite = fav_data[-1]
        favourite_ok = bool(
            favourite.get("identity_key")
            and favourite.get("metadata")
            and (args.backend != "mflux"
                 or favourite.get("identity", {}).get("model_revision"))
        )

        # bounded scheduling: rapid requests must not queue up a backlog
        calls = []
        original = surfer._generate

        def counting_generate(prompt, size, seed):
            calls.append(seed)
            return original(prompt, size, seed)

        surfer._generate = counting_generate
        # rebind the scheduler's callable for this check
        surfer.scheduler._generate = counting_generate
        for seed in range(args.seed_start + 100, args.seed_start + 108):
            surfer.scheduler.request(PROMPT, surfer.size, seed)
        final_seed = args.seed_start + 107
        last = surfer.scheduler.wait_for(PROMPT, surfer.size, final_seed, timeout=600)
        time.sleep(2.0)
        bounded = {
            "requests": 8,
            "generations": len(calls),
            "last_seed_delivered": final_seed if last else None,
            "cancelled": surfer.scheduler.cancelled_count,
            "bounded_ok": len(calls) <= 3,
        }

        # responsive controls: seed step must be immediate (no generation wait)
        surfer.seed = args.seed_start
        before = surfer.seed
        manager.keyboard_input.sequence = ["right"]
        t0 = time.time()
        surfer._handle_keys()
        control_latency_ms = (time.time() - t0) * 1000
        controls = {
            "seed_before": before,
            "seed_after": surfer.seed,
            "changed": surfer.seed != before,
            "handler_latency_ms": round(control_latency_ms, 3),
        }

        summary = {
            "generated_at": time.time(),
            "prompt": PROMPT,
            "size": [args.size, args.size],
            "steps": args.steps,
            "identity": identity,
            "identity_key": surfer.scheduler.identity_key(),
            "results": results,
            "distinct_images": len({r["sha256"] for r in results}) == len(results),
            "cache_hit": {"entry_path": entry["path"], "lookup_s": cache_lookup_s},
            "identity_guard": identity_guard,
            "favourite_records_identity": favourite_ok,
            "bounded_scheduling": bounded,
            "controls": controls,
        }
        (OUT / "verification.json").write_text(json.dumps(summary, indent=2))
        print(json.dumps({k: v for k, v in summary.items() if k != "results"}, indent=2))
    finally:
        surfer.scheduler.stop()


if __name__ == "__main__":
    main()
