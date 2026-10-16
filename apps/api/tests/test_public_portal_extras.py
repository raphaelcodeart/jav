"""Sponsor, argomento dei messaggi, ranking per periodo, Taça dos Clubes e
scheda del judoca in classifica (docs/club-portal.md).

Le promesse: uno sponsor spento sparisce dal sito; un logo è uno dei nostri;
un messaggio ha sempre un argomento valido; il ranking del mese conta solo
quel mese e quello di sempre conta tutto; la coppa va a chi ha più punti a
fine anno e l'anno in corso è ancora aperto; la scheda di chi non ha dato il
consenso non porta foto, categoria né prove in programma.
"""

import uuid
from datetime import date

import pytest

from app.core.config import get_settings
from app.domains.club import contact as contact_service
from app.domains.club import site as site_service
from app.domains.club import sponsors
from app.domains.club.service import ClubNotFoundError, ClubValidationError
from tests.test_club_fees import _athlete, _plans, _user
from tests.test_club_multi import _other_club
from tests.test_club_site import _competition, _consent_and_publish, _result
from tests.test_contact_messages import _published

TODAY = date(2026, 10, 14)



async def _unpublish(db, athlete) -> None:
    from sqlalchemy import select as _select

    from app.domains.club.site_models import ClubAthletePublicProfile
    profile = (await db.execute(_select(ClubAthletePublicProfile).where(ClubAthletePublicProfile.athlete_id == athlete.id))).scalar_one()
    profile.published = False
    await db.commit()

async def test_sponsors_public_only_when_active(db, scope):
    admin = await _user(db, scope, "admin")
    org = scope.organization_id
    lagos = await sponsors.create_sponsor(db, organization_id=org, actor_user_id=admin.id, data={
        "name": "Câmara Municipal de Lagos", "website_url": "www.cm-lagos.pt", "color": "#1f4e9c", "sort_order": 1,
    })
    assert (lagos.slug, lagos.website_url, lagos.color) == ("camara-municipal-de-lagos", "https://www.cm-lagos.pt", "#1F4E9C")
    twin = await sponsors.create_sponsor(db, organization_id=org, actor_user_id=admin.id,
                                         data={"name": "Câmara Municipal de Lagos"})
    assert twin.slug == "camara-municipal-de-lagos-2"
    assert [s.id for s in await sponsors.public_sponsors(db)] == [twin.id, lagos.id]

    await sponsors.update_sponsor(db, organization_id=org, sponsor_id=twin.id, actor_user_id=admin.id,
                                  changes={"active": False})
    assert [s.id for s in await sponsors.public_sponsors(db)] == [lagos.id]
    with pytest.raises(ClubNotFoundError):
        await sponsors.public_sponsor(db, slug=twin.slug)
    assert (await sponsors.public_sponsor(db, slug="Camara-Municipal-de-Lagos")).id == lagos.id

    for bad in ({"name": " "}, {"logo_url": "https://evil.example/logo.png"}, {"color": "blue"},
                {"website_url": "javascript alert"}):
        with pytest.raises(ClubValidationError):
            await sponsors.update_sponsor(db, organization_id=org, sponsor_id=lagos.id, actor_user_id=admin.id,
                                          changes=bad)
    ours = f"{get_settings().public_app_base_url}/media/sponsors/x.png"
    assert (await sponsors.update_sponsor(db, organization_id=org, sponsor_id=lagos.id, actor_user_id=admin.id,
                                          changes={"logo_url": ours})).logo_url == ours
    with pytest.raises(ClubNotFoundError):
        await sponsors.update_sponsor(db, organization_id=uuid.uuid4(), sponsor_id=lagos.id, actor_user_id=admin.id,
                                      changes={"name": "X"})


async def test_contact_messages_carry_a_topic(db, scope):
    await _published(db, scope)
    form = {"name": "Ana Silva", "email": "ana@example.com", "message": "Queremos patrocinar o torneio.",
            "consent": True}
    sponsor = await contact_service.submit(db, data={**form, "topic": "sponsor"}, organization_id=scope.organization_id)
    other = await contact_service.submit(db, data={**form, "topic": "<script>"}, organization_id=scope.organization_id)
    plain = await contact_service.submit(db, data=form, organization_id=scope.organization_id)
    assert (sponsor.topic, other.topic, plain.topic) == ("SPONSOR", "GENERAL", "GENERAL")
    assert contact_service.message_dict(sponsor)["topic"] == "SPONSOR"


async def test_rankings_by_period_the_club_cup_and_the_card(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    await _published(db, scope)
    parent = await _user(db, scope)
    shown = await _athlete(db, scope, parent, birth_date=date(2015, 3, 3), first_name="Tiago", last_name="Matias")
    hidden = await _athlete(db, scope, parent, birth_date=date(2016, 6, 6), first_name="Rita", last_name="Segreta")
    # Rita parte pubblica come tutti; il club non pubblica la sua scheda: resta
    # in classifica e tra gli iscritti come «Nome I.», senza pagina.
    await _unpublish(db, hidden)
    await _consent_and_publish(db, scope, shown, parent, admin)

    other = await _other_club(db, scope.organization_id, name="Judo Clube de Albufeira")
    await _published(db, other)
    other_admin = await _user(db, other, "admin2")
    await _plans(db, other, other_admin)
    rival_parent = await _user(db, other, "genitore2")
    rival = await _athlete(db, other, rival_parent, birth_date=date(2015, 1, 1), first_name="Rui", last_name="Costa")

    may = await _competition(db, scope, admin, starts_on=date(2026, 5, 10), name="Torneio de maio")
    june = await _competition(db, scope, admin, starts_on=date(2026, 6, 20), name="Taça de junho")
    last_year = await _competition(db, other, other_admin, starts_on=date(2025, 4, 4), name="Open 2025")
    await _result(db, may, shown, admin, 1)
    await _result(db, june, hidden, admin, 2)
    await _result(db, last_year, rival, other_admin, 1)

    year = await site_service.public_ranking(db, season=2026, today=TODAY)
    assert {r["id"] for r in year["rows"]} == {shown.id, hidden.id}
    month = await site_service.public_ranking(db, season=2026, period="month", month=5, today=TODAY)
    assert [r["id"] for r in month["rows"]] == [shown.id] and month["month"] == 5
    ever = await site_service.public_ranking(db, period="all", today=TODAY)
    assert {r["id"] for r in ever["rows"]} == {shown.id, hidden.id, rival.id}
    with pytest.raises(ClubValidationError):
        await site_service.public_ranking(db, season=2026, period="month", month=None, today=TODAY)

    cup = await site_service.public_club_ranking(db, season=2026, today=TODAY)
    # Nel 2026 ha gareggiato solo il primo club.
    assert len(cup["rows"]) == 1 and cup["rows"][0]["club"]["name"] != "Judo Clube de Albufeira"
    assert cup["rows"][0]["athletes"] == 2 and cup["rows"][0]["gold"] == 1 and cup["rows"][0]["silver"] == 1
    assert cup["is_final"] is False
    # L'albo d'oro: il 2025 è chiuso e l'ha vinto Albufeira.
    assert [(w["year"], w["club"]["name"]) for w in cup["winners"]] == [(2025, "Judo Clube de Albufeira")]
    closed = await site_service.public_club_ranking(db, season=2025, today=TODAY)
    assert closed["is_final"] is True and closed["rows"][0]["club"]["name"] == "Judo Clube de Albufeira"
    assert len((await site_service.public_club_ranking(db, period="all", today=TODAY))["rows"]) == 2

    # La scheda: completa con il consenso, ridotta senza.
    full = await site_service.ranking_card(db, athlete_id=shown.id, today=TODAY)
    assert full["has_page"] is True and full["profile"]["display_name"] == "Tiago M."
    short = await site_service.ranking_card(db, athlete_id=hidden.id, today=TODAY)
    assert short["has_page"] is False and short["profile"] is None
    card = short["card"]
    assert card["display_name"] == "Rita S." and card["photo_url"] is None
    assert [r["event_name"] for r in card["results"]] == ["Taça de junho"]
    assert "category" not in card and "upcoming" not in card and "photos" not in card
    with pytest.raises(ClubNotFoundError):
        await site_service.ranking_card(db, athlete_id=uuid.uuid4(), today=TODAY)
