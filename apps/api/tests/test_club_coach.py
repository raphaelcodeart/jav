"""L'area del treinador (club/coach.py, club/workclock.py, club/news.py).

Le promesse: un treinador corregge, toglie e aggiunge solo i suoi turni,
senza futuro, senza sovrapposizioni, solo nei mesi ancora aperti, e ogni
modifica resta nell'audit e si vede dalla segreteria; le note delle lezioni e
degli atleti le vedono solo i treinadores di quei corsi e la segreteria (mai
un altro club, mai un altro treinador); un treinador scrive sulla bacheca
solo per i soci, senza fissare in cima, e corregge solo i suoi post.
"""

from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy import select

from app.domains.audit.models import AuditLog
from app.domains.club import coach, news, workclock
from app.domains.club import courses as courses_service
from app.domains.club import service as club_service
from app.domains.club.models import Club, ClubWorkSession
from app.domains.club.scope import ClubScope
from tests.test_club_fees import _athlete, _plans, _user

NOW = datetime(2026, 10, 17, 15, 0, tzinfo=UTC)


async def _session(db, scope, user, start: datetime, hours: float | None) -> ClubWorkSession:
    row = ClubWorkSession(**scope.columns(), user_id=user.id, started_at=start,
                          ended_at=start + timedelta(hours=hours) if hours is not None else None)
    db.add(row)
    await db.commit()
    return row


async def test_coach_edits_adds_and_deletes_own_shifts(db, scope):
    coach_user = await _user(db, scope, "treinador")
    other = await _user(db, scope, "adjunto")
    s = await _session(db, scope, coach_user, datetime(2026, 10, 14, 17, tzinfo=UTC), 2)

    edited = await workclock.own_update(db, scope=scope, user_id=coach_user.id, session_id=s.id, now=NOW,
                                        changes={"ended_at": datetime(2026, 10, 14, 20, tzinfo=UTC), "note": "Gara"})
    assert edited["minutes"] == 180 and edited["edited_at"] is not None and edited["note"] == "Gara"

    # Validazioni: uscita prima dell'entrata, futuro, più di 24 ore.
    for changes in (
        {"ended_at": datetime(2026, 10, 14, 16, tzinfo=UTC)},
        {"ended_at": NOW + timedelta(hours=2)},
        {"ended_at": datetime(2026, 10, 15, 18, tzinfo=UTC)},
    ):
        with pytest.raises(club_service.ClubValidationError):
            await workclock.own_update(db, scope=scope, user_id=coach_user.id, session_id=s.id, now=NOW, changes=changes)
    with pytest.raises(club_service.ClubValidationError):  # un turno chiuso non si riapre
        await workclock.own_update(db, scope=scope, user_id=coach_user.id, session_id=s.id, now=NOW,
                                   changes={"ended_at": None})

    # Il turno dimenticato: non si sovrappone, non è nel futuro.
    with pytest.raises(club_service.ClubValidationError):
        await workclock.own_add(db, scope=scope, user_id=coach_user.id, now=NOW, note=None,
                                started_at=datetime(2026, 10, 14, 19, tzinfo=UTC),
                                ended_at=datetime(2026, 10, 14, 21, tzinfo=UTC))
    with pytest.raises(club_service.ClubValidationError):
        await workclock.own_add(db, scope=scope, user_id=coach_user.id, now=NOW, note=None,
                                started_at=NOW + timedelta(hours=1), ended_at=NOW + timedelta(hours=2))
    added = await workclock.own_add(db, scope=scope, user_id=coach_user.id, now=NOW, note="Dimenticato",
                                    started_at=datetime(2026, 10, 15, 18, tzinfo=UTC),
                                    ended_at=datetime(2026, 10, 15, 19, 30, tzinfo=UTC))
    assert added["added_later"] and added["minutes"] == 90

    # Un turno aperto conta fino ad adesso: niente turni sopra.
    await _session(db, scope, coach_user, NOW - timedelta(hours=1), None)
    with pytest.raises(club_service.ClubValidationError):
        await workclock.own_add(db, scope=scope, user_id=coach_user.id, now=NOW, note=None,
                                started_at=NOW - timedelta(minutes=30), ended_at=NOW - timedelta(minutes=10))

    # I mesi chiusi (prima del mese scorso) sono della segreteria.
    old = await _session(db, scope, coach_user, datetime(2026, 8, 20, 17, tzinfo=UTC), 1)
    with pytest.raises(club_service.ClubValidationError):
        await workclock.own_update(db, scope=scope, user_id=coach_user.id, session_id=old.id, now=NOW,
                                   changes={"note": "x"})
    with pytest.raises(club_service.ClubValidationError):
        await workclock.own_delete(db, scope=scope, user_id=coach_user.id, session_id=old.id, now=NOW)
    with pytest.raises(club_service.ClubValidationError):
        await workclock.own_update(db, scope=scope, user_id=coach_user.id, session_id=s.id, now=NOW,
                                   changes={"started_at": datetime(2026, 8, 31, 17, tzinfo=UTC)})

    # I turni degli altri non esistono.
    with pytest.raises(club_service.ClubNotFoundError):
        await workclock.own_update(db, scope=scope, user_id=other.id, session_id=s.id, now=NOW, changes={"note": "x"})
    with pytest.raises(club_service.ClubNotFoundError):
        await workclock.own_delete(db, scope=scope, user_id=other.id, session_id=s.id, now=NOW)

    await workclock.own_delete(db, scope=scope, user_id=coach_user.id, session_id=added["id"], now=NOW)
    assert await db.get(ClubWorkSession, added["id"]) is None

    # L'audit: prima e dopo, chi; la segreteria vede le modifiche del mese.
    actions = [a for (a,) in (await db.execute(
        select(AuditLog.action).where(AuditLog.entity_id.in_([str(s.id), str(added["id"])]))
    )).all()]
    assert sorted(actions) == ["club.work_session_added", "club.work_session_deleted", "club.work_session_edited"]
    changes = await workclock.session_changes(db, scope=scope, month=date.today().strftime("%Y-%m"))
    assert {c["action"] for c in changes} == {"edited", "added", "deleted"}
    edit = next(c for c in changes if c["action"] == "edited")
    assert edit["before"]["ended_at"].startswith("2026-10-14T19:00") and edit["after"]["note"] == "Gara"
    assert edit["user_id"] == str(coach_user.id)


async def test_secretary_correction_checks_overlaps(db, scope):
    admin = await _user(db, scope, "admin")
    coach_user = await _user(db, scope, "treinador")
    a = await _session(db, scope, coach_user, datetime(2026, 10, 14, 17, tzinfo=UTC), 2)
    await _session(db, scope, coach_user, datetime(2026, 10, 14, 20, tzinfo=UTC), 1)
    with pytest.raises(club_service.ClubValidationError):
        await workclock.correct(db, scope=scope, session_id=a.id, actor_user_id=admin.id,
                                changes={"ended_at": datetime(2026, 10, 14, 20, 30, tzinfo=UTC)})
    fixed = await workclock.correct(db, scope=scope, session_id=a.id, actor_user_id=admin.id,
                                    changes={"ended_at": datetime(2026, 10, 14, 19, 30, tzinfo=UTC)})
    assert fixed["corrected"] and fixed["minutes"] == 150


async def _course_with(db, scope, admin, instructor, athletes, name="Ragazzi"):
    course = await courses_service.create_course(
        db, scope=scope, actor_user_id=admin.id, data={"name": name, "instructor_user_id": instructor.id},
    )
    await courses_service.add_slot(db, scope=scope, course_id=course.id, actor_user_id=admin.id,
                                   weekday=1, starts_at=time(17, 30), ends_at=time(18, 30), room=None)
    for athlete in athletes:
        await courses_service.enrol(db, course=course, athlete=athlete, actor_user_id=admin.id)
    return course


async def test_notes_are_for_the_coaches_of_the_athlete_and_the_secretary(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    mine_coach = await _user(db, scope, "treinador")
    other_coach = await _user(db, scope, "altro")
    luca = await _athlete(db, scope, parent, birth_date=date(2014, 4, 4))
    sara = await _athlete(db, scope, parent, birth_date=date(2013, 2, 2), first_name="Sara", sex="F")
    mine = await _course_with(db, scope, admin, mine_coach, [luca])
    theirs = await _course_with(db, scope, admin, other_coach, [sara], name="Agonisti")
    # Ogni treinador vede tutti i corsi: qui la segreteria li separa (le
    # esclusioni sono provate in test_club_coach_visibility.py).
    await courses_service.set_coach_exclusions(db, scope=scope, course_id=mine.id, user_ids=[other_coach.id],
                                               actor_user_id=admin.id)
    await courses_service.set_coach_exclusions(db, scope=scope, course_id=theirs.id, user_ids=[mine_coach.id],
                                               actor_user_id=admin.id)
    today = date(2026, 10, 17)
    me = {"scope": scope, "user_id": mine_coach.id, "manager": False}
    them = {"scope": scope, "user_id": other_coach.id, "manager": False}
    secretary = {"scope": scope, "user_id": admin.id, "manager": True}

    # Le note delle lezioni: solo nei propri corsi.
    with pytest.raises(club_service.ClubValidationError):
        await coach.add_lesson_note(db, **me, course_id=mine.id, lesson_date=today, data={}, today=today)
    note = await coach.add_lesson_note(db, **me, course_id=mine.id, lesson_date=today, today=today, data={
        "title": "Ukemi", "techniques": "O-soto-gari, ukemi, o-soto-gari", "body": "Bene le cadute."})
    assert note["techniques"] == ["O-soto-gari", "ukemi"]
    with pytest.raises(club_service.ClubNotFoundError):
        await coach.add_lesson_note(db, **me, course_id=theirs.id, lesson_date=today, data={"title": "x"}, today=today)
    listed = await coach.list_lesson_notes(db, **me, q="cadute")
    assert [n["id"] for n in listed["items"]] == [note["id"]] and listed["techniques"][0]["name"] == "O-soto-gari"
    assert (await coach.list_lesson_notes(db, **them))["items"] == []
    with pytest.raises(club_service.ClubNotFoundError):
        await coach.list_lesson_notes(db, **them, course_id=mine.id)
    assert len((await coach.list_lesson_notes(db, **secretary))["items"]) == 1
    with pytest.raises(club_service.ClubNotFoundError):  # la corregge solo chi l'ha scritta
        await coach.update_lesson_note(db, **secretary, note_id=note["id"], data={"title": "y"}, today=today)
    with pytest.raises(club_service.ClubNotFoundError):
        await coach.delete_lesson_note(db, **them, note_id=note["id"])
    await coach.update_lesson_note(db, **me, note_id=note["id"], data={"title": "Ukemi e nage"}, today=today)

    # Le note sugli atleti: i treinadores dell'atleta e la segreteria.
    a_note = await coach.add_athlete_note(db, **me, athlete_id=luca.id, data={"category": "GOAL", "body": "Lavorare il kumikata"})
    with pytest.raises(club_service.ClubNotFoundError):
        await coach.add_athlete_note(db, **them, athlete_id=luca.id, data={"body": "x x"})
    with pytest.raises(club_service.ClubNotFoundError):
        await coach.list_athlete_notes(db, **them, athlete_id=luca.id)
    with pytest.raises(club_service.ClubValidationError):
        await coach.add_athlete_note(db, **me, athlete_id=luca.id, data={"category": "GOSSIP", "body": "x x"})
    assert [n["id"] for n in await coach.list_athlete_notes(db, **secretary, athlete_id=luca.id)] == [a_note["id"]]
    with pytest.raises(club_service.ClubNotFoundError):
        await coach.update_athlete_note(db, **secretary, note_id=a_note["id"], data={"body": "altro"})
    await coach.update_athlete_note(db, **me, note_id=a_note["id"], data={"body": "Kumikata e spostamenti"})
    audit = (await db.execute(select(AuditLog).where(AuditLog.entity_id == str(a_note["id"])))).scalar_one()
    assert audit.previous_value["body"] == "Lavorare il kumikata"

    # I miei atleti e la scheda: solo i propri.
    assert [a["id"] for a in await coach.my_athletes(db, **me, today=today)] == [luca.id]
    sheet = await coach.athlete_sheet(db, **me, athlete_id=luca.id, today=today)
    assert sheet["notes"][0]["mine"] and sheet["courses"] == [{"id": mine.id, "name": "Ragazzi"}]
    with pytest.raises(club_service.ClubNotFoundError):
        await coach.athlete_sheet(db, **me, athlete_id=sara.id, today=today)
    assert {a["id"] for a in await coach.my_athletes(db, **secretary, today=today)} == {luca.id, sara.id}

    # Un altro club: niente, nemmeno per la sua segreteria.
    other_club = Club(organization_id=scope.organization_id, name="Altro", slug="altro-club-x", settings={})
    db.add(other_club)
    await db.commit()
    elsewhere = {"scope": ClubScope(organization_id=scope.organization_id, club_id=other_club.id),
                 "user_id": admin.id, "manager": True}
    with pytest.raises(club_service.ClubNotFoundError):
        await coach.list_athlete_notes(db, **elsewhere, athlete_id=luca.id)
    with pytest.raises(club_service.ClubNotFoundError):
        await coach.delete_athlete_note(db, **elsewhere, note_id=a_note["id"])
    assert (await coach.list_lesson_notes(db, **elsewhere))["items"] == []

    # La segreteria modera: toglie la nota di un treinador.
    await coach.delete_athlete_note(db, **secretary, note_id=a_note["id"])
    await coach.delete_lesson_note(db, **secretary, note_id=note["id"])

    home = await coach.home(db, **me, now=datetime(2026, 10, 17, 12, 0))
    assert home["courses"] == 1 and home["athletes"] == 1
    # Martedì 13 il registro di Ragazzi è rimasto vuoto.
    assert any(m["date"] == date(2026, 10, 13) for m in home["missing_registers"])


async def test_coach_posts_on_the_board(db, scope):
    admin = await _user(db, scope, "admin")
    coach_user = await _user(db, scope, "treinador")
    other = await _user(db, scope, "altro")
    post = await news.create_staff_post(db, scope=scope, actor_user_id=coach_user.id, data={
        "title": "Allenamento speciale sabato", "body": "Portate il judogi bianco", "pinned": True, "audience": "NETWORK",
    })
    # Solo per i soci del club, mai fissato in cima.
    assert post["audience"] == "CLUB" and not post["pinned"] and post["author_user_id"] == coach_user.id
    assert [p["id"] for p in await news.list_author_posts(db, scope=scope, author_user_id=coach_user.id)] == [post["id"]]
    feed = await news.staff_feed(db, scope=scope, user_id=coach_user.id, today=date.today())
    assert any(i["post"] and i["post"]["id"] == post["id"] for i in feed)

    updated = await news.update_staff_post(db, scope=scope, post_id=post["id"], actor_user_id=coach_user.id,
                                           changes={"title": "Sabato: allenamento speciale", "pinned": True})
    assert updated["title"].startswith("Sabato") and not updated["pinned"]
    with pytest.raises(club_service.ClubNotFoundError):
        await news.update_staff_post(db, scope=scope, post_id=post["id"], actor_user_id=other.id, changes={"title": "x"})
    with pytest.raises(club_service.ClubNotFoundError):
        await news.delete_staff_post(db, scope=scope, post_id=post["id"], actor_user_id=other.id)
    # Un post della segreteria il treinador non lo tocca.
    club_post = await news.create_post(db, scope=scope, actor_user_id=admin.id, data={"title": "Assemblea"})
    with pytest.raises(club_service.ClubNotFoundError):
        await news.delete_staff_post(db, scope=scope, post_id=club_post["id"], actor_user_id=coach_user.id)
    # La segreteria modera i post dei treinadores.
    hidden = await news.update_post(db, scope=scope, post_id=post["id"], actor_user_id=admin.id, changes={"published": False})
    assert not hidden["published"]
    await news.delete_post(db, scope=scope, post_id=post["id"], actor_user_id=admin.id)
    assert await news.list_author_posts(db, scope=scope, author_user_id=coach_user.id) == []


async def test_coach_routes_with_only_club_instruct(db, scope, monkeypatch):
    """Le rotte vere con il solo permesso del treinador: il ranking dello
    staff si apre (quello della segreteria no: era il bug dell'area), Início,
    turni e bacheca rispondono, le modifiche ai turni sono della segreteria."""
    from app.domains.club import coach_router
    from tests.test_club_api import _client

    coach_user = await _user(db, scope, "treinador")
    app, client = await _client(db, monkeypatch, user=coach_user, scope=scope, granted={"club.instruct"})

    async def _codes(*args, **kwargs):
        return {"club.instruct"}

    monkeypatch.setattr(coach_router, "get_permission_codes_for_user", _codes)
    try:
        async with client:
            assert (await client.get("/club/admin/ranking")).status_code == 403
            ranking = await client.get("/club/staff/ranking")
            assert ranking.status_code == 200, ranking.text
            assert (await client.get("/club/staff/config")).status_code == 200
            home = await client.get("/club/staff/coach/home")
            assert home.status_code == 200, home.text
            assert home.json()["courses"] == 0
            start = (datetime.now(UTC) - timedelta(hours=3)).replace(microsecond=0)
            added = await client.post("/club/staff/clock/sessions", json={
                "started_at": start.isoformat(), "ended_at": (start + timedelta(hours=1)).isoformat(), "note": "Stage",
            })
            assert added.status_code == 201, added.text
            sessions = (await client.get(f"/club/staff/clock/sessions?month={start:%Y-%m}")).json()["sessions"]
            assert sessions[0]["added_later"] and sessions[0]["minutes"] == 60
            assert (await client.get("/club/admin/work-sessions/changes")).status_code == 403
            # (La POST passa dal rate limit su Redis, legato al loop del test: il
            # servizio dei post è provato sopra; qui basta che la bacheca risponda.)
            await news.create_staff_post(db, scope=scope, actor_user_id=coach_user.id, data={"title": "Sabato stage"})
            board = (await client.get("/club/staff/board")).json()
            assert [p["title"] for p in board["mine"]] == ["Sabato stage"]
    finally:
        app.dependency_overrides.clear()
