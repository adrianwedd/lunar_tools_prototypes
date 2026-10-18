# Artistic Intent — Reconstruction & Rework Audit

**Scope:** all 29 prototypes in `prototypes/` (27 "legacy" + `audio_mirror.py` + `ai-mirror-of-truth.py`; `example_base_usage.py` excluded as a docs example).
**Method:** archaeology of three states — (a) original commit `2e4595d` (2025-08-02, "Generated with Claude Code"), (b) the last pre-rework state `c9871ba` (2026-03-26, gallery-site commit — the final tree before the July 2026 MLX-native rework), (c) design docs (`docs/superpowers/specs/*`, `docs/superpowers/plans/*`, `docs/qa/hermes_qa_2026-06-21.md`) — compared against the current implementations (`09b4d80`, HEAD).

**Tagging:** every claim is tagged `[code]` (read from a file at a cited commit/HEAD), `[doc]` (design doc/README), `[commit]` (commit message), or `[inference]` (my conclusion from evidence; no invented intentions).

---

## 0. The critical historical fact: intent vs. working code

Across three eras:

1. **2025-08-02 (`2e4595d`):** every tool class in `src/lunar_tools_art/tools.py` was a **literal no-op stub** — `class GPT4: def generate(self,*args,**kwargs): pass`, same for DALL-E/SDXL/Flux/Renderer/WebCam/MIDI/ZMQ `[code]` (verified `2e4595d:src/lunar_tools_art/tools.py`). There was never a working GPT-4, DALL-E, or renderer in this repo's own tools layer: the *experience* existed only as prompt texts, loop structure, and README claims `[code]`. The original README descriptions therefore describe *aspirations*, and the code embeds them as LLM/image-gen prompts `[code]`.
2. **2026-03 (`a04146f..c9871ba`):** real LLM backends, emotion, prosody, Afterwords voice client, base classes were added — but the hardware/image/stub tools remained no-ops (`c9871ba:src/lunar_tools_art/tools.py` is still all-`pass` stubs) `[code]`.
3. **2026-07 (MLX-native rework, `fb60d81`/PR #26, #27, #28):** `tools/` package with real implementations (pyglet, sounddevice, OpenCV, mlx-whisper, mflux, pyncput/mido), privacy gate, headless fakes, `DeprecatedAlias` wrappers `[code]`, `[commit]` (`fb60d81` merges the rework; `dadecc9`, `03e8eeb`, `226463c`).

**The 2026-07 rework's stated goal** was: "Replace the stub tools layer with real Apple-Silicon/MLX implementations so all 29 prototypes genuinely run locally" `[doc]` (plan head). **Status:** the smoke matrix claims 28 works / 1 degraded / 0 needs-rework, with `verified-on-hardware: no` for every prototype `[code]` (`PROTOTYPE_STATUS.md`), and the CLI-UX spec itself warns that smoke status "is construction-level evidence only and must never be presented as 'verified to run on hardware'" `[doc]`. My audit found the smoke bar is **construction-only for legacy prototypes** — `tests/test_prototype_smoke.py` instantiates the class and, only for `PrototypeBase` subclasses, runs 3 `update()` calls; it never calls the manual `run()` loops `[code]`. Nearly every legacy prototype is a manual-`run()` class, so the "works" status proves almost nothing about the visitor experience.

---

## Cross-cutting behaviours shared by many prototypes

### X1. Image generators now return `(path_str, metadata)` — most image prototypes render a path as if it were an image [code]
- Legacy contract (stub era): `dalle3.generate(prompt)` → `None` or (later, documented) a PIL image; every prototype unpacks `image, _ = ...generate(prompt)` and calls `self.renderer.render(image)` (e.g. `ai-dream-interpreter-prototype.py:24,52`; `speech_activated_art.py:62,65`; `temporal-art-gallery-prototype.py:34,63`) `[code]`.
- Current contract: `ImageGenerator.generate(prompt, size, seed) -> tuple[str, dict]` — a **PNG file path**, not pixels (`src/lunar_tools_art/tools/images.py:72-88,14`) `[code]`. `DeprecatedAlias` preserves the tuple-return "adapting" shape (`images.py:286-331`) `[code]`.
- `Renderer.render()` is typed `image: np.ndarray` and the pyglet backend does `image.shape` + `image[::-1].tobytes()` (`tools/display.py:39-64`) — a `str` path raises `AttributeError` there; the **null backend silently stores whatever it is given**, where my live test: `render("/tmp/x.png")` on `backend="null"` produced *no error*, and a real pyglet render of a path string raises `'str' object has no attribute 'tobytes'` `[code]` (runtime probe on this machine).
- **Consequence:** 18 `render()` call sites across ~16 prototypes (ai-dream-interpreter, ai-fashion-show, apocalypse, audio-reactive-fractal-forest, collaborative_art, cosmic-soundscape, dynamic-visuals, emotional-landscape, escape_room ×3, interactive-storytelling-canvas, neural-transfer(frame is np — ok), real-time-glitch (np — ok), sentiment-analysis, speech-activated-art, temporal-art-gallery, virtual-time-travel) pass either a PIL `Image` (legacy behavior assumption) or now a **path string**; on real hardware with the pyglet/opencv renderer these either crash or display a single static frame per generation cycle rather than a live experience `[code]` + `[inference]`. This is the single most consequential break.

### X2. `DeprecatedAlias` silently drops stylistic kwargs [code]
`image_size="square_small"|"square_hd"`, `num_inference_steps=4`, `quality`, `style`, `response_format` and any unknown kwargs are popped and discarded with a *debug*-level log (`images.py:301-331`) `[code]`. Loses per-prototype visual identity for: `chat-room-narrative-quilt.py:64` (square patches), `generative-poetry-mosaic.py:35`, `temporal-art-gallery-prototype.py:33-37` (Flux `square_hd`, 4-step schnell, seed-by-clock) `[code]`.

### X3. MIDI control-name API drift — three prototypes' run loops crash against the real tools layer [code]
Legacy stub accepted anything. Real `MidiInput.get(self, control: int, default=0.0)` `[code]` (verified at runtime: binding `"A0"`, `val_min=`/`val_max=` raises `TypeError`).
- `virtual_time_travel.py:59` `midi_input.get("A0", val_min=0, val_max=6)` → `TypeError` in the run loop.
- `evolving-cosmic-mural-prototype.py:65` `get(f"A{i}", val_min=0, val_max=1)` → same.
- `dynamic_visuals.py:88-95` `get("A0"…"C0", val_min=…)` → same.
- All three also set `midi_input.device_name = "akai_lpd8"` — an attribute the real `MidiInput.__init__()` doesn't take and never reads (silently ignored) `[code]` + runtime probe.
- Because the smoke matrix never enters `run()` for these classes, all three are recorded "works" while being unusable on hardware `[code]` + `[inference]`.

### X4. Keyboard API drift [code]
- `apocalypse_experience.py:39` calls `keyboard_input.get("s", button_mode="toggle")` — real/fake `KeyboardInput.get(self)` takes no args → `TypeError` at runtime (verified) `[code]`.
- `virtual-cloud-chamber.py:186` calls `keyboard_input.is_any_key_pressed()` — **no such method exists on either real or fake `KeyboardInput`** (`AttributeError`, verified; `tests/test_lunar_tools_art.py:395` even contains a stale note claiming it "now exists") `[code]`. The particle-creation trigger is dead on hardware; smoke passes because the class is manual-`run()` style.

### X5. TTS contract drift: `(text, voice)` vs `(text, filename)` [code]
Real `Text2Speech.generate(text: str, voice: str|None) -> str` writes a WAV and returns its **path** (`tools/tts.py:17-44`) `[code]`.
- `utils.py:19` `generate_and_play_speech` calls `text2speech_instance.generate(text, filename)` **positionally** → the filename is interpreted as a *voice name*; used by `ai-dream-interpreter-prototype.py:55` → narration is either synthesized into a random file with a bogus voice name or the request errors `[code]` + `[inference]`.
- `whispers.py:146` calls `text2speech.generate(description, filename=...)` — real adapter has **no `filename` kwarg** → `TypeError` inside a broad `except` → logged, **sound simply never plays** on hardware (the headless `FakeText2Speech.generate(text, voice=None, **kwargs)` quietly accepts and ignores `filename`, returning a temp path, so the fake path *appears to work*: exactly a fake-friendly no-op) `[code]` + runtime probes.
- `sentiment_analysis_display.py:108` calls `sound_player.play_sound(sound)` where `sound` is a **text description** ("A cheerful, uplifting melody.") — `play_sound` treats it as a file path (`tools/audio.py:150-151` → `sf.read(path)`), guaranteed failure; the artifact predates the rework but is unchanged `[code]`.

### X6. Missing assets, with no fallback [code]
None of these referenced files exist in the repo (verified `find`): `apocalypse_ambient.mp3` (`apocalypse_experience.py:10`), `section1_narration.mp3`/`section2_music.mp3` (`augmented_audio_tours.py:25-26`), `correct_answer.mp3`/`hint.mp3` (`escape_room.py:10-11`), `your_music_track.mp3` (`neural-transfer-music-visualizer.py:18`), `arial.ttf` (`chat-room-narrative-quilt.py:17`, `generative-poetry-mosaic.py:9` — these two have default-font fallback `[code]`). The demo registry knows this: those demos carry `assets(required)` requirements whose check will fail in `doctor` `[code]`.

### X7. Blocking audio/video calls inside interactive loops [code]
`SoundPlayer.play_sound(path)` is now `play_audio(path, blocking=True)` (`tools/audio.py:150-151`) `[code]`. 8 prototypes call `play_sound` inside frame loops (whispers, escape_room, augmented tours, cloud chamber, apocalypse, sentimental display, …) — **every sound blocks the visual loop until playback finishes**. `sound_player.play_audio(…, blocking=False)` must be used explicitly (`neural-transfer-music-visualizer.py:75` was fixed to do this in `f067826` `[commit]`, `[code]`).

### X8. Headless fakes hard-code successful content [code]
`FakeSpeech2Text.transcribe()` always returns `"hello world"` with confidence 1.0 (`tools/headless.py:121-138`) and `FakeImageGenerator` writes a 1×1 PNG (verified: `m.dalle3.generate("test dream scene")` → tuple with `backend: 'fake'` metadata, live probe) `[code]`. So smoke-green proves wiring, never content; the CLI spec acknowledges this explicitly (`"construction-level evidence only"`) `[doc]`.

### X9. Emotion classifier still a placeholder until a model file is fetched [code]
`manager` logs `Emotion model path does not exist: models/emotion-ferplus-8.onnx` on construction; `scripts/fetch_models.py`'s checksum is "a documented placeholder"; nothing was "**run on-machine**" (`PROTOTYPE_STATUS.md` Task 13 section, `e97e848`) `[code]`, `[commit]`. Camera-emotion prototypes (`ai-mirror-of-truth`, `audio_mirror`) run but with `has_classifier=False`, confidence 0.0.

---

## Per-prototype sections

### 1. акустic-fingerprint-painter.py — `AcousticFingerprintPainter`
**Original intent:** record a short voice sample on keypress `r`, extract MFCC/spectral-centroid features, ask GPT-4 for abstract brushstroke parameters, paint the stroke on a black canvas — "Paints unique abstract brushstrokes driven by each visitor's voice fingerprint" `[doc]` (README `2e4595d`) `[code]` (`_record_audio_sample`, `_get_stroke_parameters_from_gpt4`, `_draw_stroke`).
**Current reality:** identical loop preserved; LLM-JSON parsing hardened (fence-tolerant parser, numeric sanitising) in the sweep `f067826` `[commit]`, `[code]`. Renders `np.array(canvas)` — the one fully np-safe image flow `[code]`.
**Lost/broken:** none *if* a real LLM is configured; on real hardware the LLM request (sync) inside the keypress branch stalls the loop, and with no LLM configured the painting silently does nothing (`llm` optional, warning once) — acceptable degradation `[code]` + `[inference]` — **no** (cosmetic only).

### 2. ai-dream-interpreter-prototype.py — `AIDreamInterpreter`
**Original intent:** "Listens to visitor speech, interprets dream-like phrases, and visualizes them via Stable Diffusion pipelines" — speak a dream, get an image + spoken interpretation `[doc]` (README) `[code]` (`interpret_dream`, `generate_and_play_speech`).
**Current reality:** same flow; DALL·E→`DeprecatedAlias(image_gen)` returns a **path**, which is passed straight to `renderer.render(image)` (X1) `[code]`; narration goes through `utils.generate_and_play_speech` whose second positional passes `.output/…mp3` **as a voice name** (X5) `[code]`.
**Lost/broken:** the twin payoff channels — the dream image (crash/garbage on hardware renderer) and the spoken interpretation (voice-name confusion) — are plausibly non-functional on hardware despite "works" `[inference]` from X1+X5 `[commit]`-backed evidence `[code]` — **yes**.

### 3. ai-fashion-show-prototype.py — `AIFashionShow`
**Original intent:** "Generates runway visuals from AI prompts… for a dynamic visual experience"; endless themed runway (5 themes × 5 outfits) with display/break timers `[doc]` (README, code themes list).
**Current reality:** unchanged structure; `image = self.dalle3.generate(prompt)` → **path** → `renderer.render(outfit)` (X1) `[code]`; `run()` loops the show forever with `time.sleep(break_duration=60)` between shows `[code]`.
**Lost/broken:** every "outfit" is a PNG path the renderer can't draw (X1); also `set_size(1024,1792)` portrait is fine — but generation is fully synchronous, so the runway is effectively a slideshow with per-image stalls `[inference]` — **yes** (unusable visuals).

### 4. ai-mirror-of-truth.py — `AiMirrorOfTruth` (PrototypeBase)
**Original intent:** hackathon piece — "observes humans through their emotions", Raspberry-Pi5 + Hailo8L NPU "emotionally intelligent interactive art," "generative visual art that morphs with user emotions," synthesized voice responses `[commit]` (`07f687d`); rewritten 2026-03-26 onto shared infrastructure: real FER+ emotion detector, prosody analyzer, Afterworks/Aftwerds voice client, pluggable LLM, entity-personality generation `[code]` (`96d8cd7`, `c986e29`) `[doc]` (mirror-of-truth plan).
**Current reality:** genuine `PrototypeBase` subclass: `update()` grabs a webcam frame, runs `manager.emotion_detector.detect()`, maintains an emotion trajectory, SPACE-to-speak, generates an AI-entity personality from the emotion history, answers via LLM with an entity system prompt, and renders a procedural "swirling" artwork coloured by primary emotion `[code]` (`ai-mirror-of-truth.py:74-126, 208-275, 310-362`).
**Lost/broken:**
- The committed visual art is PIL spirals/orbs, not the "generative art pipeline" of the hackathon framing — same as before the rewrite, not a regression `[code]`.
- Voice synthesis still **blocks the main loop** via `subprocess afplay … timeout=30` (`_speak`) `[code]` — a 30 s stall per utterance at 30 fps loop cadence `[inference]`.
- Emotion classifier is a placeholder until FER+ ONNX is fetched (X9); falls back to Haar-cascade with confidence 0.0 `[code]`.
- The Pi5/Hailo8L edge-AI positioning is historical context only — replaced by MLX/Mac intent `[commit]` + `[doc]`; — **yes** (voice blocking + placeholder emotion).

### 5. apocalypse_experience.py — `ApocalypseExperience`
**Original intent:** "Encapsulates logic for an apocalypse experience" — pressing `s` toggles an eerie ambient loop and regenerates a desolate-landscape image `[doc]` (README) `[code]`.
**Current reality:** unchanged code; `keyboard_input.get("s", button_mode="toggle")` → **`TypeError` on the real and fake KeyboardInput** (X4, verified) `[code]`; `ambient_sound_file="apocalypse_ambient.mp3"` does not exist (X6); the `s` toggle is also incompatible with `get()`'s one-shot semantics (would repeat or never toggle) `[inference]`.
**Lost/broken:** both the keyboard trigger and the ambient audio — prototype cannot do anything on hardware; "works" in the matrix is construction-only `[code]` + `[inference]` — **yes** (X4, X6).

### 6. audio_mirror.py — `AudioMirror` (PrototypeBase; flagship)
**Original intent:** "an oracle that speaks in your voice" — capture voice samples tagged by emotional state, build a **progressive voice palette**, select the palette entry whose emotion matches the insight to deliver, uncanny first-capture moment, revelation-not-reflection doctrine `[doc]` (spec §2, §2.1, §2.2; plan `2026-03-25-audio-mirror-experiment.md`).
**Current reality:** faithful FSM implementation (IDLE→DETECTION→FIRST_CAPTURE→DEEPENING→ORACLE→DEPARTURE) with real emotion/prosody/Afterwords clone hooks, oracle system prompt taken nearly verbatim from the spec `ORACLE_SYSTEM_PROMPT` `[code]` (`audio_mirror.py:21-66`, `audio_mirror_fsm.py`) — the strongest intent-to-code fidelity in the repo.
**Lost/broken:**
- Emotional palette **matching** was reduced: `_best_clone_voice()` picks the **longest-duration** clip, not the emotion-matching one (`audio_mirror.py:422-437`) — the art-direction core of spec §2.1 is implemented only as metadata, not selection `[code]` + `[inference]`.
- Capture is **synchronous `time.sleep(5)` inside `update()`** (`_capture_and_process_speech`) — the mirror visual freezes 5 s per capture at 33 ms loop cadence `[code]` + `[inference]`.
- Voice quality gating from spec §2.1 (`<5s → don't clone`; confidence <0.6 → re-capture) is implemented partially (min_reference_duration); `confidence` is **hard-coded to 0.8** whenever a transcript is non-empty rather than read from Whisper (`audio_mirror.py:206-209`) `[code]` — spec-fidelity loss.
- Never verified on hardware (Afterwords server, clone quality gates unrun) `[commit]` (`e97e848`, `PROTOTYPE_STATUS.md`) — **yes** (palette selection downgraded, sync capture, unverified).

### 7. audio-reactive-fractal-forest.py — `AudioReactiveFractalForest`
**Original intent:** "ever-evolving fractal 'forest' whose shape and colors respond in real time to ambient audio"; short mic frames → STFT bands → fractal zoom/depth + GPT-4 palette suggestion `[doc]` (README) `[code]` (`_loop_callback`, `_render_fractal`).
**Current reality:** same loop via `utils.run_until_quit`; each frame records ~0.1 s, librosa-analyzes, GPT-4 asks for palette, renders Mandelbrot-ish image `[code]`.
**Lost/broken:**
- The **palette parser is brittle:** it string-matches phrases like "cool blues" in the LLM's reply — with any real small local LLM (settings default `llama3.1:8b`) the suggestion usually won't contain the magic phrases → palette stays default black-and-white `[code]` + `[inference]`.
- `Renderer.render(fractal_image)` gets a PIL `Image`, not np array (X1: pyglet raises on `.shape`) `[code]`; `librosa.load` + STFT + LLM **on every 0.1 s frame** makes real-time reactive behavior impossible on any hardware (seconds of latency per frame) `[code]` + `[inference]` — **yes**.

### 8. augmented_audio_tours.py — `AugmentedAudioTour`
**Original intent:** "audio tours with position detection" — a camera watches the visitor's position/section, LLM-vision reports which exhibit section they're near, and that section's narration audio plays `[doc]` (README) `[code]` (`detect_position`, `section_audio_map`).
**Current reality:** `detect_position()` explicitly degrades — with no vision-capable LLM it warns once and returns `"unknown"`; the run loop then never changes section and no audio ever plays (`augmented_audio_tours.py:31-…,80-95`) `[code]`. Status row honestly marks it "degraded" `[code]`.
**Lost/broken:** the entire interactive premise (position-aware narration) is non-functional — the "known limitation" of the tools layer (`generate_vision` optional protocol default-`NotImplementedError`) `[code]`, plus the narration mp3 assets don't exist (X6) — **yes** (the only prototype status-labelled degraded, and it's the whole experience).

### 9. chat-room-narrative-quilt.py — `ChatRoomNarrativeQuilt`
**Original intent:** "Hosts a live chat where each message spawns a visual 'patch' in a growing narrative quilt" — real chat-room via Flask + Socket.IO, LLM crafts a patch description, DALL·E paints it, message text is drawn on the patch, quilt grid grows `[doc]` (README) `[code]` (`_setup_flask_routes`, `_craft_patch_description`, `_generate_panel_graphic`).
**Current reality:** the Flask/Socket.IO import and run are **commented out**; `emit("quilt_update")` is commented out with a `print` placeholder "would emit to clients"; run falls back to `input()` chat from the console; quilt clears when full `[code]` (`chat-room-narrative-quilt.py:7-8,41-54,128-135`).
**Lost/broken:** multiplayer chat-room premise replaced with single-operator keyboard input; patch images are paths rendered as `np.array(self.quilt_image)` only for local patches — the DALL·E patch itself is composited via `panel_graphic.resize(patch_size)` on a **path string** → `AttributeError` when a patch is generated on hardware (X1) `[code]` + `[inference]`; `font_path="arial.ttf"` missing (has fallback) `[code]` — **yes** (multiplayer gone; image path into `Image.resize` when generation succeeds).

### 10. collaborative-canvas.py — `CollaborativeCanvas`
**Original intent:** "multiple visitors on different machines paint together on a shared digital canvas, with periodic AI style suggestions" via ZMQ drawing events `[doc]` (README) `[code]` (`_process_drawing_event`, `_get_ai_suggestion`).
**Current reality:** same design; ZMQ endpoint resolved via tools layer with `.ip`/`.port` attributes supported (rework Task 5) `[code]`; renders `np.array(self.canvas_image)` — np-safe `[code]`.
**Lost/broken:** `_handle_incoming_messages` loops `zmq_endpoint.get_messages()` in a raw thread while a real ZMQ pair socket is opened in the constructor — the loop never waits on the real receive contract (`receive(timeout_ms=)` is the real API) so incoming `get_messages()` returns a list of str, and the dict/event-type filter treats `message.get("type")` against a `str` → unknown-message warnings `[inference]` from `[code]` (`tools/net.py`, `collaborative-canvas.py:73-80`); AI suggestion is a *log line only* — never applied to the canvas (pre-existing honesty in the code comment) `[code]` — **partial** (needs 2-machine e2e test; unverified, likely event-shape mismatch).

### 11. collaborative_art.py — `CollaborativeArtServer`
**Original intent:** server half of a ZMQ pair: peer sends prompts, server generates an SDXL image, renders it locally, sends the image back to the peer `[code]` (`handle_client`, `generate_and_modify_image`, `send_img`).
**Current reality:** identical; `stable_diffusion.generate(prompt)` → path (X1). It renders the path **and** `send_img(image)` sends the path string over ZMQ to the peer, which in the real `tools/net.py` `receive_img()` contract expects actual frames — the peer receives a path string, not an image `[code]` (`collaborative_art.py:26-31`; verified path-from-generate in X1) + `[inference]`. Background-thread `renderer.render` raises RuntimeError by design now (main-thread enforcement, `226463c`) — `handle_client` runs in a thread → **every generated prompt crashes the client thread** `[code]` + `[inference]`.
**Lost/broken:** the collaboration pipeline is broken three ways (path≠image to peer, main-thread render enforcement vs threaded loop) — **yes** (worst cross-cutting case).

### 12. cosmic-soundscape.py — `CosmicSoundscape` (new in `f067826`)
**Original intent (README, `2e4595d`):** "Creates an evolving soundscape using **4-channel audio mixing, controlled via OSC** and randomized AI prompts" `[doc]`. The original file was a **10-line broken import stub** (verified above), so no experience existed at all `[code]`.
**Current reality:** a *different* artwork was implemented in the July sweep: speak a phrase → keyword→celestial-motif mapping → palette → **one generated image** rendered `[code]` (`cosmic-soundscape.py`, f067826 commit message: "`cosmic-soundscape: implement CosmicSoundscape (was an empty file)`") `[commit]`.
**Lost/broken:** the README- and name-promised **soundscape (audio!) aspect has never existed**; what was built is speech→image. Also `_generate_visual` handles the `result[0]` tuple correctly (it is the one image prototype that adapts) but then renders `image` = **path** into `renderer.render` (X1) `[code]` — **yes** (experience re-imagined, plus X1).

### 13. data-driven-cityscape.py — `DataDrivenCityscape`
**Original intent:** "generative skyline whose architecture morphs according to live data feeds (weather, markets, social media)" with GPT-4 turning the data blob into drawing commands `[doc]` (README) `[code]` (`_fetch_weather_data`, `_get_cityscape_commands_from_gpt4`, `_draw_cityscape`).
**Current reality:** original crashed at construction when `api_keys.openweathermap` was missing; the sweep added **synthetic deterministic weather** whenever headless/key-missing/cloud-privacy-disallowed `[code]` + `[commit]` (f067826) `[doc]`. Market/social data was **always random simulation** — labelled "Placeholder for actual market data API call" since day one `[code]` (`2e4595d` and HEAD).
**Lost/broken:** honest degradation, but the original *claim* of "live data feeds" was ⅓ live weather + ⅔ random; current default (privacy `local-only`, no key) is always synthetic `[code]` (settings.toml `privacy.mode = "local-only"`) — "living city" reduced to scripted weather unless configured — **partial** (labelled; intent narrowed by privacy design `91dc557` `[commit]`).

### 14. dynamic_visuals.py — `DynamicVisualizer`
**Original intent:** "dynamic visuals with actual visual generation" — MIDI sliders (brightness/contrast/hue) map to a coloured circle whose look morphs in real time `[doc]` (README) `[code]` (`create_visual`).
**Current reality:** MIDI call-signature crashes (X3) inside `run()` `[code]`; `midi_input.device_name` attribute silently ignored `[code]`; renders `Image` object — pyglet `.shape` crash on real display (X1); "visual generation" is procedural (same since day one, not an LLM image) `[code]`.
**Lost/broken:** interactivity — MIDI never reaches the visuals on hardware — **yes** (X3, X1).

### 15. emotional-landscape-generator-prototype.py — `EmotionalLandscapeGenerator`
**Original intent:** "Captures ambient sounds, analyzes sentiment via GPT, and renders abstract landscapes reflecting emotions" — 5-second mic window, single-word emotion, a mapped landscape prompt, SDXL-turbo render `[doc]` (README) `[code]` (inline `EmotionDetector` class).
**Current reality:** unchanged; `image, _ = self.sdxl_turbo.generate(prompt)` → **path** → `renderer.render(landscape)` (X1); `sleep(update_interval=10)` between captures so it's a slow slideshow `[code]`.
**Lost/broken:** the landscape can't be displayed on hardware (X1); emotion detection here is transcript-based (GPT single-word), unaffected by FER+ placeholder — **yes** (X1).

### 16. escape_room.py — `EscapeRoomGame`
**Original intent:** "voice-driven escape room" — speech commands transcribed, LLM maps to `solve_puzzle`/`get_hint` intent, DALL·E renders puzzle scenes, sound cues on success/hint `[code]` (`run`, puzzles list).
**Current reality:** intent parsing guarded (`gpt4 is None` → intent `"unknown"`) in the sweep `[commit]` (f067826); both sound files missing (X6) so success/hint cues are silent no-ops *if* reached; puzzle images are paths → renderer crash (X1); headless fake always hears "hello world" → intent "unknown" forever `[code]` + `[inference]`.
**Lost/broken:** the game loop is playable only via an LLM that answers exactly the three intents and with sound files shipped — currently neither holds; **yes** (X1, X6).

### 17. evolving-cosmic-mural-prototype.py — `EvolvingCosmicMural`
**Original intent:** "continuously morphing mural… driven by AI descriptions and MIDI controls" — 8 fader-thresholds append cosmic modifiers, new SDXL-LCM image every 10 s, 30-frame cross-fade blend for smooth morphing `[doc]` (README + code) `[code]` (`run` MIDI thresholds + blend loop).
**Current reality:** MIDI call-signature crash (X3) — the modifier mechanism never fires `[code]` + runtime probe; blending renders `np.array(blended_image)` — np-safe path works *if* `generate_cosmic_scene()` returns an **image object**, but the deprecated `sdxl_lcm.generate` returns a **path** → `Image.blend(self.current_image, new_image, alpha)` gets `Image vs str` → `TypeError` on second generation `[code]` + `[inference]`.
**Lost/broken:** MIDI interactivity and the mural continuity both die on hardware — **yes** (X3 + X1) — one of the most broken pieces despite "works".

### 18. generative-poetry-mosaic.py — `GenerativePoetryMosaic`
**Original intent:** "interactive, growing mosaic of AI-written couplets illustrated by DALL·E backgrounds" — type a keyword, get a two-line poem, a tile, canvas fills `[doc]` (README) `[code]` (`_generate_poem`, `_create_tile`, `_add_tile_to_canvas`).
**Current reality:** unchanged flow; `_generate_background_image` returns a **path**; `tile_img = background_image.resize(self.tile_size)` — `AttributeError 'str' has no 'resize'` when a background is generated on hardware (X1) `[code]`; `arrial.ttf` missing → default-font fallback (intended) `[code]`; console `input()` interaction retained `[code]`.
**Lost/broken:** entire visible payoff (tiles) crashes post-generation — **yes** (X1).

### 19. interactive_storytelling.py — `InteractiveStoryteller`
**Original intent:** "The core interactive storytelling application" — speech in, LLM narrative continuation, periodic history summarisation to bound the context window `[doc]` (README + code `_summarize_story_history`).
**Current reality:** `run()` is **literally `pass` — "Placeholder run method for testing purposes"** since the initial commit; only the summariser logic exists; no loop ever records speech, generates narrative, or speaks `[code]` (`interactive_storytelling.py:19-21`). Yet PROTOTYPE_STATUS lists it "works — Instantiates and runs cleanly" `[code]` — the archetype of the "instantiates cleanly" shell.
**Lost/broken:** the advertised core experience was never implemented and the status matrix labels it works — **yes** (worst "shell" case).

### 20. interactive-storytelling-canvas-prototype.py — `InteractiveStorytellingCanvas`
**Original intent:** "Integrates Canvas UI to display story text, images, and controls" — voice contributions grow a story; Glif API visualizes the story as an image each turn `[doc]` (README) `[code]` (`visualize_story`, `glif_id="clgh1vxtu0011mo081dplq3xs"`).
**Current reality:** sweep replaced the old `from utils import record_and_transcribe_speech` import (which referenced a nonexistent top-level utils) with `self.speech2text.transcribe(duration=10)`; `glif_api` was never part of the tools layer — now `getattr(manager,'glif_api',None)` → `None`; so `visualize_story()` **always** returns `None` and no image ever renders `[code]` (`interactive-storytelling-canvas-prototype.py:10-17, 40-54`) + `[commit]` (f067826).
**Lost/broken:** story visualization (the "canvas" in the name) is a permanent silent no-op — the piece is a text-only story in the terminal; status says "works (fixed)" `[code]` — **yes** (silent feature removal).

### 21. neural-transfer-music-visualizer.py — `NeuralTransferMusicVisualizer`
**Original intent:** "Synchronizes neural style-transfer effects to live music beats for a dynamic visual experience" — music track plays non-blocking, webcam frames get style-transferred per beat/pitch analysis `[doc]` (README + code; current code has fixed `style_prompt` and a temp-file round-trip to `sdxl_turbo(image_path=…)`).
**Current reality:** sweep changed `sound_player.play_audio(self.audio_track, blocking=False)` and added `stop_sound()` so the loop exits cleanly `[commit]` (f067826); the **per-beat style re-transfer** is a per-frame temp-file → full SDXL call → seconds per frame in reality `[inference]` from `[code]` (sync call in the loop). `audio_track="your_music_track.mp3"` is missing from the repo — the music channel no-ops (`play_audio` fails on a missing path on hardware → degrade warnings) (X6) `[code]`; camera frame path renders np frames — fine `[code]`.
**Lost/broken:** beat-synchronised illusion is computationally unrealisable as coded (no beat analysis at all — `style_prompt` fixed, no onsets detected); music asset missing — **yes** (asset + perf).

### 22. real-time-glitch-art-lab.py — `RealTimeGlitchArtLab`
**Original intent:** "Streams live camera frames through a glitch 'corruption' pipeline" — pixel-sort / channel-shift / scanline / data-mosh-simulated transforms at ~15 fps, GPT-4 proposes glitch type+intensity every interval `[doc]` (README + code) `[code]`.
**Current reality:** unchanged; frames are np arrays → renderer-safe `[code]`; GPT-4 JSON suggestion path retained with strict `json.loads` (local 8B models produce valid JSON often enough; on parse failure keeps last glitch) `[code]`.
**Lost/broken:** none fundamental; the loop is honest and cheap — **no** (best-preserved camera piece).

### 23. sentiment_analysis_display.py — `SentimentDisplay`
**Original intent:** "Listens to visitors and renders the room's sentiment as living imagery" — record → transcribe → GPT-4 single-word sentiment → themed prompt → DALL·E image + matching "mood sound" `[doc]` (README + code).
**Current reality:** unchanged; DALL·E→path→`renderer.render(image)` (X1); `generate_sentiment_sound` returns a **description string** and `play_sound(sound)` passes the string as a file path → guaranteed audio failure (X5) `[code]`; no fallback if `renderer.render(None)` when generation returns `None` — `render(None)` would crash the loop body outside the per-iteration try? (run loop has no try around render)`[code]` + `[inference]`.
**Lost/broken:** audio channel always broken; image channel hardware-broken — **yes** (X1, X5).

### 24. speech_activated_art.py — `SpeechArtGenerator`
**Original intent:** "Speak, and the wall paints what it heard" — 3 s mic window → GPT-4 crafts prompt → DALL·E → render `[doc]` (registry) `[code]`.
**Current reality:** unchanged; path into renderer (X1); synchronous chain (STT+LLM+image) per cycle means each "wall" update takes seconds-minutes `[inference]`.
**Lost/broken:** display on hardware (X1); otherwise intact — **yes** (X1).

### 25. temporal-art-gallery-prototype.py — `TemporalArtGallery`
**Original intent:** README-era framing: "Streams remote images and audio across locations, creating a synchronized, time-based art exhibition" `[doc]`; the actual code (from the start) is: prompt chosen by **hour of day**, Flux generation with `square_hd`, 4 steps, per-hour regeneration `[code]` (`get_current_artwork_index`, `generate_artwork`).
**Current reality:** hourly flow unchanged; `flux.generate(...)` via `DeprecatedAlias` — `num_inference_steps=4`, `image_size="square_hd"` are **silently dropped**, seed-by-`int(time.time())` kept (X2) `[code]`; result is a **path** passed to `renderer.render` (X1) `[code]`; re-render check only every `check_interval` (60 s default) with `sleep` — fine `[code]`.
**Lost/broken:** the "remote streaming across locations" promise was never implemented anywhere in history (README claim only) `[code]` + `[inference]`; current hardware behavior: gallery displays nothing (path render crash) and the Flux-styling signature is dropped by the alias — **yes** (X1, X2, plus doc drift).

### 26. time-shifted-echo-chamber.py — `TimeShiftedEchoChamber`
**Original intent:** "looping echo chamber that replays what visitors say after programmable delays, layered and pitch-shifted" — d/D adjust delay, p/P adjust pitch, circular buffer of clips, pydub processing `[doc]` (README) `[code]` (`_record_clip`, `_process_and_play_clip`).
**Current reality:** **the only prototype the current smoke matrix fails** — `import pydub` → `ModuleNotFoundError: audioop` (Python 3.13 removed `audioop`; env is 3.13) — verified by running the suite today `[code]` + live run. Even headless, the class can't import, so it isn't even a shell. On Python 3.10 the loop is also flawed: `_record_clip` records **no duration** (the legacy AudioRecorder was supposed to run until stop), playback of all buffered clips is scheduled serially with cumulative `time.sleep` — a "layered echo" that plays back sequentially with growing gaps `[inference]` from `[code]` (`run` playback loop).
**Lost/broken:** import-level breakage + fake-layered (actually sequential) echo design — **yes** (hard broken today).

### 27. virtual-cloud-chamber.py — `VirtualCloudChamber`
**Original intent:** "Simulates a 2D particle-track cloud chamber where events spawn drifting particles" — speech or any keypress spawns particles; every 30 s GPT-4 narrates the particle journeys via TTS; vapour background `[doc]` (README) `[code]` (`run`, `_narrate_particle_journeys`).
**Current reality:** narration path repaired in the sweep (correct `generate(text) -> path` contract, warn-once disable) `[commit]` (f067826); particle-creation trigger broken: `keyboard_input.is_any_key_pressed()` **doesn't exist** on real or fake tools → `AttributeError` inside the run loop (X4, verified) — and the speech branch is wrapped in try/except but `is_any_key_pressed` is not, so the loop dies on the very first iteration `[code]` + runtime probe; renders `np.array(current_canvas)` — np-safe `[code]`.
**Lost/broken:** visitor agency (spawn particles) is dead; status claims "works (fixed)" `[code]` — **yes** (X4).

### 28. virtual_time_travel.py — `TimeTravelExperience`
**Original intent:** "MIDI time machine: dial an era, see and hear it re-imagined" — MIDI `A0` fader selects among 6 historical eras; TTS narrates "Welcome to the X era"; DALL·E renders the era `[code]` (`run`).
**Current reality:** `midi_input.get("A0", val_min=…)` → `TypeError` in the loop (X3, verified); the sweep added None-guards for `text2speech`/generation and render-skip on `None` `[commit]` (f067826) `[code]`; narrated era images are paths → hardware render crash (X1) `[code]`; `device_name` attr ignored (X3) `[code]`.
**Lost/broken:** MIDI control (the point of the piece) is dead; narration+visuals both degrade — **yes** (X3, X1).

### 29. whispers.py — `Whispers`
**Original intent:** three surveillance zones on a black canvas; webcam frame-diff detects movement; on trigger, generate a "whisper" TTS line ("a soft, ethereal hum", …) and burst 50 drifting trail-particles from the zone `[code]` (`_detect_movement` zones, `_generate_sound`, `_create_burst_of_particles`). README listed it without a description ("(Add description if available)") `[doc]` — intent read from the code itself.
**Current reality:** identical logic; the sound trigger is broken by TTS signature drift: `text2speech.generate(description, filename=…)` — real adapter takes no `filename` kwarg → the broad except logs and **no sound ever plays on hardware**, while the headless fake accepts and "succeeds" (X5, verified both) `[code]` + probes; particles render `np.array(canvas_image)` — np-safe (the particles will appear!) `[code]` — the visual half works.
**Lost/broken:** the audible half is silently dead on hardware while fake tests pass — the definitive "fake-friendly no-op" case — **yes** (X5).

---

## 29-row summary

| # | prototype | original-intent one-liner | current-reality one-liner | lost/broken |
|---|---|---|---|---|
| 1 | acoustic-fingerprint-painter.py | Voice fingerprint → GPT-4 brushstrokes on a shared black canvas | Same loop, hardened parsing; renders np — works with real LLM | no |
| 2 | ai-dream-interpreter-prototype.py | Speak a dream → image + spoken interpretation | Path rendered instead of image; TTS filename misread as voice name | yes |
| 3 | ai-fashion-show-prototype.py | Endless AI runway of generated outfits across themes | Generates path strings; renderer can't display them | yes |
| 4 | ai-mirror-of-truth.py | Emotion-observing mirror entity with voice & morphing art | Real emotion/prosody/LLM wired; voice blocks loop; emotion model placeholder | yes |
| 5 | apocalypse_experience.py | `s` toggles doom ambience + desolate imagery | `kb.get("s",button_mode=)` TypeError; ambient mp3 asset missing | yes |
| 6 | audio_mirror.py | Oracle speaks insights in your progressively cloned voice | Faithful FSM; emotion-matched voice selection reduced to longest clip; sync 5 s capture | yes |
| 7 | audio-reactive-fractal-forest.py | Fractal forest reacting in real time to ambient audio | Seconds-per-frame analysis; PIL image to np renderer; palette parser brittle | yes |
| 8 | augmented_audio_tours.py | Camera-position-aware audio tour narrations | Vision detection honestly degraded to "unknown"; no narration ever plays | yes |
| 9 | chat-room-narrative-quilt.py | Live chat room weaving AI-illustrated narrative quilt | Flask/SocketIO commented out → console input(); patch compositing crash on real gen | yes |
| 10 | collaborative-canvas.py | Two-machine shared painting canvas with AI suggestions | Structure intact; message-shape mismatch likely; unverified e2e | partial |
| 11 | collaborative_art.py | ZMQ peer sends prompts; server paints & returns images | Path strings sent as "images"; threaded render violates main-thread rule | yes |
| 12 | cosmic-soundscape.py | (README) 4-channel OSC audio soundscape — never existed | Speech→single cosmic image (new July implementation) | yes |
| 13 | data-driven-cityscape.py | Skyline morphing on live weather/market/social feeds | Weather synthetic by default; market/social always simulated | partial |
| 14 | dynamic_visuals.py | MIDI sliders drive colour/contrast circle | MIDI call signature crashes the loop on hardware | yes |
| 15 | emotional-landscape-generator-prototype.py | Ambient sentiment → matching generated landscape | Path render crash; 10 s slideshow cadence | yes |
| 16 | escape_room.py | Voice-command escape room with AI intents & sound cues | Intent parsing guarded; mp3 cues missing; puzzle images are paths | yes |
| 17 | evolving-cosmic-mural-prototype.py | MIDI faders steer an endlessly cross-fading cosmic mural | MIDI crash + `Image.blend` vs path TypeError kills continuity | yes |
| 18 | generative-poetry-mosaic.py | Typed keywords grow AI-couplet mosaic with DALL·E tiles | `path.resize()` AttributeError loses all tiles | yes |
| 19 | interactive_storytelling.py | Core speech→AI-story experience with history summarisation | `run()` is `pass` — never implemented; status says "works" | yes |
| 20 | interactive-storytelling-canvas-prototype.py | Voice-grown story visualized via Glif canvas | glif_api permanently None → visualization silent no-op | yes |
| 21 | neural-transfer-music-visualizer.py | Beat-synced style-transfer to a music track | No beat detection at all; music asset missing; per-frame SDXL stall | yes |
| 22 | real-time-glitch-art-lab.py | Live webcam → AI-curated glitch corruption pipeline | Works as designed (np frames, robust JSON fallback) | no |
| 23 | sentiment_analysis_display.py | Room sentiment rendered as living imagery + mood sound | Path render + plays a *description string* as a file path | yes |
| 24 | speech_activated_art.py | Speak and the wall paints what it heard | Chain intact; path render crash on hardware | yes |
| 25 | temporal-art-gallery-prototype.py | Hour-regenerating Flux gallery (README promised remote streaming, never coded) | hourly regen kept; path render crash; alias drops 4-step/square_hd styling | yes |
| 26 | time-shifted-echo-chamber.py | Layered, pitch-shifted echo of room audio | **Cannot import on Python 3.13** (audioop removed); "layering" was sequential sleeps | yes |
| 27 | virtual-cloud-chamber.py | Speech/keypress spawns drifting particle tracks + AI narration | Narration fixed; `is_any_key_pressed()` AttributeError kills the loop | yes |
| 28 | virtual_time_travel.py | MIDI fader dials historical eras with narration & imagery | MIDI call TypeError; era visuals are paths; device_name ignored | yes |
| 29 | whispers.py | Movement zones trigger TTS whispers + particle bursts | Visuals intact; TTS `filename=` kwarg rejected → sound silently never plays | yes |

---

## The 5 worst regressions

1. **Path-vs-pixels render mismatch (X1) — ~16 prototypes.** The July rework's unified `ImageGenerator.generate()` returns `(path_str, metadata)`, but `DeprecatedAlias` deliberately keeps the legacy unpacking shape, so `image, _ = ...generate()` binds a *path* where the prototypes expect an image; `Renderer.render()` on the real pyglet/opencv backends then crashes (`'str' object has no attribute 'tobytes'`), while the headless null backend silently stores it — the failure is invisible to every "works" status. This nullifies the visual payload of the image-driven installations (fashion show, poetry mosaic, dream interpreter, mural continuity, era travel, gallery, and more) `[code]` + `[inference]`.
2. **Input-tool API drift kills all interactivity (X3/X4).** `MidiInput.get("A0", val_min=…, val_max=…)`, `KeyboardInput.get("s", button_mode="toggle")`, and `is_any_key_pressed()` do not exist on the real or fake tools — so `virtual_time_travel`, `dynamic_visuals`, `evolving-cosmic-mural`, `apocalypse_experience`, and `virtual-cloud-chamber` lose their entire input premise; smoke passes because legacy classes are never `run()` `[code]` + runtime verification.
3. **TTS contract drift silently silences sound (X5/X7).** Real `Text2Speech.generate(text, voice)` rejects the `(text, filename)` callsites (`whispers`, via `utils.generate_and_play_speech` for dream interpreter; filename misread as voice name); `play_sound` is now **blocking** by default inside frame loops; `sentiment_analysis_display` plays a text description as a file path. On hardware the aural half of these rooms either freezes the loop or never fires, with errors caught into logs `[code]` + probes.
4. **Prototype shells and silent feature removal labelled "works."** `interactive_storytelling.run()` is `pass` (advertising "the core interactive storytelling application"); `cosmic-soundscape` never had its promised 4-channel OSC soundscape and was re-imagined as speech→image; `interactive-storytelling-canvas` permanently lost Glif visualization (`glif_api` is None by design); `augmented_audio_tours` honestly degraded; `time-shifted-echo-chamber` no longer imports on Python 3.13. The status matrix ("28 works") cannot distinguish these from functioning pieces `[code]` + `[commit]` + live test run.
5. **Hardware verification still at zero, with placeholders doing the sensing.** Every row of `PROTOTYPE_STATUS.md` says `verified-on-hardware: no`; the FER+ emotion model file was never fetched (checksum placeholder; construction warns) `[commit]` (`e97e848`, Task 13 notes); all Afterwords clone-quality gates remain unrun — so the flagship Audio Mirror's emotional-palette selection is downgraded to "longest clip" and untested in its intended form `[code]`, `[doc]`.