"""«Segna pagato» con la foto della prova, e la prova caricata dall'atleta
maggiorenne (club_service.staff_record_payment, athlete_router).

Le promesse: la segreteria chiude più quote della stessa famiglia con una
ricevuta sola, con o senza foto, e mai quote di due famiglie insieme;
l'atleta paga le sue quote dai 18 anni federali, non prima, e mai quelle di
un altro; la prova risulta caricata da chi l'ha caricata.
"""

from datetime import date

import pytest
from sqlalchemy import select

from app.domains.club import athlete_access
from app.domains.club import service as club_service
from app.domains.club.models import ClubFee, ClubPaymentProof
from app.domains.club.service import ClubValidationError
from tests.test_club_fees import _athlete, _plans, _user

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


async def _due(db, athlete_id):
    return list((await db.execute(select(ClubFee).where(ClubFee.athlete_id == athlete_id, ClubFee.status == "DUE"))).scalars())


async def test_staff_marks_paid_with_a_photo_and_one_receipt(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    other = await _user(db, scope, "altro")
    a = await _athlete(db, scope, parent, birth_date=date(2016, 3, 3))
    b = await _athlete(db, scope, parent, birth_date=date(2018, 3, 3), first_name="Sara")
    c = await _athlete(db, scope, other, birth_date=date(2015, 3, 3), first_name="Rui")
    fees = (await _due(db, a.id))[:1] + (await _due(db, b.id))[:1]

    with pytest.raises(ClubValidationError):
        await club_service.staff_record_payment(db, scope=scope, actor_user_id=admin.id, method="MBWAY",
                                                fee_ids=[fees[0].id, (await _due(db, c.id))[0].id])
    proof = await club_service.staff_record_payment(
        db, scope=scope, actor_user_id=admin.id, method="MBWAY", fee_ids=[f.id for f in fees],
        file_bytes=PNG, content_type="image/png", original_filename="mbway.png",
    )
    assert proof.storage_key and proof.uploaded_by_user_id == admin.id and proof.receipt_number
    for f in fees:
        await db.refresh(f)
        assert (f.status, f.payment_method, f.paid_via_proof_id) == ("PAID", "MBWAY", proof.id)
    with pytest.raises(ClubValidationError):
        await club_service.staff_record_payment(db, scope=scope, actor_user_id=admin.id, method="MBWAY", fee_ids=[fees[0].id])
    # Senza foto si può, anche in contanti con chi li ha presi.
    cash = await club_service.staff_record_payment(
        db, scope=scope, actor_user_id=admin.id, method="CASH", fee_ids=[(await _due(db, c.id))[0].id],
        cash_received_by_name="Treinador Rui",
    )
    assert cash.storage_key is None and cash.cash_received_by_name == "Treinador Rui"


async def test_an_adult_athlete_pays_his_own_fees(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    adult = await _athlete(db, scope, parent, birth_date=date(2007, 3, 3), first_name="Tiago")
    kid = await _athlete(db, scope, parent, birth_date=date(2012, 3, 3), first_name="Rita")
    login = await _user(db, scope, "tiago")
    adult.user_id = login.id
    kid_login = await _user(db, scope, "rita")
    kid.user_id = kid_login.id
    await db.commit()
    today = date(2026, 10, 16)
    assert (await athlete_access.area(db, athlete=adult, viewer_user_id=login.id, today=today))["can_pay"] is True
    assert (await athlete_access.area(db, athlete=kid, viewer_user_id=kid_login.id, today=today))["can_pay"] is False
    assert (await athlete_access.area(db, athlete=kid, viewer_user_id=parent.id, today=today))["can_pay"] is True

    fee = (await _due(db, adult.id))[0]
    proof = await club_service.upload_payment_proof(
        db, scope=scope, guardian_user_id=parent.id, fee_ids=[fee.id], file_bytes=PNG, content_type="image/png",
        original_filename="bonifico.png", method="BANK_TRANSFER", uploaded_by_user_id=login.id,
    )
    await db.refresh(fee)
    assert proof.uploaded_by_user_id == login.id and fee.paid_by_user_id == login.id and fee.status == "PAID"
    assert (await db.get(ClubPaymentProof, proof.id)).storage_key
