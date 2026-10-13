"""Marketplace 4 -- «Fai la Spesa con Jav»: catalogo, checkout, ordini.

Le regole del cliente sono quelle comuni dei Marketplace
(`marketplaces/rules.py`) e non si ripetono qui: JavCash solo da spendere e
mai per l'intero prezzo, niente cashback, bonifico scontato, IVA aggiunta
al prezzo e congelata sull'ordine, carrello con una spedizione sola.

Quello che cambia rispetto agli altri tre e' il rifornimento: non c'e' un
fornitore da interrogare ne' a cui inoltrare l'ordine. Il catalogo lo scrive
l'amministratore e la merce la spedisce l'organizzazione, quindi niente
prezzi ricalcolati a ogni sync, niente cambio valuta, niente evasione
automatica: un ordine pagato aspetta che qualcuno lo spedisca e ne segni il
tracking.
"""

import html
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import utcnow
from app.core.email import send_html_email_best_effort
from app.core.email_templates import render_email
from app.domains.audit import service as audit_service
from app.domains.jav_market.models import (
    JAV_MARKET_ORDER_PAYMENT_METHODS,
    MAX_QUANTITY,
    PRODUCT_STATUSES,
    SHIPPING_MODES,
    SHOP,
    JavMarketOrder,
    JavMarketOrderItem,
    JavMarketProducer,
    JavMarketProduct,
    JavMarketSettings,
    JavMarketVariant,
)
from app.domains.marketplaces import paging, rules
from app.domains.notifications import service as notifications_service
from app.domains.organizations import service as organizations_service
from app.domains.users.models import User
from app.domains.wallets import service as wallets_service

logger = logging.getLogger(__name__)

#: Quanti articoli diversi in un ordine. Come sugli altri negozi.
MAX_ORDER_LINES = 20

OrderLine = tuple[uuid.UUID, int]


class JavMarketError(Exception):
    """Ogni errore di questo dominio porta un messaggio gia' scritto per il
    cliente, in italiano (CLAUDE.md §6)."""


class JavMarketValidationError(JavMarketError):
    pass


class JavMarketNotFoundError(JavMarketError):
    pass


class InvalidOtpError(JavMarketError):
    pass


ERRORS = (JavMarketValidationError, JavMarketNotFoundError, InvalidOtpError)


# --- Impostazioni ---------------------------------------------------------------------------------


async def get_settings_row(db: AsyncSession, *, organization_id: uuid.UUID) -> JavMarketSettings:
    """La riga di impostazioni dell'organizzazione, creata al primo accesso:
    un negozio nuovo deve poter essere aperto senza che nessuno prepari
    niente a mano nel database."""
    found = await db.execute(
        select(JavMarketSettings).where(JavMarketSettings.organization_id == organization_id)
    )
    row = found.scalar_one_or_none()
    if row is None:
        row = JavMarketSettings(organization_id=organization_id)
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


SETTINGS_FIELDS = (
    "enabled", "shipping_mode", "shipping_flat_cents", "shipping_days",
    "ship_to_country", "auto_forward", "min_order_cents", "free_shipping_threshold_cents",
)


async def update_settings(
    db: AsyncSession, *, row: JavMarketSettings, actor_user_id: uuid.UUID, updates: dict
) -> JavMarketSettings:
    if "shipping_mode" in updates and updates["shipping_mode"] not in SHIPPING_MODES:
        raise JavMarketValidationError("Modalità di spedizione non valida.")
    for field in SETTINGS_FIELDS:
        if field in updates and updates[field] is not None:
            setattr(row, field, updates[field])
    if updates.get("free_shipping_threshold_cents") == 0:
        row.free_shipping_threshold_cents = None
    await audit_service.record(
        db, organization_id=row.organization_id, actor_user_id=actor_user_id,
        action="jav_market.settings_updated", entity_type="jav_market_settings", entity_id=str(row.id),
        new_value={k: v for k, v in updates.items() if k in SETTINGS_FIELDS},
    )
    await db.commit()
    await db.refresh(row)
    return row


def settings_read_dict(row: JavMarketSettings) -> dict:
    return {
        "enabled": row.enabled,
        "shipping_mode": row.shipping_mode,
        "shipping_flat_cents": row.shipping_flat_cents,
        "shipping_days": row.shipping_days,
        "ship_to_country": row.ship_to_country,
        "auto_forward": row.auto_forward,
        "min_order_cents": row.min_order_cents or 0,
        "free_shipping_threshold_cents": row.free_shipping_threshold_cents,
    }


def order_rules(*, settings: JavMarketSettings, merchandise_cents: int) -> dict:
    """Minimo d'ordine e spedizione gratuita, solo di questo negozio.

    `merchandise_cents` è la merce IVA inclusa, spedizione esclusa, prima
    dei JavCash: è la base scelta dall'utente per entrambe le soglie. Non
    solleva: il carrello deve poter dire «mancano X €», è create_order a
    rifiutare l'ordine sotto il minimo."""
    min_order = settings.min_order_cents or 0
    threshold = settings.free_shipping_threshold_cents
    free = threshold is not None and merchandise_cents >= threshold
    return {
        "merchandise_cents": merchandise_cents,
        "min_order_cents": min_order,
        "min_order_missing_cents": max(min_order - merchandise_cents, 0),
        "free_shipping_threshold_cents": threshold,
        "free_shipping": free,
        "free_shipping_missing_cents": (
            max(threshold - merchandise_cents, 0) if threshold is not None and not free else 0
        ),
    }


def min_order_message(missing_cents: int, min_order_cents: int) -> str:
    def eur(cents: int) -> str:
        return f"{cents / 100:.2f}".replace(".", ",") + " €"

    return (
        f"L'ordine minimo su questo shop è di {eur(min_order_cents)} (IVA inclusa): "
        f"aggiungi altri {eur(missing_cents)} di prodotti per procedere."
    )


# --- Produttori -----------------------------------------------------------------------------------


async def list_producers(db: AsyncSession, *, organization_id: uuid.UUID) -> list[JavMarketProducer]:
    rows = await db.execute(
        select(JavMarketProducer)
        .where(JavMarketProducer.organization_id == organization_id)
        .order_by(JavMarketProducer.name)
    )
    return list(rows.scalars().all())


def producer_read_dict(producer: JavMarketProducer | None) -> dict | None:
    if producer is None:
        return None
    return {
        "id": producer.id,
        "name": producer.name,
        "description": producer.description,
        "website_url": producer.website_url,
        "logo_url": producer.logo_url,
        "vat_number": producer.vat_number,
        "email": producer.email,
        "phone": producer.phone,
        "address": producer.address,
        "active": producer.active,
    }


def producer_public_dict(producer: JavMarketProducer | None) -> dict | None:
    """Quello che vede il cliente: chi fa il prodotto, non come fatturargli.
    Partita IVA, email, telefono e indirizzo restano all'amministrazione."""
    if producer is None:
        return None
    return {
        "name": producer.name,
        "description": producer.description,
        "website_url": producer.website_url,
        "logo_url": producer.logo_url,
    }


async def create_producer(
    db: AsyncSession, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID, payload: dict
) -> JavMarketProducer:
    name = (payload.get("name") or "").strip()
    if not name:
        raise JavMarketValidationError("Il nome dell'azienda è obbligatorio.")
    existing = await db.execute(
        select(JavMarketProducer).where(
            JavMarketProducer.organization_id == organization_id, JavMarketProducer.name == name
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise JavMarketValidationError(f"«{name}» è già in elenco: modifica quella scheda invece di crearne un'altra.")
    producer = JavMarketProducer(
        organization_id=organization_id, created_by_user_id=actor_user_id, name=name,
        description=(payload.get("description") or "").strip(),
        website_url=payload.get("website_url"), logo_url=payload.get("logo_url"),
        vat_number=payload.get("vat_number"), email=payload.get("email"),
        phone=payload.get("phone"), address=payload.get("address"),
    )
    db.add(producer)
    await db.commit()
    await db.refresh(producer)
    return producer


async def update_producer(
    db: AsyncSession, *, organization_id: uuid.UUID, producer_id: uuid.UUID, payload: dict
) -> JavMarketProducer:
    producer = await db.get(JavMarketProducer, producer_id)
    if producer is None or producer.organization_id != organization_id:
        raise JavMarketNotFoundError("Azienda non trovata.")
    for field in ("name", "description", "website_url", "logo_url", "vat_number", "email", "phone", "address", "active"):
        if field in payload and payload[field] is not None:
            setattr(producer, field, payload[field].strip() if isinstance(payload[field], str) else payload[field])
    producer.updated_at = utcnow()
    await db.commit()
    await db.refresh(producer)
    return producer


# --- Catalogo -------------------------------------------------------------------------------------


async def _variants(db: AsyncSession, product_id: uuid.UUID) -> list[JavMarketVariant]:
    rows = await db.execute(
        select(JavMarketVariant)
        .where(JavMarketVariant.product_id == product_id)
        .order_by(JavMarketVariant.created_at)
    )
    return list(rows.scalars().all())


def variant_sellable(variant: JavMarketVariant) -> bool:
    return variant.active and (variant.inventory is None or variant.inventory > 0)


async def create_product(
    db: AsyncSession, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID, payload: dict
) -> JavMarketProduct:
    """Un prodotto nuovo, con le sue varianti. Almeno una: un prodotto senza
    varianti non sarebbe comprabile, e crearlo per poi scoprirlo al primo
    cliente sarebbe il modo peggiore di accorgersene."""
    name = (payload.get("name") or "").strip()
    if not name:
        raise JavMarketValidationError("Il nome del prodotto è obbligatorio.")
    varianti = payload.get("variants") or []
    if not varianti:
        raise JavMarketValidationError("Serve almeno una variante con il suo prezzo.")
    rules.check_credit_percentage(int(payload.get("credit_discount_percentage") or 0))
    if payload.get("producer_id"):
        producer = await db.get(JavMarketProducer, payload["producer_id"])
        if producer is None or producer.organization_id != organization_id:
            raise JavMarketNotFoundError("Azienda produttrice non trovata.")

    product = JavMarketProduct(
        organization_id=organization_id, created_by_user_id=actor_user_id, name=name,
        description=(payload.get("description") or "").strip(),
        image_url=payload.get("image_url"), images=payload.get("images") or [],
        status=payload.get("status") or "ACTIVE",
        credit_discount_percentage=int(payload.get("credit_discount_percentage") or 0),
        unit_cost_cents=payload.get("unit_cost_cents"),
        producer_id=payload.get("producer_id"),
    )
    db.add(product)
    await db.flush()
    for v in varianti:
        _add_variant(db, product_id=product.id, payload=v)
    await db.commit()
    await db.refresh(product)
    return product


def _add_variant(db: AsyncSession, *, product_id: uuid.UUID, payload: dict) -> None:
    price = int(payload.get("price_cents") or 0)
    if price <= 0:
        raise JavMarketValidationError("Ogni variante deve avere un prezzo maggiore di zero.")
    db.add(JavMarketVariant(
        product_id=product_id,
        label=(payload.get("label") or "Unica").strip()[:255],
        sku=(payload.get("sku") or None),
        image_url=payload.get("image_url"),
        price_cents=price,
        inventory=payload.get("inventory"),
        active=payload.get("active", True),
    ))


async def update_product(
    db: AsyncSession, *, organization_id: uuid.UUID, product_id: uuid.UUID, payload: dict
) -> JavMarketProduct:
    product = await db.get(JavMarketProduct, product_id)
    if product is None or product.organization_id != organization_id:
        raise JavMarketNotFoundError("Prodotto non trovato.")
    if "credit_discount_percentage" in payload and payload["credit_discount_percentage"] is not None:
        rules.check_credit_percentage(int(payload["credit_discount_percentage"]))
    if "status" in payload and payload["status"] not in (None, *PRODUCT_STATUSES):
        raise JavMarketValidationError("Stato del prodotto non valido.")
    for field in ("name", "description", "image_url", "images", "status",
                  "credit_discount_percentage", "unit_cost_cents", "producer_id"):
        if field in payload and payload[field] is not None:
            setattr(product, field, payload[field])
    # La foto si puo' anche togliere: un null esplicito qui vuol dire "senza foto".
    if "image_url" in payload and payload["image_url"] is None:
        product.image_url = None
    product.updated_at = utcnow()
    await db.commit()
    await db.refresh(product)
    return product


async def update_variant(
    db: AsyncSession, *, organization_id: uuid.UUID, variant_id: uuid.UUID, payload: dict
) -> JavMarketVariant:
    variant = await db.get(JavMarketVariant, variant_id)
    product = await db.get(JavMarketProduct, variant.product_id) if variant else None
    if variant is None or product is None or product.organization_id != organization_id:
        raise JavMarketNotFoundError("Variante non trovata.")
    if "price_cents" in payload and payload["price_cents"] is not None and int(payload["price_cents"]) <= 0:
        raise JavMarketValidationError("Il prezzo deve essere maggiore di zero.")
    for field in ("label", "sku", "image_url", "price_cents", "inventory", "active"):
        if field in payload and payload[field] is not None:
            setattr(variant, field, payload[field])
    await db.commit()
    await db.refresh(variant)
    return variant


async def add_variant(
    db: AsyncSession, *, organization_id: uuid.UUID, product_id: uuid.UUID, payload: dict
) -> JavMarketProduct:
    product = await db.get(JavMarketProduct, product_id)
    if product is None or product.organization_id != organization_id:
        raise JavMarketNotFoundError("Prodotto non trovato.")
    _add_variant(db, product_id=product.id, payload=payload)
    await db.commit()
    await db.refresh(product)
    return product


async def list_products(db: AsyncSession, *, organization_id: uuid.UUID) -> list[JavMarketProduct]:
    rows = await db.execute(
        select(JavMarketProduct)
        .where(JavMarketProduct.organization_id == organization_id)
        .order_by(JavMarketProduct.created_at.desc())
    )
    return list(rows.scalars().all())


async def product_read_dict(db: AsyncSession, product: JavMarketProduct, *, admin: bool) -> dict:
    variants = await _variants(db, product.id)
    producer = await db.get(JavMarketProducer, product.producer_id) if product.producer_id else None
    out = {
        "id": product.id,
        "name": product.name,
        "description": product.description,
        "image_url": product.image_url,
        "images": product.images or [],
        "status": product.status,
        "credit_discount_percentage": product.credit_discount_percentage,
        "producer": producer_read_dict(producer) if admin else producer_public_dict(producer),
        "variants": [
            {
                "id": v.id, "label": v.label, "sku": v.sku, "image_url": v.image_url,
                "price_cents": v.price_cents, "inventory": v.inventory, "active": v.active,
                "in_stock": variant_sellable(v),
            }
            for v in variants
        ],
    }
    if admin:
        out["unit_cost_cents"] = product.unit_cost_cents
        out["producer_id"] = product.producer_id
    return out


async def shop_card(
    db: AsyncSession, *, product: JavMarketProduct, settings: JavMarketSettings,
    bank_transfer_discount_percentage: int, category_ids: list[uuid.UUID] | None = None,
) -> dict | None:
    """La scheda nella griglia del cliente: stessa forma degli altri negozi,
    cosi' lo Shop la disegna senza sapere da quale negozio venga."""
    from app.domains.shop_categories import service as shop_categories_service

    variants = [v for v in await _variants(db, product.id) if v.active]
    if not variants:
        return None
    producer = await db.get(JavMarketProducer, product.producer_id) if product.producer_id else None
    prices = [v.price_cents for v in variants]
    return {
        "id": product.id,
        "category_ids": category_ids if category_ids is not None
        else await shop_categories_service.category_ids_for_product(
            db, organization_id=product.organization_id, shop=SHOP, product_id=product.id
        ),
        "name": product.name,
        "description": product.description,
        "image_url": product.image_url,
        "images": product.images or [],
        "min_price_cents": min(prices),
        "max_price_cents": max(prices),
        "credit_discount_percentage": product.credit_discount_percentage,
        "shipping_days": settings.shipping_days,
        "shipping_included": settings.shipping_mode == "INCLUDED",
        "shipping_flat_cents": 0 if settings.shipping_mode == "INCLUDED" else (settings.shipping_flat_cents or 0),
        "min_order_cents": settings.min_order_cents or 0,
        "free_shipping_threshold_cents": settings.free_shipping_threshold_cents,
        "bank_transfer_discount_percentage": bank_transfer_discount_percentage,
        "in_stock": any(variant_sellable(v) for v in variants),
        "producer": producer_public_dict(producer),
        "variants": [
            {
                "id": v.id, "label": v.label, "image_url": v.image_url,
                "price_cents": v.price_cents, "in_stock": variant_sellable(v),
            }
            for v in variants
        ],
    }


async def customer_products(db: AsyncSession, *, organization_id: uuid.UUID) -> list[dict]:
    row = await get_settings_row(db, organization_id=organization_id)
    if not row.enabled:
        return []
    discount = await rules.get_bank_transfer_discount_percentage(db, organization_id=organization_id)
    out = []
    for product in await list_products(db, organization_id=organization_id):
        if product.status != "ACTIVE":
            continue
        card = await shop_card(
            db, product=product, settings=row, bank_transfer_discount_percentage=discount
        )
        if card is not None:
            out.append(card)
    return out


async def customer_products_page(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    offset: int = 0,
    limit: int = paging.PAGE_SIZE,
    search: str | None = None,
    category_id: uuid.UUID | None = None,
) -> dict:
    """Session 89: la vetrina a pagine («Mostra altri prodotti»), come tutti
    i Marketplace: vedi marketplaces/paging.py."""
    from app.domains.shop_categories import service as shop_categories_service

    row = await get_settings_row(db, organization_id=organization_id)
    if not row.enabled:
        return paging.empty_page(offset, limit)
    discount = await rules.get_bank_transfer_discount_percentage(db, organization_id=organization_id)

    async def cards(products: list[JavMarketProduct]) -> list[dict | None]:
        categories = await shop_categories_service.category_ids_by_product(
            db, organization_id=organization_id, shop=SHOP, product_ids=[p.id for p in products],
        )
        return [
            await shop_card(
                db, product=product, settings=row, bank_transfer_discount_percentage=discount,
                category_ids=categories.get(product.id, []),
            )
            for product in products
        ]

    return await paging.customer_page(
        db, model=JavMarketProduct, shop=SHOP, organization_id=organization_id, build_cards=cards,
        offset=offset, limit=limit, search=search, category_id=category_id,
    )


# --- Checkout -------------------------------------------------------------------------------------


def _lines_from(variant_id: uuid.UUID | None, quantity: int, lines: list[OrderLine] | None) -> list[OrderLine]:
    if lines is not None:
        if not lines:
            raise JavMarketValidationError("Il carrello è vuoto.")
        if len(lines) > MAX_ORDER_LINES:
            raise JavMarketValidationError(f"Al massimo {MAX_ORDER_LINES} articoli diversi per ordine.")
        return lines
    if variant_id is None:
        raise JavMarketValidationError("Nessun prodotto da ordinare.")
    return [(variant_id, quantity)]


async def _sellable(
    db: AsyncSession, *, organization_id: uuid.UUID, variant_id: uuid.UUID
) -> tuple[JavMarketProduct, JavMarketVariant]:
    variant = await db.get(JavMarketVariant, variant_id)
    product = await db.get(JavMarketProduct, variant.product_id) if variant else None
    if variant is None or product is None or product.organization_id != organization_id or product.status != "ACTIVE":
        raise JavMarketValidationError("Prodotto non disponibile.")
    if not variant_sellable(variant):
        raise JavMarketValidationError("Questa variante al momento non è disponibile.")
    return product, variant


def creditable_cents_per_line(items: list[dict]) -> list[int]:
    """La percentuale di ogni prodotto sul suo valore; la spedizione non
    entra. Stessa regola degli altri negozi, perché al cliente il JavCash
    deve comportarsi uguale ovunque."""
    return [round(i["line_total_cents"] * i["credit_discount_percentage"] / 100) for i in items]


async def order_items(db: AsyncSession, order: JavMarketOrder) -> list[JavMarketOrderItem]:
    rows = await db.execute(
        select(JavMarketOrderItem)
        .where(JavMarketOrderItem.order_id == order.id)
        .order_by(JavMarketOrderItem.created_at, JavMarketOrderItem.id)
    )
    return list(rows.scalars().all())


def items_summary(items: list) -> str:
    def campo(item, nome):
        return item[nome] if isinstance(item, dict) else getattr(item, nome)

    first = campo(items[0], "product_name")
    altri = len(items) - 1
    return first if altri <= 0 else f"{first} + altri {altri}"


def order_code(order: JavMarketOrder) -> str:
    return str(order.number) if getattr(order, "number", None) else str(order.id)[:8].upper()


def order_number(order: JavMarketOrder) -> str:
    return f"JAV-{order_code(order)}"


def bank_transfer_total_cents(*, residual_cents: int, percentage: int) -> int:
    return residual_cents - rules.bank_transfer_discount_cents(
        residual_cents=residual_cents, percentage=percentage
    )


def amount_due_cents(order: JavMarketOrder) -> int:
    """Quanto paga il cliente in euro: il residuo dopo i JavCash, meno lo
    sconto bonifico quando paga con bonifico."""
    return order.amount_cents - order.credit_applied_cents - (order.bank_transfer_discount_cents or 0)


def taxable_base_cents(order: JavMarketOrder) -> int:
    """Quanto vale la vendita al netto dell'IVA. I JavCash non si
    sottraggono: sono un modo di pagare, non uno sconto."""
    return order.amount_cents - (order.bank_transfer_discount_cents or 0) - (order.vat_amount_cents or 0)


async def payment_methods(db: AsyncSession, *, organization_id: uuid.UUID) -> dict:
    return {
        "bank_transfer": await organizations_service.is_bank_transfer_configured(db, organization_id=organization_id),
        "card": await organizations_service.is_stripe_configured(db, organization_id=organization_id),
    }


async def get_quote(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_user_id: uuid.UUID,
    variant_id: uuid.UUID | None = None,
    quantity: int = 1,
    lines: list[OrderLine] | None = None,
) -> dict:
    """Quanto costa questo acquisto. Ogni importo si calcola qui, mai dal
    browser: la spedizione una volta per ordine, l'IVA aggiunta sulla merce,
    il tetto JavCash somma delle righe."""
    row = await get_settings_row(db, organization_id=organization_id)
    if not row.enabled:
        raise JavMarketValidationError("Questo shop non è disponibile al momento.")

    items: list[dict] = []
    seen: set[uuid.UUID] = set()
    for line_variant_id, line_quantity in _lines_from(variant_id, quantity, lines):
        if line_quantity < 1 or line_quantity > MAX_QUANTITY:
            raise JavMarketValidationError(f"Quantità da 1 a {MAX_QUANTITY}.")
        if line_variant_id in seen:
            raise JavMarketValidationError("Lo stesso articolo compare due volte nell'ordine.")
        seen.add(line_variant_id)
        product, variant = await _sellable(db, organization_id=organization_id, variant_id=line_variant_id)
        if variant.inventory is not None and variant.inventory < line_quantity:
            raise JavMarketValidationError(f"«{product.name}»: disponibili solo {variant.inventory} pezzi.")
        producer = await db.get(JavMarketProducer, product.producer_id) if product.producer_id else None
        items.append({
            "variant_id": variant.id,
            "product_id": product.id,
            "product_name": product.name,
            "variant_label": variant.label,
            "producer_name": producer.name if producer else None,
            "image_url": variant.image_url or product.image_url,
            "quantity": line_quantity,
            "unit_price_cents": variant.price_cents,
            "unit_cost_cents": product.unit_cost_cents,
            "line_total_cents": variant.price_cents * line_quantity,
            "credit_discount_percentage": product.credit_discount_percentage,
        })

    items_cents = sum(i["line_total_cents"] for i in items)
    vat_percentage = await rules.get_vat_percentage(db, organization_id=organization_id)
    vat_cents = rules.vat_added_cents(net_cents=items_cents, percentage=vat_percentage)
    order_rule = order_rules(settings=row, merchandise_cents=items_cents + vat_cents)
    shipping_cents = (
        0 if row.shipping_mode == "INCLUDED" or order_rule["free_shipping"] else (row.shipping_flat_cents or 0)
    )
    amount = items_cents + vat_cents + shipping_cents

    per_line = creditable_cents_per_line(items)
    for item, creditable in zip(items, per_line):
        item["max_creditable_cents"] = creditable
    creditable_cents = min(sum(per_line), max(amount - 1, 0))
    credit_percentage = round(creditable_cents * 100 / items_cents) if items_cents > 0 else 0

    wallet = await wallets_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer_user_id)
    methods = await payment_methods(db, organization_id=organization_id)
    discount_percentage = await rules.get_bank_transfer_discount_percentage(db, organization_id=organization_id)
    user = await db.get(User, customer_user_id)
    first = items[0]
    return {
        "items": items,
        "variant_id": first["variant_id"],
        "product_name": first["product_name"],
        "variant_label": first["variant_label"],
        "quantity": first["quantity"],
        "unit_price_cents": first["unit_price_cents"],
        "items_cents": items_cents,
        "vat_cents": vat_cents,
        "vat_percentage": vat_percentage,
        "shipping_cents": shipping_cents,
        "shipping_included": row.shipping_mode == "INCLUDED",
        "shipping_days": row.shipping_days,
        **order_rule,
        "amount_cents": amount,
        "credit_discount_percentage": credit_percentage,
        "max_creditable_cents": creditable_cents,
        "customer_wallet_balance_cents": wallet.balance_cents if wallet else 0,
        "bank_transfer_discount_percentage": discount_percentage,
        "bank_transfer_amount_cents": bank_transfer_total_cents(
            residual_cents=amount, percentage=discount_percentage
        ),
        "bank_transfer_available": methods["bank_transfer"],
        "card_available": methods["card"],
        "default_address": {
            "street": user.residence_street if user else None,
            "city": user.residence_city if user else None,
            "province": user.residence_province if user else None,
            "postal_code": user.residence_postal_code if user else None,
        },
    }


async def freeze_bank_transfer_discount(db: AsyncSession, *, order: JavMarketOrder) -> None:
    """Lo sconto bonifico per il metodo di pagamento di adesso, dalla
    configurazione di oggi -- mai dal browser. Non tocca l'IVA: quella è
    congelata alla creazione (marketplaces/rules.py). Non fa commit."""
    if order.status != "AWAITING_PAYMENT":
        return
    if order.payment_method == "BANK_TRANSFER":
        percentage = await rules.get_bank_transfer_discount_percentage(db, organization_id=order.organization_id)
        order.bank_transfer_discount_cents = rules.bank_transfer_discount_cents(
            residual_cents=order.amount_cents - order.credit_applied_cents, percentage=percentage
        )
    else:
        order.bank_transfer_discount_cents = 0


async def create_order(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_user_id: uuid.UUID,
    address: dict,
    credit_applied_cents: int,
    payment_method: str,
    actor_user_id: uuid.UUID,
    otp_code: str | None,
    note: str | None,
    variant_id: uuid.UUID | None = None,
    quantity: int = 1,
    lines: list[OrderLine] | None = None,
) -> JavMarketOrder:
    """Crea l'ordine con ogni importo ricalcolato qui, mai preso dal
    browser. Nasce multi-riga: il denaro sta sulla testata, la merce sulle
    righe."""
    order_lines = _lines_from(variant_id, quantity, lines)
    quote = await get_quote(
        db, organization_id=organization_id, customer_user_id=customer_user_id, lines=order_lines
    )
    row = await get_settings_row(db, organization_id=organization_id)
    amount = quote["amount_cents"]
    if quote["min_order_missing_cents"] > 0:
        raise JavMarketValidationError(
            min_order_message(quote["min_order_missing_cents"], quote["min_order_cents"])
        )
    if credit_applied_cents < 0 or credit_applied_cents > quote["max_creditable_cents"]:
        raise JavMarketValidationError(
            f"Puoi usare al massimo {quote['max_creditable_cents'] / 100:.2f} JavCash per questo ordine."
        )
    if credit_applied_cents > 0:
        from app.domains.auth import service as auth_service

        if not otp_code or not await auth_service.verify_spend_code(
            db, user_id=customer_user_id, code=otp_code
        ):
            raise InvalidOtpError("Codice o PIN di conferma mancante, non valido o scaduto.")
    if payment_method not in JAV_MARKET_ORDER_PAYMENT_METHODS:
        raise JavMarketValidationError("Metodo di pagamento non valido.")
    methods = await payment_methods(db, organization_id=organization_id)
    if payment_method == "BANK_TRANSFER" and not methods["bank_transfer"]:
        raise JavMarketValidationError("Il pagamento con bonifico non è configurato.")
    if payment_method == "CARD" and not methods["card"]:
        raise JavMarketValidationError("Il pagamento con carta non è configurato.")

    wallet = None
    if credit_applied_cents > 0:
        wallet = await wallets_service.get_or_create_wallet(
            db, organization_id=organization_id, user_id=customer_user_id
        )
        if wallet.balance_cents < credit_applied_cents:
            raise wallets_service.InsufficientBalanceError("Saldo JavCash insufficiente.")

    order = JavMarketOrder(
        organization_id=organization_id,
        customer_user_id=customer_user_id,
        created_by_user_id=actor_user_id,
        items_cents=quote["items_cents"],
        shipping_cents=quote["shipping_cents"],
        amount_cents=amount,
        vat_percentage=quote["vat_percentage"],
        vat_amount_cents=quote["vat_cents"],
        vat_mode="ADDED",
        credit_applied_cents=credit_applied_cents,
        status="AWAITING_PAYMENT",
        payment_method=payment_method,
        note=note,
        recipient_name=address["recipient_name"],
        recipient_phone=address.get("recipient_phone"),
        address_line1=address["address_line1"],
        address_line2=address.get("address_line2"),
        city=address["city"],
        province=address["province"],
        postal_code=address["postal_code"],
        country_code=row.ship_to_country or "IT",
        shipping_days=row.shipping_days,
    )
    db.add(order)
    await db.flush()
    for item in quote["items"]:
        db.add(JavMarketOrderItem(
            order_id=order.id,
            product_id=item["product_id"],
            variant_id=item["variant_id"],
            quantity=item["quantity"],
            unit_price_cents=item["unit_price_cents"],
            unit_cost_cents=item["unit_cost_cents"],
            product_name=item["product_name"][:255],
            variant_label=(item["variant_label"] or None) and item["variant_label"][:255],
            producer_name=(item["producer_name"] or None) and item["producer_name"][:160],
            credit_discount_percentage=item["credit_discount_percentage"],
        ))
    await freeze_bank_transfer_discount(db, order=order)
    riepilogo = items_summary(quote["items"])
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="JAV_MARKET_ORDER_CREATED", entity_type="jav_market_order", entity_id=order.id,
        title=f"Nuovo ordine Fai la Spesa: {riepilogo}",
        body=f"{amount / 100:.2f} EUR -- "
             + " · ".join(f"{i['quantity']} × {i['product_name']}" for i in quote["items"]),
        exclude_user_id=actor_user_id,
    )
    if credit_applied_cents > 0:
        assert wallet is not None
        debit = await wallets_service.debit_wallet_for_jav_market_purchase(
            db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=credit_applied_cents,
            reference_jav_market_order_id=order.id, actor_user_id=actor_user_id,
            note=f"Acquisto {riepilogo}", idempotency_key=f"jav-market-order:{order.id}:credit",
        )
        order.credit_debit_transaction_id = debit.id
    await db.commit()
    await db.refresh(order)
    await _send_order_email(db, order=order)
    return order


# --- Ordini ---------------------------------------------------------------------------------------


async def list_orders(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID | None = None
) -> list[JavMarketOrder]:
    query = select(JavMarketOrder).where(JavMarketOrder.organization_id == organization_id)
    if customer_user_id is not None:
        query = query.where(JavMarketOrder.customer_user_id == customer_user_id)
    rows = await db.execute(query.order_by(JavMarketOrder.created_at.desc()))
    return list(rows.scalars().all())


async def get_org_scoped(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID
) -> JavMarketOrder | None:
    order = await db.get(JavMarketOrder, order_id)
    return order if order is not None and order.organization_id == organization_id else None


async def get_owned(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID, order_id: uuid.UUID
) -> JavMarketOrder | None:
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    return order if order is not None and order.customer_user_id == customer_user_id else None


def delivery_status(order: JavMarketOrder) -> str | None:
    """L'unico stato di spedizione che il cliente vede, con gli stessi
    valori degli altri negozi."""
    if order.status != "PAID":
        return None
    if order.delivered_at:
        return "DELIVERED"
    if order.shipped_at:
        return "SHIPPED"
    return "PREPARING" if order.fulfillment_status != "NOT_SENT" else "RECEIVED"


async def order_read_dict(db: AsyncSession, order: JavMarketOrder, *, admin: bool) -> dict:
    from app.domains.imported_products.service import _resolve_display_name

    items = await order_items(db, order)
    out = {
        "id": order.id,
        "number": order.number,
        "order_code": order_code(order),
        "customer_user_id": order.customer_user_id,
        "customer_display_name": await _resolve_display_name(
            db, organization_id=order.organization_id, user_id=order.customer_user_id
        ),
        "product_name": items_summary(items) if items else "—",
        "product_image_url": None,
        "items": [
            {
                "id": i.id, "product_id": i.product_id, "variant_id": i.variant_id,
                "product_name": i.product_name, "variant_label": i.variant_label,
                "producer_name": i.producer_name,
                "quantity": i.quantity, "unit_price_cents": i.unit_price_cents,
                "line_total_cents": i.unit_price_cents * i.quantity,
                "tracking_number": order.tracking_number, "tracking_url": order.tracking_url,
            }
            for i in items
        ],
        "items_cents": order.items_cents,
        "shipping_cents": order.shipping_cents,
        "amount_cents": order.amount_cents,
        "credit_applied_cents": order.credit_applied_cents,
        "residual_amount_cents": order.amount_cents - order.credit_applied_cents,
        "bank_transfer_discount_cents": order.bank_transfer_discount_cents or 0,
        "bank_transfer_discount_percentage": await rules.get_bank_transfer_discount_percentage(
            db, organization_id=order.organization_id
        ),
        "vat_percentage": order.vat_percentage or 0,
        "vat_amount_cents": order.vat_amount_cents or 0,
        "vat_mode": order.vat_mode,
        "amount_due_cents": amount_due_cents(order),
        "status": order.status,
        "payment_method": order.payment_method,
        "stripe_checkout_session_id": order.stripe_checkout_session_id,
        "payment_proof_uploaded_at": order.payment_proof_uploaded_at,
        "note": order.note,
        "paid_at": order.paid_at,
        "cancelled_at": order.cancelled_at,
        "cancellation_reason": order.cancellation_reason,
        "created_at": order.created_at,
        "recipient_name": order.recipient_name,
        "recipient_phone": order.recipient_phone,
        "address_line1": order.address_line1,
        "address_line2": order.address_line2,
        "city": order.city,
        "province": order.province,
        "postal_code": order.postal_code,
        "country_code": order.country_code,
        "shipping_days": order.shipping_days,
        "delivery_status": delivery_status(order),
        "tracking_number": order.tracking_number,
        "tracking_url": order.tracking_url,
        "shipped_at": order.shipped_at,
        "delivered_at": order.delivered_at,
    }
    if admin:
        costo = sum((i.unit_cost_cents or 0) * i.quantity for i in items) if items else 0
        noto = items and all(i.unit_cost_cents is not None for i in items)
        out.update({
            "fulfillment_status": order.fulfillment_status,
            "tracking_company": order.tracking_company,
            "forwarded_at": order.forwarded_at,
            "forward_error": order.forward_error,
            #: Le aziende a cui questo ordine va mandato, con la loro email:
            #: senza email non si può inoltrare, e l'admin deve vederlo
            #: prima di premere il pulsante, non dopo.
            "producers": [
                {"name": i.producer_name} for i in items if i.producer_name
            ],
            "supplier_cost_cents": costo if noto else None,
            #: Al netto di IVA e sconto: l'IVA non è mai stata nostra.
            "estimated_margin_cents": taxable_base_cents(order) - costo if noto else None,
        })
    return out


async def _mark_paid(
    db: AsyncSession, *, order: JavMarketOrder, by_card: bool, actor_user_id: uuid.UUID | None
) -> None:
    order.status = "PAID"
    order.paid_by_user_id = actor_user_id
    order.paid_at = utcnow()
    items = await order_items(db, order)
    name = items_summary(items) if items else "il tuo ordine"
    await notifications_service.notify_user(
        db, organization_id=order.organization_id, user_id=order.customer_user_id, type_="ORDER_PAID",
        entity_type="jav_market_order", entity_id=order.id,
        title=f"Il tuo ordine per {name} è confermato", body="Ti avvisiamo appena viene spedito.",
    )
    await notifications_service.notify_roles(
        db, organization_id=order.organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="JAV_MARKET_ORDER_PAID", entity_type="jav_market_order", entity_id=order.id,
        title=f"{'Pagamento Stripe' if by_card else 'Bonifico'} confermato: {name}",
        body=f"{amount_due_cents(order) / 100:.2f} EUR -- da preparare e spedire",
    )
    await _send_payment_receipt_email(db, order=order, items=items, by_card=by_card)


async def confirm_payment(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID, actor_user_id: uuid.UUID
) -> JavMarketOrder:
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None:
        raise JavMarketNotFoundError("Ordine non trovato.")
    if order.status != "AWAITING_PAYMENT":
        raise JavMarketValidationError("Questo ordine non è in attesa di pagamento.")
    if order.payment_method == "CARD":
        raise JavMarketValidationError("Un ordine pagato con carta viene confermato automaticamente da Stripe.")
    await _mark_paid(db, order=order, by_card=False, actor_user_id=actor_user_id)
    await db.commit()
    await db.refresh(order)
    await after_paid(db, order=order)
    return order


async def mark_paid_by_session(
    db: AsyncSession, *, organization_id: uuid.UUID, stripe_checkout_session_id: str,
    order_id: str | None = None,
) -> JavMarketOrder | None:
    found = await db.execute(
        select(JavMarketOrder).where(
            JavMarketOrder.organization_id == organization_id,
            JavMarketOrder.stripe_checkout_session_id == stripe_checkout_session_id,
        )
    )
    order = found.scalar_one_or_none()
    if order is None and order_id:
        try:
            order = await get_org_scoped(db, organization_id=organization_id, order_id=uuid.UUID(str(order_id)))
        except ValueError:
            order = None
    if order is None or order.status != "AWAITING_PAYMENT":
        return order
    await _mark_paid(db, order=order, by_card=True, actor_user_id=None)
    await db.commit()
    await db.refresh(order)
    await after_paid(db, order=order)
    return order


async def change_payment_method(
    db: AsyncSession, *, organization_id: uuid.UUID, order: JavMarketOrder, new_payment_method: str
) -> JavMarketOrder:
    if new_payment_method not in JAV_MARKET_ORDER_PAYMENT_METHODS:
        raise JavMarketValidationError("Metodo di pagamento non valido.")
    if order.status != "AWAITING_PAYMENT":
        raise JavMarketValidationError("L'ordine non è più in attesa di pagamento.")
    order.payment_method = new_payment_method
    await freeze_bank_transfer_discount(db, order=order)
    await db.commit()
    await db.refresh(order)
    return order


async def prepare_card_payment(db: AsyncSession, *, order: JavMarketOrder) -> int:
    """Quanto addebitare con Stripe: lo sconto bonifico sparisce, perché non
    si sta pagando con bonifico."""
    order.payment_method = "CARD"
    await freeze_bank_transfer_discount(db, order=order)
    await db.commit()
    await db.refresh(order)
    return amount_due_cents(order)


async def attach_stripe_checkout_session(
    db: AsyncSession, *, order: JavMarketOrder, session_id: str
) -> JavMarketOrder:
    order.payment_method = "CARD"
    order.stripe_checkout_session_id = session_id
    await db.commit()
    await db.refresh(order)
    return order


async def mark_shipped(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID, actor_user_id: uuid.UUID,
    tracking_number: str | None, tracking_url: str | None, tracking_company: str | None,
) -> JavMarketOrder:
    """Qui non c'è un fornitore che avvisa: la spedizione la segna
    l'amministratore, ed è il momento in cui il cliente riceve l'email."""
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None:
        raise JavMarketNotFoundError("Ordine non trovato.")
    if order.status != "PAID":
        raise JavMarketValidationError("Si spedisce solo un ordine già pagato.")
    order.fulfillment_status = "SHIPPED"
    order.tracking_number = (tracking_number or "").strip()[:128] or None
    order.tracking_url = (tracking_url or "").strip()[:1000] or None
    order.tracking_company = (tracking_company or "").strip()[:128] or None
    order.shipped_at = order.shipped_at or utcnow()
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="jav_market.order_shipped", entity_type="jav_market_order", entity_id=str(order.id),
        new_value={"tracking_number": order.tracking_number},
    )
    await db.commit()
    await db.refresh(order)
    await _notify_customer_shipping(db, order=order, delivered=False)
    return order


async def mark_delivered(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID, actor_user_id: uuid.UUID
) -> JavMarketOrder:
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None:
        raise JavMarketNotFoundError("Ordine non trovato.")
    order.fulfillment_status = "DELIVERED"
    order.delivered_at = order.delivered_at or utcnow()
    await db.commit()
    await db.refresh(order)
    await _notify_customer_shipping(db, order=order, delivered=True)
    return order


async def cancel_order(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID, reason: str, actor_user_id: uuid.UUID
) -> JavMarketOrder:
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None:
        raise JavMarketNotFoundError("Ordine non trovato.")
    if order.status != "AWAITING_PAYMENT":
        raise JavMarketValidationError("Si può annullare solo un ordine non ancora pagato.")
    order.status = "CANCELLED"
    order.cancelled_by_user_id = actor_user_id
    order.cancelled_at = utcnow()
    order.cancellation_reason = reason[:500]
    if order.credit_debit_transaction_id:
        # I JavCash spesi tornano nel wallet: la riga di addebito si
        # rovescia, invece di coniare un credito nuovo meno tracciabile.
        await wallets_service.reverse_transaction(
            db, organization_id=organization_id, transaction_id=order.credit_debit_transaction_id,
            actor_user_id=actor_user_id, reason=f"Annullamento ordine {order_number(order)}",
            idempotency_key=f"jav-market-order:{order.id}:credit-reversal",
        )
    await db.commit()
    await db.refresh(order)
    return order


# --- Email ----------------------------------------------------------------------------------------


def _items_html(items: list[JavMarketOrderItem]) -> str:
    return "".join(
        f"<br><strong>{html.escape(i.product_name)}</strong>"
        + (f" — {html.escape(i.variant_label)}" if i.variant_label else "")
        + (f"<br><small>di {html.escape(i.producer_name)}</small>" if i.producer_name else "")
        + f" × {i.quantity} — {i.unit_price_cents * i.quantity / 100:.2f} &euro;"
        for i in items
    )


async def _send_order_email(db: AsyncSession, *, order: JavMarketOrder) -> None:
    """La conferma d'ordine: cosa hai ordinato e come pagarlo."""
    user = await db.get(User, order.customer_user_id)
    if user is None:
        return
    settings = get_settings()
    code = order_code(order)
    items = await order_items(db, order)
    title = items_summary(items) if items else "il tuo ordine"
    body = (
        f"<p>Numero ordine: <strong>#{code}</strong></p>"
        f"<p>{_items_html(items).removeprefix('<br>')}<br>"
        f"Spedizione: {order.shipping_cents / 100:.2f} &euro;"
        + (f" (consegna stimata {html.escape(order.shipping_days)} giorni)" if order.shipping_days else "")
        + f"<br>Totale: <strong>{order.amount_cents / 100:.2f} &euro;</strong>"
        + (f" (di cui {order.credit_applied_cents / 100:.2f} JavCash)" if order.credit_applied_cents else "")
        + "</p>"
        f"<p>Consegna a: {html.escape(order.recipient_name)}, {html.escape(order.address_line1)}, "
        f"{html.escape(order.postal_code)} {html.escape(order.city)} ({html.escape(order.province)})</p>"
    )
    cta_label = cta_url = None
    heading = "Completa il pagamento del tuo ordine"
    if order.payment_method == "CARD":
        import stripe

        from app.domains.payments import service as payments_service

        body += f"<p>Da pagare con carta: <strong>{amount_due_cents(order) / 100:.2f} &euro;</strong></p>"
        try:
            cta_url = await payments_service.create_checkout_session_for_jav_market_order(
                db, organization_id=order.organization_id, order=order,
                success_url=f"{settings.public_app_base_url}/customer?tab=orders",
                cancel_url=f"{settings.public_app_base_url}/customer?tab=orders",
            )
            cta_label = "Paga con carta"
        except (payments_service.StripeNotConfiguredError, stripe.error.StripeError):
            logger.exception("Jav Market order %s confirmation email sent without a Stripe link", order.id)
    else:
        bank = await organizations_service.get_settings(db, organization_id=order.organization_id)
        discount = order.bank_transfer_discount_cents or 0
        body += f"<p>Da pagare con bonifico: <strong>{amount_due_cents(order) / 100:.2f} &euro;</strong>"
        if discount:
            body += (
                f"<br><small>Include lo sconto per il pagamento con bonifico ({discount / 100:.2f} &euro;).</small>"
            )
        body += "</p>"
        if bank.get("bank_iban"):
            body += (
                f"<p><strong>IBAN:</strong> {bank['bank_iban']}<br>"
                f"<strong>Intestatario:</strong> {bank.get('bank_account_holder') or 'Jav'}<br>"
                f"<strong>Causale:</strong> Ordine {code}</p>"
            )
    send_html_email_best_effort(
        context=f"Jav Market order confirmation email (order={order.id})",
        to=user.email,
        subject=f"Conferma ordine - {title} - Jav",
        html_body=render_email(
            preheader=f"Riepilogo del tuo ordine -- {title}", heading=heading, body_html=body,
            cta_label=cta_label, cta_url=cta_url,
        ),
        text_body=f"{heading}: {title}, totale {order.amount_cents / 100:.2f} EUR.",
    )


async def _send_payment_receipt_email(
    db: AsyncSession, *, order: JavMarketOrder, items: list[JavMarketOrderItem], by_card: bool
) -> None:
    """La ricevuta: cosa hai pagato. Ripete l'elenco invece di rimandare
    alla prima email -- una ricevuta che non si basta da sola non serve."""
    user = await db.get(User, order.customer_user_id)
    if user is None:
        return
    code = order_code(order)
    title = items_summary(items) if items else "il tuo ordine"
    body = (
        f"<p>Numero ordine: <strong>#{code}</strong></p>"
        f"<p>{_items_html(items).removeprefix('<br>')}</p>"
        f"<p>Spedizione: {order.shipping_cents / 100:.2f} &euro;<br>"
    )
    if order.credit_applied_cents:
        body += f"JavCash utilizzati: -{order.credit_applied_cents / 100:.2f}<br>"
    if order.bank_transfer_discount_cents:
        body += f"Sconto per pagamento con bonifico: -{order.bank_transfer_discount_cents / 100:.2f} &euro;<br>"
    body += (
        f"<strong>Totale pagato: {amount_due_cents(order) / 100:.2f} &euro;</strong> "
        f"({'carta' if by_card else 'bonifico'})</p>"
    )
    if order.vat_amount_cents:
        body += f"<p><small>IVA {order.vat_percentage}%: {order.vat_amount_cents / 100:.2f} &euro;</small></p>"
    body += "<p>Prepariamo la spedizione: ti avvisiamo appena parte.</p>"
    send_html_email_best_effort(
        context=f"Jav Market payment receipt email (order={order.id})",
        to=user.email,
        subject=f"Pagamento ricevuto - ordine #{code} - Jav",
        html_body=render_email(
            preheader=f"Ricevuta di pagamento -- {title}", heading="Pagamento ricevuto, grazie",
            body_html=body, cta_label=None, cta_url=None,
        ),
        text_body=f"Pagamento ricevuto per l'ordine #{code}: {amount_due_cents(order) / 100:.2f} EUR.",
    )


async def _notify_customer_shipping(db: AsyncSession, *, order: JavMarketOrder, delivered: bool) -> None:
    items = await order_items(db, order)
    name = items_summary(items) if items else "il tuo ordine"
    title = f"{name} {'è stato consegnato' if delivered else 'è in viaggio verso di te'}"
    await notifications_service.notify_user(
        db, organization_id=order.organization_id, user_id=order.customer_user_id, type_="ORDER_SHIPPED",
        entity_type="jav_market_order", entity_id=order.id, title=title,
        body=None if delivered else (f"Numero di tracking: {order.tracking_number}" if order.tracking_number else None),
    )
    user = await db.get(User, order.customer_user_id)
    if user is None:
        return
    body = (
        f"<p>Numero ordine: <strong>#{order_code(order)}</strong></p>"
        f"<p><strong>{html.escape(name)}</strong> {'è stato consegnato' if delivered else 'è in viaggio verso di te'}.</p>"
    )
    if not delivered and order.tracking_number:
        body += f"<p>Numero di tracking: <strong>{html.escape(order.tracking_number)}</strong></p>"
    send_html_email_best_effort(
        context=f"Jav Market shipping email (order={order.id}, delivered={delivered})",
        to=user.email,
        subject=f"{'Consegnato' if delivered else 'Spedito'}: {name} - Jav",
        html_body=render_email(
            preheader=title, heading=title, body_html=body,
            cta_label=None if delivered or not order.tracking_url else "Segui la spedizione",
            cta_url=None if delivered else order.tracking_url,
        ),
        text_body=title,
    )


# --- L'ordine che parte verso l'azienda (Session 80) -----------------------------------------------


async def _producers_of(db: AsyncSession, order: JavMarketOrder) -> dict:
    """Le righe dell'ordine raggruppate per azienda produttrice.

    Un ordine può contenere prodotti di aziende diverse: ciascuna deve
    ricevere **solo le sue righe**, perché è quello che deve preparare e
    perché il resto non la riguarda. Le righe senza azienda finiscono sotto
    `None` e le gestisce chi chiama: non c'è nessuno a cui mandarle."""
    gruppi: dict = {}
    for item in await order_items(db, order):
        product = await db.get(JavMarketProduct, item.product_id)
        producer = (
            await db.get(JavMarketProducer, product.producer_id)
            if product is not None and product.producer_id else None
        )
        chiave = producer.id if producer is not None else None
        gruppi.setdefault(chiave, {"producer": producer, "items": []})["items"].append(item)
    return gruppi


def _supplier_email_html(order: JavMarketOrder, items: list[JavMarketOrderItem], *, note: str | None) -> str:
    """Cosa serve all'azienda per preparare e spedire: cosa, quanto, e dove.

    **Nessun prezzo.** Quello che il cliente ha pagato è un fatto nostro, e
    mandarlo al fornitore significherebbe mostrargli il ricarico. Se un
    domani servisse un importo, quello giusto è il costo d'acquisto
    (`unit_cost_cents`), non il prezzo di vendita."""
    righe = "".join(
        f"<tr>"
        f"<td style=\"padding:6px 0\"><strong>{html.escape(i.product_name)}</strong>"
        + (f"<br><small>{html.escape(i.variant_label)}</small>" if i.variant_label else "")
        + "</td>"
        f"<td style=\"padding:6px 0;text-align:right\">× {i.quantity}</td>"
        f"</tr>"
        for i in items
    )
    corpo = (
        f"<p>Ordine <strong>#{order_code(order)}</strong> del "
        f"{order.created_at.strftime('%d/%m/%Y')}.</p>"
        f"<table style=\"width:100%;border-collapse:collapse;font-size:14px\">{righe}</table>"
        "<p style=\"margin-top:16px\"><strong>Consegnare a:</strong><br>"
        f"{html.escape(order.recipient_name)}<br>"
        f"{html.escape(order.address_line1)}"
        + (f"<br>{html.escape(order.address_line2)}" if order.address_line2 else "")
        + f"<br>{html.escape(order.postal_code)} {html.escape(order.city)} ({html.escape(order.province)})"
        + f"<br>{html.escape(order.country_code)}"
        + (f"<br>Telefono: {html.escape(order.recipient_phone)}" if order.recipient_phone else "")
        + "</p>"
    )
    if note:
        corpo += f"<p><strong>Note dal cliente:</strong> {html.escape(note)}</p>"
    corpo += (
        "<p>Quando la spedizione parte, rispondi a questa email con il "
        "corriere e il numero di tracking: lo giriamo noi al cliente.</p>"
    )
    return corpo


async def forward_order(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID, actor_user_id: uuid.UUID | None
) -> JavMarketOrder:
    """Manda l'ordine alle aziende che devono preparare la merce.

    Una email per azienda, con dentro solo le sue righe e l'indirizzo di
    consegna. Si può rifare: se una email si perde, l'amministratore
    ripreme il pulsante e riparte, perché qui non si crea niente dall'altra
    parte -- a differenza di AliExpress, dove un secondo invio sarebbe un
    secondo acquisto. L'automatismo invece passa di qui una volta sola
    (vedi after_paid).

    Si inoltra solo un ordine **pagato**: mandare a un'azienda una merce da
    preparare prima di aver incassato è il modo più rapido di regalarla.
    """
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None:
        raise JavMarketNotFoundError("Ordine non trovato.")
    if order.status != "PAID":
        raise JavMarketValidationError("Si invia all'azienda solo un ordine già pagato dal cliente.")

    gruppi = await _producers_of(db, order)
    senza_azienda = gruppi.pop(None, None)
    if not gruppi:
        raise JavMarketValidationError(
            "Nessun prodotto di questo ordine ha un'azienda produttrice: assegnala dal catalogo e riprova."
        )

    mandate, problemi = 0, []
    for gruppo in gruppi.values():
        producer = gruppo["producer"]
        if not producer.email:
            problemi.append(f"«{producer.name}» non ha un'email in scheda")
            continue
        inviata = send_html_email_best_effort(
            context=f"Jav Market supplier order (order={order.id}, producer={producer.id})",
            to=producer.email,
            subject=f"Nuovo ordine #{order_code(order)} da Jav",
            html_body=render_email(
                preheader=f"Ordine #{order_code(order)} da preparare",
                heading="Un nuovo ordine da preparare",
                body_html=_supplier_email_html(order, gruppo["items"], note=order.note),
                cta_label=None, cta_url=None,
            ),
            text_body=(
                f"Ordine #{order_code(order)}: "
                + ", ".join(f"{i.quantity} × {i.product_name}" for i in gruppo["items"])
                + f". Consegna a {order.recipient_name}, {order.address_line1}, "
                f"{order.postal_code} {order.city} ({order.province})."
            ),
        )
        if inviata:
            mandate += 1
        else:
            problemi.append(f"l'email a «{producer.name}» non è partita")

    if senza_azienda:
        problemi.append(
            "senza azienda: " + ", ".join(i.product_name for i in senza_azienda["items"])
        )

    order.forward_error = "; ".join(problemi)[:500] or None
    if mandate:
        order.fulfillment_status = "SENT"
        order.forwarded_at = order.forwarded_at or utcnow()
        order.forwarded_by_user_id = actor_user_id
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="jav_market.order_forwarded", entity_type="jav_market_order", entity_id=str(order.id),
        new_value={
            "aziende": [g["producer"].name for g in gruppi.values()],
            "email_inviate": mandate,
            "problemi": problemi,
        },
    )
    if problemi:
        # Lo staff deve saperlo subito: una riga senza azienda o una email
        # che non parte vuol dire merce che nessuno sta preparando.
        await notifications_service.notify_roles(
            db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
            type_="JAV_MARKET_ORDER_FORWARD_ISSUE", entity_type="jav_market_order", entity_id=order.id,
            title=f"Ordine #{order_code(order)}: invio alle aziende incompleto",
            body="; ".join(problemi)[:1000],
        )
    await db.commit()
    await db.refresh(order)
    if not mandate:
        raise JavMarketValidationError(
            "Nessuna email è partita: " + ("; ".join(problemi) or "nessuna azienda raggiungibile.")
        )
    return order


async def after_paid(db: AsyncSession, *, order: JavMarketOrder) -> None:
    """Un ordine appena pagato parte da solo verso le aziende, se
    l'amministratore ha acceso l'automatismo; altrimenti aspetta il
    pulsante «Invia alle aziende».

    Un invio fallito non deve far fallire il pagamento, che a questo punto
    è già incassato: l'errore resta scritto sull'ordine e lo staff riceve
    la notifica."""
    row = await get_settings_row(db, organization_id=order.organization_id)
    if not row.auto_forward:
        return
    try:
        await forward_order(
            db, organization_id=order.organization_id, order_id=order.id, actor_user_id=None
        )
    except JavMarketError:
        logger.warning("Invio automatico alle aziende non riuscito per l'ordine %s", order.id)
    except Exception:
        logger.exception("Invio automatico alle aziende non riuscito per l'ordine %s", order.id)
