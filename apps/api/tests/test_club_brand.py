"""La pagina del club come una pagina tutta sua (club/brand.py, club/site.py,
docs/club-portal.md, "La pagina del club").

Le promesse: un colore è un colore (niente altro finisce nel CSS), il testo
si legge sempre qualunque colore scelga il club, un'icona di Facebook porta
a Facebook, la pagina dice gruppi e orari come JAVBOT (i soldi solo se il
club lo vuole) e non porta mai dati personali; e l'unità dei corsi JAV
resta fuori come prima.
"""

import json
from datetime import date, time

import httpx
import pytest
from sqlalchemy import select

from app.domains.club import brand
from app.domains.club import site as site_service
from app.domains.club.models import Club, ClubCourse, ClubCourseSlot
from app.domains.club.service import ClubNotFoundError, ClubValidationError
from app.domains.club.site_models import ClubSite
from scripts import load_club_branding, load_official_prices
from tests.test_club_fees import _athlete, _plans, _user
from tests.test_club_site import _competition, _consent_and_publish, _result

TODAY = date(2026, 10, 14)


def test_colours_are_normalised_and_text_is_always_readable():
    assert brand.normalize_hex(" #e13f22 ") == "#E13F22"
    assert brand.normalize_hex("e32") == "#EE3322"
    assert brand.normalize_hex("") is None
    for bad in ("red", "#12345", "#GGGGGG", "url(javascript:x)", "#E13F22;background:url(x)"):
        with pytest.raises(brand.BrandColorError):
            brand.normalize_hex(bad)

    # Senza colori: JudoArteVida.
    jav = brand.theme(None, None, None)
    assert (jav["primary"], jav["accent"], jav["custom"]) == ("#E13F22", "#F3E017", False)

    for primary, accent in (("#6366F1", "#F8FF94"), ("#C92429", "#C4C4C6"), ("#000000", "#E13F22"),
                            ("#F8FF94", None), ("#808080", "#7F7F7F"), ("#FFFFFF", "#FFFFFF")):
        t = brand.theme(primary, None, accent)
        # Bottoni, titoli, scritte sulla copertina: almeno 4,5:1 (WCAG AA).
        assert brand.contrast(t["primary"], t["on_primary"]) >= 4.4
        assert brand.contrast(t["accent"], t["on_accent"]) >= 4.4
        assert brand.contrast(t["primary_text"], "#FFFFFF") >= brand.AA_TEXT
        assert brand.contrast(t["accent_on_dark"], brand.INK) >= brand.AA_TEXT
        # La copertina porta testo bianco, anche con un club giallo pallido.
        assert brand.contrast(t["cover_from"], "#FFFFFF") >= 3.0
        assert brand.contrast(t["cover_to"], "#FFFFFF") >= brand.AA_TEXT

    # Il blu di Lagos sul bianco è appena sotto 4,5: per i titoli si scurisce,
    # e l'editor lo dice.
    lagos = brand.theme("#6366F1", "#F8FF94", "#F8FF94")
    assert lagos["primary_text"] != "#6366F1" and "PRIMARY_DARKENED" in lagos["warnings"]
    assert "ACCENT_LIKE_PRIMARY" in brand.theme("#C92429", None, "#C92429")["warnings"]


async def test_the_editor_accepts_only_colours_and_real_social_links(db, scope):
    admin = await _user(db, scope, "admin")
    site = await site_service.update_site(db, scope=scope, actor_user_id=admin.id, changes={
        "brand_primary": "c92429", "brand_accent": "#ccc",
        "facebook_url": "facebook.com/judoclubedealbufeira/",
        "instagram_url": "http://www.instagram.com/clube",
        "youtube_url": "https://youtu.be/abcdefghijk",
    })
    assert (site.brand_primary, site.brand_accent, site.brand_secondary) == ("#C92429", "#CCCCCC", None)
    assert site.facebook_url == "https://facebook.com/judoclubedealbufeira/"
    assert site.instagram_url == "https://www.instagram.com/clube"
    assert site_service.admin_site_dict(site, await db.get(Club, scope.club_id))["theme"]["primary"] == "#C92429"

    for field, value in (
        ("brand_primary", "rosso"),
        ("facebook_url", "https://www.instagram.com/clube"),         # un'icona di Facebook porta a Facebook
        ("instagram_url", "https://instagram.com.evil.example/x"),
        ("youtube_url", "javascript:alert(1)"),
        ("facebook_url", "https://user:pw@facebook.com/x"),
        ("facebook_url", "https://facebook.com/"),                    # la home di Facebook non è il club
    ):
        with pytest.raises(ClubValidationError):
            await site_service.update_site(db, scope=scope, actor_user_id=admin.id, changes={field: value})
    # "" cancella, come gli altri campi.
    cleared = await site_service.update_site(db, scope=scope, actor_user_id=admin.id,
                                             changes={"brand_primary": "", "facebook_url": ""})
    assert cleared.brand_primary is None and cleared.facebook_url is None


async def test_the_fan_page_carries_brand_groups_and_ranking_but_nothing_personal(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    site = await site_service.get_site(db, scope=scope)
    await site_service.update_site(db, scope=scope, actor_user_id=admin.id, changes={
        "published": True, "brand_primary": "#6366F1", "brand_accent": "#F8FF94",
        "facebook_url": "https://www.facebook.com/judoclubedelagos/",
    })
    slug = (await db.get(Club, scope.club_id)).slug
    course = ClubCourse(**scope.columns(), name="Infantis", min_age=4, max_age=7, active=True)
    db.add(course)
    await db.flush()
    db.add(ClubCourseSlot(course_id=course.id, weekday=1, starts_at=time(18, 0), ends_at=time(19, 0)))
    await db.commit()
    parent = await _user(db, scope)
    shown = await _athlete(db, scope, parent, birth_date=date(2015, 3, 3), first_name="Tiago", last_name="Matias",
                           fiscal_code="MTSTGO15C03Z128X")
    hidden = await _athlete(db, scope, parent, birth_date=date(2016, 6, 6), first_name="Rita", last_name="Segreta")
    await _consent_and_publish(db, scope, shown, parent, admin)
    comp = await _competition(db, scope, admin, starts_on=date(2026, 10, 4))
    await _result(db, comp, shown, admin, 1)
    await _result(db, comp, hidden, admin, 2)

    page = await site_service.club_page(db, slug=slug, today=TODAY)
    assert page["theme"]["primary"] == "#6366F1" and page["theme"]["custom"] is True
    assert page["facebook_url"] == "https://www.facebook.com/judoclubedelagos/"
    # I gruppi come li dice JAVBOT: età e allenamenti sì, i soldi no (show_prices spento).
    kids = next(g for g in page["groups"] if g["name"] == "Bambini 4-7")
    assert kids["slots"] == [{"weekday": 1, "starts_at": "18:00", "ends_at": "19:00", "course": "Infantis"}]
    assert all(g["monthly_price_cents"] is None and g["description"] is None for g in page["groups"])
    # Il ranking del club: solo chi è pubblico, con il link alla sua scheda (l'id).
    assert [(r["id"], r["position"]) for r in page["ranking"]] == [(shown.id, 1)]

    site.show_prices = True
    await db.commit()
    page = await site_service.club_page(db, slug=slug, today=TODAY)
    kids = next(g for g in page["groups"] if g["name"] == "Bambini 4-7")
    assert (kids["monthly_price_cents"], kids["enrollment_price_cents"], kids["due_day"]) == (3000, 2500, 10)

    from app.core.db import get_db
    from app.main import app

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/api") as client:
            res = await client.get(f"/public-site/clubs/{slug}")
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["theme"]["on_primary"] in ("#FFFFFF", "#0A0A0A") and body["groups"] and body["ranking"]
    everything = json.dumps(body)
    for secret in ("Matias", "Segreta", "Rita", "2015-03-03", "MTSTGO15C03Z128X", "birth", "fiscal", "weight",
                   "guardian", "fee", str(parent.id), parent.email, "ip_hash"):
        assert secret not in everything, secret


async def test_the_jav_courses_unit_stays_off_the_club_pages(db, organization_id):
    from tests.test_jav_courses import _unit

    unit, actor = await _unit(db, organization_id)
    await site_service.get_site(db, scope=unit)
    await site_service.update_site(db, scope=unit, actor_user_id=actor.id,
                                   changes={"published": True, "brand_primary": "#123456"})
    slug = (await db.get(Club, unit.club_id)).slug
    with pytest.raises(ClubNotFoundError):
        await site_service.club_page(db, slug=slug, today=TODAY)
    assert slug not in [c["slug"] for c in await site_service.list_public_clubs(db)]
    assert (await site_service.public_courses(db))["unit"]["slug"] == slug


async def test_the_branding_loader_is_a_dry_run_by_default_and_idempotent(db, scope):
    club = await db.get(Club, scope.club_id)
    club.slug = "judo-clube-de-albufeira"
    await db.commit()

    planned = await load_club_branding.load(db, club.slug, apply=False)
    assert planned and (await db.execute(select(ClubSite).where(ClubSite.club_id == club.id))).first() is None

    done = await load_club_branding.load(db, club.slug, apply=True)
    assert done == planned
    site = (await db.execute(select(ClubSite).where(ClubSite.club_id == club.id))).scalars().one()
    assert (site.brand_primary, site.brand_accent) == ("#C92429", "#C4C4C6")
    assert site.facebook_url == "https://www.facebook.com/judoclubedealbufeira/"
    assert site.youtube_url.startswith("https://www.youtube.com/channel/")
    assert site.logo_url and f"club-sites/{club.id}/logo/" in site.logo_url
    assert site.published is False  # la pagina la pubblica la segreteria, non lo script
    assert await load_club_branding.load(db, club.slug, apply=True) == []


async def test_alvor_gets_its_weekly_calendar(db, scope):
    club = await db.get(Club, scope.club_id)
    club.slug = "judo-team-matias-luwawa"
    db.add(ClubSite(**scope.columns(), city="Alvor", gallery=[], coaches=[], published=True))
    await db.commit()

    await load_official_prices.load(db, club.slug, apply=True)
    assert await load_official_prices.load(db, club.slug, apply=True) == []
    slots = (await db.execute(
        select(ClubCourse.name, ClubCourse.min_age, ClubCourse.max_age, ClubCourseSlot.weekday,
               ClubCourseSlot.starts_at, ClubCourseSlot.ends_at)
        .join(ClubCourseSlot, ClubCourseSlot.course_id == ClubCourse.id).where(ClubCourse.club_id == club.id)
        .order_by(ClubCourseSlot.weekday, ClubCourseSlot.starts_at)
    )).all()
    assert slots == [
        ("Grupos 2 e 3 · Formação e Competição", 8, None, 0, time(19, 0), time(22, 0)),
        ("Grupo 1 · Iniciação", 2, 7, 1, time(18, 30), time(19, 30)),
        ("Grupos 2 e 3 · Formação e Competição", 8, None, 2, time(19, 0), time(22, 0)),
        ("Grupo 1 · Iniciação", 2, 7, 3, time(18, 30), time(19, 30)),
        ("Grupos 2 e 3 · Formação e Competição", 8, None, 4, time(19, 0), time(22, 0)),
    ]
    page = await site_service.club_page(db, slug=club.slug, today=TODAY)
    groups = {g["name"]: [s["weekday"] for s in g["slots"]] for g in page["groups"]}
    assert groups["Grupo 1 · Iniciação"] == [1, 3]
    assert groups["Grupo 2 · Formação"] == [0, 2, 4]
    assert groups["Grupo 3 · Competição, Manutenção e Veteranos"] == [0, 2, 4]
