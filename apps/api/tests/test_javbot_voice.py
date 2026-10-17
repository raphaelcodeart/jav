"""Il microfono di JAVBOT (javbot/voice.py): la voce va al servizio Whisper
interno e torna come testo; gli errori diventano frasi, mai un 500."""

import uuid

import httpx
import pytest

from app.domains.javbot import voice


def _fake_stt(monkeypatch, handler):
    real = httpx.AsyncClient
    seen: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    monkeypatch.setattr(voice.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(recording), **kw))
    return seen


async def test_the_voice_comes_back_as_text(monkeypatch):
    seen = _fake_stt(monkeypatch, lambda r: httpx.Response(200, json={"text": "  Quando é o treino?  "}))
    text = await voice.transcribe(b"opus", content_type="audio/webm", lang="pt")
    assert text == "Quando é o treino?"
    body = seen[0].content
    assert seen[0].url.path == "/transcribe" and b'name="lang"' in body and b"pt" in body


@pytest.mark.parametrize(("status", "kind"), [(413, "too_long"), (422, "unreadable"), (503, "busy"), (500, "unavailable")])
async def test_each_stt_error_has_its_sentence(monkeypatch, status, kind):
    _fake_stt(monkeypatch, lambda r: httpx.Response(status))
    with pytest.raises(voice.VoiceError) as exc:
        await voice.transcribe(b"opus", content_type="audio/webm", lang="it")
    assert exc.value.kind == kind and voice.MESSAGES[kind]


async def test_stt_down_or_audio_too_big_never_reaches_whisper(monkeypatch):
    def down(request):
        raise httpx.ConnectError("no route")

    _fake_stt(monkeypatch, down)
    with pytest.raises(voice.VoiceError) as exc:
        await voice.transcribe(b"opus", content_type="audio/webm", lang="en")
    assert exc.value.kind == "unavailable"

    seen = _fake_stt(monkeypatch, lambda r: httpx.Response(200, json={"text": "x"}))
    with pytest.raises(voice.VoiceError) as exc:
        await voice.transcribe(b"x" * (voice.MAX_AUDIO_BYTES + 1), content_type="audio/webm", lang="en")
    assert exc.value.kind == "too_long" and not seen


async def test_the_routes_answer_with_the_text_or_a_clear_error(monkeypatch):
    from app.core.deps import CurrentUser, get_current_user
    from app.main import app

    async def fake(audio, *, content_type, lang):
        if audio == b"long":
            raise voice.VoiceError("too_long")
        return f"{lang}:{content_type}"

    monkeypatch.setattr(voice, "transcribe", fake)

    # I contatori dei limiti in memoria: il client Redis condiviso può essere
    # legato al ciclo asincrono di un test precedente.
    class FakeRedis:
        def __init__(self):
            self.counts: dict[str, int] = {}

        async def incr(self, key):
            self.counts[key] = self.counts.get(key, 0) + 1
            return self.counts[key]

        async def expire(self, key, seconds):
            return True

    from app.core import rate_limit
    from app.domains.javbot import router as javbot_router

    fake_redis = FakeRedis()
    monkeypatch.setattr(rate_limit, "_get_redis", lambda: fake_redis)
    monkeypatch.setattr(javbot_router, "_get_redis", lambda: fake_redis)
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=uuid.uuid4(), organization_id=uuid.uuid4(), roles=[])
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/api") as client:
            ok = await client.post("/javbot/transcribe", data={"lang": "it"},
                                   files={"audio": ("v.webm", b"opus", "audio/webm")})
            assert ok.status_code == 200 and ok.json() == {"text": "it:audio/webm"}
            long = await client.post("/public-site/bot/transcribe", data={"lang": "pt"},
                                     files={"audio": ("v.webm", b"long", "audio/webm")})
            assert long.status_code == 413 and "minuto" in long.json()["detail"]
    finally:
        app.dependency_overrides.clear()
