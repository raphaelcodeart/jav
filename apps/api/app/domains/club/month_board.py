"""Il quadro del mese: chi ha pagato la mensilità e chi no. Specifica:
docs/club-portal.md, "Il quadro del mese".

È la prima cosa che la segreteria deve vedere: ogni mese ogni atleta paga
l'abbonamento del suo gruppo (la quota MONTHLY del mese, `period` =
"YYYY-MM"), e chi manca si deve capire con un'occhiata. Una riga per atleta
attivo, con il suo gruppo (il piano), l'importo e lo stato:

- PAID     pagata;
- DUE      da pagare (OVERDUE se la scadenza è passata);
- WAIVED   condonata;
- EXEMPT   l'atleta non paga la mensilità (`exempt_monthly`);
- NONE     nessuna quota per il mese (piano senza mensilità in quel mese,
           atleta arrivato dopo, quota non ancora generata).

Accanto, ciò che la stessa persona deve ancora pagare oltre alla mensilità:
i mesi passati non pagati (arretrati) e le altre quote scadute entro la fine
del mese (gare, judogi, iscrizione, multe). Gli ordini dello Shop restano
dello Shop: la segreteria li vede a parte. Tutto si calcola dalle quote, mai
da un totale salvato.

Lo stesso calcolo, ristretto a una famiglia, dà la card «Questo mese» della
pagina del genitore (`family_month`).
"""

import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.club.models import ClubAthlete, ClubFee, ClubPlan
from app.domains.club.scope import ClubScope
from app.domains.club.service import ClubValidationError
from app.domains.users.models import User


def parse_period(period: str | None, *, today: date) -> tuple[str, date, date]:
    """"YYYY-MM" (o None = questo mese) → (periodo, primo giorno, ultimo giorno)."""
    if not period:
        period = f"{today.year:04d}-{today.month:02d}"
    try:
        year, month = (int(x) for x in period.split("-"))
        first = date(year, month, 1)
    except (ValueError, TypeError) as exc:
        raise ClubValidationError("Mese non valido: usa AAAA-MM.") from exc
    last = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    return f"{year:04d}-{month:02d}", first, last


def _state(fee: ClubFee | None, athlete: ClubAthlete, *, today: date) -> str:
    if fee is None:
        return "EXEMPT" if athlete.exempt_monthly else "NONE"
    if fee.status == "DUE":
        return "OVERDUE" if fee.due_date < today else "DUE"
    return fee.status


async def _rows(
    db: AsyncSession, *, scope: ClubScope, athletes: list[ClubAthlete], period: str, last_day: date, today: date,
) -> list[dict]:
    from app.domains.club.family import fee_dict

    ids = [a.id for a in athletes]
    if not ids:
        return []
    fees = list((await db.execute(
        select(ClubFee).where(ClubFee.club_id == scope.club_id, ClubFee.athlete_id.in_(ids))
    )).scalars())
    plans = {p.id: p for p in (await db.execute(
        select(ClubPlan).where(ClubPlan.club_id == scope.club_id)
    )).scalars()}
    monthly: dict[uuid.UUID, ClubFee] = {}
    arrears: dict[uuid.UUID, list[ClubFee]] = {}
    others: dict[uuid.UUID, list[ClubFee]] = {}
    for f in fees:
        if f.kind == "MONTHLY" and f.period == period:
            monthly[f.athlete_id] = f
        elif f.status != "DUE":
            continue
        elif f.kind == "MONTHLY" and f.period < period:
            arrears.setdefault(f.athlete_id, []).append(f)
        elif f.kind != "MONTHLY" and f.due_date <= last_day:
            others.setdefault(f.athlete_id, []).append(f)
    by_id = {a.id: a for a in athletes}
    rows = []
    for a in athletes:
        fee = monthly.get(a.id)
        plan = plans.get(a.plan_id) if a.plan_id else None
        rows.append({
            "athlete_id": a.id,
            "first_name": a.first_name,
            "last_name": a.last_name,
            "photo_url": a.photo_url,
            "guardian_user_id": a.guardian_user_id,
            "group": plan.name if plan else None,
            "state": _state(fee, a, today=today),
            "fee": fee_dict(fee, today=today, athlete=a) if fee else None,
            "arrears": [fee_dict(f, today=today, athlete=by_id[a.id]) for f in sorted(arrears.get(a.id, []), key=lambda f: f.period)],
            "other_due": [fee_dict(f, today=today, athlete=by_id[a.id]) for f in sorted(others.get(a.id, []), key=lambda f: f.due_date)],
        })
    return rows


def _totals(rows: list[dict]) -> dict:
    counted = [r for r in rows if r["fee"] and r["state"] != "WAIVED"]
    return {
        "athletes": len(rows),
        "expected_cents": sum(r["fee"]["amount_cents"] for r in counted),
        "collected_cents": sum(r["fee"]["amount_cents"] for r in counted if r["state"] == "PAID"),
        "missing_cents": sum(r["fee"]["amount_cents"] for r in counted if r["state"] in ("DUE", "OVERDUE")),
        "paid": sum(1 for r in rows if r["state"] == "PAID"),
        "to_pay": sum(1 for r in rows if r["state"] in ("DUE", "OVERDUE")),
        "overdue": sum(1 for r in rows if r["state"] == "OVERDUE"),
        "exempt": sum(1 for r in rows if r["state"] in ("EXEMPT", "WAIVED")),
        "none": sum(1 for r in rows if r["state"] == "NONE"),
        "arrears_cents": sum(f["amount_cents"] for r in rows for f in r["arrears"]),
        "other_due_cents": sum(f["amount_cents"] for r in rows for f in r["other_due"]),
    }


async def club_month(db: AsyncSession, *, scope: ClubScope, period: str | None, today: date) -> dict:
    """Il quadro del mese per la segreteria: tutti gli atleti attivi (e chi,
    sospeso o uscito, ha comunque una mensilità in quel mese)."""
    period, first, last = parse_period(period, today=today)
    with_fee = select(ClubFee.athlete_id).where(
        ClubFee.club_id == scope.club_id, ClubFee.kind == "MONTHLY", ClubFee.period == period,
    )
    athletes = list((await db.execute(
        select(ClubAthlete).where(
            ClubAthlete.club_id == scope.club_id,
            (ClubAthlete.status == "ACTIVE") | ClubAthlete.id.in_(with_fee),
        ).order_by(ClubAthlete.first_name, ClubAthlete.last_name)
    )).scalars())
    rows = await _rows(db, scope=scope, athletes=athletes, period=period, last_day=last, today=today)
    emails = dict((await db.execute(
        select(User.id, User.email).where(User.id.in_({r["guardian_user_id"] for r in rows}))
    )).all()) if rows else {}
    for r in rows:
        r["guardian_email"] = emails.get(r["guardian_user_id"])
    return {
        "period": period, "first_day": first, "last_day": last,
        "is_current": first <= today <= last,
        "rows": rows, "totals": _totals(rows),
    }


async def family_month(
    db: AsyncSession, *, scope: ClubScope, athletes: list[ClubAthlete], today: date,
) -> dict:
    """«Questo mese» per una famiglia: la mensilità di ogni figlio e ciò che
    resta (arretrati e altre quote scadute)."""
    period, first, last = parse_period(None, today=today)
    active = [a for a in athletes if a.status == "ACTIVE"]
    rows = await _rows(db, scope=scope, athletes=active, period=period, last_day=last, today=today)
    return {"period": period, "first_day": first, "last_day": last, "is_current": True,
            "rows": rows, "totals": _totals(rows)}
