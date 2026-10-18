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
CELL_THRESHOLD = 12.0                 # smoothed grey-diff that marks a moving cell
CELL_HYST_LO = 6.0                    # cells above this sustain if moving last frame
STILL_ENERGY_MAX = 0.15                # below this mean energy the room is still
SUDDEN_ENERGY_MIN = 0.5                # absolute floor for a sudden gesture
GESTURE_STICKY_FRAMES = 3              # label change must persist this long
NOISE_FLOOR_INIT = 1.5                 # initial sensor-flicker estimate (grey levels)
GESTURE_BURST = 260                   # particles in one sudden-gesture burst
AMBIENT_BREATH_RATE = 0.02           # stillness ambient emission, particles/s per cap unit
STATE_LERP_S = 1.5                   # gesture-state parameter blend time constant

# --- visual presets (spec: prototypes/whispers_visual_presets.md) -----------

def _col_ember(pixel: np.ndarray) -> np.ndarray:
    """Warm the sampled pixel; lift dark pixels to a dim ember floor."""
    col = pixel * np.array([1.15, 0.95, 0.72], dtype=np.float32) + np.array(
        [18.0, 4.0, 0.0], dtype=np.float32
    )
    lum = pixel @ np.array([0.30, 0.55, 0.15], dtype=np.float32)
    floor = np.array([70.0, 28.0, 8.0], dtype=np.float32)
    return np.where((lum < 30.0)[..., None], np.maximum(col, floor), col)


_TIDAL_STOPS = (
    (0.00, (2.0, 12.0, 26.0)),
    (0.35, (10.0, 60.0, 96.0)),
    (0.70, (30.0, 140.0, 170.0)),
    (1.00, (120.0, 230.0, 240.0)),
)


def _col_tidal(pixel: np.ndarray) -> np.ndarray:
    """Erase the room's colour: luminance through a cool 4-stop ramp."""
    lum = (pixel @ np.array([0.30, 0.55, 0.15], dtype=np.float32)) / 255.0
    col = np.zeros_like(pixel)
    for (t0, c0), (t1, c1) in zip(_TIDAL_STOPS[:-1], _TIDAL_STOPS[1:]):
        m = (lum >= t0) & (lum <= t1)
        if not m.any():
            continue
        f = ((lum - t0) / (t1 - t0))[..., None]
        a = np.array(c0, dtype=np.float32)
        b = np.array(c1, dtype=np.float32)
        col = np.where(m[..., None], a + (b - a) * f, col)
    return col


def _col_ghost(pixel: np.ndarray) -> np.ndarray:
    """Invert-and-bloom: presence glows, background recedes."""
    inverted = np.clip(255.0 - pixel, 0, 255) * np.array(
        [1.0, 0.92, 1.0], dtype=np.float32
    )
    return 0.7 * inverted + 0.3 * pixel


_SIGNAL_STOPS = np.array(
    [
        [255.0, 140.0, 20.0],   # amber
        [255.0, 210.0, 60.0],   # gold
        [40.0, 220.0, 140.0],   # jade
        [50.0, 90.0, 255.0],    # cobalt
        [170.0, 60.0, 255.0],   # violet
        [255.0, 60.0, 120.0],   # rose
    ],
    dtype=np.float32,
)


def _col_signal(pixel: np.ndarray) -> np.ndarray:
    """Quantise hue to a 6-stop stained-glass ramp; dim stays dim."""
    import cv2

    hsv = cv2.cvtColor(
        np.clip(pixel, 0, 255).astype(np.uint8)[None, ...], cv2.COLOR_RGB2HSV
    )[0].astype(np.float32)
    h, s, v = hsv[..., 0], hsv[..., 1] / 255.0, hsv[..., 2] / 255.0
    idx = np.clip((h / 30.0).astype(int) % 6, 0, 5)
    col = _SIGNAL_STOPS[idx]
    return col * s[..., None] * (v[..., None] ** 0.8)


PRESETS: dict[str, dict] = {
    "ember": {
        "label": "Ember Library",
        "trail_alpha": 0.62,
        "size_range": (1.0, 2.8),
        "emission_scale": 0.75,
        "swirl_rate": 0.035,
        "buoyancy": 2.2,
        "glow_sigma": 1.3,
        "core_gain": 0.85,
        "halo_gain": 1.15,
        "color_map": _col_ember,
        "bg_tint": (24.0, 14.0, 8.0),
        "bg_tint_k": 0.10,
        "fade_floor": 0.04,
        "fade_exp": 2.4,
    },
    "tidal": {
        "label": "Tidal Memory",
        "trail_alpha": 0.80,
        "size_range": (0.8, 2.0),
        "emission_scale": 1.4,
        "swirl_rate": 0.020,
        "buoyancy": 0.5,
        "glow_sigma": 2.0,
        "core_gain": 0.45,
        "halo_gain": 1.8,
        "color_map": _col_tidal,
        "bg_tint": (10.0, 20.0, 26.0),
        "bg_tint_k": 0.14,
        "fade_floor": 0.10,
        "fade_exp": 1.4,
    },
    "ghost": {
        "label": "Ghost Bloom",
        "trail_alpha": 0.48,
        "size_range": (2.0, 5.0),
        "emission_scale": 0.55,
        "swirl_rate": 0.090,
        "buoyancy": -0.6,
        "glow_sigma": 2.6,
        "core_gain": 1.1,
        "halo_gain": 0.7,
        "color_map": _col_ghost,
        "bg_tint": (36.0, 34.0, 42.0),
        "bg_tint_k": 0.06,
        "fade_floor": 0.02,
        "fade_exp": 3.2,
    },
    "signal": {
        "label": "Signal Chapel",
        "trail_alpha": 0.68,
        "size_range": (1.4, 3.2),
        "emission_scale": 1.0,
        "swirl_rate": 0.140,
        "buoyancy": 1.0,
        "glow_sigma": 0.9,
        "core_gain": 1.35,
        "halo_gain": 0.95,
        "color_map": _col_signal,
        "bg_tint": (14.0, 10.0, 20.0),
        "bg_tint_k": 0.08,
        "fade_floor": 0.08,
        "fade_exp": 1.8,
    },
}
DEFAULT_PRESET = "ember"
PRESET_KEYS = {"1": "ember", "2": "tidal", "3": "ghost", "4": "signal"}

# per-state multipliers (spec: applied to the preset's base values)
STATE_MULTIPLIERS = {
    "still": {
        "trail_alpha": 1.15, "emission_scale": 0.60, "size": 0.85,
        "swirl_rate": 0.70, "buoyancy": 0.50, "glow_sigma": 1.25,
        "core_gain": 0.85, "halo_gain": 0.90, "brightness_floor": 0.10,
        "fade_exp": 0.80,
    },
    "gentle": {k: 1.0 for k in (
        "trail_alpha", "emission_scale", "size", "swirl_rate", "buoyancy",
        "glow_sigma", "core_gain", "halo_gain", "fade_exp",
    )} | {"brightness_floor": None},
    "sudden": {
        "trail_alpha": 0.75, "emission_scale": 2.60, "size": 1.40,
        "swirl_rate": 2.20, "buoyancy": 1.80, "glow_sigma": 0.70,
        "core_gain": 1.60, "halo_gain": 1.30, "brightness_floor": None,
        "fade_exp": 1.30,
    },
}
PARTICLE_LIFETIME_S = 25.0             # aura persistence: particles die slow
FILL_TIME_S = 10.0                     # sustained motion fills the cap in ~this
TRAIL_ALPHA = 0.55                     # 1.0 = no trails; lower = longer trails
HUSH_VOLUME = 0.22                     # whispers are quiet by design
WHISPER_MIN_GAP_S = 6.0                # at most one spoken whisper per gap
WHISPER_ABS_MIN_ENERGY = 0.3           # never whisper into camera noise
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


class WhisperTexture:
    """Procedural whisper-texture synthesiser (numpy, no network, no TTS).

    The sonic dimension of the installation, independent of Afterwords:
    a breathy band-limited noise bed whose **intensity** follows motion
    energy, whose **texture** (formant-ish resonances) shifts with the
    gesture state, and whose **spatial position** follows the horizontal
    centroid of motion. Clips are generated on demand (cheap numpy) and
    played non-blocking; the piece works identically with audio disabled
    (SoundPlayer degraded / absent is fine).

    A clip is ~2 s of: pink-ish noise -> 3 parallel resonant bandpasses
    (250/650/1200 Hz, breath formants) -> slow amplitude envelope. Sudden
    gestures add a sharp attack transient layer and a higher formant.
    """

    SR = 22050
    FORMANTS = (250.0, 650.0, 1200.0)

    def __init__(self, seed=None):
        self._rng = np.random.default_rng(seed)

    def clip(self, energy: float, gesture: str, pan: float) -> tuple:
        """Render one stereo clip. Returns (float32 [n,2] samples, sr).

        energy 0..~30 maps to peak 0.05..0.22; gesture selects the
        formant flavour; pan (-1..1) crossfades L/R.
        """
        dur = 2.2
        n = int(dur * self.SR)
        t = np.arange(n, dtype=np.float32) / self.SR

        # pink-ish noise: white filtered with a 1/sqrt(f) tilt approximation
        white = self._rng.standard_normal(n).astype(np.float32)
        spec = np.fft.rfft(white)
        freqs = np.fft.rfftfreq(n, 1.0 / self.SR)
        spec *= 1.0 / np.sqrt(np.maximum(freqs, 20.0) / 20.0)
        noise = np.fft.irfft(spec, n).astype(np.float32)

        sig = np.zeros(n, dtype=np.float32)
        if gesture == "sudden":
            forms = self.FORMANTS + (1800.0,)
            gains = (0.6, 0.4, 0.5, 0.7)
        elif gesture == "gentle":
            forms = self.FORMANTS
            gains = (0.5, 0.8, 0.4)
        else:  # still
            forms = self.FORMANTS[:2]
            gains = (0.9, 0.4)
        for f, g in zip(forms, gains):
            sig += g * self._resonance(noise, f)

        # slow envelope: breathe in, breathe out
        env = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 1.5
        sig *= env

        peak_target = float(np.clip(0.05 + 0.006 * energy, 0.05, 0.22))
        peak = float(np.abs(sig).max()) or 1.0
        sig *= peak_target / peak

        # pan into stereo
        theta = (pan + 1.0) * 0.25 * np.pi  # 0..pi/2
        stereo = np.stack([sig * np.cos(theta), sig * np.sin(theta)], axis=1)
        return stereo.astype(np.float32), self.SR

    def _resonance(self, noise: np.ndarray, freq: float, q: float = 8.0) -> np.ndarray:
        """FFT bandpass with a resonant peak (cheap formant)."""
        n = noise.shape[0]
        spec = np.fft.rfft(noise)
        freqs = np.fft.rfftfreq(n, 1.0 / self.SR)
        resp = np.exp(-0.5 * ((np.log(freqs + 1e-6) - np.log(freq)) * q) ** 2)
        resp[0] = 0.0
        return np.fft.irfft(spec * resp, n).astype(np.float32)


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

        # Visual preset + gesture-state parameter blending. Init in the
        # neutral "gentle" state (all multipliers 1.0) so a fresh instance
        # expresses the pure preset; the loop blends toward real states.
        self.preset_name = None
        self._gesture = "gentle"
        # optional MIDI user-adjustments (multiplicative, 1.0 = neutral)
        self.midi_adjust = {"size": 1.0, "swirl": 1.0, "emission": 1.0, "trail": 1.0}
        self._state_mix = {k: 1.0 for k in STATE_MULTIPLIERS["gentle"]}
        self._state_mix.pop("brightness_floor", None)
        self._state_mix["brightness_floor"] = None
        self.apply_preset(DEFAULT_PRESET, lerp=False)  # builds self.eff

        # Input-source state (decided in run(); nothing touches hardware in
        # __init__ so headless construction stays side-effect free).
        self.source_kind = "none"            # camera | video | synthetic
        self.source_detail = ""
        self._capture = None                 # cv2.VideoCapture (video path)
        self._last_source_frame = None
        self._clip_fps = 30.0                # recorded clip's frame rate
        self._video_frames_read = 0          # pacing counter (wall-time)

        # Motion analysis state.
        self._prev_gray = None
        self._cells_prev = np.zeros((DIFF_H, DIFF_W), dtype=bool)
        self._noise_floor = NOISE_FLOOR_INIT
        self.motion_energy = 0.0
        self._energy_ema = 0.0
        self._gesture_now = "still"
        self._gesture_frames = 0
        self._last_burst_t = -math.inf
        self.bursts_fired = 0
        self._breath_accum = 0.0

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

        # Procedural whisper texture (Afterwords-independent sonic layer).
        self.texture = WhisperTexture(seed=seed)
        self.texture_clips_played = 0
        self._last_texture_end_t = 0.0
        self.sound_enabled = True

        # Controls / evidence.
        self._show_motion = False
        self._show_hud = False
        self._prev_cv_key = None             # cv2 last_key edge detection
        self._held: set[str] = set()
        self._running = False
        self._start_t = 0.0
        self.fps = 0.0
        self.frame_count = 0
        self.frames_at_capacity = 0
        self._writer = None

    # -- presets & state-blended parameters ---------------------------------

    def apply_preset(self, name: str, lerp: bool = True) -> None:
        """Switch the visual preset. With `lerp`, numeric parameters glide
        from the current values to the new preset's over ~1.5 s so a
        mid-session switch never pops."""
        if name not in PRESETS:
            raise KeyError(f"unknown preset {name!r} (have: {sorted(PRESETS)})")
        p = PRESETS[name]
        self.preset_name = name
        self.preset_label = p["label"]
        if not lerp:
            self._params = dict(p)
            self.trail_alpha = float(p["trail_alpha"])
            # rebuild the effective dict immediately so direct-API users
            # (tests, embedders) see the new preset without a run loop
            self._update_state_blend(getattr(self, "_gesture", "gentle"), 1e9)
        else:
            self._params = dict(p)  # target; _update_state_blend lerps toward it

    def current_preset_params(self) -> dict:
        """The currently effective (state-blended) parameters."""
        return dict(self._params)

    def _update_state_blend(self, gesture: str, dt: float) -> None:
        """Blend state multipliers toward the current gesture's row with a
        ~1.5 s time constant, then derive effective draw parameters."""
        target = STATE_MULTIPLIERS.get(gesture, STATE_MULTIPLIERS["gentle"])
        alpha = 1.0 - math.exp(-dt / STATE_LERP_S)
        for k, v in target.items():
            if v is None:  # brightness_floor: state may override or defer
                self._state_mix[k] = None
                continue
            cur = self._state_mix.get(k)
            if cur is None:
                cur = 1.0
            self._state_mix[k] = cur + (v - cur) * alpha

        p = self._params
        m = self._state_mix
        eff = {
            "trail_alpha": min(0.97, p["trail_alpha"] * m["trail_alpha"]
                               * self.midi_adjust["trail"]),
            "size_range": (
                p["size_range"][0] * m["size"] * self.midi_adjust["size"],
                p["size_range"][1] * m["size"] * self.midi_adjust["size"],
            ),
            "emission_scale": p["emission_scale"] * m["emission_scale"]
            * self.midi_adjust["emission"],
            "swirl_rate": p["swirl_rate"] * m["swirl_rate"]
            * self.midi_adjust["swirl"],
            "buoyancy": p["buoyancy"] * m["buoyancy"],
            "glow_sigma": p["glow_sigma"] * m["glow_sigma"],
            "core_gain": p["core_gain"] * m["core_gain"],
            "halo_gain": p["halo_gain"] * m["halo_gain"],
            "fade_exp": p["fade_exp"] * m["fade_exp"],
            "brightness_floor": (
                m["brightness_floor"]
                if m.get("brightness_floor") is not None
                else p["fade_floor"]
            ),
            "color_map": p["color_map"],
            "bg_tint": p["bg_tint"],
            "bg_tint_k": p["bg_tint_k"],
        }
        self.eff = eff
        self.trail_alpha = eff["trail_alpha"]

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
                if not cap.isOpened():
                    cap.release()  # never leak a failed-open handle
                else:
                    ok, frame_bgr = cap.read()
                    if ok and frame_bgr is not None:
                        self._capture = cap
                        self._clip_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
                        self._video_frames_read = 1
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

            # wall-time pacing: a recorded visitor should unfold in real
            # time regardless of the render loop's fps. When the loop
            # runs slower than the clip, skip ahead to where wall time says
            # the clip should be (bounded catch-up).
            clip_fps = self._clip_fps or 30.0
            expected = int((time.time() - self._start_t) * clip_fps) + 1
            while self._video_frames_read < expected - 1:
                ok, _ = self._capture.read()   # discard lagging frames
                if not ok:
                    break
                self._video_frames_read += 1
            ok, frame_bgr = self._capture.read()
            if ok and frame_bgr is not None:
                self._video_frames_read += 1
            if not ok or frame_bgr is None:
                self._capture.set(cv2.CAP_PROP_POS_FRAMES, 0)  # loop the clip
                self._video_frames_read = 0
                ok, frame_bgr = self._capture.read()
                if ok and frame_bgr is not None:
                    self._video_frames_read = 1
            if ok and frame_bgr is not None:
                return self._to_frame(frame_bgr[..., ::-1])
            self.source_kind = "synthetic"
            self.source_detail += " (video ended; could not loop)"
            if self._capture is not None:
                self._capture.release()   # don't hold a dead handle
                self._capture = None
        return self._synthetic_frame(time.time())

    # -- motion analysis --------------------------------------------------------

    def _grey_grid(self, frame: np.ndarray) -> np.ndarray:
        import cv2

        small = cv2.resize(frame, (DIFF_W, DIFF_H))
        return cv2.cvtColor(small, cv2.COLOR_RGB2GRAY).astype(np.float32)

    def _motion_field(self, gray: np.ndarray):
        """Diff against the previous grid, with noise suppression,
        smoothing and hysteresis.

        Pipeline (all numpy, on the 160x90 grid):
          1. diff the grey grids;
          2. subtract a running noise-floor estimate (EMA of the diff's own
             low percentile) — sensor flicker stops counting as motion;
          3. smooth the diff (3x3 box blur) so single-cell noise speckles
             dissolve and coherent movement survives;
          4. hysteresis: a cell is *moving* if its smoothed diff exceeds
             CELL_THRESHOLD, or exceeds CELL_HYST_LO and was moving last
             frame (motion sustains through dips); a cell stops moving
             only when it falls below the low threshold;
          5. flow: per-block centroid shift between the previous and
             current weighted grids (cheap vector flow).

        Returns (energy, cells, flow_x, flow_y, gesture):
          energy  — scalar mean motion energy (post-suppression)
          cells   — boolean moving-cell mask (hysteresis applied)
          gesture — 'still' | 'gentle' | 'sudden' classification from the
                    energy burst ratio vs its slow EMA (see _classify_gesture)
        """
        prev = self._prev_gray
        if prev is None:
            diff = np.zeros_like(gray)
        else:
            diff = np.abs(gray - prev)

        # running noise floor: the low percentile of the diff itself is a
        # robust estimate of sensor flicker; subtract it, clamped at 0
        floor = float(np.percentile(diff, 90)) if diff.size else 0.0
        self._noise_floor = 0.95 * self._noise_floor + 0.05 * floor
        diff = np.clip(diff - (self._noise_floor + 1.0), 0.0, None)

        # smoothing: 3x3 box blur (two cumsum passes, vectorised)
        if prev is not None:
            d = np.pad(diff, 1, mode="edge")
            cs = np.cumsum(np.cumsum(d, axis=0), axis=1)
            cs = np.pad(cs, ((1, 0), (1, 0)))
            sm = (cs[3:, 3:] - cs[:-3, 3:] - cs[3:, :-3] + cs[:-3, :-3]) / 9.0
            diff = sm.astype(np.float32)

        energy = float(diff.mean())
        raw_hi = diff > CELL_THRESHOLD
        raw_lo = diff > CELL_HYST_LO
        cells = raw_hi | (raw_lo & self._cells_prev)
        self._cells_prev = cells.copy()

        flow_x = np.zeros((DIFF_H, DIFF_W), dtype=np.float32)
        flow_y = np.zeros((DIFF_H, DIFF_W), dtype=np.float32)
        if prev is not None:
            bh, bw = DIFF_H // 8, DIFF_W // 8
            # local index grids are built per block slice (the grid's last
            # row/column may be a partial block, so grids must match it)
            for y0 in range(0, DIFF_H, bh):
                for x0 in range(0, DIFF_W, bw):
                    cur = (diff * cells)[y0:y0 + bh, x0:x0 + bw]
                    cw = cur.sum()
                    if cw <= 1e-3:
                        continue
                    by, bx = np.mgrid[y0:y0 + cur.shape[0], x0:x0 + cur.shape[1]]
                    cy = (by * cur).sum() / cw
                    cx = (bx * cur).sum() / cw
                    pblock = prev[y0:y0 + cur.shape[0], x0:x0 + cur.shape[1]]
                    pw = np.abs(pblock - gray[y0:y0 + cur.shape[0], x0:x0 + cur.shape[1]])
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

        gesture = self._classify_gesture(energy)
        return energy, cells, flow_x, flow_y, gesture

    def _classify_gesture(self, energy: float) -> str:
        """Classify the room: still / gentle / sudden.

        A *sudden* gesture is an energy burst: energy well above its slow
        EMA *and* above an absolute floor. Hysteresis keeps the label
        sticky: once sudden, it holds for a few frames (the aura should
        not flicker between states), and a recent sudden episode keeps
        gentle from re-firing.
        """
        ema = self._energy_ema
        if energy < STILL_ENERGY_MAX and energy < 1.8 * max(ema, 0.5):
            label = "still"
        elif energy >= SUDDEN_ENERGY_MIN and energy >= 2.2 * max(ema, 0.4):
            label = "sudden"
        else:
            label = "gentle"
        # sticky: keep the previous label for a few frames
        if label != self._gesture:
            if self._gesture_frames > 0:
                self._gesture_frames -= 1
                label = self._gesture
            else:
                self._gesture = label
                self._gesture_frames = GESTURE_STICKY_FRAMES
        self._gesture_now = label
        return label

    # -- particles ----------------------------------------------------------------

    @property
    def n_alive(self) -> int:
        return int(self._n)

    def _spawn(self, frame, cells, flow_x, flow_y, energy, gesture, dt):
        """Emit particles from moving cells; the profile depends on the
        room's gesture state:

          still   — no new emission (the existing aura keeps drifting)
          gentle  — slow, budgeted emission: sustained motion fills the
                    aura cap in ~FILL_TIME_S, scaled 0.3x..1.6x by energy
          sudden  — an immediate burst: up to GESTURE_BURST particles in
                    one frame, brighter (larger), thrown harder along the
                    flow — a gesture should feel *answered*

        Sudden bursts are rate-limited (one per ~0.35 s) so a sustained
        frenzied movement produces repeated bursts, not a solid mass.
        """
        n_free = self.particle_cap - self._n
        if n_free <= 0:
            self.frames_at_capacity += 1
            return

        # stillness keeps the piece alive: a slow ambient "breath" of
        # large, dim particles from anywhere in the frame (no motion
        # cells needed), so the aura never fully empties and silence is
        # a valid aesthetic state. A fractional accumulator lets
        # sub-1-per-frame rates emit every few frames instead of never.
        if gesture == "still":
            self._breath_accum += self.particle_cap * AMBIENT_BREATH_RATE * dt
            n_emit = int(min(n_free, self._breath_accum))
            self._breath_accum -= n_emit
            if n_emit == 0:
                return
            pick = self._np_rng.integers(0, FRAME_W * FRAME_H, size=n_emit)
            gy, gx = np.divmod(pick, FRAME_W)
            fxs = np.clip(gx, 0, FRAME_W - 1)
            fys = np.clip(gy, 0, FRAME_H - 1)
            i0 = self._n
            i1 = i0 + n_emit
            self._px[i0:i1] = gx + 0.5
            self._py[i0:i1] = gy + 0.5
            self._vx[i0:i1] = self._np_rng.normal(0.0, 3.0, n_emit)
            self._vy[i0:i1] = self._np_rng.normal(0.0, 3.0, n_emit)
            self._age[i0:i1] = self._np_rng.random(n_emit) * PARTICLE_LIFETIME_S * 0.5
            self._size[i0:i1] = 3.0 + self._np_rng.random(n_emit) * 3.0
            # dim cool ambient colour (teal-white), not sampled from frame
            cols = np.empty((n_emit, 3), dtype=np.float32)
            cols[:, 0] = 40 + self._np_rng.random(n_emit) * 30
            cols[:, 1] = 90 + self._np_rng.random(n_emit) * 50
            cols[:, 2] = 110 + self._np_rng.random(n_emit) * 60
            self._col[i0:i1] = cols
            self._n = i1
            return

        active = np.flatnonzero(cells.ravel())
        if active.size == 0:
            return

        # a sudden gesture answers with an immediate burst (rate-limited)
        burst = gesture == "sudden" and (time.time() - self._last_burst_t) >= 0.35
        if burst:
            self._last_burst_t = time.time()

        if gesture == "still" and not burst:
            # motion cells present but energy very low: nothing new
            return
        if gesture == "gentle" or (gesture == "still" and burst) or not burst:
            # gentle emission, or a rate-limited sudden falling back to the
            # budgeted profile (never a second mass burst within 0.35 s)
            energy_factor = 0.3 + min(1.6, energy / 12.0)
            budget = (
                (self.particle_cap / FILL_TIME_S) * dt * energy_factor
                * self.eff["emission_scale"]
            )
            n_emit = int(min(n_free, active.size, max(budget, 1.0)))
            s_lo, s_hi = self.eff["size_range"]
            size_lo, size_hi = s_lo, s_hi
            flow_gain = 6.0
            jitter = 9.0
        else:
            n_emit = int(min(n_free, active.size, GESTURE_BURST))
            s_lo, s_hi = self.eff["size_range"]
            size_lo, size_hi = s_lo * 1.5, s_hi * 1.6   # bursts flare
            flow_gain = 14.0
            jitter = 26.0
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
        self._px[i0:i1] = np.clip(
            (gx + self._np_rng.random(n_emit)) * sx, 0.0, FRAME_W - 1e-3
        )
        self._py[i0:i1] = np.clip(
            (gy + self._np_rng.random(n_emit)) * sy, 0.0, FRAME_H - 1e-3
        )
        self._vx[i0:i1] = (
            flow_x.ravel()[pick] * flow_gain + self._np_rng.normal(0.0, jitter, n_emit)
        )
        self._vy[i0:i1] = (
            flow_y.ravel()[pick] * flow_gain + self._np_rng.normal(0.0, jitter, n_emit)
        )
        self._age[i0:i1] = 0.0
        self._size[i0:i1] = size_lo + self._np_rng.random(n_emit) * (size_hi - size_lo)
        # colour: sampled from the frame, then shaped by the preset's map
        self._col[i0:i1] = self.eff["color_map"](frame[fys, fxs].astype(np.float32))
        self._n = i1
        if burst:
            self.bursts_fired += 1

    def _update_particles(self, dt: float):
        """Advance the alive slice: swirl field, drag, buoyancy, ageing."""
        n = self._n
        if n == 0:
            return
        t = time.time() - self._start_t
        ang = t * self.eff["swirl_rate"]
        ox = self._px[:n] - FRAME_W / 2
        oy = self._py[:n] - FRAME_H / 2
        swirl_gain = 0.9 + 0.35 * math.sin(ang)
        self._vx[:n] += (-oy * 0.012 * swirl_gain) * dt
        self._vy[:n] += (ox * 0.012 * swirl_gain) * dt
        drag = 1.0 - min(0.9, 0.85 * dt)
        self._vx[:n] *= drag
        self._vy[:n] *= drag
        self._vy[:n] -= self.eff["buoyancy"] * dt    # preset buoyancy (may sink)
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
        fade_norm = 1.0 - self._age[:n] / PARTICLE_LIFETIME_S
        np.clip(fade_norm, 0.0, 1.0, out=fade_norm)
        floor = self.eff["brightness_floor"]
        fade = floor + (1.0 - floor) * fade_norm ** self.eff["fade_exp"]
        glow = self._glow
        glow.fill(0.0)
        np.add.at(glow, (ys, xs), self._col[:n] * fade[:, None] * 0.55)
        halo = cv2.GaussianBlur(glow, (0, 0), self.eff["glow_sigma"])
        core = cv2.resize(glow, (FRAME_W, FRAME_H), interpolation=cv2.INTER_NEAREST)
        full = cv2.resize(halo, (FRAME_W, FRAME_H), interpolation=cv2.INTER_LINEAR)
        out = canvas.astype(np.float32)
        out += core * self.eff["core_gain"]
        out += full * self.eff["halo_gain"]
        np.clip(out, 0.0, 255.0, out=out)
        canvas[:] = out.astype(np.uint8)

    # -- whispers -------------------------------------------------------------------

    def _maybe_texture(self, energy, gesture, cells):
        """Keep a whisper texture playing: a new clip starts when the
        previous one has ended (clips are ~2.2 s), so the bed is
        continuous but never overlaps. Intensity follows motion energy,
        formants follow the gesture state, stereo pan follows the
        horizontal centroid of motion. No-op when audio is unavailable
        (degraded SoundPlayer) — the visuals must never depend on sound.
        """
        if not self.sound_enabled or self.sound_player is None:
            return False
        now = time.time()
        if now < self._last_texture_end_t:
            return False  # previous clip still playing
        try:
            ys, xs = np.nonzero(cells)
            if ys.size:
                pan = float(np.clip((xs.mean() / DIFF_W) * 2.0 - 1.0, -1.0, 1.0))
            else:
                pan = 0.0
            data, sr = self.texture.clip(energy, gesture, pan)
            self.sound_player.play_audio(data, samplerate=sr, blocking=False)
            self.texture_clips_played += 1
            self._last_texture_end_t = now + data.shape[0] / sr - 0.15
            return True
        except Exception as e:
            # audio degraded: disable the texture, keep the loop alive
            self.logger.warning("Whispers: texture audio unavailable (%s); disabling sound.", e)
            self.sound_enabled = False
            return False

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
        with self._whisper_lock:
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
        """`space`: whisper now, bypassing the quiet-gap (demo control).

        The gap clock restarts from this forced whisper (a spoken line
        must never overlap the next), but the *attempt* is not re-fired
        on the next frame: `_maybe_whisper` already stamped the time.
        """
        saved = self._last_whisper_t
        ok = self._maybe_whisper(1e6)
        if not ok:
            # refused (busy synthesising): leave the gap clock untouched
            self._last_whisper_t = saved

    # -- controls ----------------------------------------------------------------------

    def _poll_midi(self):
        """Optional MIDI controls, as multiplicative user-adjustments on
        the preset (default 1.0). CC74 size/brightness, CC71 swirl rate,
        CC73 emission density, CC91 trail persistence. Absent or degraded
        MIDI leaves everything at 1.0."""
        midi = getattr(self.manager, "midi_input", None)
        if midi is None:
            return
        try:
            for cc, key in ((74, "size"), (71, "swirl"), (73, "emission"), (91, "trail")):
                v = midi.get(cc, default=-1.0)
                if v < 0:
                    continue
                # 0..1 fader -> 0.5x..1.5x user-adjust, centred at 0.5
                self.midi_adjust[key] = 0.5 + v
        except Exception:
            pass  # MIDI degraded: controls simply stop responding

    def _poll_controls(self):
        """Edge-triggered keys. Two sources are tracked SEPARATELY so they
        cannot eat each other's edges: (a) pynput/pyglet state via
        is_key_pressed, (b) the OpenCV renderer's last_key. A held-key
        discard in one source must not suppress a fresh press reported by
        the other, and a key whose poll raised (exhausted mock, flaky
        backend) keeps its previous membership instead of looking
        released."""
        pressed = set()
        for k in ("c", "m", "space", "h", "s", "q", "1", "2", "3", "4"):
            try:
                if self.keyboard.is_key_pressed(k):
                    pressed.add(k)
            except Exception:
                if k in self._held:
                    pressed.add(k)  # carry over: an error is not a release

        cv_key = getattr(self.renderer, "last_key", None)
        if cv_key is not None:
            if cv_key != self._prev_cv_key:
                pressed.add(cv_key)   # fresh edge in the window
            # same key two frames running = still held: no edge
        self._prev_cv_key = cv_key

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
        elif k == "s":
            self.sound_enabled = not self.sound_enabled
            if not self.sound_enabled:
                try:
                    self.sound_player.stop_sound()
                except Exception:
                    pass
            self.logger.info("Whispers: sound %s.", "on" if self.sound_enabled else "off")
        elif k in PRESET_KEYS:
            self.apply_preset(PRESET_KEYS[k], lerp=True)
            self.logger.info(
                "Whispers: preset -> %s (%s).", k, self.preset_label
            )
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
            f"whispers  |  {self.preset_label}  |  source: {self.source_kind} ({self.source_detail})",
            f"{self.fps:5.1f} fps  |  {self._n} particles / cap {self.particle_cap}"
            f"  |  energy {self.motion_energy:.1f}  |  {self._gesture_now}",
            f"whispers spoken {self.whispers_spoken} / attempted {self.whispers_attempted}"
            f"  |  texture {self.texture_clips_played}"
            + ("" if self.sound_enabled else "  (muted)"),
            "[c] clear  [m] motion  [space] whisper  [s] sound  [1-4] preset  [h] hud  [q] quit",
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
                self._poll_midi()

                frame = self._read_source_frame()
                gray = self._grey_grid(frame)
                energy, cells, flow_x, flow_y, gesture = self._motion_field(gray)
                self.motion_energy = energy
                self._energy_ema = 0.94 * self._energy_ema + 0.06 * energy
                self._prev_gray = gray
                self._update_state_blend(gesture, dt)

                # trails: decay the canvas toward the tinted source frame
                eff = self.eff
                src = frame.astype(np.float32)
                tint = np.array(eff["bg_tint"], dtype=np.float32)
                k = eff["bg_tint_k"]
                src = src * (1.0 - k) + tint * k
                prev = canvas.astype(np.float32)
                blended = src * (1.0 - self.trail_alpha) + prev * self.trail_alpha
                canvas[:] = np.clip(blended, 0, 255).astype(np.uint8)

                self._spawn(frame, cells, flow_x, flow_y, energy, gesture, dt)
                self._update_particles(dt)
                self._draw_particles(canvas)

                if self._show_motion:
                    self._draw_motion_overlay(canvas, cells)
                if self._show_hud:
                    self._draw_hud(canvas)

                self._maybe_whisper(energy)
                self._maybe_texture(energy, gesture, cells)

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