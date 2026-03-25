# tests/test_voice_client.py
from unittest.mock import MagicMock, patch

from src.lunar_tools_art.voice_client import CloneResult, VoiceClient


def test_health_returns_dict():
    client = VoiceClient(server_url="http://localhost:7860")
    with patch("httpx.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"status": "ok", "ready": True, "voices": ["galadriel"]},
        )
        result = client.health()
        assert result["status"] == "ok"
        assert "galadriel" in result["voices"]


def test_list_voices():
    client = VoiceClient()
    with patch("httpx.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"status": "ok", "voices": ["galadriel", "snape"]},
        )
        voices = client.list_voices()
        assert voices == ["galadriel", "snape"]


def test_synthesize_returns_bytes():
    client = VoiceClient()
    with patch("httpx.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            content=b"RIFF\x00\x00\x00\x00WAVEfmt ",
            headers={"content-type": "audio/wav"},
        )
        result = client.synthesize("Hello world", voice="galadriel")
        assert isinstance(result, bytes)
        assert len(result) > 0


def test_synthesize_with_emotion():
    client = VoiceClient()
    with patch("httpx.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            content=b"RIFF\x00\x00\x00\x00WAVEfmt ",
            headers={"content-type": "audio/wav"},
        )
        result = client.synthesize(
            "I understand", voice="viewer-abc", emotion="vulnerable"
        )
        assert isinstance(result, bytes)
        call_json = mock_post.call_args[1]["json"]
        assert call_json["emotion"] == "vulnerable"


def test_clone_voice_returns_result():
    client = VoiceClient()
    with patch("httpx.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "voice": "viewer-abc-001",
                "emotion": "neutral",
                "quality": "rough",
                "transcript_confidence": 0.85,
                "duration_s": 5.2,
                "sequence": 1,
            },
        )
        result = client.clone_voice(
            audio=b"fake-audio-data",
            session_id="abc",
            emotion="neutral",
            transcript="Hello my name is Sarah",
        )
        assert isinstance(result, CloneResult)
        assert result.quality == "rough"
        assert result.voice_name == "viewer-abc-001"


def test_cleanup_session():
    client = VoiceClient()
    with patch("httpx.delete") as mock_delete:
        mock_delete.return_value = MagicMock(status_code=200)
        client.cleanup_session("abc")
        mock_delete.assert_called_once()


def test_health_returns_none_on_error():
    client = VoiceClient()
    with patch("httpx.get", side_effect=Exception("Connection refused")):
        result = client.health()
        assert result is None


def test_health_returns_none_on_non_200():
    client = VoiceClient()
    with patch("httpx.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=503)
        result = client.health()
        assert result is None


def test_synthesize_returns_none_on_non_200():
    client = VoiceClient()
    with patch("httpx.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=503, text="warming up")
        result = client.synthesize("hello", voice="galadriel")
        assert result is None


def test_synthesize_returns_none_on_connection_error():
    client = VoiceClient()
    with patch("httpx.post", side_effect=Exception("Connection refused")):
        result = client.synthesize("hello", voice="galadriel")
        assert result is None


def test_clone_voice_returns_none_on_error():
    client = VoiceClient()
    with patch("httpx.post", side_effect=Exception("Connection refused")):
        result = client.clone_voice(audio=b"data", session_id="abc", emotion="neutral")
        assert result is None
