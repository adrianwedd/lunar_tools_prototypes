#!/usr/bin/env python3
"""On-machine smoke test for ImageGenerator (mflux backend).

Generates one real image via local mflux inference and prints the output
path and latency. Run with mflux installed and enough unified memory free
(not under LUNAR_HEADLESS, which would force the `fake` backend):

    python scripts/smoke_imagegen.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lunar_tools_art.tools.images import ImageGenerator  # noqa: E402


def main():
    gen = ImageGenerator(
        backend="mflux", model="schnell", quantize=4, output_dir="outputs/images"
    )

    prompt = "a moon garden at twilight, bioluminescent flowers, wide shot"
    print(f"Generating image for prompt: {prompt!r}")
    start = time.time()
    path, meta = gen.generate(prompt, size=(1024, 1024))
    elapsed = time.time() - start

    print(f"Saved: {path}")
    print(f"Metadata: {meta}")
    print(f"Wall-clock latency: {elapsed:.2f}s")


if __name__ == "__main__":
    main()
