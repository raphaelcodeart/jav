"""Marketplace 6 -- «Marketplace VAITTO»: catalogo, checkout, ordini.

Clone di `kappa_market` (vedi models.py): le regole del cliente sono quelle
comuni dei Marketplace (`marketplaces/rules.py`). In più, qui dentro, il
prezzo che nasce dal costo Vaitto e dal nostro ricarico; il rifornimento
dal feed sta in `feed.py`.

Gli ordini non partono da soli verso Vaitto (scelta dell'utente): restano
nel pannello, con SKU ed EAN congelati sulle righe, e l'amministratore li
inserisce su vaitto.com.
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
from app.domains.marketplaces import paging, rules
from app.domains.notifications import service as notifications_service
from app.domains.organizations import service as organizations_service
from app.domains.users.models import User
from app.domains.vaitto_market.models import (
    MAX_QUANTITY,
    PRODUCT_STATUSES,
    SHIPPING_MODES,
    SHOP,
    VAITTO_MARKET_ORDER_PAYMENT_METHODS,
    VaittoMarketOrder,
    VaittoMarketOrderItem,
    VaittoMarketProducer,
    VaittoMarketProduct,
    VaittoMarketSettings,
    VaittoMarketVariant,
)
from app.domains.wallets import service as wallets_service

logger = logging.getLogger(__name__)

#: Quanti articoli diversi in un ordine. Come sugli altri negozi.
MAX_ORDER_LINES = 20

OrderLine = tuple[uuid.UUID, int]


class VaittoMarketError(Exception):
    """Ogni errore di questo dominio porta un messaggio gia' scritto per il
    cliente, in italiano (CLAUDE.md §6)."""


class VaittoMarketValidationError(VaittoMarketError):
    pass


class VaittoMarketNotFoundError(VaittoMarketError):
    pass


class InvalidOtpError(VaittoMarketError):
    pass


ERRORS = (VaittoMarketValidationError, VaittoMarketNotFoundError, InvalidOtpError)


# --- Impostazioni ---------------------------------------------------------------------------------


async def get_settings_row(db: AsyncSession, *, organization_id: uuid.UUID) -> VaittoMarketSettings:
    """La riga di impostazioni dell'organizzazione, creata al primo accesso:
    un negozio nuovo deve poter essere aperto senza che nessuno prepari
    niente a mano nel database."""
    found = await db.execute(
        select(VaittoMarketSettings).where(VaittoMarketSettings.organization_id == organization_id)
    )
    row = found.scalar_one_or_none()
    if row is None:
        row = VaittoMarketSettings(organization_id=organization_id)
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


SETTINGS_FIELDS = (
    "enabled", "shipping_mode", "shipping_flat_cents", "shipping_days",
    "ship_to_country", "auto_forward", "auto_import", "markup_percentage", "credit_percentage",
    "credit_mode", "credit_margin_share", "prices_include_vat", "shipping_cost_cents",
)


async def update_settings(
    db: AsyncSession, *, row: VaittoMarketSettings, actor_user_id: uuid.UUID, updates: dict
) -> VaittoMarketSettings:
    if "shipping_mode" in updates and updates["shipping_mode"] not in SHIPPING_MODES:
        raise VaittoMarketValidationError("Modalità di spedizione non valida.")
    if updates.get("markup_percentage") is not None and not 0 <= int(updates["markup_percentage"]) <= 500:
        raise VaittoMarketValidationError("Il ricarico va da 0 a 500%.")
    reprice = updates.get("markup_percentage") is not None and updates["markup_percentage"] != row.markup_percentage
    if updates.get("credit_percentage") is not None:
        rules.check_credit_percentage(int(updates["credit_percentage"]))
    if updates.get("credit_mode") is not None and updates["credit_mode"] not in CREDIT_MODES:
        raise VaittoMarketValidationError("Modalità JavCash non valida.")
    if updates.get("credit_margin_share") is not None and not 0 <= int(updates["credit_margin_share"]) <= 100:
        raise VaittoMarketValidationError("La quota del guadagno va da 0 a 100%.")
    # Ogni cosa che cambia la percentuale JavCash dei prodotti: la regola, i
    # suoi numeri, o il ricarico (che cambia il guadagno).
    recredit = any(
        updates.get(k) is not None and updates[k] != getattr(row, k)
        for k in (
            "credit_percentage", "credit_mode", "credit_margin_share", "markup_percentage",
            "prices_include_vat", "shipping_cost_cents",
        )
    )
    for field in SETTINGS_FIELDS:
        if field in updates and updates[field] is not None:
            setattr(row, field, updates[field])
    # L'URL del feed contiene la chiave API: si scrive, non si legge mai, e
    # nell'audit finisce solo il fatto che è cambiato.
    if "feed_url" in updates and updates["feed_url"] is not None:
        url = updates["feed_url"].strip()
        if url and not url.startswith("https://"):
            raise VaittoMarketValidationError("L'indirizzo del feed deve iniziare con https://")
        row.feed_url = url or None
    if reprice:
        for product in await list_products(db, organization_id=row.organization_id):
            if product.markup_percentage is None:
                await reprice_product(db, product=product, settings=row)
    # La percentuale JavCash vale per tutti i prodotti, salvo quelli
    # personalizzati a mano (credit_locked).
    if recredit:
        await db.flush()
        await apply_credit_rule_to_all(db, settings=row)
    await audit_service.record(
        db, organization_id=row.organization_id, actor_user_id=actor_user_id,
        action="vaitto_market.settings_updated", entity_type="vaitto_market_settings", entity_id=str(row.id),
        new_value={
            **{k: v for k, v in updates.items() if k in SETTINGS_FIELDS},
            **({"feed_url": "modificato"} if "feed_url" in updates else {}),
        },
    )
    await db.commit()
    await db.refresh(row)
    return row


def settings_read_dict(row: VaittoMarketSettings) -> dict:
    return {
        "enabled": row.enabled,
        "shipping_mode": row.shipping_mode,
        "shipping_flat_cents": row.shipping_flat_cents,
        "shipping_days": row.shipping_days,
        "ship_to_country": row.ship_to_country,
        "auto_forward": row.auto_forward,
        # Mai l'URL: contiene la chiave. Solo se c'è e le ultime cifre.
        "feed_configured": bool(row.feed_url),
        "feed_hint": ("…" + row.feed_url.rstrip("/").split("/")[-2][-6:]) if row.feed_url and row.feed_url.count("/") > 3 else None,
        "auto_import": row.auto_import,
        "markup_percentage": row.markup_percentage,
        "credit_percentage": row.credit_percentage,
        "credit_mode": row.credit_mode,
        "credit_margin_share": row.credit_margin_share,
        "prices_include_vat": row.prices_include_vat,
        "shipping_cost_cents": row.shipping_cost_cents,
        "last_import_at": row.last_import_at,
        "last_import_summary": row.last_import_summary,
        "last_import_error": row.last_import_error,
    }


# --- Produttori -----------------------------------------------------------------------------------


async def list_producers(db: AsyncSession, *, organization_id: uuid.UUID) -> list[VaittoMarketProducer]:
    rows = await db.execute(
        select(VaittoMarketProducer)
        .where(VaittoMarketProducer.organization_id == organization_id)
        .order_by(VaittoMarketProducer.name)
    )
    return list(rows.scalars().all())


def producer_read_dict(producer: VaittoMarketProducer | None) -> dict | None:
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


def producer_public_dict(producer: VaittoMarketProducer | None) -> dict | None:
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
) -> VaittoMarketProducer:
    name = (payload.get("name") or "").strip()
    if not name:
        raise VaittoMarketValidationError("Il nome del marchio è obbligatorio.")
    existing = await db.execute(
        select(VaittoMarketProducer).where(
            VaittoMarketProducer.organization_id == organization_id, VaittoMarketProducer.name == name
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise VaittoMarketValidationError(f"«{name}» è già in elenco: modifica quella scheda invece di crearne un'altra.")
    producer = VaittoMarketProducer(
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
) -> VaittoMarketProducer:
    producer = await db.get(VaittoMarketProducer, producer_id)
    if producer is None or producer.organization_id != organization_id:
        raise VaittoMarketNotFoundError("Marchio non trovato.")
    for field in ("name", "description", "website_url", "logo_url", "vat_number", "email", "phone", "address", "active"):
        if field in payload and payload[field] is not None:
            setattr(producer, field, payload[field].strip() if isinstance(payload[field], str) else payload[field])
    producer.updated_at = utcnow()
    await db.commit()
    await db.refresh(producer)
    return producer


# --- Catalogo -------------------------------------------------------------------------------------


async def _variants(db: AsyncSession, product_id: uuid.UUID) -> list[VaittoMarketVariant]:
    rows = await db.execute(
        select(VaittoMarketVariant)
        .where(VaittoMarketVariant.product_id == product_id)
        .order_by(VaittoMarketVariant.created_at)
    )
    return list(rows.scalars().all())


def variant_sellable(variant: VaittoMarketVariant) -> bool:
    return (
        variant.active and variant.available_in_store and not variant.below_cost
        and (variant.inventory is None or variant.inventory > 0)
    )


# --- Prezzo: il suggerito da Vaitto + il nostro ricarico (Session 88) ----------------------------

#: Il ricarico con cui Vaitto costruisce il suo prezzo suggerito (colonna
#: «markup_pct» del feed, 40 su tutto il catalogo). Serve solo a ricavare il
#: suggerito di una variante che non l'ha ancora avuto da un import.
VAITTO_SUGGESTED_MARKUP = 40


def sale_price_cents(base_cents: int, markup_percentage: int) -> int:
    """Il prezzo esposto: la base (il prezzo suggerito da Vaitto) più il
    nostro ricarico, al centesimo per eccesso. Con ricarico 0 è esattamente
    il suggerito -- niente arrotondamenti: l'utente vuole vendere al prezzo
    di Vaitto. L'IVA si aggiunge al checkout come in ogni Marketplace."""
    from math import ceil

    return max(ceil(base_cents * (100 + max(0, markup_percentage)) / 100), 1)


def price_base_cents(variant: VaittoMarketVariant) -> int | None:
    """Da dove parte il prezzo: il suggerito da Vaitto; se una variante non
    l'ha ancora (import precedente alla Session 88), il costo più il ricarico
    con cui Vaitto lo calcola. Il costo da solo mai: con ricarico 0
    vorrebbe dire vendere a quanto compriamo."""
    from math import ceil

    if variant.suggested_price_cents:
        return variant.suggested_price_cents
    if variant.cost_cents:
        return ceil(variant.cost_cents * (100 + VAITTO_SUGGESTED_MARKUP) / 100)
    return None


def effective_markup(product: VaittoMarketProduct, settings: VaittoMarketSettings) -> int:
    return product.markup_percentage if product.markup_percentage is not None else settings.markup_percentage


def reprice_variant(variant: VaittoMarketVariant, *, markup: int) -> None:
    """Il prezzo di una variante dal suggerito da Vaitto, salvo che l'abbia
    scritto l'amministratore (`price_locked`) o che non venga da Vaitto
    (prodotto caricato a mano)."""
    base = price_base_cents(variant)
    if not variant.price_locked and base:
        variant.price_cents = sale_price_cents(base, markup)


# --- JavCash: fisso o dal nostro guadagno (Session 88) ----------------------------------------

CREDIT_MODES = ("FIXED", "MARGIN")


def customer_price_cents(variant: VaittoMarketVariant, settings: VaittoMarketSettings, vat_percentage: int) -> int:
    """Session 89: the price the customer sees and pays is always final,
    VAT included. A brand price (RRP) already has it; a price from Vaitto's
    markup is net, and gets it added here -- never «+ IVA» at checkout."""
    if settings.prices_include_vat:
        return variant.price_cents
    return (variant.price_cents * (100 + vat_percentage) + 50) // 100


def our_total_cost_cents(
    variant: VaittoMarketVariant, settings: VaittoMarketSettings, vat_percentage: int
) -> int | None:
    """Quanto ci costa una variante. Session 89, formula dell'utente: il
    prezzo a noi di Vaitto, preso così com'è -- «come già ivato», senza
    spedizione aggiunta."""
    return variant.cost_cents or None


def customer_net_price_cents(
    variant: VaittoMarketVariant, settings: VaittoMarketSettings, vat_percentage: int
) -> int:
    """Il prezzo al cliente senza l'IVA (scorporata, al centesimo)."""
    gross = customer_price_cents(variant, settings, vat_percentage)
    return (gross * 100 * 2 + (100 + vat_percentage)) // ((100 + vat_percentage) * 2)


def variant_gain_cents(
    variant: VaittoMarketVariant, settings: VaittoMarketSettings, vat_percentage: int
) -> int | None:
    """Il nostro guadagno su una variante (Session 89, formula dell'utente):
    prezzo al cliente senza IVA − prezzo a noi."""
    cost = our_total_cost_cents(variant, settings, vat_percentage)
    if cost is None or not variant.price_cents:
        return None
    return customer_net_price_cents(variant, settings, vat_percentage) - cost


def margin_credit_percentage(
    variants: list[VaittoMarketVariant], *, settings: VaittoMarketSettings, vat_percentage: int
) -> int | None:
    """La percentuale JavCash che viene dal guadagno: `credit_margin_share`%
    del guadagno (di norma la metà), in percentuale del prezzo che paga il
    cliente, IVA inclusa. Sulla variante vendibile che rende meno, per
    difetto al punto intero. None se nessuna variante ha costo e prezzo
    (prodotto caricato a mano).

    Moose a 315,69 € IVA inclusa (258,76 senza), costo 129,38: guadagno
    258,76 − 129,38 = 129,38, metà 64,69 = 20,5% di 315,69 → 20%."""
    from math import floor

    share = max(0, min(settings.credit_margin_share, 100))
    values = []
    for v in variants:
        gain = variant_gain_cents(v, settings, vat_percentage)
        gross = customer_price_cents(v, settings, vat_percentage) if v.price_cents else 0
        if gain is None or gross <= 0 or gain <= 0:
            continue
        values.append(floor(gain * share / gross))
    if not values:
        return None if all(variant_gain_cents(v, settings, vat_percentage) is None for v in variants) else 0
    return max(0, min(min(values), rules.MAX_CREDIT_PERCENTAGE))


def mark_below_cost(
    variants: list[VaittoMarketVariant], settings: VaittoMarketSettings, vat_percentage: int
) -> None:
    """Una variante il cui prezzo senza IVA non supera il costo non si vende."""
    for v in variants:
        gain = variant_gain_cents(v, settings, vat_percentage)
        v.below_cost = gain is not None and gain <= 0


def expected_credit_percentage(
    product: VaittoMarketProduct, variants: list[VaittoMarketVariant], settings: VaittoMarketSettings,
    vat_percentage: int,
) -> int:
    """Quanto dovrebbe avere il prodotto se nessuno l'avesse cambiato a mano."""
    if settings.credit_mode == "MARGIN":
        value = margin_credit_percentage(variants, settings=settings, vat_percentage=vat_percentage)
        if value is not None:
            return value
    return settings.credit_percentage


def apply_credit_rule(
    product: VaittoMarketProduct, variants: list[VaittoMarketVariant], settings: VaittoMarketSettings,
    vat_percentage: int,
) -> None:
    """Segna le varianti in perdita e applica la regola JavCash del negozio,
    salvo ai prodotti personalizzati a mano."""
    mark_below_cost(variants, settings, vat_percentage)
    if not product.credit_locked:
        product.credit_discount_percentage = expected_credit_percentage(product, variants, settings, vat_percentage)


async def apply_credit_rule_to_all(db: AsyncSession, *, settings: VaittoMarketSettings) -> None:
    vat = await rules.get_vat_percentage(db, organization_id=settings.organization_id)
    products = await list_products(db, organization_id=settings.organization_id)
    by_product, _ = await _preload(db, products)
    for product in products:
        apply_credit_rule(product, by_product[product.id], settings, vat)


async def reprice_product(
    db: AsyncSession, *, product: VaittoMarketProduct, settings: VaittoMarketSettings
) -> None:
    markup = effective_markup(product, settings)
    for variant in await _variants(db, product.id):
        reprice_variant(variant, markup=markup)


async def create_product(
    db: AsyncSession, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID, payload: dict
) -> VaittoMarketProduct:
    """Un prodotto nuovo, con le sue varianti. Almeno una: un prodotto senza
    varianti non sarebbe comprabile, e crearlo per poi scoprirlo al primo
    cliente sarebbe il modo peggiore di accorgersene."""
    name = (payload.get("name") or "").strip()
    if not name:
        raise VaittoMarketValidationError("Il nome del prodotto è obbligatorio.")
    varianti = payload.get("variants") or []
    if not varianti:
        raise VaittoMarketValidationError("Serve almeno una variante con il suo prezzo.")
    rules.check_credit_percentage(int(payload.get("credit_discount_percentage") or 0))
    if payload.get("producer_id"):
        producer = await db.get(VaittoMarketProducer, payload["producer_id"])
        if producer is None or producer.organization_id != organization_id:
            raise VaittoMarketNotFoundError("Marchio non trovato.")

    product = VaittoMarketProduct(
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
        raise VaittoMarketValidationError("Ogni variante deve avere un prezzo maggiore di zero.")
    db.add(VaittoMarketVariant(
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
) -> VaittoMarketProduct:
    product = await db.get(VaittoMarketProduct, product_id)
    if product is None or product.organization_id != organization_id:
        raise VaittoMarketNotFoundError("Prodotto non trovato.")
    if "credit_discount_percentage" in payload and payload["credit_discount_percentage"] is not None:
        rules.check_credit_percentage(int(payload["credit_discount_percentage"]))
    if "status" in payload and payload["status"] not in (None, *PRODUCT_STATUSES):
        raise VaittoMarketValidationError("Stato del prodotto non valido.")
    for field in ("name", "description", "image_url", "images", "status",
                  "credit_discount_percentage", "unit_cost_cents", "producer_id"):
        if field in payload and payload[field] is not None:
            setattr(product, field, payload[field])
    # La foto si puo' anche togliere: un null esplicito qui vuol dire "senza foto".
    if "image_url" in payload and payload["image_url"] is None:
        product.image_url = None
    # Il ricarico del prodotto: un numero lo fissa, null torna a quello del
    # negozio. In entrambi i casi i prezzi non scritti a mano si rifanno.
    if "markup_percentage" in payload:
        value = payload["markup_percentage"]
        if value is not None and not 0 <= int(value) <= 500:
            raise VaittoMarketValidationError("Il ricarico va da 0 a 500%.")
        product.markup_percentage = value
        await reprice_product(
            db, product=product, settings=await get_settings_row(db, organization_id=organization_id)
        )
    # La percentuale JavCash: diversa da quella che darebbe la regola del
    # negozio (fissa o dal guadagno) = personalizzata, e i ricalcoli non la
    # toccano più; «credit_locked: false» la riconsegna alla regola. Dopo il
    # ricarico, perché il ricarico cambia il guadagno.
    settings = await get_settings_row(db, organization_id=organization_id)
    vat = await rules.get_vat_percentage(db, organization_id=organization_id)
    variants = await _variants(db, product.id)
    if payload.get("credit_locked") is False:
        product.credit_locked = False
        apply_credit_rule(product, variants, settings, vat)
    elif payload.get("credit_discount_percentage") is not None:
        product.credit_locked = int(payload["credit_discount_percentage"]) != expected_credit_percentage(
            product, variants, settings, vat
        )
    elif "markup_percentage" in payload:
        apply_credit_rule(product, variants, settings, vat)
    product.updated_at = utcnow()
    await db.commit()
    await db.refresh(product)
    return product


async def update_variant(
    db: AsyncSession, *, organization_id: uuid.UUID, variant_id: uuid.UUID, payload: dict
) -> VaittoMarketVariant:
    variant = await db.get(VaittoMarketVariant, variant_id)
    product = await db.get(VaittoMarketProduct, variant.product_id) if variant else None
    if variant is None or product is None or product.organization_id != organization_id:
        raise VaittoMarketNotFoundError("Variante non trovata.")
    if "price_cents" in payload and payload["price_cents"] is not None and int(payload["price_cents"]) <= 0:
        raise VaittoMarketValidationError("Il prezzo deve essere maggiore di zero.")
    new_price = payload.get("price_cents")
    for field in ("label", "sku", "image_url", "price_cents", "inventory", "active"):
        if field in payload and payload[field] is not None:
            setattr(variant, field, payload[field])
    # Un prezzo scritto a mano e diverso da quello calcolato si blocca: l'import
    # non lo rifà. «price_locked: false» lo riconsegna al ricarico.
    if new_price is not None and price_base_cents(variant):
        settings = await get_settings_row(db, organization_id=organization_id)
        variant.price_locked = int(new_price) != sale_price_cents(
            price_base_cents(variant), effective_markup(product, settings)
        )
    if payload.get("price_locked") is False:
        variant.price_locked = False
        settings = await get_settings_row(db, organization_id=organization_id)
        reprice_variant(variant, markup=effective_markup(product, settings))
    # Un prezzo nuovo cambia il guadagno, e con la regola «dal guadagno» la
    # percentuale JavCash del prodotto.
    if new_price is not None or payload.get("price_locked") is False:
        await db.flush()
        apply_credit_rule(
            product, await _variants(db, product.id), await get_settings_row(db, organization_id=organization_id),
            await rules.get_vat_percentage(db, organization_id=organization_id),
        )
    await db.commit()
    await db.refresh(variant)
    return variant


async def add_variant(
    db: AsyncSession, *, organization_id: uuid.UUID, product_id: uuid.UUID, payload: dict
) -> VaittoMarketProduct:
    product = await db.get(VaittoMarketProduct, product_id)
    if product is None or product.organization_id != organization_id:
        raise VaittoMarketNotFoundError("Prodotto non trovato.")
    _add_variant(db, product_id=product.id, payload=payload)
    await db.commit()
    await db.refresh(product)
    return product


async def list_products(db: AsyncSession, *, organization_id: uuid.UUID) -> list[VaittoMarketProduct]:
    rows = await db.execute(
        select(VaittoMarketProduct)
        .where(VaittoMarketProduct.organization_id == organization_id)
        .order_by(VaittoMarketProduct.created_at.desc())
    )
    return list(rows.scalars().all())


async def product_read_dict(
    db: AsyncSession, product: VaittoMarketProduct, *, admin: bool,
    variants: list[VaittoMarketVariant] | None = None, producer: VaittoMarketProducer | None = None,
) -> dict:
    """`variants`/`producer` già caricati da chi elenca migliaia di prodotti
    (vedi admin_product_dicts): senza, due query per prodotto."""
    if variants is None:
        variants = await _variants(db, product.id)
    if producer is None and product.producer_id:
        producer = await db.get(VaittoMarketProducer, product.producer_id)
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
                "compare_at_cents": v.compare_at_cents,
                **({
                    "cost_cents": v.cost_cents, "suggested_price_cents": v.suggested_price_cents,
                    "barcode": v.barcode,
                    "available_in_store": v.available_in_store, "price_locked": v.price_locked,
                    "below_cost": v.below_cost,
                } if admin else {}),
            }
            for v in variants
        ],
    }
    if admin:
        out["unit_cost_cents"] = product.unit_cost_cents
        out["producer_id"] = product.producer_id
        out["vaitto_product_id"] = product.vaitto_product_id
        out["category_name"] = product.category_name
        out["subcategory"] = product.subcategory
        out["gender"] = product.gender
        out["source_url"] = product.source_url
        out["markup_percentage"] = product.markup_percentage
        out["missing_from_feed"] = product.missing_from_feed
        out["credit_locked"] = product.credit_locked
        out["last_synced_at"] = product.last_synced_at
    return out


async def _preload(
    db: AsyncSession, products: list[VaittoMarketProduct]
) -> tuple[dict[uuid.UUID, list[VaittoMarketVariant]], dict[uuid.UUID, VaittoMarketProducer]]:
    """Varianti e marche di molti prodotti in due query invece di due per
    prodotto: il catalogo Vaitto ne ha migliaia."""
    ids = [p.id for p in products]
    by_product: dict[uuid.UUID, list[VaittoMarketVariant]] = {i: [] for i in ids}
    if ids:
        for i in range(0, len(ids), 1000):
            rows = await db.execute(
                select(VaittoMarketVariant)
                .where(VaittoMarketVariant.product_id.in_(ids[i:i + 1000]))
                .order_by(VaittoMarketVariant.created_at)
            )
            for v in rows.scalars().all():
                by_product[v.product_id].append(v)
    producer_ids = {p.producer_id for p in products if p.producer_id}
    producers: dict[uuid.UUID, VaittoMarketProducer] = {}
    if producer_ids:
        rows = await db.execute(select(VaittoMarketProducer).where(VaittoMarketProducer.id.in_(producer_ids)))
        producers = {p.id: p for p in rows.scalars().all()}
    return by_product, producers


async def admin_product_dicts(db: AsyncSession, *, organization_id: uuid.UUID) -> list[dict]:
    products = await list_products(db, organization_id=organization_id)
    by_product, producers = await _preload(db, products)
    return [
        await product_read_dict(
            db, p, admin=True, variants=by_product[p.id],
            producer=producers.get(p.producer_id) if p.producer_id else None,
        )
        for p in products
    ]


async def shop_card(
    db: AsyncSession, *, product: VaittoMarketProduct, settings: VaittoMarketSettings,
    bank_transfer_discount_percentage: int, category_ids: list[uuid.UUID] | None = None,
    variants: list[VaittoMarketVariant] | None = None, producer: VaittoMarketProducer | None = None,
    vat_percentage: int | None = None,
) -> dict | None:
    """La scheda nella griglia del cliente: stessa forma degli altri negozi,
    cosi' lo Shop la disegna senza sapere da quale negozio venga. Le varianti
    che Vaitto non vende più non si mostrano nemmeno."""
    from app.domains.shop_categories import service as shop_categories_service

    if variants is None:
        variants = await _variants(db, product.id)
    variants = [v for v in variants if v.active and v.available_in_store and not v.below_cost]
    if not variants:
        return None
    if producer is None and product.producer_id:
        producer = await db.get(VaittoMarketProducer, product.producer_id)
    if vat_percentage is None:
        vat_percentage = await rules.get_vat_percentage(db, organization_id=product.organization_id)
    gross = {v.id: customer_price_cents(v, settings, vat_percentage) for v in variants}
    compare_at = [v.compare_at_cents for v in variants if v.compare_at_cents]
    prices = list(gross.values())
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
        #: Session 89: prezzi sempre finali, IVA inclusa.
        "vat_included": True,
        "bank_transfer_discount_percentage": bank_transfer_discount_percentage,
        "in_stock": any(variant_sellable(v) for v in variants),
        "producer": producer_public_dict(producer),
        #: Il prezzo di listino Vaitto, da mostrare barrato: solo se è davvero
        #: più alto del nostro.
        "compare_at_cents": max(compare_at) if compare_at and max(compare_at) > max(prices) else None,
        "variants": [
            {
                "id": v.id, "label": v.label, "image_url": v.image_url,
                "price_cents": gross[v.id], "in_stock": variant_sellable(v),
                "compare_at_cents": v.compare_at_cents if (v.compare_at_cents or 0) > gross[v.id] else None,
            }
            for v in variants
        ],
    }


async def customer_products(db: AsyncSession, *, organization_id: uuid.UUID) -> list[dict]:
    """Tutta la vetrina in una volta. Solo per i test e per chi conta: il
    cliente usa customer_products_page (2.000 prodotti sono 3,4 MB)."""
    row = await get_settings_row(db, organization_id=organization_id)
    if not row.enabled:
        return []
    active = [p for p in await list_products(db, organization_id=organization_id) if p.status == "ACTIVE"]
    cards = await _customer_cards(db, organization_id=organization_id, settings=row, products=active)
    return [card for card in cards if card is not None]


async def customer_products_page(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    offset: int = 0,
    limit: int = paging.PAGE_SIZE,
    search: str | None = None,
    category_id: uuid.UUID | None = None,
) -> dict:
    """La vetrina a pagine («Mostra altri prodotti»): vedi marketplaces/paging.py."""
    row = await get_settings_row(db, organization_id=organization_id)
    if not row.enabled:
        return paging.empty_page(offset, limit)

    async def cards(products: list[VaittoMarketProduct]) -> list[dict | None]:
        return await _customer_cards(db, organization_id=organization_id, settings=row, products=products)

    return await paging.customer_page(
        db, model=VaittoMarketProduct, shop=SHOP, organization_id=organization_id, build_cards=cards,
        offset=offset, limit=limit, search=search, category_id=category_id,
    )


async def _customer_cards(
    db: AsyncSession, *, organization_id: uuid.UUID, settings: VaittoMarketSettings,
    products: list[VaittoMarketProduct],
) -> list[dict | None]:
    """Le schede di `products`, nello stesso ordine; None per un prodotto
    che il cliente non deve vedere. Tre query per tutta la lista."""
    from app.domains.shop_categories import service as shop_categories_service

    discount = await rules.get_bank_transfer_discount_percentage(db, organization_id=organization_id)
    vat_percentage = await rules.get_vat_percentage(db, organization_id=organization_id)
    by_product, producers = await _preload(db, products)
    categories = await shop_categories_service.category_ids_by_product(
        db, organization_id=organization_id, shop=SHOP, product_ids=[p.id for p in products],
    )
    return [
        await shop_card(
            db, product=product, settings=settings, bank_transfer_discount_percentage=discount,
            category_ids=categories.get(product.id, []), variants=by_product[product.id],
            producer=producers.get(product.producer_id) if product.producer_id else None,
            vat_percentage=vat_percentage,
        )
        for product in products
    ]


# --- Checkout -------------------------------------------------------------------------------------


def _lines_from(variant_id: uuid.UUID | None, quantity: int, lines: list[OrderLine] | None) -> list[OrderLine]:
    if lines is not None:
        if not lines:
            raise VaittoMarketValidationError("Il carrello è vuoto.")
        if len(lines) > MAX_ORDER_LINES:
            raise VaittoMarketValidationError(f"Al massimo {MAX_ORDER_LINES} articoli diversi per ordine.")
        return lines
    if variant_id is None:
        raise VaittoMarketValidationError("Nessun prodotto da ordinare.")
    return [(variant_id, quantity)]


async def _sellable(
    db: AsyncSession, *, organization_id: uuid.UUID, variant_id: uuid.UUID
) -> tuple[VaittoMarketProduct, VaittoMarketVariant]:
    variant = await db.get(VaittoMarketVariant, variant_id)
    product = await db.get(VaittoMarketProduct, variant.product_id) if variant else None
    if variant is None or product is None or product.organization_id != organization_id or product.status != "ACTIVE":
        raise VaittoMarketValidationError("Prodotto non disponibile.")
    if not variant_sellable(variant):
        raise VaittoMarketValidationError("Questa variante al momento non è disponibile.")
    return product, variant


def creditable_cents_per_line(items: list[dict]) -> list[int]:
    """La percentuale di ogni prodotto sul suo valore; la spedizione non
    entra. Stessa regola degli altri negozi, perché al cliente il JavCash
    deve comportarsi uguale ovunque."""
    return [round(i["line_total_cents"] * i["credit_discount_percentage"] / 100) for i in items]


async def order_items(db: AsyncSession, order: VaittoMarketOrder) -> list[VaittoMarketOrderItem]:
    rows = await db.execute(
        select(VaittoMarketOrderItem)
        .where(VaittoMarketOrderItem.order_id == order.id)
        .order_by(VaittoMarketOrderItem.created_at, VaittoMarketOrderItem.id)
    )
    return list(rows.scalars().all())


def items_summary(items: list) -> str:
    def campo(item, nome):
        return item[nome] if isinstance(item, dict) else getattr(item, nome)

    first = campo(items[0], "product_name")
    altri = len(items) - 1
    return first if altri <= 0 else f"{first} + altri {altri}"


def order_code(order: VaittoMarketOrder) -> str:
    return str(order.number) if getattr(order, "number", None) else str(order.id)[:8].upper()


def order_number(order: VaittoMarketOrder) -> str:
    return f"JAV-{order_code(order)}"


def bank_transfer_total_cents(*, residual_cents: int, percentage: int) -> int:
    return residual_cents - rules.bank_transfer_discount_cents(
        residual_cents=residual_cents, percentage=percentage
    )


def amount_due_cents(order: VaittoMarketOrder) -> int:
    """Quanto paga il cliente in euro: il residuo dopo i JavCash, meno lo
    sconto bonifico quando paga con bonifico."""
    return order.amount_cents - order.credit_applied_cents - (order.bank_transfer_discount_cents or 0)


def taxable_base_cents(order: VaittoMarketOrder) -> int:
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
    browser: la spedizione una volta per ordine, l'IVA sempre dentro il prezzo,
    il tetto JavCash somma delle righe."""
    row = await get_settings_row(db, organization_id=organization_id)
    if not row.enabled:
        raise VaittoMarketValidationError("Questo shop non è disponibile al momento.")

    vat_percentage = await rules.get_vat_percentage(db, organization_id=organization_id)
    items: list[dict] = []
    seen: set[uuid.UUID] = set()
    for line_variant_id, line_quantity in _lines_from(variant_id, quantity, lines):
        if line_quantity < 1 or line_quantity > MAX_QUANTITY:
            raise VaittoMarketValidationError(f"Quantità da 1 a {MAX_QUANTITY}.")
        if line_variant_id in seen:
            raise VaittoMarketValidationError("Lo stesso articolo compare due volte nell'ordine.")
        seen.add(line_variant_id)
        product, variant = await _sellable(db, organization_id=organization_id, variant_id=line_variant_id)
        if variant.inventory is not None and variant.inventory < line_quantity:
            raise VaittoMarketValidationError(f"«{product.name}»: disponibili solo {variant.inventory} pezzi.")
        producer = await db.get(VaittoMarketProducer, product.producer_id) if product.producer_id else None
        items.append({
            "variant_id": variant.id,
            "product_id": product.id,
            "product_name": product.name,
            "variant_label": variant.label,
            "producer_name": producer.name if producer else None,
            "image_url": variant.image_url or product.image_url,
            "quantity": line_quantity,
            "unit_price_cents": customer_price_cents(variant, row, vat_percentage),
            "unit_cost_cents": product.unit_cost_cents,
            "line_total_cents": customer_price_cents(variant, row, vat_percentage) * line_quantity,
            "credit_discount_percentage": product.credit_discount_percentage,
            "supplier_sku": variant.sku,
            "barcode": variant.barcode,
            "supplier_url": product.source_url,
        })

    items_cents = sum(i["line_total_cents"] for i in items)
    shipping_cents = 0 if row.shipping_mode == "INCLUDED" else (row.shipping_flat_cents or 0)
    # Session 89: i prezzi delle righe sono già finali, IVA inclusa
    # (customer_price_cents): l'IVA si scorpora, non si aggiunge mai.
    vat_cents = rules.vat_included_cents(gross_cents=items_cents, percentage=vat_percentage)
    amount = items_cents + shipping_cents
    vat_mode = "INCLUDED"

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
        "vat_mode": vat_mode,
        "shipping_cents": shipping_cents,
        "shipping_included": row.shipping_mode == "INCLUDED",
        "shipping_days": row.shipping_days,
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


async def freeze_bank_transfer_discount(db: AsyncSession, *, order: VaittoMarketOrder) -> None:
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
) -> VaittoMarketOrder:
    """Crea l'ordine con ogni importo ricalcolato qui, mai preso dal
    browser. Nasce multi-riga: il denaro sta sulla testata, la merce sulle
    righe."""
    order_lines = _lines_from(variant_id, quantity, lines)
    quote = await get_quote(
        db, organization_id=organization_id, customer_user_id=customer_user_id, lines=order_lines
    )
    row = await get_settings_row(db, organization_id=organization_id)
    amount = quote["amount_cents"]
    if credit_applied_cents < 0 or credit_applied_cents > quote["max_creditable_cents"]:
        raise VaittoMarketValidationError(
            f"Puoi usare al massimo {quote['max_creditable_cents'] / 100:.2f} JavCash per questo ordine."
        )
    if credit_applied_cents > 0:
        from app.domains.auth import service as auth_service

        if not otp_code or not await auth_service.verify_spend_code(
            db, user_id=customer_user_id, code=otp_code
        ):
            raise InvalidOtpError("Codice o PIN di conferma mancante, non valido o scaduto.")
    if payment_method not in VAITTO_MARKET_ORDER_PAYMENT_METHODS:
        raise VaittoMarketValidationError("Metodo di pagamento non valido.")
    methods = await payment_methods(db, organization_id=organization_id)
    if payment_method == "BANK_TRANSFER" and not methods["bank_transfer"]:
        raise VaittoMarketValidationError("Il pagamento con bonifico non è configurato.")
    if payment_method == "CARD" and not methods["card"]:
        raise VaittoMarketValidationError("Il pagamento con carta non è configurato.")

    wallet = None
    if credit_applied_cents > 0:
        wallet = await wallets_service.get_or_create_wallet(
            db, organization_id=organization_id, user_id=customer_user_id
        )
        if wallet.balance_cents < credit_applied_cents:
            raise wallets_service.InsufficientBalanceError("Saldo JavCash insufficiente.")

    order = VaittoMarketOrder(
        organization_id=organization_id,
        customer_user_id=customer_user_id,
        created_by_user_id=actor_user_id,
        items_cents=quote["items_cents"],
        shipping_cents=quote["shipping_cents"],
        amount_cents=amount,
        vat_percentage=quote["vat_percentage"],
        vat_amount_cents=quote["vat_cents"],
        vat_mode=quote.get("vat_mode", "ADDED"),
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
        db.add(VaittoMarketOrderItem(
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
            supplier_sku=item.get("supplier_sku"),
            barcode=item.get("barcode"),
            supplier_url=item.get("supplier_url"),
        ))
    await freeze_bank_transfer_discount(db, order=order)
    riepilogo = items_summary(quote["items"])
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="VAITTO_MARKET_ORDER_CREATED", entity_type="vaitto_market_order", entity_id=order.id,
        title=f"Nuovo ordine Marketplace VAITTO: {riepilogo}",
        body=f"{amount / 100:.2f} EUR -- "
             + " · ".join(f"{i['quantity']} × {i['product_name']}" for i in quote["items"]),
        exclude_user_id=actor_user_id,
    )
    if credit_applied_cents > 0:
        assert wallet is not None
        debit = await wallets_service.debit_wallet_for_vaitto_market_purchase(
            db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=credit_applied_cents,
            reference_vaitto_market_order_id=order.id, actor_user_id=actor_user_id,
            note=f"Acquisto {riepilogo}", idempotency_key=f"vaitto-market-order:{order.id}:credit",
        )
        order.credit_debit_transaction_id = debit.id
    await db.commit()
    await db.refresh(order)
    await _send_order_email(db, order=order)
    return order


# --- Ordini ---------------------------------------------------------------------------------------


async def list_orders(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID | None = None
) -> list[VaittoMarketOrder]:
    query = select(VaittoMarketOrder).where(VaittoMarketOrder.organization_id == organization_id)
    if customer_user_id is not None:
        query = query.where(VaittoMarketOrder.customer_user_id == customer_user_id)
    rows = await db.execute(query.order_by(VaittoMarketOrder.created_at.desc()))
    return list(rows.scalars().all())


async def get_org_scoped(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID
) -> VaittoMarketOrder | None:
    order = await db.get(VaittoMarketOrder, order_id)
    return order if order is not None and order.organization_id == organization_id else None


async def get_owned(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID, order_id: uuid.UUID
) -> VaittoMarketOrder | None:
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    return order if order is not None and order.customer_user_id == customer_user_id else None


def delivery_status(order: VaittoMarketOrder) -> str | None:
    """L'unico stato di spedizione che il cliente vede, con gli stessi
    valori degli altri negozi."""
    if order.status != "PAID":
        return None
    if order.delivered_at:
        return "DELIVERED"
    if order.shipped_at:
        return "SHIPPED"
    return "PREPARING" if order.fulfillment_status != "NOT_SENT" else "RECEIVED"


async def order_read_dict(db: AsyncSession, order: VaittoMarketOrder, *, admin: bool) -> dict:
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
                # Session 88: per inserire l'ordine su vaitto.com. Solo allo
                # staff: al cliente non serve sapere da dove arriva la merce.
                **({"supplier_sku": i.supplier_sku, "barcode": i.barcode, "supplier_url": i.supplier_url}
                   if admin else {}),
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
    db: AsyncSession, *, order: VaittoMarketOrder, by_card: bool, actor_user_id: uuid.UUID | None
) -> None:
    order.status = "PAID"
    order.paid_by_user_id = actor_user_id
    order.paid_at = utcnow()
    items = await order_items(db, order)
    name = items_summary(items) if items else "il tuo ordine"
    await notifications_service.notify_user(
        db, organization_id=order.organization_id, user_id=order.customer_user_id, type_="ORDER_PAID",
        entity_type="vaitto_market_order", entity_id=order.id,
        title=f"Il tuo ordine per {name} è confermato", body="Ti avvisiamo appena viene spedito.",
    )
    await notifications_service.notify_roles(
        db, organization_id=order.organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="VAITTO_MARKET_ORDER_PAID", entity_type="vaitto_market_order", entity_id=order.id,
        title=f"{'Pagamento Stripe' if by_card else 'Bonifico'} confermato: {name}",
        body=f"{amount_due_cents(order) / 100:.2f} EUR -- da preparare e spedire",
    )
    await _send_payment_receipt_email(db, order=order, items=items, by_card=by_card)


async def confirm_payment(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID, actor_user_id: uuid.UUID
) -> VaittoMarketOrder:
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None:
        raise VaittoMarketNotFoundError("Ordine non trovato.")
    if order.status != "AWAITING_PAYMENT":
        raise VaittoMarketValidationError("Questo ordine non è in attesa di pagamento.")
    if order.payment_method == "CARD":
        raise VaittoMarketValidationError("Un ordine pagato con carta viene confermato automaticamente da Stripe.")
    await _mark_paid(db, order=order, by_card=False, actor_user_id=actor_user_id)
    await db.commit()
    await db.refresh(order)
    await after_paid(db, order=order)
    return order


async def mark_paid_by_session(
    db: AsyncSession, *, organization_id: uuid.UUID, stripe_checkout_session_id: str,
    order_id: str | None = None,
) -> VaittoMarketOrder | None:
    found = await db.execute(
        select(VaittoMarketOrder).where(
            VaittoMarketOrder.organization_id == organization_id,
            VaittoMarketOrder.stripe_checkout_session_id == stripe_checkout_session_id,
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
    db: AsyncSession, *, organization_id: uuid.UUID, order: VaittoMarketOrder, new_payment_method: str
) -> VaittoMarketOrder:
    if new_payment_method not in VAITTO_MARKET_ORDER_PAYMENT_METHODS:
        raise VaittoMarketValidationError("Metodo di pagamento non valido.")
    if order.status != "AWAITING_PAYMENT":
        raise VaittoMarketValidationError("L'ordine non è più in attesa di pagamento.")
    order.payment_method = new_payment_method
    await freeze_bank_transfer_discount(db, order=order)
    await db.commit()
    await db.refresh(order)
    return order


async def prepare_card_payment(db: AsyncSession, *, order: VaittoMarketOrder) -> int:
    """Quanto addebitare con Stripe: lo sconto bonifico sparisce, perché non
    si sta pagando con bonifico."""
    order.payment_method = "CARD"
    await freeze_bank_transfer_discount(db, order=order)
    await db.commit()
    await db.refresh(order)
    return amount_due_cents(order)


async def attach_stripe_checkout_session(
    db: AsyncSession, *, order: VaittoMarketOrder, session_id: str
) -> VaittoMarketOrder:
    order.payment_method = "CARD"
    order.stripe_checkout_session_id = session_id
    await db.commit()
    await db.refresh(order)
    return order


async def mark_shipped(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID, actor_user_id: uuid.UUID,
    tracking_number: str | None, tracking_url: str | None, tracking_company: str | None,
) -> VaittoMarketOrder:
    """Qui non c'è un fornitore che avvisa: la spedizione la segna
    l'amministratore, ed è il momento in cui il cliente riceve l'email."""
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None:
        raise VaittoMarketNotFoundError("Ordine non trovato.")
    if order.status != "PAID":
        raise VaittoMarketValidationError("Si spedisce solo un ordine già pagato.")
    order.fulfillment_status = "SHIPPED"
    order.tracking_number = (tracking_number or "").strip()[:128] or None
    order.tracking_url = (tracking_url or "").strip()[:1000] or None
    order.tracking_company = (tracking_company or "").strip()[:128] or None
    order.shipped_at = order.shipped_at or utcnow()
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="vaitto_market.order_shipped", entity_type="vaitto_market_order", entity_id=str(order.id),
        new_value={"tracking_number": order.tracking_number},
    )
    await db.commit()
    await db.refresh(order)
    await _notify_customer_shipping(db, order=order, delivered=False)
    return order


async def mark_delivered(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID, actor_user_id: uuid.UUID
) -> VaittoMarketOrder:
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None:
        raise VaittoMarketNotFoundError("Ordine non trovato.")
    order.fulfillment_status = "DELIVERED"
    order.delivered_at = order.delivered_at or utcnow()
    await db.commit()
    await db.refresh(order)
    await _notify_customer_shipping(db, order=order, delivered=True)
    return order


async def cancel_order(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID, reason: str, actor_user_id: uuid.UUID
) -> VaittoMarketOrder:
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None:
        raise VaittoMarketNotFoundError("Ordine non trovato.")
    if order.status != "AWAITING_PAYMENT":
        raise VaittoMarketValidationError("Si può annullare solo un ordine non ancora pagato.")
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
            idempotency_key=f"vaitto-market-order:{order.id}:credit-reversal",
        )
    await db.commit()
    await db.refresh(order)
    return order


# --- Email ----------------------------------------------------------------------------------------


def _items_html(items: list[VaittoMarketOrderItem]) -> str:
    return "".join(
        f"<br><strong>{html.escape(i.product_name)}</strong>"
        + (f" — {html.escape(i.variant_label)}" if i.variant_label else "")
        + (f"<br><small>di {html.escape(i.producer_name)}</small>" if i.producer_name else "")
        + f" × {i.quantity} — {i.unit_price_cents * i.quantity / 100:.2f} &euro;"
        for i in items
    )


async def _send_order_email(db: AsyncSession, *, order: VaittoMarketOrder) -> None:
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
            cta_url = await payments_service.create_checkout_session_for_vaitto_market_order(
                db, organization_id=order.organization_id, order=order,
                success_url=f"{settings.public_app_base_url}/customer?tab=orders",
                cancel_url=f"{settings.public_app_base_url}/customer?tab=orders",
            )
            cta_label = "Paga con carta"
        except (payments_service.StripeNotConfiguredError, stripe.error.StripeError):
            logger.exception("Marketplace VAITTO order %s confirmation email sent without a Stripe link", order.id)
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
        context=f"Marketplace VAITTO order confirmation email (order={order.id})",
        to=user.email,
        subject=f"Conferma ordine - {title} - Jav",
        html_body=render_email(
            preheader=f"Riepilogo del tuo ordine -- {title}", heading=heading, body_html=body,
            cta_label=cta_label, cta_url=cta_url,
        ),
        text_body=f"{heading}: {title}, totale {order.amount_cents / 100:.2f} EUR.",
    )


async def _send_payment_receipt_email(
    db: AsyncSession, *, order: VaittoMarketOrder, items: list[VaittoMarketOrderItem], by_card: bool
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
        context=f"Marketplace VAITTO payment receipt email (order={order.id})",
        to=user.email,
        subject=f"Pagamento ricevuto - ordine #{code} - Jav",
        html_body=render_email(
            preheader=f"Ricevuta di pagamento -- {title}", heading="Pagamento ricevuto, grazie",
            body_html=body, cta_label=None, cta_url=None,
        ),
        text_body=f"Pagamento ricevuto per l'ordine #{code}: {amount_due_cents(order) / 100:.2f} EUR.",
    )


async def _notify_customer_shipping(db: AsyncSession, *, order: VaittoMarketOrder, delivered: bool) -> None:
    items = await order_items(db, order)
    name = items_summary(items) if items else "il tuo ordine"
    title = f"{name} {'è stato consegnato' if delivered else 'è in viaggio verso di te'}"
    await notifications_service.notify_user(
        db, organization_id=order.organization_id, user_id=order.customer_user_id, type_="ORDER_SHIPPED",
        entity_type="vaitto_market_order", entity_id=order.id, title=title,
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
        context=f"Marketplace VAITTO shipping email (order={order.id}, delivered={delivered})",
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


async def _producers_of(db: AsyncSession, order: VaittoMarketOrder) -> dict:
    """Le righe dell'ordine raggruppate per azienda produttrice.

    Un ordine può contenere prodotti di aziende diverse: ciascuna deve
    ricevere **solo le sue righe**, perché è quello che deve preparare e
    perché il resto non la riguarda. Le righe senza azienda finiscono sotto
    `None` e le gestisce chi chiama: non c'è nessuno a cui mandarle."""
    gruppi: dict = {}
    for item in await order_items(db, order):
        product = await db.get(VaittoMarketProduct, item.product_id)
        producer = (
            await db.get(VaittoMarketProducer, product.producer_id)
            if product is not None and product.producer_id else None
        )
        chiave = producer.id if producer is not None else None
        gruppi.setdefault(chiave, {"producer": producer, "items": []})["items"].append(item)
    return gruppi


def _supplier_email_html(order: VaittoMarketOrder, items: list[VaittoMarketOrderItem], *, note: str | None) -> str:
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
) -> VaittoMarketOrder:
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
        raise VaittoMarketNotFoundError("Ordine non trovato.")
    if order.status != "PAID":
        raise VaittoMarketValidationError("Si invia al marchio solo un ordine già pagato dal cliente.")

    gruppi = await _producers_of(db, order)
    senza_azienda = gruppi.pop(None, None)
    if not gruppi:
        raise VaittoMarketValidationError(
            "Nessun prodotto di questo ordine ha un marchio: assegnalo dal catalogo e riprova."
        )

    mandate, problemi = 0, []
    for gruppo in gruppi.values():
        producer = gruppo["producer"]
        if not producer.email:
            problemi.append(f"«{producer.name}» non ha un'email in scheda")
            continue
        inviata = send_html_email_best_effort(
            context=f"Marketplace VAITTO supplier order (order={order.id}, producer={producer.id})",
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
            "senza marchio: " + ", ".join(i.product_name for i in senza_azienda["items"])
        )

    order.forward_error = "; ".join(problemi)[:500] or None
    if mandate:
        order.fulfillment_status = "SENT"
        order.forwarded_at = order.forwarded_at or utcnow()
        order.forwarded_by_user_id = actor_user_id
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="vaitto_market.order_forwarded", entity_type="vaitto_market_order", entity_id=str(order.id),
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
            type_="VAITTO_MARKET_ORDER_FORWARD_ISSUE", entity_type="vaitto_market_order", entity_id=order.id,
            title=f"Ordine #{order_code(order)}: invio ai marchi incompleto",
            body="; ".join(problemi)[:1000],
        )
    await db.commit()
    await db.refresh(order)
    if not mandate:
        raise VaittoMarketValidationError(
            "Nessuna email è partita: " + ("; ".join(problemi) or "nessun marchio raggiungibile.")
        )
    return order


async def after_paid(db: AsyncSession, *, order: VaittoMarketOrder) -> None:
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
    except VaittoMarketError:
        logger.warning("Invio automatico alle aziende non riuscito per l'ordine %s", order.id)
    except Exception:
        logger.exception("Invio automatico alle aziende non riuscito per l'ordine %s", order.id)
