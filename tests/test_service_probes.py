from unittest import mock

from lunar_tools_art import service_probes as sp


def test_llm_probe_checks_ollama_endpoint_when_provider_ollama():
    cfg = {
        "llm.provider": "ollama",
        "llm.ollama.base_url": "http://localhost:11434",
        "llm.ollama.model": "llama3.1:8b",
    }
    with (
        mock.patch.object(sp, "_get_cfg", side_effect=lambda k, d=None: cfg.get(k, d)),
        mock.patch.object(sp, "_http_ok", return_value=(False, "refused")),
    ):
        r = sp.probe_llm()
    assert r.status == "fail" and "ollama" in r.fix.lower()


def test_llm_probe_checks_provider_specific_key_for_claude():
    with (
        mock.patch.object(
            sp,
            "_get_cfg",
            side_effect=lambda k, d=None: {"llm.provider": "claude"}.get(k, d),
        ),
        mock.patch.dict("os.environ", {}, clear=True),
    ):
        r = sp.probe_llm()
    assert r.status == "fail" and "ANTHROPIC_API_KEY" in r.fix


def test_afterwords_probe_reports_url_and_fix():
    cfg = {"afterwords.server_url": "http://localhost:7860"}
    with (
        mock.patch.object(sp, "_get_cfg", side_effect=lambda k, d=None: cfg.get(k, d)),
        mock.patch.object(sp, "_http_ok", return_value=(False, "refused")),
    ):
        r = sp.probe_afterwords()
    assert r.status == "fail" and "7860" in r.detail and "afterwords" in r.fix


def test_peer_probe_always_warns():
    r = sp.probe_peer()
    assert r.status == "warn" and "second process" in r.detail


def test_assets_probe_lists_missing_files(tmp_path):
    present = tmp_path / "here.mp3"
    present.write_bytes(b"x")
    probe = sp.make_assets_probe([str(present), str(tmp_path / "gone.mp3")])
    r = probe()
    assert r.status == "fail" and "gone.mp3" in r.detail
