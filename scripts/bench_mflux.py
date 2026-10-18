#!/usr/bin/env python3
"""Benchmark real local mflux generation at 512² and 1024² on this Studio.

Cold start (weight load + first render) is reported separately from warm
renders. Peak MLX memory is read from mx.get_peak_memory().

Usage:
  env -u PYTHONPATH env/bin/python scripts/bench_mflux.py
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

OUT = ROOT / "outputs/benchmarks"
PROMPT = "A vast cosmic scene with galaxies, nebulae and stars, painterly"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default="512,1024")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--steps", type=int, default=4)
    args = ap.parse_args()

    from PIL import Image

    from src.lunar_tools_art.tools.images import ImageGenerator, mflux_snapshot_path

    OUT.mkdir(parents=True, exist_ok=True)
    gen = ImageGenerator(
        backend="mflux", model="schnell", quantize=4, steps=args.steps,
        model_path=mflux_snapshot_path("schnell"),
        output_dir=str(OUT),
    )
    identity = gen.identity()
    print(json.dumps({"identity": identity}, indent=2))

    records = []
    cold = True
    seed = 1000
    for size_s in args.sizes.split(","):
        n = int(size_s.strip())
        for run in range(args.runs):
            seed += 1
            t0 = time.time()
            path, meta = gen.generate(PROMPT, size=(n, n), seed=seed)
            wall = time.time() - t0
            p = Path(path)
            with Image.open(p) as im:
                dims = list(im.size)
            assert dims == [n, n], f"expected {n}x{n}, got {dims}"
            record = {
                "size": [n, n],
                "run": run,
                "phase": "cold" if cold else "warm",
                "seed": meta["seed"],
                "wall_s": round(wall, 3),
                "adapter_latency_s": round(meta["latency_s"], 3),
                "bytes": p.stat().st_size,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                "path": str(p.relative_to(ROOT)),
                "identity_key": meta["identity_key"],
            }
            try:
                import mlx.core as mx

                record["peak_mlx_memory_gb"] = round(mx.get_peak_memory() / 1e9, 2)
            except Exception:
                pass
            records.append(record)
            print(json.dumps(record))
            cold = False

    summary = {
        "generated_at": time.time(),
        "machine": "Apple M5 Ultra 256 GB, macOS 27.0.1",
        "model": identity,
        "prompt": PROMPT,
        "records": records,
        "warm_mean_s": {
            f"{r['size'][0]}": round(
                sum(x["wall_s"] for x in records
                    if x["size"] == r["size"] and x["phase"] == "warm")
                / max(1, sum(1 for x in records
                              if x["size"] == r["size"] and x["phase"] == "warm")),
                3,
            )
            for r in records
        },
    }
    (OUT / "benchmark.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary["warm_mean_s"], indent=2))


if __name__ == "__main__":
    main()
