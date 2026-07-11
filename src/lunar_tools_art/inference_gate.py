"""Process-wide gate serializing heavy MLX inference to bound unified-memory pressure."""

import threading

INFERENCE_LOCK = threading.Lock()
