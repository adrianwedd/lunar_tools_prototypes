# Audio Mirror & MLX Migration Design

**Date:** 2026-03-25
**Status:** Draft (Rev 2 — post QA)
**Author:** Adrian + Claude

---

## 1. Overview

Two separate prototypes, developed independently with shared infrastructure:

**Deliverable A: Mirror of Truth Rewrite** — Rebuild the existing hackathon prototype with real MLX models replacing all simulated inference. Real facial emotion detection, real local TTS via Afterwords, pluggable LLM backends. Local sensing and TTS on Apple Silicon; LLM backend is configurable (local or cloud).

**Deliverable B: Audio Mirror** (new experiment) — An installation where the viewer's voice is progressively captured, cloned via Afterwords, and an AI oracle speaks back to them *in their own voice*, delivering personal insights. The cloned voice improves over the course of the interaction, building an emotional voice palette from each sample. Experimental — requires validation gates before full implementation.

Both prototypes share MLX infrastructure and the Afterwords TTS server but are distinct experiences with separate code in `prototypes/`.

### 1.1 Validation Gates (before full Audio Mirror implementation)

The following assumptions must be benchmarked on target hardware before committing to the full Audio Mirror build:

| Assumption | Benchmark needed | Pass criteria |
|-----------|-----------------|---------------|
| TTS wall-clock latency | Synthesize 2 sentences on 8GB M1 with Afterwords | < 25s per utterance |
| Clone quality from 5s sample | Clone from 5s noisy room audio, subjective listen | Recognizably same speaker (not just same gender) |
| Clone quality from 15s sample | Clone from 15s noisy room audio, subjective listen | Clearly the same person |
| Memory pressure | Run Afterwords + prototype + camera + Whisper simultaneously | No swapping, `memory_pressure` stays normal |
| MLX emotion model | Find, load, and run candidate model on 8GB M1 | >15fps face+emotion, <300MB memory |
| Whisper under installation acoustics | Transcribe speech in noisy room with ambient sound | WER < 20% for clear speech |

If any gate fails on 8GB, the spec targets 16GB+ (new Mac) as the minimum. The Mirror of Truth rewrite proceeds regardless — it has fewer constraints.

---

## 2. Audio Mirror — Concept & Artistic Intent

The Audio Mirror is not a chatbot. It is an oracle that speaks in your voice.

The installation observes the viewer through their face, voice, words, and hesitations, then synthesizes something genuinely perceptive. It delivers that insight *as the viewer*, in their own cloned voice. The effect is hearing yourself say something true about yourself that you never articulated.

The artistic goal is revelation, not reflection. The uncanny valley of hearing your own voice is a vehicle for emotional impact, not the point itself. The installation should make people *feel something* and leave with a personal insight they didn't arrive with.

### 2.1 Progressive Voice Palette

The core technical concept: Qwen3-TTS is zero-shot — it doesn't train on the viewer, it takes a reference clip + transcript and generates speech that sounds like the reference. "Improving with time" means **building a palette of the viewer's voice across emotional states**.

Each time the viewer speaks, the installation captures a new reference clip tagged with its emotional context (from prosody analysis and facial emotion detection). Over the course of the interaction, the palette grows:

```
Early (Phase 2):
  viewer-001.wav  [neutral, 5s, confidence: 0.4]  "My name is Sarah"

Mid (Phase 3):
  viewer-001.wav  [neutral, 5s, confidence: 0.4]    "My name is Sarah"
  viewer-002.wav  [vulnerable, 8s, confidence: 0.7]  "I'm afraid of being forgotten"
  viewer-003.wav  [passionate, 12s, confidence: 0.8] "What I really care about is..."

Late (Phase 4):
  viewer-001.wav  [neutral, 5s, confidence: 0.4]
  viewer-002.wav  [vulnerable, 8s, confidence: 0.7]
  viewer-003.wav  [passionate, 12s, confidence: 0.8]
  viewer-004.wav  [tender, 10s, confidence: 0.9]    "The person I miss most is..."
```

When the entity speaks, it **selects the reference clip whose emotional tone matches what the entity wants to say**. A comforting insight uses the viewer's gentle voice. A challenging one uses their passionate voice. The viewer hears themselves in the right emotional register.

The viewer notices this progression — the voice getting closer to theirs, matching their emotional texture. This is part of the art: the entity is learning you, and you can hear it.

**Voice quality metrics (operational thresholds):**
- `reference_duration < 5s` → do not attempt clone, use default voice
- `5s <= reference_duration < 10s` → attempt clone, quality = "rough" (may not sound like viewer)
- `10s <= reference_duration < 15s` → quality = "developing" (recognizable but imperfect)
- `reference_duration >= 15s` → quality = "good" (clearly the viewer)
- Transcript confidence (from Whisper) < 0.6 → flag for re-capture, don't use as reference
- Multiple clips available → select by closest emotional match, prefer longer/higher-confidence clips

### 2.2 Interaction Phases

**Phase 0: Idle**
- Screen shows ambient visual or dark mirror surface
- Camera watches for face detection
- No audio output
- Installation is patient — it waits

*Edge cases: Multiple faces → select largest/closest face as primary viewer. Second face appearing during active session → ignore (single-viewer experience). If primary face disappears for >10s → begin departure sequence.*

**Phase 1: Detection**
- Face detected in camera frame
- Screen shifts — viewer's reflection appears with a subtle visual treatment signaling awareness
- Installation speaks in a **default Afterwords voice** (e.g., galadriel): *"Say your name."* or *"Hello. Speak to me."*
- The default voice is intentionally *not* the viewer's — the transition to their own voice is the arc

*Edge cases: Face detected but no speech for >30s → re-prompt with different phrasing. Face lost during prompt → return to Idle after 10s grace period.*

**Phase 2: First Capture**
- Viewer speaks
- Audio captured → Whisper transcription + prosody analysis (pitch, energy, pace, pauses)
- First voice palette entry created and registered with Afterwords
- **If reference >= 5s:** attempt first clone. Installation speaks back something simple in the viewer's rough-cloned voice — the first uncanny moment. Quality may be imperfect, and that's part of the experience.
- **If reference < 5s:** continue in default voice, note that the entity is "still learning your voice"
- The LLM receives the transcript + prosody + facial emotion data

*Edge cases: STT failure (empty transcript) → re-prompt: "I didn't catch that. Say it again?" Clone failure (Afterwords returns error) → continue in default voice, log error, retry on next capture. Low-confidence transcript → still use audio for voice profile, but flag transcript for LLM as uncertain.*

**Phase 3: Deepening**
- Installation asks for more, using prompts designed to elicit emotional range and longer speech:
  - *"Tell me something you've never told anyone."*
  - *"What are you afraid of?"*
  - *"Describe someone you miss."*
  - *"What would you say to yourself ten years ago?"*
- Each response:
  - Adds a new voice palette entry (tagged with detected emotion + prosody)
  - Feeds the LLM with emotional/content analysis
  - Updates the cumulative viewer profile
- The entity's voice progressively shifts from default → rough clone → better clone → emotionally-matched clone. The viewer can hear the entity learning them.
- The installation adapts its prompting strategy based on accumulated observations:
  - Nervous viewer → gentler, more open prompts
  - Playful viewer → more provocative, challenging prompts
  - Guarded viewer → indirect prompts, metaphorical questions
  - Emotional viewer → deeper, more intimate prompts
- The re-prompting is itself part of the art — the questions are crafted to take people somewhere

*Transition criteria to Phase 4: minimum 3 deepening exchanges AND at least one voice palette entry with quality >= "developing" AND LLM signals readiness to deliver insight. If after 5 exchanges the voice quality is still "rough", proceed anyway — the insight matters more than perfect voice quality.*

*Edge cases: Viewer falls silent → wait 15s, then gentle re-prompt. Viewer walks away mid-recording → save partial capture if >3s, begin departure. Prolonged silence (>60s) → departure. Bad/noisy mic → attempt denoise, lower confidence threshold, rely more on prosody than transcript content.*

**Phase 4: The Oracle**
- The entity has enough material
- The LLM synthesizes an insight from everything observed:
  - Facial emotions over time (the trajectory, not just current state)
  - Voice prosody patterns (where they hesitated, sped up, pitch changed)
  - Content of what they said (themes, contradictions, recurring words)
  - Patterns the LLM infers from the data (not "body language" or "what they didn't say" as hard claims, but patterns the LLM identifies from available signals)
- The insight is delivered in the **best available voice palette entry** whose emotional tone matches the insight's intent
- This is the peak moment of the experience
- The display shifts to complement the audio — abstract visuals driven by the emotional state

*Edge cases: TTS currently synthesizing when viewer departs → cancel synthesis, don't play to empty room. LLM generates inappropriate/harmful insight → system prompt constraints should prevent this, but prototype should have a content filter as safety net.*

**Phase 5: Departure**
- Interaction winds down naturally or viewer walks away (face lost for >10s)
- Voice palette is **deleted by default** (see Privacy section)
- If consent mechanism is enabled: offer to let viewer keep a recording of the oracle moment
- Installation returns to Idle, ready for next viewer

### 2.3 Experience Permutations

The installation is adaptive. The emotional/behavioural state of the viewer determines the direction. This isn't a branching tree — it's a continuous adaptive space where the LLM decides the direction based on accumulated observations, guided by the system prompt's artistic intent.

Examples of emergent directions:

- **The Comforter** — Viewer is anxious, hesitant. Entity speaks gently (using their vulnerable voice palette entry), offers reassurance. Insight focuses on hidden strength.
- **The Challenger** — Viewer is confident, guarded. Entity pushes back (using their passionate voice), asks harder questions. Insight reveals a vulnerability they're protecting.
- **The Mirror** — Viewer is self-aware, reflective. Entity mirrors precisely, then shows something just beyond their current self-understanding.
- **The Poet** — Viewer is emotional, open. Entity responds with metaphor and beauty (using their tender voice). Insight is delivered as something lyrical.
- **The Comedian** — Viewer is playful, deflecting. Entity plays along, then catches them off-guard with something genuine.

These emerge from the LLM's interpretation of the data, not hard-coded modes.

### 2.4 Display

- **Primary**: Live camera feed displayed as a mirror — the viewer sees themselves
- **Overlays**: Subtle audio visualizations — waveforms, emotion state indicators, abstract patterns responding to voice analysis
- **Transitions**: Visual treatments shift as the interaction deepens — the mirror becomes more dreamlike, colours shift with emotional state
- **Text**: Optionally display fragments of the entity's observations or the viewer's transcribed words
- Real-time facial dubbing/lip sync is not currently viable on MLX — the live mirror feed is unmodified video. The uncanny effect comes from the audio, not the visual.

---

## 3. Architecture

### 3.1 System Topology

```
┌──────────────────────────────────────────────────────────────┐
│  Mac (Apple Silicon, 8GB+ / 16GB+ recommended)               │
│                                                              │
│  ┌─────────────────────────┐  ┌────────────────────────────┐ │
│  │  Audio Mirror / MoT      │  │  Afterwords TTS Server     │ │
│  │  (prototype process)     │  │  localhost:7860             │ │
│  │                          │  │  Qwen3-TTS (MLX, ~6GB)     │ │
│  │  - Face detection (MLX)  │  │                            │ │
│  │  - Emotion classif (MLX) │  │  GET  /health              │ │
│  │  - Prosody (librosa/CPU) │──│  GET  /synthesize          │ │
│  │  - Whisper (MLX or CPU)  │  │  POST /clone    (new)      │ │
│  │  - Interaction FSM       │  │  POST /synthesize (new)    │ │
│  │  - Display/rendering     │  │                            │ │
│  │  - Mic capture           │  │  Runtime voice registry    │ │
│  └─────────────────────────┘  │  Atomic WAV/JSON writes     │ │
│                                │  Synth lock coordination    │ │
│  ┌─────────────────────────┐  └────────────────────────────┘ │
│  │  LLM Backend (pluggable) │                                │
│  │  - Claude API            │  ┌────────────────────────────┐ │
│  │  - Ollama (local)        │  │  Raspberry Pi(s) (optional) │ │
│  │  - Ollama Cloud (free)   │  │  - Proximity sensors       │ │
│  │  - OpenRouter (free)     │  │  - Secondary display       │ │
│  └─────────────────────────┘  └────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 Sensing Layer (in-process, real-time)

All sensing runs in the prototype process for low latency.

**Camera → Face Detection + Emotion Classification**
- MLX-optimized model for facial emotion recognition
- Candidates (require benchmarking — see Validation Gates):
  - MobileFaceNet or EfficientNet-based classifier trained on FER2013/AffectNet, converted to MLX
  - Apple Vision framework as fallback (face detection only, no emotion — available on macOS without extra deps)
  - OpenCV DNN module with a lightweight ONNX emotion model as CPU fallback
- Outputs: face bounding box, emotion probabilities (joy, sadness, anger, fear, surprise, contempt, neutral), confidence score
- Target: >15fps face detection + emotion classification
- **Fallback chain**: MLX emotion model → OpenCV DNN ONNX → OpenCV Haar cascade (face detection only, no emotion)

**Microphone → Audio Capture**
- Continuous listening for presence detection (ambient energy level)
- Triggered recording when the installation prompts the viewer to speak
- Raw audio saved for voice cloning pipeline
- Audio streamed to prosody analyzer

**Prosody Analysis (librosa, CPU)**
- Pitch (F0) tracking — rises indicate excitement/questions, drops indicate certainty/sadness
- Energy/RMS — loud vs quiet, where they trail off
- Speaking rate — words per second, acceleration/deceleration
- Pause detection — hesitations, thinking pauses, emotional pauses
- Spectral features — breathiness, vocal fry, tension
- No ML model needed — signal processing only

**Whisper Transcription**
- Primary: faster-whisper (CPU, already an Afterwords dependency) — avoids MLX memory contention on 8GB
- Alternative: mlx-whisper in-process (use on 16GB+ machines for lower latency)
- The transcription result includes per-word confidence and timestamps (used for prosody alignment)

### 3.3 Brain Layer (pluggable LLM)

The LLM is the artistic core. It receives structured observations and generates the entity's responses.

**Input to LLM:**
```json
{
  "phase": "deepening",
  "interaction_count": 3,
  "voice_palette_quality": "developing",
  "voice_palette_entries": 3,
  "viewer": {
    "facial_emotions": [
      {"timestamp": 1.2, "primary": "neutral", "intensity": 0.6},
      {"timestamp": 3.5, "primary": "surprise", "intensity": 0.8},
      {"timestamp": 7.1, "primary": "joy", "intensity": 0.4}
    ],
    "emotion_trajectory": "neutral → surprise → settling into mild joy",
    "transcripts": [
      {"text": "My name is Sarah", "prosody": {"pitch_mean": 210, "energy": 0.6, "pace_wps": 2.1, "pauses": []}, "confidence": 0.95},
      {"text": "I guess... I'm afraid of being forgotten", "prosody": {"pitch_mean": 195, "energy": 0.4, "pace_wps": 1.4, "pauses": [{"at": 1.2, "duration": 0.8}]}, "confidence": 0.91}
    ],
    "presence": {"duration_s": 45, "face_visible": true, "gaze_toward_screen": true}
  }
}
```

Note: The input contains only what the system actually measures — facial emotion, prosody, transcripts, presence. The LLM infers higher-level patterns (contradictions, avoidance, themes) from this data. We do not claim to detect "body language" or "what they didn't say" as sensor outputs.

**System Prompt (artistic direction):**
The system prompt defines:
- The entity's role (oracle, not chatbot — observe, synthesize, reveal)
- The artistic intent (revelation, not reflection)
- Guidelines for insight generation (find patterns, contradictions, emotional trajectories)
- Tone calibration based on detected state
- When to prompt for more material vs deliver the insight
- Constraints (never cruel, never trivializing, always genuine, never claim to know what the viewer is "hiding")
- Emotional voice selection guidance (which palette entry to use for each response)

**LLM Backend Abstraction:**
```python
class LLMBackend(ABC):
    @abstractmethod
    def generate(self, prompt: str, system_prompt: str | None = None) -> str: ...

class ClaudeBackend(LLMBackend): ...       # Anthropic API
class OllamaLocalBackend(LLMBackend): ...  # localhost:11434
class OllamaCloudBackend(LLMBackend): ...  # Ollama Cloud API (free tier)
class OpenRouterBackend(LLMBackend): ...   # OpenRouter API (free models)
```

Selected via `settings.toml`:
```toml
[llm]
provider = "claude"  # claude | ollama | ollama-cloud | openrouter

[llm.claude]
model = "claude-sonnet-4-20250514"

[llm.ollama]
model = "llama3.1:8b"

[llm.ollama_cloud]
model = "llama3.1:70b"
api_key_env = "OLLAMA_CLOUD_API_KEY"  # pragma: allowlist secret

[llm.openrouter]
model = "meta-llama/llama-3.1-8b-instruct:free"
api_key_env = "OPENROUTER_API_KEY"  # pragma: allowlist secret
```

### 3.4 Output Layer

**Voice Synthesis → Afterwords Server**
- Prototype sends text + voice name + optional emotion tag via `POST /synthesize`
- Afterwords selects the best matching voice palette entry for the requested emotion
- Returns WAV audio
- Prototype plays audio through speakers (afplay or SoundPlayer)

**Progressive Voice Cloning → New Afterwords Capabilities**

The Afterwords server needs the following changes (not just one endpoint):

1. **`POST /clone`** — Accept raw audio + voice name + emotion tag + session ID + pre-computed transcript
   - The prototype performs Whisper transcription and prosody analysis before calling `/clone` (avoids duplicate STT work and memory pressure on the server)
   - Process: denoise (noisereduce) → validate provided transcript against audio duration → save WAV + JSON profile → register in runtime VOICES map
   - If no transcript provided: server falls back to its own faster-whisper transcription
   - Atomic file writes: write to temp path, validate, rename into `voices/`
   - Returns: `{"voice": "viewer-abc123-001", "emotion": "vulnerable", "quality": "developing", "transcript_confidence": 0.91, "duration_s": 8.2, "sequence": 1}`
   - Must coordinate with `_synth_lock` — clone operations are serialized with synthesis (MLX Metal constraint)

2. **Runtime voice registry** — The current `VOICES` dict is populated at startup only. Add:
   - `_register_voice(name, ref_audio, ref_text, emotion_tag, metadata)` — thread-safe runtime registration
   - Voice palette support: entries keyed by `{session_id}-{sequence_number}` (e.g., `viewer-abc123-001`), with emotion tag and quality/duration/confidence stored as metadata. Selection logic picks the best matching clip by emotion similarity, preferring longer duration and higher confidence. Later captures do NOT overwrite earlier ones — the palette grows.
   - `_unregister_session(session_id)` — remove all palette entries for a session (cleanup on departure)

3. **`POST /synthesize`** (new, alongside existing GET) — Accept JSON body instead of query params for sensitive text:
   ```json
   {"text": "...", "voice": "viewer-abc123", "emotion": "vulnerable"}
   ```
   - If `emotion` is specified, selects the best matching palette entry for that session
   - Falls back to highest-quality entry if no emotion match

4. **Security**: Bind to `127.0.0.1` by default (not `0.0.0.0`) when clone endpoint is enabled. The current `0.0.0.0` binding exposes voice enrollment to the local network.

**Display → Live Mirror + Overlays**
- Camera feed rendered to screen (OpenCV window or OpenGL renderer)
- Overlaid elements:
  - Waveform visualization of current audio (capture or playback)
  - Emotion state indicator (subtle colour shifts)
  - Optional text fragments
- Rendering runs in its own thread, must not block sensing or audio pipeline

### 3.5 Latency Budget

The full path from viewer speech to entity response is:

| Step | Estimated time | Can overlap? |
|------|---------------|-------------|
| Audio capture | 3-15s (viewer speaking) | — |
| Denoise + Whisper transcription | ~2-3s (faster-whisper base.en, prototype-side) | — |
| Prosody analysis | ~0.2s | Yes, parallel with transcription |
| Clone registration (POST /clone) | ~1s (denoise + file write + register; no duplicate STT since transcript provided) | Yes, parallel with LLM call |
| LLM generation | 2-5s (cloud) / 5-15s (local) | — |
| TTS synthesis | 15-25s (Afterwords on 8GB M1) | — |
| **Total viewer-visible wait** | **~20-35s after viewer stops speaking** | |

This is too long for silence. **The installation must fill the gap:**
- Visual transitions during processing (the mirror shifts, becomes dreamlike)
- Ambient sound design (subtle audio textures while "thinking")
- Short spoken acknowledgments in default voice: *"I hear you..."*, *"Let me think about that..."*
- The LLM call and clone registration happen in parallel — the clone doesn't block the insight

On 16GB+ Mac: mlx-whisper is faster (~1s), TTS may be faster with more memory headroom, and local LLM removes network latency.

### 3.6 Memory Budget

**8GB Mac (floor — must pass validation gates):**

| Component | Memory | Notes |
|-----------|--------|-------|
| macOS + system | ~1.5 GB | Baseline OS overhead |
| Qwen3-TTS (Afterwords, separate process) | ~6 GB peak | Proven on 8GB M1. Shares unified memory. |
| Face detection + emotion (MLX, in prototype) | ~200 MB | Must benchmark — see validation gates |
| faster-whisper base.en (CPU) | ~150 MB | CPU-only, no Metal contention |
| Prototype overhead (Python, OpenCV, librosa) | ~200 MB | Conservative estimate |
| **Total** | **~8 GB** | Tight. May swap during TTS peaks. |

This is at the limit. 8GB is viable for basic operation but **swapping during TTS synthesis peaks is likely**. The new Mac (16GB+) is the recommended target. 8GB works if: Whisper uses CPU (not MLX), emotion model is <200MB, and we accept occasional latency spikes.

**16GB+ Mac (recommended):**

| Component | Memory | Notes |
|-----------|--------|-------|
| macOS + system | ~2 GB | |
| Qwen3-TTS (Afterwords) | ~6 GB | Comfortable headroom |
| Face + emotion (MLX) | ~200 MB | Room for larger model |
| mlx-whisper base.en | ~200 MB | MLX instead of CPU — faster |
| Prototype overhead | ~300 MB | |
| **Headroom** | **~7 GB** | Room for local LLM, larger Whisper, etc. |

---

## 4. Mirror of Truth Rewrite

Separate prototype, same infrastructure. Proceeds independently of Audio Mirror.

### 4.1 What Changes

| Component | Hackathon (simulated) | Rewrite (real) |
|-----------|----------------------|----------------|
| Face detection | OpenCV Haar cascades | MLX model (shared with Audio Mirror) |
| Emotion detection | `random.choice()` | MLX emotion classification model |
| Voice sentiment | OpenAI API | Local Whisper + prosody analysis |
| TTS | OpenAI TTS API | Afterwords server (preset voices) |
| LLM | GPT-4 only | Pluggable (Claude/Ollama/OllamaCloud/OpenRouter) |
| Image generation | DALL-E 3 API | Keep API for now; MLX Stable Diffusion in Phase 3 |
| Visuals | PIL procedural art | Enhanced PIL + potential OpenGL |
| Scope claim | "Runs entirely on Apple Silicon" | Local sensing + TTS; LLM optionally cloud |

### 4.2 What Stays

- The interaction concept (entity personality generation, emotional response)
- The prototype structure (class with `setup()`, `update()`, `cleanup()`)
- Manager-based resource management
- Keyboard exit handling

### 4.3 Phased Approach

1. **Phase 1**: Replace simulated emotion detection with real MLX model. Replace TTS with Afterwords. Plug in LLM abstraction.
2. **Phase 2**: Add prosody analysis. Improve visual generation. Add experience branching.
3. **Phase 3**: Local image generation via MLX Stable Diffusion (16GB+ Mac only).

---

## 5. Shared Infrastructure — New Components

### 5.1 LLM Backend Abstraction

New file: `src/lunar_tools_art/llm_backends.py`

Common interface for all LLM providers. Each backend implements `.generate(prompt, system_prompt)` → `str`. Configuration via `settings.toml`. The existing `GPT4` and `Ollama` classes in `tools.py` get refactored into this abstraction.

### 5.2 MLX Emotion Detection

New file: `src/lunar_tools_art/emotion.py`

Wraps facial emotion detection with a fallback chain.

```python
class EmotionDetector:
    def detect(self, frame: np.ndarray) -> list[EmotionResult]:
        """Returns detected faces with emotion probabilities."""

class EmotionResult:
    bbox: tuple[int, int, int, int]
    emotions: dict[str, float]  # emotion → probability
    primary_emotion: str
    confidence: float
```

Fallback chain: MLX model → OpenCV DNN ONNX → Haar cascade (face only, no emotions).

### 5.3 Prosody Analyzer

New file: `src/lunar_tools_art/prosody.py`

Pure signal processing with librosa. No ML model needed.
```python
class ProsodyAnalyzer:
    def analyze(self, audio: np.ndarray, sr: int) -> ProsodyResult:
        """Returns pitch, energy, pace, pause locations, spectral features."""

class ProsodyResult:
    pitch_mean: float
    pitch_variance: float
    energy_rms: float
    pace_wps: float  # words per second (requires transcript alignment)
    pauses: list[PauseEvent]  # location + duration
    spectral_centroid: float
    emotion_tag: str  # inferred from prosody: "neutral", "agitated", "calm", etc.
```

### 5.4 Voice Client

New file: `src/lunar_tools_art/voice_client.py`

Client for the Afterwords TTS server, including progressive voice palette management.

```python
class VoiceClient:
    def __init__(self, server_url: str = "http://localhost:7860"): ...
    def health(self) -> dict: ...
    def list_voices(self) -> list[str]: ...
    def synthesize(self, text: str, voice: str, emotion: str | None = None) -> bytes: ...
    def clone_voice(self, audio: bytes, session_id: str, emotion: str) -> CloneResult: ...
    def cleanup_session(self, session_id: str) -> None: ...

class CloneResult:
    voice_name: str
    emotion: str
    quality: str  # "rough" | "developing" | "good"
    transcript: str
    transcript_confidence: float
    duration_s: float
```

### 5.5 Afterwords Server Extensions

Changes needed in `../afterwords/server.py`:

1. **`POST /clone`** — runtime voice creation from raw audio
2. **`POST /synthesize`** — JSON body alternative to GET (for sensitive text)
3. **Runtime voice registry** — thread-safe registration/unregistration, palette support
4. **Session cleanup** — `DELETE /session/{session_id}` removes all palette entries + files
5. **Bind to 127.0.0.1** by default when clone endpoint is active
6. **Lock coordination** — clone operations serialize with `_synth_lock`

These are significant changes to Afterwords, not a single endpoint. They should be implemented and tested in the Afterwords repo separately.

---

## 6. Privacy & Consent

This installation captures voice, face, and emotional data. Privacy must be designed in, not bolted on.

### 6.1 Policy

| Principle | Implementation |
|-----------|---------------|
| **Default: no persistence** | Voice palette files deleted when session ends (face lost for >10s) |
| **No raw audio leaves the Mac** | Audio is captured, processed, and deleted locally. Voice profiles are WAV snippets, not full recordings. |
| **Cloud LLM receives transcripts + emotion summaries** | This IS sending personal data to a cloud service. When using Claude/OpenRouter/Ollama Cloud, transcripts and emotional analysis are sent over HTTPS. |
| **Local-only mode** | When LLM provider is `ollama` (local), no data leaves the machine at all. This is the privacy-maximum configuration. |
| **Consent** | If the installation is in a public gallery: signage indicating voice capture + AI analysis. No opt-in gate for the basic experience (the experience IS the interaction). Optional opt-in for archival/recording. |
| **Minors** | Not addressed in V1. Gallery operator responsible for age-appropriate deployment. |
| **Bystanders** | Single-face targeting. Other faces in frame are detected but not processed. Audio capture is directional (close-mic preferred). |
| **Retention** | Session data (voice palette, transcripts, emotion logs) deleted immediately on session end. If archival is enabled: retained for max 24h, then auto-deleted. |

### 6.2 Configuration

```toml
[privacy]
mode = "local-only"  # "local-only" | "cloud-llm" — controls whether data leaves the machine
auto_delete_session = true
archive_enabled = false
archive_retention_hours = 24
```

When `mode = "local-only"`, the LLM provider is forced to `ollama` regardless of the `[llm]` setting. This provides a hard guarantee.

---

## 7. Interaction State Machine

Formal FSM for the Audio Mirror, addressing edge cases:

```
IDLE ──[face detected]──→ DETECTION
DETECTION ──[speech detected]──→ FIRST_CAPTURE
DETECTION ──[no speech 30s]──→ DETECTION (re-prompt, max 3 retries)
DETECTION ──[no speech after 3 retries]──→ IDLE
DETECTION ──[face lost 10s]──→ IDLE
FIRST_CAPTURE ──[capture complete]──→ DEEPENING
FIRST_CAPTURE ──[STT failure]──→ DETECTION (re-prompt)
FIRST_CAPTURE ──[face lost 10s]──→ DEPARTURE
DEEPENING ──[transition criteria met]──→ ORACLE
DEEPENING ──[max exchanges (5) without quality]──→ ORACLE (proceed anyway)
DEEPENING ──[silence 15s]──→ DEEPENING (re-prompt)
DEEPENING ──[silence 60s]──→ DEPARTURE
DEEPENING ──[face lost 10s]──→ DEPARTURE
ORACLE ──[insight delivered]──→ DEPARTURE
ORACLE ──[face lost during synthesis]──→ DEPARTURE (cancel playback)
DEPARTURE ──[cleanup complete]──→ IDLE
```

**Timeouts:**
- Face lost grace period: 10s
- Speech timeout (per prompt): 30s
- Total silence timeout: 60s
- Max interaction duration: 300s (5 min)
- Max deepening exchanges: 5
- Min deepening exchanges before oracle: 3

**Failure handling:**
- STT failure → re-prompt (max 2 retries per exchange)
- Clone failure → continue in default voice, retry on next capture
- TTS failure → log, skip audio, continue interaction in text-on-screen mode
- LLM failure → use pre-written fallback insight, deliver in best available voice
- Afterwords server down → detected at startup, prototype refuses to start

---

## 8. Configuration

### 8.1 settings.toml

```toml
[llm]
# When privacy.mode = "local-only", this is forced to "ollama" regardless of setting
provider = "ollama"  # ollama | claude | ollama-cloud | openrouter

[llm.claude]
model = "claude-sonnet-4-20250514"
api_key_env = "ANTHROPIC_API_KEY"  # pragma: allowlist secret

[llm.ollama]
model = "llama3.1:8b"
base_url = "http://localhost:11434"

[llm.ollama_cloud]
model = "llama3.1:70b"
api_key_env = "OLLAMA_CLOUD_API_KEY"  # pragma: allowlist secret

[llm.openrouter]
model = "meta-llama/llama-3.1-8b-instruct:free"
api_key_env = "OPENROUTER_API_KEY"  # pragma: allowlist secret

[afterwords]
server_url = "http://localhost:7860"
default_voice = "galadriel"

[emotion]
model = "auto"  # auto-selects best available
confidence_threshold = 0.5
fallback = "opencv-dnn"  # opencv-dnn | haar-cascade

[whisper]
backend = "faster-whisper"  # faster-whisper | mlx-whisper
model = "base.en"

[audio_mirror]
min_reference_duration_s = 5
good_reference_duration_s = 15
max_interaction_duration_s = 300
min_deepening_exchanges = 3
max_deepening_exchanges = 5
face_lost_grace_s = 10
speech_timeout_s = 30
silence_timeout_s = 60

[privacy]
mode = "local-only"  # "local-only" forces llm.provider to "ollama"; "cloud-llm" allows any provider
auto_delete_session = true
archive_enabled = false
archive_retention_hours = 24
```

### 8.2 Environment Variables

```bash
ANTHROPIC_API_KEY=...       # Claude API
OLLAMA_CLOUD_API_KEY=...    # Ollama Cloud
OPENROUTER_API_KEY=...      # OpenRouter
```

---

## 9. File Structure

```
prototypes/
  audio-mirror.py                    # New: Audio Mirror experiment
  ai-mirror-of-truth.py             # Rewritten: real MLX models

src/lunar_tools_art/
  llm_backends.py                    # New: pluggable LLM abstraction
  emotion.py                         # New: MLX facial emotion detection
  prosody.py                         # New: voice prosody analysis
  voice_client.py                    # New: Afterwords TTS + clone client
  tools.py                           # Existing: updated to use new backends
  manager.py                         # Existing: updated to init new components
  prototype_base.py                  # Existing: may add SensingPrototype base

tests/
  test_llm_backends.py               # Unit tests (mocked)
  test_emotion.py                    # Unit tests (mocked MLX)
  test_prosody.py                    # Unit tests (real signal processing)
  test_voice_client.py               # Unit tests (mocked HTTP)
  test_audio_mirror.py               # Smoke tests + FSM state transition tests
  test_mirror_of_truth_rewrite.py    # Smoke tests
```

---

## 10. Dependencies

### New requirements (this repo)

```
mlx >= 0.22.0               # Apple ML framework
opencv-python >= 4.9.0       # Camera + face detection + DNN fallback
anthropic >= 0.40.0          # Claude API client
httpx >= 0.27.0              # HTTP client for Afterwords
faster-whisper >= 1.0.0      # Speech-to-text (CPU, default)
```

Optional (16GB+ Mac):
```
mlx-whisper >= 0.4.0         # MLX-accelerated speech-to-text
```

### Afterwords changes (separate repo)

- `POST /clone` endpoint
- `POST /synthesize` endpoint
- Runtime voice registry with palette support
- Session cleanup endpoint
- 127.0.0.1 default bind
- Lock coordination for clone + synthesize

---

## 11. Risks & Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| 8GB memory too tight | High | Validation gate before implementation. 16GB+ recommended. 8GB works with CPU Whisper + small emotion model. |
| Voice clone quality from short/noisy samples | High | Progressive palette — rough is OK early. Quality thresholds prevent bad clones from being used. Default voice fallback always available. |
| MLX emotion model not available/accurate | High | Validation gate. Fallback chain to OpenCV DNN ONNX. Emotion from prosody + transcript is the reliable signal; facial emotion supplements it. |
| End-to-end latency too long | Medium | Explicit latency budget. Visual/audio gap-filling during processing. Parallel LLM + clone registration. Acknowledge this is not real-time conversation — it's a deliberate, contemplative experience. |
| LLM insight quality varies across backends | Medium | Claude API for best quality. System prompt optimized per-backend. Pre-written fallback insights for LLM failures. |
| Privacy — cloud LLM receives personal data | High | Local-only mode as default config. Explicit signage for gallery deployment. No raw audio sent to cloud — only transcripts + emotion summaries. |
| Afterwords server changes are significant | Medium | Implement and test Afterwords changes first, in that repo, before Audio Mirror depends on them. |
| Viewer has negative emotional reaction | Medium | System prompt constraints (never cruel/trivializing). Content safety net. Installation operator can intervene. |

---

## 12. Success Criteria

### Mirror of Truth Rewrite
1. Real facial emotion detection running on MLX, replacing all simulated values
2. TTS via Afterwords replacing OpenAI TTS API
3. LLM switchable between Claude/Ollama/OllamaCloud/OpenRouter via config
4. Runs on 8GB Apple Silicon alongside Afterwords

### Audio Mirror
1. Viewer approaches, speaks, and hears their own cloned voice deliver a personal insight within 3-5 minutes
2. Voice palette builds progressively — at least 3 emotional variants by Phase 4
3. Cloned voice is recognizably the viewer's after 15+ seconds of cumulative reference material
4. The installation adapts its approach based on detected emotional state
5. All validation gates pass on target hardware
6. Session data is deleted on departure by default

### Artistic (subjective, evaluated through user testing)
7. The insight moment genuinely affects the viewer
8. The progressive voice improvement is noticeable and adds to the experience
9. The experience feels like encountering something — not using a tool
