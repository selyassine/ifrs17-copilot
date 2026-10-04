"""Question vocale : WER, termes, transcription factice, endpoint /v1/ask/audio."""

import pytest

from core.config import Settings
from multimodal.speech import audio_type, terms_found, transcribe, wer


def test_wer_ignore_accents_et_ponctuation():
    assert wer("Comment la CSM est-elle libérée ?", "comment la csm est elle liberee") == 0.0
    assert abs(wer("la CSM est libérée", "la C S M est libérée") - 3 / 4) < 1e-9
    assert wer("", "") == 0.0


def test_termes_et_formats():
    assert terms_found(["CSM", "B119"], "Que dit le paragraphe B119 sur la CSM") == ["CSM", "B119"]
    assert terms_found(["CSM"], "la c s m") == []
    assert audio_type("q.M4A") == "audio/mp4" and audio_type("q.txt") is None


def test_transcription_factice(tmp_path):
    s = Settings(llm_provider="fake", trace_path=tmp_path / "t.jsonl")
    tr = transcribe(b"audio", "q.wav", s, fake=lambda data, name: "Comment la CSM est-elle libérée ?")
    assert tr.text.startswith("Comment")


def test_endpoint_audio(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    import json

    from fastapi.testclient import TestClient

    import api.main as main
    from core.config import get_settings
    from core.llm import LLMClient

    settings = Settings(llm_provider="fake", router_mode="heuristic", api_token="secret",
                        trace_path=tmp_path / "t.jsonl", rag_mode="bm25", verifier_enabled=False)
    main.app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr(main, "speech_fake", lambda: (lambda data, name: "Donne-moi une recette de crêpes"))
    monkeypatch.setattr(main, "make_client", lambda s: LLMClient(s, fake_responder=lambda m, model: json.dumps({})))
    try:
        r = TestClient(main.app).post("/v1/ask/audio", headers={"X-API-Token": "secret"},
                                      files={"file": ("q.m4a", b"audio", "audio/mp4")})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["transcription"].startswith("Donne-moi") and body["answer"]["refused"]
        bad = TestClient(main.app).post("/v1/ask/audio", headers={"X-API-Token": "secret"},
                                        files={"file": ("q.txt", b"x", "text/plain")})
        assert bad.status_code == 415
    finally:
        main.app.dependency_overrides.clear()
