"""Il personale del club oltre al cartellino (workclock.py). Specifica:
docs/club-portal.md, "Il personale del club".

- **Compiti svolti** (`TASK`): chi lavora nel club (treinador, adjunto,
  monitor, segreteria) scrive dalla sua area che cosa ha fatto (preparato il
  tatami, accompagnato alla gara, pulito lo spogliatoio...). Senza costo, di
  solito: la segreteria può dargliene uno.
- **Lavoretti occasionali** (`ODD_JOB`): li scrive la segreteria, anche per
  chi non ha un account (il nome basta), con il costo.
- **Pagare** un compito o un lavoretto con un costo crea una spesa
  COLLABORATORS (`club_expenses`): la contabilità del club lo conta come
  tutte le altre spese, e la riga resta legata (`expense_id`).
- **Il mese del personale**: per ogni persona ore del cartellino, costo delle
  ore (tariffa oraria, accounting.staff_costs), compiti e lavoretti, e il
  totale.
- **Comunicazioni**: ogni persona dello staff ha due conversazioni, con la
  segreteria del suo club (CLUB) e con JudoArteVida (JAV). Un messaggio
  avvisa l'altra parte con una notifica; la risposta avvisa la persona.
"""

import uuid
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.club.operations_models import STAFF_MESSAGE_CHANNELS, ClubStaffMessage, ClubStaffTask
from app.domains.club.scope import ClubScope
from app.domains.club.service import ClubNotFoundError, ClubValidationError

MAX_BODY = 4000
JAV_ROLES = {"SUPER_ADMIN", "ORGANIZATION_ADMIN", "ADMIN"}


def _month(month: str) -> tuple[date, date]:
    try:
        y, m = (int(x) for x in month.split("-"))
        start = date(y, m, 1)
    except ValueError as exc:
        raise ClubValidationError("Il mese deve essere nel formato AAAA-MM.") from exc
    end = date(y + (m == 12), m % 12 + 1, 1)
    return start, end


def task_dict(t: ClubStaffTask) -> dict:
    return {
        "id": t.id, "user_id": t.user_id, "person_name": t.person_name, "kind": t.kind, "title": t.title,
        "done_on": t.done_on, "minutes": t.minutes, "cost_cents": t.cost_cents, "note": t.note,
        "paid_on": t.paid_on, "created_at": t.created_at,
    }


def _clean(text: str | None, limit: int) -> str | None:
    return " ".join((text or "").split())[:limit] or None


async def add_task(
    db: AsyncSession, *, scope: ClubScope, actor_user_id: uuid.UUID, kind: str, title: str, done_on: date,
    minutes: int | None = None, cost_cents: int = 0, note: str | None = None, user_id: uuid.UUID | None = None,
    person_name: str | None = None, today: date | None = None,
) -> ClubStaffTask:
    from app.domains.club.people import _names
    from app.domains.club.workclock import staff_user

    today = today or utcnow().date()
    title = _clean(title, 200)
    if not title:
        raise ClubValidationError("Scrivi che cosa è stato fatto.")
    if done_on > today + timedelta(days=1) or done_on < today - timedelta(days=400):
        raise ClubValidationError("La data non è valida.")
    if minutes is not None and not 0 < minutes <= 24 * 60:
        raise ClubValidationError("La durata va da 1 minuto a 24 ore.")
    if not 0 <= cost_cents <= 1_000_000:
        raise ClubValidationError("Il costo va da 0 a 10.000 €.")
    if user_id is not None:
        await staff_user(db, scope=scope, user_id=user_id)
        person_name = person_name or (await _names(db, {user_id})).get(user_id) or "—"
    person_name = _clean(person_name, 150)
    if not person_name:
        raise ClubValidationError("Scrivi chi ha fatto il lavoro.")
    row = ClubStaffTask(
        **scope.columns(), user_id=user_id, person_name=person_name, kind=kind, title=title, done_on=done_on,
        minutes=minutes, cost_cents=cost_cents, note=_clean(note, 500), recorded_by_user_id=actor_user_id,
    )
    db.add(row)
    await db.flush()
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id, action="club.staff_task_added",
        entity_type="club_staff_task", entity_id=str(row.id),
        new_value={"kind": kind, "title": title, "cost_cents": cost_cents, "person_name": person_name},
    )
    await db.commit()
    await db.refresh(row)
    return row


async def _task(db: AsyncSession, *, scope: ClubScope, task_id: uuid.UUID) -> ClubStaffTask:
    row = await db.get(ClubStaffTask, task_id)
    if row is None or row.club_id != scope.club_id:
        raise ClubNotFoundError("Lavoro non trovato.")
    return row


async def delete_task(db: AsyncSession, *, scope: ClubScope, task_id: uuid.UUID, actor_user_id: uuid.UUID,
                      own_user_id: uuid.UUID | None = None) -> None:
    """Toglie una riga non ancora pagata. `own_user_id`: dall'area dello
    staff, solo le proprie."""
    row = await _task(db, scope=scope, task_id=task_id)
    if own_user_id is not None and row.user_id != own_user_id:
        raise ClubNotFoundError("Lavoro non trovato.")
    if row.paid_on is not None:
        raise ClubValidationError("Questo lavoro è già stato pagato: si corregge dalla contabilità.")
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id, action="club.staff_task_deleted",
        entity_type="club_staff_task", entity_id=str(row.id), previous_value={"kind": row.kind, "title": row.title, "person_name": row.person_name,
                        "cost_cents": row.cost_cents, "done_on": row.done_on.isoformat()},
    )
    await db.delete(row)
    await db.commit()


async def pay_task(
    db: AsyncSession, *, scope: ClubScope, task_id: uuid.UUID, actor_user_id: uuid.UUID,
    cost_cents: int | None = None, paid_on: date | None = None, payment_method: str = "BANK_TRANSFER",
) -> ClubStaffTask:
    """Il pagamento: la spesa COLLABORATORS nella contabilità, una volta sola."""
    from app.domains.club import accounting

    row = await _task(db, scope=scope, task_id=task_id)
    if row.paid_on is not None:
        raise ClubValidationError("Questo lavoro è già stato pagato.")
    if cost_cents is not None:
        if not 0 < cost_cents <= 1_000_000:
            raise ClubValidationError("Il costo va da 0,01 a 10.000 €.")
        row.cost_cents = cost_cents
    if row.cost_cents <= 0:
        raise ClubValidationError("Indica quanto costa questo lavoro.")
    paid_on = paid_on or utcnow().date()
    expense = await accounting.create_expense(db, scope=scope, actor_user_id=actor_user_id, data={
        "category": "COLLABORATORS", "description": f"{row.person_name}: {row.title}"[:255],
        "amount_cents": row.cost_cents, "spent_on": paid_on, "payment_method": payment_method,
        "supplier": row.person_name,
    })
    row = await _task(db, scope=scope, task_id=task_id)
    row.paid_on = paid_on
    row.expense_id = expense.id
    if row.user_id is not None:
        from app.domains.notifications import service as notifications_service

        await notifications_service.notify_user(
            db, organization_id=scope.organization_id, user_id=row.user_id, type_="CLUB_STAFF_TASK_PAID",
            entity_type="club_staff_task", entity_id=row.id,
            title=f"Pago: {row.title} — {row.cost_cents / 100:.2f} €".replace(".", ","),
        )
    await db.commit()
    await db.refresh(row)
    return row


async def list_tasks(db: AsyncSession, *, scope: ClubScope, month: str, user_id: uuid.UUID | None = None) -> list[ClubStaffTask]:
    start, end = _month(month)
    stmt = select(ClubStaffTask).where(
        ClubStaffTask.club_id == scope.club_id, ClubStaffTask.done_on >= start, ClubStaffTask.done_on < end,
    )
    if user_id is not None:
        stmt = stmt.where(ClubStaffTask.user_id == user_id)
    return list((await db.execute(stmt.order_by(ClubStaffTask.done_on.desc(), ClubStaffTask.created_at.desc()))).scalars())


async def month_summary(db: AsyncSession, *, scope: ClubScope, month: str, today: date) -> dict:
    """Il mese del personale: persona per persona ore, costo delle ore,
    compiti e lavoretti (con quanto è ancora da pagare), e i totali."""
    from app.domains.club import accounting

    start, _end = _month(month)
    period = accounting.parse_period(month, today=today)
    people: dict[str, dict] = {}

    def person(key: str, name: str, user_id: uuid.UUID | None) -> dict:
        return people.setdefault(key, {
            "user_id": user_id, "name": name, "minutes": 0, "hours_cost_cents": 0, "hourly_rate_cents": None,
            "tasks": 0, "jobs_cost_cents": 0, "unpaid_cents": 0,
        })

    for r in await accounting.staff_costs(db, scope=scope, period=period, today=today):
        p = person(str(r["user_id"]), r["name"], r["user_id"])
        p.update(minutes=r["minutes"], hours_cost_cents=r["cost_cents"], hourly_rate_cents=r["hourly_rate_cents"])
    tasks = await list_tasks(db, scope=scope, month=month)
    for t in tasks:
        p = person(str(t.user_id) if t.user_id else f"name:{t.person_name.lower()}", t.person_name, t.user_id)
        p["tasks"] += 1
        p["jobs_cost_cents"] += t.cost_cents
        if t.paid_on is None:
            p["unpaid_cents"] += t.cost_cents
    rows = sorted(people.values(), key=lambda p: (-(p["hours_cost_cents"] + p["jobs_cost_cents"]), p["name"].lower()))
    for p in rows:
        p["total_cents"] = p["hours_cost_cents"] + p["jobs_cost_cents"]
    return {
        "month": start.strftime("%Y-%m"),
        "people": rows,
        "tasks": [task_dict(t) for t in tasks],
        "totals": {
            "minutes": sum(p["minutes"] for p in rows),
            "hours_cost_cents": sum(p["hours_cost_cents"] for p in rows),
            "jobs_cost_cents": sum(p["jobs_cost_cents"] for p in rows),
            "unpaid_cents": sum(p["unpaid_cents"] for p in rows),
            "total_cents": sum(p["total_cents"] for p in rows),
        },
    }


async def my_month(db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, month: str, today: date) -> dict:
    """L'area della persona dello staff: le sue ore e il loro valore, i suoi
    compiti e lavoretti del mese."""
    summary = await month_summary(db, scope=scope, month=month, today=today)
    mine = next((p for p in summary["people"] if p["user_id"] == user_id), None)
    return {
        "month": summary["month"],
        "minutes": mine["minutes"] if mine else 0,
        "hourly_rate_cents": mine["hourly_rate_cents"] if mine else None,
        "hours_cost_cents": mine["hours_cost_cents"] if mine else 0,
        "jobs_cost_cents": mine["jobs_cost_cents"] if mine else 0,
        "unpaid_cents": mine["unpaid_cents"] if mine else 0,
        "tasks": [t for t in summary["tasks"] if t["user_id"] == user_id],
    }


# --- Comunicazioni --------------------------------------------------------------------------------


def message_dict(m: ClubStaffMessage) -> dict:
    return {"id": m.id, "channel": m.channel, "from_staff": m.from_staff, "body": m.body,
            "created_at": m.created_at, "read_at": m.read_at}


def _channel(channel: str) -> str:
    channel = (channel or "").upper()
    if channel not in STAFF_MESSAGE_CHANNELS:
        raise ClubValidationError("Scegli a chi scrivere: il club o JudoArteVida.")
    return channel


def _body(body: str) -> str:
    body = (body or "").strip()[:MAX_BODY]
    if len(body) < 2:
        raise ClubValidationError("Il messaggio è vuoto.")
    return body


async def thread(db: AsyncSession, *, club_id: uuid.UUID, staff_user_id: uuid.UUID, channel: str,
                 mark_read_from_staff: bool | None = None) -> list[ClubStaffMessage]:
    """La conversazione, dal più vecchio. `mark_read_from_staff`: True =
    chi legge è il club/JAV (segna letti i messaggi della persona), False =
    chi legge è la persona (segna letti quelli dell'altra parte)."""
    rows = list((await db.execute(
        select(ClubStaffMessage).where(
            ClubStaffMessage.club_id == club_id, ClubStaffMessage.staff_user_id == staff_user_id,
            ClubStaffMessage.channel == _channel(channel),
        ).order_by(ClubStaffMessage.created_at)
    )).scalars())
    if mark_read_from_staff is not None:
        now = utcnow()
        changed = False
        for m in rows:
            if m.read_at is None and m.from_staff == mark_read_from_staff:
                m.read_at = now
                changed = True
        if changed:
            await db.commit()
    return rows


async def staff_write(db: AsyncSession, *, scope: ClubScope, staff_user_id: uuid.UUID, channel: str, body: str) -> ClubStaffMessage:
    from app.domains.club import clubs as clubs_service
    from app.domains.club.people import _names
    from app.domains.notifications import service as notifications_service

    channel = _channel(channel)
    row = ClubStaffMessage(**scope.columns(), staff_user_id=staff_user_id, channel=channel, from_staff=True,
                           author_user_id=staff_user_id, body=_body(body))
    db.add(row)
    await db.flush()
    name = (await _names(db, {staff_user_id})).get(staff_user_id) or "Staff"
    title = f"Messaggio dallo staff: {name}"
    if channel == "CLUB":
        await clubs_service.notify_club_staff(db, scope=scope, type_="CLUB_STAFF_MESSAGE", entity_type="club_staff_message",
                                              entity_id=row.id, title=title, body=row.body[:300])
    else:
        await notifications_service.notify_roles(
            db, organization_id=scope.organization_id, roles=JAV_ROLES, type_="CLUB_STAFF_MESSAGE",
            entity_type="club_staff_message", entity_id=row.id, title=title, body=row.body[:300],
            exclude_user_id=staff_user_id,
        )
    await db.commit()
    await db.refresh(row)
    return row


async def reply(db: AsyncSession, *, scope: ClubScope, staff_user_id: uuid.UUID, channel: str, body: str,
                author_user_id: uuid.UUID) -> ClubStaffMessage:
    """La risposta del club (CLUB) o di JudoArteVida (JAV) alla persona."""
    from app.domains.club.workclock import staff_user
    from app.domains.notifications import service as notifications_service

    await staff_user(db, scope=scope, user_id=staff_user_id)
    channel = _channel(channel)
    row = ClubStaffMessage(**scope.columns(), staff_user_id=staff_user_id, channel=channel, from_staff=False,
                           author_user_id=author_user_id, body=_body(body))
    db.add(row)
    await db.flush()
    await notifications_service.notify_user(
        db, organization_id=scope.organization_id, user_id=staff_user_id, type_="CLUB_STAFF_MESSAGE",
        entity_type="club_staff_message", entity_id=row.id,
        title="Nuova risposta da JudoArteVida" if channel == "JAV" else "Nuova risposta dalla segreteria del club",
        body=row.body[:300],
    )
    await db.commit()
    await db.refresh(row)
    return row


async def inbox(db: AsyncSession, *, channel: str, club_id: uuid.UUID | None = None,
                organization_id: uuid.UUID | None = None) -> list[dict]:
    """Le conversazioni (una per persona): per la segreteria (CLUB, il suo
    club) o per JudoArteVida (JAV, tutti i club). Con l'ultimo messaggio e
    quanti messaggi della persona non sono ancora letti."""
    from app.domains.club.models import Club
    from app.domains.club.people import _names

    channel = _channel(channel)
    where = [ClubStaffMessage.channel == channel]
    if club_id is not None:
        where.append(ClubStaffMessage.club_id == club_id)
    if organization_id is not None:
        where.append(ClubStaffMessage.organization_id == organization_id)
    groups = (await db.execute(
        select(ClubStaffMessage.club_id, ClubStaffMessage.staff_user_id, func.max(ClubStaffMessage.created_at),
               func.count().filter(ClubStaffMessage.from_staff.is_(True) & ClubStaffMessage.read_at.is_(None)))
        .where(*where).group_by(ClubStaffMessage.club_id, ClubStaffMessage.staff_user_id)
        .order_by(func.max(ClubStaffMessage.created_at).desc())
    )).all()
    if not groups:
        return []
    names = await _names(db, {g[1] for g in groups})
    clubs = {c.id: c.name for c in (await db.execute(select(Club).where(Club.id.in_({g[0] for g in groups})))).scalars()}
    out = []
    for club, user, last_at, unread in groups:
        last = (await db.execute(
            select(ClubStaffMessage).where(*where, ClubStaffMessage.club_id == club, ClubStaffMessage.staff_user_id == user)
            .order_by(ClubStaffMessage.created_at.desc()).limit(1)
        )).scalar_one()
        out.append({"club_id": club, "club_name": clubs.get(club, ""), "staff_user_id": user, "name": names.get(user, ""),
                    "last_at": last_at, "last_body": last.body[:200], "last_from_staff": last.from_staff, "unread": int(unread)})
    return out
