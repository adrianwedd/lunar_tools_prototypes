# Mirror of Truth Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the AI Mirror of Truth hackathon prototype to use real MLX-based emotion detection, Afterwords TTS, and pluggable LLM backends — replacing all simulated/API-based components with local inference on Apple Silicon.

**Architecture:** The existing `prototypes/ai-mirror-of-truth.py` is rewritten to use the shared infrastructure (llm_backends, emotion, prosody, voice_client) built in the previous plan. The prototype inherits from `PrototypeBase` and follows `setup()` / `update()` / `cleanup()` lifecycle. Camera, mic, and rendering use the Manager's existing tools.

**Tech Stack:** Python 3.11+, OpenCV, librosa, Afterwords TTS server, pluggable LLM (Claude/Ollama/OllamaCloud/OpenRouter)

**Spec:** `docs/superpowers/specs/2026-03-25-audio-mirror-and-mlx-migration-design.md` (Section 4)

**Dependencies:** Shared infrastructure plan (complete). Afterwords server (must be running for TTS, but existing endpoints suffice — Mirror of Truth uses preset voices, not cloning).

---

### Task 1: Rewrite AiMirrorOfTruth with PrototypeBase

**Files:**
- Modify: `prototypes/ai-mirror-of-truth.py`
- Modify: `tests/test_lunar_tools_art.py` (update smoke test)

**What:** Rewrite the class to inherit from `PrototypeBase`, implement `setup()` / `update()` / `cleanup()`. Replace `random.choice()` emotion detection with the real `EmotionDetector`. Replace OpenAI TTS with Afterwords `VoiceClient`. Replace GPT-4-only LLM with `manager.llm_backend`.

- [ ] **Step 1: Write/update the smoke test**

```python
def test_mirror_of_truth_rewrite_smoke():
    """Mirror of Truth initializes and runs one update cycle without error."""
    from prototypes.ai_mirror_of_truth import AiMirrorOfTruth
    from unittest.mock import MagicMock, patch

    manager = MagicMock()
    manager.keyboard_input.is_key_pressed.return_value = True  # exit immediately
    manager.webcam.get_img.return_value = np.zeros((480, 640, 3), dtype=np.uint8)
    manager.llm_backend = MagicMock()
    manager.emotion_detector = MagicMock()
    manager.prosody_analyzer = MagicMock()
    manager.voice_client = MagicMock()

    mirror = AiMirrorOfTruth(manager)
    # Should not raise
    mirror.setup()
    mirror.update()
    mirror.cleanup()
```

- [ ] **Step 2: Run test to verify it fails** (current class doesn't have setup/update/cleanup)

- [ ] **Step 3: Rewrite the prototype**

Key changes:
- Inherit from `PrototypeBase` instead of standalone class
- `setup()`: initialize entity state, emotion buffer, conversation history
- `update()`: one iteration of the main loop — get frame, detect emotion, check for speech input, generate response, render
- `cleanup()`: stop audio, release resources
- Replace `self._analyze_facial_emotions()` (random.choice) with `self.manager.emotion_detector.detect(frame)`
- Replace `self.gpt4.generate()` with `self.manager.llm_backend.generate(prompt, system_prompt=...)`
- Replace `self.text2speech.generate()` + `self.sound_player.play_audio()` with `self.manager.voice_client.synthesize()` + `afplay`
- Keep the visual art generation (`_generate_visual_art`) — it's PIL-based and works fine
- Remove hardcoded OpenAI dependencies

- [ ] **Step 4: Run smoke test + full test suite**
- [ ] **Step 5: Commit**

```bash
git commit -m "feat: rewrite Mirror of Truth with real emotion detection, Afterwords TTS, pluggable LLM"
```

---

### Task 2: Add Prosody Analysis to Speech Input

**Files:**
- Modify: `prototypes/ai-mirror-of-truth.py`

**What:** When the viewer speaks, analyze prosody (pitch, energy, pace) alongside transcription. Feed both to the LLM for richer emotional understanding.

- [ ] **Step 1: Write test** — verify prosody data is included in LLM prompt
- [ ] **Step 2: Implement** — after `speech2text.transcribe()`, run `manager.prosody_analyzer.analyze()` on the audio, include prosody summary in the LLM prompt
- [ ] **Step 3: Test and commit**

```bash
git commit -m "feat: add prosody analysis to Mirror of Truth speech processing"
```

---

### Task 3: Improve Visual Generation

**Files:**
- Modify: `prototypes/ai-mirror-of-truth.py`

**What:** Enhance the PIL-based visual art to respond more dynamically to real emotion data. The current `_generate_visual_art` uses hardcoded emotion-to-color mapping with basic spirals. Improve with:
- Smooth transitions between emotional states (lerp between color palettes)
- More varied visual elements (particle systems, flowing lines, not just spirals + orbs)
- Intensity drives more visual parameters (blur, saturation, element count)

- [ ] **Step 1: Write test** — verify visual output changes shape based on emotion input
- [ ] **Step 2: Implement enhanced visuals**
- [ ] **Step 3: Test and commit**

```bash
git commit -m "feat: enhance Mirror of Truth visuals with emotion-responsive rendering"
```

---

### Task 4: Experience Branching via LLM System Prompt

**Files:**
- Modify: `prototypes/ai-mirror-of-truth.py`

**What:** Craft the system prompt that guides the entity's personality. The prompt receives the emotion trajectory and adapts its approach. This is the artistic core — the quality of the system prompt determines the quality of the experience.

- [ ] **Step 1: Write test** — verify system prompt includes emotion trajectory and viewer history
- [ ] **Step 2: Implement** — craft system prompt template, accumulate emotion trajectory over time, pass full context to LLM
- [ ] **Step 3: Test and commit**

```bash
git commit -m "feat: add adaptive system prompt with emotion trajectory for Mirror of Truth"
```

---

## Notes

- The Mirror of Truth uses **preset Afterwords voices** (e.g., galadriel, snape) — not viewer voice cloning. That's the Audio Mirror's feature.
- Image generation (DALL-E/SDXL) is kept as API calls for now. MLX Stable Diffusion is Phase 3 (16GB+ Mac).
- The `run()` method comes from `PrototypeBase` — the rewrite only needs to implement `setup()`, `update()`, `cleanup()`.
