# Hardware Reality Audit — lunar_tools_prototypes

**Repo:** `/Users/adrian/repos/lunar_tools_prototypes` @ `09b4d80` (clean tree, nothing committed).
**Audit date:** 2026-10-18. Auditor: Hermes subagent (adversarial audit of current code against its own claims).
**Machine:** see docs/STUDIO_CAPABILITY.md for benchmarking/environment probing.

**Method legend used below:**
- **measured** — executed on this machine during this audit, output observed.
- **code-read** — read the current source; claim follows directly from code paths.
- **inferred** — derived from code + observed environment facts but not directly executed.
- **unverified** — could not be checked this session.

**Classification vocabulary:** `hardware-verified` / `implementation-complete-but-unverified` / `partially-functional` / `stubbed` / `concept-only`.

---

## 0. TL;DR

| Claim under audit | Verdict |
|---|---|
| PROTOTYPE_STATUS.md: "28 works / 1 degraded of 29" | **Overstated.** `works` means "smoke test passes" — for 25 of 29 that is *constructor-only* (the smoke bar for legacy `run()` prototypes never calls `run()`), per code-read of `tests/test_prototype_smoke.py:8-9,84`. Honest matrix below downgrades most. Also there are actually **31** prototype modules (excluding `__init__.py`/`example_base_usage.py`): `seed_surfer.py` and `real_time_glitch_lab.py` exist but are **absent from PROTOTYPE_STATUS.md and the demo registry** — both were added later and the sweep never re-counted (measured: registry diff in §2). |
| CLAUDE.md: "baseline 244 passed" | **Not reproducible as stated** (measured, §1). On Python 3.13 (`env/` venv is 3.13): `2 failed, 242 passed in 124s` — pydub's `audioop` import (removed in Python 3.13) breaks `time-shifted-echo-chamber.py` collection. On Python 3.12 with full requirements: `1 failed, 265 passed in 122.5s` — `test_demo_registry.py::test_registry_covers_every_prototype_file` fails because `seed_surfer`/`real_time_glitch_lab` are missing from `demo_registry.DEMOS`. **The suite was not green at HEAD on either interpreter.** |
| Hardware-verified all "no" in PROTOTYPE_STATUS.md | **Correct and honest** (column says `no` for all; confirmed no hardware-verified claims exist). |
| `headless` suite exercises "the artistic loop" | **Overstated.** Only `PrototypeBase` subclasses (cosmic-soundscape, audio_mirror, ai-mirror-of-truth, example usage) get a bounded `setup()/3×update()/cleanup()`; the other ~25 legacy prototypes get `cls(manager)` and nothing else (code-read). |

`docs/STUDIO_CAPABILITY.md` (parallel agent) owns machine benchmarking; placeholders below where that content belongs.

---

## 1. Test-suite state (measured)

Environment note (measured): the repo's `env/` virtualenv exists but is **empty of deps** (bare 3.13 venv, no site-packages beyond virtualenv scaffolding); the Hermès-installed environments and `~/.hermes/hermes-agent/.venv` also lack pytest/numpy. A clean scratch venv built from `requirements.txt` (+`pip install -e .`) was used:

- **Python 3.13** (`lunar-env`, matches `pyproject requires-python>=3.10` and repo `env/pyvenv.cfg` 3.13):
  `LUNAR_HEADLESS=1 pytest -q` → **`2 failed, 242 passed, 4 warnings in 124.04s` (wall 124.8s)**, RC=1.
  Failures: `time-shifted-echo-chamber` smoke ×2 (prototype module imports `pydub`; pydub 0.25 imports stdlib `audioop`, **removed in Python 3.13**) — py3.13 interpreter mismatch, not a prototype logic bug, but it still falsifies "fully green on 3.13".
- **Python 3.12** (`lunar-env312`, full `requirements.txt` + `-e .`):
  `LUNAR_HEADLESS=1 pytest -q` → **`1 failed, 265 passed in 122.51s`**, RC=1.
  Failure: `tests/test_demo_registry.py:18` — registry `DEMOS` (29 modules) ≠ prototype stems (31): `real_time_glitch_lab` and `seed_surfer` missing from the registry. The CLI's "the registry is THE source of truth" docstring (demo_registry.py:1) therefore lists **2 prototypes that cannot be launched via the CLI**.
- The 244/242/265 count drift across docs (199 → 244 → measured 242/265) shows the "baseline" claim was never re-verified per environment; the CLAUDE.md numbers match no measured configuration.

**Verdict: claim "LUNAR_HEADLESS=1 pytest -q → 244 passed, 0 failed" is FALSE as written today.** Closest true statement: "242 passed + 2 collection failures on py3.13; 265 passed + 1 registry failure on py3.12."

### What the smoke matrix actually proves (code-read, `tests/test_prototype_smoke.py`)
- `SKIP` excludes `audio_mirror.py`, `ai-mirror-of-truth.py`, `example_base_usage.py` (they have dedicated tests).
- `XFAIL_REASONS = {}` (line 32) — no known-broken entries.
- For legacy `run()` prototypes: **construction only** (line 84 comment: "construction without error is the smoke bar"). **Zero artistic-loop iterations are executed for 25/29 matrix entries.**
- For `PrototypeBase` subclasses: `should_exit` counter patched to 3 → `update()` runs exactly 3 times against the **all-fake** headless tools layer (audio writes 0.1 s of silence, renderer appends to a list, STT/TTS return canned values). This validates plumbing, not art.

---

## 2. Prototype honest matrix (all 31 module files; `example_base_usage.py` excluded from the 29-prototype contract)

Per-prototype: what `run()`/`update()` actually does, evidence, and honest class.

### PrototypeBase style (loop actually executed headless, 3 iterations)

| # | Prototype | Honest class | Evidence & reality when executed with real hardware present |
|---|---|---|---|
| 1 | ai-mirror-of-truth.py | **partially-functional** | 363 lines, best-engineered prototype: real webcam → `EmotionDetector.detect` (emotion.py) → prosody → LLM entity personality → `_speak()` via `voice_client.synthesize` (ai-mirror-of-truth.py:280-310) → `afplay` subprocess, blocking `time.sleep(3)` for recording inside `update()` path (:145-150). **Blocking TTS+LLM+record inside the 30 ms frame loop** (loop_delay=0.033 :28). Headless path fully faked by dedicated tests. On this machine TODAY: webcam denied (measured §4), **Afterwords synthesize via POST → 404** (measured §3; server is GET-only) → `_speak` warns and silently skips → the installation's voice half is dead. Gap named: voice path + camera permission + per-frame blocking. |
| 2 | audio_mirror.py | **partially-functional** | 533 lines, FSM-based (dedicated FSM + integration tests, code-read). Same hard dependency triangle: mic (absent on this machine, measured: 0 input devices), camera (permission-denied), Afterwords (POST-broken). Emotion classifier model file `models/emotion-ferplus-8.onnx` **does not exist** (measured: no `models/` dir; scripts/fetch_models.py:27-33 checksum is a `'0'×64` placeholder and is documented "intentionally NOT been run") → EmotionDetector falls to placeholder labels with confidence 0.0 (code-read emotion.py:79-97). Gap named: mic + camera + TTS verb + FER+ asset. |
| 3 | cosmic-soundscape.py | **implementation-complete-but-unverified** | 124 lines, clean `setup/update/cleanup`; `update()` does STT listen → prompt build → `image_gen.generate` → render (cosmic-soundscape.py:46-70). All 3 iterations headless passed (measured). With real tools: synchronous STT (`transcribe(duration=4)`) + synchronous image-gen inside `update()` — seconds-long frame stalls by design (code-read). Image backend default `mflux` — **mflux ≥0.23 no longer exports `Flux1`/`Config`** (measured §5: `ImportError: cannot import name 'Config' from 'mflux'`) → real image path raises `InferenceError` on a fresh `requirements.txt` install. |
| 4 | example_base_usage.py | **implementation-complete-but-unverified** (docs example, excluded from the 29) | 169 lines, deliberately minimal. |

### Legacy constructor-only smoke style (never had `run()` executed by the suite)

| # | Prototype | Honest class | Evidence (file:line) & real-hardware reality |
|---|---|---|---|
| 5 | acoustic-fingerprint-painter.py | **partially-functional** | Constructor-only smoke (211 lines). `run()` (:183-207) needs keyboard 'r'; then record→librosa MFCC→gpt4→draw. No mic on this machine (measured §4) → `AudioRecorder` degrades to no-op paths (audio.py:34-45) → feature vector all-zeros fallback (:79-84 log-then-continue) → painting proceeds with meaningless input = **wallpaper degeneration**. LLM fine via real Ollama but `llama3.1:8b` is **not installed** in Ollama (measured: only `Qwen3.8-27B-OBLITERATED:Q8_0` present → 404). Gap: mic device, ollama model. |
| 6 | ai-dream-interpreter-prototype.py | **partially-functional** | `run()` (:32-66) blocks per cycle on 10 s `record_and_transcribe_speech` (STT backend mlx-whisper — **not installed in this env** (`import mlx_whisper` ModuleNotFoundError, measured) and repo `env/` has nothing at all). `interpret_dream` unpacks `image, _ = self.dalle3.generate(...)` (tuple-alias OK, code-read) but `dalle3.generate` returns `(path, meta)` — **renderer.render() receives a str path, not a PIL image** (see Issue A, interface #1) → `_render_pyglet` does `image.shape` → AttributeError on a str → caught by outer `except` → next-loop wallpaper. Gap: STT env, image contract, whisper model. |
| 7 | ai-fashion-show-prototype.py | **implementation-complete-but-unverified** | 88 lines; `run_fashion_show` → dalle3→render→sleep(10) loop. Same dead image-into-render contract violation (Issue A) as #6 in real mode; also synchronous 1024×1792 mflux gen = multi-sec stall per outfit (by design, it's a slideshow — tolerable). Unverified on hardware (`no` column). |
| 8 | apocalypse_experience.py | **partially-functional** | 51 lines. `run()` toggles 's' → `play_sound('apocalypse_ambient.mp3')` — **asset file does not exist anywhere in repo** (measured: no assets dir; default kwarg `apocalypse_ambient.mp3`) → `SoundPlayer.play_audio` `sf.read('apocalypse_ambient.mp3')` fails with FileNotFoundError → uncaught in play path? play_sound has no try → crashes loop on first toggle (code-read audio.py:127-147: only PortAudioError/OSError from sd.play handled — sf.read raises outside that). Output-only audio fine (speakers present). |
| 9 | audio-reactive-fractal-forest.py | **implementation-complete-but-unverified** | 147 lines; uses `run_until_quit` (utils.py) + MIDI; smoke constructor-only. FakeMidi hides that real `MidiInput.get()` would raise `TypeError` on the same calls used by siblings (Issue D, but this file's calls were not verified in detail — unverified). |
| 10 | augmented_audio_tours.py | **stubbed** (vision feature) — matches "degraded" honestly | `detect_position` :32-60: no LLM-vision at all — every current backend raises `NotImplementedError` in `generate_vision` (llm_backends.py:33-35) → caught → returns "unknown" forever with a once-warning; the tour never identifies sections. Audio map also references files not in repo (inferred from same asset pattern — unverified specific paths). Status doc itself admits this. |
| 11 | chat-room-narrative-quilt.py | **stubbed** (network half) | `_setup_flask_routes` :41-56 — socketio handler body is **commented-out emission** ("Disabled - requires Flask-SocketIO"); run() :139-156 falls back to `input()` prompt in a loop; the installed art-piece (web chat quilt) never works as designed. LLM+DALL-E patch generation exists and would work locally once image contract fixed. |
| 12 | collaborative-canvas.py | **partially-functional** | Sets `self.zmq_endpoint.is_server = True` (:25) but `ZMQPairEndpoint` (net.py:15-53) has **no `is_server` attribute/logic** — bind/connect decided by ctor `bind=True` default; attribute assignment is a silent no-op → both ends bind on default addr (:5871) → connection fails → endpoint degrades (net.py:38-41 log-then-continue) → drawing sync dead while canvas still renders. Issue E. |
| 13 | collaborative_art.py | **partially-functional** | Same `ip/port` reassignment pattern (collaborative_art.py:24-26) — `ZMQPairEndpoint.address` reassignment is not re-parsed into a socket (socket already bound at ctor time to default address) → peers on the "configured" port never connect. `sdxl_turbo.generate` → render(image-path) Issue A. |
| 14 | data-driven-cityscape.py | **implementation-complete-but-unverified** | 317 lines. Weather fetch is properly triple-gated (headless / no key / privacy) with honest synthetic fallback and key-redaction (:39-70 — good practice, not an overstate). LLM→cityscape→render loop with 1 fps-ish pacing. Main risk: network call is synchronous in loop but 15 s timeout, once per cycle — acceptable. Unverified on hardware. |
| 15 | dynamic_visuals.py | **stubbed-at-runtime** (MIDI contract break) | `midi_input.get("A0", val_min=0.5, val_max=1.5)` (:89-95) — real `MidiInput.get(control:int, default:float)` (input.py:136) → **TypeError every frame** (measured directly: `TypeError: MidiInput.get() got an unexpected keyword argument 'val_min'`). `FakeMidiInput.get(*args, **kwargs) -> 0.0` (headless.py:110-118) swallows the kwargs → **smoke passes, real run crashes instantly**. Also passes a *string* key where an int CC number is required. |
| 16 | emotional-landscape-generator-prototype.py | **implementation-complete-but-unverified** | sdxl_turbo + gpt4 + STT + `manager.emotion_detector` (EmotionDetector present: manager wiring :146-149; classifier missing → placeholder emotions, honest degradation). Image contract Issue A. |
| 17 | escape_room.py | **partially-functional** | `play_sound("correct_answer.mp3")`/`"hint.mp3"` (:10-11, :110, :134) — **both mp3 assets missing from repo** (measured: no assets anywhere) → crash on first solve/hint. Blocking STT(5 s)+LLM in loop (by design, turn-based — tolerable). |
| 18 | evolving-cosmic-mural-prototype.py | **stubbed-at-runtime** (MIDI contract break) | `midi_input.get(f"A{i}", val_min=0, val_max=1)` (:65) with string keys → TypeError each frame on real MIDI path (same class as #15, measured). Blending/render logic fine (code-read :52-99). |
| 19 | generative-poetry-mosaic.py | **implementation-complete-but-unverified** | input()-driven CLI flow (:85-115); LLM + dalle3 + PIL tile compose all implemented. No blocking-in-frame concern (turn-based). Image contract Issue A. |
| 20 | interactive_storytelling.py | **stubbed** | **`run()` is literally `pass`** (interactive_storytelling.py:19-20 "Placeholder run method for testing purposes") — the smoke test's `storyteller.run()` is a no-op; summarizer helper exists but nothing drives it. PROTOTYPE_STATUS.md calls this "works: instantiates and runs cleanly" — technically true and vacuous. This is the clearest smoke-overstate exhibit. |
| 21 | interactive-storytelling-canvas-prototype.py | **implementation-complete-but-unverified** | STT(10 s)→gpt4 story→dalle3 visualize→render, turn-based. Contract Issue A. |
| 22 | neural-transfer-music-visualizer.py | **partially-functional** | "Neural transfer" is actually text-to-image with an `image_path:` kwarg passed to `sdxl_turbo.generate` (:55-57) — `DeprecatedAlias.generate` **silently drops unknown kwarg `image_path`** (images.py:319-329 debug-log-drop) → img2img transfer is impossible; the piece generates unrelated style images per beat instead of stylizing the frame. Also blocking SDXL in the per-frame visualizer loop with webcam feed (loop_delay small) → stutters to slideshow when a beat hits. "Beat detection" reads the whole mp3 via librosa each frame if implemented as described (code-read :104-115 → `_detect_beat(audio_data_path)` per frame — sync CPU work per frame). Audio track default `audio_track` path — asset presence unverified. |
| 23 | real-time-glitch-art-lab.py (legacy, hyphens) | **partially-functional** | `run()` calls `_get_glitch_suggestion_from_gpt4` **synchronously every 10 s inside the 15 fps loop** (:114-118) — 30 s timeout LLM stall in a per-frame loop (Issue C). Pixel-sort glitch is Pure-Python per-pixel loop (:33-41) — O(w·h) per frame ≈ tens of seconds at 1024 px; unusable at 15 fps. gpt4 configured model missing (measured). |
| 24 | real_time_glitch_lab.py (underscores, new) | **implementation-complete-but-unverified** | 182 lines, reworked: capture thread, `MainLoopQueue.drain`, camera-state standby frames, paced loops (code-read :100-176) — the only legacy-style piece architected for realtime. **Missing from demo registry + PROTOTYPE_STATUS.md** (measured §1 py3.12 failure). Smoke ran through it (constructor; loop only via `run()` — actually it has `run()` and smoke treats legacy as constructor-only → loop unexecuted by tests). |
| 25 | seed_surfer.py | **implementation-complete-but-unverified** | 217 lines + SeedScheduler (bounded latest-wins, prefetch, PNG cache — sound design, code-read :41-100). `image_gen.generate` returns `(path, meta)` and scheduler expects exactly that (bridge :75-78) — correct new-style contract. **Missing from demo registry + PROTOTYPE_STATUS.md**. Unverified on hardware; also requires mflux working (broken API §5). |
| 26 | sentiment_analysis_display.py | **partially-functional** | Loop: record(→blocking stop)→STT→dalle3→`renderer.render(image)` (path-vs-PIL Issue A)→`utils.generate_and_play_speech` → **`t2s.generate(text, filename)` passes the target filename as `voice`** (utils.py:22-35 → Text2Speech.generate(text, voice)) and then plays `filename` which TTS never wrote (real adapter writes its own temp .wav and returns its path, tts.py:33-45) → playback of a nonexistent .mp3. Double contract bug (Issue B). |
| 27 | speech_activated_art.py | **implementation-complete-but-unverified** | turn-based STT(→gpt4)→dalle3→render. Standard gaps (A, STT env, ollama model). |
| 28 | temporal-art-gallery-prototype.py | **implementation-complete-but-unverified** | flux alias + `num_inference_steps=4` kwarg silently dropped by DeprecatedAlias (images.py:319) — harmless (mflux hardcodes 4 steps, images.py:276). Hour-based slideshow, sleeps 60 s between generations. Fine if image path fixed. |
| 29 | time-shifted-echo-chamber.py | **partially-functional** | Blocks in-loop on `pydub.playback.play(audio_segment)` (:60 — blocking full-clip playback inside main loop, acceptable here since the piece *is* playback, but it can't be interrupted) + 2 s+ record per clip. Import breaks under Python 3.13 (`audioop`, measured). Headless smoke passes because FakePlayer writes silence and `pydub.play` isn't reached in constructor-only style... actually play() is reached? — constructor-only (code-read smoke:84) so never exercised. |
| 30 | virtual-cloud-chamber.py | **implementation-complete-but-unverified** | Particle sim + once-guarded narration chain (LLM→TTS→blocking play ( :152-153)). Good warn-once disable patterns (:150-160). STT imported but unused? (use list shows speech2text present — decorative; inferred). Same hardware gaps: mic, TTS POST bug. |
| 31 | virtual_time_travel.py | **stubbed-at-runtime** (MIDI contract break) | `midi_input.get("A0", val_min=0, val_max=len(eras)-1)` (:59-61) → TypeError per frame on real MIDI (measured pattern; this specific call inferred identical). TTS narration guarded properly if text2speech None. dalle3 Issue A. |
| 32 | whispers.py | **implementation-complete-but-unverified** | zone motion → particles → TTS bursts + blocking `play_sound` (:146, inline). Needs mic/camera/TTS-verb. |

(31 numbered rows = the 29-prototype contract set plus `seed_surfer.py` and `real_time_glitch_lab.py` #24/#25 which the status docs forgot.)

### Count summary (corrected, honest classes — authoritative)

Over the **29-prototype contract set** (i.e. all prototype modules except `example_base_usage.py`; note the status doc's "29" omits the two newer files `seed_surfer.py` and `real_time_glitch_lab.py`, which exist in the tree and are counted separately below):

| Class | Count | Members |
|---|---|---|
| hardware-verified | **0** | — (matches the doc's honest `no` column; not disputed) |
| implementation-complete-but-unverified | **11** | ai-fashion-show-prototype, audio-reactive-fractal-forest, cosmic-soundscape, data-driven-cityscape, emotional-landscape-generator-prototype, generative-poetry-mosaic, interactive-storytelling-canvas-prototype, speech_activated_art, temporal-art-gallery-prototype, virtual-cloud-chamber, whispers |
| partially-functional | **13** | acoustic-fingerprint-painter, ai-dream-interpreter-prototype, ai-mirror-of-truth, apocalypse_experience, audio_mirror, collaborative_art, collaborative-canvas, dynamic_visuals, escape_room, neural-transfer-music-visualizer, real-time-glitch-art-lab (legacy), sentiment_analysis_display, time-shifted-echo-chamber |
| stubbed (or stubbed-at-runtime) | **5** | augmented_audio_tours (vision path), chat-room-narrative-quilt (chat transport commented out), evolving-cosmic-mural-prototype (MIDI contract), interactive_storytelling (`run()` is `pass`), virtual_time_travel (MIDI contract) |
| concept-only | **0** | — |

Plus **2 undocumented newer prototypes** — `real_time_glitch_lab.py` and `seed_surfer.py` — both **implementation-complete-but-unverified** and absent from the demo registry and PROTOTYPE_STATUS.md.

---

## 3. Tools layer (`src/lunar_tools_art/tools/*.py`) — backend reality table

All ten modules import cleanly in a fully-installed env (measured: dry `import` of each OK). No `NotImplementedError` at tool level except LLM vision (llm_backends.py:33).

| Tool module | Real backend status | Reality check |
|---|---|---|
| **display.py** Renderer | **implemented** — pyglet window / OpenCV imshow / null backends; main-thread-only guard (display.py:41-43). | code-read; headless null exercised by tests. Real pyglet path unverified on hardware (window open never attempted this audit — see STUDIO_CAPABILITY). |
| **camera.py** WebCam | **implemented** (cv2.VideoCapture, RGB convert, degrade-on-fail :13-59). | measured: `cap.isOpened()` False with *"not authorized to capture video"* — macOS camera permission not granted to the test host. Camera is present but the API-authorized path is unproven. |
| **audio.py** AudioRecorder/SoundPlayer | **implemented** (sounddevice rec/play, degrade-guard, blocking play_sound alias :150-151). | measured: **0 input devices** (monitor + speakers only) → recorder degrades. Playback path plausible; play_sound asset playback unverified end-to-end. |
| **images.py** ImageGenerator | **implemented, but backend broken as shipped**: `fake` + `openai` + `replicate` paths written; `mflux` path calls `mflux.Config`/`Flux1.from_name` (images.py:262-283) — **mflux 0.23.0 (what `mflux>=0.6` resolves to) no longer has either symbol** (measured ImportError). `generate_async` exists for the fixes needed (images.py:90-106). | measured live: real `generate()` → `ImportError: cannot import name 'Config' from 'mflux'`. FLUX.1-schnell weights ARE on disk in `~/.cache/huggingface/hub` (measured) — the model asset exists; the adapter doesn't match current mflux API. |
| **`_legacy_cloud.py`** SDXL_TURBO/Dalle3/Flux/SDXL_LCM | **intentional no-op stubs** — `generate()` literally `pass` (code-read). DeprecatedAlias wrappers in manager are the real path (manager.py:114-118). | any code still importing these classes directly silently generates nothing (warning once). |
| **stt.py** Speech2Text | **implemented** (mlx-whisper default, faster-whisper alternative; :46-118) — raises InferenceError instead of faking when lib/model missing (honest). | measured: `mlx_whisper` ModuleNotFoundError in every env on this machine; `faster_whisper` needs `av` (absent in scratch env). faster-whisper GGML models for base.en **are cached** (measured in HF hub). STT currently cannot run anywhere on this machine → every voice-driven prototype is dead unless env extended. |
| **tts.py** Text2Speech | **implemented adapter, wire-broken**: `VoiceClient.synthesize` does `httpx.post("/synthesize", json=…)` (voice_client.py:55-74) but the running Afterwords server (measured 2026-10-18) serves **GET only** — POST returns 404; GET with the same JSON returns 200 with a valid 2.24 s WAV. | measured live: `POST → 404 {\"error\":\"clone not enabled (start with --allow-clone)\"}`; `GET → 200, 107564 bytes, 7.4 s`. So server-side model is loaded and speaking; the client just uses the wrong verb. TTS latency ≈ 7 s for one sentence → blocks interactive loops if called synchronously. |
| **input.py** Keyboard/Midi | Keyboard **implemented** (pynput or pyglet hooks :14-43). MidiInput **implemented but signature-incompatible with every current prototype call** (get(control:int) vs get(str, val_min=…) — Issue D, measured TypeError). | input device list unprobed this session (no MIDI device claimed present). |
| **net.py** ZMQPairEndpoint | **implemented** with honest degrade (warn-once, no-ops) but **no `is_server` support** and address reassignment dead (Issue E). | code-read; socket path unverified live (headless fakes it). |
| **headless.py** fakes | comprehensive; FakeMidiInput's kwargs-swallowing `get()` is the one fake that **masks a real signature break** (headless.py:110-118 vs measured TypeError). | code-read + measured. |
| llm_backends.py | 5 backends implemented (ollama local/cloud, claude, openrouter, mlx). `create_backend` wired. Vision = NotImplementedError for all (llm_backends.py:33). | measured: Ollama server up; configured model `llama3.1:8b` **not installed** → 404; the one installed model (`Qwen3.8-27B-OBLITERATED:Q8_0`) works through the same backend (measured: real completion in 9.6 s — note ~10 s for a one-line answer; interactive-loop latency concern). |

**Import-time failures:** none among tools modules (all dry-import OK). Broken-at-call-time: images(mflux), tts(POST), stt(missing libs), midi(signature).

---

## 4. Hardware assets present / missing on this machine (measured)

| Asset | State |
|---|---|
| Afterwords TTS server (:7860) | **up**, model loaded (`Qwen3-TTS-12Hz-0.6B-Base-8bit` MLX), 180+ voices. GET synthesize works (7.4 s, valid WAV). `/clone` returns "not enabled (--allow-clone)" (voice_client.py's clone_voice would fail silently → None). |
| Ollama (:11434) | up; ONLY `hf.co/OBLITERATUS/Qwen3.8-27B-OBLITERATED:Q8_0` installed. settings.toml's `llama3.1:8b` → 404. |
| Mic | **none** (0 input channels configured). |
| Camera | present but **not API-authorized** for the audit's process (TCC). |
| Speakers | present (Mac Studio Speakers default). |
| MIDI | none probed; mido absent in scratch env. |
| FER+ ONNX model | **missing** (`models/` dir does not exist; scripts/fetch_models.py ships `'0'×64` checksum placeholder, fetch will refuse by design :27-33,59-66). |
| FLUX.1-schnell weights | **cached on disk** (`~/.cache/huggingface/hub/models--black-forest-labs--FLUX.1-schnell`, diffusion model + text encoder + VAE safetensors present) — but `models--mlx-community` listing shows no mflux-format snapshot for it; adapter/API mismatch stands regardless. |
| Whisper models | faster-whisper `base.en`/`base`/`small.en`/`medium.en` cached in HF hub (measured). mlx-community whisper snapshot **not** cached → default `mlx-whisper` backend will attempt a network HF download on first use (inferred from cache listing + code path). |
| mlx/mlx-lm/mlx-whisper/mflux | installed only via requirements extras (`mlx` extra, pyproject.toml:41); in this audit's envs `mlx*` fails (dylib load) and `mflux` exists at 0.23.0 with different API. afterwords/.venv has `mlx` but not `mlx-whisper`/`mflux` (measured). |

Real-machine benchmark numbers (mflux gen, whisper latency, pyglet fps): **see docs/STUDIO_CAPABILITY.md**.

---

## 5. Found issues with file:line evidence

**A. Path-vs-PIL render contract (found hunt #1)** — `DeprecatedAlias.generate` returns `(path:str, meta)` (images.py:301-331; measured live: `('/var/…/lunar_tools_39…png', {...})`). But legacy call sites keep `image, _ = self.dalle3.generate(prompt)` and hand `image` straight to `renderer.render(...)` which does `image.shape` (display.py:62-67) / `ImageData(w,h,"RGB", image[::-1].tobytes())`. A str path → AttributeError (`'str' object has no attribute 'shape'`) caught by the prototype's broad except → silent wallpaper/skip. Affected call sites (code-read): ai-dream-interpreter-prototype.py:24, ai-fashion-show-prototype.py:36, apocalypse_experience.py:24, chat-room-narrative-quilt.py:64, collaborative_art.py:28, emotional-landscape-generator-prototype.py:59, escape_room.py:49,61, evolving-cosmic-mural-prototype.py:41, generative-poetry-mosaic.py:35, neural-transfer-music-visualizer.py:56, sentiment_analysis_display.py:58, speech_activated_art.py:62, temporal-art-gallery-prototype.py:34, virtual_time_travel.py:41. Headless smoke never catches this (never calls run()). Note fake backend `_generate_fake` also returns `(path, meta)` (images.py:131-140).

**B. utils.generate_and_play_speech double contract bug** — calls `text2speech_instance.generate(text, filename)` (utils.py:29): `filename` lands in the **voice** parameter of the real adapter (`generate(self, text, voice=None)` tts.py:26), then plays `filename` which was never written (real generate returns its own temp path; the .wav is not `.output/…mp3`). With the running Afterwords server this yields voice-name 404s / InferenceError. Used by ai-dream-interpreter and sentiment_analysis_display.

**C. Synchronous blocking calls in per-frame loops (found hunt #3)** — real-time-glitch-art-lab.py:118 (LLM every 10 s in a 15 fps loop, 30 s timeout); audio.py:151 `play_sound` default `blocking=True` used in per-frame loops (whispers.py:~146, virtual-cloud-chamber.py:153, apocalypse_experience via 's'); ai-mirror-of-truth.py:145-150 hard `time.sleep(3)` inside `update()`-call-path (frame loop pacing 33 ms); neural-transfer-music-visualizer.py:52-100 (sync SDXL + whole-file librosa load per beat inside visual loop); time-shifted-echo-chamber.py:60 `pydub.playback.play` (uninterruptible clip playback). The infra offers `generate_async` + `MainLoopQueue` (images.py:90-106, loop_utils.py:50) but only seed_surfer/real_time_glitch_lab use it.

**D. FakeMidi masks a signature crash (found hunt #6-adjacent)** — real `MidiInput.get(control:int, default:float)` (input.py:136) vs prototypes calling `get("A0", val_min=0, val_max=…)` (dynamic_visuals.py:89-95, evolving-cosmic-mural-prototype.py:65, virtual_time_travel.py:59-61; also evolving-mural "A{i}" strings) → measured `TypeError: MidiInput.get() got an unexpected keyword argument 'val_min'`. `FakeMidiInput.get(*args, **kwargs)->0.0` (headless.py:110-118) accepts everything → smoke green, real hardware crashes on frame 1. (This is a tools-fake-leaking-wrong-contract, same class as DeprecatedAlias leaking wrong kwargs.)

**E. ZMQ `is_server`/address reassignment no-ops** — net.py:15-53 binds/connects once in `__init__` from ctor args; `collaborative-canvas.py:25` (`self.zmq_endpoint.is_server = True`) and `collaborative_art.py:24-26` (mutating `.ip/.port`) modify plain attributes with zero effect → both peers default-bind `tcp://127.0.0.1:5871` → second bind fails → endpoint degrades silently (net.py:38-41) → multi-participant prototypes run without any actual peer link, no error visible beyond one warning.

**F. VoiceClient speaks POST, server speaks GET** — voice_client.py:63-74 `httpx.post(f"{self.server_url}/synthesize", json=…)` vs running server OpenAPI: `/synthesize` accepts GET (and a POST that 404s, measured). Every TTS call in every prototype returns None → InferenceError or silent skip. Tests mask it with mocks (test_voice_client.py:30-37 patches `httpx.post`; test_tools_tts.py injects a stub client). No test pins the wire protocol against a live server.

**G. Silent-fallback wallpaper patterns (found hunt #2)** — benign-but-degrading log-then-continue sites: WebCam degraded (camera.py:29-31,44-52), AudioRecorder/SoundPlayer degraded (audio.py:34-45,127-146), ZMQ degrade (net.py:38-41), LLM-None guards (escape_room.py:97-102, acoustic painter, emotional-landscape), narration auto-disable (virtual-cloud-chamber.py:150-160), augmented_audio_tours "unknown" (once-warn). Each hides a missing resource; the *installation keeps running* as visuals-only — by design in some cases (wallpaper risk) but never escalates visibility. The single most dangerous: FakeMidi (crash-masking, Issue D) and path/PIL (render-masking, Issue A) since they change behavior silently per frame.

**H. Status/test overstatements (found hunt #4)** — documented in §0/§1: constructor-only smoke bar for ~25/29; `interactive_storytelling.run()` is `pass` yet marked "works"; counts 199 (PROTOTYPE_STATUS.md:63) vs 244 (CLAUDE.md:65,213) vs measured 242/265; registry ≠ stems (test_demo_registry.py:18 fails at HEAD); status doc omits 2 newer prototypes entirely.

**I. Missing model assets (found hunt #5)** — `models/emotion-ferplus-8.onnx` absent (settings.toml:29 points here); `scripts/fetch_models.py` refuses to fetch until a human replaces the `'0'×64` checksum (fetch_models.py:27-33,58-66) — so the emotion pipeline is guaranteed placeholder for now. Asset files referenced by prototypes but absent from the repo: `apocalypse_ambient.mp3` (apocalypse_experience.py:8), `correct_answer.mp3` / `hint.mp3` (escape_room.py:10-11), and legacy `dalle3`/`utils` expect `.output/` dirs created ad hoc. `mlx-community/whisper-…-mlx` snapshot not in HF cache → first STT use triggers a download.

**J. DeprecatedAlias leaking/wrong kwargs (found hunt #6)** — drops unknown kwargs via `logger.debug` (images.py:319-329); demonstrable harm: `neural-transfer-music-visualizer.py:56` passes `image_path=…` for img2img — dropped at debug level, so "neural transfer" degrades silently to fresh txt2img. Also drops `num_inference_steps` (benign here: mflux hardcodes 4 at images.py:276 — coincidence, not correctness). `_LEGACY_IMAGE_SIZES` maps a subset; unknown `image_size` strings silently become 1024² (images.py:310-313 measured mapping only in fake test). No warning (only debug) is emitted for dropped kwargs — only the one-time deprecation warning fires.

**K. mflux API mismatch** — `requirements.txt:43 mflux>=0.6` resolves to 0.23.0 (measured); `_MfluxBackend` expects the ≤0.6-era API (`from mflux import Flux1, Config`, images.py:262,272) — ImportError per generate. Pin `mflux<0.x`-to-working-version or port to `FluxInitializer`/new API. FLUX weights on disk may or may not match the new layout (unverified: format migration not attempted this session).

**L. `Llama3.2-3B` / ollama model defaults missing** — settings.toml:5 `model = "llama3.1:8b"` not in the local Ollama; `mlx-community/Llama-3.2-3B-Instruct-4bit` not in HF cache (measured) → `[llm] provider=ollama` 404s → `generate()` returns None (log-then-continue, llm_backends.py:47-58) → every LLM-driven prototype silently loses its AI half.

---

## 6. Claim-provenance ladder

- **Measured this session:** both pytest runs (§1, timings: 124.8 s py3.13, 122.5 s py3.12 wall); registry mismatch; TypeError from MidiInput.get; mflux 0.23 ImportError; Afterwords GET 200 / POST 404 + 7.4 s latency + 2.24 s WAV duration; Ollama model list + one real completion through the backend; empty repo `env/`; no mic; camera TCC-denied; absent models/ dir and FER+ checksum placeholder; missing asset mp3s; HF cache contents.
- **Code-read:** every prototype/tool behavior statement above with file:line; smoke-matrix bar; DeprecatedAlias drop list; utils.py contract bug; ZMQ is_server no-op; `run()==pass`.
- **Inferred:** STT first-use network download; mlx-whisper absent machine-wide (import probed only in this env pair); `play(sound)` behavior with truly absent files (soundfile raise path read, not executed); per-frame CPU cost of pure-Python pixel sort (complexity math, no timing run — see STUDIO_CAPABILITY for measured fps work).
- **Unverified (defer to STUDIO_CAPABILITY / a hardware session):** actual mflux render quality/latency on this M5 Ultra; pyglet window fps; MIDI device presence; faster-whisper transcription latency with cached models; audio playback end-to-end; whether an approved camera permission flips WebCam to working.

---

## 7. Top blocking issues (ranked)

1. **MidiInput contract break crashes 3 prototypes on frame 1** with real MIDI path — dynamic_visuals.py:89-95, evolving-cosmic-mural-prototype.py:65, virtual_time_travel.py:59-61 (measured TypeError).
2. **VoiceClient POST vs server GET** — TTS is 0% functional against the live local server (voice_client.py:63-74; measured 404).
3. **Real-hardware image contract: path returned, renderer expects pixels** (images.py:301-331 + display.py:62-67; 14 call sites) — every LLM-image prototype renders nothing or crashes silently on real hardware.
4. **mflux adapter vs current mflux 0.23 API** — ImportError per generate (images.py:262,272; measured) → no real image generation at all, weights on disk notwithstanding.
5. **No STT runtime available anywhere on this machine** (mlx-whisper module absent, faster-whisper missing `av`; measured) — every voice-driven prototype is dead.
6. **Smoke matrix measures constructor + 3 fake iterations only** — the claimed "works" is plumbing-green, not art-green (test_prototype_smoke.py:8-9,84).
7. **demo_registry missing 2 prototypes** — `seed_surfer`, `real_time_glitch_lab` unlaunchable via the CLI's source-of-truth; suite red at HEAD (test_demo_registry.py:18).
8. **Suite not green at HEAD on either interpreter** (py3.13: audioop/pydub collection failure; py3.12: registry) — CLAUDE.md baseline claim false as written.
9. **Emotion classifier chain dead by design-default:** FER+ ONNX missing and fetch script refuses to fetch until checksum placeholder replaced by a human (fetch_models.py:27-33) — emotion features across ai-mirror/audio_mirror/emotional-landscape are placeholder labels at confidence 0.0.
10. **utils.generate_and_play_speech wrong parameter + wrong file** (utils.py:29-32) — breaks the two prototypes using it and masks the TTS verb bug behind a second error.

Honorable mentions: LLM model defaults not installed (404 → None → AI half silently gone); ZMQ `is_server` no-op kills both collaborative pieces; `_legacy_cloud.generate()→pass` stubs; pure-Python pixel-sort in RealTimeGlitchArtLab(legacy); camera TCC authorization needed.

---

## 8. Corrected counts + suite verdict (summary block for the parent)

- Counted set: 31 prototype module files; the 29-prototype contract set classifies as — **hardware-verified 0, implementation-complete-but-unverified 11, partially-functional 13, stubbed 5, concept-only 0**; plus 2 undocumented-but-implemented (`real_time_glitch_lab`, `seed_surfer`) both implementation-complete-but-unverified and absent from the registry/status docs.
- `LUNAR_HEADLESS=1 pytest -q` at HEAD: **NOT fully passing.** py3.13 (repo's `env` python): 2 failed / 242 passed / 124.0 s; py3.12 (full requirements): 1 failed / 265 passed / 122.5 s. The CLAUDE.md "244 passed, 0 failed" claim does not reproduce under any tested configuration; PROTOTYPE_STATUS.md's "199 passed" is stale.
---

## 9. Post-audit integration session — corrections and measurements

**Date:** 2026-10-18, 14:00–16:05 AEDT.
**Tree:** `f320b07` (archaeology + Glitch Lab/Seed Surfer registered) plus the
working changes committed with this section.
**Method:** every number below was measured on this machine. Commands were run
with `env -u PYTHONPATH` (see 9.1).

### 9.1 Corrections to this audit

| Audit claim | Correction (measured) |
|---|---|
| §5/§K: "FLUX.1-schnell weights ARE on disk" | **False.** Shards 1 and 3 of the transformer, the CLIP encoder and the VAE were present; transformer shard 2 (9.95 GB) and T5 shard 1 (4.99 GB) were missing. The cache looked populated because HF creates snapshot symlinks before the blobs arrive. `doctor` now checks every index-referenced shard before claiming `image-gen` ready. |
| §K: mflux 0.23 API mismatch blocks generation | **Fixed.** The adapter now imports `mflux.models.flux.variants.txt2img.flux.Flux1` and calls `generate_image(seed, prompt, num_inference_steps, height, width, guidance)`; dependency pinned to `mflux>=0.23,<0.24`. |
| §5: "mlx* fails (dylib load)" | In the current `env/` (Python 3.13) `mlx` 0.32.4 imports and runs. The failure this session was a **PYTHONPATH leak**: the agent shell exported a Python 3.14 `site-packages`, whose `numpy` shadowed the 3.13 env's (`No module named numpy._core._multiarray_umath`). All measured commands use `env -u PYTHONPATH`. |
| §2: seed_surfer / real_time_glitch_lab absent from registry | **Fixed at f320b07.** Both are launchable via `lunar_tools_demo.py list/run`. |
| §7 blockers 3/4/7 | Path-vs-pixels renderer contract fixed defensively; mflux adapter fixed; registry fixed. |

### 9.2 mflux — real local images

Model identity recorded in every cache entry and image metadata:
`black-forest-labs/FLUX.1-schnell` @ `741f7c3c…`, 4-bit quantisation, 4 inference
steps, guidance 4.0. The adapter was pointed at the local snapshot
(`HF_HUB_OFFLINE` is not usable because mflux resolves the repo through the Hub
API), so no weights were re-downloaded during measurement.

| Size | Cold (load + first render) | Warm mean (n=3) | Peak MLX memory |
|---|---|---|---|
| 512×512 | 2.73 s | **1.644 s** | 13.42 GB |
| 1024×1024 | — (same process, warm) | **5.887 s** | 21.84 GB |

Image at 1024²: 1.9–2.1 MB PNG; the 768 px copy is
`docs/evidence/mflux_schnell_1024.png`. The image is a coherent cosmic scene
(independently described by a vision pass), not noise.

### 9.3 Seed Surfer — real inference

`scripts/verify_seed_surfer.py --seeds 4` against the mflux backend:

- seeds 42–45: 2.756 s / 1.660 s / 1.701 s / 1.726 s, four distinct SHA-256s.
- cache hit for seed 42: **10 µs** lookup, no generation.
- identity guard: spoofing a different weights revision makes
  `cached_entry()` return `None` — a stale image cannot masquerade as the
  current model's output.
- favourites: record identity, revision, identity key, cache key, path and
  generation metadata.
- bounded scheduling: 8 rapid requests → **1 generation**, 7 cancelled,
  only the last seed delivered.
- keyboard: a `right` key step changed the seed 42→52 with 0.36 ms handler
  latency (logic path; no physical key event without a window).

Contact sheet: `docs/evidence/seed_surfer_seeds_42-45.png`.

### 9.4 Glitch Lab — pipeline verified, camera not

`scripts/verify_glitch_lab.py` over a 6 s 720p recorded clip (synthetic test
pattern, `outputs/glitch_lab/synthetic_reference_720p.mp4`):

- capture thread → transform → renderer delivered **30.1 fps** (121 frames in
  4.0 s), zero spurious duplicate drops after switching the loop to a
  condition-variable wait.
- all four families transform real frames (pixel_sort 77.3 % of pixels changed
  at intensity 0.8; channel shift 5.0 %; scanline 1.4 %; mosh 2.0 %).
- keyboard logic (1–4, up/down, space) changes family/intensity.
- camera loss/recovery: `tests/test_identity_and_video.py` drives a webcam that
  fails twice then recovers; state goes NO_CAMERA → CONNECTED and rendering
  resumes.
- **Camera hardware: denied.** `cv2.VideoCapture(0)` logs
  `OpenCV: not authorized to capture video (status 0), requesting...` and
  fails in 0.26–0.45 s. TCC approval needs the logged-in user to accept the
  prompt for the calling binary; it cannot be granted from this session.
- **Windowed rendering: unverified.** This agent shell has no WindowServer
  screens; pyglet raises `IndexError: list index out of range` in
  `display.get_default_screen()`. The 30.1 fps figure is the null-renderer
  pipeline rate, not pyglet presentation fps.

Montage: `docs/evidence/glitch_families_montage.png`.

### 9.5 Test suite (Python 3.13, `env/`)

`LUNAR_HEADLESS=1 env -u PYTHONPATH ./env/bin/python -m pytest -q`:
**2 failed, 273 passed** in 105.9 s. Both failures are the pre-existing
`time-shifted-echo-chamber` pair caused by `pydub 0.25` importing
`audioop`/`pyaudioop`, removed in Python 3.13 — unrelated to this work and
reported separately.

### 9.6 Remaining blockers

1. **Camera TCC permission** — human action required; cannot be automated.
2. **Windowed rendering** — must be launched from a GUI login session.
3. **Weight provisioning** — `scripts/fetch_models.py` does not cover FLUX;
   a fresh cache needs ~34 GB downloaded before the first render, and HF can
   leave half-populated snapshots that look complete.
4. **pydub/audioop on Python 3.13** — two baseline test failures.
