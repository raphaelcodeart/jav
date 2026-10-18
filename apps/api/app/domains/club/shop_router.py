"""Lo shop del club (`/club/admin/shop/...`): la segreteria (`club.manage`)
carica i prodotti del suo club (t-shirt, judogi del club, materiale) e
gestisce gli ordini fatti nel suo shop: conferma il pagamento, segna la
spedizione o la consegna, annulla. Usa lo stesso catalogo dello Shop
(domains/jav_market) con `club_id` = il club: lo shop di JudoArteVida
resta della piattaforma. Specifica: docs/club-portal.md, "Lo shop del club"."""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.rate_limit import rate_limit
from app.core.storage import UploadValidationError, upload_media
from app.domains.club.scope import ClubUser, require_club_permission
from app.domains.jav_market import service as shop
from app.domains.jav_market.schemas import (
    JavMarketOrderCancelRequest,
    JavMarketShipRequest,
    ProductUpdate,
    ProductWrite,
    VariantUpdate,
    VariantWrite,
)

router = APIRouter(prefix="/club/admin/shop", tags=["club-admin"])
MANAGE = "club.manage"


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, shop.JavMarketNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/products")
async def list_products(user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await shop.admin_products_read(db, organization_id=user.organization_id, club_id=user.club_id)


@router.post("/images", dependencies=[Depends(rate_limit("club-shop-image", max_requests=60, window_seconds=300))])
async def upload_image(file: UploadFile = File(...), user: ClubUser = Depends(require_club_permission(MANAGE))) -> dict:
    try:
        url = upload_media(file_bytes=await file.read(), content_type=file.content_type or "",
                           key_prefix=f"photos/club-shop/{user.club_id}")
    except UploadValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La foto deve essere un JPG, PNG o WebP di massimo 5 MB.") from exc
    return {"image_url": url}


@router.post("/products", status_code=status.HTTP_201_CREATED)
async def create_product(payload: ProductWrite, user: ClubUser = Depends(require_club_permission(MANAGE)),
                         db: AsyncSession = Depends(get_db)) -> dict:
    data = payload.model_dump()
    # JavCash e fornitori sono dello shop di JudoArteVida.
    data.update({"credit_discount_percentage": 0, "producer_id": None})
    try:
        product = await shop.create_product(db, organization_id=user.organization_id, actor_user_id=user.user_id,
                                            payload=data, club_id=user.club_id)
    except shop.ERRORS as exc:
        raise _http(exc) from exc
    return await shop.product_read_dict(db, product, admin=True)


@router.patch("/products/{product_id}")
async def update_product(product_id: uuid.UUID, payload: ProductUpdate, user: ClubUser = Depends(require_club_permission(MANAGE)),
                         db: AsyncSession = Depends(get_db)) -> dict:
    data = payload.model_dump(exclude_unset=True)
    data.pop("credit_discount_percentage", None)
    data.pop("producer_id", None)
    try:
        product = await shop.update_product(db, organization_id=user.organization_id, product_id=product_id,
                                            payload=data, club_id=user.club_id)
    except shop.ERRORS as exc:
        raise _http(exc) from exc
    return await shop.product_read_dict(db, product, admin=True)


@router.post("/products/{product_id}/variants", status_code=status.HTTP_201_CREATED)
async def add_variant(product_id: uuid.UUID, payload: VariantWrite, user: ClubUser = Depends(require_club_permission(MANAGE)),
                      db: AsyncSession = Depends(get_db)) -> dict:
    try:
        product = await shop.add_variant(db, organization_id=user.organization_id, product_id=product_id,
                                         payload=payload.model_dump(), club_id=user.club_id)
    except shop.ERRORS as exc:
        raise _http(exc) from exc
    return await shop.product_read_dict(db, product, admin=True)


@router.patch("/variants/{variant_id}")
async def update_variant(variant_id: uuid.UUID, payload: VariantUpdate, user: ClubUser = Depends(require_club_permission(MANAGE)),
                         db: AsyncSession = Depends(get_db)) -> dict:
    try:
        v = await shop.update_variant(db, organization_id=user.organization_id, variant_id=variant_id,
                                      payload=payload.model_dump(exclude_unset=True), club_id=user.club_id)
    except shop.ERRORS as exc:
        raise _http(exc) from exc
    return {"id": v.id, "label": v.label, "price_cents": v.price_cents, "inventory": v.inventory, "active": v.active,
            "max_height_cm": v.max_height_cm}


# --- Gli ordini dello shop del club ---------------------------------------------------------------

@router.get("/orders")
async def list_orders(user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db)) -> list[dict]:
    orders = await shop.list_orders(db, organization_id=user.organization_id, seller_club_id=user.club_id)
    return [await shop.order_read_dict(db, o, admin=True) for o in orders]


async def _mine(db: AsyncSession, user: ClubUser, order_id: uuid.UUID):
    order = await shop.get_org_scoped(db, organization_id=user.organization_id, order_id=order_id)
    if order is None or order.club_id != user.club_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ordine non trovato.")
    return order


@router.get("/orders/{order_id}/payment-proof-url")
async def proof_url(order_id: uuid.UUID, user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db)) -> dict:
    order = await _mine(db, user, order_id)
    if order.payment_proof_storage_key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Prova di pagamento non trovata.")
    return {"url": shop.presigned_payment_proof_url(order)}


@router.post("/orders/{order_id}/confirm-payment")
async def confirm_payment(order_id: uuid.UUID, user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db)) -> dict:
    await _mine(db, user, order_id)
    try:
        order = await shop.confirm_payment(db, organization_id=user.organization_id, order_id=order_id, actor_user_id=user.user_id)
    except shop.ERRORS as exc:
        raise _http(exc) from exc
    return await shop.order_read_dict(db, order, admin=True)


@router.post("/orders/{order_id}/ship")
async def ship(order_id: uuid.UUID, payload: JavMarketShipRequest, user: ClubUser = Depends(require_club_permission(MANAGE)),
               db: AsyncSession = Depends(get_db)) -> dict:
    await _mine(db, user, order_id)
    try:
        order = await shop.mark_shipped(db, organization_id=user.organization_id, order_id=order_id, actor_user_id=user.user_id,
                                        tracking_number=payload.tracking_number, tracking_url=payload.tracking_url,
                                        tracking_company=payload.tracking_company)
    except shop.ERRORS as exc:
        raise _http(exc) from exc
    return await shop.order_read_dict(db, order, admin=True)


@router.post("/orders/{order_id}/delivered")
async def delivered(order_id: uuid.UUID, user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db)) -> dict:
    await _mine(db, user, order_id)
    try:
        order = await shop.mark_delivered(db, organization_id=user.organization_id, order_id=order_id, actor_user_id=user.user_id)
    except shop.ERRORS as exc:
        raise _http(exc) from exc
    return await shop.order_read_dict(db, order, admin=True)


@router.post("/orders/{order_id}/cancel")
async def cancel(order_id: uuid.UUID, payload: JavMarketOrderCancelRequest, user: ClubUser = Depends(require_club_permission(MANAGE)),
                 db: AsyncSession = Depends(get_db)) -> dict:
    await _mine(db, user, order_id)
    try:
        order = await shop.cancel_order(db, organization_id=user.organization_id, order_id=order_id,
                                        reason=payload.reason, actor_user_id=user.user_id)
    except shop.ERRORS as exc:
        raise _http(exc) from exc
    return await shop.order_read_dict(db, order, admin=True)
