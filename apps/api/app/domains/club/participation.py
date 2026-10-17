"""«Voglio partecipare»: chi del mio conto può andare a una gara, e perché no.

Un debito blocca: con una quota **scaduta e non pagata** (dell'atleta, o della
famiglia come la quota socio) non ci si iscrive alle gare, finché non si paga.
La segreteria può segnare una quota precisa come «non bloccante»
(`ClubFee.non_blocking`): resta un debito, ma non ferma l'iscrizione. La
regola sta qui ed è usata da `competitions.eligibility` (iscrizione della
famiglia) e dal «Voglio partecipare» dell'atleta, così vale da ogni parte.
"""

import uuid
from datetime import date

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.club.models import ClubAthlete, ClubCompetition, ClubCompetitionEntry, ClubFee

DEBTS_REASON = (
    "Ci sono quote scadute da pagare: con dei debiti non ci si iscrive alle gare. "
    "Paga le quote (o parlane con la segreteria) e poi iscriviti."
)


async def blocking_debts(
    db: AsyncSession, *, athlete: ClubAthlete, today: date, exclude_competition_id: uuid.UUID | None = None,
) -> list[ClubFee]:
    """Le quote che impediscono di iscriversi: da pagare, scadute prima di
    oggi, non segnate «non bloccanti»; dell'atleta o del suo conto (quota
    socio del titolare). La quota della stessa gara non conta."""
    stmt = select(ClubFee).where(
        ClubFee.club_id == athlete.club_id,
        ClubFee.status == "DUE",
        ClubFee.due_date < today,
        ClubFee.non_blocking.is_(False),
        ClubFee.amount_cents > 0,
        or_(
            ClubFee.athlete_id == athlete.id,
            and_(ClubFee.athlete_id.is_(None), ClubFee.guardian_user_id == athlete.guardian_user_id),
        ),
    )
    if exclude_competition_id is not None:
        stmt = stmt.where(or_(ClubFee.competition_id.is_(None), ClubFee.competition_id != exclude_competition_id))
    return list((await db.execute(stmt.order_by(ClubFee.due_date))).scalars())


async def my_athletes(db: AsyncSession, *, club_id: uuid.UUID, user_id: uuid.UUID) -> list[tuple[ClubAthlete, str]]:
    """Gli atleti di chi guarda, con che cosa può fare: ENROLL se è il
    titolare del conto (si iscrive), WISH se è l'atleta con il suo accesso
    (chiede al titolare)."""
    rows = (
        await db.execute(
            select(ClubAthlete).where(
                ClubAthlete.club_id == club_id, ClubAthlete.status == "ACTIVE",
                or_(ClubAthlete.guardian_user_id == user_id, ClubAthlete.user_id == user_id),
            ).order_by(ClubAthlete.first_name)
        )
    ).scalars()
    return [(a, "ENROLL" if a.guardian_user_id == user_id else "WISH") for a in rows]


async def registered_competition_ids(db: AsyncSession, *, athlete_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    if not athlete_ids:
        return []
    return list(
        (
            await db.execute(
                select(ClubCompetitionEntry.competition_id).where(
                    ClubCompetitionEntry.athlete_id.in_(athlete_ids), ClubCompetitionEntry.status == "REGISTERED",
                ).distinct()
            )
        ).scalars()
    )


async def status_for(
    db: AsyncSession, *, competition: ClubCompetition, athlete: ClubAthlete, mode: str, today: date,
) -> dict:
    """Lo stato di un atleta davanti a una gara, per la finestra del bottone."""
    from app.domains.club import competitions as competitions_service
    from app.domains.club.family import fee_dict

    entry = (
        await db.execute(
            select(ClubCompetitionEntry).where(
                ClubCompetitionEntry.competition_id == competition.id, ClubCompetitionEntry.athlete_id == athlete.id
            )
        )
    ).scalar_one_or_none()
    debts = await blocking_debts(db, athlete=athlete, today=today, exclude_competition_id=competition.id)
    base = {
        "athlete_id": athlete.id, "name": f"{athlete.first_name} {athlete.last_name}", "photo_url": athlete.photo_url,
        "mode": mode, "debts": [fee_dict(f, today=today, athlete=athlete) for f in debts],
        "debts_cents": sum(f.amount_cents for f in debts),
    }
    if entry is not None and entry.status == "REGISTERED":
        return {**base, "status": "REGISTERED", "reason": None}
    ok, reason = await competitions_service.eligibility(db, competition=competition, athlete=athlete, today=today)
    if ok:
        return {**base, "status": "CAN", "reason": None}
    return {**base, "status": "DEBTS" if reason == DEBTS_REASON else "NO", "reason": reason}


async def send_wish(db: AsyncSession, *, athlete: ClubAthlete, competition: ClubCompetition) -> bool:
    """«Voglio partecipare» dell'atleta che non si iscrive da solo: email e
    notifica al titolare del conto, con la scadenza. Una volta sola per atleta
    e gara: False se era già stata mandata."""
    from html import escape

    from app.domains.club import service as club_service
    from app.domains.club.tasks import _claim_reminder
    from app.domains.notifications import service as notifications_service

    comp = competition
    fresh = await _claim_reminder(db, organization_id=athlete.organization_id, kind="COMPETITION_WISH",
                                  entity_id=f"{athlete.id}:{comp.id}", stage="wish")
    if not fresh:
        await db.commit()
        return False
    deadline = comp.registration_deadline.strftime("%d/%m/%Y")
    title = f"{athlete.first_name} quer participar: {comp.name}"
    await notifications_service.notify_user(
        db, organization_id=athlete.organization_id, user_id=athlete.guardian_user_id, type_="CLUB_COMPETITION_WISH",
        entity_type="club_competition", entity_id=comp.id, title=title,
        body=f"Inscreva-o até {deadline} na página das provas.",
    )
    await db.commit()
    await club_service.email_guardian(
        db, user_id=athlete.guardian_user_id, context="competition wish",
        subject=title, heading=f"{athlete.first_name} quer ir à prova!",
        lines=[
            f"<strong>{escape(athlete.first_name)}</strong> carregou em «Quero participar» na prova "
            f"<strong>{escape(comp.name)}</strong> ({comp.starts_on.strftime('%d/%m/%Y')}"
            f"{', ' + escape(comp.location) if comp.location else ''}).",
            f"Lembre-se de o inscrever <strong>até {deadline}</strong> na página das provas do portal.",
        ],
        cta_label="Inscrever na prova",
    )
    return True
