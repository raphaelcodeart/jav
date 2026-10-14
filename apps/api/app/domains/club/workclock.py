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
    previous = {"started_at": str(session.started_at), "ended_at": str(session.ended_at)}
    for key in ("started_at", "ended_at", "note"):
        if key in changes:
            setattr(session, key, changes[key])
    if session.ended_at is not None and session.ended_at <= session.started_at:
        raise ClubValidationError("L'uscita deve essere dopo l'entrata.")
    if session.ended_at is not None and session.ended_at - session.started_at > timedelta(hours=24):
        raise ClubValidationError("Un turno non può durare più di 24 ore.")
    session.corrected_by_user_id = actor_user_id
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.work_session_corrected", entity_type="club_work_session", entity_id=str(session.id),
        previous_value=previous,
        new_value={"started_at": str(session.started_at), "ended_at": str(session.ended_at)},
    )
    await db.commit()
    await db.refresh(session)
    return session_dict(session)


async def staff_user(db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if user is None or user.club_id != scope.club_id:
        raise ClubNotFoundError("Persona non trovata.")
    return user
