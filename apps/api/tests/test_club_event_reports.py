"""Risultati dal treinador, scheda dell'evento e relatórios, attraverso le
rotte vere (docs/club-portal.md, "Risultati dal treinador, scheda
dell'evento e relatórios").

Le promesse: il piazzamento scritto dal treinador conta nel Jav Ranking
esattamente come quello della segreteria; un treinador di un altro club non
scrive niente; i contatti li vede solo lo staff; un treinador tocca solo i
suoi relatórios e solo la segreteria stampa il PDF, uno per periodo.
"""

import uuid
from datetime import date, timedelta

import httpx

from app.domains.club import competitions as competitions_service
from app.domains.club import event_reports
from app.domains.club.models import Club
from app.domains.club.scope import ClubScope
from app.domains.customers.models import Customer
from tests.test_club_fees import _athlete, _plans, _user

TODAY = date.today()


async def _client(db, monkeypatch, *, user, scope, granted: set[str]):
    from app.core import deps
    from app.core.db import get_db
    from app.core.deps import CurrentUser, get_current_user
    from app.domains.club import competition_staff_router
    from app.domains.club import router as club_router
    from app.domains.club import scope as scope_module
    from app.main import app

    async def _codes(*args, **kwargs):
        return granted

    for module in (deps, club_router, scope_module, competition_staff_router):
        monkeypatch.setattr(module, "get_permission_codes_for_user", _codes)
    from app.core import rate_limit
    monkeypatch.setattr(rate_limit, "_redis_client", None)

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=user.id, organization_id=scope.organization_id, roles=["CUSTOMER"]
    )
    return app, httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/api")


async def _setup(db, scope, *, starts_on=TODAY + timedelta(days=10), name="Open de Faro"):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope, "pai")
    db.add(Customer(organization_id=scope.organization_id, user_id=parent.id, kind="PRIVATE",
                    email=parent.email, phone="912000111"))
    await db.commit()
    kid = await _athlete(db, scope, parent, birth_date=date(TODAY.year - 12, 3, 1), first_name="Tiago",
                         last_name="Lopes", today=TODAY)
    comp = await _comp(db, scope, admin, starts_on=starts_on, name=name)
    entry = await competitions_service.register_entry(
        db, competition=comp, athlete=kid, actor_user_id=parent.id, category=None, today=starts_on - timedelta(days=5),
    )
    return admin, parent, kid, comp, entry


async def _comp(db, scope, admin, *, starts_on, name):
    return await competitions_service.create_competition(db, scope=scope, actor_user_id=admin.id, data={
        "name": name, "starts_on": starts_on, "ends_on": starts_on, "location": "Faro",
        "registration_deadline": starts_on - timedelta(days=3),
        "level": "NATIONAL", "fee_cents": 0, "requires_agonistic_certificate": False,
        "description": "Prova nacional de juvenis.",
    })


async def _other_club(db, scope) -> ClubScope:
    club = Club(organization_id=scope.organization_id, name="Outro clube", slug=f"c-{uuid.uuid4().hex[:8]}", settings={})
    db.add(club)
    await db.commit()
    return ClubScope(organization_id=scope.organization_id, club_id=club.id)


async def test_coach_results_feed_the_ranking_and_other_clubs_cannot_write(db, scope, monkeypatch):
    admin, _parent, kid, comp, entry = await _setup(db, scope)
    coach = await _user(db, scope, "treinador")
    other = await _other_club(db, scope)
    stranger = await _user(db, other, "treinador-fora")

    app, client = await _client(db, monkeypatch, user=coach, scope=scope, granted={"club.instruct"})
    try:
        async with client:
            listed = (await client.get("/club/staff/competitions")).json()
            assert [(c["name"], c["entries_count"]) for c in listed] == [("Open de Faro", 1)]
            # Alla pesata: peso e categoria, la gara resta aperta.
            r = await client.patch(f"/club/staff/competitions/{comp.id}/entries/{entry.id}",
                                   json={"weight_kg": "38.4", "category": "-40 kg"})
            assert r.status_code == 200, r.text
            assert r.json()["category"] == "-40 kg" and r.json()["placement"] is None
            await db.refresh(comp)
            assert comp.status == "OPEN"
            # Dopo la gara: l'oro e una nota.
            r = await client.patch(f"/club/staff/competitions/{comp.id}/entries/{entry.id}",
                                   json={"placement": 1, "result_notes": "Três ippons"})
            assert r.status_code == 200, r.text
            assert r.json()["points"] == competitions_service.points_for(placement=1, level="NATIONAL")
            bad = await client.patch(f"/club/staff/competitions/{comp.id}/entries/{entry.id}", json={"placement": 4})
            assert bad.status_code == 400
            detail = (await client.get(f"/club/staff/competitions/{comp.id}")).json()
            row = detail["entries"][0]
            assert row["athlete_name"] == "Tiago Lopes" and row["weight_kg"] == "38.4"
            # Minorenne: il contatto è dell'encarregado.
            assert row["contact"]["phone"] == "912000111" and row["contact"]["is_guardian"]
    finally:
        app.dependency_overrides.clear()

    # Come la segreteria: la gara è DONE e i punti sono nel ranking.
    await db.refresh(comp)
    assert comp.status == "DONE"
    rows = await competitions_service.ranking(db, scope=scope, season=comp.starts_on.year, club_only=True)
    assert [(r["athlete_id"], r["points"], r["gold"]) for r in rows] == [(kid.id, 15, 1)]

    app, client = await _client(db, monkeypatch, user=stranger, scope=other, granted={"club.instruct"})
    try:
        async with client:
            r = await client.patch(f"/club/staff/competitions/{comp.id}/entries/{entry.id}", json={"placement": 3})
            assert r.status_code == 404
            assert (await client.get(f"/club/staff/competitions/{comp.id}")).status_code == 404
    finally:
        app.dependency_overrides.clear()
    await db.refresh(entry)
    assert entry.placement == 1

    # Una famiglia non è staff: niente rotte del treinador, e la scheda
    # senza contatti, con nome e iniziale.
    app, client = await _client(db, monkeypatch, user=admin, scope=scope, granted={"club.athlete", "club.family"})
    try:
        async with client:
            assert (await client.patch(f"/club/staff/competitions/{comp.id}/entries/{entry.id}",
                                       json={"placement": 2})).status_code == 403
            seen = (await client.get(f"/club/calendar/events/{comp.id}")).json()
            assert seen["description"] == "Prova nacional de juvenis."
            assert seen["entries"][0]["athlete_name"] == "Tiago L."
            assert seen["entries"][0]["contact"] is None and seen["entries"][0]["weight_kg"] is None
    finally:
        app.dependency_overrides.clear()


async def test_reports_crud_permissions_and_pdf_per_period(db, scope, monkeypatch):
    past = TODAY - timedelta(days=40)
    admin, _parent, _kid, comp, entry = await _setup(db, scope, starts_on=past, name="Taça de Lagos")
    await competitions_service.record_results(db, scope=scope, competition_id=comp.id, actor_user_id=admin.id,
                                              results=[(entry.id, 2)])
    later = await _comp(db, scope, admin, starts_on=past + timedelta(days=35), name="Estágio de Sagres")
    coach = await _user(db, scope, "treinador")
    colleague = await _user(db, scope, "colega")

    app, client = await _client(db, monkeypatch, user=coach, scope=scope, granted={"club.instruct"})
    try:
        async with client:
            r = await client.post("/club/staff/event-reports", json={
                "competition_id": str(comp.id), "title": "Lagos, uma prata",
                "narrative": "Correu bem.\n\nO Tiago lutou muito.",
                "costs": [{"kind": "FUEL", "amount_cents": 4500, "note": "Carrinha"},
                          {"kind": "FOOD", "amount_cents": 2350}],
            })
            assert r.status_code == 201, r.text
            report = r.json()
            assert report["total_cents"] == 6850
            assert [(x["athlete_name"], x["placement"]) for x in report["results"]] == [("Tiago Lopes", 2)]
            again = await client.post("/club/staff/event-reports", json={"competition_id": str(comp.id)})
            assert again.status_code == 400
            r = await client.patch(f"/club/staff/event-reports/{report['id']}",
                                   json={"costs": [{"kind": "HOTEL", "amount_cents": 12000, "note": "2 noites"}]})
            assert r.json()["total_cents"] == 12000
            r = await client.post(f"/club/staff/event-reports/{report['id']}/photos",
                                  files={"file": ("f.png", _png(), "image/png")})
            assert r.status_code == 201, r.text
            photo = r.json()["photos"][0]
            assert photo["url"]
            # Il treinador non esporta: è della segreteria.
            pdf = await client.get(f"/club/admin/event-reports/pdf?from={past}&to={TODAY}")
            assert pdf.status_code == 403
            second = await client.post("/club/staff/event-reports", json={"competition_id": str(later.id)})
            assert second.status_code == 201
    finally:
        app.dependency_overrides.clear()

    app, client = await _client(db, monkeypatch, user=colleague, scope=scope, granted={"club.instruct"})
    try:
        async with client:
            assert (await client.get("/club/staff/event-reports")).json() == []
            assert (await client.get(f"/club/staff/event-reports/{report['id']}")).status_code == 404
            assert (await client.patch(f"/club/staff/event-reports/{report['id']}", json={"title": "Meu"})).status_code == 404
            assert (await client.delete(f"/club/staff/event-reports/{report['id']}")).status_code == 404
    finally:
        app.dependency_overrides.clear()

    app, client = await _client(db, monkeypatch, user=admin, scope=scope, granted={"club.instruct", "club.manage"})
    try:
        async with client:
            all_reports = (await client.get("/club/staff/event-reports")).json()
            assert len(all_reports) == 2 and all(r["can_edit"] for r in all_reports)
            r = await client.patch(f"/club/staff/event-reports/{report['id']}", json={"title": "Lagos (revisto)"})
            assert r.status_code == 200 and r.json()["title"] == "Lagos (revisto)"
            whole = await client.get(f"/club/admin/event-reports/pdf?from={past - timedelta(days=1)}&to={TODAY}")
            assert whole.status_code == 200
            assert whole.content.startswith(b"%PDF") and len(whole.content) > 3000
            assert whole.headers["x-report-count"] == "2"
            # Un periodo che prende solo il primo evento: un PDF con un relatório.
            one = await client.get(f"/club/admin/event-reports/pdf?from={past}&to={past + timedelta(days=5)}")
            assert one.headers["x-report-count"] == "1" and one.content.startswith(b"%PDF")
            r = await client.delete(f"/club/staff/event-reports/{report['id']}/photos/{photo['id']}")
            assert r.json()["photos"] == []
            assert (await client.delete(f"/club/staff/event-reports/{report['id']}")).status_code == 204
            assert len((await client.get("/club/staff/event-reports")).json()) == 1
    finally:
        app.dependency_overrides.clear()


def _png() -> bytes:
    import io

    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 40, 30)).save(out, format="PNG")
    return out.getvalue()


def test_empty_period_still_makes_a_pdf():
    pdf = event_reports.render_pdf(reports=[], date_from=date(2026, 1, 1), date_to=date(2026, 12, 31),
                                   club_name="Clube", generated_on=date(2026, 10, 17))
    assert pdf.startswith(b"%PDF") and len(pdf) > 1500
