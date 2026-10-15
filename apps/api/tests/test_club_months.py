"""Club: l'età federale a metà stagione, come si paga una mensilità, il
calendario dei mesi e la giustificazione per la scuola (docs/club-portal.md).

Le promesse: a gennaio chi entra nella fascia del gruppo dopo paga la
mensilità nuova (e il genitore lo sa), ma un mese già emesso non cambia;
ogni mensilità pagata dice come e, per i contanti, a chi; la giustificazione
è solo per chi è iscritto e il suo PDF sta nel bucket privato.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.core.storage import download_document
from app.domains.club import competitions as competitions_service
from app.domains.club import months as months_service
from app.domains.club import school_letters
from app.domains.club import service as club_service
from app.domains.club.models import ClubFee
from app.domains.notifications.models import Notification
from app.domains.rbac.models import Role, UserRole
from app.domains.users.models import User

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200


async def _user(db, scope, label="genitore", role: str | None = None) -> User:
    user = User(
        organization_id=scope.organization_id, club_id=scope.club_id,
        email=f"{label}-{uuid.uuid4().hex[:8]}@example.demo", password_hash=hash_password("x"),
    )
    db.add(user)
    await db.flush()
    if role:
        existing = (
            await db.execute(select(Role).where(Role.organization_id == scope.organization_id, Role.code == role))
        ).scalar_one_or_none()
        if existing is None:
            existing = Role(organization_id=scope.organization_id, code=role, name=role.title())
            db.add(existing)
            await db.flush()
        db.add(UserRole(user_id=user.id, organization_id=scope.organization_id, role_id=existing.id))
    await db.commit()
    await db.refresh(user)
    return user


async def _plans(db, scope, actor):
    kids = await club_service.create_plan(db, scope=scope, actor_user_id=actor.id, data={
        "name": "Bambini 4-7", "min_age": 4, "max_age": 7, "monthly_fee_cents": 3000, "due_day": 10,
    })
    youth = await club_service.create_plan(db, scope=scope, actor_user_id=actor.id, data={
        "name": "Ragazzi 8-13", "min_age": 8, "max_age": 13, "monthly_fee_cents": 4000, "due_day": 10,
    })
    return kids, youth


async def _athlete(db, scope, guardian, *, birth_date, today=date(2026, 10, 15), **kw):
    return await club_service.create_athlete(
        db, scope=scope, guardian_user_id=guardian.id, actor_user_id=guardian.id,
        first_name=kw.pop("first_name", "Luca"), last_name="Bianchi", birth_date=birth_date,
        sex=kw.pop("sex", "M"), today=today, **kw,
    )


async def _monthly(db, athlete_id, period) -> ClubFee:
    return (
        await db.execute(
            select(ClubFee).where(ClubFee.athlete_id == athlete_id, ClubFee.kind == "MONTHLY", ClubFee.period == period)
        )
    ).scalar_one()


async def test_in_january_the_federal_age_moves_the_athlete_to_the_next_group(db, scope):
    admin = await _user(db, scope, "admin")
    kids, youth = await _plans(db, scope, admin)
    parent = await _user(db, scope)
    # Nato a marzo 2019: 7 anni federali nel 2026, 8 nel 2027.
    athlete = await _athlete(db, scope, parent, birth_date=date(2019, 3, 3))
    assert athlete.plan_id == kids.id

    await club_service.generate_monthly_fees(db, scope=scope, period="2026-12", today=date(2026, 12, 1))
    assert (await _monthly(db, athlete.id, "2026-12")).amount_cents == 3000

    await club_service.generate_monthly_fees(db, scope=scope, period="2027-01", today=date(2027, 1, 1))
    january = await _monthly(db, athlete.id, "2027-01")
    assert january.amount_cents == 4000
    await db.refresh(athlete)
    assert athlete.plan_id == youth.id
    # La mensilità di dicembre era già emessa: non cambia.
    assert (await _monthly(db, athlete.id, "2026-12")).amount_cents == 3000
    note = (
        await db.execute(select(Notification).where(
            Notification.recipient_user_id == parent.id, Notification.type == "CLUB_PLAN_CHANGED"
        ))
    ).scalar_one()
    assert "Ragazzi 8-13" in note.title

    # Rigenerare un mese passato usa il gruppo di quell'anno, ma non
    # riporta indietro il piano dell'atleta.
    await club_service.generate_monthly_fees(db, scope=scope, period="2026-11", today=date(2027, 1, 2))
    assert (await _monthly(db, athlete.id, "2026-11")).amount_cents == 3000
    await db.refresh(athlete)
    assert athlete.plan_id == youth.id


async def test_a_plan_chosen_by_hand_does_not_move_in_january(db, scope):
    admin = await _user(db, scope, "admin")
    kids, _youth = await _plans(db, scope, admin)
    parent = await _user(db, scope)
    athlete = await _athlete(db, scope, parent, birth_date=date(2019, 3, 3))
    await club_service.update_athlete(
        db, athlete=athlete, actor_user_id=admin.id, changes={"plan_id": kids.id}, as_admin=True,
    )

    await club_service.generate_monthly_fees(db, scope=scope, period="2027-01", today=date(2027, 1, 1))
    assert (await _monthly(db, athlete.id, "2027-01")).amount_cents == 3000


async def test_cash_given_to_a_coach_pays_the_month_and_tells_the_coach(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    coach = await _user(db, scope, "treinador", role="INSTRUCTOR")
    parent = await _user(db, scope)
    athlete = await _athlete(db, scope, parent, birth_date=date(2016, 3, 3))
    october = await _monthly(db, athlete.id, "2026-10")

    receivers = await club_service.cash_receivers(db, scope=scope)
    assert [r["user_id"] for r in receivers] == [coach.id]

    proof = await club_service.upload_payment_proof(
        db, scope=scope, guardian_user_id=parent.id, fee_ids=[october.id], file_bytes=None, content_type=None,
        original_filename=None, method="CASH", cash_received_by_user_id=coach.id,
    )
    await db.refresh(october)
    assert (october.status, october.payment_method, october.cash_received_by_user_id) == ("PAID", "CASH", coach.id)
    assert proof.storage_key is None and proof.method == "CASH"
    assert (await db.execute(select(Notification).where(
        Notification.recipient_user_id == coach.id, Notification.type == "CLUB_CASH_DECLARED"
    ))).scalar_one()

    # "Non li ho ricevuti": la segreteria rifiuta, il mese torna da pagare
    # e non dice più contanti.
    await club_service.reject_proof(db, scope=scope, proof_id=proof.id, actor_user_id=admin.id, reason="Non ricevuti")
    await db.refresh(october)
    assert (october.status, october.payment_method, october.cash_received_by_name) == ("DUE", None, None)


async def test_cash_needs_someone_who_received_it(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    stranger = await _user(db, scope, "altro")
    parent = await _user(db, scope)
    athlete = await _athlete(db, scope, parent, birth_date=date(2016, 3, 3))
    october = await _monthly(db, athlete.id, "2026-10")

    with pytest.raises(club_service.ClubValidationError):
        await club_service.upload_payment_proof(
            db, scope=scope, guardian_user_id=parent.id, fee_ids=[october.id], file_bytes=None,
            content_type=None, original_filename=None, method="CASH",
        )
    # Un account del club che non è dello staff non può "ricevere" contanti.
    with pytest.raises(club_service.ClubValidationError):
        await club_service.mark_fee_paid(
            db, scope=scope, fee_id=october.id, actor_user_id=admin.id, note=None, method="CASH",
            cash_received_by_user_id=stranger.id,
        )
    # Un nome scritto a mano sì (il presidente, un allenatore senza account).
    fee = await club_service.mark_fee_paid(
        db, scope=scope, fee_id=october.id, actor_user_id=admin.id, note=None, method="CASH",
        cash_received_by_name="Presidente Matias",
    )
    assert (fee.payment_method, fee.cash_received_by_name) == ("CASH", "Presidente Matias")
    # Riaprirla cancella anche come era stata pagata.
    fee = await club_service.reopen_fee(db, scope=scope, fee_id=fee.id, actor_user_id=admin.id)
    assert (fee.status, fee.payment_method, fee.cash_received_by_name) == ("DUE", None, None)


async def test_a_bank_transfer_proof_records_the_method(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    athlete = await _athlete(db, scope, parent, birth_date=date(2016, 3, 3))
    october = await _monthly(db, athlete.id, "2026-10")
    await club_service.upload_payment_proof(
        db, scope=scope, guardian_user_id=parent.id, fee_ids=[october.id], file_bytes=PNG,
        content_type="image/png", original_filename="bonifico.png",
    )
    await db.refresh(october)
    assert october.payment_method == "BANK_TRANSFER"


async def test_the_season_calendar_shows_each_month(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    athlete = await _athlete(db, scope, parent, birth_date=date(2019, 3, 3), today=date(2026, 9, 5))
    await club_service.generate_monthly_fees(db, scope=scope, period="2026-10", today=date(2026, 10, 1))
    september = await _monthly(db, athlete.id, "2026-09")
    await club_service.mark_fee_paid(
        db, scope=scope, fee_id=september.id, actor_user_id=admin.id, note=None, method="CARD",
    )

    data = await months_service.season_months(db, athlete=athlete, season=2026, today=date(2026, 10, 20))
    by_period = {m["period"]: m for m in data["months"]}
    assert len(data["months"]) == 12
    assert by_period["2026-09"]["state"] == "PAID"
    assert by_period["2026-09"]["fee"]["payment_method"] == "CARD"
    # Scadeva il 10 ottobre: il 20 è in rosso.
    assert by_period["2026-10"]["state"] == "OVERDUE"
    # Novembre si pagherà con il gruppo di oggi; gennaio con quello dei
    # Ragazzi: il genitore lo vede prima.
    assert (by_period["2026-11"]["state"], by_period["2026-11"]["expected_cents"]) == ("UPCOMING", 3000)
    assert (by_period["2027-01"]["expected_cents"], by_period["2027-01"]["group_name"]) == (4000, "Ragazzi 8-13")
    assert by_period["2027-01"]["federal_age"] == 8
    assert by_period["2027-08"]["state"] == "NOT_BILLED"
    assert data["summary"]["paid_cents"] == 3000
    assert data["summary"]["overdue_cents"] == 3000


async def _competition(db, scope, admin):
    return await competitions_service.create_competition(db, scope=scope, actor_user_id=admin.id, data={
        "name": "Torneio de Portimão", "starts_on": date(2026, 11, 14), "ends_on": date(2026, 11, 15),
        "location": "Portimão", "registration_deadline": date(2026, 11, 1), "level": "REGIONAL", "fee_cents": 0,
        "requires_agonistic_certificate": False,
    })


async def test_the_school_letter_is_for_registered_athletes_and_stays_private(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    athlete = await _athlete(db, scope, parent, birth_date=date(2014, 4, 4), sex="F", first_name="Ana")
    comp = await _competition(db, scope, admin)
    entry = await competitions_service.register_entry(
        db, competition=comp, athlete=athlete, actor_user_id=parent.id, category=None, today=date(2026, 10, 20)
    )

    draft = await school_letters.draft(db, scope=scope, competition_id=comp.id, entry_id=entry.id, today=date(2026, 11, 2))
    # Portoghese di default, al femminile, con i dati dell'atleta e della gara.
    assert "a atleta Ana Bianchi" in draft["body_text"]
    assert "selecionada" in draft["body_text"]
    assert "Torneio de Portimão" in draft["body_text"]
    assert draft["generated_at"] is None

    letter = await school_letters.generate(
        db, scope=scope, competition_id=comp.id, entry_id=entry.id,
        body_text=draft["body_text"] + "\n\nTurma 7.º B", actor_user_id=admin.id,
    )
    first_key = letter.storage_key
    assert first_key.startswith(f"club-school-letters/{scope.club_id}/")
    assert download_document(storage_key=first_key).startswith(b"%PDF-")
    # Riaprendola, si riparte dal testo stampato, correzioni comprese.
    again = await school_letters.draft(db, scope=scope, competition_id=comp.id, entry_id=entry.id, today=date(2026, 11, 3))
    assert again["body_text"].endswith("Turma 7.º B")

    letter = await school_letters.generate(
        db, scope=scope, competition_id=comp.id, entry_id=entry.id, body_text=again["body_text"], actor_user_id=admin.id,
    )
    assert letter.storage_key != first_key

    await competitions_service.withdraw_entry(
        db, competition=comp, athlete=athlete, actor_user_id=parent.id, today=date(2026, 10, 25)
    )
    with pytest.raises(club_service.ClubValidationError):
        await school_letters.generate(
            db, scope=scope, competition_id=comp.id, entry_id=entry.id, body_text=again["body_text"],
            actor_user_id=admin.id,
        )


async def test_after_the_deadline_nobody_can_register(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    athlete = await _athlete(db, scope, parent, birth_date=date(2014, 4, 4))
    comp = await _competition(db, scope, admin)
    with pytest.raises(club_service.ClubValidationError, match="chiuse"):
        await competitions_service.register_entry(
            db, competition=comp, athlete=athlete, actor_user_id=parent.id, category=None, today=date(2026, 11, 2)
        )
