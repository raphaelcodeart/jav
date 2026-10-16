"""Le API di JAVBOT.

- `/javbot/...`            l'assistente dell'area privata: qualsiasi utente
  con una sessione. Che cosa vede lo decidono gli strumenti (tools.py) con
  i permessi e il club di chi chiede, esattamente come le rotte del club;
- `/public-site/bot`       l'assistente del sito: senza login, senza stato,
  solo dati pubblici (public.py).

Limiti di frequenza: l'area privata conta **per utente** (le richieste
passano tutte dal proxy BFF, quindi per indirizzo IP sarebbero un solo
contatore per tutti); il sito conta per IP, che la rotta della dashboard
inoltra in `X-Forwarded-For`.
"""

import uuid

import redis.asyncio as redis
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db, utcnow
from app.core.deps import CurrentUser, get_current_user
from app.core.rate_limit import _get_redis, rate_limit
from app.domains.club.scope import CLUB_HEADER
from app.domains.javbot import public as public_bot
from app.domains.javbot import service, voice
from app.domains.javbot.schemas import (
    BotMessageRead,
    ConversationRead,
    ExchangeRead,
    LangWrite,
    MessageWrite,
    PublicBotRead,
    PublicBotWrite,
)
from app.domains.javbot.texts import lang_of
from app.domains.javbot.tools import ToolContext

router = APIRouter(prefix="/javbot", tags=["javbot"])
public_router = APIRouter(prefix="/public-site", tags=["public-site"])

#: Messaggi al minuto per utente: una persona che scrive, non uno script.
USER_MAX_PER_MINUTE = 30
#: Messaggi a voce al minuto per utente: la trascrizione costa CPU.
VOICE_MAX_PER_MINUTE = 8


async def _count_per_minute(user_id: uuid.UUID, kind: str, limit: int) -> None:
    """Come core/rate_limit.py, ma per utente. Se Redis non risponde si
    lascia passare: l'assistente non deve spegnersi per un contatore."""
    key = f"ratelimit:{kind}:{user_id}:{utcnow().strftime('%Y%m%d%H%M')}"
    try:
        client = _get_redis()
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, 70)
    except redis.RedisError:
        return
    if count > limit:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Troppi messaggi in poco tempo: aspetta un minuto e riprova.")


async def _user_rate_limit(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    await _count_per_minute(current_user.user_id, "javbot", USER_MAX_PER_MINUTE)
    return current_user


async def _voice_rate_limit(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    await _count_per_minute(current_user.user_id, "javbot-voice", VOICE_MAX_PER_MINUTE)
    return current_user


async def _transcribed(audio: UploadFile, lang: str) -> dict:
    data = await audio.read(voice.MAX_AUDIO_BYTES + 1)
    try:
        text = await voice.transcribe(data, content_type=audio.content_type or "", lang=lang_of(lang))
    except voice.VoiceError as exc:
        code = {"too_long": 413, "unreadable": 422, "busy": 503, "unavailable": 503}[exc.kind]
        raise HTTPException(code, voice.MESSAGES[exc.kind]) from None
    return {"text": text}


@router.post("/transcribe")
async def transcribe_voice(
    audio: UploadFile = File(...),
    lang: str = Form(""),
    _user: CurrentUser = Depends(_voice_rate_limit),
) -> dict:
    """Il microfono della chat: la voce in testo (voice.py). Il testo torna
    nel campo, non parte da solo: chi parla lo rilegge e lo invia."""
    return await _transcribed(audio, lang)


async def _context(request: Request, db: AsyncSession, current_user: CurrentUser, lang: str | None) -> ToolContext:
    return await service.build_context(
        db, current_user=current_user, requested_club=request.headers.get(CLUB_HEADER), lang=lang,
    )


async def _exchange(db: AsyncSession, messages) -> ExchangeRead:
    return ExchangeRead(messages=[BotMessageRead(**m) for m in await service.message_dicts(db, messages)])


@router.get("/conversation", response_model=ConversationRead)
async def get_conversation(
    request: Request,
    lang: str | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationRead:
    """L'ultima conversazione (o una nuova, con il saluto) e le sue battute."""
    ctx = await _context(request, db, current_user, lang)
    conversation = await service.open_conversation(db, ctx=ctx)
    messages = await service.history(db, conversation=conversation)
    return ConversationRead(
        id=conversation.id, messages=[BotMessageRead(**m) for m in await service.message_dicts(db, messages)],
    )


@router.post("/conversation/reset", response_model=ConversationRead)
async def reset_conversation(
    request: Request,
    payload: LangWrite,
    current_user: CurrentUser = Depends(_user_rate_limit),
    db: AsyncSession = Depends(get_db),
) -> ConversationRead:
    """"Ricomincia": una conversazione nuova; la vecchia resta finché scade."""
    ctx = await _context(request, db, current_user, payload.lang)
    conversation = await service.open_conversation(db, ctx=ctx, fresh=True)
    messages = await service.history(db, conversation=conversation)
    return ConversationRead(
        id=conversation.id, messages=[BotMessageRead(**m) for m in await service.message_dicts(db, messages)],
    )


@router.post("/messages", response_model=ExchangeRead)
async def post_message(
    request: Request,
    payload: MessageWrite,
    current_user: CurrentUser = Depends(_user_rate_limit),
    db: AsyncSession = Depends(get_db),
) -> ExchangeRead:
    ctx = await _context(request, db, current_user, payload.lang)
    return await _exchange(db, await service.post_message(db, ctx=ctx, text=payload.text))


@router.post("/tasks/{task_id}/confirm", response_model=ExchangeRead)
async def confirm_task(
    task_id: uuid.UUID,
    request: Request,
    payload: LangWrite,
    current_user: CurrentUser = Depends(_user_rate_limit),
    db: AsyncSession = Depends(get_db),
) -> ExchangeRead:
    """Il "sì" esplicito: esegue il compito una volta sola (planner.execute_task)."""
    ctx = await _context(request, db, current_user, payload.lang)
    return await _exchange(db, await service.decide_task(db, ctx=ctx, task_id=task_id, accept=True))


@router.post("/tasks/{task_id}/cancel", response_model=ExchangeRead)
async def cancel_task(
    task_id: uuid.UUID,
    request: Request,
    payload: LangWrite,
    current_user: CurrentUser = Depends(_user_rate_limit),
    db: AsyncSession = Depends(get_db),
) -> ExchangeRead:
    ctx = await _context(request, db, current_user, payload.lang)
    return await _exchange(db, await service.decide_task(db, ctx=ctx, task_id=task_id, accept=False))


@public_router.post(
    "/bot", response_model=PublicBotRead,
    dependencies=[Depends(rate_limit("public-bot", max_requests=40, window_seconds=300))],
)
async def public_bot_answer(payload: PublicBotWrite, db: AsyncSession = Depends(get_db)) -> PublicBotRead:
    """L'assistente del sito: nessun login, nessuno stato, nessun dato
    personale (public.py)."""
    ctx = ToolContext(
        db=db, user_id=None, organization_id=None, scope=None, permissions=frozenset(),
        lang=lang_of(payload.lang), today=utcnow().date(),
    )
    reply = await public_bot.answer(ctx, payload.text, club_slug=(payload.club_slug or "").strip().lower() or None)
    return PublicBotRead(text=reply.text, actions=reply.actions, quick_replies=reply.quick_replies)


@public_router.post(
    "/bot/transcribe",
    dependencies=[Depends(rate_limit("public-bot-voice", max_requests=12, window_seconds=300))],
)
async def public_bot_transcribe(audio: UploadFile = File(...), lang: str = Form("")) -> dict:
    """Il microfono di JAVBOT sul sito: come /javbot/transcribe, per IP."""
    return await _transcribed(audio, lang)
