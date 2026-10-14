"""Le categorie dello Shop: API.

Reading the list is the one thing every logged-in user may do, customers
included -- they need the names to filter the grid, and there is nothing to
hide in them. Everything else (creating, renaming, reordering, switching
off, deleting, assigning products) is `products.manage`, the same permission
that governs the catalog itself: whoever decides what is sold decides how it
is arranged.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, get_current_user, require_permission
from app.domains.shop_categories import service
from app.domains.shop_categories.schemas import (
    ShopCategoryAssignmentRead,
    ShopCategoryAssignmentUpdate,
    ShopCategoryCreate,
    ShopCategoryRead,
    ShopCategoryUpdate,
)

router = APIRouter(prefix="/shop-categories", tags=["shop-categories"])

MANAGE = "products.manage"


def _http(exc: service.ShopCategoryError) -> HTTPException:
    if isinstance(exc, service.ShopCategoryNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("", response_model=list[ShopCategoryRead])
async def list_shop_categories(
    shop: str = Query(...),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ShopCategoryRead]:
    """The chips of one shop, ordered by position then name, with how many
    products each holds. Inactive ones are returned too: the admin screen
    needs them, and the customer app simply does not offer them."""
    try:
        key = service.normalize_shop(shop)
    except service.ShopCategoryError as exc:
        raise _http(exc) from exc
    rows = await service.list_categories(db, organization_id=current_user.organization_id, shop=key)
    return [
        ShopCategoryRead(
            id=category.id, shop=category.shop, name=category.name, position=category.position,
            active=category.active, producer_id=category.producer_id, product_count=count,
        )
        for category, count in rows
    ]


@router.get("/assignments")
async def list_shop_category_assignments(
    shop: str = Query(...),
    current_user: CurrentUser = Depends(require_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, list[str]]:
    """{product_id: [category_id, ...]} for this shop -- one call for the
    whole management screen, and only the products that have at least one."""
    try:
        key = service.normalize_shop(shop)
    except service.ShopCategoryError as exc:
        raise _http(exc) from exc
    return await service.assignments_for_shop(db, organization_id=current_user.organization_id, shop=key)


@router.put("/assignments", response_model=ShopCategoryAssignmentRead)
async def replace_shop_category_assignments(
    payload: ShopCategoryAssignmentUpdate,
    current_user: CurrentUser = Depends(require_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ShopCategoryAssignmentRead:
    """Replaces a product's categories inside one shop; an empty list clears
    them. Never touches the product itself, which lives in another domain."""
    try:
        category_ids = await service.replace_assignments(
            db, organization_id=current_user.organization_id, shop=payload.shop,
            product_id=payload.product_id, category_ids=payload.category_ids,
            actor_user_id=current_user.user_id,
        )
    except service.ShopCategoryError as exc:
        raise _http(exc) from exc
    return ShopCategoryAssignmentRead(
        shop=service.normalize_shop(payload.shop), product_id=payload.product_id, category_ids=category_ids
    )


@router.post("", response_model=ShopCategoryRead, status_code=status.HTTP_201_CREATED)
async def create_shop_category(
    payload: ShopCategoryCreate,
    current_user: CurrentUser = Depends(require_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ShopCategoryRead:
    try:
        category = await service.create_category(
            db, organization_id=current_user.organization_id, shop=payload.shop, name=payload.name,
            position=payload.position, producer_id=payload.producer_id,
            actor_user_id=current_user.user_id,
        )
    except service.ShopCategoryError as exc:
        raise _http(exc) from exc
    return ShopCategoryRead(
        id=category.id, shop=category.shop, name=category.name, position=category.position,
        active=category.active, producer_id=category.producer_id, product_count=0,
    )


@router.patch("/{category_id}", response_model=ShopCategoryRead)
async def update_shop_category(
    category_id: uuid.UUID,
    payload: ShopCategoryUpdate,
    current_user: CurrentUser = Depends(require_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ShopCategoryRead:
    try:
        category = await service.update_category(
            db, organization_id=current_user.organization_id, category_id=category_id,
            name=payload.name, position=payload.position, active=payload.active,
            # Mandato a null toglie il fornitore; non mandato lo lascia com'è.
            producer_id=(
                payload.producer_id if "producer_id" in payload.model_fields_set else service.UNCHANGED
            ),
            actor_user_id=current_user.user_id,
        )
    except service.ShopCategoryError as exc:
        raise _http(exc) from exc
    return ShopCategoryRead(
        id=category.id, shop=category.shop, name=category.name, position=category.position,
        active=category.active, producer_id=category.producer_id,
        # Nothing about the products changed, but the screen re-renders the
        # chip from this answer and the count has to still be there.
        product_count=await service.product_count(db, category_id=category.id),
    )


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shop_category(
    category_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    """The category and its assignments go; the products stay exactly as
    they are."""
    try:
        await service.delete_category(
            db, organization_id=current_user.organization_id, category_id=category_id,
            actor_user_id=current_user.user_id,
        )
    except service.ShopCategoryError as exc:
        raise _http(exc) from exc
