"""L'area dell'atleta, attraverso le rotte vere: le prove con «Voglio
partecipare», il riquadro dei soldi con l'aiuto del club, e la prova di
pagamento dall'area.

Le promesse: l'atleta vede le prove aperte e avvisa il titolare una volta
sola; il titolare non «chiede a sé stesso»; un costo pagato dal club entra nel
wallet come ricarica più addebito (il saldo non cambia) e si somma nell'aiuto;
un minorenne non paga dalla sua area, il titolare sì.
"""

from datetime import date, timedelta

import httpx

from app.domains.club import athlete_access
from app.domains.club import competitions as competitions_service
from app.domains.rbac.models import Role
from tests.test_club_fees import PNG, _athlete, _plans, _user


async def _client(db, monkeypatch, *, user, scope, granted: set[str]):
    from app.core import deps
    from app.core.db import get_db
    from app.core.deps import CurrentUser, get_current_user
    from app.domains.club import router as club_router
    from app.domains.club import scope as scope_module
    from app.main import app

    async def _codes(*args, **kwargs):
        return granted

    for module in (deps, club_router, scope_module):
        monkeypatch.setattr(module, "get_permission_codes_for_user", _codes)
    # Il client Redis del rate limit è globale: uno nato nel loop di un test
    # precedente qui non funziona più.
    from app.core import rate_limit
    monkeypatch.setattr(rate_limit, "_redis_client", None)

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=user.id, organization_id=scope.organization_id, roles=["CUSTOMER"]
    )
    return app, httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/api")


async def test_area_competitions_wish_money_and_payment(db, scope, monkeypatch):
    for code in ("ATHLETE", "CUSTOMER"):
        db.add(Role(organization_id=scope.organization_id, code=code, name=code.title()))
    await db.commit()
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    kid = await _athlete(db, scope, parent, birth_date=date(2014, 3, 1), first_name="Tiago", today=date.today())
    await athlete_access.set_login(db, athlete=kid, actor_user_id=parent.id, username="tiago.x", email=None, password="segreto1")
    await db.refresh(kid)
    soon = date.today() + timedelta(days=20)
    comp = await competitions_service.create_competition(db, scope=scope, actor_user_id=admin.id, data={
        "name": "Torneio de Lagos", "starts_on": soon, "ends_on": soon, "location": "Lagos",
        "registration_deadline": soon - timedelta(days=5), "level": "REGIONAL", "fee_cents": 0,
        "requires_agonistic_certificate": False,
    })

    from app.domains.users.models import User
    kid_user = await db.get(User, kid.user_id)
    app, client = await _client(db, monkeypatch, user=kid_user, scope=scope, granted={"club.athlete"})
    try:
        async with client:
            rows = (await client.get(f"/club/athlete-area/{kid.id}/competitions")).json()
            assert [r["name"] for r in rows] == ["Torneio de Lagos"]
            assert rows[0]["registrations_open"] and rows[0]["entry_status"] is None and not rows[0]["viewer_is_holder"]
            first = (await client.post(f"/club/athlete-area/{kid.id}/competitions/{comp.id}/wish")).json()
            again = (await client.post(f"/club/athlete-area/{kid.id}/competitions/{comp.id}/wish")).json()
            assert first["sent"] and again["already"] and not again["sent"]

            money = (await client.get(f"/club/athlete-area/{kid.id}/money")).json()
            assert money["support_total_cents"] == 0

            # Il minorenne non paga dalla sua area.
            fees = (await client.get(f"/club/athlete-area/{kid.id}")).json()["fees"]
            due = [f["id"] for f in fees if f["status"] == "DUE"]
            assert due
            refused = await client.post(f"/club/athlete-area/{kid.id}/payment-proofs",
                                        files={"file": ("b.png", PNG, "image/png")}, data={"fee_ids": due})
            assert refused.status_code == 403
    finally:
        app.dependency_overrides.clear()

    app, client = await _client(db, monkeypatch, user=admin, scope=scope, granted={"club.manage"})
    try:
        async with client:
            bad = await client.post(f"/club/admin/athletes/{kid.id}/supports",
                                    json={"category": "PIZZA", "amount_cents": 100, "paid_on": str(date.today())})
            assert bad.status_code == 422
            for cat, cents in (("TRANSPORT", 1200), ("MATERIAL", 3500), ("TRANSPORT", 800)):
                r = await client.post(f"/club/admin/athletes/{kid.id}/supports",
                                      json={"category": cat, "amount_cents": cents, "note": "Faro", "paid_on": str(date.today())})
                assert r.status_code == 201, r.text
            money = (await client.get(f"/club/admin/athletes/{kid.id}/supports")).json()
            assert money["support_total_cents"] == 5500
            assert money["support_by_category"] == {"TRANSPORT": 2000, "MATERIAL": 3500}
            assert money["wallet_balance_cents"] == 0  # ricarica e addebito si annullano
            assert len(money["supports"]) == 3
    finally:
        app.dependency_overrides.clear()

    app, client = await _client(db, monkeypatch, user=parent, scope=scope, granted={"club.athlete", "club.family"})
    try:
        async with client:
            rows = (await client.get(f"/club/athlete-area/{kid.id}/competitions")).json()
            assert rows[0]["viewer_is_holder"]
            own = (await client.post(f"/club/athlete-area/{kid.id}/competitions/{comp.id}/wish")).json()
            assert own["holder"] and not own["sent"]
            assert (await client.get(f"/club/athlete-area/{kid.id}/money")).json()["support_total_cents"] == 5500
            paid = await client.post(f"/club/athlete-area/{kid.id}/payment-proofs",
                                     files={"file": ("b.png", PNG, "image/png")}, data={"fee_ids": due})
            assert paid.status_code == 201, paid.text
    finally:
        app.dependency_overrides.clear()
