"""Whispers — a movement-responsive particle installation.

Visitors move through the frame; their motion becomes a drifting particle
aura, and the space occasionally answers in a hushed voice.

Motion analysis (identical pipeline for every input source):
frame differencing on a 160x90 grey grid, vectorised with numpy. Motion
energy (mean abs diff) drives three things:

- **emission** — moving cells spawn particles each frame, in numbers
  proportional to how much of the room is moving and how fast; particle
  colours are sampled from the underlying frame, so the aura is a live
  portrait of the room's own light; drift direction follows the motion's
  flow field (per-block centroid shift between frames);
- **the aura** — particles live ~25 s, orbiting a slow swirl field with
  faint upward buoyancy, so a session's movement accumulates into a
  session-long atmosphere (`c` clears it; the piece can begin again);
- **whispers** — a burst of motion after a quiet period invites one spoken
  fragment: synthesis runs on a background thread against the local
  Afterwords server and playback is `blocking=False` at low volume, so the
  voice never freezes the loop and never interrupts itself.

A still room is not an error state: the aura keeps breathing with no input.

Input sources, first that opens wins:
  1. `camera_id` webcam via the manager's WebCam tool;
  2. `video_path` — a recorded clip, looped (same differencing pipeline as
     the webcam, so the installation logic is genuinely exercised on
     machines without a camera; the HUD always names the active source);
  3. synthetic procedural motion (testing fallback, named in the HUD).

Rendering goes through the manager's Renderer (real pyglet or OpenCV
window in hardware mode, null in headless tests). Target: 60 fps at 720p
with 2,000 live particles (measured by `scripts/verify_whispers.py`).

Controls (via manager.keyboard_input; when the OpenCV renderer is focused
the key also arrives via its `last_key` fallback, since pynput needs
Accessibility trust that headless agents do not have):
  c      clear the aura                      (edge-triggered)
  m      toggle motion-cells overlay         (edge-triggered)
  space  whisper now, ignoring the gap       (edge-triggered)
  h      toggle HUD (fps/particles/source)   (edge-triggered)
  q      quit

Run:
  python lunar_tools_demo.py run whispers
  python lunar_tools_demo.py run whispers --config duration=30 \
      --config video_path=outputs/glitch_lab/synthetic_reference_720p.mp4 \
      --config record_path=outputs/whispers/demo.mp4
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

# --- tuning -----------------------------------------------------------------

FRAME_W, FRAME_H = 1280, 720          # render size (16:9)
DIFF_W, DIFF_H = 160, 90              # motion analysis grid (8x downscale)
CELL_THRESHOLD = 12.0                 # grey-diff level that marks a moving cell
PARTICLE_LIFETIME_S = 25.0             # aura persistence: particles die slow
FILL_TIME_S = 10.0                     # sustained motion fills the cap in ~this
TRAIL_ALPHA = 0.55                     # 1.0 = no trails; lower = longer trails
HUSH_VOLUME = 0.22                     # whispers are quiet by design
WHISPER_MIN_GAP_S = 6.0                # at most one spoken whisper per gap
WHISPER_ABS_MIN_ENERGY = 2.5           # never whisper into camera noise
WHISPER_BURST_FACTOR = 1.8             # energy must exceed this x its slow EMA
SWIRL_RATE = 0.05                      # orbit field angular rate

WHISPER_PHRASES = [
    "Someone was here, just now.",
    "The light remembers you.",
    "Move slowly. The room is listening.",
    "Every gesture outlives the hand.",
    "You have been here before, in a dream.",
    "The particles agree with you.",
    "Something almost happened here.",
    "Stay. The air is still deciding.",
    "This is how a room keeps a diary.",
    "Your outline is still arriving.",
    "Quietly, quietly, the walls lean in.",
    "The dust was waiting for exactly this.",
]


class WhisperEvent:
    """One spoken (or attempted) whisper — evidence for the HUD and tests."""

    __slots__ = ("text", "voice", "path", "played", "error", "t")

    def __init__(self, text, voice, path, played, error, t):
        self.text = text
        self.voice = voice
        self.path = path
        self.played = played
        self.error = error
        self.t = t

    def as_dict(self):
        return {
            "text": self.text,
            "voice": self.voice,
            "path": self.path,
            "played": self.played,
            "error": self.error,
            "t": self.t,
        }


def _hush(path: str, volume: float):
    """Read a TTS wav, mix to mono, scale to a whisper's volume.

    Returns (float32 samples, samplerate) — played via
    ``SoundPlayer.play_audio(samples, samplerate=sr, blocking=False)``.
    """
    import soundfile as sf

    data, sr = sf.read(path)
    if data.ndim > 1:
        data = data.mean(axis=1)
    data = np.asarray(data, dtype=np.float32)
    return data * volume, sr


class Whispers:
    """Movement-responsive particle installation (see module docstring)."""

    def __init__(
        self,
        lunar_tools_art_manager,
        duration: float | None = None,
        camera_id: int = 0,
        video_path: str | None = None,
        voice: str | None = None,
        particle_cap: int = 2000,
        trail_alpha: float = TRAIL_ALPHA,
        whisper_gap_s: float = WHISPER_MIN_GAP_S,
        seed: int | None = None,
        record_path: str | None = None,
        synthetic_motion: bool = False,
    ):
        self.manager = lunar_tools_art_manager
        self.renderer = lunar_tools_art_manager.renderer
        self.keyboard = lunar_tools_art_manager.keyboard_input
        self.webcam = getattr(lunar_tools_art_manager, "webcam", None)
        self.sound_player = lunar_tools_art_manager.sound_player
        self.text2speech = getattr(lunar_tools_art_manager, "text2speech", None)
        self.logger = getattr(lunar_tools_art_manager, "logger", None) or logger
        self.last_fatal_error = None

        self.duration = duration
        self.camera_id = int(camera_id)
        self.video_path = video_path
        self.voice = voice
        self.particle_cap = max(16, int(particle_cap))
        self.trail_alpha = float(trail_alpha)
        self.whisper_gap_s = float(whisper_gap_s)
        self.record_path = record_path
        self.synthetic_motion = bool(synthetic_motion)
        self._rng = random.Random(seed)
        self._np_rng = np.random.default_rng(seed)

        # Input-source state (decided in run(); nothing touches hardware in
        # __init__ so headless construction stays side-effect free).
        self.source_kind = "none"            # camera | video | synthetic
        self.source_detail = ""
        self._capture = None                 # cv2.VideoCapture (video path)
        self._last_source_frame = None

        # Motion analysis state.
        self._prev_gray = None
        self.motion_energy = 0.0
        self._energy_ema = 0.0

        # Particle store: slots [0, n) are alive; death compacts via
        # swap-with-survivors, spawn appends. All updates vectorised.
        cap = self.particle_cap
        self._n = 0
        self._px = np.zeros(cap)
        self._py = np.zeros(cap)
        self._vx = np.zeros(cap)
        self._vy = np.zeros(cap)
        self._age = np.zeros(cap)
        self._size = np.zeros(cap)
        self._col = np.zeros((cap, 3))       # float RGB

        # Half-resolution additive glow layer (the vectorised draw target).
        self._glow = np.zeros((FRAME_H // 2, FRAME_W // 2, 3), dtype=np.float32)

        # Whisper state.
        self.whisper_events: list[WhisperEvent] = []
        self.whispers_spoken = 0
        self.whispers_attempted = 0
        self._last_whisper_t = -math.inf
        self._whisper_busy = False
        self._whisper_lock = threading.Lock()

        # Controls / evidence.
        self._show_motion = False
        self._show_hud = False
        self._prev_key = None                # cv2 last_key edge detection
        self._held: set[str] = set()
        self._running = False
        self._start_t = 0.0
        self.fps = 0.0
        self.frame_count = 0
        self.frames_at_capacity = 0
        self._writer = None

    # -- input sources --------------------------------------------------------

    def _to_frame(self, frame: np.ndarray) -> np.ndarray:
        """Resize any input frame to render size (RGB HxWx3 uint8)."""
        import cv2

        if frame.shape[:2] != (FRAME_H, FRAME_W) or not frame.flags.c_contiguous:
            frame = cv2.resize(frame, (FRAME_W, FRAME_H))
            frame = np.ascontiguousarray(frame)
        return frame

    def _open_source(self) -> None:
        """Pick the first available motion source and prime the differencer."""
        # 1. webcam via the manager's WebCam tool (the real installation path)
        if self.webcam is not None and not self.synthetic_motion:
            frame = self.webcam.get_img()
            if frame is not None:
                self.source_kind = "camera"
                self.source_detail = f"webcam {self.camera_id}"
                self._last_source_frame = self._to_frame(frame)
                self._prev_gray = self._grey_grid(self._last_source_frame)
                self.logger.info("Whispers: source = webcam (%s).", self.source_detail)
                return
            self.logger.warning(
                "Whispers: no webcam available; trying the video source."
            )

        # 2. recorded video, looped — same differencing pipeline as the webcam
        if self.video_path:
            path = Path(self.video_path)
            if not path.exists():
                self.logger.warning("Whispers: video_path %s does not exist.", path)
            else:
                import cv2

                cap = cv2.VideoCapture(str(path))
                if cap.isOpened():
                    ok, frame_bgr = cap.read()
                    if ok and frame_bgr is not None:
                        self._capture = cap
                        self.source_kind = "video"
                        self.source_detail = f"{path.name} (looped)"
                        self._last_source_frame = self._to_frame(frame_bgr[..., ::-1])
                        self._prev_gray = self._grey_grid(self._last_source_frame)
                        self.logger.info("Whispers: source = video (%s).", self.source_detail)
                        return
                    cap.release()
                self.logger.warning("Whispers: could not open video %s.", path)

        # 3. synthetic fallback — the piece stays alive without any visitor
        self.source_kind = "synthetic"
        self.source_detail = "procedural motion (no camera or video source)"
        self.logger.warning(
            "Whispers: synthetic motion source; the pipeline is identical "
            "but no visitor is present."
        )
        self._last_source_frame = self._synthetic_frame(time.time())
        self._prev_gray = self._grey_grid(self._last_source_frame)

    def _synthetic_frame(self, t: float) -> np.ndarray:
        """Slow procedural motion (testing fallback; also used mid-run if
        the camera dies, so the piece never hard-crashes)."""
        import cv2

        x = np.linspace(0.0, 1.0, DIFF_W, dtype=np.float32)
        y = np.linspace(0.0, 1.0, DIFF_H, dtype=np.float32)
        gx, gy = np.meshgrid(x, y)
        r = np.hypot(gx - 0.5, gy - 0.5)
        v = 0.5 + 0.5 * np.sin(r * 12.0 - t * 1.1)
        for cx, cy, sp in (
            (0.30 + 0.18 * math.sin(t * 0.50), 0.42 + 0.20 * math.sin(t * 0.33), 1.0),
            (0.70 + 0.20 * math.cos(t * 0.41), 0.60 + 0.16 * math.cos(t * 0.62), 0.8),
            (0.50 + 0.25 * math.sin(t * 0.23), 0.75 + 0.12 * math.sin(t * 0.71), 0.6),
        ):
            d = np.hypot(gx - cx, gy - cy)
            v = np.clip(v + sp * np.exp(-((d * 7.0) ** 2)), 0.0, 1.0)
        small = np.zeros((DIFF_H, DIFF_W, 3), dtype=np.uint8)
        small[..., 0] = (v * 190 + 40).astype(np.uint8)
        small[..., 1] = (v * 130 + 15).astype(np.uint8)
        small[..., 2] = (235 - v * 130).astype(np.uint8)
        return cv2.resize(small, (FRAME_W, FRAME_H))

    def _read_source_frame(self) -> np.ndarray:
        """Next full-res RGB frame from the active source (never raises)."""
        if self.source_kind == "camera":
            frame = self.webcam.get_img()
            if frame is not None:
                return self._to_frame(frame)
            self.source_kind = "synthetic"
            self.source_detail += " (camera lost mid-session)"
            self.logger.warning("Whispers: camera lost mid-session; drifting.")
        elif self.source_kind == "video" and self._capture is not None:
            import cv2

            ok, frame_bgr = self._capture.read()
            if not ok or frame_bgr is None:
                self._capture.set(cv2.CAP_PROP_POS_FRAMES, 0)  # loop the clip
                ok, frame_bgr = self._capture.read()
            if ok and frame_bgr is not None:
                return self._to_frame(frame_bgr[..., ::-1])
            self.source_kind = "synthetic"
            self.source_detail += " (video ended; could not loop)"
        return self._synthetic_frame(time.time())

    # -- motion analysis --------------------------------------------------------

    def _grey_grid(self, frame: np.ndarray) -> np.ndarray:
        import cv2

        small = cv2.resize(frame, (DIFF_W, DIFF_H))
        return cv2.cvtColor(small, cv2.COLOR_RGB2GRAY).astype(np.float32)

    def _motion_field(self, gray: np.ndarray):
        """Diff against the previous grid.

        Returns (energy, cells, flow_x, flow_y):
          energy — scalar mean abs diff (0..255)
          cells  — boolean DIFF_H x DIFF_W moving-cell mask
          flow   — per-cell motion direction from an 8x8-block centroid shift
                   between the previous and current grids (cheap vector flow).
        """
        prev = self._prev_gray
        if prev is None:
            diff = np.zeros_like(gray)
        else:
            diff = np.abs(gray - prev)
        energy = float(diff.mean())
        cells = diff > CELL_THRESHOLD

        flow_x = np.zeros((DIFF_H, DIFF_W), dtype=np.float32)
        flow_y = np.zeros((DIFF_H, DIFF_W), dtype=np.float32)
        if prev is not None:
            bh, bw = DIFF_H // 8, DIFF_W // 8
            # local index grids are built per block slice (the grid's last
            # row/column may be a partial block, so grids must match it)
            for y0 in range(0, DIFF_H, bh):
                for x0 in range(0, DIFF_W, bw):
                    cur = diff[y0:y0 + bh, x0:x0 + bw]
                    cw = cur.sum()
                    if cw <= 1e-3:
                        continue
                    by, bx = np.mgrid[y0:y0 + cur.shape[0], x0:x0 + cur.shape[1]]
                    cy = (by * cur).sum() / cw
                    cx = (bx * cur).sum() / cw
                    pblock = prev[y0:y0 + cur.shape[0], x0:x0 + cur.shape[1]]
                    pw = np.abs(pblock)
                    pws = pw.sum()
                    if pws <= 1e-3:
                        continue
                    py_c = (by * pw).sum() / pws
                    px_c = (bx * pw).sum() / pws
                    flow_x[y0:y0 + cur.shape[0], x0:x0 + cur.shape[1]] = np.clip(
                        cx - px_c, -4.0, 4.0
                    )
                    flow_y[y0:y0 + cur.shape[0], x0:x0 + cur.shape[1]] = np.clip(
                        cy - py_c, -4.0, 4.0
                    )
        return energy, cells, flow_x, flow_y

    # -- particles ----------------------------------------------------------------

    @property
    def n_alive(self) -> int:
        return int(self._n)

    def _spawn(self, frame, cells, flow_x, flow_y, energy, dt):
        """Emit particles from moving cells; count scales with motion.

        Budget keeps sustained motion filling the aura cap in ~FILL_TIME_S
        (so the piece accumulates rather than flashing), scaled 0.3x..1.6x
        by motion energy, and capped by free slots and moving-cell count.
        """
        n_free = self.particle_cap - self._n
        if n_free <= 0:
            self.frames_at_capacity += 1
            return
        active = np.flatnonzero(cells.ravel())
        if active.size == 0:
            return
        energy_factor = 0.3 + min(1.6, energy / 12.0)
        budget = (self.particle_cap / FILL_TIME_S) * dt * energy_factor
        n_emit = int(min(n_free, active.size, max(budget, 1.0)))
        if n_emit <= 0:
            return

        replace = active.size < n_emit
        pick = self._np_rng.choice(active, size=n_emit, replace=replace)
        gy, gx = np.divmod(pick, DIFF_W)
        sx, sy = FRAME_W / DIFF_W, FRAME_H / DIFF_H
        fxs = np.clip((gx * sx).astype(int), 0, FRAME_W - 1)
        fys = np.clip((gy * sy).astype(int), 0, FRAME_H - 1)

        i0 = self._n
        i1 = i0 + n_emit
        self._px[i0:i1] = (gx + self._np_rng.random(n_emit)) * sx
        self._py[i0:i1] = (gy + self._np_rng.random(n_emit)) * sy
        self._vx[i0:i1] = (
            flow_x.ravel()[pick] * 6.0 + self._np_rng.normal(0.0, 9.0, n_emit)
        )
        self._vy[i0:i1] = (
            flow_y.ravel()[pick] * 6.0 + self._np_rng.normal(0.0, 9.0, n_emit)
        )
        self._age[i0:i1] = 0.0
        self._size[i0:i1] = 1.2 + self._np_rng.random(n_emit) * 2.4
        self._col[i0:i1] = frame[fys, fxs].astype(np.float32)
        self._n = i1

    def _update_particles(self, dt: float):
        """Advance the alive slice: swirl field, drag, buoyancy, ageing."""
        n = self._n
        if n == 0:
            return
        t = time.time() - self._start_t
        ang = t * SWIRL_RATE
        ox = self._px[:n] - FRAME_W / 2
        oy = self._py[:n] - FRAME_H / 2
        swirl_gain = 0.9 + 0.35 * math.sin(ang)
        self._vx[:n] += (-oy * 0.012 * swirl_gain) * dt
        self._vy[:n] += (ox * 0.012 * swirl_gain) * dt
        drag = 1.0 - min(0.9, 0.85 * dt)
        self._vx[:n] *= drag
        self._vy[:n] *= drag
        self._vy[:n] -= 1.4 * dt                 # faint upward buoyancy
        self._px[:n] += self._vx[:n] * dt
        self._py[:n] += self._vy[:n] * dt
        self._age[:n] += dt

        # wrap at the edges: the aura has no walls
        self._px[:n] %= FRAME_W
        self._py[:n] %= FRAME_H

        # death by age; compact survivors to keep [0:n) contiguous
        dead = self._age[:n] > PARTICLE_LIFETIME_S
        if dead.any():
            keep = ~dead
            nk = int(keep.sum())
            self._px[:nk] = self._px[:n][keep]
            self._py[:nk] = self._py[:n][keep]
            self._vx[:nk] = self._vx[:n][keep]
            self._vy[:nk] = self._vy[:n][keep]
            self._age[:nk] = self._age[:n][keep]
            self._size[:nk] = self._size[:n][keep]
            self._col[:nk] = self._col[:n][keep]
            self._n = nk

    def _draw_particles(self, canvas: np.ndarray):
        """Additive glow draw, fully vectorised (no per-particle Python).

        Particles are splatted onto a half-res float layer, blurred for the
        halo, then composited up to full resolution with a bright core.
        """
        import cv2

        n = self._n
        if n == 0:
            return
        xs = self._px[:n].astype(np.int32) >> 1
        ys = self._py[:n].astype(np.int32) >> 1
        fade = 1.0 - self._age[:n] / PARTICLE_LIFETIME_S
        np.clip(fade, 0.0, 1.0, out=fade)
        fade = 0.06 + 0.94 * fade * fade        # dim slowly, die at end
        glow = self._glow
        glow.fill(0.0)
        np.add.at(glow, (ys, xs), self._col[:n] * fade[:, None] * 0.55)
        halo = cv2.GaussianBlur(glow, (0, 0), 1.1)
        core = cv2.resize(glow, (FRAME_W, FRAME_H), interpolation=cv2.INTER_NEAREST)
        full = cv2.resize(halo, (FRAME_W, FRAME_H), interpolation=cv2.INTER_LINEAR)
        out = canvas.astype(np.float32)
        out += core * 0.9
        out += full * 1.4
        np.clip(out, 0.0, 255.0, out=out)
        canvas[:] = out.astype(np.uint8)

    # -- whispers -------------------------------------------------------------------

    def _maybe_whisper(self, energy: float) -> bool:
        """A burst of motion after a quiet period invites one whisper.

        Synthesis + playback happen on a daemon thread; the render loop
        never blocks on the voice.
        """
        now = time.time()
        if now - self._last_whisper_t < self.whisper_gap_s:
            return False
        if energy < WHISPER_ABS_MIN_ENERGY:
            return False
        if energy < WHISPER_BURST_FACTOR * max(self._energy_ema, 0.5):
            return False
        if self.text2speech is None or self.sound_player is None:
            return False
        if self._whisper_busy:
            return False
        self._last_whisper_t = now
        text = self._rng.choice(WHISPER_PHRASES)
        voice = self.voice
        self.whispers_attempted += 1
        self._whisper_busy = True

        def _synth_and_play():
            path = None
            err = None
            played = False
            try:
                path = self.text2speech.generate(text, voice)
            except Exception as e:  # TTS down must never kill the visuals
                err = f"synthesis failed: {e}"
            if path is not None:
                try:
                    samples, sr = _hush(path, HUSH_VOLUME)
                    self.sound_player.play_audio(samples, samplerate=sr, blocking=False)
                    played = True
                except Exception as e:
                    err = err or f"playback failed: {e}"
            evt = WhisperEvent(text, voice or "default", path, played, err, time.time())
            with self._whisper_lock:
                self.whisper_events.append(evt)
                if played:
                    self.whispers_spoken += 1
                self._whisper_busy = False

        threading.Thread(target=_synth_and_play, daemon=True).start()
        return True

    def _force_whisper(self):
        """`space`: whisper now, bypassing the quiet-gap (demo control)."""
        saved = self._last_whisper_t
        self._last_whisper_t = -math.inf
        # temporarily pretend the energy is a huge burst
        ok = self._maybe_whisper(1e6)
        if not ok and self.text2speech is not None and not self._whisper_busy:
            # gap guard is the only refusing condition at 1e6 energy; retry
            # once ignoring the busy flag is unsafe, so just restore and leave
            pass
        self._last_whisper_t = saved if not self.whisper_events else saved

    # -- controls ----------------------------------------------------------------------

    def _poll_controls(self):
        """Edge-triggered keys from pynput/pyglet, plus the OpenCV fallback."""
        pressed = set()
        for k in ("c", "m", "space", "h", "q"):
            try:
                if self.keyboard.is_key_pressed(k):
                    pressed.add(k)
            except Exception:
                pass
        # OpenCV renderer path: keys arrive via renderer.last_key (cv2
        # window focused). pynput in untrusted contexts never fires, so this
        # is what makes interactive control work from a terminal-launched
        # OpenCV window without Accessibility grants.
        last = getattr(self.renderer, "last_key", None)
        if last is not None:
            pressed.add(last)
            if last == self._prev_key:
                pressed.discard(last)  # key still held: edge only
        if last is None:
            self._prev_key = None
        else:
            self._prev_key = last

        for k in pressed - self._held:
            self._on_key(k)
        self._held = pressed

    def _on_key(self, k: str):
        if k == "c":
            self._clear_aura()
        elif k == "m":
            self._show_motion = not self._show_motion
        elif k == "space":
            self._force_whisper()
        elif k == "h":
            self._show_hud = not self._show_hud
        elif k == "q":
            self.logger.info("Whispers: 'q' pressed — stopping.")
            self._running = False

    def _clear_aura(self):
        self._n = 0
        self.logger.info("Whispers: aura cleared.")

    # -- overlays -------------------------------------------------------------------------

    def _draw_hud(self, canvas: np.ndarray):
        import cv2

        res = getattr(self, "_last_whisper_result", None)
        lines = [
            f"whispers  |  source: {self.source_kind} ({self.source_detail})",
            f"{self.fps:5.1f} fps  |  {self._n} particles / cap {self.particle_cap}"
            f"  |  energy {self.motion_energy:.1f}",
            f"whispers spoken {self.whispers_spoken} / attempted {self.whispers_attempted}",
            "[c] clear  [m] motion overlay  [space] whisper  [h] hud  [q] quit",
        ]
        y = 22
        for line in lines:
            cv2.putText(canvas, line, (12, y), cv2.FONT_HERSHEY_SIMPLEX,
                        0.48, (235, 235, 235), 1, cv2.LINE_AA)
            y += 24

    def _draw_motion_overlay(self, canvas: np.ndarray, cells: np.ndarray):
        import cv2

        big = cv2.resize(cells.astype(np.uint8), (FRAME_W, FRAME_H))
        mask = big > 0
        darkened = (canvas[mask].astype(np.float32) * 0.35).astype(np.uint8)
        canvas[mask] = darkened
        boost = canvas[..., 2].astype(np.float32)
        boost[mask] = np.clip(boost[mask] + 70.0, 0, 255)
        canvas[..., 2] = boost.astype(np.uint8)

    # -- recording ---------------------------------------------------------------------------

    # (the recorder opens lazily from the main loop via _maybe_open_writer)

    def _maybe_open_writer(self, canvas):
        """Open the recorder once the loop's real fps is measured (3 s in).

        The VideoWriter needs a fixed fps; writing 60-fps while the loop
        renders slower would compress the timeline. Waiting for the measured
        rate keeps playback duration aligned with wall time (and with the
        whisper offsets used for the audio mux).
        """
        if self._writer is not None or not getattr(self, "_writer_pending_path", None):
            return
        if time.time() - self._start_t < 3.0 or self.frame_count < 30:
            return
        import cv2

        path = Path(self._writer_pending_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # measured mean rate over the warm-up window (the per-frame EMA can
        # spike on the first frame's tiny dt)
        fps = max(1.0, self.frame_count / (time.time() - self._start_t))
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(path), fourcc, fps, (FRAME_W, FRAME_H))
        if not writer.isOpened():
            self.logger.warning("Whispers: could not open %s for recording.", path)
            self._writer_pending_path = None
            return
        self.logger.info("Whispers: recording at %.0f fps to %s", fps, path)
        self._writer = writer
        self._writer_fps = fps

    # -- main loop -------------------------------------------------------------------------------

    def run(self):
        self._open_source()
        self._start_t = time.time()
        self._running = True
        self._writer = None
        self._writer_fps = None
        self._writer_pending_path = self.record_path
        try:
            self.renderer.set_size(FRAME_W, FRAME_H)
        except Exception:
            pass
        canvas = np.zeros((FRAME_H, FRAME_W, 3), dtype=np.uint8)
        last_t = time.time()
        self.fps = 0.0
        ema_fps = None

        try:
            while self._running:
                now = time.time()
                dt = min(0.1, max(1e-4, now - last_t))
                last_t = now

                if self.duration is not None and now - self._start_t >= self.duration:
                    self.logger.info("Whispers: duration %ss reached.", self.duration)
                    break

                self._poll_controls()

                frame = self._read_source_frame()
                gray = self._grey_grid(frame)
                energy, cells, flow_x, flow_y = self._motion_field(gray)
                self.motion_energy = energy
                self._energy_ema = 0.94 * self._energy_ema + 0.06 * energy
                self._prev_gray = gray

                # trails: decay the canvas toward the current source frame
                src = frame.astype(np.float32)
                prev = canvas.astype(np.float32)
                blended = src * (1.0 - self.trail_alpha) + prev * self.trail_alpha
                canvas[:] = np.clip(blended, 0, 255).astype(np.uint8)

                self._spawn(frame, cells, flow_x, flow_y, energy, dt)
                self._update_particles(dt)
                self._draw_particles(canvas)

                if self._show_motion:
                    self._draw_motion_overlay(canvas, cells)
                if self._show_hud:
                    self._draw_hud(canvas)

                self._maybe_whisper(energy)

                self.renderer.render(canvas)
                self._maybe_open_writer(canvas)
                if self._writer is not None:
                    self._writer.write(canvas[:, :, ::-1])  # mp4 wants BGR
                self.frame_count += 1

                inst_fps = 1.0 / max(dt, 1 / 240.0)  # clamp the first-frame spike
                ema_fps = inst_fps if ema_fps is None else (
                    0.92 * ema_fps + 0.08 * inst_fps
                )
                self.fps = ema_fps

        except KeyboardInterrupt:
            self.logger.info("Whispers: Ctrl+C — stopping.")
        except Exception as e:  # surface but do not hide the window state
            self.last_fatal_error = str(e)
            self.logger.exception("Whispers: fatal error in the main loop.")
        finally:
            self._running = False
            if self._capture is not None:
                self._capture.release()
                self._capture = None
            if self._writer is not None:
                self._writer.release()
                self._writer = None
            try:
                self.sound_player.stop_sound()
            except Exception:
                pass
            try:
                self.renderer.close()
            except Exception:
                pass
            self.logger.info(
                "Whispers: finished — %d frames over %.1fs (%.1f fps avg), "
                "%d particles alive, %d/%d whispers spoken (source=%s).",
                self.frame_count,
                time.time() - self._start_t,
                self.frame_count / max(1e-6, time.time() - self._start_t),
                self._n,
                self.whispers_spoken,
                self.whispers_attempted,
                self.source_kind,
            )


if __name__ == "__main__":
    from src.lunar_tools_art import Manager

    Whispers(Manager()).run()