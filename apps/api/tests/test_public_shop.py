"""Lo Shop JAV sul sito pubblico (jav_market/public_router.py).

Le promesse: si vedono solo i prodotti di JudoArteVida (mai quelli dei
club), con il prezzo IVA compresa; a negozio spento la vetrina è vuota.
"""

from app.domains.jav_market import public_router
from app.domains.jav_market import service as market
from tests.test_jav_market import _shop, _user


async def test_public_shop_shows_only_jav_products_with_vat(db, scope, monkeypatch):
    org = scope.organization_id

    async def _org(_db, _raw):
        return org

    monkeypatch.setattr(public_router, "resolve_organization_id", _org)
    admin = await _user(db, org, "ADMIN")
    await _shop(db, org, admin)
    await market.create_product(db, organization_id=org, actor_user_id=admin.id, club_id=scope.club_id,
                                payload={"name": "T-shirt do clube", "variants": [{"label": "M", "price_cents": 1500}]})
    await market.create_product(db, organization_id=org, actor_user_id=admin.id,
                                payload={"name": "Whey 1kg", "variants": [{"label": "Unica", "price_cents": 1000}]})

    page = await public_router.public_shop(offset=0, limit=24, q=None, category_id=None, db=db)
    names = {i["name"] for i in page["items"]}
    assert "Whey 1kg" in names and "T-shirt do clube" not in names
    whey = next(i for i in page["items"] if i["name"] == "Whey 1kg")
    assert whey["price_cents"] == 1220  # 10,00 + IVA 22%
    assert set(whey) >= {"id", "name", "image_url", "in_stock"} and "unit_cost_cents" not in whey

    row = await market.get_settings_row(db, organization_id=org)
    await market.update_settings(db, row=row, actor_user_id=admin.id, updates={"enabled": False})
    assert (await public_router.public_shop(offset=0, limit=24, q=None, category_id=None, db=db))["items"] == []
