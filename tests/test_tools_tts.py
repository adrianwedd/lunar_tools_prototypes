import pytest


class StubVC:
    def __init__(self, payload=b"RIFFfakewav"):
        self.payload = payload
        self.calls = []

    def synthesize(self, text, voice, emotion=None):
        self.calls.append((text, voice, emotion))
        return self.payload

    def health(self):
        return {"status": "down"}


def test_generate_writes_bytes_to_wav(tmp_path):
    from lunar_tools_art.tools.tts import Text2Speech

    vc = StubVC()
    t2s = Text2Speech(vc, output_dir=str(tmp_path))
    path = t2s.generate("hello")
    assert path.endswith(".wav")
    assert open(path, "rb").read() == b"RIFFfakewav"
    assert vc.calls[0][1] == "galadriel"  # default voice


def test_none_synthesis_raises(tmp_path):
    from lunar_tools_art.exceptions import InferenceError
    from lunar_tools_art.tools.tts import Text2Speech

    with pytest.raises(InferenceError):
        Text2Speech(StubVC(payload=None), output_dir=str(tmp_path)).generate("hello")
