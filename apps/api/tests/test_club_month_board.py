"""Il quadro del mese (club/month_board.py, docs/club-portal.md).

Le promesse: ogni atleta attivo compare una volta con la mensilità del mese
e il suo stato; chi è esente lo dice; i totali tornano con le quote; i mesi
non pagati prima sono arretrati e le altre quote scadute stanno a parte; la
famiglia vede solo i suoi.
"""

from datetime import date

import pytest
from sqlalchemy import select

from app.domains.club import month_board
from app.domains.club import service as club_service
from app.domains.club.models import ClubFee
from app.domains.club.service import ClubValidationError
from tests.test_club_fees import _athlete, _plans, _user

TODAY = date(2026, 10, 20)


async def _monthly(db, athlete_id, period):
    return (await db.execute(select(ClubFee).where(
        ClubFee.athlete_id == athlete_id, ClubFee.kind == "MONTHLY", ClubFee.period == period,
    ))).scalar_one()


async def test_the_month_board_says_who_still_has_to_pay(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    other_parent = await _user(db, scope, "altro")
    luca = await _athlete(db, scope, parent, birth_date=date(2016, 3, 3), first_name="Luca")
    sara = await _athlete(db, scope, parent, birth_date=date(2018, 3, 3), first_name="Sara")
    rui = await _athlete(db, scope, other_parent, birth_date=date(2015, 3, 3), first_name="Rui")
    free = await _athlete(db, scope, other_parent, birth_date=date(2014, 3, 3), first_name="Tó")
    free.exempt_monthly = True
    await db.commit()

    october = await _monthly(db, luca.id, "2026-10")
    await club_service.mark_fee_paid(db, scope=scope, fee_id=october.id, actor_user_id=admin.id, note=None, method="MBWAY")
    # Un mese vecchio non pagato e una gara da pagare: a parte.
    db.add(ClubFee(**scope.columns(), athlete_id=rui.id, kind="MONTHLY", period="2026-09", description="Mensilità settembre",
                   amount_cents=3000, due_date=date(2026, 9, 10), status="DUE"))
    db.add(ClubFee(**scope.columns(), athlete_id=rui.id, kind="COMPETITION", period="gara-1", description="Taça do Algarve",
                   amount_cents=1500, due_date=date(2026, 10, 25), status="DUE"))
    db.add(ClubFee(**scope.columns(), athlete_id=rui.id, kind="EQUIPMENT", period="ordine-1", description="Judogi",
                   amount_cents=4500, due_date=date(2026, 12, 1), status="DUE"))
    # La quota di Tó, se c'è, si toglie: è esente.
    for fee in (await db.execute(select(ClubFee).where(ClubFee.athlete_id == free.id, ClubFee.kind == "MONTHLY"))).scalars():
        await db.delete(fee)
    await db.commit()

    board = await month_board.club_month(db, scope=scope, period="2026-10", today=TODAY)
    rows = {r["first_name"]: r for r in board["rows"]}
    assert set(rows) == {"Luca", "Sara", "Rui", "Tó"}
    assert rows["Luca"]["state"] == "PAID" and rows["Luca"]["fee"]["payment_method"] == "MBWAY"
    assert rows["Sara"]["state"] == "OVERDUE"  # scadenza il 10, oggi è il 20
    assert rows["Tó"]["state"] == "EXEMPT" and rows["Tó"]["fee"] is None
    assert rows["Luca"]["group"] and rows["Luca"]["guardian_email"] == parent.email
    assert [f["period"] for f in rows["Rui"]["arrears"]] == ["2026-09"]
    # La gara e l'iscrizione dell'anno sì; il judogi scade a dicembre: non è di questo mese.
    others = [f["description"] for f in rows["Rui"]["other_due"]]
    assert "Taça do Algarve" in others and "Judogi" not in others
    assert all(f["kind"] != "MONTHLY" for f in rows["Rui"]["other_due"])

    t = board["totals"]
    monthly = [r["fee"]["amount_cents"] for r in board["rows"] if r["fee"]]
    assert t["expected_cents"] == sum(monthly)
    assert t["collected_cents"] == rows["Luca"]["fee"]["amount_cents"]
    assert t["missing_cents"] == t["expected_cents"] - t["collected_cents"]
    assert (t["paid"], t["exempt"], t["arrears_cents"]) == (1, 1, 3000)
    assert t["other_due_cents"] == sum(f["amount_cents"] for r in board["rows"] for f in r["other_due"])
    assert board["is_current"] is True and board["period"] == "2026-10"

    with pytest.raises(ClubValidationError):
        month_board.parse_period("2026-13", today=TODAY)

    mine = await month_board.family_month(db, scope=scope, athletes=[luca, sara], today=TODAY)
    assert {r["first_name"] for r in mine["rows"]} == {"Luca", "Sara"} and mine["totals"]["to_pay"] == 1
