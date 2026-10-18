"""Il conto dell'atleta (docs/club-portal.md, "Il conto dell'atleta").

Le promesse: l'accesso lo crea solo il titolare; un figlio senza email entra
con nome utente o QR e nessuna posta parte verso di lui; l'area la vedono
solo l'atleta e il suo titolare; a 18 anni l'atleta (e solo lui) può
diventare titolare del suo conto.
"""

from datetime import date

import pytest

from app.core.email import is_placeholder_address
from app.domains.auth import service as auth_service
from app.domains.club import athlete_access
from app.domains.club import service as club_service
from app.domains.rbac.models import Role, UserRole
from app.domains.users.models import User
from tests.test_club_fees import _athlete, _user

TODAY = date(2026, 10, 15)


async def _roles(db, scope) -> None:
    for code in ("ATHLETE", "CUSTOMER"):
        db.add(Role(organization_id=scope.organization_id, code=code, name=code.title()))
    await db.commit()


async def _role_codes(db, user_id) -> set[str]:
    from sqlalchemy import select

    rows = await db.execute(select(Role.code).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user_id))
    return set(rows.scalars())


async def test_a_child_without_email_logs_in_with_username_or_qr(db, scope):
    await _roles(db, scope)
    parent = await _user(db, scope)
    kid = await _athlete(db, scope, parent, birth_date=date(2016, 3, 1), first_name="Tiago")

    with pytest.raises(club_service.ClubValidationError):  # serve una password
        await athlete_access.set_login(db, athlete=kid, actor_user_id=parent.id, username="tiago.l", email=None, password=None)
    with pytest.raises(club_service.ClubValidationError):  # nome utente non valido
        await athlete_access.set_login(db, athlete=kid, actor_user_id=parent.id, username="Ti Ago", email=None, password="segreto1")

    row = await athlete_access.set_login(
        db, athlete=kid, actor_user_id=parent.id, username="Tiago.L", email=None, password="segreto1",
    )
    assert row["has_login"] and row["username"] == "tiago.l" and row["email"] is None
    user = await db.get(User, kid.user_id)
    assert is_placeholder_address(user.email) and await _role_codes(db, user.id) == {"ATHLETE"}

    # Si entra con il nome utente (maiuscole o no) come con un'email.
    access, _refresh = await auth_service.authenticate(
        db, organization_id=scope.organization_id, email="tiago.l", password="segreto1", ip_address=None, user_agent=None,
    )
    assert access

    # Il QR: vale finché non si revoca; uno nuovo spegne il vecchio.
    code, _ = await athlete_access.create_qr(db, athlete=kid, actor_user_id=parent.id)
    assert (await athlete_access.user_for_code(db, organization_id=scope.organization_id, code=code)).id == user.id
    code2, _ = await athlete_access.create_qr(db, athlete=kid, actor_user_id=parent.id)
    with pytest.raises(athlete_access.LoginCodeError):
        await athlete_access.user_for_code(db, organization_id=scope.organization_id, code=code)
    await athlete_access.disable_login(db, athlete=kid, actor_user_id=parent.id)
    with pytest.raises(athlete_access.LoginCodeError):
        await athlete_access.user_for_code(db, organization_id=scope.organization_id, code=code2)
    with pytest.raises(auth_service.AccountLockedError):
        await auth_service.authenticate(
            db, organization_id=scope.organization_id, email="tiago.l", password="segreto1", ip_address=None, user_agent=None,
        )


async def test_usernames_are_unique_and_only_the_holder_manages_them(db, scope):
    await _roles(db, scope)
    parent = await _user(db, scope)
    other = await _user(db, scope, "altro")
    a = await _athlete(db, scope, parent, birth_date=date(2015, 1, 1))
    b = await _athlete(db, scope, other, birth_date=date(2015, 1, 1))
    await athlete_access.set_login(db, athlete=a, actor_user_id=parent.id, username="luca.b", email=None, password="segreto1")
    with pytest.raises(club_service.ClubValidationError):
        await athlete_access.set_login(db, athlete=b, actor_user_id=other.id, username="luca.b", email=None, password="segreto1")
    # Un'altra famiglia non apre né l'atleta né la sua area.
    with pytest.raises(club_service.ClubNotFoundError):
        await club_service.get_owned_athlete(db, scope=scope, guardian_user_id=other.id, athlete_id=a.id)
    with pytest.raises(club_service.ClubNotFoundError):
        await athlete_access.area_athlete(db, user_id=other.id, club_id=scope.club_id, athlete_id=a.id)
    # L'atleta e il titolare sì.
    assert (await athlete_access.area_athlete(db, user_id=a.user_id, club_id=scope.club_id, athlete_id=a.id)).id == a.id
    assert (await athlete_access.area_athlete(db, user_id=parent.id, club_id=scope.club_id, athlete_id=a.id)).id == a.id
    areas = await athlete_access.area_athletes(db, user_id=parent.id, club_id=scope.club_id)
    assert [x.id for x in areas] == [a.id]


async def test_the_area_shows_fees_read_only_and_who_manages(db, scope):
    await _roles(db, scope)
    parent = await _user(db, scope)
    kid = await _athlete(db, scope, parent, birth_date=date(2014, 5, 1))
    await athlete_access.set_login(db, athlete=kid, actor_user_id=parent.id, username="kid.one", email=None, password="segreto1")
    as_kid = await athlete_access.area(db, athlete=kid, viewer_user_id=kid.user_id, today=TODAY)
    assert as_kid["is_minor"] and as_kid["viewer_is_athlete"] and not as_kid["can_manage"]
    assert not as_kid["can_become_holder"] and "fees" in as_kid
    as_parent = await athlete_access.area(db, athlete=kid, viewer_user_id=parent.id, today=TODAY)
    assert as_parent["can_manage"] and not as_parent["viewer_is_athlete"]


async def test_at_18_the_athlete_becomes_holder_of_the_own_account(db, scope):
    await _roles(db, scope)
    parent = await _user(db, scope)
    teen = await _athlete(db, scope, parent, birth_date=date(2008, 9, 1), first_name="Rita")
    young = await _athlete(db, scope, parent, birth_date=date(2012, 1, 1))
    await athlete_access.set_login(db, athlete=teen, actor_user_id=parent.id, username="rita", email=None, password="segreto1")
    await athlete_access.set_login(db, athlete=young, actor_user_id=parent.id, username="young", email=None, password="segreto1")

    # Il genitore non può farlo al suo posto, un minorenne non può, e serve un'email vera.
    with pytest.raises(club_service.ClubValidationError):
        await athlete_access.become_holder(db, athlete=teen, user_id=parent.id, email=None, today=TODAY)
    with pytest.raises(club_service.ClubValidationError):
        await athlete_access.become_holder(db, athlete=young, user_id=young.user_id, email="y@example.demo", today=TODAY)
    with pytest.raises(club_service.ClubValidationError):
        await athlete_access.become_holder(db, athlete=teen, user_id=teen.user_id, email=None, today=TODAY)

    view = await athlete_access.area(db, athlete=teen, viewer_user_id=teen.user_id, today=TODAY)
    assert view["can_become_holder"]
    await athlete_access.become_holder(db, athlete=teen, user_id=teen.user_id, email="Rita@Example.demo", today=TODAY)
    await db.refresh(teen)
    assert teen.guardian_user_id == teen.user_id and teen.is_self
    user = await db.get(User, teen.user_id)
    assert user.email == "rita@example.demo" and "CUSTOMER" in await _role_codes(db, user.id)
    # Il genitore resta collegato (club_athlete_links): lo vede ancora, ma
    # il titolare ora è l'atleta.
    assert {a.id for a in await athlete_access.area_athletes(db, user_id=parent.id, club_id=scope.club_id)} == {
        young.id, teen.id}
