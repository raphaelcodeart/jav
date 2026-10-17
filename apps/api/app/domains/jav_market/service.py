"""Lo Shop -- «Fai la Spesa con Jav»: catalogo, checkout, ordini.

Le regole del cliente sono quelle comuni dei negozi
(`marketplaces/rules.py`) e non si ripetono qui: JavCash solo da spendere e
mai per l'intero prezzo, niente cashback, pagamento con bonifico confermato
dall'amministratore, IVA aggiunta al prezzo e congelata sull'ordine,
carrello con una spedizione sola.

Il rifornimento: non c'e' un fornitore da interrogare via API. Il catalogo
lo scrive l'amministratore, quindi niente prezzi ricalcolati a ogni sync e
niente cambio valuta. La merce la prepara l'azienda che la produce (il
fornitore del prodotto, o della sua categoria): l'ordine pagato le arriva
per email -- uno alla volta, oppure raccolto con gli altri suoi nella coda
«Fornitori da avvisare» (in fondo a questo file) -- e il tracking lo segna
l'amministratore quando il fornitore glielo manda.
"""

import html
import logging
import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.core.email import EmailNotConfiguredError, send_html_email, send_html_email_best_effort
from app.core.email_templates import render_email, render_letter
from app.domains.audit import service as audit_service
from app.domains.club.models import ClubAthlete
from app.domains.customers.models import Company, Customer, CustomerProfile
from app.domains.customers.service import display_name_for
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
    JavMarketSupplierDispatch,
    JavMarketVariant,
)
from app.domains.marketplaces import paging, rules
from app.domains.network.models import AgentProfile
from app.domains.notifications import service as notifications_service
from app.domains.organizations import service as organizations_service
from app.domains.shop_categories.models import ShopCategory, ShopCategoryProduct
from app.domains.users.models import User
from app.domains.wallets import service as wallets_service

logger = logging.getLogger(__name__)

#: Quanti articoli diversi in un ordine.
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


class JavMarketConflictError(JavMarketError):
    """Quello che lo schermo mostrava non è più vero (un ordine già mandato da
    qualcun altro, o da un doppio clic): -> 409, e si ricarica la pagina."""


ERRORS = (JavMarketValidationError, JavMarketNotFoundError, InvalidOtpError, JavMarketConflictError)


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
    "supplier_email_from", "supplier_email_signature",
)

#: Un controllo di forma e basta: chi decide se l'indirizzo esiste è il
#: server di posta. Serve a fermare il refuso evidente prima di un invio.
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


async def update_settings(
    db: AsyncSession, *, row: JavMarketSettings, actor_user_id: uuid.UUID, updates: dict
) -> JavMarketSettings:
    if "shipping_mode" in updates and updates["shipping_mode"] not in SHIPPING_MODES:
        raise JavMarketValidationError("Modalità di spedizione non valida.")
    sender = (updates.get("supplier_email_from") or "").strip()
    if sender and not EMAIL_RE.match(sender):
        raise JavMarketValidationError(
            "L'indirizzo da cui scrivere ai fornitori non sembra un'email valida (es. info@tuodominio.it)."
        )
    for field in SETTINGS_FIELDS:
        if field in updates and updates[field] is not None:
            value = updates[field]
            # Mittente e firma si possono svuotare: un campo vuoto vuol dire
            # «usa quello predefinito», non una stringa vuota da salvare.
            if field in ("supplier_email_from", "supplier_email_signature"):
                value = value.strip() or None
            setattr(row, field, value)
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
        "supplier_email_from": row.supplier_email_from,
        "supplier_email_signature": row.supplier_email_signature,
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
    # L'email si può anche togliere (un campo svuotato arriva come stringa
    # vuota): meglio nessuna email che una vuota, che sembrerebbe compilata.
    if producer.email is not None and not producer.email:
        producer.email = None
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
    db: AsyncSession, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID, payload: dict,
    club_id: uuid.UUID | None = None,
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
        organization_id=organization_id, club_id=club_id, created_by_user_id=actor_user_id, name=name,
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
    db: AsyncSession, *, organization_id: uuid.UUID, product_id: uuid.UUID, payload: dict,
    club_id: uuid.UUID | None = None,
) -> JavMarketProduct:
    product = await db.get(JavMarketProduct, product_id)
    if product is None or product.organization_id != organization_id or product.club_id != club_id:
        raise JavMarketNotFoundError("Prodotto non trovato.")
    if "credit_discount_percentage" in payload and payload["credit_discount_percentage"] is not None:
        rules.check_credit_percentage(int(payload["credit_discount_percentage"]))
    if "status" in payload and payload["status"] not in (None, *PRODUCT_STATUSES):
        raise JavMarketValidationError("Stato del prodotto non valido.")
    if payload.get("producer_id"):
        producer = await db.get(JavMarketProducer, payload["producer_id"])
        if producer is None or producer.organization_id != organization_id:
            raise JavMarketNotFoundError("Azienda produttrice non trovata.")
    for field in ("name", "description", "image_url", "images", "status",
                  "credit_discount_percentage", "unit_cost_cents", "producer_id"):
        if field in payload and payload[field] is not None:
            setattr(product, field, payload[field])
    # La foto si puo' anche togliere: un null esplicito qui vuol dire "senza foto".
    if "image_url" in payload and payload["image_url"] is None:
        product.image_url = None
    # Anche il fornitore: senza, il prodotto prende quello della sua categoria.
    if "producer_id" in payload and payload["producer_id"] is None:
        product.producer_id = None
    product.updated_at = utcnow()
    await db.commit()
    await db.refresh(product)
    return product


async def update_variant(
    db: AsyncSession, *, organization_id: uuid.UUID, variant_id: uuid.UUID, payload: dict,
    club_id: uuid.UUID | None = None,
) -> JavMarketVariant:
    variant = await db.get(JavMarketVariant, variant_id)
    product = await db.get(JavMarketProduct, variant.product_id) if variant else None
    if variant is None or product is None or product.organization_id != organization_id or product.club_id != club_id:
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
    db: AsyncSession, *, organization_id: uuid.UUID, product_id: uuid.UUID, payload: dict,
    club_id: uuid.UUID | None = None,
) -> JavMarketProduct:
    product = await db.get(JavMarketProduct, product_id)
    if product is None or product.organization_id != organization_id or product.club_id != club_id:
        raise JavMarketNotFoundError("Prodotto non trovato.")
    _add_variant(db, product_id=product.id, payload=payload)
    await db.commit()
    await db.refresh(product)
    return product


async def list_products(
    db: AsyncSession, *, organization_id: uuid.UUID, club_id: uuid.UUID | None = None, any_seller: bool = False,
) -> list[JavMarketProduct]:
    """I prodotti di un venditore: lo shop di un club (`club_id`) o quello
    di JudoArteVida (None). `any_seller`: tutti (la vetrina li filtra da sé)."""
    query = select(JavMarketProduct).where(JavMarketProduct.organization_id == organization_id)
    if not any_seller:
        query = query.where(
            JavMarketProduct.club_id == club_id if club_id is not None else JavMarketProduct.club_id.is_(None)
        )
    rows = await db.execute(query.order_by(JavMarketProduct.created_at.desc()))
    return list(rows.scalars().all())


@dataclass(frozen=True)
class ResolvedSupplier:
    """Chi prepara la merce di un prodotto, e perché proprio lui."""

    producer: JavMarketProducer | None
    #: "PRODUCT" = scelto sul prodotto, "CATEGORY" = ereditato dalla
    #: categoria (`category_name`), None = nessuno.
    source: str | None = None
    category_name: str | None = None


async def resolve_suppliers(
    db: AsyncSession, *, organization_id: uuid.UUID, products: Sequence[JavMarketProduct]
) -> dict[uuid.UUID, ResolvedSupplier]:
    """Il fornitore di ogni prodotto: **l'unico posto** in cui si decide.

    Quello scritto sul prodotto, se c'è; altrimenti quello della prima sua
    categoria (in ordine di posizione, poi di nome) che ne ha uno. Il
    prodotto vince perché è la scelta più precisa: «Integratori» va a
    un'azienda, ma la barretta che arriva da un'altra si corregge sul
    prodotto senza toccare la categoria. Una categoria nascosta al cliente
    conta lo stesso: nasconderla toglie un filtro, non cambia chi fa la merce.

    Due query per tutta la lista, mai una per prodotto: la chiama l'elenco
    del catalogo in amministrazione."""
    without = [p.id for p in products if p.producer_id is None]
    via_category: dict[uuid.UUID, tuple[uuid.UUID, str]] = {}
    if without:
        rows = await db.execute(
            select(ShopCategoryProduct.product_id, ShopCategory.producer_id, ShopCategory.name)
            .join(ShopCategory, ShopCategory.id == ShopCategoryProduct.category_id)
            .where(
                ShopCategoryProduct.organization_id == organization_id,
                ShopCategoryProduct.shop == SHOP,
                ShopCategoryProduct.product_id.in_(without),
                ShopCategory.producer_id.is_not(None),
            )
            .order_by(ShopCategory.position, ShopCategory.name)
        )
        for product_id, producer_id, category_name in rows.all():
            via_category.setdefault(product_id, (producer_id, category_name))

    ids = {p.producer_id for p in products if p.producer_id} | {pid for pid, _ in via_category.values()}
    producers: dict[uuid.UUID, JavMarketProducer] = {}
    if ids:
        found = await db.execute(select(JavMarketProducer).where(JavMarketProducer.id.in_(ids)))
        producers = {p.id: p for p in found.scalars().all()}

    out: dict[uuid.UUID, ResolvedSupplier] = {}
    for product in products:
        if product.producer_id:
            out[product.id] = ResolvedSupplier(producers.get(product.producer_id), "PRODUCT")
        elif product.id in via_category:
            producer_id, category_name = via_category[product.id]
            out[product.id] = ResolvedSupplier(producers.get(producer_id), "CATEGORY", category_name)
        else:
            out[product.id] = ResolvedSupplier(None)
    return out


def supplier_brief(producer: JavMarketProducer | None) -> dict | None:
    """Quanto serve all'amministratore per riconoscere un fornitore in un
    elenco, e per capire se gli si può scrivere."""
    if producer is None:
        return None
    return {"id": producer.id, "name": producer.name, "email": producer.email, "active": producer.active}


async def admin_products_read(db: AsyncSession, *, organization_id: uuid.UUID, club_id: uuid.UUID | None = None) -> list[dict]:
    """L'elenco del catalogo in amministrazione (di JudoArteVida, o del club
    `club_id`), con fornitore risolto e categorie lette in blocco."""
    from app.domains.shop_categories import service as shop_categories_service

    products = await list_products(db, organization_id=organization_id, club_id=club_id)
    suppliers = await resolve_suppliers(db, organization_id=organization_id, products=products)
    categories = await shop_categories_service.category_ids_by_product(
        db, organization_id=organization_id, shop=SHOP, product_ids=[p.id for p in products],
    )
    return [
        await product_read_dict(
            db, p, admin=True, supplier=suppliers[p.id], category_ids=categories.get(p.id, [])
        )
        for p in products
    ]


async def product_read_dict(
    db: AsyncSession, product: JavMarketProduct, *, admin: bool,
    supplier: ResolvedSupplier | None = None, category_ids: list[uuid.UUID] | None = None,
) -> dict:
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
        "club_id": product.club_id,
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
        from app.domains.shop_categories import service as shop_categories_service

        if supplier is None:
            supplier = (
                await resolve_suppliers(db, organization_id=product.organization_id, products=[product])
            )[product.id]
        out["unit_cost_cents"] = product.unit_cost_cents
        out["producer_id"] = product.producer_id
        #: Il fornitore a cui andranno gli ordini, anche quando arriva dalla
        #: categoria: l'amministratore deve vederlo sul prodotto, non
        #: dedurlo.
        out["supplier"] = supplier_brief(supplier.producer)
        out["supplier_source"] = supplier.source
        out["supplier_category_name"] = supplier.category_name
        out["category_ids"] = (
            category_ids if category_ids is not None
            else await shop_categories_service.category_ids_for_product(
                db, organization_id=product.organization_id, shop=SHOP, product_id=product.id
            )
        )
    return out


async def shop_card(
    db: AsyncSession, *, product: JavMarketProduct, settings: JavMarketSettings,
    bank_transfer_discount_percentage: int, category_ids: list[uuid.UUID] | None = None,
    sellers: dict | None = None,
) -> dict | None:
    """La scheda nella griglia del cliente: la stessa forma che la vetrina
    a pagine (`marketplaces/paging.py`) si aspetta da ogni negozio."""
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
        #: Chi vende: il club (il suo shop) o JudoArteVida.
        "seller": (sellers or {}).get(product.club_id) if product.club_id else {"club_id": None, "name": "JudoArteVida"},
        #: Con lo shop di JudoArteVida spento i suoi prodotti si guardano e basta.
        "purchasable": product.club_id is not None or settings.enabled,
        "variants": [
            {
                "id": v.id, "label": v.label, "image_url": v.image_url,
                "price_cents": v.price_cents, "in_stock": variant_sellable(v),
            }
            for v in variants
        ],
    }


def seller_filters(*, viewer_club_id: uuid.UUID | None, seller: str | None = None) -> list:
    """Che cosa vede chi compra: lo shop di JudoArteVida e quello del suo
    club (mai lo shop di un altro club). `seller`: "CLUB" o "JAV" per uno solo."""
    from sqlalchemy import or_

    if seller == "JAV" or viewer_club_id is None:
        return [JavMarketProduct.club_id.is_(None)]
    if seller == "CLUB":
        return [JavMarketProduct.club_id == viewer_club_id]
    return [or_(JavMarketProduct.club_id.is_(None), JavMarketProduct.club_id == viewer_club_id)]


async def club_payee(db: AsyncSession, club_id: uuid.UUID | None) -> dict | None:
    """A chi si fa il bonifico di un ordine dello shop di un club: il club
    (IBAN e istruzioni delle sue impostazioni). None = JudoArteVida (i dati
    dell'organizzazione, /organizations/me/payment-info)."""
    from app.domains.club.models import Club

    if club_id is None:
        return None
    club = await db.get(Club, club_id)
    settings = (club.settings or {}) if club else {}
    return {"iban": settings.get("bank_iban"), "holder": settings.get("bank_account_holder") or (club.name if club else ""),
            "instructions": settings.get("bank_transfer_instructions")}


async def seller_names(db: AsyncSession, club_ids: set) -> dict:
    from app.domains.club.models import Club

    ids = {c for c in club_ids if c}
    if not ids:
        return {}
    return {cid: {"club_id": cid, "name": name} for cid, name in (await db.execute(
        select(Club.id, Club.name).where(Club.id.in_(ids)))).all()}


async def customer_products(db: AsyncSession, *, organization_id: uuid.UUID, viewer_club_id: uuid.UUID | None = None) -> list[dict]:
    row = await get_settings_row(db, organization_id=organization_id)
    discount = await rules.get_bank_transfer_discount_percentage(db, organization_id=organization_id)
    out = []
    # Con lo shop di JudoArteVida spento resta quello del club.
    products = [p for p in await list_products(db, organization_id=organization_id, any_seller=True)
                if (p.club_id is None and row.enabled) or (p.club_id is not None and p.club_id == viewer_club_id)]
    sellers = await seller_names(db, {p.club_id for p in products})
    for product in products:
        if product.status != "ACTIVE":
            continue
        card = await shop_card(
            db, product=product, settings=row, bank_transfer_discount_percentage=discount, sellers=sellers,
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
    viewer_club_id: uuid.UUID | None = None,
    seller: str | None = None,
    showcase: bool = False,
) -> dict:
    """La vetrina a pagine («Mostra altri prodotti»), come tutti
    i Marketplace: vedi marketplaces/paging.py. Lo shop di JudoArteVida e
    quello del club di chi guarda (`seller` per uno solo dei due).
    `showcase`: la vetrina che si guarda soltanto e quindi mostra i prodotti
    anche a negozio spento (il sito pubblico, e l'area: lì le schede hanno
    `purchasable` falso e il checkout le rifiuta). `jav_open` dice se lo
    shop di JudoArteVida vende."""
    from app.domains.shop_categories import service as shop_categories_service

    row = await get_settings_row(db, organization_id=organization_id)
    if not row.enabled and not showcase:
        # Lo shop di JudoArteVida è spento: resta quello del club.
        if viewer_club_id is None or seller == "JAV":
            return paging.empty_page(offset, limit)
        seller = "CLUB"
    discount = await rules.get_bank_transfer_discount_percentage(db, organization_id=organization_id)

    async def cards(products: list[JavMarketProduct]) -> list[dict | None]:
        categories = await shop_categories_service.category_ids_by_product(
            db, organization_id=organization_id, shop=SHOP, product_ids=[p.id for p in products],
        )
        sellers = await seller_names(db, {p.club_id for p in products})
        return [
            await shop_card(
                db, product=product, settings=row, bank_transfer_discount_percentage=discount,
                category_ids=categories.get(product.id, []), sellers=sellers,
            )
            for product in products
        ]

    page = await paging.customer_page(
        db, model=JavMarketProduct, shop=SHOP, organization_id=organization_id, build_cards=cards,
        offset=offset, limit=limit, search=search, category_id=category_id,
        scope_filters=seller_filters(viewer_club_id=viewer_club_id, seller=seller),
    )
    return {**page, "jav_open": row.enabled}


async def customer_product(
    db: AsyncSession, *, organization_id: uuid.UUID, product_id: uuid.UUID, viewer_club_id: uuid.UUID | None,
) -> dict | None:
    """Una scheda sola, per aprire un prodotto fuori dalla griglia (il
    desiderio di un figlio nella lista dei desideri, club/judogi.py). Solo
    se chi guarda lo vedrebbe anche nella vetrina."""
    product = await db.get(JavMarketProduct, product_id)
    if (product is None or product.organization_id != organization_id or product.status != "ACTIVE"
            or product.club_id not in (None, viewer_club_id)):
        return None
    row = await get_settings_row(db, organization_id=organization_id)
    discount = await rules.get_bank_transfer_discount_percentage(db, organization_id=organization_id)
    return await shop_card(db, product=product, settings=row, bank_transfer_discount_percentage=discount,
                           sellers=await seller_names(db, {product.club_id}))


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
    entra."""
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
        producer = (
            await resolve_suppliers(db, organization_id=organization_id, products=[product])
        )[product.id].producer
        items.append({
            "variant_id": variant.id,
            "product_id": product.id,
            "product_name": product.name,
            "variant_label": variant.label,
            "producer_id": producer.id if producer else None,
            "producer_name": producer.name if producer else None,
            "image_url": variant.image_url or product.image_url,
            "quantity": line_quantity,
            "unit_price_cents": variant.price_cents,
            "unit_cost_cents": product.unit_cost_cents,
            "line_total_cents": variant.price_cents * line_quantity,
            "credit_discount_percentage": product.credit_discount_percentage,
            "club_id": product.club_id,
        })

    # Un ordine è di un venditore solo: lo shop del club o quello di JudoArteVida.
    sellers_in_cart = {i["club_id"] for i in items}
    if len(sellers_in_cart) > 1:
        raise JavMarketValidationError(
            "Lo shop del club e quello di JudoArteVida si pagano separatamente: fai un ordine per ciascuno."
        )
    seller_club_id = next(iter(sellers_in_cart))
    if seller_club_id is None and not row.enabled:
        raise JavMarketValidationError("Questo shop non è disponibile al momento.")
    items_cents = sum(i["line_total_cents"] for i in items)
    # Il prezzo di un club (un'associazione) è già quello finale: niente IVA aggiunta.
    vat_percentage = 0 if seller_club_id else await rules.get_vat_percentage(db, organization_id=organization_id)
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
    seller = (await seller_names(db, {seller_club_id})).get(seller_club_id) if seller_club_id else None
    return {
        "items": items,
        "seller_club_id": seller_club_id,
        "seller": seller or {"club_id": None, "name": "JudoArteVida"},
        "payee": await club_payee(db, seller_club_id),
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
    athlete_id: uuid.UUID | None = None,
) -> JavMarketOrder:
    """Crea l'ordine con ogni importo ricalcolato qui, mai preso dal
    browser. Nasce multi-riga: il denaro sta sulla testata, la merce sulle
    righe. `athlete_id`, se c'è, deve essere un atleta della famiglia di chi
    compra."""
    if athlete_id is not None:
        athlete = await db.get(ClubAthlete, athlete_id)
        if athlete is None or athlete.organization_id != organization_id or athlete.guardian_user_id != customer_user_id:
            raise JavMarketNotFoundError("Atleta non trovato.")
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

    wallet = None
    if credit_applied_cents > 0:
        wallet = await wallets_service.get_or_create_wallet(
            db, organization_id=organization_id, user_id=customer_user_id
        )
        if wallet.balance_cents < credit_applied_cents:
            raise wallets_service.InsufficientBalanceError("Saldo JavCash insufficiente.")

    if quote["seller_club_id"] is not None and credit_applied_cents:
        raise JavMarketValidationError("Il credito JavCash vale solo nello shop di JudoArteVida.")
    order = JavMarketOrder(
        organization_id=organization_id,
        club_id=quote["seller_club_id"],
        customer_user_id=customer_user_id,
        athlete_id=athlete_id,
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
            producer_id=item["producer_id"],
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
    if athlete_id is not None:
        # Il desiderio dell'atleta per questi prodotti è esaudito
        # (club/judogi.py, lista dei desideri).
        from app.domains.club.judogi import mark_products_ordered

        await mark_products_ordered(
            db, athlete_id=athlete_id, product_ids={item["product_id"] for item in quote["items"]},
            order_id=order.id, actor_user_id=actor_user_id,
        )
    await db.commit()
    await db.refresh(order)
    await _send_order_email(db, order=order)
    return order


# --- Ordini ---------------------------------------------------------------------------------------


async def list_orders(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID | None = None,
    seller_club_id: uuid.UUID | None = None,
) -> list[JavMarketOrder]:
    """`seller_club_id`: solo gli ordini dello shop di quel club."""
    query = select(JavMarketOrder).where(JavMarketOrder.organization_id == organization_id)
    if customer_user_id is not None:
        query = query.where(JavMarketOrder.customer_user_id == customer_user_id)
    if seller_club_id is not None:
        query = query.where(JavMarketOrder.club_id == seller_club_id)
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
    """L'unico stato di spedizione che il cliente vede."""
    if order.status != "PAID":
        return None
    if order.delivered_at:
        return "DELIVERED"
    if order.shipped_at:
        return "SHIPPED"
    return "PREPARING" if order.fulfillment_status != "NOT_SENT" else "RECEIVED"


async def _resolve_display_name(db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID) -> str:
    """Il nome con cui mostrare il cliente: quello da promoter se lo è, poi
    l'anagrafica cliente, infine l'email."""
    agent = (
        await db.execute(
            select(AgentProfile.display_name).where(
                AgentProfile.organization_id == organization_id, AgentProfile.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if agent:
        return agent

    customer = (
        await db.execute(
            select(Customer).where(Customer.organization_id == organization_id, Customer.user_id == user_id)
        )
    ).scalar_one_or_none()
    if customer is not None:
        profile = await db.get(CustomerProfile, customer.id)
        company = await db.get(Company, customer.id)
        name = display_name_for(customer.kind, profile, company)
        if name != "—":
            return name

    user = await db.get(User, user_id)
    return user.email if user else "—"


async def _athlete_name(db: AsyncSession, athlete_id: uuid.UUID | None) -> str | None:
    if athlete_id is None:
        return None
    athlete = await db.get(ClubAthlete, athlete_id)
    return f"{athlete.first_name} {athlete.last_name}" if athlete else None


async def order_read_dict(db: AsyncSession, order: JavMarketOrder, *, admin: bool) -> dict:
    items = await order_items(db, order)
    out = {
        "id": order.id,
        "number": order.number,
        "order_code": order_code(order),
        "customer_user_id": order.customer_user_id,
        "customer_display_name": await _resolve_display_name(
            db, organization_id=order.organization_id, user_id=order.customer_user_id
        ),
        "athlete_id": order.athlete_id,
        "athlete_name": await _athlete_name(db, order.athlete_id),
        "seller": ((await seller_names(db, {order.club_id})).get(order.club_id) if order.club_id
                   else {"club_id": None, "name": "JudoArteVida"}),
        "payee": await club_payee(db, order.club_id),
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
            #: Le righe non ancora mandate a nessun fornitore: zero vuol dire
            #: che il pulsante «Invia alle aziende» non ha più niente da fare.
            "supplier_pending_count": sum(1 for i in items if i.supplier_dispatch_id is None),
            "supplier_cost_cents": costo if noto else None,
            #: Al netto di IVA e sconto: l'IVA non è mai stata nostra.
            "estimated_margin_cents": taxable_base_cents(order) - costo if noto else None,
        })
    return out


async def _mark_paid(db: AsyncSession, *, order: JavMarketOrder, actor_user_id: uuid.UUID | None) -> None:
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
        title=f"Bonifico confermato: {name}",
        body=f"{amount_due_cents(order) / 100:.2f} EUR -- da preparare e spedire",
    )
    await _send_payment_receipt_email(db, order=order, items=items)


async def confirm_payment(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID, actor_user_id: uuid.UUID
) -> JavMarketOrder:
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None:
        raise JavMarketNotFoundError("Ordine non trovato.")
    if order.status != "AWAITING_PAYMENT":
        raise JavMarketValidationError("Questo ordine non è in attesa di pagamento.")
    await _mark_paid(db, order=order, actor_user_id=actor_user_id)
    await db.commit()
    await db.refresh(order)
    await after_paid(db, order=order)
    return order


PAYMENT_PROOF_PRESIGNED_URL_TTL_SECONDS = 300


async def upload_payment_proof(
    db: AsyncSession, *, order: JavMarketOrder, file_bytes: bytes, content_type: str, original_filename: str,
    actor_user_id: uuid.UUID,
) -> JavMarketOrder:
    """Il genitore allega la foto del bonifico a un ordine dello Shop (il
    judogi, il materiale): è un'informazione in più per chi conferma il
    bonifico, mai una conferma. Diversamente dalle quote del club, qui la
    merce parte solo quando la piattaforma ha visto i soldi. Ricaricarla
    sostituisce la precedente."""
    from app.core.storage import UploadValidationError
    from app.core.storage import upload_document as storage_upload_document

    if order.status != "AWAITING_PAYMENT":
        raise JavMarketValidationError("Questo ordine non è in attesa di pagamento.")
    if order.payment_method != "BANK_TRANSFER":
        raise JavMarketValidationError("La prova di pagamento serve solo per gli ordini pagati con bonifico.")
    try:
        order.payment_proof_storage_key = storage_upload_document(
            file_bytes=file_bytes, content_type=content_type,
            key_prefix=f"jav-market-payment-proofs/{order.customer_user_id}",
        )
    except UploadValidationError as exc:
        raise JavMarketValidationError("Carica una foto (JPG o PNG) o un PDF, di massimo 15 MB.") from exc
    order.payment_proof_original_filename = original_filename[:255]
    order.payment_proof_uploaded_at = utcnow()
    await audit_service.record(
        db, organization_id=order.organization_id, actor_user_id=actor_user_id,
        action="jav_market.payment_proof_uploaded", entity_type="jav_market_order", entity_id=str(order.id),
    )
    await notifications_service.notify_roles(
        db, organization_id=order.organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="ORDER_PAYMENT_PROOF_UPLOADED", entity_type="jav_market_order", entity_id=order.id,
        title=f"Prova di bonifico caricata: ordine {order_number(order)}",
        body=f"{amount_due_cents(order) / 100:.2f} EUR -- controlla e conferma il pagamento",
        exclude_user_id=actor_user_id,
    )
    await db.commit()
    await db.refresh(order)
    return order


def presigned_payment_proof_url(order: JavMarketOrder) -> str:
    from app.core.storage import generate_presigned_document_url

    assert order.payment_proof_storage_key is not None  # lo controlla la rotta
    return generate_presigned_document_url(
        storage_key=order.payment_proof_storage_key, expires_in_seconds=PAYMENT_PROOF_PRESIGNED_URL_TTL_SECONDS
    )


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
    if order.payment_method == "BANK_TRANSFER":
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
    db: AsyncSession, *, order: JavMarketOrder, items: list[JavMarketOrderItem]
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
        "(bonifico)</p>"
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


# --- L'ordine che parte verso l'azienda -----------------------------------------------
#
# Ottobre 2026: gli ordini si mandano ai fornitori per riga, non per ordine.
# Una riga è «da mandare» finché `supplier_dispatch_id` è NULL; la segna solo
# un'email partita davvero (`JavMarketSupplierDispatch`). Le strade per
# mandarla sono tre -- la coda «Fornitori da avvisare» (più ordini dello
# stesso fornitore in un'email sola, con anteprima modificabile), il
# pulsante sul singolo ordine e l'invio automatico al pagamento -- e tutte
# segnano le stesse righe: un ordine partito da una strada non riparte
# dall'altra.

#: Il messaggio di quando lo schermo è rimasto indietro rispetto al database.
STALE_QUEUE_MESSAGE = (
    "Nel frattempo qualcosa è cambiato: alcuni di questi ordini sono già stati mandati al fornitore "
    "(forse da un altro amministratore, o da un doppio clic) oppure non sono più da mandare. "
    "Aggiorna la pagina e riprova: nessuna email è partita."
)


async def _effective_producer_ids(
    db: AsyncSession, *, organization_id: uuid.UUID, items: Iterable[JavMarketOrderItem]
) -> dict[uuid.UUID, uuid.UUID | None]:
    """Il fornitore di ogni riga ancora da mandare.

    Quello congelato sulla riga quando c'è. Se manca -- un ordine fatto
    prima che il prodotto o la sua categoria avessero un fornitore -- vale
    quello di oggi: l'avviso «righe senza fornitore» dice all'amministratore
    di assegnarlo, e deve bastare farlo perché la riga entri nella coda. Lo
    si congela sulla riga nel momento in cui parte (`_record_dispatch`)."""
    items = list(items)
    out: dict[uuid.UUID, uuid.UUID | None] = {i.id: i.producer_id for i in items}
    missing = {i.product_id for i in items if i.producer_id is None}
    if missing:
        rows = await db.execute(select(JavMarketProduct).where(JavMarketProduct.id.in_(missing)))
        products = list(rows.scalars().all())
        resolved = await resolve_suppliers(db, organization_id=organization_id, products=products)
        for item in items:
            if item.producer_id is None and item.product_id in resolved:
                producer = resolved[item.product_id].producer
                out[item.id] = producer.id if producer else None
    return out


def _pending_rows_query(organization_id: uuid.UUID):
    """Le righe da mandare: ordine pagato, non ancora spedito né consegnato
    (se la merce è già partita il fornitore non ha più niente da fare), riga
    mai mandata."""
    return (
        select(JavMarketOrderItem, JavMarketOrder)
        .join(JavMarketOrder, JavMarketOrder.id == JavMarketOrderItem.order_id)
        .where(
            JavMarketOrder.organization_id == organization_id,
            JavMarketOrder.status == "PAID",
            JavMarketOrder.shipped_at.is_(None),
            JavMarketOrder.delivered_at.is_(None),
            JavMarketOrderItem.supplier_dispatch_id.is_(None),
        )
        .order_by(JavMarketOrder.number, JavMarketOrderItem.created_at, JavMarketOrderItem.id)
    )


def _line_label(item: JavMarketOrderItem) -> str:
    """«2 × Judogi Kumite – 170 cm». «Unica» non si scrive: è la variante di
    chi di varianti non ne ha, e al fornitore non dice niente."""
    variant = f" – {item.variant_label}" if item.variant_label and item.variant_label != "Unica" else ""
    return f"{item.quantity} × {item.product_name}{variant}"


def supplier_letter(
    *, producer_name: str, orders: Sequence[tuple[JavMarketOrder, Sequence[JavMarketOrderItem]]],
    signature: str | None,
) -> tuple[str, str]:
    """Oggetto e testo della lettera a un fornitore: uno o più ordini, un
    blocco ciascuno, perché ogni ordine va a un indirizzo diverso.

    Testo semplice e non HTML: è quello che l'amministratore legge e corregge
    nell'anteprima, ed è `render_letter` a impaginarlo.

    **Nessun prezzo.** Quello che il cliente ha pagato è un fatto nostro, e
    mandarlo al fornitore significherebbe mostrargli il ricarico. Se un
    domani servisse un importo, quello giusto è il costo d'acquisto
    (`unit_cost_cents`), non il prezzo di vendita."""
    count = len(orders)
    pieces = sum(i.quantity for _order, items in orders for i in items)
    if count == 1:
        subject = f"Nuovo ordine da preparare: #{order_code(orders[0][0])}"
        intro = "vi inviamo un nuovo ordine da preparare e spedire direttamente al cliente."
    else:
        subject = f"{count} nuovi ordini da preparare"
        intro = (
            f"vi inviamo {count} nuovi ordini ({pieces} pezzi in tutto) da preparare e spedire "
            "direttamente ai clienti: ogni ordine va al suo indirizzo."
        )

    blocks = []
    for order, items in orders:
        lines = [f"ORDINE #{order_code(order)} del {order.created_at.strftime('%d/%m/%Y')}"]
        lines += [f"- {_line_label(i)}" for i in items]
        address = ["Consegnare a:", order.recipient_name, order.address_line1]
        if order.address_line2:
            address.append(order.address_line2)
        address.append(f"{order.postal_code} {order.city} ({order.province})")
        address.append(order.country_code)
        if order.recipient_phone:
            address.append(f"Telefono: {order.recipient_phone}")
        block = "\n".join(lines) + "\n\n" + "\n".join(address)
        if order.note:
            block += f"\n\nNote del cliente: {order.note}"
        blocks.append(block)

    closing = (
        "Quando la merce parte, rispondete a questa email indicando per ogni ordine il corriere "
        "e il numero di tracking: lo giriamo noi al cliente."
    )
    body = (
        f"Buongiorno {producer_name},\n\n{intro}\n\n"
        + "\n\n".join(blocks)
        + f"\n\n{closing}\n\n{(signature or '').strip() or 'Grazie,' + chr(10) + 'lo staff di Jav'}"
    )
    return subject, body


def _sender(settings: JavMarketSettings) -> dict:
    """Mittente, risposta e copia nascosta delle email ai fornitori: tutte
    e tre l'indirizzo scelto nelle impostazioni (info@...). La risposta col
    tracking torna lì, e la casella tiene la copia di ogni ordine mandato --
    è anche il modo di rimandarne uno che il fornitore dice di non aver
    ricevuto. Senza impostazione: il mittente predefinito dell'SMTP."""
    address = settings.supplier_email_from or None
    return {"from_address": address, "reply_to": address, "bcc": address}


async def _record_dispatch(
    db: AsyncSession, *, organization_id: uuid.UUID, producer_id: uuid.UUID, source: str,
    to_email: str, subject: str, body_text: str, items: Sequence[JavMarketOrderItem],
    actor_user_id: uuid.UUID | None,
) -> JavMarketSupplierDispatch:
    """Scrive l'invio e segna le sue righe. Si chiama solo **dopo** che
    l'email è partita: è questo a rendere un invio fallito innocuo."""
    dispatch = JavMarketSupplierDispatch(
        organization_id=organization_id, producer_id=producer_id, source=source,
        to_email=to_email[:255], subject=subject[:255], body_text=body_text,
        sent_at=utcnow(), sent_by_user_id=actor_user_id,
    )
    db.add(dispatch)
    await db.flush()
    for item in items:
        item.supplier_dispatch_id = dispatch.id
        # Congelato adesso se non lo era: vedi _effective_producer_ids.
        item.producer_id = item.producer_id or producer_id
    return dispatch


async def _mark_orders_sent(
    db: AsyncSession, *, organization_id: uuid.UUID, orders: Iterable[JavMarketOrder],
    actor_user_id: uuid.UUID | None,
) -> list[JavMarketOrder]:
    """Un ordine passa a «mandato» quando tutte le sue righe che hanno un
    fornitore sono partite: con due fornitori, mandarlo al primo non basta.
    Uno stato già più avanti (spedito, consegnato) non torna indietro."""
    done = []
    for order in orders:
        items = await order_items(db, order)
        effective = await _effective_producer_ids(db, organization_id=organization_id, items=items)
        if not all(i.supplier_dispatch_id is not None for i in items if effective[i.id] is not None):
            continue
        if order.fulfillment_status == "NOT_SENT":
            order.fulfillment_status = "SENT"
        order.forwarded_at = order.forwarded_at or utcnow()
        order.forwarded_by_user_id = actor_user_id
        done.append(order)
    return done


def _queue_order_dict(order: JavMarketOrder, items: Sequence[JavMarketOrderItem]) -> dict:
    return {
        "id": order.id,
        "order_code": order_code(order),
        "created_at": order.created_at,
        "paid_at": order.paid_at,
        "recipient_name": order.recipient_name,
        "city": order.city,
        "province": order.province,
        "items": [
            {"id": i.id, "product_name": i.product_name, "variant_label": i.variant_label, "quantity": i.quantity}
            for i in items
        ],
    }


async def supplier_queue(db: AsyncSession, *, organization_id: uuid.UUID) -> dict:
    """«Fornitori da avvisare»: le righe pagate e non ancora mandate,
    raccolte per fornitore e, dentro, per ordine.

    Le righe che non hanno nessun fornitore stanno in una lista a parte:
    non si possono mandare a nessuno, e l'amministratore deve vederle invece
    di scoprire tra una settimana che quella merce non l'ha preparata
    nessuno."""
    rows = (await db.execute(_pending_rows_query(organization_id))).all()
    effective = await _effective_producer_ids(
        db, organization_id=organization_id, items=[item for item, _order in rows]
    )

    by_producer: dict[uuid.UUID, dict[uuid.UUID, tuple[JavMarketOrder, list[JavMarketOrderItem]]]] = {}
    unassigned = []
    for item, order in rows:
        producer_id = effective[item.id]
        if producer_id is None:
            unassigned.append({
                "item_id": item.id, "order_id": order.id, "order_code": order_code(order),
                "product_id": item.product_id, "product_name": item.product_name,
                "variant_label": item.variant_label, "quantity": item.quantity,
            })
            continue
        by_order = by_producer.setdefault(producer_id, {})
        by_order.setdefault(order.id, (order, []))[1].append(item)

    producers: dict[uuid.UUID, JavMarketProducer] = {}
    if by_producer:
        found = await db.execute(select(JavMarketProducer).where(JavMarketProducer.id.in_(by_producer)))
        producers = {p.id: p for p in found.scalars().all()}

    suppliers = []
    for producer_id, by_order in by_producer.items():
        producer = producers[producer_id]
        orders = list(by_order.values())
        suppliers.append({
            "producer": supplier_brief(producer),
            "order_count": len(orders),
            "item_count": sum(len(items) for _o, items in orders),
            "piece_count": sum(i.quantity for _o, items in orders for i in items),
            "orders": [_queue_order_dict(order, items) for order, items in orders],
        })
    suppliers.sort(key=lambda s: s["producer"]["name"].lower())
    return {"suppliers": suppliers, "unassigned": unassigned}


async def _producer(db: AsyncSession, *, organization_id: uuid.UUID, producer_id: uuid.UUID) -> JavMarketProducer:
    producer = await db.get(JavMarketProducer, producer_id)
    if producer is None or producer.organization_id != organization_id:
        raise JavMarketNotFoundError("Fornitore non trovato.")
    return producer


async def supplier_draft(db: AsyncSession, *, organization_id: uuid.UUID, producer_id: uuid.UUID) -> dict:
    """La lettera pronta da mandare a un fornitore con tutti i suoi ordini
    in attesa, e gli id delle righe che contiene: l'invio manda **quelle**,
    non «tutto quello che c'è in coda in quel momento», così un ordine
    pagato mentre l'amministratore rilegge l'anteprima non parte senza che
    l'abbia visto."""
    producer = await _producer(db, organization_id=organization_id, producer_id=producer_id)
    settings = await get_settings_row(db, organization_id=organization_id)
    rows = (await db.execute(_pending_rows_query(organization_id))).all()
    effective = await _effective_producer_ids(
        db, organization_id=organization_id, items=[item for item, _order in rows]
    )
    by_order: dict[uuid.UUID, tuple[JavMarketOrder, list[JavMarketOrderItem]]] = {}
    for item, order in rows:
        if effective[item.id] == producer.id:
            by_order.setdefault(order.id, (order, []))[1].append(item)
    if not by_order:
        raise JavMarketConflictError(
            f"Non ci sono ordini da mandare a «{producer.name}»: forse sono appena partiti. Aggiorna la pagina."
        )
    orders = list(by_order.values())
    subject, body = supplier_letter(
        producer_name=producer.name, orders=orders, signature=settings.supplier_email_signature
    )
    return {
        "producer_id": producer.id,
        "producer_name": producer.name,
        "to_email": producer.email or "",
        "from_email": settings.supplier_email_from,
        "subject": subject,
        "body_text": body,
        "item_ids": [i.id for _o, items in orders for i in items],
        "order_codes": [order_code(o) for o, _items in orders],
    }


async def send_supplier_dispatch(
    db: AsyncSession, *, organization_id: uuid.UUID, producer_id: uuid.UUID, to_email: str,
    subject: str, body_text: str, item_ids: Sequence[uuid.UUID], actor_user_id: uuid.UUID,
) -> JavMarketSupplierDispatch:
    """Manda la lettera (com'è stata corretta nell'anteprima) e segna le
    righe che contiene.

    Contro il doppio invio: le righe si bloccano (`FOR UPDATE`) e devono
    essere ancora tutte da mandare e tutte di questo fornitore. Un secondo
    clic aspetta il primo, poi le trova già segnate e si ferma con un 409
    prima di spedire. L'email parte con `send_html_email` e non nella
    versione «best effort»: qui l'email **è** il lavoro, e se non parte
    l'amministratore deve saperlo e nessuna riga deve risultare mandata."""
    producer = await _producer(db, organization_id=organization_id, producer_id=producer_id)
    to_email, subject, body_text = to_email.strip(), subject.strip(), body_text.strip()
    if not EMAIL_RE.match(to_email):
        raise JavMarketValidationError("Scrivi un indirizzo email valido per il fornitore.")
    if not subject:
        raise JavMarketValidationError("Scrivi l'oggetto dell'email.")
    if not body_text:
        raise JavMarketValidationError("Il testo dell'email è vuoto.")
    wanted = list(dict.fromkeys(item_ids))
    if not wanted:
        raise JavMarketValidationError("Nessun ordine da mandare.")
    # Prima del blocco: get_settings_row può fare commit (prima lettura), e un
    # commit qui scioglierebbe i FOR UPDATE.
    settings = await get_settings_row(db, organization_id=organization_id)

    rows = (
        await db.execute(
            select(JavMarketOrderItem, JavMarketOrder)
            .join(JavMarketOrder, JavMarketOrder.id == JavMarketOrderItem.order_id)
            .where(JavMarketOrderItem.id.in_(wanted), JavMarketOrder.organization_id == organization_id)
            .with_for_update(of=JavMarketOrderItem)
        )
    ).all()
    effective = await _effective_producer_ids(
        db, organization_id=organization_id, items=[item for item, _order in rows]
    )
    still_pending = len(rows) == len(wanted) and all(
        order.status == "PAID" and order.shipped_at is None and order.delivered_at is None
        and item.supplier_dispatch_id is None and effective[item.id] == producer.id
        for item, order in rows
    )
    if not still_pending:
        await db.rollback()
        raise JavMarketConflictError(STALE_QUEUE_MESSAGE)

    try:
        send_html_email(
            to=to_email, subject=subject, html_body=render_letter(subject=subject, body_text=body_text),
            text_body=body_text, **_sender(settings),
        )
    except EmailNotConfiguredError as exc:
        await db.rollback()
        raise JavMarketValidationError(
            "L'email non è partita: l'invio delle email non è ancora configurato sul server. "
            "Nessun ordine è stato segnato come mandato. Chiedi a chi gestisce la piattaforma di "
            "configurare la posta in uscita, oppure copia il testo e mandalo tu dalla tua casella."
        ) from exc
    except Exception as exc:
        logger.exception("Email al fornitore %s non partita", producer.id)
        await db.rollback()
        raise JavMarketValidationError(
            "L'email non è partita: il server di posta non l'ha accettata. Nessun ordine è stato "
            "segnato come mandato, quindi puoi riprovare tra qualche minuto senza rischiare doppioni. "
            "Se si ripete, controlla l'indirizzo del fornitore e quello del mittente nelle impostazioni."
        ) from exc

    items = [item for item, _order in rows]
    dispatch = await _record_dispatch(
        db, organization_id=organization_id, producer_id=producer.id, source="QUEUE",
        to_email=to_email, subject=subject, body_text=body_text, items=items, actor_user_id=actor_user_id,
    )
    orders = list({order.id: order for _item, order in rows}.values())
    await _mark_orders_sent(db, organization_id=organization_id, orders=orders, actor_user_id=actor_user_id)
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="jav_market.supplier_dispatch_sent", entity_type="jav_market_supplier_dispatch",
        entity_id=str(dispatch.id),
        new_value={
            "fornitore": producer.name, "a": to_email, "oggetto": subject,
            "ordini": [order_code(o) for o in orders], "righe": len(items),
        },
    )
    await db.commit()
    await db.refresh(dispatch)
    return dispatch


async def list_supplier_dispatches(
    db: AsyncSession, *, organization_id: uuid.UUID, limit: int = 50
) -> list[dict]:
    """Lo storico delle email ai fornitori, le più recenti prima, con il
    testo esatto che è partito."""
    rows = (
        await db.execute(
            select(JavMarketSupplierDispatch, JavMarketProducer.name, User.email)
            .join(JavMarketProducer, JavMarketProducer.id == JavMarketSupplierDispatch.producer_id)
            .outerjoin(User, User.id == JavMarketSupplierDispatch.sent_by_user_id)
            .where(JavMarketSupplierDispatch.organization_id == organization_id)
            .order_by(JavMarketSupplierDispatch.sent_at.desc())
            .limit(limit)
        )
    ).all()
    ids = [d.id for d, _name, _email in rows]
    counts: dict[uuid.UUID, tuple[int, int]] = {}
    codes: dict[uuid.UUID, list[str]] = {}
    if ids:
        for dispatch_id, item_count, piece_count in (
            await db.execute(
                select(
                    JavMarketOrderItem.supplier_dispatch_id, func.count(), func.sum(JavMarketOrderItem.quantity)
                )
                .where(JavMarketOrderItem.supplier_dispatch_id.in_(ids))
                .group_by(JavMarketOrderItem.supplier_dispatch_id)
            )
        ).all():
            counts[dispatch_id] = (item_count, int(piece_count or 0))
        for dispatch_id, number in (
            await db.execute(
                select(JavMarketOrderItem.supplier_dispatch_id, JavMarketOrder.number)
                .join(JavMarketOrder, JavMarketOrder.id == JavMarketOrderItem.order_id)
                .where(JavMarketOrderItem.supplier_dispatch_id.in_(ids))
                .distinct()
                .order_by(JavMarketOrder.number)
            )
        ).all():
            codes.setdefault(dispatch_id, []).append(str(number))
    return [
        {
            "id": d.id,
            "producer_id": d.producer_id,
            "producer_name": name,
            "source": d.source,
            "to_email": d.to_email,
            "subject": d.subject,
            "body_text": d.body_text,
            "sent_at": d.sent_at,
            "sent_by_email": sent_by,
            "order_codes": codes.get(d.id, []),
            "order_count": len(codes.get(d.id, [])),
            "item_count": counts.get(d.id, (0, 0))[0],
            "piece_count": counts.get(d.id, (0, 0))[1],
        }
        for d, name, sent_by in rows
    ]


async def forward_order(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID, actor_user_id: uuid.UUID | None
) -> JavMarketOrder:
    """Manda un solo ordine ai suoi fornitori, senza anteprima: il pulsante
    sull'ordine e l'invio automatico al pagamento.

    Una email per fornitore, con dentro solo le sue righe e l'indirizzo di
    consegna -- la stessa lettera della coda (`supplier_letter`). Manda solo
    le righe **non ancora mandate**: un ordine già partito dalla coda non
    riparte da qui, e uno partito da qui sparisce dalla coda. Se un'email
    si perde, la copia è nella casella del mittente (vedi `_sender`).

    Si inoltra solo un ordine **pagato**: mandare a un'azienda una merce da
    preparare prima di aver incassato è il modo più rapido di regalarla.
    """
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None:
        raise JavMarketNotFoundError("Ordine non trovato.")
    if order.status != "PAID":
        raise JavMarketValidationError("Si invia all'azienda solo un ordine già pagato dal cliente.")

    settings = await get_settings_row(db, organization_id=organization_id)
    items = await order_items(db, order)
    effective = await _effective_producer_ids(db, organization_id=organization_id, items=items)
    gruppi: dict[uuid.UUID | None, list[JavMarketOrderItem]] = {}
    for item in items:
        if item.supplier_dispatch_id is None:
            gruppi.setdefault(effective[item.id], []).append(item)
    senza_azienda = gruppi.pop(None, None)
    if not gruppi:
        if senza_azienda:
            raise JavMarketValidationError(
                "Nessun prodotto di questo ordine ha un fornitore: assegnalo al prodotto o alla sua "
                "categoria dal catalogo e riprova."
            )
        raise JavMarketValidationError(
            "Questo ordine è già stato mandato a tutti i suoi fornitori: lo trovi nello storico degli invii."
        )

    mandate, problemi, aziende = 0, [], []
    for producer_id, righe in gruppi.items():
        assert producer_id is not None
        producer = await _producer(db, organization_id=organization_id, producer_id=producer_id)
        aziende.append(producer.name)
        if not producer.email:
            problemi.append(f"«{producer.name}» non ha un'email in scheda")
            continue
        subject, body = supplier_letter(
            producer_name=producer.name, orders=[(order, righe)], signature=settings.supplier_email_signature
        )
        inviata = send_html_email_best_effort(
            context=f"Jav Market supplier order (order={order.id}, producer={producer.id})",
            to=producer.email, subject=subject,
            html_body=render_letter(subject=subject, body_text=body), text_body=body,
            **_sender(settings),
        )
        if inviata:
            mandate += 1
            await _record_dispatch(
                db, organization_id=organization_id, producer_id=producer.id,
                source="ORDER" if actor_user_id else "AUTO", to_email=producer.email, subject=subject,
                body_text=body, items=righe, actor_user_id=actor_user_id,
            )
        else:
            problemi.append(f"l'email a «{producer.name}» non è partita")

    if senza_azienda:
        problemi.append("senza fornitore: " + ", ".join(i.product_name for i in senza_azienda))

    order.forward_error = "; ".join(problemi)[:500] or None
    if mandate:
        # Come prima che esistesse la coda: basta un fornitore avvisato
        # perché l'ordine sia «in preparazione»; quello che manca resta
        # scritto in forward_error e nella coda.
        if order.fulfillment_status == "NOT_SENT":
            order.fulfillment_status = "SENT"
        order.forwarded_at = order.forwarded_at or utcnow()
        order.forwarded_by_user_id = actor_user_id
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="jav_market.order_forwarded", entity_type="jav_market_order", entity_id=str(order.id),
        new_value={"aziende": aziende, "email_inviate": mandate, "problemi": problemi},
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
    pulsante «Invia alle aziende» o la coda «Fornitori da avvisare».

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
