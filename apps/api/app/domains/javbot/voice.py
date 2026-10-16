"""Il microfono di JAVBOT: la voce diventa testo sul nostro server.

Il browser registra un breve audio e lo manda qui; lo giriamo al servizio
Whisper interno (apps/stt, mai raggiungibile da fuori) e restituiamo il
testo, che la persona rilegge nel campo prima di inviarlo. L'audio non si
salva da nessuna parte (né qui né in stt) e nei log non entra: è la promessa
della Política de Privacidade.
"""

import httpx

from app.core.config import get_settings

#: Un messaggio a voce, non una registrazione: circa un minuto in opus.
MAX_AUDIO_BYTES = 2 * 1024 * 1024
#: Sul server di due CPU un minuto di voce si trascrive in circa un minuto
#: e mezzo; oltre, meglio dire «riprova».
TIMEOUT_SECONDS = 120.0


class VoiceError(Exception):
    """`kind`: too_long, unreadable, busy, unavailable."""

    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind


MESSAGES = {
    "too_long": "Il messaggio a voce è troppo lungo: al massimo un minuto.",
    "unreadable": "Non sono riuscito a sentire l'audio: riprova.",
    "busy": "Sto già trascrivendo altri messaggi: riprova tra qualche secondo.",
    "unavailable": "Il microfono non è disponibile in questo momento: scrivi il messaggio.",
}


async def transcribe(audio: bytes, *, content_type: str, lang: str | None) -> str:
    url = get_settings().stt_url.rstrip("/")
    if not url:
        raise VoiceError("unavailable")
    if not audio:
        raise VoiceError("unreadable")
    if len(audio) > MAX_AUDIO_BYTES:
        raise VoiceError("too_long")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            res = await client.post(
                f"{url}/transcribe",
                files={"audio": ("voice", audio, content_type or "application/octet-stream")},
                data={"lang": lang or ""},
            )
    except httpx.HTTPError:
        raise VoiceError("unavailable") from None
    if res.status_code == 413:
        raise VoiceError("too_long")
    if res.status_code in (400, 422):
        raise VoiceError("unreadable")
    if res.status_code == 503:
        raise VoiceError("busy")
    if res.status_code != 200:
        raise VoiceError("unavailable")
    return str(res.json().get("text") or "").strip()
