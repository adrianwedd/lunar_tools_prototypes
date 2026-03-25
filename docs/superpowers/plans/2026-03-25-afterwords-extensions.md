# Afterwords Server Extensions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the Afterwords TTS server with runtime voice cloning, session-based voice palettes, and a POST synthesize endpoint — enabling the Audio Mirror prototype to clone a viewer's voice on-the-fly and synthesize speech in emotional variants.

**Architecture:** All changes are in `../afterwords/server.py`. The existing server has `GET /health` and `GET /synthesize`. We add: `POST /clone` (runtime voice creation), `POST /synthesize` (JSON body for sensitive text), `DELETE /session/{id}` (cleanup), runtime voice registry with palette support, and localhost-only binding when clone is enabled.

**Tech Stack:** FastAPI, MLX (Qwen3-TTS via mlx-audio), noisereduce, faster-whisper, soundfile

**Spec:** `docs/superpowers/specs/2026-03-25-audio-mirror-and-mlx-migration-design.md` (Section 3.4, 5.5)

**Repo:** All work in `../afterwords/` — this is a separate repository.

**Dependency:** Requires shared infrastructure plan to be complete (it is). The Audio Mirror prototype depends on these endpoints.

---

### Task 1: Runtime Voice Registry

**Files:**
- Modify: `../afterwords/server.py`
- Create: `../afterwords/tests/test_voice_registry.py`

**What:** The current `VOICES` dict is populated at startup and never modified. Add thread-safe runtime registration/unregistration functions that the new endpoints will use.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_voice_registry.py
import pytest
from unittest.mock import patch

# We'll test the registry functions directly
from server import _register_voice, _unregister_session, _resolve_voice, VOICES


def test_register_voice():
    _register_voice(
        name="viewer-abc-001",
        ref_audio="/tmp/test.wav",
        ref_text="Hello world",
        emotion_tag="neutral",
        metadata={"quality": "rough", "duration_s": 5.0, "confidence": 0.8},
    )
    assert "viewer-abc-001" in VOICES
    ref_audio, ref_text = VOICES["viewer-abc-001"][:2]
    assert ref_audio == "/tmp/test.wav"
    assert ref_text == "Hello world"
    # Cleanup
    del VOICES["viewer-abc-001"]


def test_unregister_session():
    # Register multiple entries for a session
    _register_voice("viewer-xyz-001", "/tmp/a.wav", "one", "neutral", {})
    _register_voice("viewer-xyz-002", "/tmp/b.wav", "two", "sad", {})
    _register_voice("other-voice", "/tmp/c.wav", "three", "neutral", {})

    _unregister_session("viewer-xyz")

    assert "viewer-xyz-001" not in VOICES
    assert "viewer-xyz-002" not in VOICES
    assert "other-voice" in VOICES
    # Cleanup
    del VOICES["other-voice"]


def test_register_does_not_overwrite():
    _register_voice("viewer-abc-001", "/tmp/a.wav", "first", "neutral", {})
    _register_voice("viewer-abc-002", "/tmp/b.wav", "second", "sad", {})
    assert "viewer-abc-001" in VOICES
    assert "viewer-abc-002" in VOICES
    # Cleanup
    del VOICES["viewer-abc-001"]
    del VOICES["viewer-abc-002"]


def test_resolve_voice_with_emotion():
    """When emotion is specified, find the best matching palette entry."""
    _register_voice("viewer-s1-001", "/tmp/a.wav", "hi", "neutral", {"duration_s": 5, "confidence": 0.8})
    _register_voice("viewer-s1-002", "/tmp/b.wav", "sad", "vulnerable", {"duration_s": 10, "confidence": 0.9})

    # Request vulnerable emotion — should get entry 002
    result = _resolve_voice("viewer-s1", emotion="vulnerable")
    assert result is not None
    assert result[0] == "/tmp/b.wav"

    # Cleanup
    del VOICES["viewer-s1-001"]
    del VOICES["viewer-s1-002"]
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd ../afterwords && pytest tests/test_voice_registry.py -v`

- [ ] **Step 3: Implement registry functions in server.py**

Add a `_voice_metadata` dict alongside `VOICES` to store emotion tags and quality info. Add `_register_voice()`, `_unregister_session()`, and update `_resolve_voice()` to accept an optional `emotion` parameter that selects the best matching palette entry.

Key design:
- `_voice_metadata[name] = {"emotion": tag, "duration_s": d, "confidence": c, "session_id": sid}`
- `_register_voice` acquires `_model_lock` for thread safety
- `_unregister_session` removes all entries whose name starts with the session_id prefix
- `_resolve_voice(voice, emotion=None)` — if emotion is given, search all palette entries for that session, find closest emotion match, prefer higher confidence/duration

- [ ] **Step 4: Run tests to verify pass**
- [ ] **Step 5: Commit**

```bash
git add server.py tests/test_voice_registry.py
git commit -m "feat: add runtime voice registry with session palette support"
```

---

### Task 2: POST /clone Endpoint

**Files:**
- Modify: `../afterwords/server.py`
- Create: `../afterwords/tests/test_clone_endpoint.py`

**What:** Accept raw audio via multipart POST, denoise it, optionally transcribe (if no transcript provided), save as voice profile, register in runtime VOICES map.

- [ ] **Step 1: Write failing tests**

Test the endpoint with mocked model (no GPU needed):
- POST audio + session_id + emotion + transcript → 200, returns voice name + quality
- POST without audio → 400
- POST with very short audio (<1s) → 400 (too short)
- POST with transcript provided → skips transcription, uses provided text
- POST without transcript → falls back to faster-whisper

- [ ] **Step 2: Run tests to verify failure**
- [ ] **Step 3: Implement POST /clone**

```python
@app.post("/clone")
async def clone_voice(
    audio: UploadFile = File(...),
    session_id: str = Form(...),
    emotion: str = Form("neutral"),
    transcript: str | None = Form(None),
):
    # Read audio bytes
    # Denoise with noisereduce (under _synth_lock — Metal not thread-safe)
    # If no transcript: transcribe with faster-whisper (under _synth_lock)
    # Calculate quality from duration
    # Atomic write: save to temp, validate, rename to voices/
    # Register in runtime VOICES
    # Return JSON with voice name, emotion, quality, confidence, duration, sequence
```

- [ ] **Step 4: Run tests to verify pass**
- [ ] **Step 5: Commit**

```bash
git commit -m "feat: add POST /clone endpoint for runtime voice creation"
```

---

### Task 3: POST /synthesize Endpoint

**Files:**
- Modify: `../afterwords/server.py`
- Modify: `../afterwords/tests/test_server.py`

**What:** Add a POST version of /synthesize that accepts JSON body instead of query params (for sensitive text). Supports optional `emotion` parameter for palette selection.

- [ ] **Step 1: Write failing tests**

- POST `{"text": "hello", "voice": "galadriel"}` → 200, WAV audio
- POST `{"text": "insight", "voice": "viewer-abc", "emotion": "vulnerable"}` → uses emotion-matched palette entry
- POST with empty text → 400
- POST with unknown voice → 400

- [ ] **Step 2: Run tests to verify failure**
- [ ] **Step 3: Implement POST /synthesize**

```python
@app.post("/synthesize")
def synthesize_post(body: SynthesizeRequest):
    # Same logic as GET /synthesize but reads from JSON body
    # If emotion specified: use _resolve_voice(voice, emotion=emotion)
    # Otherwise: use _resolve_voice(voice) as before
```

- [ ] **Step 4: Run tests to verify pass**
- [ ] **Step 5: Commit**

```bash
git commit -m "feat: add POST /synthesize with emotion-aware palette selection"
```

---

### Task 4: DELETE /session/{session_id} Endpoint

**Files:**
- Modify: `../afterwords/server.py`
- Modify: `../afterwords/tests/test_server.py`

**What:** Clean up all voice palette entries and files for a session.

- [ ] **Step 1: Write failing tests**

- DELETE /session/abc → 200, removes all viewer-abc-* entries from VOICES
- DELETE /session/nonexistent → 200 (idempotent, no error)
- Verify files are also deleted from voices/ directory

- [ ] **Step 2-5: Implement, test, commit**

```bash
git commit -m "feat: add DELETE /session endpoint for voice palette cleanup"
```

---

### Task 5: Localhost Binding + Security

**Files:**
- Modify: `../afterwords/server.py`

**What:** Default to `127.0.0.1` when clone endpoint is active (prevent network voice enrollment). Add `--allow-clone` flag that enables the clone/session endpoints and switches to localhost binding.

- [ ] **Step 1: Write test**
- Verify default host is `127.0.0.1` when `--allow-clone` is passed
- Verify clone endpoint returns 404 when `--allow-clone` is NOT passed

- [ ] **Step 2-5: Implement, test, commit**

```bash
git commit -m "feat: bind to 127.0.0.1 by default when clone endpoint is active"
```

---

## Notes

- All changes are in the `../afterwords/` repo, not this repo
- The existing test suite (`pytest` in afterwords) mocks the ML model — no GPU needed for testing
- The `_synth_lock` must be acquired for denoise and transcribe operations in `/clone` since they may use Metal
- Voice palette files go in `voices/` with naming convention `{session_id}-{sequence}-ref.wav`
- This plan should be executed in the afterwords repo working directory
