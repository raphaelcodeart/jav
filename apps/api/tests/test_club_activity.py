"""Club: gare e Jav Ranking, cinture, corsi e presenze, livelli e promemoria.

Le regole che contano: alla gara che lo chiede non si iscrive chi non ha un
certificato agonistico valido quel giorno; il ranking si somma dai risultati
(ex aequo compresi) e non si salva; una cintura si guadagna solo verso
l'alto; una presenza segnata due volte resta una; un promemoria parte una
volta sola.
"""

import uuid
from datetime import date, time

import pytest
from sqlalchemy import func, select

from app.domains.club import achievements
from app.domains.club import competitions as competitions_service
from app.domains.club import courses as courses_service
from app.domains.club import family as family_service
from app.domains.club import service as club_service
from app.domains.club import tasks as club_tasks
from app.domains.club.models import (
    ClubAttendance,
    ClubFee,
    ClubMedicalCertificate,
    ClubReminderSent,
)
from tests.test_club_fees import PNG, _athlete, _plans, _user

TODAY = date(2026, 10, 15)


async def _competition(db, scope, admin, **kw):
    data = {
        "name": kw.pop("name", "Trofeo d'autunno"),
        "starts_on": kw.pop("starts_on", date(2026, 11, 8)),
        "registration_deadline": kw.pop("registration_deadline", date(2026, 11, 1)),
        "level": kw.pop("level", "REGIONAL"),
        "fee_cents": kw.pop("fee_cents", 1500),
        "requires_agonistic_certificate": kw.pop("requires_agonistic_certificate", True),
        **kw,
    }
    return await competitions_service.create_competition(
        db, scope=scope, actor_user_id=admin.id, data=data
    )


async def _agonistic_certificate(db, athlete, parent, *, issued_on=date(2026, 9, 1), expires_on=date(2027, 8, 31)):
    return await club_service.upload_certificate(
        db, athlete=athlete, actor_user_id=parent.id, type_="AGONISTIC", issued_on=issued_on, expires_on=expires_on,
        file_bytes=PNG, content_type="image/png", original_filename="certificato.png",
    )


async def test_competition_entry_needs_a_valid_agonistic_certificate(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    athlete = await _athlete(db, scope, parent, birth_date=date(2014, 4, 4))
    comp = await _competition(db, scope, admin)

    ok, reason = await competitions_service.eligibility(db, competition=comp, athlete=athlete, today=TODAY)
    assert not ok and "certificato medico agonistico" in reason
    with pytest.raises(club_service.ClubValidationError):
        await competitions_service.register_entry(
            db, competition=comp, athlete=athlete, actor_user_id=parent.id, category="-46 kg", today=TODAY
        )

    # Un certificato che scade prima della gara non basta.
    await _agonistic_certificate(db, athlete, parent, issued_on=date(2025, 11, 1), expires_on=date(2026, 11, 1))
    ok, _ = await competitions_service.eligibility(db, competition=comp, athlete=athlete, today=TODAY)
    assert not ok

    await _agonistic_certificate(db, athlete, parent)
    entry = await competitions_service.register_entry(
        db, competition=comp, athlete=athlete, actor_user_id=parent.id, category="-46 kg", today=TODAY
    )
    assert entry.status == "REGISTERED"
    fee = (
        await db.execute(select(ClubFee).where(ClubFee.athlete_id == athlete.id, ClubFee.kind == "COMPETITION"))
    ).scalar_one()
    assert (fee.amount_cents, fee.status, fee.due_date) == (1500, "DUE", date(2026, 11, 1))


async def test_withdrawing_waives_the_unpaid_fee_and_registering_again_reopens_it(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    athlete = await _athlete(db, scope, parent, birth_date=date(2014, 4, 4))
    comp = await _competition(db, scope, admin, requires_agonistic_certificate=False)

    await competitions_service.register_entry(
        db, competition=comp, athlete=athlete, actor_user_id=parent.id, category=None, today=TODAY
    )
    await competitions_service.withdraw_entry(db, competition=comp, athlete=athlete, actor_user_id=parent.id, today=TODAY)
    fees = (await db.execute(select(ClubFee).where(ClubFee.competition_id == comp.id))).scalars().all()
    assert [f.status for f in fees] == ["WAIVED"]

    entry = await competitions_service.register_entry(
        db, competition=comp, athlete=athlete, actor_user_id=parent.id, category="-50 kg", today=TODAY
    )
    assert entry.category == "-50 kg"
    fees = (await db.execute(select(ClubFee).where(ClubFee.competition_id == comp.id))).scalars().all()
    assert [f.status for f in fees] == ["DUE"]
    with pytest.raises(club_service.ClubValidationError):
        await competitions_service.register_entry(
            db, competition=comp, athlete=athlete, actor_user_id=parent.id, category=None, today=TODAY
        )
    # Dopo la scadenza non ci si iscrive e non ci si ritira più dal portale.
    with pytest.raises(club_service.ClubValidationError):
        await competitions_service.withdraw_entry(
            db, competition=comp, athlete=athlete, actor_user_id=parent.id, today=date(2026, 11, 2)
        )


async def test_ranking_sums_the_level_points_table_and_ties(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    other_parent = await _user(db, scope, "altro")
    a = await _athlete(db, scope, parent, birth_date=date(2014, 4, 4), first_name="Aldo")
    b = await _athlete(db, scope, other_parent, birth_date=date(2014, 6, 6), first_name="Bruno")
    c = await _athlete(db, scope, other_parent, birth_date=date(2014, 7, 7), first_name="Carlo")
    regional = await _competition(db, scope, admin, requires_agonistic_certificate=False, fee_cents=0)
    club = await _competition(
        db, scope, admin, name="Gara sociale", level="CLUB", requires_agonistic_certificate=False,
        fee_cents=0, starts_on=date(2026, 12, 13), registration_deadline=date(2026, 12, 10),
    )
    entries = {}
    for comp in (regional, club):
        for athlete in (a, b, c):
            entries[(comp.id, athlete.id)] = await competitions_service.register_entry(
                db, competition=comp, athlete=athlete, actor_user_id=athlete.guardian_user_id, category=None,
                today=TODAY,
            )

    # Regionale (5/3/2/1): Aldo 1° = 5, Bruno 3° = 2, Carlo partecipa = 1.
    await competitions_service.record_results(
        db, scope=scope, competition_id=regional.id, actor_user_id=admin.id,
        results=[(entries[(regional.id, a.id)].id, 1), (entries[(regional.id, b.id)].id, 3),
                 (entries[(regional.id, c.id)].id, 0)],
    )
    # Club (3/2/1/1): Bruno 1° = 3, Carlo 1° (ex aequo nella sua categoria) = 3.
    await competitions_service.record_results(
        db, scope=scope, competition_id=club.id, actor_user_id=admin.id,
        results=[(entries[(club.id, b.id)].id, 1), (entries[(club.id, c.id)].id, 1),
                 (entries[(club.id, a.id)].id, None)],
    )

    rows = await competitions_service.ranking(
        db, scope=scope, season=2026, viewer_user_id=parent.id
    )
    assert [(r["display_name"], r["points"], r["position"]) for r in rows] == [
        ("Aldo B.", 5, 1),
        ("Bruno B.", 5, 1),
        ("Carlo B.", 4, 3),
    ]
    assert [r["is_mine"] for r in rows] == [True, False, False]
    # Correggere un risultato corregge la classifica: niente da ricalcolare.
    await competitions_service.record_results(
        db, scope=scope, competition_id=regional.id, actor_user_id=admin.id,
        results=[(entries[(regional.id, a.id)].id, 2)],
    )
    rows = await competitions_service.ranking(db, scope=scope, season=2026)
    assert rows[0]["display_name"] == "Bruno B."
    assert await competitions_service.ranking(db, scope=scope, season=2026, sex="F") == []
    banded = await competitions_service.ranking(
        db, scope=scope, season=2026, age_band="GRUPO_2"
    )
    assert len(banded) == 3  # 12 anni federali nel 2026: Grupo 2


async def test_belts_only_go_up_and_the_current_one_is_the_highest(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    athlete = await _athlete(db, scope, parent, birth_date=date(2014, 4, 4))

    yellow = await club_service.award_belt(db, athlete=athlete, grade="YELLOW", awarded_on=date(2027, 1, 20), actor_user_id=admin.id)
    # Inserito dopo ma datato prima: la cintura attuale resta la più alta.
    await club_service.award_belt(
        db, athlete=athlete, grade="BLUE", awarded_on=date(2026, 12, 1), actor_user_id=admin.id
    )
    assert (await club_service.current_belts(db, athlete_ids=[athlete.id]))[athlete.id] == "BLUE"
    with pytest.raises(club_service.ClubValidationError):
        await club_service.award_belt(db, athlete=athlete, grade="ORANGE", awarded_on=TODAY, actor_user_id=admin.id)

    await club_service.delete_belt(db, scope=scope, belt_id=yellow.id, actor_user_id=admin.id)
    history = [g.grade for g in await club_service.belt_history(db, athlete_id=athlete.id)]
    assert history == ["WHITE", "BLUE"]


async def test_attendance_is_one_row_per_day_and_feeds_the_level(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    instructor = await _user(db, scope, "maestro")
    athlete = await _athlete(db, scope, parent, birth_date=date(2014, 4, 4))
    course = await courses_service.create_course(
        db, scope=scope, actor_user_id=admin.id,
        data={"name": "Ragazzi", "instructor_user_id": instructor.id, "min_age": 8, "max_age": 13},
    )
    await courses_service.add_slot(
        db, scope=scope, course_id=course.id, actor_user_id=admin.id,
        weekday=1, starts_at=time(17, 30), ends_at=time(18, 30), room="Tatami 1",
    )
    await courses_service.enrol(db, course=course, athlete=athlete, actor_user_id=parent.id)
    await courses_service.enrol(db, course=course, athlete=athlete, actor_user_id=parent.id)  # idempotente

    day = date(2026, 10, 13)
    roster = await courses_service.roster(db, course=course, on=day)
    assert [(a.id, present) for a, present, _note in roster] == [(athlete.id, None)]

    await courses_service.mark_attendance(db, course=course, athlete=athlete, on=day, present=False, actor_user_id=instructor.id)
    await courses_service.mark_attendance(db, course=course, athlete=athlete, on=day, present=True, actor_user_id=instructor.id)
    rows = (await db.execute(select(func.count()).where(ClubAttendance.athlete_id == athlete.id))).scalar_one()
    assert rows == 1
    assert (await courses_service.attendance_counts(db, athlete_ids=[athlete.id]))[athlete.id] == 1

    card = (await family_service.athlete_cards(db, athletes=[athlete], today=TODAY))[0]
    assert card["attendances"] == 1
    assert card["xp"] == achievements.XP_PER_ATTENDANCE
    assert card["achievements_earned"] == 1  # Primo allenamento


def test_levels_grow_quadratically():
    assert [achievements.level_for(xp) for xp in (0, 99, 100, 299, 300, 600, 1000)] == [1, 1, 2, 2, 3, 4, 5]
    exp = achievements.experience(attendances=15, belts_earned=1, ranking_points=0)
    assert exp["xp"] == 300 and exp["level"] == 3 and exp["progress"] == 0


async def test_family_summary_adds_up_what_is_due(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    await _athlete(db, scope, parent, birth_date=date(2014, 4, 4))
    await _athlete(db, scope, parent, birth_date=date(2020, 4, 4), first_name="Anna", sex="F")

    summary = await family_service.family_summary(
        db, scope=scope, guardian_user_id=parent.id, today=TODAY
    )
    assert summary["season_label"] == "2026/2027"
    assert len(summary["athletes"]) == 2
    # Iscrizione 3/12 di 25 + ottobre 40 (Luca); iscrizione 3/12 di 25 +
    # ottobre 30 meno 5 di sconto famiglia (Anna); quota socio del genitore,
    # 3/12 di 60.
    assert summary["due_cents"] == 625 + 4000 + 625 + 2500 + 1500
    assert {a["certificate"]["status"] for a in summary["athletes"]} == {"MISSING"}


async def test_reminders_go_out_once(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    athlete = await _athlete(db, scope, parent, birth_date=date(2014, 4, 4))
    await _agonistic_certificate(db, athlete, parent, issued_on=date(2025, 11, 1), expires_on=date(2026, 11, 1))

    # Il 20 ottobre: ottobre e iscrizione scaduti il 10, certificato a 12 giorni.
    sent = await club_tasks.send_reminders(db, scope=scope, today=date(2026, 10, 20))
    again = await club_tasks.send_reminders(db, scope=scope, today=date(2026, 10, 20))

    # Iscrizione, ottobre e quota socio scadute, più il certificato.
    assert sent == 4
    assert again == 0
    stages = set(
        (await db.execute(select(ClubReminderSent.kind, ClubReminderSent.stage).where(
            ClubReminderSent.organization_id == scope.organization_id
        ))).all()
    )
    assert stages == {("FEE_OVERDUE", "overdue"), ("CERTIFICATE", "30")}
    # A sette giorni dalla scadenza parte il secondo avviso, una volta.
    assert await club_tasks.send_reminders(db, scope=scope, today=date(2026, 10, 26)) == 1
    certs = (await db.execute(select(func.count()).where(ClubMedicalCertificate.athlete_id == athlete.id))).scalar_one()
    assert certs == 1


async def test_expired_registrations_close_by_themselves(db, scope):
    admin = await _user(db, scope, "admin")
    comp = await _competition(db, scope, admin)
    assert await club_tasks.close_expired_competitions(db, scope=scope, today=date(2026, 11, 1)) == 0
    assert await club_tasks.close_expired_competitions(db, scope=scope, today=date(2026, 11, 2)) == 1
    await db.refresh(comp)
    assert comp.status == "CLOSED"


async def test_unknown_ids_are_not_found(db, scope):
    with pytest.raises(club_service.ClubNotFoundError):
        await club_service.get_athlete(db, scope=scope, athlete_id=uuid.uuid4())
