"""Gli avvisi della mensilità e la multa del 16 (club/payment_reminders.py).

Le promesse: spenti non fanno niente; il 1°, il 10 e il 15 dalle 9:00 avvisano
una volta chi non ha pagato la mensilità del mese; il 16 dalle 9:00 nasce una
multa sola per atleta e mese; chi ha pagato non riceve niente.
"""

from datetime import date, datetime

from sqlalchemy import select

from app.domains.club import clubs as clubs_service
from app.domains.club import payment_reminders
from app.domains.club.models import ClubFee
from tests.test_club_fees import _athlete, _plans, _user


async def _monthly(db, athlete_id, period):
    return (await db.execute(select(ClubFee).where(ClubFee.athlete_id == athlete_id, ClubFee.kind == "MONTHLY",
                                                   ClubFee.period == period))).scalar_one_or_none()


async def test_warnings_and_the_fine(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    late = await _athlete(db, scope, parent, birth_date=date(2016, 3, 3), first_name="Luca", today=date(2026, 11, 1))
    good = await _athlete(db, scope, parent, birth_date=date(2016, 3, 3), first_name="Sara", today=date(2026, 11, 1))
    paid = await _monthly(db, good.id, "2026-11")
    assert paid is not None
    paid.status = "PAID"
    await db.commit()

    assert await payment_reminders.run(db, scope=scope, now=datetime(2026, 11, 1, 10, 0)) == 0  # spento
    await clubs_service.update_club_settings(db, scope=scope, actor_user_id=admin.id, changes={"late_fee_enabled": True})
    assert await payment_reminders.run(db, scope=scope, now=datetime(2026, 11, 1, 8, 0)) == 0  # prima delle 9
    assert await payment_reminders.run(db, scope=scope, now=datetime(2026, 11, 1, 9, 5)) == 1
    assert await payment_reminders.run(db, scope=scope, now=datetime(2026, 11, 1, 15, 5)) == 0  # già avvisato oggi
    assert await payment_reminders.run(db, scope=scope, now=datetime(2026, 11, 10, 9, 5)) == 1
    assert await payment_reminders.run(db, scope=scope, now=datetime(2026, 11, 12, 9, 5)) == 0  # non è un giorno di avviso
    assert await payment_reminders.run(db, scope=scope, now=datetime(2026, 11, 16, 9, 5)) == 1
    assert await payment_reminders.run(db, scope=scope, now=datetime(2026, 11, 17, 9, 5)) == 0  # una multa sola
    fines = list((await db.execute(select(ClubFee).where(ClubFee.kind == "FINE", ClubFee.athlete_id == late.id))).scalars())
    assert len(fines) == 1 and fines[0].amount_cents == 1500 and fines[0].period == "atraso-2026-11"
    assert not (await db.execute(select(ClubFee).where(ClubFee.kind == "FINE", ClubFee.athlete_id == good.id))).first()
