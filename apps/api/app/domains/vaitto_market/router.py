"""Marketplace 5 -- «Marketplace VAITTO»: API.

Stessi permessi degli altri negozi di prodotti importati, così chi può
gestirne uno li gestisce tutti: `imported_products.manage` per il catalogo,
`wallet.manage` per gli ordini. Le rotte del cliente sotto
`/vaitto-market/orders/mine` ricalcano una per una quelle degli altri
negozi, ed è il motivo per cui «I miei Ordini» li tratta allo stesso modo.
"""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import CurrentUser, get_current_user, require_permission
from app.core.rate_limit import rate_limit
from app.core.storage import UploadValidationError, upload_media
from app.domains.carts import service as carts_service
from app.domains.marketplaces import paging
from app.domains.payments import service as payments_service
from app.domains.vaitto_market import service
from app.domains.vaitto_market.schemas import (
    BulkStatusRequest,
    CheckoutSessionRead,
    ProducerUpdate,
    ProducerWrite,
    ProductUpdate,
    ProductWrite,
    VaittoMarketCartCreditOtpRequest,
    VaittoMarketCartOrderRequest,
    VaittoMarketOrderCancelRequest,
    VaittoMarketOrderCreditOtpRequest,
    VaittoMarketOrderPaymentMethodUpdate,
    VaittoMarketOrderSelfCreateRequest,
    VaittoMarketSettingsRead,
    VaittoMarketSettingsUpdate,
    VaittoMarketShipRequest,
    VariantUpdate,
    VariantWrite,
)

router = APIRouter(prefix="/vaitto-market", tags=["vaitto-market"])

CATALOG = "imported_products.manage"
ORDERS = "wallet.manage"
ERRORS = service.ERRORS


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, service.VaittoMarketNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# --- Admin: impostazioni --------------------------------------------------------------------------


@router.get("/settings", response_model=VaittoMarketSettingsRead)
async def get_vaitto_market_settings(
    current_user: CurrentUser = Depends(require_permission(CATALOG)), db: AsyncSession = Depends(get_db)
) -> VaittoMarketSettingsRead:
    row = await service.get_settings_row(db, organization_id=current_user.organization_id)
    return VaittoMarketSettingsRead(**service.settings_read_dict(row))


@router.patch("/settings", response_model=VaittoMarketSettingsRead)
async def update_vaitto_market_settings(
    payload: VaittoMarketSettingsUpdate,
    current_user: CurrentUser = Depends(require_permission(CATALOG)),
    db: AsyncSession = Depends(get_db),
) -> VaittoMarketSettingsRead:
    row = await service.get_settings_row(db, organization_id=current_user.organization_id)
    try:
        row = await service.update_settings(
            db, row=row, actor_user_id=current_user.user_id,
            updates=payload.model_dump(exclude_unset=True),
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return VaittoMarketSettingsRead(**service.settings_read_dict(row))


# --- Admin: aziende produttrici -------------------------------------------------------------------


@router.get("/producers")
async def list_vaitto_market_producers(
    current_user: CurrentUser = Depends(require_permission(CATALOG)), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    rows = await service.list_producers(db, organization_id=current_user.organization_id)
    return [service.producer_read_dict(p) for p in rows]


@router.post("/producers", status_code=status.HTTP_201_CREATED)
async def create_vaitto_market_producer(
    payload: ProducerWrite,
    current_user: CurrentUser = Depends(require_permission(CATALOG)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        producer = await service.create_producer(
            db, organization_id=current_user.organization_id,
            actor_user_id=current_user.user_id, payload=payload.model_dump(),
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return service.producer_read_dict(producer)


@router.patch("/producers/{producer_id}")
async def update_vaitto_market_producer(
    producer_id: uuid.UUID,
    payload: ProducerUpdate,
    current_user: CurrentUser = Depends(require_permission(CATALOG)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        producer = await service.update_producer(
            db, organization_id=current_user.organization_id, producer_id=producer_id,
            payload=payload.model_dump(exclude_unset=True),
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return service.producer_read_dict(producer)


# --- Admin: catalogo ------------------------------------------------------------------------------


@router.get("/products")
async def list_vaitto_market_products(
    current_user: CurrentUser = Depends(require_permission(CATALOG)), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    return await service.admin_product_dicts(db, organization_id=current_user.organization_id)


# --- Admin: feed Vaitto (Session 88) ---------------------------------------------------------------


def _queue_import(organization_id: uuid.UUID, actor_user_id: uuid.UUID, stash_key: str | None) -> None:
    from app.celery_app import celery_app

    celery_app.send_task(
        "app.celery_app.vaitto_import_feed_task",
        args=[str(organization_id), str(actor_user_id), stash_key],
    )


@router.post(
    "/feed/import",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit("vaitto-feed-import", max_requests=6, window_seconds=600))],
)
async def import_vaitto_feed_now(
    current_user: CurrentUser = Depends(require_permission(CATALOG)), db: AsyncSession = Depends(get_db)
) -> dict:
    """«Aggiorna ora» dal feed. Parte in background: migliaia di righe non
    stanno nei 60 secondi di una richiesta; il pannello legge l'esito da
    GET /settings (last_import_*)."""
    row = await service.get_settings_row(db, organization_id=current_user.organization_id)
    if not row.feed_url:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Manca l'indirizzo del feed Vaitto nelle impostazioni.")
    _queue_import(current_user.organization_id, current_user.user_id, None)
    return {"queued": True}


@router.post(
    "/feed/upload",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit("vaitto-feed-upload", max_requests=6, window_seconds=600))],
)
async def upload_vaitto_feed(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_permission(CATALOG)),
) -> dict:
    """Un CSV nel formato «universal» di Vaitto caricato a mano. Il formato
    si controlla subito, così un file sbagliato si scopre qui e non dopo;
    l'import vero parte in background come quello dal feed."""
    from app.core.storage import stash_private_file
    from app.domains.vaitto_market import feed

    content = await file.read()
    if len(content) > feed.MAX_FEED_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Il file è troppo grande.")
    try:
        groups = feed.parse_feed(content)
    except feed.VaittoFeedError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    key = stash_private_file(
        file_bytes=content, content_type="text/csv",
        key_prefix=f"imports/vaitto/{current_user.organization_id}",
    )
    _queue_import(current_user.organization_id, current_user.user_id, key)
    return {"queued": True, "products": len(groups)}


@router.post("/products/bulk-status")
async def bulk_status_vaitto_market_products(
    payload: BulkStatusRequest,
    current_user: CurrentUser = Depends(require_permission(CATALOG)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.domains.vaitto_market import feed

    try:
        count = await feed.bulk_set_status(
            db, organization_id=current_user.organization_id, status=payload.status,
            producer_id=payload.producer_id, subcategory=payload.subcategory, category_name=payload.category_name,
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return {"updated": count}


@router.get("/facets")
async def vaitto_market_facets(
    current_user: CurrentUser = Depends(require_permission(CATALOG)), db: AsyncSession = Depends(get_db)
) -> dict:
    """Marche e sottocategorie con quanti prodotti hanno e quanti sono
    accesi: i due elenchi da cui si accende e si spegne in blocco."""
    from sqlalchemy import case, func, select

    from app.domains.vaitto_market.feed import SUBCATEGORY_IT
    from app.domains.vaitto_market.models import VaittoMarketProducer, VaittoMarketProduct

    active = func.sum(case((VaittoMarketProduct.status == "ACTIVE", 1), else_=0))
    brands = await db.execute(
        select(VaittoMarketProducer.id, VaittoMarketProducer.name, func.count(VaittoMarketProduct.id), active)
        .join(VaittoMarketProduct, VaittoMarketProduct.producer_id == VaittoMarketProducer.id)
        .where(VaittoMarketProducer.organization_id == current_user.organization_id)
        .group_by(VaittoMarketProducer.id, VaittoMarketProducer.name)
        .order_by(VaittoMarketProducer.name)
    )
    subs = await db.execute(
        select(VaittoMarketProduct.subcategory, func.count(VaittoMarketProduct.id), active)
        .where(
            VaittoMarketProduct.organization_id == current_user.organization_id,
            VaittoMarketProduct.subcategory.is_not(None),
        )
        .group_by(VaittoMarketProduct.subcategory)
        .order_by(VaittoMarketProduct.subcategory)
    )
    return {
        "brands": [{"id": i, "name": n, "products": c, "active": a or 0} for i, n, c, a in brands.all()],
        "subcategories": [
            {"key": k, "name": SUBCATEGORY_IT.get(k, k), "products": c, "active": a or 0} for k, c, a in subs.all()
        ],
    }


@router.post(
    "/images",
    dependencies=[Depends(rate_limit("vaitto-market-image-upload", max_requests=60, window_seconds=300))],
)
async def upload_vaitto_market_image(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_permission(CATALOG)),
) -> dict:
    """Carica una foto dal computer e ne restituisce l'URL pubblico.

    Non tocca nessun prodotto: la scheda «Carica un prodotto» ancora non ha
    un id quando si sceglie la foto, quindi l'URL torna al form, che lo
    manda con il resto in POST/PATCH /products come se fosse stato incollato
    a mano. Stesso bucket pubblico delle foto del catalogo (core/storage.py)."""
    try:
        url = upload_media(
            file_bytes=await file.read(), content_type=file.content_type or "",
            key_prefix=f"photos/vaitto-market/{current_user.organization_id}",
        )
    except UploadValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"image_url": url}


@router.post("/products", status_code=status.HTTP_201_CREATED)
async def create_vaitto_market_product(
    payload: ProductWrite,
    current_user: CurrentUser = Depends(require_permission(CATALOG)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        product = await service.create_product(
            db, organization_id=current_user.organization_id,
            actor_user_id=current_user.user_id, payload=payload.model_dump(),
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return await service.product_read_dict(db, product, admin=True)


@router.patch("/products/{product_id}")
async def update_vaitto_market_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    current_user: CurrentUser = Depends(require_permission(CATALOG)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        product = await service.update_product(
            db, organization_id=current_user.organization_id, product_id=product_id,
            payload=payload.model_dump(exclude_unset=True),
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return await service.product_read_dict(db, product, admin=True)


@router.post("/products/{product_id}/variants", status_code=status.HTTP_201_CREATED)
async def add_vaitto_market_variant(
    product_id: uuid.UUID,
    payload: VariantWrite,
    current_user: CurrentUser = Depends(require_permission(CATALOG)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        product = await service.add_variant(
            db, organization_id=current_user.organization_id, product_id=product_id,
            payload=payload.model_dump(),
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.product_read_dict(db, product, admin=True)


@router.patch("/variants/{variant_id}")
async def update_vaitto_market_variant(
    variant_id: uuid.UUID,
    payload: VariantUpdate,
    current_user: CurrentUser = Depends(require_permission(CATALOG)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        variant = await service.update_variant(
            db, organization_id=current_user.organization_id, variant_id=variant_id,
            payload=payload.model_dump(exclude_unset=True),
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return {"id": variant.id, "label": variant.label, "price_cents": variant.price_cents,
            "inventory": variant.inventory, "active": variant.active}


# --- Cliente: vetrina -----------------------------------------------------------------------------


@router.get("/products/mine")
async def list_my_vaitto_market_products(
    current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    """La griglia del cliente. Vuota quando il negozio è spento: la scheda
    sparisce da sola dallo Shop, senza che nessuno la nasconda a mano.
    Session 89: solo la prima pagina -- la vetrina usa /products/mine/page;
    questa resta per una pagina del browser ancora alla versione di prima."""
    page = await service.customer_products_page(db, organization_id=current_user.organization_id)
    return page["items"]


@router.get("/products/mine/page")
async def page_my_vaitto_market_products(
    offset: int = Query(0, ge=0),
    limit: int = Query(paging.PAGE_SIZE, ge=1, le=paging.MAX_PAGE_SIZE),
    q: str | None = Query(None, max_length=100),
    category_id: uuid.UUID | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """La vetrina a pagine («Mostra altri prodotti»), con ricerca e
    categoria filtrate sul server: vedi marketplaces/paging.py."""
    return await service.customer_products_page(
        db, organization_id=current_user.organization_id, offset=offset, limit=limit,
        search=q, category_id=category_id,
    )


# --- Cliente: checkout ----------------------------------------------------------------------------


@router.get("/orders/quote/mine")
async def get_my_vaitto_market_quote(
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


async def _my_cart_lines(db: AsyncSession, current_user: CurrentUser) -> list[tuple[uuid.UUID, int]]:
    try:
        _, lines = await carts_service.checkout_lines(
            db, customer_user_id=current_user.user_id, shop=service.SHOP
        )
    except (carts_service.CartValidationError, carts_service.CartNotFoundError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return lines


@router.get("/orders/quote/mine/cart")
async def get_my_vaitto_market_cart_quote(
    current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    lines = await _my_cart_lines(db, current_user)
    try:
        return await service.get_quote(
            db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id, lines=lines,
        )
    except ERRORS as exc:
        raise _http(exc) from exc


async def _request_otp(
    db: AsyncSession, current_user: CurrentUser, *, quote: dict, credit_cents: int, via_email: bool = False
) -> dict:
    from app.domains.auth import service as auth_service
    from app.domains.users.models import User

    user = await db.get(User, current_user.user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utente non trovato.")
    articoli = len(quote["items"])
    cosa = quote["product_name"] if articoli == 1 else f"{articoli} articoli"
    method = await auth_service.request_spend_code(
        db, user=user, via_email=via_email,
        context_line=(
            f"Stai per acquistare <strong>{cosa}</strong> "
            f"(ordine da {quote['amount_cents'] / 100:.2f} &euro;) e utilizzare "
            f"<strong>{credit_cents / 100:.2f} JavCash</strong> dal tuo wallet "
            "per pagarne una parte. Usa questo codice per confermare l'operazione."
        ),
    )
    return {"ok": True, "method": method}


@router.post(
    "/orders/mine/request-credit-otp",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit("vaitto-market-credit-otp", max_requests=5, window_seconds=300))],
)
async def request_my_vaitto_market_credit_otp(
    payload: VaittoMarketOrderCreditOtpRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    via: str | None = None,
) -> dict:
    try:
        quote = await service.get_quote(
            db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id,
            variant_id=payload.variant_id, quantity=payload.quantity,
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await _request_otp(
        db, current_user, quote=quote, credit_cents=payload.credit_applied_cents, via_email=via == "email"
    )


@router.post(
    "/orders/mine/cart/request-credit-otp",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit("vaitto-market-cart-credit-otp", max_requests=5, window_seconds=300))],
)
async def request_my_vaitto_market_cart_credit_otp(
    payload: VaittoMarketCartCreditOtpRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    via: str | None = None,
) -> dict:
    lines = await _my_cart_lines(db, current_user)
    try:
        quote = await service.get_quote(
            db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id, lines=lines,
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await _request_otp(
        db, current_user, quote=quote, credit_cents=payload.credit_applied_cents, via_email=via == "email"
    )


@router.post("/orders/mine", status_code=status.HTTP_201_CREATED)
async def create_my_vaitto_market_order(
    payload: VaittoMarketOrderSelfCreateRequest,
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


@router.post("/orders/mine/cart", status_code=status.HTTP_201_CREATED)
async def create_my_vaitto_market_order_from_cart(
    payload: VaittoMarketCartOrderRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Il carrello diventa un ordine, e solo allora si svuota."""
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
async def list_my_vaitto_market_orders(
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


@router.patch("/orders/mine/{order_id}/payment-method")
async def change_my_vaitto_market_payment_method(
    order_id: uuid.UUID,
    payload: VaittoMarketOrderPaymentMethodUpdate,
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


@router.post("/orders/mine/{order_id}/checkout-session", response_model=CheckoutSessionRead)
async def create_my_vaitto_market_checkout_session(
    order_id: uuid.UUID,
    success_url: str | None = None,
    cancel_url: str | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CheckoutSessionRead:
    order = await _owned(db, current_user, order_id)
    base = get_settings().public_app_base_url
    try:
        url = await payments_service.create_checkout_session_for_vaitto_market_order(
            db, organization_id=current_user.organization_id, order=order,
            success_url=success_url or f"{base}/customer?tab=orders",
            cancel_url=cancel_url or f"{base}/customer?tab=orders",
        )
    except payments_service.StripeNotConfiguredError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return CheckoutSessionRead(checkout_url=url)


# --- Admin: ordini --------------------------------------------------------------------------------


@router.get("/orders")
async def list_vaitto_market_orders(
    current_user: CurrentUser = Depends(require_permission(ORDERS)), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    orders = await service.list_orders(db, organization_id=current_user.organization_id)
    return [await service.order_read_dict(db, o, admin=True) for o in orders]


@router.post("/orders/{order_id}/confirm-payment")
async def confirm_vaitto_market_payment(
    order_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission(ORDERS)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        order = await service.confirm_payment(
            db, organization_id=current_user.organization_id, order_id=order_id,
            actor_user_id=current_user.user_id,
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.order_read_dict(db, order, admin=True)


@router.post("/orders/{order_id}/forward")
async def forward_vaitto_market_order(
    order_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission(ORDERS)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Manda l'ordine alle aziende che devono preparare la merce: una email
    per azienda, con le sue righe e l'indirizzo di consegna.

    Si può ripetere. Qui, a differenza di AliExpress, un secondo invio non
    crea un secondo acquisto: è solo una email in più, e serve quando la
    prima si perde."""
    try:
        order = await service.forward_order(
            db, organization_id=current_user.organization_id, order_id=order_id,
            actor_user_id=current_user.user_id,
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.order_read_dict(db, order, admin=True)


@router.post("/orders/{order_id}/ship")
async def ship_vaitto_market_order(
    order_id: uuid.UUID,
    payload: VaittoMarketShipRequest,
    current_user: CurrentUser = Depends(require_permission(ORDERS)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Qui non c'è un fornitore che avvisa: la spedizione la segna
    l'amministratore, ed è quello il momento in cui il cliente riceve
    l'email con il tracking."""
    try:
        order = await service.mark_shipped(
            db, organization_id=current_user.organization_id, order_id=order_id,
            actor_user_id=current_user.user_id, tracking_number=payload.tracking_number,
            tracking_url=payload.tracking_url, tracking_company=payload.tracking_company,
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.order_read_dict(db, order, admin=True)


@router.post("/orders/{order_id}/delivered")
async def deliver_vaitto_market_order(
    order_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission(ORDERS)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        order = await service.mark_delivered(
            db, organization_id=current_user.organization_id, order_id=order_id,
            actor_user_id=current_user.user_id,
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.order_read_dict(db, order, admin=True)


@router.post("/orders/{order_id}/cancel")
async def cancel_vaitto_market_order(
    order_id: uuid.UUID,
    payload: VaittoMarketOrderCancelRequest,
    current_user: CurrentUser = Depends(require_permission(ORDERS)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        order = await service.cancel_order(
            db, organization_id=current_user.organization_id, order_id=order_id,
            reason=payload.reason, actor_user_id=current_user.user_id,
        )
    except ERRORS as exc:
        raise _http(exc) from exc
    return await service.order_read_dict(db, order, admin=True)
