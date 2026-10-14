"""Più club sulla stessa piattaforma (docs/club-portal.md, "Più club").

La promessa da proteggere è una: la segreteria e le famiglie di un club non
vedono e non toccano niente di un altro club, nemmeno conoscendone gli id.
Poi le porte d'ingresso: chi lavora su quale club (club/scope.py), la
creazione di un club con la sua segreteria, la registrazione di una famiglia
dal link del club, e la prova di bonifico di un ordine dello Shop.
"""

import uuid
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.deps import CurrentUser
from app.domains.auth import service as auth_service
from app.domains.auth.schemas import RegisterFamilyRequest
from app.domains.club import clubs as clubs_service
from app.domains.club import competitions as competitions_service
from app.domains.club import scope as scope_module
from app.domains.club import service as club_service
from app.domains.club.models import Club, ClubFee
from app.domains.club.scope import ClubScope, resolve_club
from app.domains.jav_market import service as shop_service
from app.domains.jav_market.models import JavMarketOrder
from app.domains.rbac.models import Role, UserRole
from app.domains.users.models import User
from tests.test_club_fees import PNG, _athlete, _plans, _user


async def _other_club(db, organization_id, name="Judo Clube de Lagos") -> ClubScope:
    club = Club(organization_id=organization_id, name=name, slug=clubs_service.slugify(name), settings={})
    db.add(club)
    await db.commit()
    return ClubScope(organization_id=organization_id, club_id=club.id)


async def _roles(db, organization_id, *codes) -> None:
    for code in codes:
        db.add(Role(organization_id=organization_id, code=code, name=code.title()))
    await db.commit()


def _as(user: User) -> CurrentUser:
    return CurrentUser(user_id=user.id, organization_id=user.organization_id, roles=[])


async def test_a_club_never_sees_another_club(db, scope):
    lagos = await _other_club(db, scope.organization_id)
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    await _plans(db, lagos, admin)
    parent = await _user(db, scope)
    mine = await _athlete(db, scope, parent, birth_date=date(2014, 4, 4))
    lagos_parent = await _user(db, lagos, "lagos")
    theirs = await _athlete(db, lagos, lagos_parent, birth_date=date(2014, 4, 4), first_name="Tiago")

    assert [a.id for a in await club_service.search_athletes(db, scope=scope)] == [mine.id]
    with pytest.raises(club_service.ClubNotFoundError):
        await club_service.get_athlete(db, scope=scope, athlete_id=theirs.id)
    their_fee = (await db.execute(select(ClubFee).where(ClubFee.athlete_id == theirs.id))).scalars().first()
    with pytest.raises(club_service.ClubNotFoundError):
        await club_service.waive_fee(db, scope=scope, fee_id=their_fee.id, actor_user_id=admin.id, reason="no")
    fees = await club_service.list_fees(db, scope=scope)
    assert {f.athlete_id for f in fees if f.athlete_id} == {mine.id}
    assert {f.guardian_user_id for f in fees if f.kind == "MEMBERSHIP"} == {parent.id}

    # Una gara di Lagos non esiste per il club di prova, nemmeno per id.
    lagos_comp = await competitions_service.create_competition(db, scope=lagos, actor_user_id=admin.id, data={
        "name": "Taça do Algarve", "starts_on": date(2026, 11, 7), "registration_deadline": date(2026, 11, 1), "level": "CLUB", "fee_cents": 0,
        "requires_agonistic_certificate": False,
    })
    assert await competitions_service.list_competitions(db, scope=scope) == []
    with pytest.raises(club_service.ClubNotFoundError):
        await competitions_service.get_competition(db, scope=scope, competition_id=lagos_comp.id)


async def test_monthly_fees_are_generated_club_by_club(db, scope):
    lagos = await _other_club(db, scope.organization_id)
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    await _plans(db, lagos, admin)
    await _athlete(db, scope, await _user(db, scope), birth_date=date(2014, 4, 4))
    await _athlete(db, lagos, await _user(db, lagos, "lagos"), birth_date=date(2014, 4, 4))

    assert await club_service.generate_monthly_fees(db, scope=scope, period="2026-11") == 1
    assert await club_service.generate_monthly_fees(db, scope=lagos, period="2026-11") == 1


async def test_who_works_on_which_club(db, scope, monkeypatch):
    lagos = await _other_club(db, scope.organization_id)
    granted: set[str] = set()

    async def _codes(*args, **kwargs):
        return granted

    monkeypatch.setattr(scope_module, "get_permission_codes_for_user", _codes)

    # Un account del club lavora sul suo club, qualunque club chieda.
    secretary = await _user(db, scope, "segreteria")
    club = await resolve_club(db, current_user=_as(secretary), requested=str(lagos.club_id))
    assert club.id == scope.club_id

    # Lo staff della piattaforma deve scegliere, e poter entrare.
    staff = User(organization_id=scope.organization_id, email=f"staff-{uuid.uuid4().hex[:6]}@x.demo", password_hash="x")
    db.add(staff)
    await db.commit()
    with pytest.raises(HTTPException) as denied:
        await resolve_club(db, current_user=_as(staff), requested=str(lagos.club_id))
    assert denied.value.status_code == 403
    granted.add(scope_module.CLUBS_ENTER)
    with pytest.raises(HTTPException) as unchosen:
        await resolve_club(db, current_user=_as(staff), requested=None)
    assert unchosen.value.status_code == 409
    assert (await resolve_club(db, current_user=_as(staff), requested=str(lagos.club_id))).id == lagos.club_id

    # Un club di un'altra organizzazione non esiste.
    from app.domains.organizations.models import Organization

    elsewhere = Organization(name=f"Altra {uuid.uuid4()}", status="ACTIVE")
    db.add(elsewhere)
    await db.commit()
    foreign = await _other_club(db, elsewhere.id, "Club Lontano")
    with pytest.raises(HTTPException) as missing:
        await resolve_club(db, current_user=_as(staff), requested=str(foreign.club_id))
    assert missing.value.status_code == 404

    # Un club sospeso chiude ai suoi account, non allo staff.
    await clubs_service.update_club(
        db, organization_id=scope.organization_id, club_id=scope.club_id, actor_user_id=staff.id,
        changes={"status": "SUSPENDED"},
    )
    with pytest.raises(HTTPException) as suspended:
        await resolve_club(db, current_user=_as(secretary), requested=None)
    assert suspended.value.status_code == 403
    assert (await resolve_club(db, current_user=_as(staff), requested=str(scope.club_id))).id == scope.club_id


async def test_creating_a_club_gives_it_an_address_and_a_secretary(db, organization_id):
    await _roles(db, organization_id, "SECRETARY")
    superadmin = User(organization_id=organization_id, email=f"sa-{uuid.uuid4().hex[:6]}@x.demo", password_hash="x")
    db.add(superadmin)
    await db.commit()

    club, invite_link = await clubs_service.create_club(
        db, organization_id=organization_id, actor_user_id=superadmin.id, name="Judo Clube de Lagos", slug=None,
        secretary_email="Segreteria@Lagos.demo", settings={"bank_iban": "PT50 0000", "unknown": "ignorato"},
    )
    assert club.slug == "judo-clube-de-lagos"
    # Nei test l'SMTP non c'è: il link di primo accesso torna a chi crea il
    # club, che lo consegna a mano.
    assert invite_link is not None and "/reset-password?token=" in invite_link
    assert club.settings == {"bank_iban": "PT50 0000"}
    secretary = (await db.execute(select(User).where(User.email == "segreteria@lagos.demo"))).scalar_one()
    assert secretary.club_id == club.id
    role = (
        await db.execute(select(Role.code).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == secretary.id))
    ).scalar_one()
    assert role == "SECRETARY"

    with pytest.raises(club_service.ClubValidationError):
        await clubs_service.create_club(
            db, organization_id=organization_id, actor_user_id=superadmin.id, name="Judo Clube de Lagos", slug=None,
        )
    with pytest.raises(club_service.ClubValidationError):
        await clubs_service.add_staff(
            db, scope=ClubScope(organization_id=organization_id, club_id=club.id), actor_user_id=superadmin.id,
            email="segreteria@lagos.demo", role="INSTRUCTOR",
        )


async def test_a_family_registers_from_the_club_link(db, scope):
    await _roles(db, scope.organization_id, "CUSTOMER")
    club = await db.get(Club, scope.club_id)
    payload = {
        "email": "Famiglia@Example.demo", "password": "password-lunga", "first_name": "maria", "last_name": "silva",
        "accept_privacy": True,
    }
    user = await auth_service.register_family(db, payload=RegisterFamilyRequest(club_slug=club.slug, **payload))
    assert user.club_id == scope.club_id
    assert user.email == "famiglia@example.demo"
    assert user.privacy_accepted_at is not None

    with pytest.raises(auth_service.RegistrationError):
        await auth_service.register_family(db, payload=RegisterFamilyRequest(club_slug=club.slug, **payload))
    with pytest.raises(auth_service.RegistrationError):
        await auth_service.register_family(
            db, payload=RegisterFamilyRequest(club_slug="nessun-club", **{**payload, "email": "altra@example.demo"})
        )


async def test_a_shop_order_takes_a_transfer_proof_without_being_paid(db, scope):
    parent = await _user(db, scope)
    order = JavMarketOrder(
        organization_id=scope.organization_id, customer_user_id=parent.id, created_by_user_id=parent.id,
        amount_cents=4500, recipient_name="Maria Silva", address_line1="Rua 1", city="Lagos", province="FA",
        postal_code="8600", status="AWAITING_PAYMENT", payment_method="BANK_TRANSFER",
    )
    db.add(order)
    await db.commit()

    order = await shop_service.upload_payment_proof(
        db, order=order, file_bytes=PNG, content_type="image/png", original_filename="bonifico.png",
        actor_user_id=parent.id,
    )
    assert order.payment_proof_storage_key is not None
    # La merce parte solo quando la piattaforma conferma il bonifico.
    assert order.status == "AWAITING_PAYMENT"

    order.status = "PAID"
    await db.commit()
    with pytest.raises(shop_service.JavMarketValidationError):
        await shop_service.upload_payment_proof(
            db, order=order, file_bytes=PNG, content_type="image/png", original_filename="bonifico.png",
            actor_user_id=parent.id,
        )
