"""Audio-Reactive Fractal Forest — continuously audio-reactive installation.

A forest of procedurally-grown fractal trees that breathes with ambient
sound: rhythm onsets bloom the canopy, spectral energy grows the branches,
and the spectral centroid shifts the foliage hue (low=amber, high=jade).
Silence leaves the forest swaying in a gentle autonomous breeze — never a
frozen wallpaper.

Audio: a background daemon thread reads fixed-size blocks from a live
sounddevice InputStream (when asked and available) or a recorded WAV
looped through the exact same InputStream-shaped interface
(`read() -> float32 block`). Per-block analysis is numpy only: RMS energy,
spectral centroid (rfft), and an onset detector (energy burst above its
running median). The render loop only ever reads the latest feature
snapshot — it never blocks on audio, and there is no per-frame librosa
load and no LLM call anywhere.

Rendering: numpy/OpenCV, vectorised. Each tree is a recursive branch
skeleton (generated once, cached as flat arrays); per frame the visible
segments are drawn batched-by-depth with cv2.polylines, swayed by a
depth-weighted vectorised sine, and the canopy is an additive glow layer.
No per-pixel Mandelbrot; 720p at >=30 fps is the acceptance bar (measured
by scripts/verify_forest.py).

Controls: `c` replant (new random trees), `h` HUD, `q` quit.

Run:
  python lunar_tools_demo.py run audio-reactive-fractal-forest
  python lunar_tools_demo.py run audio-reactive-fractal-forest \
      --config duration=30 --config wav_path=outputs/forest/test_signal.wav
"""

from __future__ import annotations

import logging
import math
import random
import threading
import time
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

FRAME_W, FRAME_H = 1280, 720
FPS_TARGET = 30.0
BLOCK_S = 1 / 30          # audio analysis block (matches the frame budget)
SILENCE_RMS = 0.01
ONSET_FACTOR = 1.6        # energy must exceed this x its running median
ONSET_ABS = 0.02
MAX_TREES = 14
HORIZON = FRAME_H * 0.93


class Branch:
    __slots__ = ("x0", "y0", "x1", "y1", "depth", "order")

    def __init__(self, x0, y0, x1, y1, depth, order):
        self.x0, self.y0 = x0, y0
        self.x1, self.y1 = x1, y1
        self.depth = depth      # generation; growth reveals by depth
        self.order = order      # birth order within the whole tree (sway phase)


def _grow_tree(rng, x_base: float, height: float, max_depth: int = 7):
    """Recursive branch skeleton -> flat segment list."""
    segments: list[Branch] = []
    counter = [0]

    def grow(x, y, angle, length, depth):
        if depth > max_depth or length < 4.0:
            return
        x2 = x + math.cos(angle) * length
        y2 = y + math.sin(angle) * length
        segments.append(Branch(x, y, x2, y2, depth, counter[0]))
        counter[0] += 1
        n = 2 if depth < 3 else rng.choice((2, 2, 3))
        spread = rng.uniform(0.25, 0.55)
        for i in range(n):
            a = angle + (i - (n - 1) / 2) * spread + rng.uniform(-0.08, 0.08)
            grow(x2, y2, a, length * rng.uniform(0.62, 0.78), depth + 1)

    grow(x_base, HORIZON, -math.pi / 2 + rng.uniform(-0.08, 0.08), height, 0)
    return segments


class ForestSkeleton:
    """All trees' segments as flat numpy arrays for vectorised drawing."""

    def __init__(self, seed: int | None = None):
        rng = random.Random(seed)
        self.trees = []
        n = rng.randint(MAX_TREES - 4, MAX_TREES)
        for i in range(n):
            x = FRAME_W * (i + rng.uniform(0.15, 0.85)) / n
            x = min(max(x, 30), FRAME_W - 30)
            height = rng.uniform(0.28, 0.62) * FRAME_H
            self.trees.append(_grow_tree(rng, x, height))
        allSegs = [s for t in self.trees for s in t]
        self.x0 = np.array([s.x0 for s in allSegs], dtype=np.float32)
        self.y0 = np.array([s.y0 for s in allSegs], dtype=np.float32)
        self.x1 = np.array([s.x1 for s in allSegs], dtype=np.float32)
        self.y1 = np.array([s.y1 for s in allSegs], dtype=np.float32)
        self.depth = np.array([s.depth for s in allSegs], dtype=np.int32)
        self.order = np.array([s.order for s in allSegs], dtype=np.float32)
        self.order_norm = (self.order - self.order.min()) / max(
            1e-6, self.order.max() - self.order.min()
        )
        self.dmax = int(self.depth.max()) if self.depth.size else 0

    def n_segments(self) -> int:
        return int(self.x0.size)

    def positions(self, sway_phase: float, sway_gain: float):
        """Swayed tips: depth-weighted sine offset, fully vectorised."""
        ang = np.arctan2(self.y1 - self.y0, self.x1 - self.x0)
        w = (self.depth / max(1, self.dmax)) ** 1.6 * sway_gain
        off = np.sin(sway_phase + self.order_norm * 2.1) * w
        nx = self.x1 + np.cos(ang + math.pi / 2) * off
        ny = self.y1 + np.sin(ang + math.pi / 2) * off
        return nx.astype(np.float32), ny.astype(np.float32)


def _pace(deadline: float) -> None:
    """Wait until `deadline` (perf_counter seconds).

    The Python 3.13.15 arm64 build on this machine oversleeps OS waits by
    ~100 ms for sub-100 ms durations (measured: time.sleep / Event.wait /
    select all show it, even single-threaded), which would cap any paced
    loop at ~8 fps. So fine pacing busy-waits on perf_counter. The caller
    only paces the frame's *leftover* budget, and on healthy machines the
    remainder is small; on this machine accuracy beats idle.
    """
    while time.perf_counter() < deadline:
        pass


class AudioFeatures:
    """Snapshot of the latest audio analysis (swapped atomically by the
    reader thread; read without blocking in the render loop)."""

    __slots__ = ("rms", "centroid", "onset", "t")

    def __init__(self, rms=0.0, centroid=0.0, onset=False, t=0.0):
        self.rms = rms
        self.centroid = centroid      # 0..1 normalised spectral centroid
        self.onset = onset
        self.t = t


class WavBlockSource:
    """Recorded WAV looped through an InputStream-shaped interface:
    `read()` returns the next fixed-size float32 block, looping forever —
    exactly the shape a live InputStream callback delivers."""

    def __init__(self, path: str, block: int, sr: int):
        import soundfile as sf

        data, file_sr = sf.read(path, dtype="float32", always_2d=True)
        data = data.mean(axis=1)
        if file_sr != sr:
            n = int(len(data) * sr / file_sr)
            idx = np.linspace(0, len(data) - 1, n).astype(np.int64)
            data = data[idx]
        self.data = np.ascontiguousarray(data)
        self.block = block
        self.i = 0

    def read(self):
        if self.i + self.block > len(self.data):
            self.i = 0  # loop
        out = self.data[self.i:self.i + self.block]
        self.i += self.block
        if len(out) < self.block:
            out = np.pad(out, (0, self.block - len(out)))
        return out

    def close(self):
        pass


class LiveMicSource:
    """Live sounddevice InputStream source (optional; mic-gated)."""

    def __init__(self, block: int, sr: int):
        import sounddevice as sd

        self._queue: list[np.ndarray] = []
        self._stream = sd.InputStream(
            samplerate=sr, channels=1, blocksize=block, callback=self._cb
        )
        self._stream.start()
        self.block = block

    def _cb(self, indata, frames, time_info, status):
        self._queue.append(indata[:, 0].copy())
        if len(self._queue) > 8:
            self._queue.pop(0)

    def read(self):
        if self._queue:
            return self._queue.pop(0)
        return np.zeros(self.block, dtype=np.float32)

    def close(self):
        self._stream.stop()
        self._stream.close()


class _SilenceSource:
    """No mic, no WAV: the forest drifts in silence (a valid state)."""

    def __init__(self, block):
        self.block = block

    def read(self):
        return np.zeros(self.block, dtype=np.float32)

    def close(self):
        pass


class AudioReactiveFractalForest:
    """Continuously audio-reactive fractal forest installation."""

    def __init__(
        self,
        lunar_tools_art_manager,
        duration: float | None = None,
        wav_path: str | None = None,
        use_mic: bool = False,
        seed: int | None = None,
        record_path: str | None = None,
        samplerate: int = 22050,
    ):
        self.manager = lunar_tools_art_manager
        self.renderer = lunar_tools_art_manager.renderer
        self.keyboard = lunar_tools_art_manager.keyboard_input
        self.logger = getattr(lunar_tools_art_manager, "logger", None) or logger
        self.last_fatal_error = None

        self.duration = duration
        self.wav_path = wav_path
        self.use_mic = bool(use_mic)
        self.record_path = record_path
        self.samplerate = int(samplerate)
        self._rng = random.Random(seed)
        self._np_rng = np.random.default_rng(seed)

        self.block = int(BLOCK_S * self.samplerate)
        self.features = AudioFeatures()
        self._feature_lock = threading.Lock()
        self._reader_thread = None
        self._running = False
        self._start_t = 0.0

        # forest state
        self.skeleton = ForestSkeleton(seed)
        self.growth = 0.35          # 0..1: how much of each tree is revealed
        self.bloom = 0.0             # onset flash on the canopy
        self._energy_med = 0.0
        self.frame_count = 0
        self.fps = 0.0
        self._show_hud = False
        self._held: set[str] = set()
        self._prev_key = None
        self._writer = None
        self._writer_pending_path = record_path
        self._writer_fps = None
        self.onsets_detected = 0
        self.last_onset_t = None
        self.growth_samples: list[tuple[float, float]] = []  # (t, growth)

    # -- audio reader thread ----------------------------------------------------

    def _analyse_block(self, samples: np.ndarray, t: float) -> AudioFeatures:
        rms = float(np.sqrt(np.mean(samples ** 2))) if samples.size else 0.0
        win = samples * np.hanning(len(samples))
        spec = np.abs(np.fft.rfft(win))
        freqs = np.fft.rfftfreq(len(samples), 1.0 / self.samplerate)
        if spec.sum() > 1e-9:
            centroid = float((freqs * spec).sum() / spec.sum())
        else:
            centroid = 0.0
        centroid_norm = min(1.0, centroid / (self.samplerate / 4))
        med = self._energy_med
        onset = rms > ONSET_ABS and rms > ONSET_FACTOR * max(med, 0.005)
        self._energy_med = 0.9 * med + 0.1 * rms
        return AudioFeatures(rms, centroid_norm, onset, t)

    def _reader_loop(self, source):
        try:
            while self._running:
                block = source.read()
                feats = self._analyse_block(block, time.time())
                with self._feature_lock:
                    self.features = feats
                # a WAV source must be paced to wall time (a live stream
                # blocks in read() by itself)
                time.sleep(BLOCK_S)
        except Exception as e:
            self.logger.warning("Forest: audio reader stopped: %s", e)
        finally:
            source.close()

    def _open_audio(self):
        if self.use_mic:
            try:
                src = LiveMicSource(self.block, self.samplerate)
                self.logger.info("Forest: live microphone source.")
                return src
            except Exception as e:
                self.logger.warning("Forest: mic unavailable (%s); WAV fallback.", e)
        if self.wav_path and Path(self.wav_path).exists():
            try:
                src = WavBlockSource(self.wav_path, self.block, self.samplerate)
                self.logger.info("Forest: recorded source %s (looped).", self.wav_path)
                return src
            except Exception as e:
                self.logger.warning(
                    "Forest: could not read %s (%s); silence drift.", self.wav_path, e
                )
        self.logger.warning("Forest: silence source (autonomous drift mode).")
        return _SilenceSource(self.block)

    # -- controls ------------------------------------------------------------------

    def _poll_controls(self):
        pressed = set()
        for k in ("q", "h", "c"):
            try:
                if self.keyboard.is_key_pressed(k):
                    pressed.add(k)
            except Exception:
                pass
        last = getattr(self.renderer, "last_key", None)
        if last is not None:
            pressed.add(last)
            if last == self._prev_key:
                pressed.discard(last)
        self._prev_key = last
        for k in pressed - self._held:
            self._on_key(k)
        self._held = pressed

    def _on_key(self, k):
        if k == "q":
            self.logger.info("Forest: 'q' — stopping.")
            self._running = False
        elif k == "h":
            self._show_hud = not self._show_hud
        elif k == "c":
            self.skeleton = ForestSkeleton(self._rng.randint(0, 10**9))
            self.growth = 0.35
            self.logger.info("Forest: replanted.")

    # -- rendering --------------------------------------------------------------------

    def _draw(self, canvas: np.ndarray, t: float, feats: AudioFeatures, dt: float):
        import cv2

        # growth follows energy; silence recedes slowly (never freezes)
        target = 0.30 + min(0.65, feats.rms * 6.0)
        rate = 1.8 if feats.rms > SILENCE_RMS else 0.15
        self.growth += (target - self.growth) * min(1.0, rate * dt)
        self.bloom = max(0.0, self.bloom - 2.4 * dt)
        if feats.onset:
            self.bloom = 1.0
            self.onsets_detected += 1
            self.last_onset_t = t
        self.growth_samples.append((t, self.growth))

        # night-sky gradient (vectorised)
        g = np.linspace(0.55, 1.0, FRAME_H, dtype=np.float32)[:, None, None]
        top = np.array([6, 9, 16], dtype=np.float32)
        bot = np.array([14, 16, 30], dtype=np.float32)
        canvas[:] = np.clip(top * g + bot * (1 - g), 0, 255).astype(np.uint8)

        # breeze: always blowing; audio only modulates its strength
        breeze = 0.5 + 0.5 * math.sin(t * 0.7)
        sway_gain = (0.8 + 2.2 * breeze) * (1.0 + 0.9 * min(1.0, feats.rms * 8))
        sway_phase = t * (0.9 + 1.4 * min(1.0, feats.rms * 5))

        sk = self.skeleton
        nx, ny = sk.positions(sway_phase, sway_gain)

        reveal = self.growth * (sk.dmax + 1)
        vis = (sk.depth + sk.order_norm * 0.9) <= reveal
        vis_idx = np.flatnonzero(vis)

        # branches: batched polylines per depth (shading + thickness by depth)
        for d in range(sk.dmax + 1):
            idx = vis_idx[sk.depth[vis_idx] == d]
            if idx.size == 0:
                continue
            thickness = max(1, 7 - d)
            shade = 46 + 88 * (d / max(1, sk.dmax))
            color = (int(shade * 0.95), int(shade * 0.8), int(shade * 0.7))
            segs = np.stack(
                [
                    np.stack([sk.x0[idx], sk.y0[idx]], axis=1),
                    np.stack([nx[idx], ny[idx]], axis=1),
                ],
                axis=1,
            ).astype(np.int32)
            cv2.polylines(canvas, segs, False, color, thickness, cv2.LINE_AA)

        # canopy: additive glow at the deepest visible tips; hue from the
        # spectral centroid (low=amber, high=jade), brightness from energy
        # + the onset bloom
        deep = np.flatnonzero((sk.depth >= sk.dmax - 1) & vis)
        out = canvas.astype(np.float32)
        if deep.size:
            glow = np.zeros((FRAME_H // 2, FRAME_W // 2, 3), dtype=np.float32)
            xs = (nx[deep] * 0.5).astype(np.int32)
            ys = (ny[deep] * 0.5).astype(np.int32)
            ok = (xs >= 0) & (xs < FRAME_W // 2) & (ys >= 0) & (ys < FRAME_H // 2)
            xs, ys = xs[ok], ys[ok]
            c = feats.centroid
            hue = np.array(
                [255 * (1 - c) * 0.9 + 40, 150 + 90 * c, 60 + 120 * c],
                dtype=np.float32,
            )
            bright = (0.35 + 0.65 * min(1.0, feats.rms * 6)) * (1 + self.bloom)
            if xs.size:
                np.add.at(glow, (ys, xs), hue * bright)
            halo = cv2.GaussianBlur(glow, (0, 0), 1.6)
            full = cv2.resize(halo, (FRAME_W, FRAME_H), interpolation=cv2.INTER_LINEAR)
            out += full * 1.2
        np.clip(out, 0, 255, out=out)
        canvas[:] = out.astype(np.uint8)

        # ground
        cv2.rectangle(canvas, (0, int(HORIZON)), (FRAME_W, FRAME_H), (16, 14, 12), -1)

    def _draw_hud(self, canvas):
        import cv2

        f = self.features
        lines = [
            f"fractal forest  |  rms {f.rms:.3f}  |  centroid {f.centroid:.2f}"
            f"  |  growth {self.growth:.2f}  |  bloom {self.bloom:.2f}",
            f"{self.fps:5.1f} fps  |  onsets {self.onsets_detected}"
            f"  |  trees {len(self.skeleton.trees)}"
            f"  |  segments {self.skeleton.n_segments()}",
            "[c] replant  [h] hud  [q] quit",
        ]
        y = 22
        for line in lines:
            cv2.putText(canvas, line, (12, y), cv2.FONT_HERSHEY_SIMPLEX,
                        0.48, (235, 235, 235), 1, cv2.LINE_AA)
            y += 24

    # -- main loop ----------------------------------------------------------------------

    def run(self):
        source = self._open_audio()
        self._start_t = time.time()
        self._running = True
        self._reader_thread = threading.Thread(
            target=self._reader_loop, args=(source,), daemon=True
        )
        self._reader_thread.start()

        try:
            self.renderer.set_size(FRAME_W, FRAME_H)
        except Exception:
            pass
        canvas = np.zeros((FRAME_H, FRAME_W, 3), dtype=np.uint8)
        last_t = time.time()
        ema_fps = None
        self._writer = None
        _frame_deadline = time.perf_counter()

        try:
            while self._running:
                now = time.time()
                dt = min(0.1, max(1e-4, now - last_t))
                last_t = now
                t = now - self._start_t

                if self.duration is not None and t >= self.duration:
                    self.logger.info("Forest: duration %ss reached.", self.duration)
                    break

                self._poll_controls()
                with self._feature_lock:
                    feats = AudioFeatures(
                        self.features.rms, self.features.centroid,
                        self.features.onset, self.features.t,
                    )
                self._draw(canvas, t, feats, dt)
                if self._show_hud:
                    self._draw_hud(canvas)

                self.renderer.render(canvas)
                self._maybe_open_writer(canvas)
                if self._writer is not None:
                    self._writer.write(canvas[:, :, ::-1])
                self.frame_count += 1

                inst = 1.0 / max(dt, 1 / 120.0)
                ema_fps = inst if ema_fps is None else 0.9 * ema_fps + 0.1 * inst
                self.fps = ema_fps

                # pace to the target fps; the audio reader paces itself.
                # deadline in perf_counter seconds (matching _pace's clock)
                _ace = time.perf_counter()
                _frame_deadline = _ace if _frame_deadline is None else _frame_deadline
                _frame_deadline += 1.0 / FPS_TARGET
                _pace(_frame_deadline)

        except KeyboardInterrupt:
            self.logger.info("Forest: Ctrl+C — stopping.")
        except Exception as e:
            self.last_fatal_error = str(e)
            self.logger.exception("Forest: fatal error in the main loop.")
        finally:
            self._running = False
            if self._writer is not None:
                self._writer.release()
                self._writer = None
            try:
                self.renderer.close()
            except Exception:
                pass
            self.logger.info(
                "Forest: finished — %d frames over %.1fs (%.1f fps avg), "
                "%d onsets (last at %s).",
                self.frame_count,
                time.time() - self._start_t,
                self.frame_count / max(1e-6, time.time() - self._start_t),
                self.onsets_detected,
                f"{self.last_onset_t:.2f}s" if self.last_onset_t is not None else "never",
            )

    def _maybe_open_writer(self, canvas):
        if self._writer is not None or not self._writer_pending_path:
            return
        if time.time() - self._start_t < 3.0 or self.frame_count < 30:
            return
        import cv2

        path = Path(self._writer_pending_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fps = max(1.0, self.frame_count / (time.time() - self._start_t))
        writer = cv2.VideoWriter(
            str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (FRAME_W, FRAME_H)
        )
        if not writer.isOpened():
            self.logger.warning("Forest: could not open %s for recording.", path)
            self._writer_pending_path = None
            return
        self.logger.info("Forest: recording at %.1f fps to %s", fps, path)
        self._writer = writer
        self._writer_fps = fps


if __name__ == "__main__":
    from src.lunar_tools_art import Manager

    AudioReactiveFractalForest(Manager()).run()