# Audio Mirror Experiment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Audio Mirror — an installation that captures a viewer's voice, progressively clones it via Afterwords, and speaks back to them in their own voice delivering personal insights. The cloned voice improves over the interaction, building an emotional voice palette.

**Architecture:** New prototype in `prototypes/audio-mirror.py` inheriting from `PrototypeBase`. Uses a finite state machine (IDLE → DETECTION → FIRST_CAPTURE → DEEPENING → ORACLE → DEPARTURE). Integrates all shared infrastructure: EmotionDetector for face/presence, ProsodyAnalyzer for voice analysis, VoiceClient for TTS + progressive cloning, pluggable LLM for insight generation. Display shows live camera mirror with overlays.

**Tech Stack:** Python 3.11+, OpenCV (camera + display), librosa, Afterwords TTS server (with clone extensions), pluggable LLM

**Spec:** `docs/superpowers/specs/2026-03-25-audio-mirror-and-mlx-migration-design.md` (Sections 2, 3, 7)

**Dependencies:**
- Shared infrastructure (complete)
- Afterwords server extensions (POST /clone, POST /synthesize, DELETE /session) — must be implemented first
- Validation gates should be run before full implementation (spec Section 1.1)

---

### Task 0: Run Validation Gates

**Files:**
- Create: `scripts/validation-gates.py`

**What:** Before building the full Audio Mirror, benchmark the key assumptions on target hardware. This is a script, not a test — run manually and evaluate results.

- [ ] **Step 1: Write validation script**

```python
#!/usr/bin/env python3
"""Audio Mirror Validation Gates — run on target hardware before implementation."""

# Gate 1: TTS latency — synthesize 2 sentences via Afterwords, measure wall-clock
# Gate 2: Memory pressure — monitor memory_pressure while running camera + Whisper + Afterwords
# Gate 3: Emotion model — find, load, benchmark candidate MLX emotion model
# Gate 4: Clone quality — clone from 5s and 15s samples, play back for subjective evaluation
# Gate 5: Whisper in noisy room — transcribe speech with ambient sound
```

- [ ] **Step 2: Run gates, document results**
- [ ] **Step 3: Commit**

```bash
git commit -m "feat: add validation gate script for Audio Mirror benchmarks"
```

---

### Task 1: Interaction State Machine

**Files:**
- Create: `src/lunar_tools_art/audio_mirror_fsm.py`
- Create: `tests/test_audio_mirror_fsm.py`

**What:** The core state machine that drives the Audio Mirror experience. Pure logic — no hardware dependencies. Receives events (face_detected, speech_captured, face_lost, timeout, etc.) and transitions between states, tracking session data.

- [ ] **Step 1: Write failing tests**

```python
def test_idle_to_detection_on_face():
    fsm = AudioMirrorFSM()
    assert fsm.state == "IDLE"
    fsm.on_face_detected()
    assert fsm.state == "DETECTION"

def test_detection_to_first_capture_on_speech():
    fsm = AudioMirrorFSM()
    fsm.on_face_detected()
    fsm.on_speech_captured(transcript="Hello", duration_s=5.0, confidence=0.9)
    assert fsm.state == "FIRST_CAPTURE"

def test_detection_returns_to_idle_after_max_retries():
    fsm = AudioMirrorFSM(max_detection_retries=3)
    fsm.on_face_detected()
    for _ in range(3):
        fsm.on_speech_timeout()
    assert fsm.state == "IDLE"

def test_deepening_to_oracle_on_criteria_met():
    fsm = AudioMirrorFSM(min_deepening_exchanges=2)
    fsm.on_face_detected()
    fsm.on_speech_captured("hi", 5.0, 0.9)
    fsm.on_capture_complete()
    # Two deepening exchanges
    fsm.on_speech_captured("something deep", 10.0, 0.9)
    fsm.on_speech_captured("more depth", 12.0, 0.9)
    fsm.on_oracle_ready()
    assert fsm.state == "ORACLE"

def test_face_lost_triggers_departure():
    fsm = AudioMirrorFSM()
    fsm.on_face_detected()
    fsm.on_speech_captured("hi", 5.0, 0.9)
    fsm.on_capture_complete()
    fsm.on_face_lost()
    assert fsm.state == "DEPARTURE"

def test_departure_cleans_up_to_idle():
    fsm = AudioMirrorFSM()
    fsm.on_face_detected()
    fsm.on_face_lost()
    fsm.on_cleanup_complete()
    assert fsm.state == "IDLE"

def test_session_tracks_voice_palette():
    fsm = AudioMirrorFSM()
    fsm.on_face_detected()
    fsm.on_speech_captured("hi", 5.0, 0.9)
    assert len(fsm.session.voice_entries) == 1
    fsm.on_capture_complete()
    fsm.on_speech_captured("more", 10.0, 0.85)
    assert len(fsm.session.voice_entries) == 2
```

- [ ] **Step 2: Implement FSM**

States: IDLE, DETECTION, FIRST_CAPTURE, DEEPENING, ORACLE, DEPARTURE
Session data: voice_entries, transcripts, emotion_timeline, interaction_count
Configurable: timeouts, min/max exchanges, quality thresholds

- [ ] **Step 3-5: Test, verify, commit**

```bash
git commit -m "feat: add Audio Mirror interaction state machine"
```

---

### Task 2: Audio Mirror Prototype Shell

**Files:**
- Create: `prototypes/audio-mirror.py`
- Create: `tests/test_audio_mirror.py`

**What:** The main prototype class inheriting from PrototypeBase. Wires the FSM, sensing, brain, and output layers together. Initial implementation with working camera mirror display and FSM transitions, but TTS/clone calls stubbed.

- [ ] **Step 1: Write smoke test**
- [ ] **Step 2: Implement prototype shell**

Structure:
```python
class AudioMirror(PrototypeBase):
    def setup(self):
        self.fsm = AudioMirrorFSM(...)
        self.session_id = uuid.uuid4().hex[:8]
        # Init camera, mic, display

    def update(self):
        frame = self.manager.webcam.get_img()
        emotions = self.manager.emotion_detector.detect(frame)
        self._handle_fsm_events(frame, emotions)
        self._render_mirror(frame, emotions)

    def cleanup(self):
        self.manager.voice_client.cleanup_session(self.session_id)
```

- [ ] **Step 3-5: Test, verify, commit**

```bash
git commit -m "feat: add Audio Mirror prototype shell with FSM and camera mirror"
```

---

### Task 3: Voice Capture + Progressive Cloning

**Files:**
- Modify: `prototypes/audio-mirror.py`

**What:** Implement mic capture, Whisper transcription, prosody analysis, and progressive voice cloning. Each speech capture creates a new voice palette entry via Afterwords `/clone`.

- [ ] **Step 1: Write test** — verify clone_voice is called with correct emotion tag after speech capture
- [ ] **Step 2: Implement**

Flow per capture:
1. Record audio (triggered by FSM entering capture state)
2. Transcribe with faster-whisper → transcript + confidence
3. Analyze prosody → emotion tag
4. POST /clone to Afterwords with audio + transcript + emotion
5. Update FSM session with new voice entry
6. Determine voice quality from duration

- [ ] **Step 3-5: Test, verify, commit**

```bash
git commit -m "feat: add voice capture and progressive cloning to Audio Mirror"
```

---

### Task 4: LLM Brain — Prompting + Insight Generation

**Files:**
- Modify: `prototypes/audio-mirror.py`

**What:** Wire the LLM to generate responses and insights. Craft the oracle system prompt. The LLM receives structured observations (emotions, transcripts, prosody) and generates:
- Re-prompting questions (Phase 3)
- The oracle insight (Phase 4)
- Voice emotion selection guidance

- [ ] **Step 1: Write test** — verify LLM receives structured observation data
- [ ] **Step 2: Implement system prompt + observation formatting**

The system prompt defines:
- Oracle role (observe, synthesize, reveal — not chatbot)
- Artistic constraints (never cruel, always genuine)
- Emotion voice selection guidance
- Phase-aware behavior (prompting vs insight)

- [ ] **Step 3-5: Test, verify, commit**

```bash
git commit -m "feat: add LLM brain with oracle system prompt to Audio Mirror"
```

---

### Task 5: TTS Output — Emotional Voice Synthesis

**Files:**
- Modify: `prototypes/audio-mirror.py`

**What:** Synthesize speech via Afterwords using the progressive voice palette. Select the voice palette entry whose emotion matches the intent of what the entity is saying. Fall back to default voice when palette is empty or quality is too low.

- [ ] **Step 1: Write test** — verify synthesize is called with correct emotion parameter
- [ ] **Step 2: Implement**

Logic:
- If no voice palette entries with quality >= "rough": use default voice
- If emotion parameter from LLM: use matching palette entry
- Fall back to highest-quality entry if no emotion match
- Play audio via afplay (macOS) or SoundPlayer

- [ ] **Step 3-5: Test, verify, commit**

```bash
git commit -m "feat: add emotional voice synthesis output to Audio Mirror"
```

---

### Task 6: Gap-Filling — Visual + Audio During Processing

**Files:**
- Modify: `prototypes/audio-mirror.py`

**What:** The 20-35s latency between speech and response needs to be filled. Add:
- Visual transitions (mirror becomes dreamlike during processing)
- Ambient audio textures (subtle thinking sounds)
- Short acknowledgment phrases in default voice: "I hear you...", "Let me think about that..."

- [ ] **Step 1: Implement visual processing state** — camera feed gets a gaussian blur + color shift during thinking
- [ ] **Step 2: Add acknowledgment audio** — play a short phrase in default voice immediately after capture
- [ ] **Step 3: Test and commit**

```bash
git commit -m "feat: add gap-filling visuals and audio during Audio Mirror processing"
```

---

### Task 7: Privacy + Session Cleanup

**Files:**
- Modify: `prototypes/audio-mirror.py`

**What:** Implement the privacy policy from the spec:
- Auto-delete voice palette on departure (face lost for >10s)
- Call DELETE /session/{id} on Afterwords
- Delete local temp audio files
- Respect privacy.mode config (force ollama when local-only)

- [ ] **Step 1: Write test** — verify cleanup_session is called on departure
- [ ] **Step 2: Implement**
- [ ] **Step 3: Test and commit**

```bash
git commit -m "feat: add privacy-first session cleanup to Audio Mirror"
```

---

### Task 8: Integration Test — Full Interaction Flow

**Files:**
- Create: `tests/test_audio_mirror_integration.py`

**What:** End-to-end test (with mocked hardware) that walks through the full interaction: IDLE → face detected → speech captured → voice cloned → deepening → oracle insight → departure → cleanup. Verify the FSM, LLM, voice client, and session management all work together.

- [ ] **Step 1: Write integration test**
- [ ] **Step 2: Verify it passes**
- [ ] **Step 3: Commit**

```bash
git commit -m "test: add full interaction flow integration test for Audio Mirror"
```

---

## Notes

- The Audio Mirror depends on Afterwords server extensions (POST /clone, POST /synthesize, DELETE /session). If those aren't ready yet, Tasks 3-5 can be developed against mocked VoiceClient responses.
- Run validation gates (Task 0) before committing significant time to hardware integration.
- The FSM (Task 1) is pure logic and can be developed and tested immediately with no dependencies.
- Tasks 2-7 should be done sequentially — each builds on the previous.
