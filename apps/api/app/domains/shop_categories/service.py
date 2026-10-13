"""Reading and curating the Shop's categories.

Two kinds of function live here. The first are the administrator's: create,
rename, reorder, switch off, delete, assign. The second are the ones every
product list calls -- category_ids_by_product() and its siblings -- and they
exist in this shape for one reason: a Shop grid asks for the categories of a
whole page of products in a single query. A query per product would be felt
immediately, since this runs on every tab the customer opens.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.shop_categories.models import SHOPS, ShopCategory, ShopCategoryProduct


class ShopCategoryError(Exception):
    """Anything the caller did wrong -- the message is Italian and shown as is."""


class ShopCategoryNotFoundError(ShopCategoryError):
    """-> 404."""


class ShopCategoryValidationError(ShopCategoryError):
    """-> 400."""


def normalize_shop(shop: str | None) -> str:
    """The one door every `shop` value goes through, whether it arrived as a
    query parameter or in a body -- so an unknown shop is refused in Italian
    in one place instead of in six routers."""
    key = (shop or "").strip().lower()
    if key not in SHOPS:
        raise ShopCategoryValidationError("Shop non valido.")
    return key


# --- Lettura ---------------------------------------------------------------------------------------


async def list_categories(
    db: AsyncSession, *, organization_id: uuid.UUID, shop: str
) -> list[tuple[ShopCategory, int]]:
    """Every category of a shop with how many products it holds, ordered the
    way the chips are shown (position, then name). Two queries whatever the
    number of categories."""
    stmt = (
        select(ShopCategory)
        .where(ShopCategory.organization_id == organization_id, ShopCategory.shop == shop)
        .order_by(ShopCategory.position, ShopCategory.name)
    )
    categories = list((await db.execute(stmt)).scalars().all())
    if not categories:
        return []

    counts_stmt = (
        select(ShopCategoryProduct.category_id, func.count())
        .where(ShopCategoryProduct.category_id.in_([c.id for c in categories]))
        .group_by(ShopCategoryProduct.category_id)
    )
    counts: dict[uuid.UUID, int] = {
        category_id: count for category_id, count in (await db.execute(counts_stmt)).all()
    }
    return [(category, counts.get(category.id, 0)) for category in categories]


async def get_category(
    db: AsyncSession, *, organization_id: uuid.UUID, category_id: uuid.UUID
) -> ShopCategory:
    category = await db.get(ShopCategory, category_id)
    if category is None or category.organization_id != organization_id:
        raise ShopCategoryNotFoundError("Categoria non trovata.")
    return category


async def product_count(db: AsyncSession, *, category_id: uuid.UUID) -> int:
    """How many products one category holds -- the list reads its counts in
    bulk instead (see list_categories); this is for a single category."""
    stmt = (
        select(func.count())
        .select_from(ShopCategoryProduct)
        .where(ShopCategoryProduct.category_id == category_id)
    )
    return (await db.execute(stmt)).scalar_one()


async def category_ids_by_shop_product(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    shops: Sequence[str],
    product_ids: Sequence[uuid.UUID],
) -> dict[tuple[str, uuid.UUID], list[uuid.UUID]]:
    """{(shop, product_id): [category_id, ...]} in ONE query.

    Keyed by the pair and not by the product alone because the catalog list
    carries products of three shops at once: an assignment left behind by a
    product that has since been moved to another section must not reappear
    in the new one.
    """
    if not product_ids:
        return {}
    stmt = select(
        ShopCategoryProduct.shop, ShopCategoryProduct.product_id, ShopCategoryProduct.category_id
    ).where(
        ShopCategoryProduct.organization_id == organization_id,
        ShopCategoryProduct.shop.in_(list(shops)),
        ShopCategoryProduct.product_id.in_(list(product_ids)),
    )
    out: dict[tuple[str, uuid.UUID], list[uuid.UUID]] = {}
    for shop, product_id, category_id in (await db.execute(stmt)).all():
        out.setdefault((shop, product_id), []).append(category_id)
    return out


async def category_ids_by_product(
    db: AsyncSession, *, organization_id: uuid.UUID, shop: str, product_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[uuid.UUID]]:
    """The single-shop shortcut used by the marketplaces: {product_id: [...]},
    still one query for the whole page."""
    pairs = await category_ids_by_shop_product(
        db, organization_id=organization_id, shops=(shop,), product_ids=product_ids
    )
    return {product_id: ids for (_shop, product_id), ids in pairs.items()}


async def category_ids_for_product(
    db: AsyncSession, *, organization_id: uuid.UUID, shop: str, product_id: uuid.UUID
) -> list[uuid.UUID]:
    """One product's categories -- for the endpoints that answer with a
    single product (an import, a patch, a sync), never inside a loop."""
    by_product = await category_ids_by_product(
        db, organization_id=organization_id, shop=shop, product_ids=(product_id,)
    )
    return by_product.get(product_id, [])


async def assignments_for_shop(
    db: AsyncSession, *, organization_id: uuid.UUID, shop: str
) -> dict[str, list[str]]:
    """{product_id: [category_id, ...]} for every product of this shop that
    has at least one -- what the admin grid needs to draw its checkboxes
    without asking once per row. Strings, because this is JSON."""
    stmt = select(ShopCategoryProduct.product_id, ShopCategoryProduct.category_id).where(
        ShopCategoryProduct.organization_id == organization_id, ShopCategoryProduct.shop == shop
    )
    out: dict[str, list[str]] = {}
    for product_id, category_id in (await db.execute(stmt)).all():
        out.setdefault(str(product_id), []).append(str(category_id))
    return out


# --- Scrittura -------------------------------------------------------------------------------------


async def _name_taken(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    shop: str,
    name: str,
    exclude_id: uuid.UUID | None = None,
) -> bool:
    """Checked here as well as by the unique index, so the administrator
    reads "esiste già una categoria..." instead of an integrity error."""
    stmt = select(ShopCategory.id).where(
        ShopCategory.organization_id == organization_id,
        ShopCategory.shop == shop,
        func.lower(ShopCategory.name) == name.lower(),
    )
    if exclude_id is not None:
        stmt = stmt.where(ShopCategory.id != exclude_id)
    return (await db.execute(stmt)).first() is not None


async def create_category(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    shop: str,
    name: str,
    position: int = 0,
    actor_user_id: uuid.UUID,
) -> ShopCategory:
    shop = normalize_shop(shop)
    name = name.strip()
    if not name:
        raise ShopCategoryValidationError("Il nome della categoria è obbligatorio.")
    if await _name_taken(db, organization_id=organization_id, shop=shop, name=name):
        raise ShopCategoryValidationError("Esiste già una categoria con questo nome in questo shop.")

    category = ShopCategory(
        organization_id=organization_id, shop=shop, name=name, position=position, active=True
    )
    db.add(category)
    await db.flush()
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="shop_category.created", entity_type="shop_category", entity_id=str(category.id),
        new_value={"shop": shop, "name": name},
    )
    await db.commit()
    await db.refresh(category)
    return category


async def update_category(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    category_id: uuid.UUID,
    name: str | None = None,
    position: int | None = None,
    active: bool | None = None,
    actor_user_id: uuid.UUID,
) -> ShopCategory:
    category = await get_category(db, organization_id=organization_id, category_id=category_id)
    previous = {"name": category.name, "position": category.position, "active": category.active}

    if name is not None:
        new_name = name.strip()
        if not new_name:
            raise ShopCategoryValidationError("Il nome della categoria è obbligatorio.")
        if await _name_taken(
            db, organization_id=organization_id, shop=category.shop, name=new_name, exclude_id=category.id
        ):
            raise ShopCategoryValidationError("Esiste già una categoria con questo nome in questo shop.")
        category.name = new_name
    if position is not None:
        category.position = position
    if active is not None:
        category.active = active
    category.updated_at = utcnow()

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="shop_category.updated", entity_type="shop_category", entity_id=str(category.id),
        previous_value=previous,
        new_value={"name": category.name, "position": category.position, "active": category.active},
    )
    await db.commit()
    await db.refresh(category)
    return category


async def delete_category(
    db: AsyncSession, *, organization_id: uuid.UUID, category_id: uuid.UUID, actor_user_id: uuid.UUID
) -> None:
    """Takes its assignments with it (ON DELETE CASCADE, and explicitly here
    so the unit of work sees it too) -- the products themselves are never
    touched: this layer only ever describes them."""
    category = await get_category(db, organization_id=organization_id, category_id=category_id)
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="shop_category.deleted", entity_type="shop_category", entity_id=str(category.id),
        previous_value={"shop": category.shop, "name": category.name},
    )
    await db.execute(delete(ShopCategoryProduct).where(ShopCategoryProduct.category_id == category.id))
    await db.delete(category)
    await db.commit()


async def replace_assignments(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    shop: str,
    product_id: uuid.UUID,
    category_ids: Sequence[uuid.UUID],
    actor_user_id: uuid.UUID,
) -> list[uuid.UUID]:
    """Sets, in full, which categories of `shop` a product belongs to.

    The ids are resolved against this organization AND this shop before
    anything is written: a category of another shop (or another
    organization) is refused rather than silently dropped, because it can
    only mean the screen is sending the wrong thing.
    """
    shop = normalize_shop(shop)
    wanted = list(dict.fromkeys(category_ids))

    if wanted:
        found_stmt = select(ShopCategory.id).where(
            ShopCategory.organization_id == organization_id,
            ShopCategory.shop == shop,
            ShopCategory.id.in_(wanted),
        )
        found = set((await db.execute(found_stmt)).scalars().all())
        if len(found) != len(wanted):
            raise ShopCategoryValidationError(
                "Una o più categorie non esistono o non appartengono a questo shop."
            )

    await db.execute(
        delete(ShopCategoryProduct).where(
            ShopCategoryProduct.organization_id == organization_id,
            ShopCategoryProduct.shop == shop,
            ShopCategoryProduct.product_id == product_id,
        )
    )
    for category_id in wanted:
        db.add(
            ShopCategoryProduct(
                organization_id=organization_id,
                category_id=category_id,
                shop=shop,
                product_id=product_id,
            )
        )

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="shop_category.products_assigned", entity_type="shop_category_product",
        entity_id=str(product_id),
        new_value={"shop": shop, "category_ids": [str(cid) for cid in wanted]},
    )
    await db.commit()
    return wanted
