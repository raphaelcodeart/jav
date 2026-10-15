"""Ciò che è arrivato con il gestionale dei club (docs/legacy-judo-aev.md).

Le promesse: un esente non ha mensilità né iscrizione; lo sconto personale
vale dove la segreteria l'ha messo; il numero di ricevuta è progressivo e
non si ripete mai; un evento della rete lo vedono tutti i club, ognuno ci
iscrive i suoi e registra i risultati dei suoi, ma nessun club lo modifica;
un'iscrizione divisa in rate non si emette una seconda volta intera; i punti
seguono la tabella dei club; i dati del vecchio gestionale si leggono bene.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import select

from app.domains.club import competitions as competitions_service
from app.domains.club import pricing as pricing_rules
from app.domains.club import receipts
from app.domains.club import service as club_service
from app.domains.club.models import Club, ClubCompetition, ClubFee
from app.domains.club.scope import ClubScope
from app.domains.club.service import ClubValidationError
from app.legacy import judo_aev
from tests.test_club_fees import _athlete, _fees, _plans, _user


async def _other_club(db, scope) -> ClubScope:
    club = Club(organization_id=scope.organization_id, name="Outro clube", slug=f"outro-{uuid.uuid4().hex[:8]}", settings={})
    db.add(club)
    await db.commit()
    return ClubScope(organization_id=scope.organization_id, club_id=club.id)


# --- Prezzi ---------------------------------------------------------------------------------------


async def test_exempt_athletes_have_no_monthly_or_annual_fee(db, scope):
    admin = await _user(db, scope, "admin")
    kids, _youth, _all = await _plans(db, scope, admin)
    parent = await _user(db, scope)
    athlete = await _athlete(db, scope, parent, birth_date=date(2020, 5, 5))
    athlete.exempt_monthly = True
    athlete.exempt_annual = True
    await db.commit()
    await club_service.ensure_monthly_fee(db, athlete=athlete, plan=kids, year=2027, month=1,
                                          pricing=pricing_rules.DEFAULT_PRICING, family_size=1)
    await club_service.ensure_enrollment_fee(db, athlete=athlete, plan=kids, year=2027)
    await db.commit()
    assert [f for f in await _fees(db, athlete.id) if f.period.startswith("2027")] == []


def test_custom_discount_applies_only_where_it_was_given():
    class _A:
        adapted_judo = False
        social_tier = "D"
        exempt_monthly = False
        exempt_annual = False
        custom_discount_kind = "FIXED"
        custom_discount_value = 1500
        custom_discount_scope = "MONTHLY"
        custom_discount_note = "Grupo 2 · 1x semana"

    pricing = {**pricing_rules.DEFAULT_PRICING, "tier_discount_pct": {"A": 25, "B": 20, "C": 15, "D": 10},
               "family_discount_cents": 0}
    price = pricing_rules.monthly_price(list_cents=6000, athlete=_A(), family_size=1, pricing=pricing)
    # 60 € −10% (escalão D) = 54 €, −15 € = 39 €.
    assert price["amount_cents"] == 3900
    assert price["discount_note"] == "Escalão D −10% · Grupo 2 · 1x semana −15,00 €"
    # Sulle quote annuali no: lo sconto era solo sulla mensilità.
    assert pricing_rules.annual_price(amount_cents=12000, athlete=_A())["amount_cents"] == 12000
    _A.custom_discount_kind, _A.custom_discount_value, _A.custom_discount_scope = "PERCENT", 50, "BOTH"
    assert pricing_rules.annual_price(amount_cents=12000, athlete=_A())["amount_cents"] == 6000


async def test_enrollment_in_instalments_is_not_emitted_again(db, scope):
    admin = await _user(db, scope, "admin")
    kids, _youth, _all = await _plans(db, scope, admin)
    parent = await _user(db, scope)
    athlete = await _athlete(db, scope, parent, birth_date=date(2020, 5, 5))
    for n in (1, 2):
        db.add(ClubFee(**scope.columns(), athlete_id=athlete.id, kind="ENROLLMENT", period=f"2027/{n}",
                       installment_no=n, installments_total=2, description=f"Iscrizione 2027 · rata {n}/2",
                       amount_cents=1250, due_date=date(2027, 1 + n, 15), status="DUE"))
    await db.commit()
    await club_service.ensure_enrollment_fee(db, athlete=athlete, plan=kids, year=2027)
    await db.commit()
    assert sorted(f.period for f in await _fees(db, athlete.id, kind="ENROLLMENT") if f.period.startswith("2027")) == [
        "2027/1", "2027/2"]


# --- Ricevute -------------------------------------------------------------------------------------


async def test_receipt_numbers_are_progressive_per_club_prefix_and_year(db, scope):
    other = await _other_club(db, scope)
    first = await receipts.next_number(db, club_id=scope.club_id, prefix="MEN", year=2026)
    second = await receipts.next_number(db, club_id=scope.club_id, prefix="MEN", year=2026)
    quota = await receipts.next_number(db, club_id=scope.club_id, prefix="QUO", year=2026)
    elsewhere = await receipts.next_number(db, club_id=other.club_id, prefix="MEN", year=2026)
    next_year = await receipts.next_number(db, club_id=scope.club_id, prefix="MEN", year=2027)
    assert (first, second, quota, elsewhere, next_year) == (
        "MEN-2026-0001", "MEN-2026-0002", "QUO-2026-0001", "MEN-2026-0001", "MEN-2027-0001")
    assert receipts.prefix_for(["MONTHLY", "MONTHLY"]) == "MEN"
    assert receipts.prefix_for(["MONTHLY", "COMPETITION"]) == "PAG"


# --- Eventi della rete ----------------------------------------------------------------------------


async def test_network_events_are_shared_but_each_club_keeps_its_own(db, scope):
    other = await _other_club(db, scope)
    admin = await _user(db, scope, "admin")
    other_admin = await _user(db, other, "admin2")
    mine = await _athlete(db, scope, await _user(db, scope), birth_date=date(2014, 3, 3), first_name="Rui")
    theirs = await _athlete(db, other, await _user(db, other, "g2"), birth_date=date(2014, 4, 4), first_name="Ana")
    event = ClubCompetition(
        organization_id=scope.organization_id, club_id=None, name="Open de Lisboa", starts_on=date(2026, 12, 12),
        ends_on=date(2026, 12, 12), level="OPENS", registration_deadline=date(2026, 12, 5), fee_cents=1500,
        requires_agonistic_certificate=False, status="OPEN", kind="COMPETITION",
    )
    db.add(event)
    await db.commit()

    assert event.id in {c.id for c in await competitions_service.list_competitions(db, scope=scope)}
    assert event.id in {c.id for c in await competitions_service.list_competitions(db, scope=other)}
    with pytest.raises(ClubValidationError):
        await competitions_service.update_competition(
            db, scope=scope, competition_id=event.id, actor_user_id=admin.id, changes={"fee_cents": 0})

    today = date(2026, 11, 1)
    e1 = await competitions_service.register_entry(db, competition=event, athlete=mine, actor_user_id=admin.id,
                                                   category=None, today=today)
    e2 = await competitions_service.register_entry(db, competition=event, athlete=theirs,
                                                   actor_user_id=other_admin.id, category=None, today=today)
    assert (e1.club_id, e2.club_id) == (scope.club_id, other.club_id)
    fee = (await db.execute(select(ClubFee).where(ClubFee.athlete_id == mine.id, ClubFee.kind == "COMPETITION"))).scalar_one()
    assert fee.club_id == scope.club_id and fee.amount_cents == 1500

    # Ognuno registra i suoi: il risultato di un altro club qui "non c'è".
    await competitions_service.record_results(db, scope=scope, competition_id=event.id, actor_user_id=admin.id,
                                              results=[(e1.id, 1)])
    with pytest.raises(club_service.ClubNotFoundError):
        await competitions_service.record_results(db, scope=scope, competition_id=event.id,
                                                  actor_user_id=admin.id, results=[(e2.id, 1)])
    await db.refresh(event)
    assert event.status == "OPEN"  # lo stato è della rete, non di chi registra
    points = await competitions_service.athlete_points(db, athlete_ids=[mine.id])
    assert points[mine.id]["points"] == 10 and points[mine.id]["gold"] == 1  # oro in un Open


def test_level_points_table():
    assert competitions_service.points_for(placement=1, level="NATIONAL") == 15
    assert competitions_service.points_for(placement=3, level="EUROPEAN_CHAMPIONSHIP") == 15
    assert competitions_service.points_for(placement=5, level="OPENS") == 3  # vale la partecipazione
    assert competitions_service.points_for(placement=0, level="OLYMPIC_GAMES") == 8
    assert competitions_service.points_for(placement=None, level="REGIONAL") == 0


# --- Il vecchio gestionale ------------------------------------------------------------------------


def test_legacy_values_are_read_correctly():
    assert judo_aev.belt_code("6º Kyu – Branco") == "WHITE"
    assert judo_aev.belt_code("6º Kyu – Branco 9 Barras Amarelas (5 anos)") == "WHITE_BARS_9"
    assert judo_aev.belt_code("3º Kyu – Verde Azul (13 anos)") == "GREEN_BLUE"
    assert judo_aev.belt_code("2º Kyu – Azul Castanho (15 anos)") == "BLUE_BROWN"
    assert judo_aev.belt_code("1º Kyu – Castanho (16 anos)") == "BROWN"
    assert judo_aev.belt_code("2º Dan – Preta") == "BLACK_2"
    assert judo_aev.belt_code(None) is None
    assert judo_aev.months_of("Janeiro,Fevereiro,Março 2026") == [1, 2, 3]
    assert judo_aev.files_of('["comprovativos\\/2\\/a.jpg","comprovativos\\/2\\/b.pdf"]') == [
        "comprovativos/2/a.jpg", "comprovativos/2/b.pdf"]
    assert judo_aev.files_of("comprovativos/1/x.jpg") == ["comprovativos/1/x.jpg"]
    assert (judo_aev.height_cm("1,52"), judo_aev.height_cm("152 cm"), judo_aev.height_cm("")) == (152, 152, None)
    assert judo_aev.split_name("Maria  da Silva Santos") == ("Maria", "da Silva Santos")
    assert judo_aev.cents("42.50") == 4250


async def test_staff_access_link_only_for_the_clubs_own_staff(db, scope):
    from app.domains.club import clubs as clubs_service
    from app.domains.rbac.models import Role, UserRole

    admin = await _user(db, scope, "admin")
    secretary = await _user(db, scope, "segreteria")
    role = (await db.execute(select(Role).where(Role.code == "SECRETARY"))).scalars().first()
    if role is None:
        role = Role(code="SECRETARY", name="Segreteria", organization_id=None)
        db.add(role)
        await db.flush()
    db.add(UserRole(user_id=secretary.id, organization_id=scope.organization_id, role_id=role.id))
    await db.commit()
    link = await clubs_service.staff_access_link(db, scope=scope, user_id=secretary.id, actor_user_id=admin.id)
    assert link and "/reset-password?token=" in link  # senza SMTP: il link da consegnare
    family = await _user(db, scope, "famiglia")
    with pytest.raises(club_service.ClubNotFoundError):
        await clubs_service.staff_access_link(db, scope=scope, user_id=family.id, actor_user_id=admin.id)
    other = await _other_club(db, scope)
    with pytest.raises(club_service.ClubNotFoundError):
        await clubs_service.staff_access_link(db, scope=other, user_id=secretary.id, actor_user_id=admin.id)


# --- Documenti del club ---------------------------------------------------------------------------


PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


async def test_club_documents_are_private_to_the_club_and_remind_before_expiry(db, scope):
    from app.domains.club import club_documents
    from app.domains.club.tasks import _claim_reminder  # noqa: F401  (stesso registro dei promemoria)

    admin = await _user(db, scope, "admin")
    today = date(2026, 10, 15)
    tax = await club_documents.add_document(
        db, scope=scope, actor_user_id=admin.id, file_bytes=PDF, content_type="application/pdf", filename="at.pdf",
        data={"category": "TAX", "title": "Certidão de não dívida", "issued_on": date(2026, 5, 1),
              "expires_on": date(2026, 11, 1)},
    )
    statutes = await club_documents.add_document(
        db, scope=scope, actor_user_id=admin.id, file_bytes=PDF, content_type="application/pdf", filename="e.pdf",
        data={"category": "STATUTES", "title": "Estatutos"},
    )
    assert club_documents.status_of(tax, today=today) == "EXPIRING"
    assert club_documents.status_of(statutes, today=today) == "NONE"
    assert club_documents.status_of(tax, today=date(2026, 11, 2)) == "EXPIRED"

    other = await _other_club(db, scope)
    assert await club_documents.list_documents(db, scope=other) == []
    with pytest.raises(club_service.ClubNotFoundError):
        await club_documents.get_document(db, scope=other, document_id=tax.id)

    with pytest.raises(ClubValidationError):
        await club_documents.add_document(
            db, scope=scope, actor_user_id=admin.id, file_bytes=b"<html>", content_type="text/html", filename="x.html",
            data={"category": "OTHER", "title": "Pagina"},
        )

    # Un avviso per documento e per momento, anche rilanciando il job.
    assert await club_documents.expiry_reminders(db, scope=scope, today=today) == 1
    assert await club_documents.expiry_reminders(db, scope=scope, today=today) == 0
    assert await club_documents.expiry_reminders(db, scope=scope, today=date(2026, 11, 1)) == 1
    await club_documents.remove_document(db, scope=scope, document_id=statutes.id, actor_user_id=admin.id)
    assert [d.id for d in await club_documents.list_documents(db, scope=scope)] == [tax.id]


async def test_ranking_is_of_the_calendar_year_and_of_the_whole_network(db, scope):
    other = await _other_club(db, scope)
    admin = await _user(db, scope, "admin")
    mine = await _athlete(db, scope, await _user(db, scope), birth_date=date(2016, 3, 3), first_name="Rui")
    theirs = await _athlete(db, other, await _user(db, other, "g2"), birth_date=date(2016, 4, 4), first_name="Ana")
    event = ClubCompetition(
        organization_id=scope.organization_id, club_id=None, name="Regional de Faro", starts_on=date(2026, 3, 7),
        ends_on=date(2026, 3, 7), level="REGIONAL", registration_deadline=date(2026, 3, 1), fee_cents=0,
        requires_agonistic_certificate=False, status="OPEN", kind="COMPETITION",
    )
    db.add(event)
    await db.commit()
    for athlete, user in ((mine, admin), (theirs, admin)):
        await competitions_service.register_entry(db, competition=event, athlete=athlete, actor_user_id=user.id,
                                                  category=None, today=date(2026, 2, 1))
    entries = await competitions_service.list_entries(db, competition_ids=[event.id])
    by_athlete = {e.athlete_id: e for e in entries}
    by_athlete[mine.id].placement, by_athlete[theirs.id].placement = 3, 1
    await db.commit()

    # Marzo 2026 è nella "stagione" 2025/26, ma il ranking è dell'anno 2026.
    rows = await competitions_service.ranking(db, scope=scope, season=2026)
    assert [(r["display_name"], r["points"], r["club_name"]) for r in rows] == [
        ("Ana B.", 5, "Outro clube"), ("Rui B.", 2, "Club di prova")]
    assert {r["age_band"] for r in rows} == {"GRUPO_2"}  # 10 anni federali nel 2026
    assert [r["display_name"] for r in await competitions_service.ranking(db, scope=scope, season=2026, club_only=True)] == ["Rui B."]
    assert await competitions_service.ranking(db, scope=scope, season=2025) == []
