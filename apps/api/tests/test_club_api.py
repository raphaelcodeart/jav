"""Club, attraverso le rotte vere: la famiglia via HTTP.

I test di servizio dicono che le regole valgono; questo dice che le rotte le
usano davvero -- il permesso giusto su ogni gruppo, l'upload multipart della
prova con più quote, e che un genitore che indovina l'id di un atleta altrui
riceve 404 e non i suoi dati.
"""

from datetime import date

import httpx

from app.domains.club import service as club_service
from tests.test_club_fees import PNG, _plans, _user


async def _client(db, monkeypatch, *, user, scope, granted: set[str]):
    from app.core import deps
    from app.core.db import get_db
    from app.core.deps import CurrentUser, get_current_user
    from app.domains.club import router as club_router
    from app.main import app

    async def _codes(*args, **kwargs):
        return granted

    monkeypatch.setattr(deps, "get_permission_codes_for_user", _codes)
    monkeypatch.setattr(club_router, "get_permission_codes_for_user", _codes)

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=user.id, organization_id=scope.organization_id, roles=["CUSTOMER"]
    )
    return app, httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/api")


async def test_a_family_end_to_end_through_the_api(db, scope, monkeypatch):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    other = await _user(db, scope, "altro")
    stranger = await club_service.create_athlete(
        db, scope=scope, guardian_user_id=other.id, actor_user_id=other.id,
        first_name="Estraneo", last_name="Rossi", birth_date=date(2015, 1, 1), sex="M",
    )

    app, client = await _client(db, monkeypatch, user=parent, scope=scope, granted={"club.family"})
    try:
        async with client:
            created = await client.post("/club/athletes", json={
                "first_name": "Giulia", "last_name": "Verdi", "birth_date": "2016-05-05", "sex": "F",
            })
            assert created.status_code == 201, created.text
            athlete = created.json()
            assert athlete["belt"]["code"] == "WHITE"
            assert athlete["level"] == 1
            assert athlete["plan"]["name"] == "Ragazzi 8-13"

            family = (await client.get("/club/family")).json()
            assert [a["first_name"] for a in family["athletes"]] == ["Giulia"]
            fee_ids = [f["id"] for f in family["due_fees"]]
            # L'iscrizione, più la quota del mese in corso se è un mese fatturato.
            assert fee_ids

            # Un atleta di un'altra famiglia: 404, non 403.
            assert (await client.get(f"/club/athletes/{stranger.id}")).status_code == 404

            uploaded = await client.post(
                "/club/payment-proofs",
                files={"file": ("bonifico.png", PNG, "image/png")},
                data={"fee_ids": fee_ids, "note": "Ottobre"},
            )
            assert uploaded.status_code == 201, uploaded.text
            assert {f["status"] for f in uploaded.json()["fees"]} == {"PAID"}

            family = (await client.get("/club/family")).json()
            assert family["due_cents"] == 0
            assert len(family["recent_proofs"]) == 1

            config = (await client.get("/club/config")).json()
            assert config["belts"][0]["code"] == "WHITE"
            assert "Fanciulli" in config["age_bands"][1]["label"]

            # Il genitore non entra nelle rotte della segreteria.
            assert (await client.get("/club/admin/fees")).status_code == 403
    finally:
        app.dependency_overrides.clear()


async def test_a_shop_order_can_only_name_an_athlete_of_the_family(db, scope):
    """Il judogi "per Giulia" deve essere per una Giulia di questa famiglia:
    il controllo viene prima di qualunque altra cosa dell'ordine."""
    import pytest

    from app.domains.jav_market import service as jav_market_service

    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    other = await _user(db, scope, "altro")
    stranger = await club_service.create_athlete(
        db, scope=scope, guardian_user_id=other.id, actor_user_id=other.id,
        first_name="Estraneo", last_name="Rossi", birth_date=date(2015, 1, 1), sex="M",
    )
    with pytest.raises(jav_market_service.JavMarketNotFoundError):
        await jav_market_service.create_order(
            db, organization_id=scope.organization_id, customer_user_id=parent.id, address={},
            credit_applied_cents=0, payment_method="BANK_TRANSFER", actor_user_id=parent.id, otp_code=None,
            note=None, lines=[], athlete_id=stranger.id,
        )
