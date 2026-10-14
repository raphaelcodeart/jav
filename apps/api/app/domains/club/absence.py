"""Taxa de falta: chi in un mese ha fatto meno della metà delle lezioni paga
mezza mensilità; chi non è mai venuto non la paga.

La decide la segreteria, non il sistema: qui si calcola chi ne avrebbe
diritto (dalle presenze segnate) e la segreteria applica con un clic, o no.

Le lezioni "fatte" sono quelle per cui qualcuno ha segnato almeno una
presenza (o assenza) nei corsi dell'atleta: un corso in cui nessuno segna
niente non dice niente, e allora non si propone nulla. Si applica solo a una
mensilità ancora da pagare: una già pagata si rimborsa in altro modo
(riaprendola, o con un credito).
"""

import uuid
from datetime import date

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.audit import service as audit_service
from app.domains.club import seasons
from app.domains.club.models import ClubAthlete, ClubAttendance, ClubCourseAthlete, ClubFee
from app.domains.club.scope import ClubScope
from app.domains.club.service import ClubNotFoundError, ClubValidationError


def suggestion(*, held: int, presences: int) -> str | None:
    if held <= 0:
        return None
    if presences == 0:
        return "FULL"
    if presences * 2 < held:
        return "HALF"
    return None


def _net(fee: ClubFee) -> int:
    """La mensilità senza la taxa de falta: listino meno gli sconti."""
    gross = fee.gross_amount_cents if fee.gross_amount_cents is not None else fee.amount_cents
    return gross - (fee.discount_cents or 0)


async def month_overview(db: AsyncSession, *, scope: ClubScope, period: str) -> list[dict]:
    """Per ogni mensilità del mese: lezioni fatte, presenze, suggerimento."""
    from app.domains.club.family import fee_dict

    try:
        year, month = seasons.parse_period(period)
    except ValueError as exc:
        raise ClubValidationError("Il mese deve essere nel formato AAAA-MM.") from exc
    start = date(year, month, 1)
    end = date(year + (month == 12), month % 12 + 1, 1)
    rows = (
        await db.execute(
            select(ClubFee, ClubAthlete)
            .join(ClubAthlete, ClubAthlete.id == ClubFee.athlete_id)
            .where(ClubFee.club_id == scope.club_id, ClubFee.kind == "MONTHLY", ClubFee.period == period)
            .order_by(ClubAthlete.last_name, ClubAthlete.first_name)
        )
    ).all()
    out = []
    for fee, athlete in rows:
        courses = select(ClubCourseAthlete.course_id).where(ClubCourseAthlete.athlete_id == athlete.id)
        held = (
            await db.execute(
                select(func.count(distinct(func.concat(ClubAttendance.course_id, ClubAttendance.date)))).where(
                    ClubAttendance.course_id.in_(courses), ClubAttendance.date >= start, ClubAttendance.date < end
                )
            )
        ).scalar_one()
        presences = (
            await db.execute(
                select(func.count()).where(
                    ClubAttendance.athlete_id == athlete.id, ClubAttendance.present.is_(True),
                    ClubAttendance.date >= start, ClubAttendance.date < end,
                )
            )
        ).scalar_one()
        out.append({
            "fee": fee_dict(fee, today=date.today(), athlete=athlete),
            "athlete_name": f"{athlete.first_name} {athlete.last_name}",
            "lessons_held": held, "presences": presences,
            "suggestion": suggestion(held=held, presences=presences),
            "applied": fee.absence_adjustment,
        })
    return out


async def apply(
    db: AsyncSession, *, scope: ClubScope, fee_id: uuid.UUID, adjustment: str | None, actor_user_id: uuid.UUID,
) -> ClubFee:
    """Applica (HALF / FULL) o toglie (None) la taxa de falta a una mensilità
    da pagare. L'importo si ricalcola sempre dal netto, così applicarla due
    volte non la dimezza due volte."""
    fee = await db.get(ClubFee, fee_id)
    if fee is None or fee.club_id != scope.club_id or fee.kind != "MONTHLY":
        raise ClubNotFoundError("Mensilità non trovata.")
    if fee.status != "DUE":
        raise ClubValidationError(
            "La mensilità non è più da pagare: per rimborsarla riaprila o dai un credito alla famiglia."
        )
    net = _net(fee)
    fee.amount_cents = {"HALF": net // 2, "FULL": 0}.get(adjustment or "", net)
    fee.absence_adjustment = adjustment
    if fee.amount_cents == 0:
        fee.status = "WAIVED"
        fee.waive_reason = "Taxa de falta: nessuna presenza nel mese"
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.absence_adjustment", entity_type="club_fee", entity_id=str(fee.id),
        new_value={"adjustment": adjustment, "amount_cents": fee.amount_cents},
    )
    await db.commit()
    await db.refresh(fee)
    return fee
