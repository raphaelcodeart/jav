"""JAVBOT: conversazioni, messaggi e conferme.

Il router chiama solo queste funzioni; il "cervello" è planner.py (area
privata) e public.py (sito). Qui si decide chi è l'utente per gli strumenti
(`build_context`: il club da club/scope.py, i permessi da rbac), si salvano
le battute e si tiene pulito lo storico (conservazione in models.py).
"""

import uuid
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.core.deps import CurrentUser
from app.domains.club.lessons import club_now
from app.domains.club.scope import resolve_club
from app.domains.javbot import planner as planner_module
from app.domains.javbot.models import RETENTION_DAYS, JavbotConversation, JavbotMessage, JavbotTask
from app.domains.javbot.planner import Planner, Reply
from app.domains.javbot.texts import lang_of, say
from app.domains.javbot.tools import ToolContext
from app.domains.rbac.service import get_permission_codes_for_user

#: Quante battute rimanda la chat quando si riapre.
HISTORY_LIMIT = 40
MAX_TEXT = 1000


async def build_context(
    db: AsyncSession, *, current_user: CurrentUser, requested_club: str | None, lang: str | None,
) -> ToolContext:
    """L'utente come lo vedono gli strumenti. Il club lo decide
    club/scope.py (per lo staff della piattaforma, quello in cui è
    "entrato"); senza club gli strumenti del club rispondono "non vedo"."""
    from app.domains.club.scope import ClubScope

    try:
        club = await resolve_club(db, current_user=current_user, requested=requested_club)
        scope = ClubScope(organization_id=club.organization_id, club_id=club.id)
    except HTTPException:
        scope = None
    permissions = frozenset(
        await get_permission_codes_for_user(db, user_id=current_user.user_id, organization_id=current_user.organization_id)
    )
    today = (await club_now(db, club_id=scope.club_id)).date() if scope else utcnow().date()
    return ToolContext(
        db=db, user_id=current_user.user_id, organization_id=current_user.organization_id, scope=scope,
        permissions=permissions, lang=lang_of(lang), today=today,
    )


async def purge_old(db: AsyncSession, *, user_id: uuid.UUID) -> None:
    """Le conversazioni ferme da più di RETENTION_DAYS, con messaggi e
    compiti (ON DELETE CASCADE). Nessun job: si pulisce quando l'utente
    torna."""
    limit = utcnow() - timedelta(days=RETENTION_DAYS)
    old = select(JavbotConversation.id).where(JavbotConversation.user_id == user_id, JavbotConversation.updated_at < limit)
    await db.execute(delete(JavbotTask).where(JavbotTask.conversation_id.in_(old)))
    await db.execute(delete(JavbotMessage).where(JavbotMessage.conversation_id.in_(old)))
    await db.execute(delete(JavbotConversation).where(JavbotConversation.id.in_(old)))


async def _latest(db: AsyncSession, *, ctx: ToolContext) -> JavbotConversation | None:
    stmt = select(JavbotConversation).where(JavbotConversation.user_id == ctx.user_id)
    # Un superadmin che cambia club non deve ritrovarsi la conversazione
    # (e i compiti) dell'altro club.
    stmt = stmt.where(
        JavbotConversation.club_id == ctx.scope.club_id if ctx.scope else JavbotConversation.club_id.is_(None)
    )
    return (await db.execute(stmt.order_by(JavbotConversation.updated_at.desc()).limit(1))).scalars().first()


async def _start(db: AsyncSession, *, ctx: ToolContext) -> JavbotConversation:
    conversation = JavbotConversation(
        organization_id=ctx.organization_id, user_id=ctx.user_id,
        club_id=ctx.scope.club_id if ctx.scope else None, state={},
    )
    db.add(conversation)
    await db.flush()
    greeting = await Planner(ctx, conversation).greeting()
    _add_message(db, ctx=ctx, conversation_id=conversation.id, role="bot", reply=greeting)
    await db.commit()
    return conversation


async def open_conversation(db: AsyncSession, *, ctx: ToolContext, fresh: bool = False) -> JavbotConversation:
    """L'ultima conversazione dell'utente in questo club, o una nuova con il
    saluto. `fresh` ne apre comunque una nuova ("Ricomincia")."""
    await purge_old(db, user_id=ctx.user_id)
    conversation = None if fresh else await _latest(db, ctx=ctx)
    if conversation is None:
        return await _start(db, ctx=ctx)
    await db.commit()
    return conversation


def _add_message(
    db: AsyncSession, *, ctx: ToolContext, conversation_id: uuid.UUID, role: str, reply: Reply | None = None,
    text: str | None = None, intent: str | None = None,
) -> JavbotMessage:
    message = JavbotMessage(
        conversation_id=conversation_id, user_id=ctx.user_id, club_id=ctx.scope.club_id if ctx.scope else None,
        role=role, text=reply.text if reply else (text or ""), actions=reply.actions if reply else [],
        quick_replies=reply.quick_replies if reply else [], intent=intent,
    )
    db.add(message)
    return message


async def _save_exchange(
    db: AsyncSession, *, ctx: ToolContext, conversation_id: uuid.UUID, user_text: str, reply: Reply,
) -> list[JavbotMessage]:
    # Dopo un'esecuzione fallita la sessione ha fatto rollback: la
    # conversazione si rilegge invece di fidarsi dell'oggetto in memoria.
    conversation = await db.get(JavbotConversation, conversation_id, populate_existing=True)
    conversation.state = reply.state
    conversation.updated_at = utcnow()
    asked = _add_message(db, ctx=ctx, conversation_id=conversation_id, role="user", text=user_text, intent=reply.intent)
    await db.flush()
    answered = _add_message(db, ctx=ctx, conversation_id=conversation_id, role="bot", reply=reply)
    await db.commit()
    return [asked, answered]


async def post_message(db: AsyncSession, *, ctx: ToolContext, text: str) -> list[JavbotMessage]:
    text = (text or "").strip()[:MAX_TEXT]
    conversation = await open_conversation(db, ctx=ctx)
    conversation_id = conversation.id
    reply = await Planner(ctx, conversation).reply(text)
    return await _save_exchange(db, ctx=ctx, conversation_id=conversation_id, user_text=text, reply=reply)


async def decide_task(db: AsyncSession, *, ctx: ToolContext, task_id: uuid.UUID, accept: bool) -> list[JavbotMessage]:
    """Il bottone "Conferma" / "Annulla" di una proposta. La conferma non
    porta niente dal browser se non l'id: ciò che si esegue è nel compito."""
    task = await db.get(JavbotTask, task_id)
    if task is None or task.user_id != ctx.user_id:
        conversation = await open_conversation(db, ctx=ctx)
        reply = Reply(say(ctx.lang, "task.notFound"))
        return await _save_exchange(db, ctx=ctx, conversation_id=conversation.id,
                                    user_text=say(ctx.lang, "qr.yes" if accept else "qr.no"), reply=reply)
    conversation_id = task.conversation_id
    if accept:
        reply = await planner_module.execute_task(ctx, task_id)
    else:
        reply = await planner_module.cancel_task(ctx, task_id)
    return await _save_exchange(db, ctx=ctx, conversation_id=conversation_id,
                                user_text=say(ctx.lang, "qr.yes" if accept else "qr.no"), reply=reply)


async def history(db: AsyncSession, *, conversation: JavbotConversation) -> list[JavbotMessage]:
    rows = (
        await db.execute(
            select(JavbotMessage)
            .where(JavbotMessage.conversation_id == conversation.id)
            # A pari istante, la domanda prima della risposta ("bot" < "user").
            .order_by(JavbotMessage.created_at.desc(), JavbotMessage.role.asc())
            .limit(HISTORY_LIMIT)
        )
    ).scalars().all()
    return list(reversed(rows))


async def message_dicts(db: AsyncSession, messages: list[JavbotMessage]) -> list[dict]:
    """Le battute per il browser, con lo stato dei compiti citati nei
    bottoni: una proposta già confermata non si mostra più come da
    confermare."""
    task_ids = {
        uuid.UUID(a["task_id"]) for m in messages for a in (m.actions or [])
        if a.get("task_id")
    }
    statuses = dict(
        (await db.execute(select(JavbotTask.id, JavbotTask.status).where(JavbotTask.id.in_(task_ids)))).all()
    ) if task_ids else {}
    out = []
    for m in messages:
        actions = []
        for action in m.actions or []:
            if action.get("task_id"):
                action = {**action, "task_status": statuses.get(uuid.UUID(action["task_id"]), "CANCELLED")}
            actions.append(action)
        out.append({
            "id": m.id, "role": m.role, "text": m.text, "actions": actions,
            "quick_replies": m.quick_replies or [], "created_at": m.created_at,
        })
    return out
