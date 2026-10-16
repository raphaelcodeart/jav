"""Gli obblighi dell'atleta (club/obligations.py).

Le promesse: il judogi colorato è azul per i maschi, rosa per le femmine e
rosa o azul dal Grupo 3; il judogi bianco o (per i maschi) l'azul e la quota
annuale pagata rendono pronti per le gare; un ordine annullato non conta.
"""

from datetime import date

from sqlalchemy import select

from app.domains.club import obligations
from app.domains.club.models import ClubFee
from app.domains.club.operations_models import ClubEquipmentOrder
from tests.test_club_fees import _athlete, _plans, _user

TODAY = date(2026, 10, 16)


def _order(scope, athlete, colour, status="PENDING"):
    return ClubEquipmentOrder(**scope.columns(), athlete_id=athlete.id, kimono_name=athlete.first_name,
                              kimono_type="TRAINING", color=colour, brand="Fuji", size_cm=130, status=status)


async def test_judogi_colours_and_ready_to_compete(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    boy = await _athlete(db, scope, parent, birth_date=date(2016, 3, 3), first_name="Luca", sex="M")
    girl = await _athlete(db, scope, parent, birth_date=date(2016, 3, 3), first_name="Sara", sex="F")
    teen = await _athlete(db, scope, parent, birth_date=date(2011, 3, 3), first_name="Ana", sex="F")
    db.add_all([_order(scope, boy, "Azul"), _order(scope, girl, "Azul"), _order(scope, teen, "Azul"),
                _order(scope, girl, "Rosa", status="CANCELLED")])
    await db.commit()

    res = await obligations.obligations(db, athletes=[boy, girl, teen], today=TODAY)
    colour = {k: next(i for i in v["items"] if i["code"] == "JUDOGI_COLOUR")["ok"] for k, v in res.items()}
    assert colour == {boy.id: True, girl.id: False, teen.id: True}
    assert next(i for i in res[girl.id]["items"] if i["code"] == "JUDOGI_COLOUR")["rule"] == "PINK"

    # La quota annuale ancora da pagare: nessuno è pronto per le gare.
    assert not any(v["can_compete"] for v in res.values())
    for fee in (await db.execute(select(ClubFee).where(ClubFee.kind == "ENROLLMENT"))).scalars():
        fee.status = "PAID"
    girl.white_judogi = True
    await db.commit()
    res = await obligations.obligations(db, athletes=[boy, girl, teen], today=TODAY)
    # Il maschio gareggia con l'azul, la femmina con il bianco dichiarato, Ana no (ha solo l'azul).
    assert {k: v["can_compete"] for k, v in res.items()} == {boy.id: True, girl.id: True, teen.id: False}
    assert "WHITE_JUDOGI" in res[teen.id]["compete_missing"]
