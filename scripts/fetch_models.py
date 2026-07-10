#!/usr/bin/env python3
"""Download ML model weights used by shared infrastructure into models/.

Currently fetches the FER+ emotion classifier (emotion-ferplus-8.onnx) from
the official onnx/models GitHub release and verifies its SHA-256 checksum
before writing it to disk.

Run on-machine (not in CI, not under LUNAR_HEADLESS):

    python scripts/fetch_models.py
"""

import hashlib
import sys
import urllib.request
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"

# Official onnx/models release asset for the FER+ emotion classifier.
# https://github.com/onnx/models/tree/main/validated/vision/body_analysis/emotion_ferplus
FERPLUS_URL = (
    "https://github.com/onnx/models/raw/main/validated/vision/body_analysis/"
    "emotion_ferplus/model/emotion-ferplus-8.onnx"
)
# NOTE: placeholder checksum — this script has intentionally NOT been run.
# Before first real use, download the file once via a trusted channel,
# compute `shasum -a 256 models/emotion-ferplus-8.onnx`, and replace this
# value. The script will refuse to install the model on a mismatch.
FERPLUS_SHA256 = "0000000000000000000000000000000000000000000000000000000000000"
FERPLUS_FILENAME = "emotion-ferplus-8.onnx"

MODELS = [
    {
        "name": "FER+ emotion classifier",
        "url": FERPLUS_URL,
        "filename": FERPLUS_FILENAME,
        "sha256": FERPLUS_SHA256,
    },
]


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(model: dict) -> bool:
    dest = MODELS_DIR / model["filename"]
    if dest.exists():
        digest = sha256_of(dest)
        if digest == model["sha256"]:
            print(f"[skip] {model['name']}: already present and verified at {dest}")
            return True
        print(
            f"[warn] {model['name']}: existing file at {dest} has unexpected "
            f"checksum ({digest}); re-downloading."
        )

    print(f"[fetch] {model['name']} <- {model['url']}")
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    tmp_dest = dest.with_suffix(dest.suffix + ".part")
    try:
        urllib.request.urlretrieve(model["url"], tmp_dest)  # noqa: S310
    except Exception as e:
        print(f"[error] {model['name']}: download failed: {e}")
        return False

    digest = sha256_of(tmp_dest)
    if digest != model["sha256"]:
        print(
            f"[error] {model['name']}: checksum mismatch "
            f"(expected {model['sha256']}, got {digest}); refusing to install."
        )
        tmp_dest.unlink(missing_ok=True)
        return False

    tmp_dest.rename(dest)
    print(f"[ok] {model['name']}: verified and saved to {dest}")
    return True


def main() -> int:
    ok = True
    for model in MODELS:
        ok = fetch(model) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
