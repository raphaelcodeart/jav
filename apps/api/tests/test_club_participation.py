"""«Quero participar»: con una quota scaduta non ci si iscrive alle gare
(né dalla famiglia né con la richiesta dell'atleta), salvo che la segreteria
l'abbia segnata «non bloccante». Il bottone sa chi è già iscritto."""

from datetime import date, timedelta

from app.domains.club import athlete_access
from app.domains.club import competitions as competitions_service
from app.domains.rbac.models import Role
from tests.test_club_area_extras import _client
from tests.test_club_fees import _athlete, _fees, _no_debts, _plans, _user


async def test_debts_block_participation_until_marked_non_blocking(db, scope, monkeypatch):
    for code in ("ATHLETE", "CUSTOMER"):
        db.add(Role(organization_id=scope.organization_id, code=code, name=code.title()))
    await db.commit()
    today = date.today()
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    kid = await _athlete(db, scope, parent, birth_date=date(2014, 3, 1), first_name="Tiago", today=today)
    await athlete_access.set_login(db, athlete=kid, actor_user_id=parent.id, username="tiago.p", email=None, password="segreto1")
    await db.refresh(kid)
    # Tutto da pagare più avanti, tranne una quota scaduta da dieci giorni.
    await _no_debts(db, kid)
    late = (await _fees(db, kid.id))[0]
    late.due_date = today - timedelta(days=10)
    await db.commit()
    soon = today + timedelta(days=20)
    comp = await competitions_service.create_competition(db, scope=scope, actor_user_id=admin.id, data={
        "name": "Torneio de Lagos", "starts_on": soon, "ends_on": soon, "location": "Lagos",
        "registration_deadline": soon - timedelta(days=5), "level": "REGIONAL", "fee_cents": 1000,
        "requires_agonistic_certificate": False,
    })

    from app.domains.users.models import User
    kid_user = await db.get(User, kid.user_id)
    app, client = await _client(db, monkeypatch, user=kid_user, scope=scope, granted={"club.athlete"})
    try:
        async with client:
            wish = await client.post(f"/club/athlete-area/{kid.id}/competitions/{comp.id}/wish")
            assert wish.status_code == 400 and "debiti" in wish.json()["detail"]
            state = (await client.get(f"/club/participation/{comp.id}")).json()
            assert [(a["mode"], a["status"]) for a in state["athletes"]] == [("WISH", "DEBTS")]
    finally:
        app.dependency_overrides.clear()

    app, client = await _client(db, monkeypatch, user=parent, scope=scope, granted={"club.family"})
    try:
        async with client:
            mine = (await client.get("/club/participation/mine")).json()
            assert mine["has_athletes"] and mine["registered"] == []
            state = (await client.get(f"/club/participation/{comp.id}")).json()
            row = state["athletes"][0]
            assert row["mode"] == "ENROLL" and row["status"] == "DEBTS"
            assert [d["id"] for d in row["debts"]] == [str(late.id)] and row["debts_cents"] == late.amount_cents
            refused = await client.post(f"/club/participation/{comp.id}", json={"athlete_id": str(kid.id)})
            assert refused.status_code == 400
            # Anche dalla pagina delle gare della famiglia.
            old = await client.post(f"/club/competitions/{comp.id}/entries", json={"athlete_id": str(kid.id)})
            assert old.status_code == 400
    finally:
        app.dependency_overrides.clear()

    app, client = await _client(db, monkeypatch, user=admin, scope=scope, granted={"club.manage"})
    try:
        async with client:
            r = await client.post(f"/club/admin/fees/{late.id}/blocking", json={"non_blocking": True})
            assert r.status_code == 200 and r.json()["non_blocking"] is True
    finally:
        app.dependency_overrides.clear()

    app, client = await _client(db, monkeypatch, user=parent, scope=scope, granted={"club.family"})
    try:
        async with client:
            assert (await client.get(f"/club/participation/{comp.id}")).json()["athletes"][0]["status"] == "CAN"
            ok = await client.post(f"/club/participation/{comp.id}", json={"athlete_id": str(kid.id)})
            assert ok.json() == {"result": "REGISTERED"}, ok.text
            assert (await client.get("/club/participation/mine")).json()["registered"] == [str(comp.id)]
            state = (await client.get(f"/club/participation/{comp.id}")).json()
            assert state["athletes"][0]["status"] == "REGISTERED"
            # La quota della gara stessa (scade alla chiusura) non blocca nulla.
            assert state["athletes"][0]["debts"] == []
    finally:
        app.dependency_overrides.clear()
