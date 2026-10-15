"""Le mensilità di un atleta, mese per mese, per una stagione.

È il calendario che il genitore (e l'atleta, e la segreteria) apre per
vedere che cosa è pagato, che cosa è da pagare e che cosa è scaduto: dodici
caselle da settembre ad agosto, una per mese, e per ogni mese il gruppo con
cui conta (l'età federale di quell'anno, seasons.federal_age), la quota se è
già emessa, come è stata pagata e le presenze del mese.

Per i mesi non ancora emessi l'importo è una **previsione** calcolata qui,
con il gruppo che l'atleta avrà in quell'anno e gli sconti di oggi: così il
genitore vede prima che a gennaio la mensilità sale. La quota vera la
congela il job del 1° del mese (service.generate_monthly_fees).
"""

from datetime import date

from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.club import pricing as pricing_rules
from app.domains.club import seasons
from app.domains.club import service as club_service
from app.domains.club.models import ClubAthlete, ClubAttendance, ClubFee, ClubPaymentProof
from app.domains.club.scope import scope_of

#: Gli stati di una casella. PAID, WAIVED, DUE e OVERDUE hanno una quota;
#: UPCOMING è un mese futuro che si pagherà; NOT_BILLED un mese che il
#: gruppo non fattura (luglio, agosto); NOT_ENROLLED un mese fuori
#: dall'iscrizione; NONE un mese passato senza quota.
MONTH_STATES = ("PAID", "WAIVED", "DUE", "OVERDUE", "UPCOMING", "NOT_BILLED", "NOT_ENROLLED", "NONE")


def season_periods(season: int) -> list[tuple[int, int]]:
    """(anno, mese) da settembre ad agosto."""
    return [(season + (m < 9), m) for m in (9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8)]


def _enrolled(athlete: ClubAthlete, year: int, month: int) -> bool:
    first_of_month = date(year, month, 1)
    next_month = date(year + (month == 12), month % 12 + 1, 1)
    return athlete.joined_on < next_month and (athlete.left_on is None or athlete.left_on >= first_of_month)


async def season_months(db: AsyncSession, *, athlete: ClubAthlete, season: int, today: date) -> dict:
    """Le dodici caselle della stagione, più i totali per i grafici."""
    from app.domains.club.family import fee_dict

    scope = scope_of(athlete)
    periods = season_periods(season)
    keys = [f"{y:04d}-{m:02d}" for y, m in periods]
    plans = {p.id: p for p in await club_service.list_plans(db, scope=scope)}
    active_plans = [p for p in plans.values() if p.active]
    pricing = await club_service.club_pricing(db, club_id=athlete.club_id)
    family_size = (
        await db.execute(
            select(func.count()).where(
                ClubAthlete.club_id == athlete.club_id, ClubAthlete.guardian_user_id == athlete.guardian_user_id,
                ClubAthlete.status == "ACTIVE",
            )
        )
    ).scalar_one()
    fees = {
        f.period: f
        for f in (
            await db.execute(
                select(ClubFee).where(
                    ClubFee.athlete_id == athlete.id, ClubFee.kind == "MONTHLY", ClubFee.period.in_(keys)
                )
            )
        ).scalars()
    }
    proof_ids = {f.paid_via_proof_id for f in fees.values() if f.paid_via_proof_id}
    proofs = {
        p.id: p
        for p in (await db.execute(select(ClubPaymentProof).where(ClubPaymentProof.id.in_(proof_ids)))).scalars()
    } if proof_ids else {}
    attendance = {
        (int(y), int(m)): n
        for y, m, n in (
            await db.execute(
                select(extract("year", ClubAttendance.date), extract("month", ClubAttendance.date), func.count())
                .where(
                    ClubAttendance.athlete_id == athlete.id, ClubAttendance.present.is_(True),
                    ClubAttendance.date >= seasons.season_start(season),
                    ClubAttendance.date <= seasons.season_end(season),
                )
                .group_by(extract("year", ClubAttendance.date), extract("month", ClubAttendance.date))
            )
        ).all()
    }
    current_plan = plans.get(athlete.plan_id) if athlete.plan_id else None
    this_period = seasons.period_of(today)

    months = []
    for (year, month), period in zip(periods, keys, strict=True):
        plan = current_plan
        if not athlete.plan_locked:
            plan = club_service.pick_plan(active_plans, age=seasons.federal_age(athlete.birth_date, year)) or current_plan
        fee = fees.get(period)
        expected = None
        if fee is not None:
            state = fee.status if fee.status != "DUE" else ("OVERDUE" if fee.due_date < today else "DUE")
        elif plan is None or month not in (plan.billing_months or []) or plan.monthly_fee_cents <= 0:
            state = "NOT_BILLED"
        elif athlete.status != "ACTIVE" or not _enrolled(athlete, year, month):
            state = "NOT_ENROLLED"
        elif period > this_period:
            state = "UPCOMING"
            expected = pricing_rules.monthly_price(
                list_cents=plan.monthly_fee_cents, athlete=athlete, family_size=family_size, pricing=pricing
            )["amount_cents"]
        else:
            state = "NONE"
        proof = proofs.get(fee.paid_via_proof_id) if fee is not None and fee.paid_via_proof_id else None
        months.append({
            "period": period,
            "year": year,
            "month": month,
            "state": state,
            "current": period == this_period,
            "federal_age": seasons.federal_age(athlete.birth_date, year),
            "group_name": plan.name if plan else None,
            "expected_cents": expected,
            "fee": fee_dict(fee, today=today) if fee is not None else None,
            "proof": {
                "id": proof.id, "method": proof.method, "has_file": proof.storage_key is not None,
                "status": proof.status, "created_at": proof.created_at,
            } if proof is not None else None,
            "attendances": attendance.get((year, month), 0),
        })

    def total(*states: str) -> int:
        return sum(m["fee"]["amount_cents"] for m in months if m["state"] in states and m["fee"])

    return {
        "season": season,
        "season_label": seasons.season_label(season),
        "months": months,
        "summary": {
            "paid_cents": total("PAID"),
            "due_cents": total("DUE", "OVERDUE"),
            "overdue_cents": total("OVERDUE"),
            "upcoming_cents": sum(m["expected_cents"] or 0 for m in months),
            "months_paid": sum(1 for m in months if m["state"] == "PAID"),
            "months_due": sum(1 for m in months if m["state"] == "DUE"),
            "months_overdue": sum(1 for m in months if m["state"] == "OVERDUE"),
            "months_upcoming": sum(1 for m in months if m["state"] == "UPCOMING"),
            "attendances": sum(m["attendances"] for m in months),
        },
    }
