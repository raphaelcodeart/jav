"""Gli avvisi automatici della mensilità e la multa per il ritardo.
Specifica: docs/club-portal.md, "Avvisi della mensilità e multa".

Il club li accende o spegne dalle Impostazioni (`clubs.settings`:
`late_fee_enabled`, `late_fee_cents`, 15 € se non indicato). Acceso:

- il **1°, il 10 e il 15** del mese, dalle 9:00 (ora del club), un'email a
  ogni famiglia con la **mensilità del mese corrente** ancora da pagare (nessuna
  prova caricata: con la prova la quota risulta già pagata), che avvisa della
  multa del 16;
- il **16 alle 9:00** per ogni mensilità del mese ancora da pagare nasce una
  quota `FINE` (la multa), una sola per atleta e mese, e la famiglia lo legge
  per email e nelle notifiche.

Conta solo la mensilità del mese corrente: altri debiti non c'entrano. Il job
gira ogni ora (celery_app.club_payment_reminders_task); ogni avviso parte una
volta sola (`club_reminders_sent`), la multa una volta sola (UNIQUE atleta,
tipo, periodo).
"""

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.club.models import Club, ClubAthlete, ClubFee
from app.domains.club.scope import ClubScope

WARNING_DAYS = (1, 10, 15)
FINE_DAY = 16
SEND_HOUR = 9
DEFAULT_FINE_CENTS = 1500
MONTHS_PT = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
             "outubro", "novembro", "dezembro")


def _euro(cents: int) -> str:
    return f"{cents / 100:.2f} €".replace(".", ",")


def settings_of(club: Club) -> tuple[bool, int]:
    s = club.settings or {}
    return bool(s.get("late_fee_enabled")), int(s.get("late_fee_cents") or DEFAULT_FINE_CENTS)


async def _due_monthly(db: AsyncSession, *, scope: ClubScope, period: str) -> list[tuple[ClubFee, ClubAthlete]]:
    return list((await db.execute(
        select(ClubFee, ClubAthlete).join(ClubAthlete, ClubAthlete.id == ClubFee.athlete_id).where(
            ClubFee.club_id == scope.club_id, ClubFee.kind == "MONTHLY", ClubFee.period == period,
            ClubFee.status == "DUE", ClubAthlete.status == "ACTIVE",
        )
    )).all())


async def run(db: AsyncSession, *, scope: ClubScope, now: datetime | None = None) -> int:
    """Quanti avvisi e multe ha fatto partire in questo giro."""
    from html import escape

    from app.domains.club import service as club_service
    from app.domains.club.lessons import club_now
    from app.domains.club.tasks import _claim_reminder
    from app.domains.notifications import service as notifications_service

    club = await db.get(Club, scope.club_id)
    if club is None:
        return 0
    enabled, fine_cents = settings_of(club)
    if not enabled:
        return 0
    now = now or await club_now(db, club_id=scope.club_id)
    today = now.date()
    if now.hour < SEND_HOUR:
        return 0
    period = f"{today.year:04d}-{today.month:02d}"
    month = f"{MONTHS_PT[today.month - 1]} {today.year}"
    fine = _euro(fine_cents)
    done = 0

    if today.day in WARNING_DAYS:
        emails = []
        for fee, athlete in await _due_monthly(db, scope=scope, period=period):
            if not await _claim_reminder(db, organization_id=scope.organization_id, kind="LATE_FEE_WARNING",
                                         entity_id=str(fee.id), stage=f"day{today.day}"):
                continue
            title = f"Mensalidade de {month} por pagar — {athlete.first_name}"
            await notifications_service.notify_user(
                db, organization_id=scope.organization_id, user_id=athlete.guardian_user_id, type_="CLUB_LATE_FEE_WARNING",
                entity_type="club_fee", entity_id=fee.id, title=title,
                body=f"Pague até dia 15: a dia {FINE_DAY} às {SEND_HOUR}:00 é aplicada uma multa de {fine}.",
            )
            emails.append((athlete, fee, title))
            done += 1
        await db.commit()
        for athlete, fee, title in emails:
            await club_service.email_guardian(
                db, user_id=athlete.guardian_user_id, context="late fee warning", subject=title,
                heading=f"A mensalidade de {month} ainda não está paga",
                lines=[
                    f"A mensalidade de <strong>{escape(athlete.first_name)}</strong> de {month} "
                    f"(<strong>{_euro(fee.amount_cents)}</strong>) ainda está por pagar.",
                    f"Pague e carregue o comprovativo no portal <strong>até dia 15</strong>: "
                    f"a dia {FINE_DAY} às {SEND_HOUR}:00 é aplicada automaticamente uma multa de <strong>{fine}</strong>.",
                    "Se já pagou, carregue o comprovativo: a quota fica logo paga e não recebe mais avisos.",
                ],
                cta_label="Pagar a mensalidade",
            )

    if today.day >= FINE_DAY:
        fined = []
        for fee, athlete in await _due_monthly(db, scope=scope, period=period):
            fine_period = f"atraso-{period}"
            exists = (await db.execute(select(ClubFee.id).where(
                ClubFee.athlete_id == athlete.id, ClubFee.kind == "FINE", ClubFee.period == fine_period,
            ))).first()
            if exists:
                continue
            row = ClubFee(
                **scope.columns(), athlete_id=athlete.id, kind="FINE", period=fine_period,
                description=f"Multa por atraso — mensalidade de {month}", amount_cents=fine_cents,
                due_date=today + timedelta(days=7), status="DUE",
            )
            db.add(row)
            await db.flush()
            await notifications_service.notify_user(
                db, organization_id=scope.organization_id, user_id=athlete.guardian_user_id, type_="CLUB_LATE_FEE",
                entity_type="club_fee", entity_id=row.id, title=f"Multa de {fine}: mensalidade de {month} — {athlete.first_name}",
            )
            fined.append((athlete, fee))
            done += 1
        await db.commit()
        for athlete, fee in fined:
            await club_service.email_guardian(
                db, user_id=athlete.guardian_user_id, context="late fee applied",
                subject=f"Multa por atraso — {athlete.first_name}", heading="Foi aplicada a multa por atraso",
                lines=[
                    f"A mensalidade de <strong>{escape(athlete.first_name)}</strong> de {month} não foi paga até dia 15: "
                    f"foi aplicada uma multa de <strong>{fine}</strong>.",
                    "Pague a mensalidade e a multa no portal e carregue o comprovativo.",
                ],
                cta_label="Pagar no portal",
            )
    return done


def preview(today: date) -> dict:
    """Che cosa succede oggi (per la schermata delle impostazioni)."""
    return {"warning_today": today.day in WARNING_DAYS, "fine_today": today.day == FINE_DAY,
            "warning_days": list(WARNING_DAYS), "fine_day": FINE_DAY, "hour": SEND_HOUR}
