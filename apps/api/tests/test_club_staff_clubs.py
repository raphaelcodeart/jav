"""Un treinador, più club (club/staff_clubs.py, club/scope.py).

Le promesse: un account solo allena in più club e sceglie dove entrare; la
scelta vale solo per le rotte del treinador (famiglia e segreteria restano
nel club dell'account); nel club di un'altra appartenenza non è mai
segreteria; la segreteria chiede, il superadmin approva o toglie; nell'elenco
delle persone del club il treinador compare, solo come treinador.
"""

import uuid
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.deps import CurrentUser
from app.domains.club import people, staff_clubs
from app.domains.club.models import Club, ClubStaffMembership
from app.domains.club.scope import ClubScope, resolve_club, staff_club
from app.domains.club.service import ClubValidationError
from app.domains.rbac.models import Role, UserRole
from tests.test_club_area_extras import _client
from tests.test_club_fees import _athlete, _user


async def _role(db, scope, code):
    role = (await db.execute(select(Role).where(Role.code == code))).scalars().first()
    if role is None:
        role = Role(organization_id=scope.organization_id, code=code, name=code.title())
        db.add(role)
        await db.flush()
    return role


async def _coach(db, scope, label, *, extra_roles=()):
    user = await _user(db, scope, label)
    for code in ("INSTRUCTOR", *extra_roles):
        db.add(UserRole(user_id=user.id, organization_id=scope.organization_id, role_id=(await _role(db, scope, code)).id))
    await staff_clubs.ensure_home_membership(db, user=user, actor_user_id=None)
    await db.commit()
    return user


async def _other_club(db, scope, name="JTML Alvor") -> Club:
    club = Club(organization_id=scope.organization_id, name=name, slug=f"c-{uuid.uuid4().hex[:8]}", settings={})
    db.add(club)
    await db.commit()
    return club


async def test_one_account_many_clubs(db, scope, monkeypatch):
    alvor = await _other_club(db, scope)
    admin = await _user(db, scope, "superadmin")
    marco = await _coach(db, scope, "marco", extra_roles=("CUSTOMER",))
    await _athlete(db, scope, marco, birth_date=date(2015, 5, 5), first_name="Figlio", today=date.today())

    # Prima solo Lagos: la scelta di Alvor non vale, resta il suo club.
    me = CurrentUser(user_id=marco.id, organization_id=scope.organization_id, roles=["INSTRUCTOR"])
    club = await resolve_club(db, current_user=me, requested=None, staff_requested=str(alvor.id))
    assert club.id == scope.club_id

    # La segreteria di Alvor lo chiede; il superadmin approva.
    row = await staff_clubs.request(db, organization_id=scope.organization_id, club_id=alvor.id,
                                    actor_user_id=admin.id, email=marco.email)
    assert row.status == "REQUESTED"
    assert await staff_club(db, user=marco, requested=str(alvor.id)) is None
    with pytest.raises(ClubValidationError, match="già partita"):
        await staff_clubs.request(db, organization_id=scope.organization_id, club_id=alvor.id,
                                  actor_user_id=admin.id, email=marco.email)
    await staff_clubs.assign(db, organization_id=scope.organization_id, club_id=alvor.id, actor_user_id=admin.id,
                             user_id=marco.id)
    club = await resolve_club(db, current_user=me, requested=None, staff_requested=str(alvor.id))
    assert club.id == alvor.id

    mine = await staff_clubs.my_clubs(db, user=marco, can_instruct_home=True)
    assert [c["name"] for c in mine["clubs"]] == ["Club di prova", "JTML Alvor"] and mine["clubs"][0]["home"]
    assert mine["clubs"][0]["athletes"] == 1 and mine["me"]["photo_url"] is None

    # Nell'elenco di Alvor è solo treinador (a Lagos è anche genitore).
    alvor_people = await people.list_people(db, scope=ClubScope(organization_id=scope.organization_id, club_id=alvor.id))
    assert [(p["user_id"], p["kinds"]) for p in alvor_people] == [(marco.id, ["COACH"])]
    home_people = await people.list_people(db, scope=scope)
    assert next(p for p in home_people if p["user_id"] == marco.id)["kinds"] == ["PARENT", "COACH"]

    # Via HTTP: l'area del treinador segue la scelta, la famiglia no.
    app, client = await _client(db, monkeypatch, user=marco, scope=scope,
                                granted={"club.instruct", "club.family", "club.athlete"})
    try:
        async with client:
            headers = {"X-Jav-Staff-Club": str(alvor.id)}
            staff = await client.get("/club/current", params={"area": "staff"}, headers=headers)
            assert staff.status_code == 200 and staff.json()["name"] == "JTML Alvor"
            family = await client.get("/club/current", headers=headers)
            assert family.json()["name"] == "Club di prova"
            courses = await client.get("/club/staff/courses", headers=headers)
            assert courses.status_code == 200, courses.text
    finally:
        app.dependency_overrides.clear()

    # La segreteria toglie da Alvor chi viene da fuori, non il suo staff.
    await staff_clubs.remove(db, organization_id=scope.organization_id, club_id=alvor.id, user_id=marco.id,
                             actor_user_id=admin.id, by_secretary=True)
    with pytest.raises(ClubValidationError, match="ruolo"):
        await staff_clubs.remove(db, organization_id=scope.organization_id, club_id=scope.club_id, user_id=marco.id,
                                 actor_user_id=admin.id, by_secretary=True)


async def test_never_secretary_in_another_club(db, scope, monkeypatch):
    alvor = await _other_club(db, scope)
    boss = await _coach(db, scope, "segreteria-allenatore", extra_roles=("SECRETARY",))
    await staff_clubs.assign(db, organization_id=scope.organization_id, club_id=alvor.id, actor_user_id=boss.id,
                             user_id=boss.id)
    from app.domains.club import coach_router

    async def _codes(*args, **kwargs):
        return {"club.instruct", "club.manage"}

    monkeypatch.setattr(coach_router, "get_permission_codes_for_user", _codes)
    app, client = await _client(db, monkeypatch, user=boss, scope=scope, granted={"club.instruct", "club.manage"})
    try:
        async with client:
            # Nel suo club è segreteria (vede tutto); ad Alvor la segreteria
            # resta nel club dell'account, e l'area del treinador non lo fa manager.
            r = await client.get("/club/admin/staff", headers={"X-Jav-Staff-Club": str(alvor.id)})
            assert r.status_code == 200
            assert all(s["user_id"] != uuid.UUID(int=0) for s in r.json())
            home = await client.get("/club/staff/coach/athletes")
            other = await client.get("/club/staff/coach/athletes", headers={"X-Jav-Staff-Club": str(alvor.id)})
            assert home.status_code == other.status_code == 200, other.text
    finally:
        app.dependency_overrides.clear()
    # Lo staff di Alvor elenca il treinador ospite.
    from app.domains.club.clubs import _staff_by_club

    staff = (await _staff_by_club(db, club_ids=[alvor.id]))[alvor.id]
    assert [(s["user_id"], s["home"], s["membership_status"]) for s in staff] == [(boss.id, False, "ACTIVE")]
    assert (await db.execute(select(ClubStaffMembership).where(ClubStaffMembership.user_id == boss.id))).scalars().all()


async def test_the_scope_ignores_foreign_clubs(db, scope):
    stranger = await _other_club(db, scope, "Albufeira")
    marco = await _coach(db, scope, "solo-lagos")
    assert await staff_club(db, user=marco, requested=str(stranger.id)) is None
    assert await staff_club(db, user=marco, requested="non-un-uuid") is None
    me = CurrentUser(user_id=marco.id, organization_id=scope.organization_id, roles=["INSTRUCTOR"])
    assert (await resolve_club(db, current_user=me, requested=None, staff_requested=str(stranger.id))).id == scope.club_id
    stranger.status = "SUSPENDED"
    await db.commit()
    with pytest.raises(HTTPException):
        await resolve_club(db, current_user=CurrentUser(user_id=uuid.uuid4(), organization_id=scope.organization_id,
                                                         roles=[]), requested=None)


async def test_a_guest_coach_can_lead_a_course(db, scope):
    from app.domains.club import courses as courses_service

    unit = await _other_club(db, scope, "Cursos JAV")
    unit_scope = ClubScope(organization_id=scope.organization_id, club_id=unit.id)
    marco = await _coach(db, scope, "marco-corsi")
    stranger = await _coach(db, scope, "estraneo")
    with pytest.raises(ClubValidationError):
        await courses_service.create_course(db, scope=unit_scope, actor_user_id=marco.id,
                                            data={"name": "Torraltinha", "instructor_user_id": marco.id})
    await staff_clubs.assign(db, organization_id=scope.organization_id, club_id=unit.id, actor_user_id=marco.id,
                             user_id=marco.id)
    course = await courses_service.create_course(db, scope=unit_scope, actor_user_id=marco.id,
                                                 data={"name": "Torraltinha", "instructor_user_id": marco.id})
    assert course.instructor_user_id == marco.id
    with pytest.raises(ClubValidationError):
        await courses_service.update_course(db, scope=unit_scope, course_id=course.id, actor_user_id=marco.id,
                                            changes={"instructor_user_id": stranger.id})
