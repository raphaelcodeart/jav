"""Gli obblighi di un atleta, per la fascia della sua scheda (area
dell'atleta e pagina della famiglia). Specifica: docs/club-portal.md, "Gli
obblighi dell'atleta".

- **Judogi colorato** (l'ordine al club, `club_equipment_orders`): azul per
  i maschi, rosa per le femmine; dal Grupo 3 (13 anni federali in su) una
  femmina sceglie rosa o azul. Manca finché non c'è un ordine non annullato
  del colore giusto.
- **Judogi bianco**: serve per le gare. Lo dichiara la famiglia o la
  segreteria (`club_athletes.white_judogi`), o risulta da un ordine bianco.
- **Certificato medico** valido (in scadenza = avviso).
- **Quota annuale** dell'anno pagata: è l'iscrizione (`ENROLLMENT`), che
  comprende quota socio, taxa de falta, seguro, iscrizione alla federazione
  e all'associazione distrettuale, in un'unica quota (anche a rate).
- **Pronto per le gare**: quota annuale pagata e judogi bianco; un maschio
  può gareggiare anche con il judogi azul.

Sono avvisi: per ora non bloccano l'iscrizione alle gare (competitions.eligibility).
"""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.club import seasons
from app.domains.club import service as club_service
from app.domains.club.models import ClubAthlete, ClubFee
from app.domains.club.operations_models import ClubEquipmentOrder

#: Da quanti anni federali una femmina può scegliere il judogi azul (Grupo 3).
FREE_COLOUR_AGE = 13

BLUE = ("azul", "blue", "blu")
PINK = ("rosa", "pink")
WHITE = ("branco", "white", "bianco")


def _has(colour: str, words: tuple[str, ...]) -> bool:
    c = colour.lower()
    return any(w in c for w in words)


async def obligations(db: AsyncSession, *, athletes: list[ClubAthlete], today: date) -> dict[uuid.UUID, dict]:
    ids = [a.id for a in athletes]
    if not ids:
        return {}
    orders: dict[uuid.UUID, list[ClubEquipmentOrder]] = {}
    for o in (await db.execute(select(ClubEquipmentOrder).where(
        ClubEquipmentOrder.athlete_id.in_(ids), ClubEquipmentOrder.status != "CANCELLED",
        ClubEquipmentOrder.kind == "JUDOGI", ClubEquipmentOrder.retired_on.is_(None),
    ))).scalars():
        orders.setdefault(o.athlete_id, []).append(o)
    year = str(today.year)
    annual: dict[uuid.UUID, list[ClubFee]] = {}
    for f in (await db.execute(select(ClubFee).where(
        ClubFee.athlete_id.in_(ids), ClubFee.kind == "ENROLLMENT", ClubFee.period.startswith(year),
    ))).scalars():
        annual.setdefault(f.athlete_id, []).append(f)
    certs = await club_service.latest_certificates(db, athlete_ids=ids)

    out: dict[uuid.UUID, dict] = {}
    for a in athletes:
        age = seasons.federal_age(a.birth_date, today.year)
        mine = orders.get(a.id, [])
        if a.sex == "M":
            colour_ok = any(_has(o.color, BLUE) for o in mine)
            colour_rule = "BLUE"
        elif age >= FREE_COLOUR_AGE:
            colour_ok = any(_has(o.color, BLUE) or _has(o.color, PINK) for o in mine)
            colour_rule = "PINK_OR_BLUE"
        else:
            colour_ok = any(_has(o.color, PINK) for o in mine)
            colour_rule = "PINK"
        colour_order = next((o for o in mine if not _has(o.color, WHITE)), None)
        white_ok = a.white_judogi or any(_has(o.color, WHITE) for o in mine)
        blue_ok = any(_has(o.color, BLUE) for o in mine)

        cert_status = club_service.certificate_status(certs.get(a.id), today=today)
        fees = annual.get(a.id, [])
        if a.exempt_annual:
            annual_state = "EXEMPT"
        elif not fees:
            annual_state = "NOT_ISSUED"
        elif all(f.status in ("PAID", "WAIVED") for f in fees):
            annual_state = "PAID"
        else:
            annual_state = "DUE"
        annual_ok = annual_state in ("PAID", "EXEMPT")
        compete_judogi = white_ok or (a.sex == "M" and blue_ok)

        items = [
            {"code": "JUDOGI_COLOUR", "ok": colour_ok, "rule": colour_rule,
             "status": colour_order.status if colour_order else None},
            {"code": "WHITE_JUDOGI", "ok": white_ok, "declared": a.white_judogi},
            {"code": "CERTIFICATE", "ok": cert_status in ("VALID", "EXPIRING"), "state": cert_status},
            {"code": "ANNUAL_FEE", "ok": annual_ok, "state": annual_state,
             "due_cents": sum(f.amount_cents for f in fees if f.status == "DUE")},
        ]
        out[a.id] = {
            "items": items,
            "missing": sum(1 for i in items if not i["ok"]),
            "can_compete": annual_ok and compete_judogi,
            "compete_missing": [c for c, ok in (("ANNUAL_FEE", annual_ok), ("WHITE_JUDOGI", compete_judogi)) if not ok],
        }
    return out
