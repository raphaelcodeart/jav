"""Prezzi del club: sconti sulla mensilità, iscrizione annuale con quota socio,
credito degli inviti nel wallet, eventi (gara/stage) e richiesta di trasporto.
Specifica: docs/club-portal.md, "Prezzi e sconti" e "Trasporto".

Le promesse: lo sconto si calcola una volta e resta sulla quota; prima la
percentuale e poi gli euro; il genitore socio paga una volta per famiglia;
un invito rende credito una volta per pagamento e lo restituisce se il
pagamento salta; il credito usato torna se la prova è rifiutata; la lettera
del trasporto si prepara da sola alla chiusura e parte solo quando qualcuno
(o l'impostazione dell'evento) lo decide.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import func, select

from app.domains.auth import service as auth_service
from app.domains.club import clubs as clubs_service
from app.domains.club import competitions as competitions_service
from app.domains.club import pricing as pricing_rules
from app.domains.club import referrals
from app.domains.club import service as club_service
from app.domains.club import transport as transport_service
from app.domains.club.models import Club, ClubFee, ClubTransportRequest
from app.domains.customers.models import Customer
from app.domains.friend_referrals import service as friend_referrals_service
from app.domains.notifications.models import Notification
from app.domains.rbac.models import Role, UserRole
from app.domains.wallets import service as wallets_service
from tests.test_club_fees import PNG, _athlete, _fees, _plans, _user


async def _admin_set(db, athlete, admin, **changes):
    return await club_service.update_athlete(db, athlete=athlete, actor_user_id=admin.id, changes=changes, as_admin=True)


async def _balance(db, scope, user) -> int:
    wallet = await wallets_service.get_wallet_by_user_id(db, organization_id=scope.organization_id, user_id=user.id)
    return wallet.balance_cents if wallet else 0


async def test_tier_percentage_comes_first_then_the_family_euros(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    luca = await _athlete(db, scope, parent, birth_date=date(2016, 3, 3))
    await _athlete(db, scope, parent, birth_date=date(2015, 3, 3), first_name="Marco")
    await _admin_set(db, luca, admin, social_tier="A")

    await club_service.generate_monthly_fees(db, scope=scope, period="2026-11")
    november = (await _fees(db, luca.id, kind="MONTHLY", period="2026-11"))[0]
    # 40 € −25% = 30 €, poi −5 € famiglia = 25 €.
    assert (november.gross_amount_cents, november.discount_cents, november.amount_cents) == (4000, 1500, 2500)
    assert november.discount_note == "Escalão A −25% · Famiglia −5,00 €"

    # Il prezzo è congelato: cambiare lo sconto non tocca la quota emessa.
    await clubs_service.update_club_pricing(
        db, scope=scope, actor_user_id=admin.id, changes={"tier_discount_pct": {"A": 50}}
    )
    await db.refresh(november)
    assert november.amount_cents == 2500


def test_adapted_judo_counts_as_tier_a_and_never_goes_below_zero():
    pricing = pricing_rules.get_pricing(None)

    class _A:
        adapted_judo = True
        social_tier = "C"

    price = pricing_rules.monthly_price(list_cents=600, athlete=_A(), family_size=3, pricing=pricing)
    assert price["discount_note"] == "Judo adattato −25% · Famiglia −4,50 €"
    assert price["amount_cents"] == 0
    # Escalão e judo adattato non si sommano: vale il maggiore.
    custom = {**pricing, "tier_discount_pct": {"A": 25, "B": 30, "C": 5}, "family_discount_cents": 0}

    class _B:
        adapted_judo = True
        social_tier = "B"

    assert pricing_rules.monthly_price(list_cents=4000, athlete=_B(), family_size=1, pricing=custom)[
        "discount_note"] == "Escalão B −30%"
    assert pricing_rules.monthly_price(list_cents=4000, athlete=_A(), family_size=1, pricing=custom)[
        "discount_note"] == "Judo adattato −25%"
    assert pricing_rules.prorated(12000, start_month=9) == 4000
    assert pricing_rules.prorated(12000, start_month=1) == 12000
    with pytest.raises(ValueError):
        pricing_rules.validate_pricing({"tier_discount_pct": {"A": 120}})


async def test_the_new_year_bills_enrollment_and_one_membership_per_family(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    await _athlete(db, scope, parent, birth_date=date(2016, 3, 3))
    await _athlete(db, scope, parent, birth_date=date(2019, 3, 3), first_name="Anna", sex="F")
    # Un adulto che si allena: la sua iscrizione comprende già la quota socio.
    adult = await _user(db, scope, "adulto")
    await _athlete(db, scope, adult, birth_date=date(1985, 1, 1), is_self=True)

    created = await club_service.start_year(db, scope=scope, year=2027)
    again = await club_service.start_year(db, scope=scope, year=2027)
    # Due iscrizioni (l'adulto ha un piano senza iscrizione) e una quota socio.
    assert (created, again) == (3, 0)
    memberships = (
        await db.execute(select(ClubFee).where(ClubFee.kind == "MEMBERSHIP", ClubFee.period == "2027"))
    ).scalars().all()
    assert [(m.guardian_user_id, m.amount_cents) for m in memberships] == [(parent.id, 6000)]


async def _family_with_invite(db, scope, admin):
    """Una famiglia che ne ha invitata un'altra dal suo link."""
    inviter = await _user(db, scope, "invita")
    invited = await _user(db, scope, "invitato")
    customer = Customer(organization_id=scope.organization_id, user_id=invited.id, kind="PRIVATE", email=invited.email)
    db.add(customer)
    await db.flush()
    code = await friend_referrals_service.get_or_create_code(db, organization_id=scope.organization_id, user_id=inviter.id)
    club = await db.get(Club, scope.club_id)
    await referrals.record_club_invite(db, club=club, invite_code=code.code, customer_id=customer.id)
    await db.commit()
    child = await _athlete(db, scope, invited, birth_date=date(2016, 3, 3), first_name="Rui")
    return inviter, invited, child


async def test_an_invited_family_paying_a_month_credits_the_inviter_once(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    inviter, invited, child = await _family_with_invite(db, scope, admin)
    october = (await _fees(db, child.id, kind="MONTHLY"))[0]
    enrollment = (await _fees(db, child.id, kind="ENROLLMENT"))[0]

    proof = await club_service.upload_payment_proof(
        db, scope=scope, guardian_user_id=invited.id, fee_ids=[october.id, enrollment.id],
        file_bytes=PNG, content_type="image/png", original_filename="bonifico.png",
    )
    # Solo la mensilità rende credito, non l'iscrizione.
    assert await _balance(db, scope, inviter) == 500
    await referrals.on_fee_paid(db, fee=october)
    assert await _balance(db, scope, inviter) == 500

    await club_service.reject_proof(db, scope=scope, proof_id=proof.id, actor_user_id=admin.id, reason="Illeggibile")
    assert await _balance(db, scope, inviter) == 0

    # Ripagata: un pagamento nuovo, un credito nuovo.
    await club_service.mark_fee_paid(db, scope=scope, fee_id=october.id, actor_user_id=admin.id, note="Contanti")
    assert await _balance(db, scope, inviter) == 500

    info = await referrals.invite_link(
        db, organization_id=scope.organization_id, club=await db.get(Club, scope.club_id), user_id=inviter.id
    )
    assert info["invited_count"] == 1
    assert info["path"].startswith(f"/c/{(await db.get(Club, scope.club_id)).slug}?invito=")


async def test_wallet_credit_pays_fees_and_comes_back_if_the_proof_is_rejected(db, scope, monkeypatch):
    async def _ok(*args, **kwargs):
        return True

    monkeypatch.setattr(auth_service, "verify_spend_code", _ok)
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    child = await _athlete(db, scope, parent, birth_date=date(2016, 3, 3))
    wallet = await wallets_service.get_or_create_wallet(db, organization_id=scope.organization_id, user_id=parent.id)
    await wallets_service.credit_wallet(
        db, organization_id=scope.organization_id, wallet_id=wallet.id, amount_cents=1000, type_="ADMIN_CREDIT",
        actor_user_id=None, source="CLUB_REFERRAL", idempotency_key=f"test-{uuid.uuid4()}",
    )
    october = (await _fees(db, child.id, kind="MONTHLY"))[0]
    enrollment = (await _fees(db, child.id, kind="ENROLLMENT"))[0]

    # Il credito non basta per la mensilità: serve anche la ricevuta.
    with pytest.raises(club_service.ClubValidationError):
        await club_service.upload_payment_proof(
            db, scope=scope, guardian_user_id=parent.id, fee_ids=[october.id], file_bytes=None,
            content_type=None, original_filename=None, credit_cents=1000, spend_code="1234",
        )
    # L'iscrizione (6,25 €) la paga tutta il credito: niente foto.
    proof = await club_service.upload_payment_proof(
        db, scope=scope, guardian_user_id=parent.id, fee_ids=[enrollment.id], file_bytes=None,
        content_type=None, original_filename=None, credit_cents=625, spend_code="1234",
    )
    assert (proof.storage_key, proof.credit_cents) == (None, 625)
    assert await _balance(db, scope, parent) == 375

    await club_service.reject_proof(db, scope=scope, proof_id=proof.id, actor_user_id=admin.id, reason="Errore")
    assert await _balance(db, scope, parent) == 1000
    await db.refresh(enrollment)
    assert enrollment.status == "DUE"

    # Più credito di quello che c'è: rifiutato, senza toccare niente.
    with pytest.raises(club_service.ClubValidationError):
        await club_service.upload_payment_proof(
            db, scope=scope, guardian_user_id=parent.id, fee_ids=[october.id], file_bytes=PNG,
            content_type="image/png", original_filename="b.png", credit_cents=2000, spend_code="1234",
        )


async def _event(db, scope, admin, **kw):
    data = {
        "name": kw.pop("name", "Taça do Algarve"), "starts_on": date(2026, 11, 7),
        "registration_deadline": date(2026, 11, 1), "level": "REGIONAL", "fee_cents": 0,
        "requires_agonistic_certificate": False, **kw,
    }
    return await competitions_service.create_competition(db, scope=scope, actor_user_id=admin.id, data=data)


async def test_closing_registrations_prepares_the_transport_letter(db, scope, monkeypatch):
    sent: list[dict] = []
    monkeypatch.setattr("app.core.email.send_html_email", lambda **kw: sent.append(kw))
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    secretary = await _user(db, scope, "segreteria")
    role = Role(organization_id=scope.organization_id, code="SECRETARY", name="Secretary")
    db.add(role)
    await db.flush()
    db.add(UserRole(user_id=secretary.id, organization_id=scope.organization_id, role_id=role.id))
    club = await db.get(Club, scope.club_id)
    club.settings = {"transport_entity_name": "Câmara Municipal de Lagos", "transport_entity_email": "cm@lagos.demo",
                     "contact_email": "clube@lagos.demo"}
    await db.commit()
    parent = await _user(db, scope)
    athlete = await _athlete(db, scope, parent, birth_date=date(2014, 4, 4), today=date(2026, 10, 15))
    comp = await _event(db, scope, admin, transport_needed=True, transport_companions=2,
                        transport_departure="Pavilhão, 7h00")
    assert (comp.transport_entity_name, comp.transport_entity_email) == ("Câmara Municipal de Lagos", "cm@lagos.demo")
    await competitions_service.register_entry(
        db, competition=comp, athlete=athlete, actor_user_id=parent.id, category=None, today=date(2026, 10, 20)
    )

    await competitions_service.set_competition_status(
        db, scope=scope, competition_id=comp.id, actor_user_id=admin.id, status="CLOSED"
    )
    request = (
        await db.execute(select(ClubTransportRequest).where(ClubTransportRequest.competition_id == comp.id))
    ).scalar_one()
    assert (request.status, request.athletes_count, request.to_email) == ("DRAFT", 1, "cm@lagos.demo")
    assert "Viajarão 1 atletas e 2 acompanhantes" in request.body_text
    assert "Luca Bianchi (2014)" in request.body_text
    assert sent == []
    notified = (
        await db.execute(select(func.count()).where(Notification.recipient_user_id == secretary.id))
    ).scalar_one()
    assert notified == 1

    request = await transport_service.send(
        db, scope=scope, competition_id=comp.id, to_email="cm@lagos.demo", subject="Pedido",
        body_text="Corpo corretto a mano\n\nObrigado", actor_user_id=admin.id,
    )
    assert request.status == "SENT"
    assert sent[0]["to"] == "cm@lagos.demo" and sent[0]["reply_to"] == "clube@lagos.demo"
    assert sent[0]["text_body"] == "Corpo corretto a mano\n\nObrigado"


async def test_auto_send_and_a_missing_mail_server(db, scope, monkeypatch):
    from app.core.email import EmailNotConfiguredError

    def _no_smtp(**kw):
        raise EmailNotConfiguredError("no smtp")

    monkeypatch.setattr("app.core.email.send_html_email", _no_smtp)
    admin = await _user(db, scope, "admin")
    comp = await _event(db, scope, admin, transport_needed=True, transport_auto_send=True,
                        transport_entity_email="cm@lagos.demo")
    await competitions_service.set_competition_status(
        db, scope=scope, competition_id=comp.id, actor_user_id=admin.id, status="CLOSED"
    )
    request = (
        await db.execute(select(ClubTransportRequest).where(ClubTransportRequest.competition_id == comp.id))
    ).scalar_one()
    # Il server di posta manca: la lettera resta pronta, con il motivo.
    assert request.status == "DRAFT"
    assert "configurato" in request.last_error


async def test_a_stage_gives_no_ranking_points(db, scope):
    admin = await _user(db, scope, "admin")
    stage = await _event(db, scope, admin, kind="STAGE", name="Estágio de Natal")
    with pytest.raises(club_service.ClubValidationError):
        await competitions_service.record_results(
            db, scope=scope, competition_id=stage.id, actor_user_id=admin.id, results=[]
        )
