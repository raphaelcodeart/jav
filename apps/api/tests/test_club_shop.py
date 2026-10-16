"""Lo shop di ogni club (club/shop_router.py, jav_market con `club_id`).

Le promesse: una famiglia vede lo shop del suo club e quello di
JudoArteVida, mai lo shop di un altro club; un ordine è di un venditore solo
(e ne porta il club); i prodotti di un club li modifica solo quel club.
"""

import pytest

from app.domains.jav_market import service as market
from tests.test_club_legacy_features import _other_club
from tests.test_jav_market import _shop, _user, _variants


async def test_each_club_has_its_shop_next_to_the_jav_one(db, scope):
    org = scope.organization_id
    admin = await _user(db, org, "ADMIN")
    _row, _producer, pane, _miele = await _shop(db, org, admin)
    other = await _other_club(db, scope)
    tshirt = await market.create_product(db, organization_id=org, actor_user_id=admin.id, club_id=scope.club_id,
                                         payload={"name": "T-shirt do clube", "variants": [{"label": "M", "price_cents": 1500}]})
    other_bag = await market.create_product(db, organization_id=org, actor_user_id=admin.id, club_id=other.club_id,
                                            payload={"name": "Saco do outro clube", "variants": [{"label": "Unica", "price_cents": 2000}]})

    names = lambda page: {i["name"] for i in page["items"]}  # noqa: E731
    mine = await market.customer_products_page(db, organization_id=org, viewer_club_id=scope.club_id)
    assert "T-shirt do clube" in names(mine) and "Pane di segale" in names(mine) and "Saco do outro clube" not in names(mine)
    only_club = await market.customer_products_page(db, organization_id=org, viewer_club_id=scope.club_id, seller="CLUB")
    assert names(only_club) == {"T-shirt do clube"}
    card = next(i for i in mine["items"] if i["name"] == "T-shirt do clube")
    assert card["seller"]["club_id"] == scope.club_id

    # La piattaforma vede nel suo catalogo solo lo shop di JudoArteVida.
    assert {p["name"] for p in await market.admin_products_read(db, organization_id=org)} >= {"Pane di segale"}
    assert "T-shirt do clube" not in {p["name"] for p in await market.admin_products_read(db, organization_id=org)}
    # Un club non tocca i prodotti di un altro.
    with pytest.raises(market.JavMarketNotFoundError):
        await market.update_product(db, organization_id=org, product_id=other_bag.id, payload={"name": "X"}, club_id=scope.club_id)

    customer = await _user(db, org)
    shirt_v = (await _variants(db, tshirt))[0]
    bread_v = (await _variants(db, pane))[0]
    with pytest.raises(market.JavMarketValidationError):
        await market.get_quote(db, organization_id=org, customer_user_id=customer.id, lines=[(shirt_v.id, 1), (bread_v.id, 1)])
    quote = await market.get_quote(db, organization_id=org, customer_user_id=customer.id, lines=[(shirt_v.id, 2)])
    assert quote["seller_club_id"] == scope.club_id


async def test_the_club_shop_works_with_the_jav_shop_switched_off(db, scope):
    org = scope.organization_id
    admin = await _user(db, org, "ADMIN")
    _row, _producer, pane, _miele = await _shop(db, org, admin)
    row = await market.get_settings_row(db, organization_id=org)
    await market.update_settings(db, row=row, actor_user_id=admin.id, updates={"enabled": False})
    tshirt = await market.create_product(db, organization_id=org, actor_user_id=admin.id, club_id=scope.club_id,
                                         payload={"name": "T-shirt", "variants": [{"label": "M", "price_cents": 1500}]})
    page = await market.customer_products_page(db, organization_id=org, viewer_club_id=scope.club_id)
    assert [i["name"] for i in page["items"]] == ["T-shirt"]
    customer = await _user(db, org)
    quote = await market.get_quote(db, organization_id=org, customer_user_id=customer.id,
                                   lines=[((await _variants(db, tshirt))[0].id, 1)])
    # Il prezzo del club è quello finale: niente IVA aggiunta.
    assert quote["vat_cents"] == 0 and quote["items_cents"] == 1500
    with pytest.raises(market.JavMarketValidationError):
        await market.get_quote(db, organization_id=org, customer_user_id=customer.id,
                               lines=[((await _variants(db, pane))[0].id, 1)])
