"""I lavori automatici del club: ciò che fa sì che il club si gestisca da solo.

Ognuno è idempotente per costruzione (vincoli UNIQUE: quote, promemoria) e
lavora un club alla volta. Li lancia Celery beat (celery_app.py);
generate_monthly_fees si può lanciare anche a mano dalla segreteria.
"""

import logging
import uuid
from datetime import date, timedelta
from html import escape

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.club import seasons, transport
from app.domains.club.competitions import visible_to as competitions_visible_to
from app.domains.club import service as club_service
from app.domains.club.models import (
    ClubAthlete,
    ClubCompetition,
    ClubCompetitionEntry,
    ClubFee,
    ClubReminderSent,
)
from app.domains.club.scope import ClubScope
from app.domains.notifications import service as notifications_service

logger = logging.getLogger(__name__)

#: Quanti giorni prima della scadenza delle iscrizioni si avvisano le famiglie.
COMPETITION_DEADLINE_NOTICE_DAYS = 3


async def _claim_reminder(db: AsyncSession, *, organization_id: uuid.UUID, kind: str, entity_id: str, stage: str) -> bool:
    """True se questo promemoria non era ancora stato inviato (e da adesso lo è)."""
    result = await db.execute(
        insert(ClubReminderSent)
        .values(id=uuid.uuid4(), created_at=utcnow(), organization_id=organization_id, kind=kind,
                entity_id=entity_id, stage=stage)
        .on_conflict_do_nothing(constraint="uq_club_reminders_sent_kind_entity_stage")
        .returning(ClubReminderSent.id)
    )
    return result.first() is not None


def _certificate_stage(expires_on: date, today: date) -> str | None:
    days = (expires_on - today).days
    if days < 0:
        return "expired"
    if days <= 7:
        return "7"
    if days <= 30:
        return "30"
    return None


async def send_reminders(db: AsyncSession, *, scope: ClubScope, today: date | None = None) -> int:
    """Gli avvisi del mattino: quote scadute, certificati e tesseramenti in
    scadenza o scaduti, iscrizioni alle gare che stanno per chiudere.
    Ciascuno parte una volta sola (club_reminders_sent)."""
    today = today or utcnow().date()
    pending: list[tuple[uuid.UUID, str, str, str, list[str]]] = []  # (genitore, tipo, titolo, oggetto, righe)

    athletes = {
        a.id: a
        for a in (
            await db.execute(
                select(ClubAthlete).where(ClubAthlete.club_id == scope.club_id, ClubAthlete.status == "ACTIVE")
            )
        ).scalars()
    }

    overdue = (
        await db.execute(
            select(ClubFee).where(
                ClubFee.club_id == scope.club_id, ClubFee.status == "DUE", ClubFee.due_date < today
            )
        )
    ).scalars().all()
    for fee in overdue:
        athlete = athletes.get(fee.athlete_id) if fee.athlete_id else None
        # La quota socio del genitore non ha un atleta: l'avviso va a lui.
        guardian_id = athlete.guardian_user_id if athlete is not None else fee.guardian_user_id
        if guardian_id is None or (fee.athlete_id is not None and athlete is None):
            continue
        if await _claim_reminder(db, organization_id=scope.organization_id, kind="FEE_OVERDUE", entity_id=str(fee.id), stage="overdue"):
            who = f" ({athlete.first_name})" if athlete is not None else ""
            title = f"Quota da pagare: {fee.description}{who}"
            pending.append((guardian_id, "CLUB_FEE_OVERDUE", title, title, [
                (f"La quota <strong>{escape(fee.description)}</strong>{escape(who)} "
                f"({fee.amount_cents / 100:.2f} €) era in scadenza il {fee.due_date.strftime('%d/%m/%Y')}."),
                "Se hai già pagato, carica la foto del pagamento dal portale: ci vuole un minuto.",
            ]))

    certs = await club_service.latest_certificates(db, athlete_ids=list(athletes))
    for athlete_id, athlete in athletes.items():
        cert = certs.get(athlete_id)
        if cert is not None:
            stage = _certificate_stage(cert.expires_on, today)
            if stage and await _claim_reminder(
                db, organization_id=scope.organization_id, kind="CERTIFICATE", entity_id=str(cert.id), stage=stage
            ):
                when = cert.expires_on.strftime("%d/%m/%Y")
                title = (
                    f"Il certificato medico di {athlete.first_name} è scaduto" if stage == "expired"
                    else f"Il certificato medico di {athlete.first_name} scade il {when}"
                )
                pending.append((athlete.guardian_user_id, "CLUB_CERTIFICATE", title, title, [
                    f"{escape(title)}.",
                    ("Senza certificato valido non si può allenare né gareggiare: carica il nuovo "
                    "certificato nella scheda dell'atleta."),
                ]))
        if athlete.federation_expires_on is not None:
            stage = _certificate_stage(athlete.federation_expires_on, today)
            if stage in ("30", "expired") and await _claim_reminder(
                db, organization_id=scope.organization_id, kind="FEDERATION",
                entity_id=f"{athlete.id}:{athlete.federation_expires_on.isoformat()}", stage=stage,
            ):
                title = (
                    f"Il tesseramento di {athlete.first_name} è scaduto" if stage == "expired"
                    else f"Il tesseramento di {athlete.first_name} scade il "
                         f"{athlete.federation_expires_on.strftime('%d/%m/%Y')}"
                )
                pending.append((athlete.guardian_user_id, "CLUB_FEDERATION", title, title, [
                    f"{escape(title)}.", "La segreteria provvede al rinnovo: tienilo d'occhio dal portale.",
                ]))

    closing = (
        await db.execute(
            select(ClubCompetition).where(
                ClubCompetition.club_id == scope.club_id, ClubCompetition.status == "OPEN",
                ClubCompetition.registration_deadline >= today,
                ClubCompetition.registration_deadline <= today + timedelta(days=COMPETITION_DEADLINE_NOTICE_DAYS),
            )
        )
    ).scalars().all()
    for comp in closing:
        registered = {
            a for (a,) in (
                await db.execute(
                    select(ClubCompetitionEntry.athlete_id).where(
                        ClubCompetitionEntry.competition_id == comp.id, ClubCompetitionEntry.status == "REGISTERED"
                    )
                )
            ).all()
        }
        guardians = {a.guardian_user_id for a in athletes.values() if a.id not in registered}
        for guardian_id in guardians:
            if await _claim_reminder(
                db, organization_id=scope.organization_id, kind="COMPETITION_DEADLINE",
                entity_id=f"{comp.id}:{guardian_id}", stage="deadline",
            ):
                title = f"Iscrizioni a «{comp.name}» aperte fino al {comp.registration_deadline.strftime('%d/%m/%Y')}"
                pending.append((guardian_id, "CLUB_COMPETITION_DEADLINE", title, title, [
                    (f"Le iscrizioni a <strong>{escape(comp.name)}</strong> del "
                    f"{comp.starts_on.strftime('%d/%m/%Y')} chiudono il "
                    f"{comp.registration_deadline.strftime('%d/%m/%Y')}."),
                    "Puoi iscrivere i tuoi atleti dal portale.",
                ]))

    for guardian_id, type_, title, _subject, _lines in pending:
        await notifications_service.notify_user(
            db, organization_id=scope.organization_id, user_id=guardian_id, type_=type_,
            entity_type="club", entity_id=guardian_id, title=title,
        )
    # I documenti del club in scadenza (certidões, assicurazioni): un avviso
    # alla segreteria, nella stessa transazione degli altri promemoria.
    from app.domains.club import club_documents

    documents_sent = await club_documents.expiry_reminders(db, scope=scope, today=today)
    # I promemoria risultano inviati solo se il commit riesce: un job che
    # cade a metà li rimanda tutti al giro dopo, invece di perderne qualcuno.
    await db.commit()
    for guardian_id, _type, title, subject, lines in pending:
        await club_service.email_guardian(
            db, user_id=guardian_id, context="club reminder", subject=subject, heading=title, lines=lines
        )
    return len(pending) + documents_sent


async def close_expired_competitions(db: AsyncSession, *, scope: ClubScope, today: date | None = None) -> int:
    today = today or utcnow().date()
    comps = (
        await db.execute(
            # Anche quelli della rete: chiuderli da ogni club è innocuo, e
            # così nessun evento resta aperto oltre la scadenza.
            select(ClubCompetition).where(
                competitions_visible_to(scope), ClubCompetition.status == "OPEN",
                ClubCompetition.registration_deadline < today,
            )
        )
    ).scalars().all()
    for comp in comps:
        comp.status = "CLOSED"
    await db.commit()
    for comp in comps:
        await transport.on_registrations_closed(db, comp=comp)
    return len(comps)


async def run_monthly_fees(db: AsyncSession, *, scope: ClubScope, today: date | None = None) -> int:
    today = today or utcnow().date()
    return await club_service.generate_monthly_fees(db, scope=scope, period=seasons.period_of(today), today=today)


async def run_new_year(db: AsyncSession, *, scope: ClubScope, today: date | None = None) -> int:
    """1° gennaio: iscrizioni dell'anno e quote socio dei genitori."""
    today = today or utcnow().date()
    return await club_service.start_year(db, scope=scope, year=today.year)


async def run_new_season(db: AsyncSession, *, scope: ClubScope, today: date | None = None) -> int:
    today = today or utcnow().date()
    return await club_service.start_season(db, scope=scope, season=seasons.season_of(today))


async def run_recurring_expenses(db: AsyncSession, *, scope: ClubScope, today: date | None = None) -> int:
    """I costi fissi del mese in corso diventano spese (club/accounting.py)."""
    from app.domains.club import accounting

    return await accounting.materialise_recurring(db, scope=scope, today=today or utcnow().date())


async def run_payment_reminders(db: AsyncSession, *, scope: ClubScope, today: date | None = None) -> int:
    """Avvisi della mensilità (1, 10, 15) e multa del 16 (club/payment_reminders.py)."""
    from app.domains.club import payment_reminders

    return await payment_reminders.run(db, scope=scope)

