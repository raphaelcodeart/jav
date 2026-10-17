"""Club: piani per età, quote, prove di pagamento (docs/club-portal.md).

Quello che questi test proteggono è la promessa "il club si gestisce da
solo": il piano lo sceglie l'età federale, le quote si generano una
volta sola anche se il job gira due volte, una prova caricata paga subito e
un rifiuto riapre esattamente ciò che aveva pagato -- e mai niente di
un'altra famiglia.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import func, select

from app.core.security import hash_password
from app.domains.club import service as club_service
from app.domains.club.models import ClubAthlete, ClubFee
from app.domains.users.models import User

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200


async def _user(db, scope, label="genitore") -> User:
    user = User(
        organization_id=scope.organization_id,
        club_id=scope.club_id,
        email=f"{label}-{uuid.uuid4().hex[:8]}@example.demo",
        password_hash=hash_password("x"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _plans(db, scope, actor):
    kids = await club_service.create_plan(db, scope=scope, actor_user_id=actor.id, data={
        "name": "Bambini 4-7", "min_age": 4, "max_age": 7, "monthly_fee_cents": 3000,
        "enrollment_fee_cents": 2500, "due_day": 10,
    })
    youth = await club_service.create_plan(db, scope=scope, actor_user_id=actor.id, data={
        "name": "Ragazzi 8-13", "min_age": 8, "max_age": 13, "monthly_fee_cents": 4000,
        "enrollment_fee_cents": 2500, "due_day": 10,
    })
    everyone = await club_service.create_plan(db, scope=scope, actor_user_id=actor.id, data={
        "name": "Adulti", "min_age": 4, "max_age": None, "monthly_fee_cents": 5000,
        "enrollment_fee_cents": 0, "due_day": 5,
    })
    return kids, youth, everyone


async def _athlete(db, scope, guardian, *, birth_date, today=date(2026, 10, 15), **kw) -> ClubAthlete:
    return await club_service.create_athlete(
        db, scope=scope, guardian_user_id=guardian.id, actor_user_id=guardian.id,
        first_name=kw.pop("first_name", "Luca"), last_name=kw.pop("last_name", "Bianchi"),
        birth_date=birth_date, sex=kw.pop("sex", "M"), today=today, **kw,
    )


async def _no_debts(db, athlete: ClubAthlete, *, days: int = 3650) -> None:
    """Sposta in avanti le scadenze delle quote dell'atleta e del suo conto:
    con quote scadute non ci si iscrive alle gare (club/participation.py)."""
    from datetime import timedelta

    from sqlalchemy import or_, update

    await db.execute(update(ClubFee).where(
        or_(ClubFee.athlete_id == athlete.id, (ClubFee.athlete_id.is_(None)) & (ClubFee.guardian_user_id == athlete.guardian_user_id))
    ).values(due_date=date.today() + timedelta(days=days)))
    await db.commit()


async def _fees(db, athlete_id, **filters) -> list[ClubFee]:
    stmt = select(ClubFee).where(ClubFee.athlete_id == athlete_id)
    for key, value in filters.items():
        stmt = stmt.where(getattr(ClubFee, key) == value)
    return list((await db.execute(stmt.order_by(ClubFee.due_date))).scalars())


async def test_plan_follows_the_federal_age(db, scope):
    admin = await _user(db, scope, "admin")
    kids, youth, _everyone = await _plans(db, scope, admin)
    parent = await _user(db, scope)

    # Compie 8 anni a febbraio 2027: nel 2026 ne ha 7 federali.
    seven = await _athlete(db, scope, parent, birth_date=date(2019, 2, 20))
    assert seven.plan_id == kids.id

    # Il 15 ottobre 2026 ha ancora 7 anni, ma ne compie 8 a novembre: l'età
    # federale (gli anni compiuti entro il 31 dicembre) è 8. Ragazzi, e non
    # "Adulti 4+", che pure lo copre -- vince il piano più stretto.
    eight = await _athlete(db, scope, parent, birth_date=date(2018, 11, 20), first_name="Anna", sex="F")
    assert eight.plan_id == youth.id


async def test_creating_an_athlete_does_the_paperwork_by_itself(db, scope):
    admin = await _user(db, scope, "admin")
    kids, _youth, _everyone = await _plans(db, scope, admin)
    parent = await _user(db, scope)

    athlete = await _athlete(db, scope, parent, birth_date=date(2020, 5, 1))

    fees = await _fees(db, athlete.id)
    # L'iscrizione segue l'anno solare: entrando a ottobre si pagano
    # ottobre, novembre e dicembre, 3/12 di 25 €.
    assert {(f.kind, f.period, f.amount_cents) for f in fees} == {
        ("ENROLLMENT", "2026", 625),
        ("MONTHLY", "2026-10", 3000),
    }
    # Un atleta minorenne: il genitore diventa socio, a pro rata anche lui
    # (60 € l'anno, 3/12).
    membership = (
        await db.execute(select(ClubFee).where(ClubFee.guardian_user_id == parent.id, ClubFee.kind == "MEMBERSHIP"))
    ).scalar_one()
    assert (membership.period, membership.amount_cents, membership.athlete_id) == ("2026", 1500, None)
    belts = await club_service.current_belts(db, athlete_ids=[athlete.id])
    assert belts[athlete.id] == "WHITE"
    assert kids.id == athlete.plan_id


async def test_monthly_generation_is_idempotent_and_respects_the_season(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    athlete = await _athlete(db, scope, parent, birth_date=date(2016, 3, 3))

    created = await club_service.generate_monthly_fees(db, scope=scope, period="2026-11")
    again = await club_service.generate_monthly_fees(db, scope=scope, period="2026-11")

    assert created == 1
    assert again == 0
    assert len(await _fees(db, athlete.id, kind="MONTHLY", period="2026-11")) == 1
    # Agosto non è nei mesi fatturati di default: nessuna quota.
    assert await club_service.generate_monthly_fees(db, scope=scope, period="2027-08") == 0
    with pytest.raises(club_service.ClubValidationError):
        await club_service.generate_monthly_fees(db, scope=scope, period="novembre")


async def test_no_fee_for_a_month_before_joining_or_after_leaving(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    athlete = await _athlete(db, scope, parent, birth_date=date(2016, 3, 3), today=date(2026, 12, 2))

    assert await club_service.generate_monthly_fees(db, scope=scope, period="2026-11") == 0

    await club_service.update_athlete(
        db, athlete=athlete, actor_user_id=admin.id, changes={"status": "LEFT"}, as_admin=True,
        today=date(2027, 1, 20),
    )
    assert await club_service.generate_monthly_fees(db, scope=scope, period="2027-02") == 0


async def test_a_proof_pays_its_fees_at_once_and_a_rejection_reopens_them(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    luca = await _athlete(db, scope, parent, birth_date=date(2016, 3, 3))
    anna = await _athlete(db, scope, parent, birth_date=date(2019, 3, 3), first_name="Anna", sex="F")
    october = [
        (await _fees(db, luca.id, kind="MONTHLY"))[0],
        (await _fees(db, anna.id, kind="MONTHLY"))[0],
    ]

    # Due figli, un bonifico solo.
    proof = await club_service.upload_payment_proof(
        db, scope=scope, guardian_user_id=parent.id, fee_ids=[f.id for f in october],
        file_bytes=PNG, content_type="image/png", original_filename="bonifico.png",
    )

    assert proof.status == "ACCEPTED"
    # Anna è la seconda della famiglia: la sua mensilità ha lo sconto
    # famiglia (5 €).
    assert proof.amount_cents == 4000 + 2500
    for fee in october:
        await db.refresh(fee)
        assert fee.status == "PAID"
        assert fee.paid_via_proof_id == proof.id

    # La stessa quota non si paga due volte.
    with pytest.raises(club_service.ClubValidationError):
        await club_service.upload_payment_proof(
            db, scope=scope, guardian_user_id=parent.id, fee_ids=[october[0].id],
            file_bytes=PNG, content_type="image/png", original_filename="doppio.png",
        )

    await club_service.reject_proof(
        db, scope=scope, proof_id=proof.id, actor_user_id=admin.id, reason="Importo illeggibile",
    )
    for fee in october:
        await db.refresh(fee)
        assert fee.status == "DUE"
        assert fee.paid_via_proof_id is None
    # Le altre quote (le iscrizioni) non le aveva pagate: restano come sono.
    enrollment = (await _fees(db, luca.id, kind="ENROLLMENT"))[0]
    assert enrollment.status == "DUE"


async def test_a_parent_cannot_touch_another_family(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    mine = await _user(db, scope)
    other = await _user(db, scope, "altro")
    their_child = await _athlete(db, scope, other, birth_date=date(2016, 3, 3))
    their_fee = (await _fees(db, their_child.id, kind="MONTHLY"))[0]

    with pytest.raises(club_service.ClubNotFoundError):
        await club_service.get_owned_athlete(
            db, scope=scope, guardian_user_id=mine.id, athlete_id=their_child.id
        )
    with pytest.raises(club_service.ClubNotFoundError):
        await club_service.upload_payment_proof(
            db, scope=scope, guardian_user_id=mine.id, fee_ids=[their_fee.id],
            file_bytes=PNG, content_type="image/png", original_filename="furbo.png",
        )
    await db.refresh(their_fee)
    assert their_fee.status == "DUE"
    assert await club_service.list_family_athletes(
        db, scope=scope, guardian_user_id=mine.id
    ) == []


async def test_a_plan_chosen_by_hand_survives_the_new_season(db, scope):
    admin = await _user(db, scope, "admin")
    kids, _youth, everyone = await _plans(db, scope, admin)
    parent = await _user(db, scope)
    athlete = await _athlete(db, scope, parent, birth_date=date(2020, 5, 1))
    assert athlete.plan_id == kids.id

    athlete = await club_service.update_athlete(
        db, athlete=athlete, actor_user_id=admin.id, changes={"plan_id": everyone.id}, as_admin=True,
    )
    assert athlete.plan_locked is True

    await club_service.start_season(db, scope=scope, season=2027)
    await db.refresh(athlete)
    assert athlete.plan_id == everyone.id
    # Il genitore non può scegliersi il piano.
    athlete = await club_service.update_athlete(
        db, athlete=athlete, actor_user_id=parent.id, changes={"plan_id": kids.id, "first_name": "Luca Maria"},
        as_admin=False,
    )
    assert athlete.plan_id == everyone.id
    assert athlete.first_name == "Luca Maria"


async def test_only_one_self_athlete_per_account(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    await _athlete(db, scope, parent, birth_date=date(1985, 1, 1), is_self=True)

    with pytest.raises(club_service.ClubValidationError):
        await _athlete(db, scope, parent, birth_date=date(1985, 1, 1), is_self=True)
    count = (
        await db.execute(select(func.count()).where(ClubAthlete.guardian_user_id == parent.id))
    ).scalar_one()
    assert count == 1


async def test_waive_and_mark_paid_by_hand(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    athlete = await _athlete(db, scope, parent, birth_date=date(2016, 3, 3))
    monthly = (await _fees(db, athlete.id, kind="MONTHLY"))[0]
    enrollment = (await _fees(db, athlete.id, kind="ENROLLMENT"))[0]

    paid = await club_service.mark_fee_paid(
        db, scope=scope, fee_id=monthly.id, actor_user_id=admin.id, note="Contanti in palestra",
        method="CASH", cash_received_by_name="Segreteria",
    )
    waived = await club_service.waive_fee(
        db, scope=scope, fee_id=enrollment.id, actor_user_id=admin.id, reason="Fratello minore"
    )
    assert (paid.status, waived.status) == ("PAID", "WAIVED")

    reopened = await club_service.reopen_fee(
        db, scope=scope, fee_id=enrollment.id, actor_user_id=admin.id
    )
    assert reopened.status == "DUE"
    assert reopened.waive_reason is None
