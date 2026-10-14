"""Il carrello del cliente.

Solo rotte "mie": un carrello è di chi lo possiede e nessun amministratore
lo tocca, quindi qui non esistono percorsi di gestione. L'identità arriva
dal cookie di sessione come ovunque, e il controllo che una riga sia
davvero del richiedente sta nel servizio, non qui, perché è l'unico punto
da cui si passa sempre.

Il pagamento **non** è qui: trasformare il carrello in un ordine è affare
del negozio, che conosce indirizzo, spedizione, IVA e metodi di pagamento
suoi (`POST /jav-market/orders/mine/cart`). Qui si riempie e si svuota.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, get_current_user
from app.domains.carts import service
from app.domains.carts.schemas import CartItemAddRequest, CartItemQuantityUpdate

router = APIRouter(prefix="/carts", tags=["carts"])


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, service.CartNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/mine")
async def get_my_cart(
    current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    """Tutto il carrello, una sezione per negozio, con i prezzi di adesso."""
    return await service.summary(
        db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id
    )


@router.post("/mine/{shop}/items", status_code=status.HTTP_201_CREATED)
async def add_to_my_cart(
    shop: str,
    payload: CartItemAddRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        await service.add_item(
            db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id,
            shop=shop, variant_id=payload.variant_id, quantity=payload.quantity,
        )
    except (service.CartValidationError, service.CartNotFoundError) as exc:
        raise _http(exc) from exc
    return await service.summary(
        db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id
    )


@router.patch("/mine/{shop}/items/{item_id}")
async def update_my_cart_item(
    shop: str,
    item_id: uuid.UUID,
    payload: CartItemQuantityUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        await service.set_quantity(
            db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id,
            shop=shop, item_id=item_id, quantity=payload.quantity,
        )
    except (service.CartValidationError, service.CartNotFoundError) as exc:
        raise _http(exc) from exc
    return await service.summary(
        db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id
    )


@router.delete("/mine/{shop}/items/{item_id}")
async def remove_from_my_cart(
    shop: str,
    item_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        await service.remove_item(db, customer_user_id=current_user.user_id, shop=shop, item_id=item_id)
    except (service.CartValidationError, service.CartNotFoundError) as exc:
        raise _http(exc) from exc
    return await service.summary(
        db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id
    )


@router.delete("/mine/{shop}")
async def clear_my_cart(
    shop: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        await service.clear(db, customer_user_id=current_user.user_id, shop=shop)
    except (service.CartValidationError, service.CartNotFoundError) as exc:
        raise _http(exc) from exc
    return await service.summary(
        db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id
    )
