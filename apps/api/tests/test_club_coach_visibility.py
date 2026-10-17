"""Che cosa vede un treinador (courses.visible_course_filter).

Le promesse: un treinador senza corsi assegnati vede tutti i corsi del club,
le loro lezioni e i loro atleti (e quelli che non sono in nessun corso); la
segreteria lo esclude da un corso e quel corso, con gli atleti che stanno
solo lì, per lui non esiste più; chi insegna il corso lo vede comunque; la
segreteria vede sempre tutto; la quota del treinador sui corsi resta del
titolare: vedere un corso non vuol dire guadagnarci.
"""

from datetime import date, datetime, time

import pytest
from sqlalchemy import select

from app.domains.audit.models import AuditLog
from app.domains.club import coach, jav_courses, lessons
from app.domains.club import courses as courses_service
from app.domains.club import service as club_service
from tests.test_club_fees import _athlete, _plans, _user

TODAY = date(2026, 10, 17)


async def _course(db, scope, admin, name, athletes, instructor=None):
    data = {"name": name}
    if instructor is not None:
        data["instructor_user_id"] = instructor.id
    course = await courses_service.create_course(db, scope=scope, actor_user_id=admin.id, data=data)
    # Sabato 17 ottobre 2026: weekday 5.
    await courses_service.add_slot(db, scope=scope, course_id=course.id, actor_user_id=admin.id,
                                   weekday=5, starts_at=time(10, 0), ends_at=time(11, 0), room=None)
    for athlete in athletes:
        await courses_service.enrol(db, course=course, athlete=athlete, actor_user_id=admin.id)
    return course


async def _club(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    kids = {
        name: await _athlete(db, scope, parent, birth_date=birth, first_name=name, sex=sex)
        for name, birth, sex in (
            ("Luca", date(2016, 4, 4), "M"), ("Sara", date(2012, 2, 2), "F"), ("Eva", date(2010, 3, 3), "F"),
        )
    }
    g1 = await _course(db, scope, admin, "Grupo 1", [kids["Luca"]])
    g2 = await _course(db, scope, admin, "Grupo 2", [kids["Sara"], kids["Luca"]])
    return admin, kids, g1, g2


async def test_a_coach_without_courses_sees_the_whole_club(db, scope):
    _admin, kids, g1, g2 = await _club(db, scope)
    coach_user = await _user(db, scope, "treinador")
    me = {"scope": scope, "user_id": coach_user.id, "manager": False}

    assert {c.id for c in await coach.my_courses(db, **me)} == {g1.id, g2.id}
    names = {a["first_name"] for a in await coach.my_athletes(db, **me, today=TODAY)}
    # Eva non è in nessun corso: la vede lo stesso (come la segreteria).
    assert names == {"Luca", "Sara", "Eva"}
    sheet = await coach.athlete_sheet(db, **me, athlete_id=kids["Sara"].id, today=TODAY)
    assert sheet["courses"] == [{"id": g2.id, "name": "Grupo 2"}]
    await coach.athlete_sheet(db, **me, athlete_id=kids["Eva"].id, today=TODAY)

    day = await lessons.lessons(db, scope=scope, start=TODAY, end=TODAY, teacher_user_id=coach_user.id,
                                now=datetime(2026, 10, 17, 9, 0))
    assert {lesson["course_name"] for lesson in day} == {"Grupo 1", "Grupo 2"}
    assert not any(lesson["mine"] for lesson in day)
    home = await coach.home(db, **me, now=datetime(2026, 10, 17, 9, 0))
    assert home["courses"] == 2 and len(home["lessons_today"]) == 2
    note = await coach.add_lesson_note(db, **me, course_id=g1.id, lesson_date=TODAY, today=TODAY,
                                       data={"title": "Ukemi"})
    assert note["course_id"] == g1.id


async def test_the_secretary_hides_a_course_from_one_coach(db, scope):
    admin, kids, g1, g2 = await _club(db, scope)
    hidden = await _user(db, scope, "treinador")
    other = await _user(db, scope, "altro")
    stays = await courses_service.set_coach_exclusions(
        db, scope=scope, course_id=g2.id, user_ids=[hidden.id], actor_user_id=admin.id,
    )
    assert stays == [hidden.id]
    me = {"scope": scope, "user_id": hidden.id, "manager": False}

    assert [c.id for c in await coach.my_courses(db, **me)] == [g1.id]
    # Sara sta solo nel Grupo 2: per lui non esiste. Luca è anche nel Grupo 1.
    names = {a["first_name"] for a in await coach.my_athletes(db, **me, today=TODAY)}
    assert names == {"Luca", "Eva"}
    with pytest.raises(club_service.ClubNotFoundError):
        await coach.athlete_sheet(db, **me, athlete_id=kids["Sara"].id, today=TODAY)
    luca = await coach.athlete_sheet(db, **me, athlete_id=kids["Luca"].id, today=TODAY)
    assert luca["courses"] == [{"id": g1.id, "name": "Grupo 1"}]
    with pytest.raises(club_service.ClubNotFoundError):
        await coach.add_lesson_note(db, **me, course_id=g2.id, lesson_date=TODAY, today=TODAY, data={"title": "x"})
    day = await lessons.lessons(db, scope=scope, start=TODAY, end=TODAY, teacher_user_id=hidden.id,
                                now=datetime(2026, 10, 17, 9, 0))
    assert [lesson["course_name"] for lesson in day] == ["Grupo 1"]
    assert not await courses_service.can_see(db, course=g2, user_id=hidden.id)

    # Gli altri treinador e la segreteria non cambiano.
    assert {c.id for c in await coach.my_courses(db, scope=scope, user_id=other.id, manager=False)} == {g1.id, g2.id}
    secretary = {"scope": scope, "user_id": admin.id, "manager": True}
    assert {a["first_name"] for a in await coach.my_athletes(db, **secretary, today=TODAY)} == {"Luca", "Sara", "Eva"}

    # Chi insegna il corso lo vede anche se escluso per sbaglio, ed è «suo».
    await courses_service.update_course(db, scope=scope, course_id=g2.id, actor_user_id=admin.id,
                                        changes={"instructor_user_id": hidden.id})
    mine = await coach.my_courses(db, **me)
    assert [c.id for c in mine] == [g2.id, g1.id]  # i suoi per primi
    day = await lessons.lessons(db, scope=scope, start=TODAY, end=TODAY, teacher_user_id=hidden.id,
                                now=datetime(2026, 10, 17, 9, 0))
    assert {lesson["course_name"]: lesson["mine"] for lesson in day} == {"Grupo 1": False, "Grupo 2": True}

    # Togliere l'esclusione: si torna a vedere tutto; resta nell'audit.
    assert await courses_service.set_coach_exclusions(
        db, scope=scope, course_id=g2.id, user_ids=[], actor_user_id=admin.id,
    ) == []
    actions = list((await db.execute(
        select(AuditLog.action).where(AuditLog.entity_id == str(g2.id), AuditLog.action == "club.course_coach_exclusions_set")
    )).scalars())
    assert len(actions) == 2


async def test_exclusions_only_for_people_of_the_club(db, scope):
    from app.domains.club.models import Club
    from app.domains.club.scope import ClubScope

    admin, _kids, g1, _g2 = await _club(db, scope)
    other_club = Club(organization_id=scope.organization_id, name="Altro", slug="altro-club-vis", settings={})
    db.add(other_club)
    await db.commit()
    stranger = await _user(db, ClubScope(organization_id=scope.organization_id, club_id=other_club.id), "fuori")
    with pytest.raises(club_service.ClubValidationError):
        await courses_service.set_coach_exclusions(
            db, scope=scope, course_id=g1.id, user_ids=[stranger.id], actor_user_id=admin.id,
        )


async def test_seeing_a_course_does_not_earn_its_share(db, organization_id):
    """La quota del treinador resta del titolare: un collega che vede il corso
    (e ne segna le presenze) non guadagna niente."""
    from tests.test_jav_courses import _course as jav_course
    from tests.test_jav_courses import _unit

    unit_scope, actor = await _unit(db, organization_id)
    owner = await _user(db, unit_scope, "treinador")
    colleague = await _user(db, unit_scope, "altro")
    course = await jav_course(db, unit_scope, actor, name="Judo Luz", coach=owner)
    assert await courses_service.can_see(db, course=course, user_id=colleague.id)
    assert (await jav_courses.coach_earnings(db, scope=unit_scope, user_id=colleague.id, year=2026))["rows"] == []


async def test_the_admin_routes_and_the_coach_course_list(db, scope, monkeypatch):
    from tests.test_club_api import _client

    admin, _kids, g1, g2 = await _club(db, scope)
    coach_user = await _user(db, scope, "treinador")
    app, client = await _client(db, monkeypatch, user=admin, scope=scope, granted={"club.manage", "club.instruct"})
    try:
        async with client:
            put = await client.put(f"/club/admin/courses/{g1.id}/coach-exclusions", json={"user_ids": [str(coach_user.id)]})
            assert put.status_code == 200, put.text
            assert put.json() == [str(coach_user.id)]
            got = await client.get(f"/club/admin/courses/{g1.id}/coach-exclusions")
            assert got.json() == [str(coach_user.id)]
            listed = {c["id"]: c for c in (await client.get("/club/admin/courses")).json()}
            assert listed[str(g1.id)]["excluded_coach_ids"] == [str(coach_user.id)]
            assert listed[str(g2.id)]["excluded_coach_ids"] == []
    finally:
        app.dependency_overrides.clear()

    app, client = await _client(db, monkeypatch, user=coach_user, scope=scope, granted={"club.instruct"})
    try:
        async with client:
            assert (await client.put(f"/club/admin/courses/{g1.id}/coach-exclusions", json={"user_ids": []})).status_code == 403
            courses = (await client.get("/club/staff/courses")).json()
            assert [c["name"] for c in courses] == ["Grupo 2"]
            assert (await client.get(f"/club/staff/courses/{g1.id}/roster")).status_code == 404
            assert (await client.get(f"/club/staff/courses/{g2.id}/roster")).status_code == 200
    finally:
        app.dependency_overrides.clear()
