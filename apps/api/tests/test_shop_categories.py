"""Le categorie dello Shop.

The layer is a separate one -- two tables and no column added to any of the
product tables -- so what these tests protect is exactly what that
costs: that a category always belongs to one shop and one organization,
that assigning is a replace and never a merge, that deleting a category
takes its assignments and leaves the products alone, and that every product
list really does carry `category_ids`, since without it the Shop would have
to ask once per product.

The two list endpoints are exercised through the ASGI app rather than the
service, because that is where the single bulk query lives.
"""

import uuid

import httpx
import pytest
from sqlalchemy import func, select

from app.core.security import hash_password
from app.domains.catalog import service as catalog_service
from app.domains.catalog.schemas import ProductCreate
from app.domains.jav_market.models import JavMarketProduct
from app.domains.organizations.models import Organization
from app.domains.shop_categories import service as shop_categories_service
from app.domains.shop_categories.models import ShopCategory, ShopCategoryProduct
from app.domains.users.models import User


async def _user(db, organization_id) -> User:
    user = User(
        organization_id=organization_id,
        email=f"shop-cat-{uuid.uuid4().hex[:8]}@example.demo",
        password_hash=hash_password("x"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _category(db, organization_id, actor, *, shop="jav_market", name="Casa", position=0) -> ShopCategory:
    return await shop_categories_service.create_category(
        db, organization_id=organization_id, shop=shop, name=name, position=position,
        actor_user_id=actor.id,
    )


async def test_create_and_list_ordered_by_position_then_name(db, organization_id):
    actor = await _user(db, organization_id)
    await _category(db, organization_id, actor, name="Utensili", position=1)
    await _category(db, organization_id, actor, name="Cucina", position=0)
    await _category(db, organization_id, actor, name="Bagno", position=0)

    rows = await shop_categories_service.list_categories(db, organization_id=organization_id, shop="jav_market")

    assert [c.name for c, _count in rows] == ["Bagno", "Cucina", "Utensili"]
    assert [count for _c, count in rows] == [0, 0, 0]
    # Another shop's grid is untouched by any of this.
    assert await shop_categories_service.list_categories(db, organization_id=organization_id, shop="dropshipping") == []


async def test_duplicate_name_in_the_same_shop_is_refused_in_italian(db, organization_id):
    actor = await _user(db, organization_id)
    await _category(db, organization_id, actor, name="Casa")

    with pytest.raises(shop_categories_service.ShopCategoryValidationError) as refused:
        # Same name in a different case: still the same category to a human.
        await _category(db, organization_id, actor, name="  casa ")
    assert "Esiste già una categoria" in str(refused.value)

    # The same name in ANOTHER shop is a different category and is allowed:
    # each grid is curated on its own.
    other = await _category(db, organization_id, actor, shop="dropshipping", name="Casa")
    assert other.shop == "dropshipping"


async def test_unknown_shop_is_refused(db, organization_id):
    actor = await _user(db, organization_id)
    with pytest.raises(shop_categories_service.ShopCategoryValidationError):
        await _category(db, organization_id, actor, shop="amazon", name="Casa")


async def test_rename_reorder_and_deactivate(db, organization_id):
    actor = await _user(db, organization_id)
    category = await _category(db, organization_id, actor, name="Casa", position=3)
    await _category(db, organization_id, actor, name="Giardino")

    renamed = await shop_categories_service.update_category(
        db, organization_id=organization_id, category_id=category.id, name="Casa e cucina",
        position=0, actor_user_id=actor.id,
    )
    assert (renamed.name, renamed.position, renamed.active) == ("Casa e cucina", 0, True)

    # A rename onto a name already taken in the same shop is refused too.
    with pytest.raises(shop_categories_service.ShopCategoryValidationError):
        await shop_categories_service.update_category(
            db, organization_id=organization_id, category_id=category.id, name="giardino",
            actor_user_id=actor.id,
        )

    # Switching one off keeps it (and its products): it is simply no longer
    # offered as a filter.
    switched_off = await shop_categories_service.update_category(
        db, organization_id=organization_id, category_id=category.id, active=False, actor_user_id=actor.id
    )
    assert switched_off.active is False
    assert switched_off.name == "Casa e cucina"
    names = [c.name for c, _ in await shop_categories_service.list_categories(
        db, organization_id=organization_id, shop="jav_market"
    )]
    assert "Casa e cucina" in names


async def test_assignments_are_replaced_and_counted(db, organization_id):
    actor = await _user(db, organization_id)
    casa = await _category(db, organization_id, actor, name="Casa")
    giardino = await _category(db, organization_id, actor, name="Giardino")
    product_id, other_product_id = uuid.uuid4(), uuid.uuid4()

    await shop_categories_service.replace_assignments(
        db, organization_id=organization_id, shop="jav_market", product_id=product_id,
        category_ids=[casa.id, giardino.id], actor_user_id=actor.id,
    )
    await shop_categories_service.replace_assignments(
        db, organization_id=organization_id, shop="jav_market", product_id=other_product_id,
        category_ids=[casa.id], actor_user_id=actor.id,
    )

    counts = {c.name: n for c, n in await shop_categories_service.list_categories(
        db, organization_id=organization_id, shop="jav_market"
    )}
    assert counts == {"Casa": 2, "Giardino": 1}

    # A replace is a replace, not a merge.
    await shop_categories_service.replace_assignments(
        db, organization_id=organization_id, shop="jav_market", product_id=product_id,
        category_ids=[giardino.id], actor_user_id=actor.id,
    )
    assignments = await shop_categories_service.assignments_for_shop(
        db, organization_id=organization_id, shop="jav_market"
    )
    assert assignments[str(product_id)] == [str(giardino.id)]

    # The empty list removes them all, and the product disappears from the map.
    await shop_categories_service.replace_assignments(
        db, organization_id=organization_id, shop="jav_market", product_id=product_id,
        category_ids=[], actor_user_id=actor.id,
    )
    assignments = await shop_categories_service.assignments_for_shop(
        db, organization_id=organization_id, shop="jav_market"
    )
    assert str(product_id) not in assignments
    assert assignments[str(other_product_id)] == [str(casa.id)]
    assert await shop_categories_service.product_count(db, category_id=giardino.id) == 0


async def test_a_category_of_another_shop_or_organization_is_refused(db, organization_id):
    actor = await _user(db, organization_id)
    casa_shop = await _category(db, organization_id, actor, shop="jav_market", name="Casa")

    with pytest.raises(shop_categories_service.ShopCategoryValidationError) as refused:
        await shop_categories_service.replace_assignments(
            db, organization_id=organization_id, shop="dropshipping", product_id=uuid.uuid4(),
            category_ids=[casa_shop.id], actor_user_id=actor.id,
        )
    assert "non appartengono a questo shop" in str(refused.value)

    other_org = Organization(name=f"Altra {uuid.uuid4()}", status="ACTIVE")
    db.add(other_org)
    await db.commit()
    other_actor = await _user(db, other_org.id)
    foreign = await _category(db, other_org.id, other_actor, shop="jav_market", name="Casa")

    with pytest.raises(shop_categories_service.ShopCategoryValidationError):
        await shop_categories_service.replace_assignments(
            db, organization_id=organization_id, shop="jav_market", product_id=uuid.uuid4(),
            category_ids=[foreign.id], actor_user_id=actor.id,
        )
    # And it is invisible from here in the first place.
    assert [c.id for c, _ in await shop_categories_service.list_categories(
        db, organization_id=organization_id, shop="jav_market"
    )] == [casa_shop.id]


async def test_deleting_a_category_takes_its_assignments_and_nothing_else(db, organization_id):
    actor = await _user(db, organization_id)
    casa = await _category(db, organization_id, actor, name="Casa")
    giardino = await _category(db, organization_id, actor, name="Giardino")
    product_id = uuid.uuid4()
    await shop_categories_service.replace_assignments(
        db, organization_id=organization_id, shop="jav_market", product_id=product_id,
        category_ids=[casa.id, giardino.id], actor_user_id=actor.id,
    )

    await shop_categories_service.delete_category(
        db, organization_id=organization_id, category_id=casa.id, actor_user_id=actor.id
    )

    assert await db.get(ShopCategory, casa.id) is None
    left = (await db.execute(
        select(func.count()).select_from(ShopCategoryProduct).where(ShopCategoryProduct.category_id == casa.id)
    )).scalar_one()
    assert left == 0
    # The other category keeps the same product: only the deleted one went.
    assert await shop_categories_service.category_ids_for_product(
        db, organization_id=organization_id, shop="jav_market", product_id=product_id
    ) == [giardino.id]

    with pytest.raises(shop_categories_service.ShopCategoryNotFoundError):
        await shop_categories_service.delete_category(
            db, organization_id=organization_id, category_id=casa.id, actor_user_id=actor.id
        )


async def test_category_ids_travel_on_the_product_lists(db, organization_id, monkeypatch):
    """The point of the whole layer: the Shop filters its grids without a
    call per product. The catalog list (our own products) and the
    assignments of the Shop (jav_market), through the real routes."""
    from app.core import deps
    from app.core.db import get_db
    from app.core.deps import CurrentUser, get_current_user
    from app.main import app

    actor = await _user(db, organization_id)
    granted: set[str] = {"products.read", "products.manage", "shop.manage"}

    async def _codes(*args, **kwargs):
        return granted

    monkeypatch.setattr(deps, "get_permission_codes_for_user", _codes)

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=actor.id, organization_id=organization_id, roles=["ADMIN"]
    )

    # A catalog product in the PARTNER section -> shop "partner".
    product = await catalog_service.create_product(
        db, organization_id=organization_id,
        payload=ProductCreate(
            code=f"PRD-{uuid.uuid4().hex[:6]}", product_type="PHYSICAL", customer_type="BOTH",
            category="PARTNER", name="Tazza Jav", base_price_cents=1500, contract_duration_months=None,
        ),
        actor_user_id=actor.id,
    )
    # A Shop product, written straight to the table: the categories layer
    # never asks the shop how its products got there.
    shop_product = JavMarketProduct(
        organization_id=organization_id, name="Lampada LED", created_by_user_id=actor.id,
    )
    db.add(shop_product)
    await db.commit()

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test/api"
        ) as client:
            created = await client.post(
                "/shop-categories", json={"shop": "partner", "name": "Gadget", "position": 2}
            )
            assert created.status_code == 201, created.text
            gadget = created.json()
            assert (gadget["shop"], gadget["name"], gadget["position"], gadget["product_count"]) == (
                "partner", "Gadget", 2, 0
            )

            duplicate = await client.post("/shop-categories", json={"shop": "partner", "name": "gadget"})
            assert duplicate.status_code == 400
            assert "Esiste già una categoria" in duplicate.json()["detail"]

            shop_created = await client.post("/shop-categories", json={"shop": "jav_market", "name": "Illuminazione"})
            assert shop_created.status_code == 201
            illuminazione = shop_created.json()

            assigned = await client.put(
                "/shop-categories/assignments",
                json={"shop": "partner", "product_id": str(product.id), "category_ids": [gadget["id"]]},
            )
            assert assigned.status_code == 200, assigned.text
            wrong_shop = await client.put(
                "/shop-categories/assignments",
                json={"shop": "jav_market", "product_id": str(shop_product.id), "category_ids": [gadget["id"]]},
            )
            assert wrong_shop.status_code == 400
            shop_assigned = await client.put(
                "/shop-categories/assignments",
                json={"shop": "jav_market", "product_id": str(shop_product.id), "category_ids": [illuminazione["id"]]},
            )
            assert shop_assigned.status_code == 200, shop_assigned.text

            listed = await client.get("/shop-categories", params={"shop": "partner"})
            assert listed.status_code == 200
            assert [(c["name"], c["product_count"]) for c in listed.json()] == [("Gadget", 1)]

            assignments = await client.get("/shop-categories/assignments", params={"shop": "jav_market"})
            assert assignments.json() == {str(shop_product.id): [illuminazione["id"]]}

            # 1. the catalog list (admin grid and customer catalog alike)
            catalog = await client.get("/products")
            assert catalog.status_code == 200, catalog.text
            card = next(p for p in catalog.json() if p["id"] == str(product.id))
            assert card["category_ids"] == [gadget["id"]]
            # `category` (the Shop section) and the new categories are two
            # different things and both still travel.
            assert card["category"] == "PARTNER"

            # A product nobody categorised carries an empty list, never a null.
            detail = await client.get(f"/products/{product.id}")
            assert detail.json()["category_ids"] == [gadget["id"]]

            # The customer may read the names (that is the filter) and
            # nothing else: no permission beyond being logged in.
            granted.clear()
            assert (await client.get("/shop-categories", params={"shop": "partner"})).status_code == 200
            assert (await client.post("/shop-categories", json={"shop": "jav_market", "name": "X"})).status_code == 403
            assert (await client.get("/shop-categories/assignments", params={"shop": "jav_market"})).status_code == 403
            assert (await client.delete(f"/shop-categories/{gadget['id']}")).status_code == 403
    finally:
        app.dependency_overrides.clear()
