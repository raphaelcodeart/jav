"""Il sito pubblico JudoArteVida (docs/club-portal.md, "Sito pubblico").

La promessa da proteggere è la privacy: molti atleti sono minorenni, e il
sito lo legge chiunque. Un atleta compare solo con il consenso della
famiglia e la pubblicazione del club; un club solo se è attivo e ha
pubblicato la sua pagina; e di un atleta pubblico non esce mai niente oltre
a nome e iniziale, cintura, club, fascia d'età, medaglie e punti.
"""

import json
from datetime import date, time

import httpx
import pytest

from app.domains.club import clubs as clubs_service
from app.domains.club import service as club_service
from app.domains.club import site as site_service
from app.domains.club.models import (
    ClubCompetition,
    ClubCompetitionEntry,
    ClubCourse,
    ClubCourseSlot,
)
from app.domains.club.site_models import ClubSite
from tests.test_club_fees import _athlete, _plans, _user
from tests.test_club_multi import _other_club

TODAY = date(2026, 10, 14)


async def _published_site(db, scope, **content) -> ClubSite:
    site = ClubSite(**scope.columns(), published=True, gallery=[], coaches=[], **content)
    db.add(site)
    await db.commit()
    return site


async def _slug(db, scope) -> str:
    return (await clubs_service.get_club(db, organization_id=scope.organization_id, club_id=scope.club_id)).slug


async def _competition(db, scope, admin, *, starts_on, kind="COMPETITION", name="Taça do Algarve") -> ClubCompetition:
    comp = ClubCompetition(
        **scope.columns(), name=name, kind=kind, starts_on=starts_on, ends_on=starts_on,
        registration_deadline=starts_on, level="REGIONAL", fee_cents=0, requires_agonistic_certificate=False,
        status="DONE" if starts_on < TODAY else "OPEN", created_by_user_id=admin.id,
    )
    db.add(comp)
    await db.commit()
    return comp


async def _result(db, comp, athlete, admin, placement) -> None:
    db.add(ClubCompetitionEntry(
        organization_id=comp.organization_id, club_id=comp.club_id, competition_id=comp.id,
        athlete_id=athlete.id, category="-38 kg", registered_by_user_id=admin.id, placement=placement,
    ))
    await db.commit()


async def _consent_and_publish(db, scope, athlete, parent, admin, *, show_photo=False) -> None:
    await site_service.update_consent(
        db, athlete=athlete, actor_user_id=parent.id, changes={"consent": True, "show_photo": show_photo},
    )
    await site_service.set_athlete_published(
        db, scope=scope, athlete_id=athlete.id, published=True, actor_user_id=admin.id,
    )


async def test_an_unpublished_or_suspended_club_does_not_exist(db, scope):
    admin = await _user(db, scope, "admin")
    slug = await _slug(db, scope)

    # La pagina nasce in bozza: per il sito il club non c'è.
    await site_service.get_site(db, scope=scope)
    with pytest.raises(club_service.ClubNotFoundError):
        await site_service.club_page(db, slug=slug, today=TODAY)
    assert (await site_service.portal_home(db, today=TODAY))["clubs"] == []
    comp = await _competition(db, scope, admin, starts_on=date(2026, 11, 7))
    with pytest.raises(club_service.ClubNotFoundError):
        await site_service.event_detail(db, event_id=comp.id, today=TODAY)

    await site_service.update_site(
        db, scope=scope, actor_user_id=admin.id, changes={"published": True, "tagline": "Judo para todos"},
    )
    page = await site_service.club_page(db, slug=slug, today=TODAY)
    assert page["tagline"] == "Judo para todos"
    assert [e["id"] for e in page["upcoming_events"]] == [comp.id]
    home = await site_service.portal_home(db, today=TODAY)
    assert [c["slug"] for c in home["clubs"]] == [slug]

    # Sospeso: sparisce, anche se la pagina resta pubblicata.
    await clubs_service.update_club(
        db, organization_id=scope.organization_id, club_id=scope.club_id, actor_user_id=admin.id,
        changes={"status": "SUSPENDED"},
    )
    with pytest.raises(club_service.ClubNotFoundError):
        await site_service.club_page(db, slug=slug, today=TODAY)
    assert await site_service.list_events(db, today=TODAY) == []


async def test_without_the_family_consent_an_athlete_is_never_public(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    await _published_site(db, scope)
    slug = await _slug(db, scope)
    parent = await _user(db, scope)
    kid = await _athlete(db, scope, parent, birth_date=date(2015, 3, 3), first_name="Tiago", last_name="Matias")

    # Il club non può pubblicare chi non ha il consenso.
    with pytest.raises(club_service.ClubValidationError):
        await site_service.set_athlete_published(
            db, scope=scope, athlete_id=kid.id, published=True, actor_user_id=admin.id,
        )
    assert (await site_service.club_page(db, slug=slug, today=TODAY))["judoka"] == []
    with pytest.raises(club_service.ClubNotFoundError):
        await site_service.judoka_profile(db, athlete_id=kid.id, today=TODAY)

    # Il consenso da solo non basta: decide anche il club.
    await site_service.update_consent(db, athlete=kid, actor_user_id=parent.id, changes={"consent": True})
    assert (await site_service.club_page(db, slug=slug, today=TODAY))["judoka"] == []

    await site_service.set_athlete_published(
        db, scope=scope, athlete_id=kid.id, published=True, actor_user_id=admin.id,
    )
    page = await site_service.club_page(db, slug=slug, today=TODAY)
    assert [j["display_name"] for j in page["judoka"]] == ["Tiago M."]
    assert (await site_service.judoka_profile(db, athlete_id=kid.id, today=TODAY))["display_name"] == "Tiago M."

    # Ritirato il consenso, sparisce subito, e la pubblicazione non torna da sola.
    withdrawn = await site_service.update_consent(db, athlete=kid, actor_user_id=parent.id, changes={"consent": False})
    assert withdrawn["consent"] is False and withdrawn["published"] is False
    assert (await site_service.club_page(db, slug=slug, today=TODAY))["judoka"] == []
    await site_service.update_consent(db, athlete=kid, actor_user_id=parent.id, changes={"consent": True})
    assert (await site_service.club_page(db, slug=slug, today=TODAY))["judoka"] == []

    # Un atleta che lascia il club esce dal sito.
    await site_service.set_athlete_published(db, scope=scope, athlete_id=kid.id, published=True, actor_user_id=admin.id)
    kid.status = "LEFT"
    await db.commit()
    with pytest.raises(club_service.ClubNotFoundError):
        await site_service.judoka_profile(db, athlete_id=kid.id, today=TODAY)


async def test_public_payloads_carry_only_what_may_be_public(db, scope, monkeypatch):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    await _published_site(db, scope, city="Lagos")
    slug = await _slug(db, scope)
    parent = await _user(db, scope)
    shown = await _athlete(
        db, scope, parent, birth_date=date(2015, 3, 3), first_name="Tiago", last_name="Matias",
        fiscal_code="MTSTGO15C03Z128X",
    )
    shown.photo_url = "https://example.demo/media/tiago.jpg"
    shown.weight_kg = 37
    hidden = await _athlete(db, scope, parent, birth_date=date(2016, 6, 6), first_name="Rita", last_name="Segreta")
    await _consent_and_publish(db, scope, shown, parent, admin, show_photo=False)

    past = await _competition(db, scope, admin, starts_on=date(2026, 10, 4))
    await _result(db, past, shown, admin, 1)
    await _result(db, past, hidden, admin, 2)
    course = ClubCourse(**scope.columns(), name="Infantis", level="Iniciação", min_age=6, max_age=9, active=True)
    db.add(course)
    await db.flush()
    db.add(ClubCourseSlot(course_id=course.id, weekday=1, starts_at=time(18, 0), ends_at=time(19, 0), room="Tatami 1"))
    await db.commit()

    page = await site_service.club_page(db, slug=slug, today=TODAY)
    [judoka] = page["judoka"]
    assert set(judoka) == {
        "id", "display_name", "photo_url", "has_page", "belt", "age_band", "club",
        "points", "competitions", "gold", "silver", "bronze",
    }
    assert judoka["display_name"] == "Tiago M."
    assert judoka["photo_url"] is None  # la famiglia non ha permesso la foto
    assert judoka["age_band"] == "GRUPO_2"
    assert judoka["gold"] == 1 and judoka["points"] == 5  # oro regionale
    assert page["schedule"] == [{"weekday": 1, "slots": [{
        "course": "Infantis", "level": "Iniciação", "min_age": 6, "max_age": 9,
        "starts_at": "18:00", "ends_at": "19:00", "room": "Tatami 1",
    }]}]
    # L'oro di Tiago c'è; l'argento di Rita (senza consenso) no.
    assert [(m["display_name"], m["placement"]) for m in page["recent_medals"]] == [("Tiago M.", 1)]

    detail = await site_service.event_detail(db, event_id=past.id, today=TODAY)
    assert detail["participants_count"] == 2
    assert [p["display_name"] for p in detail["participants"]] == ["Tiago M."]

    # La foto compare solo con il permesso della famiglia.
    await site_service.update_consent(db, athlete=shown, actor_user_id=parent.id, changes={"show_photo": True})
    profile = await site_service.judoka_profile(db, athlete_id=shown.id, today=TODAY)
    assert profile["photo_url"] == "https://example.demo/media/tiago.jpg"
    assert profile["results"][0]["placement"] == 1

    # Attraverso l'API vera: nel JSON non c'è nulla di privato.
    from app.core.db import get_db
    from app.main import app

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/api") as client:
            bodies = []
            for path in (
                "/public-site/home", f"/public-site/clubs/{slug}", f"/public-site/judoka/{shown.id}",
                f"/public-site/events/{past.id}", "/public-site/ranking", "/public-site/events?when=past",
            ):
                res = await client.get(path)
                assert res.status_code == 200, (path, res.text)
                bodies.append(json.dumps(res.json()))
            assert (await client.get(f"/public-site/judoka/{hidden.id}")).status_code == 404
            # In classifica ci sono tutti (decisione del titolare), ma chi non
            # ha il consenso è solo "Nome I.": niente pagina, niente foto.
            ranking = (await client.get("/public-site/ranking")).json()["rows"]
            rita = next(r for r in ranking if r["id"] == str(hidden.id))
            assert (rita["display_name"], rita["has_page"], rita["photo_url"]) == ("Rita S.", False, None)
    finally:
        app.dependency_overrides.clear()
    everything = "\n".join(bodies)
    for secret in ("Matias", "Segreta", "2015-03-03", "MTSTGO15C03Z128X", "birth", "fiscal", "weight",
                   "guardian", "fee", str(parent.id), parent.email):
        assert secret not in everything, secret


async def test_a_club_admin_edits_only_the_own_site(db, scope):
    lagos = await _other_club(db, scope.organization_id)
    admin = await _user(db, scope, "admin")
    await _plans(db, lagos, admin)
    lagos_parent = await _user(db, lagos, "lagos")
    theirs = await _athlete(db, lagos, lagos_parent, birth_date=date(2014, 4, 4))
    await site_service.update_consent(db, athlete=theirs, actor_user_id=lagos_parent.id, changes={"consent": True})

    await site_service.update_site(
        db, scope=scope, actor_user_id=admin.id,
        changes={"about": "O nosso clube", "gallery": [{"url": "https://example.demo/a.jpg", "caption": "Treino"}]},
    )
    assert (await site_service.get_site(db, scope=lagos)).about is None
    assert (await site_service.get_site(db, scope=scope)).gallery == [
        {"url": "https://example.demo/a.jpg", "caption": "Treino"},
    ]

    # Un atleta di un altro club, anche con il consenso, non si pubblica da qui.
    with pytest.raises(club_service.ClubNotFoundError):
        await site_service.set_athlete_published(
            db, scope=scope, athlete_id=theirs.id, published=True, actor_user_id=admin.id,
        )
    assert await site_service.list_athletes_public_status(db, scope=scope) == []
    [row] = await site_service.list_athletes_public_status(db, scope=lagos)
    assert row["consent"] is True and row["published"] is False

    # Un indirizzo che non è un indirizzo web si rifiuta con una frase chiara.
    with pytest.raises(club_service.ClubValidationError):
        await site_service.update_site(
            db, scope=scope, actor_user_id=admin.id, changes={"instagram_url": "javascript:alert(1)"},
        )


async def test_family_consent_routes_are_family_only(db, scope, monkeypatch):
    from tests.test_club_api import _client

    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    other = await _user(db, scope, "altro")
    mine = await _athlete(db, scope, parent, birth_date=date(2015, 3, 3))
    theirs = await _athlete(db, scope, other, birth_date=date(2015, 3, 3), first_name="Estraneo")

    app, client = await _client(db, monkeypatch, user=parent, scope=scope, granted={"club.family"})
    try:
        async with client:
            res = await client.put(f"/club/athletes/{mine.id}/public-profile", json={"consent": True, "bio": "Ippon!"})
            assert res.status_code == 200, res.text
            assert res.json()["consent"] is True and res.json()["published"] is False
            assert (await client.get(f"/club/athletes/{theirs.id}/public-profile")).status_code == 404
            assert (await client.put(f"/club/athletes/{theirs.id}/public-profile", json={"consent": True})).status_code == 404
            # Il genitore non entra nell'editor della pagina del club.
            assert (await client.get("/club/admin/site")).status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_the_youtube_feed_is_read_without_trusting_it():
    from app.domains.club.videos import parse_feed

    xml = (
        "<feed><entry><yt:videoId>_CZLqZpNnn8</yt:videoId><media:title>Troféu &amp; Juvenil</media:title>"
        "<published>2026-06-23T10:00:00+00:00</published><media:statistics views=\"42\"/></entry>"
        "<entry><yt:videoId>bad id\"><script></yt:videoId><media:title>x</media:title></entry></feed>"
    )
    videos = parse_feed(xml)
    assert [(v["id"], v["title"], v["published"], v["views"]) for v in videos] == [
        ("_CZLqZpNnn8", "Troféu & Juvenil", "2026-06-23", 42)
    ]
    assert videos[0]["thumbnail"] == "https://i.ytimg.com/vi/_CZLqZpNnn8/hqdefault.jpg"


async def test_the_club_mini_site_is_cleaned_before_it_reaches_the_page(db, scope):
    """Storia, numeri, pilastri, novità e video: la segreteria scrive, il
    servizio ripulisce (ordine, limiti, indirizzi, solo l'id di YouTube) e
    la pagina pubblica mostra esattamente ciò che è stato salvato."""
    admin = await _user(db, scope, "admin")
    await _published_site(db, scope)
    site = await site_service.update_site(db, scope=scope, actor_user_id=admin.id, changes={
        "founded_year": 1985,
        "venue": "  Pavilhão Municipal  ",
        "highlights": [{"value": "40+", "label": "anos de judo"}, {"value": "", "label": "vuoto"}],
        "history": [
            {"year": 2010, "title": "Primeiro campeão nacional"},
            {"year": 1985, "title": "Fundação", "text": "Num ginásio emprestado."},
        ],
        "pillars": [{"title": "Respeito", "text": "No tatami e fora dele."}, {"title": " "}],
        "news": [
            {"date": date(2026, 3, 1), "title": "Torneio da Primavera"},
            {"date": date(2026, 9, 20), "title": "Abertura da época", "image_url": "https://media.example/x.jpg"},
        ],
        "videos": [
            {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "caption": "Estágio"},
            {"url": "https://youtu.be/dQw4w9WgXcQ"},
        ],
        "coaches": [{"name": "Ana", "grade": "Cinto preto 3.º dan", "bio": "Treinadora desde 2001."}],
    })
    assert site.venue == "Pavilhão Municipal"
    assert site.highlights == [{"value": "40+", "label": "anos de judo"}]
    assert [h["year"] for h in site.history] == [1985, 2010]
    assert [p["title"] for p in site.pillars] == ["Respeito"]
    assert [n["date"] for n in site.news] == ["2026-09-20", "2026-03-01"]
    assert site.videos == [{"youtube_id": "dQw4w9WgXcQ", "caption": "Estágio"}]
    assert site.coaches[0]["grade"] == "Cinto preto 3.º dan"

    page = await site_service.club_page(db, slug=await _slug(db, scope), today=TODAY)
    assert page["founded_year"] == 1985 and page["news"][0]["title"] == "Abertura da época"

    # Un iframe verso un sito qualsiasi non si può mettere; un link non web nemmeno.
    with pytest.raises(club_service.ClubValidationError):
        await site_service.update_site(db, scope=scope, actor_user_id=admin.id, changes={
            "videos": [{"url": "https://evil.example/watch?v=dQw4w9WgXcQ"}],
        })
    with pytest.raises(club_service.ClubValidationError):
        await site_service.update_site(db, scope=scope, actor_user_id=admin.id, changes={
            "news": [{"date": date(2026, 1, 1), "title": "x", "link_url": "javascript:alert(1)"}],
        })
    with pytest.raises(club_service.ClubValidationError):
        await site_service.update_site(db, scope=scope, actor_user_id=admin.id, changes={
            "pillars": [{"title": f"p{i}"} for i in range(site_service.MAX_PILLARS + 1)],
        })


def test_a_club_channel_feed_is_read_only_from_a_channel_link():
    from app.domains.club import videos

    assert videos.channel_id_from_url("https://www.youtube.com/channel/UCKyB7cQxPl56Mm3xsdxolFw") == "UCKyB7cQxPl56Mm3xsdxolFw"
    assert videos.channel_id_from_url("https://www.youtube.com/channel/UCKyB7cQxPl56Mm3xsdxolFw/videos") == "UCKyB7cQxPl56Mm3xsdxolFw"
    # Un @nome non si risolve senza le API di Google; un altro sito mai.
    assert videos.channel_id_from_url("https://www.youtube.com/@judoclube") is None
    assert videos.channel_id_from_url("https://evil.example/channel/UCKyB7cQxPl56Mm3xsdxolFw") is None
    assert videos.channel_id_from_url(None) is None
