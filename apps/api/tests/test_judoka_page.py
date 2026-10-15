"""La scheda pubblica del judoca, in stile IJF (docs/club-portal.md, "Sito
pubblico" → "La scheda del judoca").

Le promesse: la scheda dice tutto ciò che il gestionale sa già di sportivo
(cinture con le date, risultati, prove in programma, posto nel ranking,
medaglie) più ciò che la segreteria scrive (profilo IJF, tecnica, guardia) e
le foto e i video che pubblica uno per uno; niente esce senza consenso e
pubblicazione, foto e video solo con il permesso della foto, gli atleti dei
corsi JAV mai, e nessun dato personale arriva al browser.
"""

import json
from datetime import date

import httpx
import pytest
from sqlalchemy import update

from app.domains.club import service as club_service
from app.domains.club import site as site_service
from app.domains.club.models import ClubCompetitionEntry
from app.domains.club.site_models import ClubAthleteMedia
from tests.test_club_fees import _athlete, _plans, _user
from tests.test_club_multi import _other_club
from tests.test_club_site import _competition, _consent_and_publish, _published_site, _result

TODAY = date(2026, 10, 14)
#: Un PNG di 1×1 pixel: abbastanza vero da passare il controllo dei byte magici.
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)
IJF = "https://www.ijf.org/judoka/12345"


async def _api(db):
    from app.core.db import get_db
    from app.main import app

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    return app, httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/api")


async def _world(db, scope):
    """Un club pubblico con Tiago (consenso, foto permessa, pubblicato), un
    rivale della stessa fascia con più punti, una gara fatta e una in
    programma."""
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    await _published_site(db, scope, city="Lagos")
    parent = await _user(db, scope)
    tiago = await _athlete(db, scope, parent, birth_date=date(2015, 3, 3), first_name="Tiago", last_name="Matias",
                           fiscal_code="MTSTGO15C03Z128X")
    tiago.photo_url = "https://example.demo/media/tiago.jpg"
    tiago.weight_kg = 37
    rival = await _athlete(db, scope, parent, birth_date=date(2015, 5, 5), first_name="Rui", last_name="Rival")
    await _consent_and_publish(db, scope, tiago, parent, admin, show_photo=True)
    await _consent_and_publish(db, scope, rival, parent, admin)
    await club_service.award_belt(db, athlete=tiago, grade="YELLOW", awarded_on=date(2026, 10, 16),
                                  actor_user_id=admin.id)
    past = await _competition(db, scope, admin, starts_on=date(2026, 10, 4))
    past.location = "Portimão"
    await _result(db, past, tiago, admin, 2)
    await _result(db, past, rival, admin, 1)
    upcoming = await _competition(db, scope, admin, starts_on=date(2026, 11, 7), name="Open de Lisboa")
    await _result(db, upcoming, tiago, admin, None)
    return admin, parent, tiago, rival, past, upcoming


async def test_the_page_carries_the_ijf_style_card(db, scope):
    admin, _parent, tiago, _rival, past, upcoming = await _world(db, scope)
    await site_service.update_athlete_page(
        db, scope=scope, athlete_id=tiago.id, actor_user_id=admin.id,
        changes={"ijf_profile_url": IJF, "favorite_technique": " Seoi-nage ", "dominant_side": "left",
                 "bio": "Judo desde os 5 anos"},
    )
    page = await site_service.add_athlete_photo(
        db, scope=scope, athlete_id=tiago.id, actor_user_id=admin.id, file_bytes=PNG, content_type="image/png",
        caption="Pódio em Portimão",
    )
    [photo] = page["media"]
    assert photo["published"] is False  # una foto caricata non è ancora sul web
    page = await site_service.add_athlete_video(
        db, scope=scope, athlete_id=tiago.id, actor_user_id=admin.id, url="https://youtu.be/_CZLqZpNnn8?t=3",
    )
    video = next(m for m in page["media"] if m["kind"] == "VIDEO")
    assert video["youtube_id"] == "_CZLqZpNnn8"
    for media in (photo, video):
        await site_service.update_athlete_media(
            db, scope=scope, athlete_id=tiago.id, media_id=media["id"], actor_user_id=admin.id,
            changes={"published": True},
        )
    # Il secondo video resta in bozza.
    await site_service.add_athlete_video(
        db, scope=scope, athlete_id=tiago.id, actor_user_id=admin.id,
        url="https://www.youtube.com/watch?v=RIZHYD0y1mw",
    )

    profile = await site_service.judoka_profile(db, athlete_id=tiago.id, today=TODAY)
    assert profile["display_name"] == "Tiago M."
    assert profile["photo_url"] == "https://example.demo/media/tiago.jpg"
    assert profile["belt"] == "YELLOW"
    assert [b["grade"] for b in profile["belt_history"]] == ["WHITE", "YELLOW"]
    assert profile["belt_history"][-1]["awarded_on"] == date(2026, 10, 16)
    assert profile["age_band"] == "GRUPO_2"
    assert profile["category"] == "-38 kg"
    assert (profile["silver"], profile["gold"], profile["competitions"]) == (1, 0, 1)
    # Il rivale ha vinto: Tiago è secondo su due nella sua fascia.
    assert profile["ranking"] == {"position": 2, "total": 2, "age_band": "GRUPO_2", "points": 3}
    [result] = profile["results"]
    assert (result["event_id"], result["placement"], result["location"]) == (past.id, 2, "Portimão")
    assert [(u["id"], u["category"]) for u in profile["upcoming"]] == [(upcoming.id, "-38 kg")]
    assert profile["ijf_profile_url"] == IJF
    assert (profile["favorite_technique"], profile["dominant_side"]) == ("Seoi-nage", "LEFT")
    assert profile["bio"] == "Judo desde os 5 anos"
    assert [p["caption"] for p in profile["photos"]] == ["Pódio em Portimão"]
    assert [v["youtube_id"] for v in profile["videos"]] == ["_CZLqZpNnn8"]  # quello in bozza no

    # Il ranking e la scheda si leggono anche dall'API vera, e il ranking
    # porta l'id con cui si apre la scheda.
    app, client = await _api(db)
    try:
        async with client:
            body = (await client.get(f"/public-site/judoka/{tiago.id}")).json()
            ranking = (await client.get("/public-site/ranking")).json()
    finally:
        app.dependency_overrides.clear()
    assert body["ranking"]["position"] == 2 and body["videos"][0]["youtube_id"] == "_CZLqZpNnn8"
    assert str(tiago.id) in {r["id"] for r in ranking["rows"]}


async def test_unpublished_media_and_no_photo_permission_stay_private(db, scope):
    admin, parent, tiago, _rival, _past, _upcoming = await _world(db, scope)
    page = await site_service.add_athlete_photo(
        db, scope=scope, athlete_id=tiago.id, actor_user_id=admin.id, file_bytes=PNG, content_type="image/png",
    )
    photo_url = page["media"][0]["url"]
    assert (await site_service.judoka_profile(db, athlete_id=tiago.id, today=TODAY))["photos"] == []

    await site_service.update_athlete_media(
        db, scope=scope, athlete_id=tiago.id, media_id=page["media"][0]["id"], actor_user_id=admin.id,
        changes={"published": True},
    )
    assert [p["url"] for p in (await site_service.judoka_profile(db, athlete_id=tiago.id, today=TODAY))["photos"]] \
        == [photo_url]

    # La famiglia toglie il permesso della foto: spariscono anche foto e video.
    await site_service.update_consent(db, athlete=tiago, actor_user_id=parent.id, changes={"show_photo": False})
    profile = await site_service.judoka_profile(db, athlete_id=tiago.id, today=TODAY)
    assert profile["photos"] == [] and profile["videos"] == [] and profile["photo_url"] is None

    # Ritira il consenso: tutto torna privato, e un nuovo consenso non
    # ripubblica né la scheda né i media.
    await site_service.update_consent(db, athlete=tiago, actor_user_id=parent.id, changes={"consent": False})
    with pytest.raises(club_service.ClubNotFoundError):
        await site_service.judoka_profile(db, athlete_id=tiago.id, today=TODAY)
    admin_view = await site_service.athlete_page_admin(db, scope=scope, athlete_id=tiago.id)
    assert admin_view["live"] is False and [m["published"] for m in admin_view["media"]] == [False]

    # Togliere una foto la toglie davvero.
    admin_view = await site_service.delete_athlete_media(
        db, scope=scope, athlete_id=tiago.id, media_id=admin_view["media"][0]["id"], actor_user_id=admin.id,
    )
    assert admin_view["media"] == []


@pytest.mark.parametrize("url", [
    "https://www.ijf.org/judoka/12345",
    "https://www.ijf.org/judoka/12345/results",
    "https://ijf.org/judoka/7",
    "https://judobase.ijf.org/#/competitor/profile/4321/results",
    "https://judobase.ijf.org/#/competitor/profile/4321",
])
def test_a_real_ijf_profile_link_is_accepted(url):
    assert site_service.check_ijf_url(f"  {url} ") == url


@pytest.mark.parametrize("url", [
    "http://www.ijf.org/judoka/12345",            # niente http in chiaro
    "https://www.ijf.org/",                        # non è una scheda
    "https://www.ijf.org/judoka/abc",
    "https://www.ijf.org.evil.example/judoka/1",   # un dominio che ci somiglia
    "https://evil.example/www.ijf.org/judoka/1",
    "https://user@www.ijf.org/judoka/1",
    "https://judobase.ijf.org/#/competition/2024",
    "javascript:alert(1)",
])
def test_anything_else_is_refused_with_a_clear_message(url):
    with pytest.raises(club_service.ClubValidationError, match="IJF"):
        site_service.check_ijf_url(url)


def test_videos_are_youtube_only_and_stored_as_ids():
    for url in ("https://www.youtube.com/watch?v=_CZLqZpNnn8&t=1", "https://youtu.be/_CZLqZpNnn8",
                "https://m.youtube.com/shorts/_CZLqZpNnn8", "https://www.youtube-nocookie.com/embed/_CZLqZpNnn8"):
        assert site_service.youtube_id_from_url(url) == "_CZLqZpNnn8"
    for url in ("https://vimeo.com/123", "https://www.youtube.com/watch?v=short", "https://youtube.com.evil/x",
                "_CZLqZpNnn8", "https://www.youtube.com/@ml8126"):
        with pytest.raises(club_service.ClubValidationError):
            site_service.youtube_id_from_url(url)


async def test_the_page_texts_are_validated_and_club_scoped(db, scope):
    admin, _parent, tiago, *_ = await _world(db, scope)
    with pytest.raises(club_service.ClubValidationError):
        await site_service.update_athlete_page(db, scope=scope, athlete_id=tiago.id, actor_user_id=admin.id,
                                               changes={"ijf_profile_url": "https://example.com/judoka/1"})
    with pytest.raises(club_service.ClubValidationError):
        await site_service.update_athlete_page(db, scope=scope, athlete_id=tiago.id, actor_user_id=admin.id,
                                               changes={"dominant_side": "BOTH"})
    await site_service.add_athlete_video(db, scope=scope, athlete_id=tiago.id, actor_user_id=admin.id,
                                         url="https://youtu.be/_CZLqZpNnn8")
    with pytest.raises(club_service.ClubValidationError, match="già"):
        await site_service.add_athlete_video(db, scope=scope, athlete_id=tiago.id, actor_user_id=admin.id,
                                             url="https://www.youtube.com/watch?v=_CZLqZpNnn8")
    # "" cancella.
    await site_service.update_athlete_page(db, scope=scope, athlete_id=tiago.id, actor_user_id=admin.id,
                                           changes={"ijf_profile_url": IJF})
    page = await site_service.update_athlete_page(db, scope=scope, athlete_id=tiago.id, actor_user_id=admin.id,
                                                  changes={"ijf_profile_url": ""})
    assert page["ijf_profile_url"] is None

    # Un altro club non vede né tocca la scheda.
    lagos = await _other_club(db, scope.organization_id)
    with pytest.raises(club_service.ClubNotFoundError):
        await site_service.athlete_page_admin(db, scope=lagos, athlete_id=tiago.id)
    with pytest.raises(club_service.ClubNotFoundError):
        await site_service.update_athlete_page(db, scope=lagos, athlete_id=tiago.id, actor_user_id=admin.id,
                                               changes={"bio": "x"})


async def test_admin_routes_are_for_the_club_only(db, scope, monkeypatch):
    from tests.test_club_api import _client

    admin, parent, tiago, *_ = await _world(db, scope)
    app, client = await _client(db, monkeypatch, user=admin, scope=scope, granted={"club.manage"})
    try:
        async with client:
            res = await client.put(f"/club/admin/site/athletes/{tiago.id}/page",
                                   json={"ijf_profile_url": IJF, "favorite_technique": "Uchi-mata"})
            assert res.status_code == 200, res.text
            assert res.json()["live"] is True and res.json()["public_path"] == f"/judocas/{tiago.id}"
            res = await client.put(f"/club/admin/site/athletes/{tiago.id}/page",
                                   json={"ijf_profile_url": "https://example.com"})
            assert res.status_code == 400 and "IJF" in res.json()["detail"]
            res = await client.post(f"/club/admin/site/athletes/{tiago.id}/page/videos",
                                    json={"url": "https://youtu.be/_CZLqZpNnn8"})
            assert res.status_code == 200, res.text
            media_id = res.json()["media"][0]["id"]
            res = await client.patch(f"/club/admin/site/athletes/{tiago.id}/page/media/{media_id}",
                                     json={"published": True})
            assert res.status_code == 200 and res.json()["media"][0]["published"] is True
    finally:
        app.dependency_overrides.clear()

    app, client = await _client(db, monkeypatch, user=parent, scope=scope, granted={"club.family"})
    try:
        async with client:
            assert (await client.get(f"/club/admin/site/athletes/{tiago.id}/page")).status_code == 403
    finally:
        app.dependency_overrides.clear()


async def test_jav_course_athletes_have_no_page_even_with_media(db, organization_id):
    from tests.test_jav_courses import _public_world

    unit, actor, _shown, _hidden, kid, _comp, _parent = await _public_world(db, organization_id)
    # Media forzati a mano, pubblicati: il sito non li guarda nemmeno.
    db.add(ClubAthleteMedia(**unit.columns(), athlete_id=kid.id, kind="VIDEO", youtube_id="_CZLqZpNnn8",
                            published=True, created_by_user_id=actor.id))
    db.add(ClubAthleteMedia(**unit.columns(), athlete_id=kid.id, kind="PHOTO",
                            url="https://example.demo/media/escolar.jpg", published=True))
    await db.commit()

    with pytest.raises(club_service.ClubNotFoundError):
        await site_service.judoka_profile(db, athlete_id=kid.id, today=TODAY)
    # E la segreteria dell'unità non può nemmeno preparare la scheda.
    for call in (
        site_service.athlete_page_admin(db, scope=unit, athlete_id=kid.id),
        site_service.update_athlete_page(db, scope=unit, athlete_id=kid.id, actor_user_id=actor.id,
                                         changes={"ijf_profile_url": IJF}),
        site_service.add_athlete_video(db, scope=unit, athlete_id=kid.id, actor_user_id=actor.id,
                                       url="https://youtu.be/RIZHYD0y1mw"),
    ):
        with pytest.raises(club_service.ClubValidationError, match="corsi JAV"):
            await call

    app, client = await _api(db)
    try:
        async with client:
            assert (await client.get(f"/public-site/judoka/{kid.id}")).status_code == 404
            everything = json.dumps([(await client.get(p)).json() for p in ("/public-site/home", "/public-site/ranking")])
    finally:
        app.dependency_overrides.clear()
    for secret in ("_CZLqZpNnn8", "escolar.jpg", str(kid.id), "Tiago"):
        assert secret not in everything, secret


async def test_no_personal_data_reaches_the_browser(db, scope):
    admin, parent, tiago, rival, _past, _upcoming = await _world(db, scope)
    await site_service.update_athlete_page(db, scope=scope, athlete_id=tiago.id, actor_user_id=admin.id,
                                           changes={"ijf_profile_url": IJF})
    page = await site_service.add_athlete_photo(
        db, scope=scope, athlete_id=tiago.id, actor_user_id=admin.id, file_bytes=PNG, content_type="image/png",
    )
    draft_url = page["media"][0]["url"]
    # Un'iscrizione ritirata non è una prova in programma.
    withdrawn = await _competition(db, scope, admin, starts_on=date(2026, 12, 5), name="Torneio Ritirado")
    await _result(db, withdrawn, tiago, admin, None)
    await db.execute(update(ClubCompetitionEntry).where(ClubCompetitionEntry.competition_id == withdrawn.id)
                     .values(status="WITHDRAWN"))
    await db.commit()

    app, client = await _api(db)
    try:
        async with client:
            res = await client.get(f"/public-site/judoka/{tiago.id}")
            assert res.status_code == 200, res.text
            body = res.json()
    finally:
        app.dependency_overrides.clear()
    assert "Torneio Ritirado" not in json.dumps(body)
    everything = json.dumps(body)
    for secret in ("Matias", "2015-03-03", "MTSTGO15C03Z128X", "birth", "fiscal", "weight", "guardian",
                   "email", "phone", "address", parent.email, str(parent.id), str(admin.id), draft_url,
                   "consent", "created_by"):
        assert secret not in everything, secret
