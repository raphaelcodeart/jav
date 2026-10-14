"""Le persone del club, il calendario e le presenze, il cartellino, la taxa
de falta e gli investimenti.

Le promesse: ognuno compare una volta con i suoi tipi; treinador solo chi ha
un account da istruttore; l'adjunto vede i corsi in cui insegna; il genitore
segna solo oggi e non cancella ciò che ha segnato lo staff; un turno aperto
alla volta; la taxa de falta si propone solo con presenze segnate e si
applica dal netto, senza dimezzare due volte; un investimento non si
registra due volte per un doppio clic.
"""

from datetime import date, datetime, time, timedelta

import pytest

from app.domains.club import absence as absence_service
from app.domains.club import courses as courses_service
from app.domains.club import lessons as lessons_service
from app.domains.club import people as people_service
from app.domains.club import service as club_service
from app.domains.club import workclock
from app.domains.rbac.models import Role, UserRole
from app.domains.wallets import service as wallets_service
from tests.test_club_fees import _athlete, _fees, _plans, _user

MONDAY = date(2026, 10, 12)


async def _role(db, scope, user, code):
    role = Role(organization_id=scope.organization_id, code=code, name=code.title())
    db.add(role)
    await db.flush()
    db.add(UserRole(user_id=user.id, organization_id=scope.organization_id, role_id=role.id))
    await db.commit()


async def _course_with_monday_slot(db, scope, admin, instructor):
    course = await courses_service.create_course(
        db, scope=scope, actor_user_id=admin.id, data={"name": "Judo 8-13", "instructor_user_id": instructor.id}
    )
    await courses_service.add_slot(
        db, scope=scope, course_id=course.id, actor_user_id=admin.id, weekday=0,
        starts_at=time(18, 0), ends_at=time(19, 0), room=None,
    )
    return course


async def test_everyone_once_with_their_kinds(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope, "genitore")
    child = await _athlete(db, scope, parent, birth_date=date(2014, 4, 4))
    coach = await _user(db, scope, "treinador")
    await _role(db, scope, coach, "INSTRUCTOR")
    secretary = await _user(db, scope, "segreteria")
    await _role(db, scope, secretary, "SECRETARY")
    await _role(db, scope, parent, "CUSTOMER")

    with pytest.raises(club_service.ClubValidationError):
        await people_service.set_function(db, scope=scope, actor_user_id=admin.id, function="COACH", user_id=parent.id)
    await people_service.set_function(db, scope=scope, actor_user_id=admin.id, function="ASSISTANT_COACH", user_id=coach.id)
    await people_service.set_function(db, scope=scope, actor_user_id=admin.id, function="MONITOR", athlete_id=child.id)

    rows = {r["name"].split()[0] if r["kind"] == "ATHLETE" else r["email"]: r for r in await people_service.list_people(db, scope=scope)}
    assert rows["Luca"]["kinds"] == ["ATHLETE", "MONITOR"]
    assert rows[parent.email]["kinds"] == ["PARENT"]
    assert rows[parent.email]["due_cents"] > 0  # i debiti della famiglia
    assert rows[coach.email]["kinds"] == ["ASSISTANT_COACH"]
    assert rows[secretary.email]["kinds"] == ["SECRETARY"]


async def test_an_investment_goes_to_the_family_wallet_once(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    child = await _athlete(db, scope, parent, birth_date=date(2014, 4, 4))

    await people_service.invest(db, scope=scope, athlete_id=child.id, amount_cents=2000, note="Borsa di studio",
                                actor_user_id=admin.id, on=MONDAY)
    await people_service.invest(db, scope=scope, athlete_id=child.id, amount_cents=2000, note="Borsa di studio",
                                actor_user_id=admin.id, on=MONDAY)
    wallet = await wallets_service.get_wallet_by_user_id(db, organization_id=scope.organization_id, user_id=parent.id)
    assert wallet.balance_cents == 2000
    card = await people_service.person_card(db, scope=scope, athlete_id=child.id)
    assert card["totals"]["invested_cents"] == 2000
    assert card["investments"][0]["athlete_name"] == "Luca Bianchi"
    assert card["debts"]  # iscrizione e mensilità


async def test_the_assistant_sees_the_lesson_and_the_current_one_is_chosen(db, scope):
    admin = await _user(db, scope, "admin")
    coach = await _user(db, scope, "treinador")
    assistant = await _user(db, scope, "adjunto")
    course = await _course_with_monday_slot(db, scope, admin, coach)
    await courses_service.set_course_staff(db, scope=scope, course_id=course.id, user_ids=[assistant.id], actor_user_id=admin.id)

    week = await lessons_service.lessons(
        db, scope=scope, start=MONDAY, end=MONDAY + timedelta(days=6), teacher_user_id=assistant.id,
        now=datetime.combine(MONDAY, time(18, 20)),
    )
    assert [(lesson["date"], lesson["current"]) for lesson in week] == [(MONDAY, True)]
    assert await courses_service.teaches(db, course=course, user_id=assistant.id)


async def test_a_parent_marks_only_today_and_cannot_undo_the_coach(db, scope, monkeypatch):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    coach = await _user(db, scope, "treinador")
    course = await _course_with_monday_slot(db, scope, admin, coach)
    parent = await _user(db, scope)
    child = await _athlete(db, scope, parent, birth_date=date(2014, 4, 4))
    await courses_service.enrol(db, course=course, athlete=child, actor_user_id=parent.id)

    async def _monday(*args, **kwargs):
        return datetime.combine(MONDAY, time(18, 5))

    monkeypatch.setattr(lessons_service, "club_now", _monday)
    today = await lessons_service.family_today(db, scope=scope, guardian_user_id=parent.id)
    assert [(r["course_name"], r["present"]) for r in today] == [("Judo 8-13", None)]
    await lessons_service.family_mark(db, scope=scope, guardian_user_id=parent.id, athlete_id=child.id,
                                      course_id=course.id, present=True, note="Arriva alle 18:15")
    log = await lessons_service.day_log(db, scope=scope, on=MONDAY)
    assert [(r["athlete_name"], r["note"], r["recorded_by_kind"]) for r in log] == [("Luca Bianchi", "Arriva alle 18:15", "FAMILY")]

    # Lo staff conferma: il genitore non la toglie più.
    await courses_service.mark_attendance(db, course=course, athlete=child, on=MONDAY, present=True, actor_user_id=coach.id)
    with pytest.raises(club_service.ClubValidationError):
        await lessons_service.family_mark(db, scope=scope, guardian_user_id=parent.id, athlete_id=child.id,
                                          course_id=course.id, present=False, note=None)
    # Un altro giorno: nessuna lezione da segnare per il genitore.
    with pytest.raises(club_service.ClubNotFoundError):
        await lessons_service.family_mark(db, scope=scope, guardian_user_id=parent.id, athlete_id=child.id,
                                          course_id=course.id, present=True, note=None, today=MONDAY + timedelta(days=1))


async def test_one_open_shift_at_a_time(db, scope):
    coach = await _user(db, scope, "treinador")
    status = await workclock.clock_in(db, scope=scope, user_id=coach.id, note=None)
    assert status["open_session"] is not None
    with pytest.raises(club_service.ClubValidationError):
        await workclock.clock_in(db, scope=scope, user_id=coach.id, note=None)
    status = await workclock.clock_out(db, scope=scope, user_id=coach.id, note="Lezione serale")
    assert status["open_session"] is None
    hours = await workclock.hours_by_staff(db, scope=scope, month=datetime.now().strftime("%Y-%m"))
    assert [h["user_id"] for h in hours] == [coach.id]


async def test_absence_fee_is_suggested_from_marks_and_applied_from_the_net(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    coach = await _user(db, scope, "treinador")
    course = await _course_with_monday_slot(db, scope, admin, coach)
    parent = await _user(db, scope)
    luca = await _athlete(db, scope, parent, birth_date=date(2016, 3, 3))
    anna = await _athlete(db, scope, parent, birth_date=date(2016, 5, 5), first_name="Anna", sex="F")
    for athlete in (luca, anna):
        await courses_service.enrol(db, course=course, athlete=athlete, actor_user_id=parent.id)
    # Ottobre: tre lezioni fatte; Anna c'era a una sola, Luca a nessuna.
    for day in (date(2026, 10, 5), date(2026, 10, 12), date(2026, 10, 13)):
        await courses_service.mark_attendance(db, course=course, athlete=luca, on=day, present=False, actor_user_id=coach.id)
    await courses_service.mark_attendance(db, course=course, athlete=anna, on=date(2026, 10, 5), present=True, actor_user_id=coach.id)

    rows = {r["athlete_name"]: r for r in await absence_service.month_overview(db, scope=scope, period="2026-10")}
    assert (rows["Anna Bianchi"]["lessons_held"], rows["Anna Bianchi"]["suggestion"]) == (3, "HALF")
    assert rows["Luca Bianchi"]["suggestion"] == "FULL"

    october = (await _fees(db, anna.id, kind="MONTHLY"))[0]
    net = october.amount_cents
    fee = await absence_service.apply(db, scope=scope, fee_id=october.id, adjustment="HALF", actor_user_id=admin.id)
    fee = await absence_service.apply(db, scope=scope, fee_id=october.id, adjustment="HALF", actor_user_id=admin.id)
    assert fee.amount_cents == net // 2
    fee = await absence_service.apply(db, scope=scope, fee_id=october.id, adjustment=None, actor_user_id=admin.id)
    assert fee.amount_cents == net

    luca_october = (await _fees(db, luca.id, kind="MONTHLY"))[0]
    fee = await absence_service.apply(db, scope=scope, fee_id=luca_october.id, adjustment="FULL", actor_user_id=admin.id)
    assert (fee.amount_cents, fee.status) == (0, "WAIVED")
