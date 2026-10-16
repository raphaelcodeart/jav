"""Il servizio di trascrizione di JAVBOT: riceve un breve audio dall'API
(mai dal browser: non è esposto fuori dalla rete dei container), lo
trascrive con Whisper e restituisce il testo. L'audio resta in memoria e
sparisce con la richiesta: niente file, niente log del contenuto.

Una trascrizione per volta (il server ha due CPU): le altre aspettano in
fila, e oltre `QUEUE_WAIT_SECONDS` rispondono 503 «riprova».
"""

import asyncio
import io
import os
import time

import av
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from faster_whisper import WhisperModel

MODEL_NAME = os.environ.get("WHISPER_MODEL", "small")
MODELS_DIR = os.environ.get("WHISPER_MODELS_DIR", "/models")
MAX_BYTES = 3 * 1024 * 1024
QUEUE_WAIT_SECONDS = 20
LANGS = {"pt", "it", "en"}
MAX_SECONDS = 90
RATE = 16000

app = FastAPI(title="jav-stt", docs_url=None, redoc_url=None, openapi_url=None)
model = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8", cpu_threads=2, download_root=MODELS_DIR)
lock = asyncio.Lock()


def _decode(audio: bytes) -> np.ndarray:
    """webm/opus (Chrome, Firefox), mp4/aac (Safari), wav: in 16 kHz mono.
    Non `faster_whisper.decode_audio`, che con PyAV recente si rompe."""
    resampler = av.AudioResampler(format="s16", layout="mono", rate=RATE)
    chunks: list[np.ndarray] = []
    samples = 0
    with av.open(io.BytesIO(audio), mode="r") as container:
        for frame in container.decode(audio=0):
            for out in resampler.resample(frame):
                chunk = out.to_ndarray().reshape(-1)
                chunks.append(chunk)
                samples += chunk.size
            if samples > MAX_SECONDS * RATE:
                raise ValueError("too_long")
        for out in resampler.resample(None):
            chunks.append(out.to_ndarray().reshape(-1))
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks).astype(np.float32) / 32768.0


def _transcribe(audio: bytes, lang: str | None) -> tuple[str, float]:
    samples = _decode(audio)
    if samples.size < RATE // 4:
        return "", samples.size / RATE
    segments, info = model.transcribe(
        samples, language=lang, beam_size=1, vad_filter=True,
        condition_on_previous_text=False,
    )
    text = " ".join(s.text.strip() for s in segments).strip()
    return text, info.duration


@app.get("/health")
def health() -> dict:
    return {"ok": True, "model": MODEL_NAME}


@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...), lang: str = Form("")) -> dict:
    data = await audio.read(MAX_BYTES + 1)
    if not data:
        raise HTTPException(400, "empty")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "too_long")
    language = lang if lang in LANGS else None
    try:
        await asyncio.wait_for(lock.acquire(), timeout=QUEUE_WAIT_SECONDS)
    except TimeoutError:
        raise HTTPException(503, "busy") from None
    try:
        started = time.monotonic()
        try:
            text, duration = await asyncio.to_thread(_transcribe, data, language)
        except ValueError as exc:
            if str(exc) == "too_long":
                raise HTTPException(413, "too_long") from None
            raise HTTPException(422, "unreadable") from None
        except Exception:  # audio illeggibile (formato, file rotto)
            raise HTTPException(422, "unreadable") from None
        return {"text": text, "duration": round(duration, 1), "seconds": round(time.monotonic() - started, 2)}
    finally:
        lock.release()
