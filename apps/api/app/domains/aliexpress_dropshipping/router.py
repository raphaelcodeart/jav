"""Marketplace 3 (AliExpress dropshipping) API.

Same permissions and same paths as the Shopify router (/shopify ->
/aliexpress): admin screens need imported_products.manage, order handling
wallet.manage, and the customer paths under /aliexpress/orders/mine mirror
/shopify/orders/mine one for one, so the unified "I miei Ordini" treats
every shop the same way.

Only the settings differ, because a Shopify store and an AliExpress app have
nothing in common to configure: no domain and no Admin token here, but an
App Key, an App Secret and the authorisation of the seller account
(/aliexpress/oauth/authorize-url and the public callback below).
"""

import urllib.parse
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import CurrentUser, get_current_user, require_permission
from app.core.rate_limit import rate_limit
from app.domains.aliexpress_dropshipping import client as aliexpress
from app.domains.aliexpress_dropshipping import service
from app.domains.aliexpress_dropshipping.models import AliexpressProduct
from app.domains.aliexpress_dropshipping.schemas import (
    AliexpressAuthorizeUrlRead,
    AliexpressCartCreditOtpRequest,
    AliexpressCartOrderRequest,
    AliexpressImportRequest,
    AliexpressOrderCancelRequest,
    AliexpressOrderCreditOtpRequest,
    AliexpressOrderPaymentMethodUpdate,
    AliexpressOrderSelfCreateRequest,
    AliexpressProductUpdate,
    AliexpressSettingsRead,
    AliexpressSettingsUpdate,
    AliexpressVariantUpdate,
    CheckoutSessionRead,
    PaymentProofUrlRead,
)
from app.domains.carts import service as carts_service
from app.domains.marketplaces import paging, rules
from app.domains.payments import service as payments_service
from app.domains.shop_categories import service as shop_categories_service
from app.domains.wallets import service as wallets_service

router = APIRouter(prefix="/aliexpress", tags=["aliexpress-dropshipping"])

CATALOG = "imported_products.manage"
ORDERS = "wallet.manage"
ERRORS = (service.AliexpressError, aliexpress.AliexpressApiError, wallets_service.InsufficientBalanceError)


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, service.AliexpressNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# --- Admin: impostazioni ---------------------------------------------------------------------------


@router.get("/settings", response_model=AliexpressSettingsRead)
async def get_aliexpress_settings(
    current_user: CurrentUser = Depends(require_permission(CATALOG)), db: AsyncSession = Depends(get_db)
) -> AliexpressSettingsRead:
    row = await service.get_settings_row(db, organization_id=current_user.organization_id)
    return AliexpressSettingsRead(**service.settings_read_dict(row))


@router.patch("/settings", response_model=AliexpressSettingsRead)
async def update_aliexpress_settings(
    payload: AliexpressSettingsUpdate,
    current_user: CurrentUser = Depends(require_permission(CATALOG)),
    db: AsyncSession = Depends(get_db),
) -> AliexpressSettingsRead:
    row = await service.get_settings_row(db, organization_id=current_user.organization_id)
    updates = payload.model_dump(exclude_unset=True)
    for key in [k for k, v in updates.items() if v is None and k not in ("app_key", "app_secret", "shipping_days")]:
        updates.pop(key)
    if "currency_rate" in updates:
        updates["currency_rate"] = Decimal(str(updates["currency_rate"]))
    try:
        row = await service.update_settings(db, row=row, updates=updates, actor_user_id=current_user.user_id)
    except ERRORS as exc:
        raise _http(exc) from exc
    return AliexpressSettingsRead(**service.settings_read_dict(row))


@router.post("/settings/test")
async def test_aliexpress_connection(
    current_user: CurrentUser = Depends(require_permission(CATALOG)), db: AsyncSession = Depends(get_db)
) -> dict:
    """Asks AliExpress for the categories the account may sell: the settings
    plus a handful of real category names, so "connesso" is not a guess."""
    row = await service.get_settings_row(db, organization_id=current_user.organization_id)
    try:
        return await service.test_connection(db, row=row)
    except ERRORS as exc:
        raise _http(exc) from exc


@router.get("/oauth/authorize-url", response_model=AliexpressAuthorizeUrlRead)
async def get_aliexpress_authorize_url(
    current_user: CurrentUser = Depends(require_permission(CATALOG)), db: AsyncSession = Depends(get_db)
) -> AliexpressAuthorizeUrlRead:
    """Where to send the administrator to authorise the AliExpress account,
    and the exact address to register in the app's portal."""
    row = await service.get_settings_row(db, organization_id=current_user.organization_id)
    try:
        url = service.authorize_url(row)
    except ERRORS as exc:
        raise _http(exc) from exc
    return AliexpressAuthorizeUrlRead(url=url, callback_url=aliexpress.callback_url())


# --- Admin: catalogo AliExpress ---------------------------------------------------------------------


@router.get("/catalog/search")
async def search_aliexpress_catalog(
    keyword: str | None = None,
    cursor: str | None = None,
    current_user: CurrentUser = Depends(require_permission(CATALOG)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await service.get_settings_row(db, organization_id=current_user.organization_id)
    try:
        return await service.search_catalog(
            db, row=row, keyword=(keyword or "").strip() or None, cursor=cursor or None
        )
    except ERRORS as exc:
        raise _http(exc) from exc


@router.get("/catalog/product")
async def preview_aliexpress_product(
    product_id: str,
    current_user: CurrentUser = Depends(require_permission(CATALOG)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """`product_id` is AliExpress' own id, as a query parameter for the same
    reason as Shopify's: it is not ours to put in a path."""
    row = await service.get_settings_row(db, organization_id=current_user.organization_id)
    try:
        return await service.preview_product(db, row=row, product_id=product_id)
    except ERRORS as exc:
        raise _http(exc) from exc


@router.get("/catalog/freight")
async def get_aliexpress_freight(
    product_id: str,
    sku_id: str | None = None,
    quantity: int = 1,
    current_user: CurrentUser = Depends(require_permission(CATALOG)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """What AliExpress charges to ship this product to Italy: the numbers
    behind the flat shipping in the settings."""
    row = await service.get_settings_row(db, organization_id=current_user.organization_id)
    try:
        return await service.freight_options(
            db, row=row, product_id=product_id, sku_id=sku_id, quantity=quantity
        )
    except ERRORS as exc:
        raise _http(exc) from exc


# --- Admin: prodotti importati ---------------------------------------------------------------------


@router.get("/products")
async def list_aliexpress_products(
    current_user: CurrentUser = Depends(require_permission(CATALOG)), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    products = await service.list_products(db, organization_id=current_user.organization_id, active_only=False)
    # The categories of the whole page in one query (shop_categories): an
    # N+1 here would be felt on every opening of the Shop.
    categories = await shop_categories_service.category_ids_by_product(
        db, organization_id=current_user.organization_id, shop=service.SHOP,
        product_ids=[p.id for p in products],
    )
    return [
        await service.product_admin_dict(db, p, category_ids=categories.get(p.id, []))
        for p in products
    ]


@router.post("/products", status_code=status.HTTP_201_CREATED)
async def import_aliexpress_product(
    payload: AliexpressImportRequest,
    current_user: CurrentUser = Depends(require_permission(CATALOG)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await service.get_settings_row(db, organization_id=current_user.organization_id)
    try:
        product = await service.import_product(
            db, row=row, actor_user_id=current_user.user_id, product_id=payload.product_id, name=payload.name,
            description=payload.description, credit_discount_percentage=payload.credit_discount_percentage,
            markup_percentage=payload.markup_percentage, variant_ids=payload.variant_ids, activate=payload.activate,
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.product_admin_dict(db, product)


@router.get("/products/active/page")
async def page_aliexpress_products_active(
    offset: int = Query(0, ge=0),
    limit: int = Query(paging.PAGE_SIZE, ge=1, le=paging.MAX_PAGE_SIZE),
    q: str | None = Query(None, max_length=100),
    category_id: uuid.UUID | None = None,
    current_user: CurrentUser = Depends(require_permission("products.read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Session 89: la vetrina a pagine («Mostra altri prodotti»), con ricerca
    e categoria filtrate sul server: vedi marketplaces/paging.py. Prima di
    /products/active/{product_id}, che altrimenti leggerebbe «page» come id."""
    row = await service.get_settings_row(db, organization_id=current_user.organization_id)
    if not row.enabled:
        return paging.empty_page(offset, limit)
    percentage = await rules.get_bank_transfer_discount_percentage(db, organization_id=current_user.organization_id)

    async def cards(products: list) -> list[dict | None]:
        categories = await shop_categories_service.category_ids_by_product(
            db, organization_id=current_user.organization_id, shop=service.SHOP,
            product_ids=[p.id for p in products],
        )
        return [
            await service.product_customer_dict(
                db, product, settings=row, bank_transfer_discount_percentage=percentage, category_ids=categories.get(product.id, []),
            )
            for product in products
        ]

    return await paging.customer_page(
        db, model=AliexpressProduct, shop=service.SHOP, organization_id=current_user.organization_id,
        build_cards=cards, offset=offset, limit=limit, search=q, category_id=category_id,
    )


@router.get("/products/active")
async def list_aliexpress_products_active(
    current_user: CurrentUser = Depends(require_permission("products.read")), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    """The customer's "Marketplace 3" tab: empty while the shop is switched off.
    Session 89: solo la prima pagina -- lo Shop usa /products/active/page;
    questa resta per una pagina del browser ancora alla versione di prima."""
    page = await page_aliexpress_products_active(
        offset=0, limit=paging.PAGE_SIZE, q=None, category_id=None, current_user=current_user, db=db,
    )
    return page["items"]


@router.patch("/products/{product_id}")
async def update_aliexpress_product(
    product_id: uuid.UUID,
    payload: AliexpressProductUpdate,
    current_user: CurrentUser = Depends(require_permission(CATALOG)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await service.get_settings_row(db, organization_id=current_user.organization_id)
    updates = payload.model_dump(exclude_unset=True)
    for key in [k for k, v in updates.items() if v is None and k not in ("markup_percentage", "image_url")]:
        updates.pop(key)
    try:
        product = await service.get_product(db, organization_id=current_user.organization_id, product_id=product_id)
        product = await service.update_product(
            db, row=row, product=product, updates=updates, actor_user_id=current_user.user_id
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.product_admin_dict(db, product)


@router.post("/products/{product_id}/sync")
async def sync_aliexpress_product(
    product_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission(CATALOG)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await service.get_settings_row(db, organization_id=current_user.organization_id)
    try:
        product = await service.get_product(db, organization_id=current_user.organization_id, product_id=product_id)
        product = await service.sync_product(db, row=row, product=product)
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.product_admin_dict(db, product)


@router.patch("/variants/{variant_id}")
async def update_aliexpress_variant(
    variant_id: uuid.UUID,
    payload: AliexpressVariantUpdate,
    current_user: CurrentUser = Depends(require_permission(CATALOG)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    updates = payload.model_dump(exclude_unset=True)
    for key in [k for k, v in updates.items() if v is None and k != "price_override_cents"]:
        updates.pop(key)
    try:
        variant = await service.update_variant(
            db, organization_id=current_user.organization_id, variant_id=variant_id, updates=updates
        )
        product = await service.get_product(
            db, organization_id=current_user.organization_id, product_id=variant.product_id
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.product_admin_dict(db, product)


# --- Cliente: checkout ---------------------------------------------------------------------------


@router.get("/products/active/{product_id}")
async def get_aliexpress_product_live(
    product_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("products.read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """La scheda che il cliente ha appena aperto, riletta da AliExpress se
    l'ultima lettura ha più di dieci minuti (Session 87). `available: false`
    vuol dire che nel frattempo AliExpress l'ha tolta: la scheda lo dice
    subito invece di lasciarlo scoprire al pagamento."""
    row = await service.get_settings_row(db, organization_id=current_user.organization_id)
    try:
        product = await service.get_product(db, organization_id=current_user.organization_id, product_id=product_id)
    except service.AliexpressNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Prodotto non trovato.") from exc
    if not row.enabled or product.status != "ACTIVE":
        return {"available": False, "product": None}
    product = await service.refresh_if_stale(db, row=row, product=product, max_age=service.LIVE_CHECK_ON_VIEW)
    percentage = await rules.get_bank_transfer_discount_percentage(db, organization_id=current_user.organization_id)
    card = await service.product_customer_dict(db, product, settings=row, bank_transfer_discount_percentage=percentage)
    return {"available": card is not None and card["in_stock"], "product": card}


@router.get("/orders/quote/mine")
async def get_my_aliexpress_quote(
    variant_id: uuid.UUID,
    quantity: int = 1,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        return await service.get_quote(
            db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id,
            variant_id=variant_id, quantity=quantity,
        )
    except ERRORS as exc:
        raise _http(exc) from exc


@router.post(
    "/orders/mine/request-credit-otp",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit("aliexpress-order-credit-otp", max_requests=5, window_seconds=300))],
)
async def request_my_aliexpress_credit_otp(
    payload: AliexpressOrderCreditOtpRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    via: str | None = None,
) -> dict:
    from app.domains.auth import service as auth_service
    from app.domains.users.models import User

    user = await db.get(User, current_user.user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utente non trovato.")
    try:
        quote = await service.get_quote(
            db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id,
            variant_id=payload.variant_id, quantity=payload.quantity,
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    context_line = (
        f"Stai per acquistare <strong>{quote['product_name']}</strong> "
        f"(ordine da {quote['amount_cents'] / 100:.2f} &euro;) e utilizzare "
        f"<strong>{payload.credit_applied_cents / 100:.2f} JavCash</strong> dal tuo wallet "
        "per pagarne una parte. Usa questo codice per confermare l'operazione."
    )
    method = await auth_service.request_spend_code(
        db, user=user, via_email=via == "email", context_line=context_line
    )
    return {"ok": True, "method": method}


@router.post("/orders/mine", status_code=status.HTTP_201_CREATED)
async def create_my_aliexpress_order(
    payload: AliexpressOrderSelfCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        order = await service.create_order(
            db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id,
            variant_id=payload.variant_id, quantity=payload.quantity, address=payload.address.model_dump(),
            credit_applied_cents=payload.credit_applied_cents, payment_method=payload.payment_method,
            actor_user_id=current_user.user_id, otp_code=payload.otp_code, note=payload.note,
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.order_read_dict(db, order, admin=False)


# --- Cliente: checkout dal carrello ----------------------------------------------------------------
#
# Le stesse tre operazioni di sopra -- preventivo, codice OTP, ordine -- ma
# su ciò che c'è nel carrello invece che su un prodotto solo. Il browser non
# manda mai le righe: le legge il server dal carrello del richiedente.


async def _my_cart_lines(db: AsyncSession, current_user: CurrentUser) -> list[tuple[uuid.UUID, int]]:
    try:
        _, lines = await carts_service.checkout_lines(
            db, customer_user_id=current_user.user_id, shop=service.SHOP
        )
    except (carts_service.CartValidationError, carts_service.CartNotFoundError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return lines


@router.get("/orders/quote/mine/cart")
async def get_my_aliexpress_cart_quote(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    lines = await _my_cart_lines(db, current_user)
    try:
        return await service.get_quote(
            db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id,
            lines=lines,
        )
    except ERRORS as exc:
        raise _http(exc) from exc


@router.post(
    "/orders/mine/cart/request-credit-otp",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit("aliexpress-cart-credit-otp", max_requests=5, window_seconds=300))],
)
async def request_my_aliexpress_cart_credit_otp(
    payload: AliexpressCartCreditOtpRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    via: str | None = None,
) -> dict:
    from app.domains.auth import service as auth_service
    from app.domains.users.models import User

    user = await db.get(User, current_user.user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utente non trovato.")
    lines = await _my_cart_lines(db, current_user)
    try:
        quote = await service.get_quote(
            db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id,
            lines=lines,
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    articles = len(quote["items"])
    what = quote["product_name"] if articles == 1 else f"{articles} articoli"
    context_line = (
        f"Stai per acquistare <strong>{what}</strong> "
        f"(ordine da {quote['amount_cents'] / 100:.2f} &euro;) e utilizzare "
        f"<strong>{payload.credit_applied_cents / 100:.2f} JavCash</strong> dal tuo wallet "
        "per pagarne una parte. Usa questo codice per confermare l'operazione."
    )
    method = await auth_service.request_spend_code(
        db, user=user, via_email=via == "email", context_line=context_line
    )
    return {"ok": True, "method": method}


@router.post("/orders/mine/cart", status_code=status.HTTP_201_CREATED)
async def create_my_aliexpress_order_from_cart(
    payload: AliexpressCartOrderRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Il carrello diventa un ordine, e solo allora si svuota.

    Nell'ordine che conta: l'ordine prima, il carrello dopo. Se la
    creazione fallisce -- saldo insufficiente, OTP sbagliato, articolo
    esaurito nel frattempo -- il cliente ritrova il carrello intatto invece
    di doverlo ricomporre."""
    lines = await _my_cart_lines(db, current_user)
    try:
        order = await service.create_order(
            db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id,
            lines=lines, address=payload.address.model_dump(),
            credit_applied_cents=payload.credit_applied_cents, payment_method=payload.payment_method,
            actor_user_id=current_user.user_id, otp_code=payload.otp_code, note=payload.note,
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    await carts_service.clear(db, customer_user_id=current_user.user_id, shop=service.SHOP)
    return await service.order_read_dict(db, order, admin=False)


@router.get("/orders/mine")
async def list_my_aliexpress_orders(
    current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    orders = await service.list_orders(
        db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id
    )
    return [await service.order_read_dict(db, o, admin=False) for o in orders]


async def _owned(db: AsyncSession, current_user: CurrentUser, order_id: uuid.UUID):
    order = await service.get_owned(
        db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id, order_id=order_id
    )
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ordine non trovato.")
    return order


@router.post("/orders/mine/{order_id}/checkout-session", response_model=CheckoutSessionRead)
async def create_my_aliexpress_checkout_session(
    order_id: uuid.UUID,
    success_url: str,
    cancel_url: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CheckoutSessionRead:
    order = await _owned(db, current_user, order_id)
    if order.status != "AWAITING_PAYMENT":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Questo ordine non è da pagare.")
    try:
        checkout_url = await payments_service.create_checkout_session_for_aliexpress_order(
            db, organization_id=current_user.organization_id, order=order, success_url=success_url,
            cancel_url=cancel_url,
        )
    except payments_service.StripeNotConfiguredError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return CheckoutSessionRead(checkout_url=checkout_url)


@router.patch("/orders/mine/{order_id}/payment-method")
async def change_my_aliexpress_payment_method(
    order_id: uuid.UUID,
    payload: AliexpressOrderPaymentMethodUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    order = await _owned(db, current_user, order_id)
    try:
        order = await service.change_payment_method(
            db, organization_id=current_user.organization_id, order=order,
            new_payment_method=payload.payment_method,
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.order_read_dict(db, order, admin=False)


@router.post(
    "/orders/mine/{order_id}/payment-proof",
    dependencies=[Depends(rate_limit("aliexpress-payment-proof-upload", max_requests=20, window_seconds=300))],
)
async def upload_my_aliexpress_payment_proof(
    order_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    order = await _owned(db, current_user, order_id)
    try:
        order = await service.upload_payment_proof(
            db, organization_id=current_user.organization_id, order=order, file_bytes=await file.read(),
            content_type=file.content_type or "", original_filename=file.filename or "prova-pagamento",
            actor_user_id=current_user.user_id,
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.order_read_dict(db, order, admin=False)


@router.get("/orders/mine/{order_id}/payment-proof-url", response_model=PaymentProofUrlRead)
async def get_my_aliexpress_payment_proof_url(
    order_id: uuid.UUID, current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> PaymentProofUrlRead:
    order = await _owned(db, current_user, order_id)
    if order.payment_proof_storage_key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ricevuta non trovata.")
    return PaymentProofUrlRead(url=service.presigned_payment_proof_url(order))


# --- Admin: ordini ----------------------------------------------------------------------------------


@router.get("/orders")
async def list_aliexpress_orders(
    status_filter: str | None = None,
    current_user: CurrentUser = Depends(require_permission(ORDERS)),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    orders = await service.list_orders(db, organization_id=current_user.organization_id, status_filter=status_filter)
    return [await service.order_read_dict(db, o, admin=True) for o in orders]


@router.post("/orders/{order_id}/confirm-payment")
async def confirm_aliexpress_order_payment(
    order_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission(ORDERS)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        order = await service.confirm_payment(
            db, organization_id=current_user.organization_id, order_id=order_id, actor_user_id=current_user.user_id
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.order_read_dict(db, order, admin=True)


@router.post("/orders/{order_id}/cancel")
async def cancel_aliexpress_order(
    order_id: uuid.UUID,
    payload: AliexpressOrderCancelRequest,
    current_user: CurrentUser = Depends(require_permission(ORDERS)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        order = await service.cancel_order(
            db, organization_id=current_user.organization_id, order_id=order_id, reason=payload.reason,
            actor_user_id=current_user.user_id,
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.order_read_dict(db, order, admin=True)


@router.get("/orders/{order_id}/payment-proof-url", response_model=PaymentProofUrlRead)
async def get_aliexpress_order_payment_proof_url(
    order_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission(ORDERS)),
    db: AsyncSession = Depends(get_db),
) -> PaymentProofUrlRead:
    order = await service.get_org_scoped(db, organization_id=current_user.organization_id, order_id=order_id)
    if order is None or order.payment_proof_storage_key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ricevuta non trovata.")
    return PaymentProofUrlRead(url=service.presigned_payment_proof_url(order))


@router.post("/orders/{order_id}/forward")
async def forward_aliexpress_order(
    order_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission(ORDERS)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """"Invia ad AliExpress": places the order with the supplier if it is not
    there yet. Recorded on the order, never raised."""
    try:
        order = await service.forward_order(
            db, organization_id=current_user.organization_id, order_id=order_id, actor_user_id=current_user.user_id
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.order_read_dict(db, order, admin=True)


@router.post("/orders/{order_id}/sync")
async def sync_aliexpress_order(
    order_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission(ORDERS)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    order = await service.get_org_scoped(db, organization_id=current_user.organization_id, order_id=order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ordine non trovato.")
    if not order.aliexpress_order_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Questo ordine non è ancora su AliExpress.")
    try:
        await service.sync_orders(db, organization_id=current_user.organization_id, orders=[order])
    except ERRORS as exc:
        raise _http(exc) from exc
    await db.refresh(order)
    return await service.order_read_dict(db, order, admin=True)


# --- Autorizzazione dell'account (pubblico: lo chiama AliExpress) -----------------------------


@router.get("/oauth/callback", include_in_schema=False)
async def aliexpress_oauth_callback(request: Request, db: AsyncSession = Depends(get_db)) -> RedirectResponse:
    """Public: AliExpress sends the administrator back here with the code.
    The path is the one registered in the AliExpress portal (served by the
    dashboard, proxied here), so it must not change. Nobody is logged in:
    the signed `state` is what identifies the settings row and proves the
    round trip is ours."""
    params = dict(request.query_params)
    base = get_settings().public_app_base_url.rstrip("/") + "/admin/aliexpress-connected"

    def done(result: str, message: str | None = None) -> RedirectResponse:
        query = {"aliexpress": result, **({"message": message} if message else {})}
        return RedirectResponse(f"{base}?{urllib.parse.urlencode(query)}", status_code=302)

    state = params.get("state", "")
    settings_id = service.oauth_state_settings_id(state)
    row = (
        await service.get_settings_row_any_org(db, settings_id=settings_id) if settings_id is not None else None
    )
    if row is None and settings_id is not None:
        # The link was started from the old imported-products plugin, whose
        # state carries a provider id instead. Both screens send the
        # administrator to the same address registered on AliExpress, so
        # this one door has to open for both until the old one is retired.
        from app.domains.imported_products import service as imported_products_service

        provider = await imported_products_service.get_provider_any_org(db, provider_id=settings_id)
        if provider is not None:
            if not imported_products_service.aliexpress_state_ok(provider, state):
                return done("error", "Richiesta non valida o scaduta: riparti da “Collega AliExpress”.")
            if not params.get("code"):
                return done("error", params.get("error_description") or "AliExpress non ha inviato il codice di autorizzazione.")
            try:
                await imported_products_service.aliexpress_complete_authorisation(
                    db, provider=provider, code=params["code"]
                )
            except aliexpress.AliexpressApiError as exc:
                return done("error", str(exc))
            return done("connected")
    if row is None or not service.oauth_state_ok(row, state):
        return done("error", "Richiesta non valida o scaduta: riparti da “Collega AliExpress”.")
    if not params.get("code"):
        return done("error", params.get("error_description") or "AliExpress non ha inviato il codice di autorizzazione.")
    try:
        await service.complete_authorisation(db, row=row, code=params["code"])
    except aliexpress.AliexpressApiError as exc:
        return done("error", str(exc))
    return done("connected")
