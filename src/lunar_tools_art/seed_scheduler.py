"""Seed Surfer generation scheduler.

A single bounded worker replaces ``ImageGenerator.generate_async`` thread
sprawl (which spawns an unbounded daemon thread per request with no
backpressure, no cancellation and no dedup) for interactive seed navigation.

Contract:
- At most ONE generation thread runs at a time (single worker; the global
  ``INFERENCE_LOCK`` additionally serialises heavy MLX across stacks).
- **Latest-request-wins**: at most one *queued* user request is retained;
  a newer request supersedes it immediately.
- **Deduplication**: identical ``(prompt, size, seed)`` requests collapse
  while queued.
- **Cancellation**: pending jobs are cancelled by supersession; in-flight
  work cannot be killed thread-wise, so its result is *discarded as stale*
  if it no longer matches the desired seed when it completes.
- **Prefetch**: adjacent seeds (seed +/- 1) are generated at lower priority
  only when no user request is waiting; prefetch jobs are also superseded.
- **Persistence**: every successful image is written to the generator's
  PNG path with complete generation metadata (backend, model, seed, size,
  latency, timestamps), and an index entry is recorded so navigation across
  restarts is instant.

Deterministic tests use a fake ``generate`` callable; no ML inference.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class Job:
    __slots__ = ("prompt", "size", "seed", "priority", "seq", "cancelled")

    def __init__(self, prompt, size, seed, priority, seq):
        self.prompt = prompt
        self.size = size
        self.seed = seed
        self.priority = priority  # lower = served first
        self.seq = seq  # submission order; higher = newer
        self.cancelled = False

    @property
    def key(self):
        return (self.prompt, self.size, self.seed)


class SeedScheduler:
    """Single-worker, latest-wins generation scheduler for seed exploration."""

    def __init__(
        self,
        generate,  # callable(prompt, size, seed) -> (png_path, metadata)
        cache_index_path: Path,
        on_success=None,  # callable(job_result_dict) posted from worker thread
        prefetch_radius: int = 1,
        identity=None,  # dict or callable()->dict describing the generator
    ):
        self._generate = generate
        self._cache_index_path = Path(cache_index_path)
        self._on_success = on_success
        self._prefetch_radius = prefetch_radius
        self._identity = identity

        self._lock = threading.Lock()
        self._pending: Job | None = None  # at most one queued user job
        self._prefetch_pending: Job | None = None  # at most one queued prefetch
        self._inflight: Job | None = None
        self._seq = 0
        self._desired = None  # key of the user job the user currently wants
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None
        self.index = self._load_index()

        # stats
        self.completed = 0
        self.discarded_stale = 0
        self.cancelled_count = 0
        self.errors = 0

    # -- cache identity -----------------------------------------------------

    def identity(self) -> dict | None:
        """Resolve the generator identity (dict or zero-arg callable)."""
        ident = self._identity
        if callable(ident):
            try:
                ident = ident()
            except Exception as e:
                logger.warning(f"Cache identity resolution failed: {e}")
                return None
        return ident

    def identity_key(self) -> str:
        ident = self.identity()
        if not ident:
            return "noidentity"
        blob = json.dumps(ident, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]

    def cache_key(self, prompt, size, seed) -> str:
        """Prompt+size+seed is not enough: model/revision/settings must match.

        Without the identity suffix a cached image rendered by another model
        (or another revision of the same model) would be served as if it were
        the current model's output.
        """
        return f"{prompt}|{size[0]}x{size[1]}|{seed}|{self.identity_key()}"

    # -- index persistence --------------------------------------------------

    def _load_index(self):
        if self._cache_index_path.exists():
            try:
                index = json.loads(self._cache_index_path.read_text())
                index.setdefault("entries", {})
                index["version"] = 2
                return index
            except Exception as e:
                logger.warning(f"Corrupt cache index {self._cache_index_path}: {e}")
        return {"entries": {}, "version": 2}

    def cached_entry(self, prompt, size, seed):
        return self.index["entries"].get(self.cache_key(prompt, size, seed))

    # -- public API ----------------------------------------------------------

    def request(self, prompt, size, seed, priority=0):
        """User navigation request. Supersedes any queued request."""
        job = Job(prompt, size, seed, priority, self._next_seq())
        with self._lock:
            superseded = self._pending
            self._pending = job
            # Drop an equal prefetch (a queued prefetch for the same key is
            # now redundant: the user job covers it).
            if self._prefetch_pending and self._prefetch_pending.key == job.key:
                self._prefetch_pending = None
            self._desired = job.key
            if superseded is not None and not superseded.cancelled:
                superseded.cancelled = True
                self.cancelled_count += 1
        self._wake.set()
        return job

    def request_prefetch(self, prompt, size, seed):
        """Lower-priority exploration of neighbouring seeds. Never displaces
        a user request."""
        if self.cached_entry(prompt, size, seed) is not None:
            return None  # already cached; nothing to do
        job = Job(prompt, size, seed, priority=10, seq=self._next_seq())
        with self._lock:
            if self._prefetch_pending is None:
                self._prefetch_pending = job
        self._wake.set()
        return job

    def start(self):
        if self._worker is None:
            self._worker = threading.Thread(
                target=self._run, name="seed-scheduler", daemon=True
            )
            self._worker.start()

    def stop(self, timeout=2.0):
        self._stop.set()
        self._wake.set()
        if self._worker is not None:
            self._worker.join(timeout)

    def wait_for(self, prompt, size, seed, timeout=None):
        """Block until the given key is cached (test helper). Returns entry or None."""
        deadline = time.time() + timeout if timeout else None
        while True:
            entry = self.cached_entry(prompt, size, seed)
            if entry is not None and Path(entry["path"]).exists():
                return entry
            if deadline is not None and time.time() > deadline:
                return None
            time.sleep(0.01)

    # -- internals ------------------------------------------------------------

    def _next_seq(self):
        with self._lock:
            self._seq += 1
            return self._seq

    def _claim_job(self):
        """Pick the next job to run: user job > prefetch job > None."""
        with self._lock:
            job = self._pending
            if job is not None:
                self._pending = None
                self._inflight = job
                return job
            job = self._prefetch_pending
            if job is not None:
                self._prefetch_pending = None
                if self.cached_entry(job.prompt, job.size, job.seed) is None:
                    self._inflight = job
                    return job
        return None

    def _run(self):
        while not self._stop.is_set():
            job = self._claim_job()
            if job is None:
                self._wake.wait(timeout=0.25)
                self._wake.clear()
                continue
            try:
                t0 = time.time()
                png_path, metadata = self._generate(job.prompt, size=job.size, seed=job.seed)
                latency = time.time() - t0
                metadata = dict(metadata or {})
                metadata.update(
                    {
                        "prompt": job.prompt,
                        "size": list(job.size),
                        "seed": job.seed,
                        "latency_s": round(latency, 3),
                        "generated_at": time.time(),
                    }
                )
                with self._lock:
                    # Stale-discard applies only to user (priority-0) jobs: a
                    # prefetch never held the desired key, so it is never stale.
                    stale = (
                        self._inflight is job
                        and job.priority == 0
                        and self._desired is not None
                        and job.key != self._desired
                    )
                    self._inflight = None
                if stale:
                    # Superseded while rendering: record but do not surface.
                    self.discarded_stale += 1
                    logger.info(
                        f"Discarding stale in-flight result seed={job.seed}"
                    )
                entry = self._record(job.prompt, job.size, job.seed, png_path, metadata)
                self.completed += 1
                if not stale and job.priority == 0:
                    # The user's wanted image is now delivered; clear the
                    # desired key so later prefetch work is not misread as stale.
                    with self._lock:
                        if self._desired == job.key:
                            self._desired = None
                if not stale and self._on_success is not None:
                    try:
                        self._on_success(
                            {"prompt": job.prompt, "size": job.size, "seed": job.seed,
                             "path": str(png_path), "metadata": metadata,
                             "priority": job.priority}
                        )
                    except Exception:
                        logger.exception("on_success callback raised")
            except Exception as e:
                self.errors += 1
                logger.error(f"Seed generation failed (seed={job.seed}): {e}")
                with self._lock:
                    self._inflight = None

    def _record(self, prompt, size, seed, png_path, metadata):
        key = self.cache_key(prompt, size, seed)
        identity = self.identity()
        entry = {
            "path": str(png_path),
            "metadata": metadata,
            "identity": identity,
            "identity_key": self.identity_key(),
            "cache_key": key,
        }
        with self._lock:
            self.index["entries"][key] = entry
            data = self.index
        tmp = self._cache_index_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1, default=str))
        tmp.replace(self._cache_index_path)
        return entry