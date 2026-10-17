"""Il cartellino di chi lavora nel club (treinador, treinador adjunto,
segreteria): "Entro" ed "Esco" dal telefono, le ore si sommano da sole.

Un turno aperto per persona alla volta (indice UNIQUE parziale su
`club_work_sessions`): un doppio "Entro" non apre due turni. La segreteria
vede le ore di tutti, mese per mese, e può correggere un turno (chi ha
dimenticato di uscire): resta scritto chi l'ha corretto.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.club.models import ClubWorkSession
from app.domains.club.scope import ClubScope
from app.domains.club.service import ClubNotFoundError, ClubValidationError
from app.domains.users.models import User

#: Un turno più lungo di così è quasi sempre un'uscita dimenticata: si
#: chiude comunque, ma la segreteria lo vede segnato.
LONG_SESSION_HOURS = 14


def minutes(session: ClubWorkSession, *, now: datetime | None = None) -> int:
    end = session.ended_at or now or utcnow()
    return max(int((end - session.started_at).total_seconds() // 60), 0)


def session_dict(session: ClubWorkSession, *, now: datetime | None = None) -> dict:
    return {
        "id": session.id, "user_id": session.user_id, "started_at": session.started_at,
        "ended_at": session.ended_at, "note": session.note, "minutes": minutes(session, now=now),
        "edited_at": session.edited_at, "added_later": bool(session.added_later),
        "corrected": session.corrected_by_user_id is not None,
    }


async def _open_session(db: AsyncSession, *, user_id: uuid.UUID) -> ClubWorkSession | None:
    return (
        await db.execute(
            select(ClubWorkSession).where(ClubWorkSession.user_id == user_id, ClubWorkSession.ended_at.is_(None))
        )
    ).scalar_one_or_none()


def _month_bounds(month: str) -> tuple[datetime, datetime]:
    year, mon = (int(x) for x in month.split("-"))
    start = datetime(year, mon, 1, tzinfo=UTC)
    end = datetime(year + (mon == 12), mon % 12 + 1, 1, tzinfo=UTC)
    return start, end


async def status(db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID) -> dict:
    now = utcnow()
    month_start, month_end = _month_bounds(now.strftime("%Y-%m"))
    sessions = list(
        (
            await db.execute(
                select(ClubWorkSession)
                .where(
                    ClubWorkSession.club_id == scope.club_id, ClubWorkSession.user_id == user_id,
                    ClubWorkSession.started_at >= month_start, ClubWorkSession.started_at < month_end,
                )
                .order_by(ClubWorkSession.started_at.desc())
            )
        ).scalars()
    )
    open_session = await _open_session(db, user_id=user_id)
    today = now.date()
    return {
        "open_session": session_dict(open_session, now=now) if open_session else None,
        "today_minutes": sum(minutes(s, now=now) for s in sessions if s.started_at.date() == today),
        "month_minutes": sum(minutes(s, now=now) for s in sessions),
        "sessions": [session_dict(s, now=now) for s in sessions],
    }


async def clock_in(db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, note: str | None) -> dict:
    if await _open_session(db, user_id=user_id) is not None:
        raise ClubValidationError("Hai già timbrato l'entrata: timbra l'uscita prima di entrare di nuovo.")
    db.add(ClubWorkSession(**scope.columns(), user_id=user_id, started_at=utcnow(), note=(note or "").strip() or None))
    await db.commit()
    return await status(db, scope=scope, user_id=user_id)


async def clock_out(db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, note: str | None) -> dict:
    session = await _open_session(db, user_id=user_id)
    if session is None or session.club_id != scope.club_id:
        raise ClubValidationError("Non risulta un'entrata da chiudere.")
    session.ended_at = utcnow()
    if note and note.strip():
        session.note = note.strip()[:300]
    await db.commit()
    return await status(db, scope=scope, user_id=user_id)


async def hours_by_staff(db: AsyncSession, *, scope: ClubScope, month: str) -> list[dict]:
    """Le ore del mese, persona per persona, con i turni."""
    from app.domains.club.people import _names

    try:
        start, end = _month_bounds(month)
    except ValueError as exc:
        raise ClubValidationError("Il mese deve essere nel formato AAAA-MM.") from exc
    now = utcnow()
    sessions = list(
        (
            await db.execute(
                select(ClubWorkSession)
                .where(
                    ClubWorkSession.club_id == scope.club_id,
                    ClubWorkSession.started_at >= start, ClubWorkSession.started_at < end,
                )
                .order_by(ClubWorkSession.started_at)
            )
        ).scalars()
    )
    by_user: dict[uuid.UUID, list[ClubWorkSession]] = {}
    for s in sessions:
        by_user.setdefault(s.user_id, []).append(s)
    names = await _names(db, set(by_user))
    return sorted(
        (
            {"user_id": uid, "name": names.get(uid, ""), "minutes": sum(minutes(s, now=now) for s in rows),
             "sessions": [session_dict(s, now=now) for s in rows]}
            for uid, rows in by_user.items()
        ),
        key=lambda r: r["name"].lower(),
    )


async def correct(
    db: AsyncSession, *, scope: ClubScope, session_id: uuid.UUID, actor_user_id: uuid.UUID, changes: dict,
) -> dict:
    session = await db.get(ClubWorkSession, session_id)
    if session is None or session.club_id != scope.club_id:
        raise ClubNotFoundError("Turno non trovato.")
    previous = _audit_values(session)
    started_at = _aware(changes["started_at"]) if changes.get("started_at") else session.started_at
    ended_at = _aware(changes["ended_at"]) if "ended_at" in changes else session.ended_at
    await _validate(db, user_id=session.user_id, started_at=started_at, ended_at=ended_at,
                    exclude_id=session.id, now=utcnow())
    session.started_at, session.ended_at = started_at, ended_at
    if "note" in changes:
        session.note = (changes["note"] or "").strip()[:300] or None
    session.corrected_by_user_id = actor_user_id
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.work_session_corrected", entity_type="club_work_session", entity_id=str(session.id),
        previous_value=previous, new_value=_audit_values(session),
    )
    await db.commit()
    await db.refresh(session)
    return session_dict(session)


async def staff_user(db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if user is None or user.club_id != scope.club_id:
        raise ClubNotFoundError("Persona non trovata.")
    return user


# --- I turni corretti dalla persona stessa -------------------------------------------------------
#
# Chi lavora nel club può correggere i suoi turni (un'uscita dimenticata, un
# orario sbagliato), toglierne uno timbrato per sbaglio e aggiungerne uno che
# ha dimenticato di timbrare. Ogni modifica resta nell'audit (prima e dopo),
# e sul turno resta scritto che è stato ritoccato: la segreteria lo vede nelle
# ore del mese e nell'elenco delle modifiche.

#: Un orario "nel futuro" di qualche minuto è l'orologio del telefono, non
#: un tentativo: si tollera.
FUTURE_TOLERANCE = timedelta(minutes=5)
#: Le azioni dell'audit che raccontano la storia dei turni.
SESSION_ACTIONS = (
    "club.work_session_edited", "club.work_session_added", "club.work_session_deleted",
    "club.work_session_corrected",
)


def _aware(value: datetime) -> datetime:
    """Un orario senza fuso arriva dal browser come ora UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def editable_from(now: datetime) -> datetime:
    """Il primo istante che la persona può ancora correggere: l'inizio del
    mese scorso. Prima, le ore sono già state contate e pagate: lì corregge
    solo la segreteria."""
    first = datetime(now.year, now.month, 1, tzinfo=UTC)
    return datetime(first.year - (first.month == 1), (first.month - 2) % 12 + 1, 1, tzinfo=UTC)


def _audit_values(session: ClubWorkSession) -> dict:
    return {
        "club_id": str(session.club_id), "user_id": str(session.user_id),
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None, "note": session.note,
    }


async def _validate(
    db: AsyncSession, *, user_id: uuid.UUID, started_at: datetime, ended_at: datetime | None,
    exclude_id: uuid.UUID | None, now: datetime,
) -> None:
    """Le regole di ogni turno scritto a mano: niente futuro, l'uscita dopo
    l'entrata, al massimo 24 ore, e nessuna sovrapposizione con un altro
    turno della stessa persona (un turno aperto conta fino ad adesso)."""
    if started_at > now + FUTURE_TOLERANCE or (ended_at is not None and ended_at > now + FUTURE_TOLERANCE):
        raise ClubValidationError("Un turno non può essere nel futuro.")
    if ended_at is not None and ended_at <= started_at:
        raise ClubValidationError("L'uscita deve essere dopo l'entrata.")
    if ended_at is not None and ended_at - started_at > timedelta(hours=24):
        raise ClubValidationError("Un turno non può durare più di 24 ore.")
    end = ended_at or now
    others = (
        await db.execute(
            select(ClubWorkSession).where(
                ClubWorkSession.user_id == user_id,
                ClubWorkSession.started_at < end,
                *([ClubWorkSession.id != exclude_id] if exclude_id else []),
            )
        )
    ).scalars()
    for other in others:
        if (other.ended_at or now) > started_at:
            raise ClubValidationError(
                "Questo turno si sovrappone a un altro già registrato: correggi prima quello."
            )


async def _own_session(
    db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, session_id: uuid.UUID, now: datetime,
) -> ClubWorkSession:
    session = await db.get(ClubWorkSession, session_id)
    if session is None or session.club_id != scope.club_id or session.user_id != user_id:
        raise ClubNotFoundError("Turno non trovato.")
    if session.started_at < editable_from(now):
        raise ClubValidationError(
            "Questo turno è di un mese già chiuso: per correggerlo scrivi alla segreteria."
        )
    return session


async def own_update(
    db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, session_id: uuid.UUID, changes: dict,
    now: datetime | None = None,
) -> dict:
    """La persona corregge un suo turno: entrata, uscita, nota."""
    now = now or utcnow()
    session = await _own_session(db, scope=scope, user_id=user_id, session_id=session_id, now=now)
    previous = _audit_values(session)
    started_at = _aware(changes["started_at"]) if changes.get("started_at") else session.started_at
    ended_at = _aware(changes["ended_at"]) if changes.get("ended_at") else session.ended_at
    if "ended_at" in changes and changes["ended_at"] is None and session.ended_at is not None:
        raise ClubValidationError("Un turno chiuso ha bisogno dell'ora di uscita.")
    if started_at < editable_from(now):
        raise ClubValidationError("Si possono correggere solo i turni di questo mese e del mese scorso.")
    await _validate(db, user_id=user_id, started_at=started_at, ended_at=ended_at, exclude_id=session.id, now=now)
    session.started_at, session.ended_at = started_at, ended_at
    if "note" in changes:
        session.note = (changes["note"] or "").strip()[:300] or None
    if _audit_values(session) == previous:
        return session_dict(session, now=now)
    session.edited_at, session.edited_by_user_id = now, user_id
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=user_id, action="club.work_session_edited",
        entity_type="club_work_session", entity_id=str(session.id), previous_value=previous,
        new_value=_audit_values(session),
    )
    await db.commit()
    await db.refresh(session)
    return session_dict(session, now=now)


async def own_add(
    db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, started_at: datetime, ended_at: datetime,
    note: str | None, now: datetime | None = None,
) -> dict:
    """Un turno dimenticato, scritto dopo: con entrata e uscita, sempre."""
    now = now or utcnow()
    started_at, ended_at = _aware(started_at), _aware(ended_at)
    if started_at < editable_from(now):
        raise ClubValidationError("Si possono aggiungere solo i turni di questo mese e del mese scorso.")
    await _validate(db, user_id=user_id, started_at=started_at, ended_at=ended_at, exclude_id=None, now=now)
    session = ClubWorkSession(
        **scope.columns(), user_id=user_id, started_at=started_at, ended_at=ended_at,
        note=(note or "").strip()[:300] or None, added_later=True, edited_at=now, edited_by_user_id=user_id,
    )
    db.add(session)
    await db.flush()
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=user_id, action="club.work_session_added",
        entity_type="club_work_session", entity_id=str(session.id), new_value=_audit_values(session),
    )
    await db.commit()
    await db.refresh(session)
    return session_dict(session, now=now)


async def own_delete(
    db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, session_id: uuid.UUID, now: datetime | None = None,
) -> None:
    """Toglie un turno timbrato per sbaglio. Resta nell'audit com'era."""
    now = now or utcnow()
    session = await _own_session(db, scope=scope, user_id=user_id, session_id=session_id, now=now)
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=user_id, action="club.work_session_deleted",
        entity_type="club_work_session", entity_id=str(session.id), previous_value=_audit_values(session),
    )
    await db.delete(session)
    await db.commit()


async def session_changes(db: AsyncSession, *, scope: ClubScope, month: str) -> list[dict]:
    """Le modifiche ai turni fatte nel mese (dalla persona o dalla
    segreteria), dalla più recente: chi, quando, prima e dopo."""
    from app.domains.audit.models import AuditLog
    from app.domains.club.people import _names

    try:
        start, end = _month_bounds(month)
    except ValueError as exc:
        raise ClubValidationError("Il mese deve essere nel formato AAAA-MM.") from exc
    club = str(scope.club_id)
    rows = list(
        (
            await db.execute(
                select(AuditLog)
                .where(
                    AuditLog.organization_id == scope.organization_id, AuditLog.action.in_(SESSION_ACTIONS),
                    AuditLog.created_at >= start, AuditLog.created_at < end,
                    (AuditLog.new_value["club_id"].astext == club) | (AuditLog.previous_value["club_id"].astext == club),
                )
                .order_by(AuditLog.created_at.desc())
                .limit(500)
            )
        ).scalars()
    )
    people: set[uuid.UUID] = set()
    for r in rows:
        if r.actor_user_id:
            people.add(r.actor_user_id)
        owner = (r.new_value or r.previous_value or {}).get("user_id")
        if owner:
            people.add(uuid.UUID(owner))
    names = await _names(db, people)
    out = []
    for r in rows:
        owner = (r.new_value or r.previous_value or {}).get("user_id")
        out.append({
            "id": r.id, "session_id": r.entity_id, "action": r.action.removeprefix("club.work_session_"),
            "at": r.created_at, "actor_name": names.get(r.actor_user_id, "") if r.actor_user_id else "",
            "user_id": owner, "user_name": names.get(uuid.UUID(owner), "") if owner else "",
            "before": r.previous_value, "after": r.new_value,
        })
    return out


async def my_sessions(db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, month: str) -> dict:
    """I turni di un mese della persona, con il limite da cui li può ancora
    correggere (`editable_from`): il mese scorso si sfoglia e si corregge."""
    try:
        start, end = _month_bounds(month)
    except ValueError as exc:
        raise ClubValidationError("Il mese deve essere nel formato AAAA-MM.") from exc
    now = utcnow()
    sessions = list(
        (
            await db.execute(
                select(ClubWorkSession)
                .where(
                    ClubWorkSession.club_id == scope.club_id, ClubWorkSession.user_id == user_id,
                    ClubWorkSession.started_at >= start, ClubWorkSession.started_at < end,
                )
                .order_by(ClubWorkSession.started_at.desc())
            )
        ).scalars()
    )
    return {
        "month": start.strftime("%Y-%m"), "editable_from": editable_from(now),
        "minutes": sum(minutes(s, now=now) for s in sessions),
        "sessions": [session_dict(s, now=now) for s in sessions],
    }
