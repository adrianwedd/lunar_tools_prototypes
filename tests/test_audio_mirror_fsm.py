"""Tests for the Audio Mirror interaction state machine."""

from src.lunar_tools_art.audio_mirror_fsm import AudioMirrorFSM, FSMConfig


def test_starts_idle():
    fsm = AudioMirrorFSM()
    assert fsm.state == "IDLE"


def test_idle_to_detection():
    fsm = AudioMirrorFSM()
    fsm.on_face_detected()
    assert fsm.state == "DETECTION"


def test_detection_to_first_capture():
    fsm = AudioMirrorFSM()
    fsm.on_face_detected()
    fsm.on_speech_captured("Hello", 5.0, 0.9)
    assert fsm.state == "FIRST_CAPTURE"
    assert len(fsm.session.voice_entries) == 1


def test_detection_retries_then_idle():
    fsm = AudioMirrorFSM(FSMConfig(max_detection_retries=2))
    fsm.on_face_detected()
    fsm.on_speech_timeout()
    assert fsm.state == "DETECTION"  # retry 1
    fsm.on_speech_timeout()
    assert fsm.state == "IDLE"  # max retries


def test_detection_face_lost():
    fsm = AudioMirrorFSM()
    fsm.on_face_detected()
    fsm.on_face_lost()
    assert fsm.state == "IDLE"


def test_first_capture_to_deepening():
    fsm = AudioMirrorFSM()
    fsm.on_face_detected()
    fsm.on_speech_captured("Hello", 5.0, 0.9)
    fsm.on_capture_complete()
    assert fsm.state == "DEEPENING"


def test_first_capture_stt_failure():
    fsm = AudioMirrorFSM()
    fsm.on_face_detected()
    fsm.on_speech_captured("Hello", 5.0, 0.9)
    # Actually let's test STT failure from FIRST_CAPTURE -> DETECTION
    fsm2 = AudioMirrorFSM()
    fsm2.on_face_detected()
    fsm2.on_speech_captured("", 2.0, 0.1)  # bad capture
    fsm2.on_stt_failure()
    assert fsm2.state == "DETECTION"


def test_deepening_accumulates():
    fsm = AudioMirrorFSM(FSMConfig(min_deepening_exchanges=3))
    fsm.on_face_detected()
    fsm.on_speech_captured("hi", 5.0, 0.9)
    fsm.on_capture_complete()
    assert fsm.state == "DEEPENING"
    fsm.on_speech_captured("something deep", 10.0, 0.9, emotion="vulnerable")
    assert len(fsm.session.voice_entries) == 2
    assert fsm.state == "DEEPENING"


def test_deepening_to_oracle():
    fsm = AudioMirrorFSM(FSMConfig(min_deepening_exchanges=2))
    fsm.on_face_detected()
    fsm.on_speech_captured("hi", 5.0, 0.9)
    fsm.on_capture_complete()
    fsm.on_speech_captured("deep", 10.0, 0.9)
    fsm.on_speech_captured("deeper", 12.0, 0.9)
    assert fsm.oracle_criteria_met
    fsm.on_oracle_ready()
    assert fsm.state == "ORACLE"


def test_max_exchanges_forces_oracle():
    fsm = AudioMirrorFSM(
        FSMConfig(min_deepening_exchanges=2, max_deepening_exchanges=3)
    )
    fsm.on_face_detected()
    fsm.on_speech_captured("hi", 5.0, 0.9)
    fsm.on_capture_complete()
    for i in range(3):
        fsm.on_speech_captured(f"msg {i}", 5.0, 0.9)
    # After max exchanges, should auto-transition
    assert fsm.state == "ORACLE"


def test_face_lost_in_deepening():
    fsm = AudioMirrorFSM()
    fsm.on_face_detected()
    fsm.on_speech_captured("hi", 5.0, 0.9)
    fsm.on_capture_complete()
    fsm.on_face_lost()
    assert fsm.state == "DEPARTURE"


def test_silence_timeout_departure():
    fsm = AudioMirrorFSM()
    fsm.on_face_detected()
    fsm.on_speech_captured("hi", 5.0, 0.9)
    fsm.on_capture_complete()
    fsm.on_silence_timeout()
    assert fsm.state == "DEPARTURE"


def test_oracle_to_departure():
    fsm = AudioMirrorFSM(FSMConfig(min_deepening_exchanges=1))
    fsm.on_face_detected()
    fsm.on_speech_captured("hi", 10.0, 0.9)
    fsm.on_capture_complete()
    fsm.on_speech_captured("deep", 10.0, 0.9)
    fsm.on_oracle_ready()
    fsm.on_insight_delivered()
    assert fsm.state == "DEPARTURE"


def test_departure_to_idle():
    fsm = AudioMirrorFSM()
    fsm.on_face_detected()
    fsm.on_face_lost()
    fsm.on_cleanup_complete()
    assert fsm.state == "IDLE"


def test_voice_quality_from_duration():
    fsm = AudioMirrorFSM()
    assert fsm.best_voice_quality == "none"
    fsm.on_face_detected()
    fsm.on_speech_captured("hi", 3.0, 0.9)  # < 5s
    assert fsm.best_voice_quality == "rough"
    fsm.on_capture_complete()
    fsm.on_speech_captured("more", 12.0, 0.9)  # 12s
    assert fsm.best_voice_quality == "developing"


def test_reset():
    fsm = AudioMirrorFSM()
    fsm.on_face_detected()
    fsm.on_speech_captured("hi", 5.0, 0.9)
    fsm.reset()
    assert fsm.state == "IDLE"
    assert len(fsm.session.voice_entries) == 0
