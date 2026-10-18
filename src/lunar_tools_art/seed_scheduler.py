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
        on_error=None,  # callable(prompt, size, seed, exc) posted from worker thread
        prefetch_radius: int = 1,
        identity=None,  # dict or callable()->dict describing the generator
    ):
        self._generate = generate
        self._cache_index_path = Path(cache_index_path)
        self._on_success = on_success
        self._on_error = on_error
        self._prefetch_radius = prefetch_radius
        self._identity = identity

        self._lock = threading.RLock()  # re-entrant: helpers nest under request()
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

    def _is_cached(self, key) -> bool:
        """True when an index entry exists AND its PNG is still on disk."""
        entry = self.index["entries"].get(self.cache_key(*key))
        if not entry:
            return False
        try:
            return Path(entry["path"]).exists()
        except (OSError, TypeError):
            return False

    def status(self) -> dict:
        """Snapshot of the queues, for UI indication and tests."""
        with self._lock:
            return {
                "desired_seed": self._desired[2] if self._desired else None,
                "inflight_seed": self._inflight.seed if self._inflight else None,
                "pending_seed": self._pending.seed if self._pending else None,
                "prefetch_seed": (
                    self._prefetch_pending.seed if self._prefetch_pending else None
                ),
                "completed": self.completed,
                "errors": self.errors,
                "discarded_stale": self.discarded_stale,
            }

    # -- public API ----------------------------------------------------------

    def request(self, prompt, size, seed, priority=0):
        """User navigation request. Supersedes any queued request.

        Idempotent: a key that is already cached, already queued, or already
        being generated returns immediately without scheduling another job.
        The interaction loop calls this every frame (~20 Hz); without this
        dedup the same seed would be regenerated once per completed job.
        """
        size = tuple(size)
        key = (prompt, size, seed)
        with self._lock:
            if self._is_cached(key):
                # Nothing left to generate; the loop will load it from cache.
                if self._desired == key:
                    self._desired = None
                return None

            inflight = self._inflight
            if inflight is not None and inflight.key == key:
                # Exactly what the user wants is already rendering: drop any
                # queued request that this one superseded.
                superseded, self._pending = self._pending, None
                if superseded is not None and not superseded.cancelled:
                    superseded.cancelled = True
                    self.cancelled_count += 1
                self._prefetch_pending = None if self._same_key(
                    self._prefetch_pending, key
                ) else self._prefetch_pending
                self._desired = key
                return inflight

            pending = self._pending
            if pending is not None and pending.key == key:
                self._desired = key
                return pending

            job = Job(prompt, size, seed, priority, self._next_seq_locked())
            if pending is not None and not pending.cancelled:
                pending.cancelled = True
                self.cancelled_count += 1
            self._pending = job
            if self._same_key(self._prefetch_pending, key):
                self._prefetch_pending = None
            self._desired = key
        self._wake.set()
        return job

    @staticmethod
    def _same_key(job, key) -> bool:
        return job is not None and job.key == key

    def request_prefetch(self, prompt, size, seed):
        """Lower-priority exploration of neighbouring seeds. Never displaces
        a user request, and never runs while the user is waiting on one."""
        size = tuple(size)
        key = (prompt, size, seed)
        with self._lock:
            if self._is_cached(key):
                return None
            if self._desired is not None:
                return None  # user target outstanding: prefetch must not jump it
            if self._same_key(self._prefetch_pending, key):
                return self._prefetch_pending
            inflight = self._inflight
            if inflight is not None and inflight.key == key:
                return inflight
            if self._prefetch_pending is not None:
                # One prefetch slot, and no churn: if a different neighbour is
                # already queued, let it run before replacing it. The loop asks
                # for both neighbours every frame, so replace-wins here would
                # oscillate and starve one of them.
                return None
            job = Job(prompt, size, seed, priority=10, seq=self._next_seq_locked())
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
            return self._next_seq_locked()

    def _next_seq_locked(self):
        """Caller already holds ``_lock``."""
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
            if self._desired is not None:
                # The visitor is waiting on the in-flight user job; starting
                # a prefetch here would add seconds to the next navigation.
                return None
            job = self._prefetch_pending
            if job is not None:
                self._prefetch_pending = None
                if not self._is_cached(job.key):
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
                    if self._desired == job.key:
                        # Do not keep a failed key as "desired": that would
                        # suppress prefetch indefinitely.
                        self._desired = None
                if self._on_error is not None:
                    try:
                        self._on_error(job.prompt, job.size, job.seed, e)
                    except Exception:
                        logger.exception("on_error callback raised")

    def _record(self, prompt, size, seed, png_path, metadata):
        png = Path(png_path)
        if not png.exists() or png.stat().st_size == 0:
            # Never index a path that cannot be displayed: a backend that
            # "succeeds" without writing a PNG is a failure, not a cache hit.
            raise FileNotFoundError(f"generator returned missing/empty image: {png}")
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