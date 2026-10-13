"""Marketplace 3 (AliExpress dropshipping): settings, catalog, checkout, fulfillment.

See models.py for why this is a domain of its own. The checkout is the
Shopify one step by step (credit cap, OTP before spending JavCash, bank
transfer or card for the rest, bank transfer discounted, Stripe webhook as
the only proof of a card payment); what differs is the supplier side -- the
paid order is placed on AliExpress with the DS API, and shipping is read
back from its tracking.

**Reading AliExpress' answers.** Nothing here trusts a single nesting. Every
read goes through `client.first()` with the shapes the documentation gives,
and a product that cannot be understood raises with the gateway's own words
instead of quietly becoming an empty catalogue: a silent empty answer is the
one failure an administrator cannot diagnose. The field names marked
"da verificare dal vivo" are the ones we could not confirm against a real
answer -- the seller account is not authorised yet -- so they accept every
plausible spelling at once.
"""

import hashlib
import hmac
import html
import logging
import re
import time
import uuid
from datetime import timedelta
from decimal import Decimal

import stripe
from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import utcnow
from app.core.email import send_html_email_best_effort
from app.core.email_templates import render_email
from app.domains.aliexpress_dropshipping import client as aliexpress
from app.domains.aliexpress_dropshipping import pricing
from app.domains.aliexpress_dropshipping.models import (
    ALIEXPRESS_ORDER_PAYMENT_METHODS,
    PRICE_BASES,
    PRICE_ROUNDINGS,
    SHIPPING_MODES,
    AliexpressOrder,
    AliexpressOrderItem,
    AliexpressProduct,
    AliexpressSettings,
    AliexpressVariant,
)
from app.domains.audit import service as audit_service
from app.domains.marketplaces import rules
from app.domains.notifications import service as notifications_service
from app.domains.organizations import service as organizations_service
from app.domains.shop_categories import service as shop_categories_service
from app.domains.users.models import User
from app.domains.wallets import service as wallets_service

logger = logging.getLogger(__name__)

#: Which grid of the Shop these products sit in, for the categories layer
#: (shop_categories/models.py::SHOPS). Nothing else in this domain knows
#: about that layer: it is read here, on the product cards, and written
#: from its own endpoints.
SHOP = "aliexpress"

MAX_QUANTITY = 10
#: Quanti articoli *diversi* può portare un ordine. Il carrello non è un
#: magazzino: oltre questa soglia un ordine diventa ingestibile da evadere
#: e, su AliExpress, quasi certamente si spezza in più ordini fornitore.
MAX_ORDER_LINES = 20
MAX_ATTEMPTS = 6
#: The order is on AliExpress and still moving: worth asking about.
FOLLOWED_FULFILLMENT = ("SENT", "SHIPPED")
#: How long a signed OAuth state is worth anything.
STATE_MAX_AGE_SECONDS = 1800


class AliexpressError(Exception):
    pass


class AliexpressValidationError(AliexpressError):
    pass


class AliexpressNotFoundError(AliexpressError):
    pass


class InvalidOtpError(AliexpressError):
    pass


def order_number(order: AliexpressOrder) -> str:
    """Come si chiama un ordine per chi lo deve leggere: un numero, non un
    pezzo di UUID. Il fallback sull'UUID serve solo all'istante fra
    l'inserimento e la rilettura, quando la sequenza non ha ancora
    risposto."""
    return f"JAV-{order_code(order)}"


def order_code(order: AliexpressOrder) -> str:
    """Il numero nudo, per email e schermate."""
    return str(order.number) if getattr(order, "number", None) else str(order.id)[:8].upper()


def out_order_id(order: AliexpressOrder) -> str:
    """Our reference on AliExpress: deterministic, so a retry that reaches
    the supplier twice is the same order twice, never two orders."""
    return f"jav-{order.id.hex}"


def short_name(name: str, limit: int = 60) -> str:
    """Il nome di un prodotto dentro un messaggio al cliente. I titoli
    importati da AliExpress superano spesso i duecento caratteri, e un
    messaggio così lungo il browser lo scambia per un errore tecnico e lo
    nasconde dietro «errore imprevisto» (Session 87). Il cliente sa già di
    quale prodotto si parla: basta l'inizio del nome."""
    name = " ".join((name or "").split())
    return name if len(name) <= limit else name[: limit - 1].rstrip(" ,.;:-") + "…"


def html_to_text(value: str | None, limit: int = 8000) -> str:
    """AliExpress descriptions are HTML: kept as plain text with line breaks,
    nothing from a third party is ever rendered as markup on our pages."""
    if not value:
        return ""
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", value)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</div>|</h\d>", "\n", text)
    text = re.sub(r"(?i)<li[^>]*>", "• ", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    return text[:limit]


def _decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return None


def _pick(node, *names: str):
    """The first of several spellings of the same field that a dict carries."""
    if not isinstance(node, dict):
        return None
    for name in names:
        value = node.get(name)
        if value not in (None, ""):
            return value
    return None


# --- Impostazioni -------------------------------------------------------------------------------


async def get_settings_row(db: AsyncSession, *, organization_id: uuid.UUID) -> AliexpressSettings:
    row = (
        await db.execute(select(AliexpressSettings).where(AliexpressSettings.organization_id == organization_id))
    ).scalar_one_or_none()
    if row is None:
        row = AliexpressSettings(
            organization_id=organization_id, default_credit_percentage=rules.DEFAULT_CREDIT_PERCENTAGE
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


def settings_read_dict(row: AliexpressSettings) -> dict:
    return {
        "app_key": row.app_key,
        "app_secret_configured": bool(row.app_secret),
        "app_secret_hint": f"…{row.app_secret[-4:]}" if row.app_secret else None,
        "connected": bool(row.access_token),
        "account_label": row.account_label,
        "token_expires_at": row.token_expires_at,
        "last_connected_at": row.last_connected_at,
        "enabled": row.enabled,
        "ship_to_country": row.ship_to_country,
        "target_currency": row.target_currency,
        "target_language": row.target_language,
        "currency_rate": float(row.currency_rate),
        "price_basis": row.price_basis,
        "markup_percentage": row.markup_percentage,
        "markup_fixed_cents": row.markup_fixed_cents,
        "price_rounding": row.price_rounding,
        "shipping_mode": row.shipping_mode,
        "shipping_minimum_cents": row.shipping_minimum_cents,
        "shipping_days": row.shipping_days,
        "default_credit_percentage": row.default_credit_percentage,
        "max_credit_percentage": rules.MAX_CREDIT_PERCENTAGE,
        "auto_forward": row.auto_forward,
    }


PRICING_KEYS = (
    "currency_rate", "price_basis", "markup_percentage", "markup_fixed_cents", "price_rounding",
    "shipping_mode", "shipping_minimum_cents",
)


async def update_settings(
    db: AsyncSession, *, row: AliexpressSettings, updates: dict, actor_user_id: uuid.UUID
) -> AliexpressSettings:
    """Saves the settings; a changed pricing rule re-prices every variant from
    its stored AliExpress figures straight away."""
    if "price_rounding" in updates and updates["price_rounding"] not in PRICE_ROUNDINGS:
        raise AliexpressValidationError("Arrotondamento non valido.")
    if "shipping_mode" in updates and updates["shipping_mode"] not in SHIPPING_MODES:
        raise AliexpressValidationError("Modalità di spedizione non valida.")
    if "price_basis" in updates and updates["price_basis"] not in PRICE_BASES:
        raise AliexpressValidationError("Base di prezzo non valida.")
    if "default_credit_percentage" in updates:
        try:
            rules.check_credit_percentage(updates["default_credit_percentage"])
        except rules.CreditPercentageError as exc:
            raise AliexpressValidationError(str(exc)) from exc
    if updates.get("ship_to_country"):
        updates["ship_to_country"] = str(updates["ship_to_country"]).upper()
    if updates.get("target_currency"):
        updates["target_currency"] = str(updates["target_currency"]).upper()
    # Credentials never reach the audit log: popped from `updates` here.
    credentials_changed = False
    if "app_key" in updates:
        app_key = (updates.pop("app_key") or "").strip() or None
        if app_key != row.app_key:
            row.app_key = app_key
            credentials_changed = True
    if "app_secret" in updates:
        secret = (updates.pop("app_secret") or "").strip() or None
        if secret and secret != row.app_secret:
            row.app_secret = secret
            credentials_changed = True
    if credentials_changed:
        # An authorisation obtained with the old app is worthless: the
        # account must be linked again with the new one.
        row.access_token = None
        row.refresh_token = None
        row.token_expires_at = None
        row.account_label = None
        row.last_connected_at = None
    enabling = updates.get("enabled")
    if enabling and not (row.app_key and row.app_secret and row.access_token):
        raise AliexpressValidationError(
            "Per attivare il Marketplace servono prima App Key, App Secret e l'autorizzazione "
            "dell'account AliExpress."
        )
    reprice = any(k in updates and updates[k] != getattr(row, k) for k in PRICING_KEYS)
    for key, value in updates.items():
        setattr(row, key, value)
    row.updated_at = utcnow()
    await audit_service.record(
        db, organization_id=row.organization_id, actor_user_id=actor_user_id,
        action="aliexpress.settings_updated", entity_type="aliexpress_settings", entity_id=str(row.id),
        new_value={k: (str(v) if isinstance(v, Decimal) else v) for k, v in updates.items()},
    )
    await db.commit()
    await db.refresh(row)
    if reprice:
        await reprice_all(db, settings=row)
    return row


def _category_names(body: dict) -> list[str]:
    """Just enough of the connection test's answer to show the administrator
    that it is real data."""
    node = aliexpress.first(
        body,
        ("aliexpress_ds_category_get_response", "resp_result", "result", "categories"),
        ("aliexpress_ds_category_get_response", "result", "categories"),
        ("result", "categories"),
        ("categories",),
    )
    names = []
    for item in aliexpress.items_of(node, "category")[:5]:
        if isinstance(item, dict):
            names.append(str(_pick(item, "category_name", "name", "category_id") or ""))
    return [n for n in names if n]


async def test_connection(db: AsyncSession, *, row: AliexpressSettings) -> dict:
    """Asks AliExpress for the categories the account may sell: the cheapest
    proof that App Key, signature, token and DS permission all hold."""
    body = await aliexpress.category_get(row, language=row.target_language)
    row.last_connected_at = utcnow()
    await db.commit()
    await db.refresh(row)
    return {**settings_read_dict(row), "sample_categories": _category_names(body)}


# --- Autorizzazione dell'account (OAuth) --------------------------------------------------------
#
# Signed and stateless: the state carries the settings row's id, so the
# public callback -- which nobody is logged in for -- can find the row, and
# the HMAC over it proves the round trip is ours and recent.


def oauth_state(row: AliexpressSettings) -> str:
    ts = int(time.time())
    payload = f"{row.id}.{ts}"
    mac = hmac.new((row.app_secret or "").encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{mac}"


def oauth_state_settings_id(state: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(state.split(".", 1)[0])
    except (ValueError, AttributeError):
        return None


def oauth_state_ok(row: AliexpressSettings, state: str) -> bool:
    parts = (state or "").split(".")
    if len(parts) != 3:
        return False
    try:
        age = time.time() - int(parts[1])
    except ValueError:
        return False
    if age < -60 or age > STATE_MAX_AGE_SECONDS:
        return False
    expected = hmac.new(
        (row.app_secret or "").encode(), f"{parts[0]}.{parts[1]}".encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, parts[2])


async def get_settings_row_any_org(db: AsyncSession, *, settings_id: uuid.UUID) -> AliexpressSettings | None:
    """For the public callback only: no user, hence no organization, and the
    signed state is what stands in for both."""
    return await db.get(AliexpressSettings, settings_id)


def authorize_url(row: AliexpressSettings) -> str:
    if not aliexpress.has_credentials(row):
        raise aliexpress.AliexpressNotConfiguredError()
    return aliexpress.authorize_url(app_key=row.app_key, state=oauth_state(row))


async def complete_authorisation(
    db: AsyncSession, *, row: AliexpressSettings, code: str, actor_user_id: uuid.UUID | None = None
) -> AliexpressSettings:
    await aliexpress.create_token(row, code=code)
    await audit_service.record(
        db, organization_id=row.organization_id, actor_user_id=actor_user_id,
        action="aliexpress.account_authorised", entity_type="aliexpress_settings", entity_id=str(row.id),
        new_value={"account": row.account_label},
    )
    await db.commit()
    await db.refresh(row)
    return row


def _variant_price(variant: AliexpressVariant, *, settings: AliexpressSettings, product: AliexpressProduct) -> int:
    return pricing.sale_price_cents(
        cost=variant.cost_amount, price=variant.source_price_amount, settings=settings,
        markup_percentage=product.markup_percentage,
    )


async def reprice_all(db: AsyncSession, *, settings: AliexpressSettings) -> int:
    products = list(
        (
            await db.execute(
                select(AliexpressProduct).where(AliexpressProduct.organization_id == settings.organization_id)
            )
        ).scalars()
    )
    count = 0
    for product in products:
        for variant in await _variants(db, product.id):
            variant.price_cents = _variant_price(variant, settings=settings, product=product)
            count += 1
    await db.commit()
    return count


# --- Catalogo AliExpress (ricerca e anteprima) --------------------------------------------------


def _images_of(node) -> list[str]:
    """`image_urls` is a semicolon-separated string in the answers we know,
    a list in others. Both, then."""
    if isinstance(node, list):
        return [str(u) for u in node if u]
    if isinstance(node, str):
        return [u.strip() for u in node.replace(",", ";").split(";") if u.strip()]
    return []


def _sku_label(sku: dict) -> str:
    """"Colore: Nero · Taglia: M" from the SKU's properties, which is the only
    thing the customer will ever read about a variant."""
    properties = aliexpress.items_of(
        _pick(sku, "ae_sku_property_dtos", "ae_sku_property_d_t_o_s", "sku_property_list", "aeSkuPropertyDtos"),
        "ae_sku_property_d_t_o", "sku_property",
    )
    parts = []
    for prop in properties:
        if not isinstance(prop, dict):
            continue
        name = _pick(prop, "sku_property_name", "skuPropertyName", "property_name")
        value = _pick(
            prop, "property_value_definition_name", "sku_property_value", "propertyValueDefinitionName",
            "skuPropertyValue", "property_value",
        )
        if value:
            parts.append(f"{name}: {value}" if name else str(value))
    return " · ".join(str(p) for p in parts)[:255]


def _parse_sku(sku: dict, *, settings: AliexpressSettings) -> dict | None:
    sku_id = _pick(sku, "sku_id", "skuId", "id")
    if sku_id is None:
        return None
    # offer_sale_price is what a dropshipper actually pays; sku_price is the
    # list price. Da verificare dal vivo: some answers carry the pair as
    # offer_sale_price/sku_price, others as sale_price/original_price.
    cost = _decimal(_pick(sku, "offer_sale_price", "offerSalePrice", "sku_bulk_order_price", "sale_price"))
    price = _decimal(_pick(sku, "sku_price", "skuPrice", "original_price", "sku_sale_price")) or cost or Decimal(0)
    stock = _pick(sku, "sku_available_stock", "skuAvailableStock", "ipm_sku_stock", "available_stock")
    try:
        inventory = int(stock) if stock is not None else None
    except (TypeError, ValueError):
        inventory = None
    label = _sku_label(sku) or "Standard"
    image = None
    for prop in aliexpress.items_of(
        _pick(sku, "ae_sku_property_dtos", "ae_sku_property_d_t_o_s", "sku_property_list"), "ae_sku_property_d_t_o"
    ):
        if isinstance(prop, dict) and _pick(prop, "sku_image", "skuImage"):
            image = str(_pick(prop, "sku_image", "skuImage"))
            break
    return {
        "variant_id": str(sku_id),
        "sku_attr": str(_pick(sku, "sku_attr", "skuAttr") or "") or None,
        "sku": str(_pick(sku, "sku_code", "skuCode", "seller_sku") or "") or None,
        "label": label,
        "image_url": image,
        "cost_amount": float(cost) if cost is not None else None,
        "source_price_amount": float(price),
        "inventory": inventory,
        "price_cents": pricing.sale_price_cents(cost=cost, price=price, settings=settings),
    }


def _parse_product(body: dict, *, settings: AliexpressSettings) -> dict:
    """One AliExpress product as the admin screens show it, with our price per
    SKU. Raises when the answer carries no product at all, rather than
    returning an empty card nobody can explain."""
    result = aliexpress.first(
        body,
        ("aliexpress_ds_product_get_response", "result"),
        ("aliexpress_ds_product_get_response", "resp_result", "result"),
        ("result",),
        ("data",),
    )
    if not isinstance(result, dict):
        raise AliexpressNotFoundError("AliExpress non ha restituito il prodotto: riprova o controlla l'ID.")
    base = _pick(result, "ae_item_base_info_dto", "ae_item_base_info_d_t_o", "aeItemBaseInfoDto", "item_base_info") or {}
    multimedia = _pick(result, "ae_multimedia_info_dto", "ae_multimedia_info_d_t_o", "aeMultimediaInfoDto") or {}
    store = _pick(result, "ae_store_info", "ae_store_info_dto", "aeStoreInfo") or {}
    sku_node = _pick(result, "ae_item_sku_info_dtos", "ae_item_sku_info_d_t_o_s", "aeItemSkuInfoDtos", "sku_info") or {}

    product_id = str(_pick(base, "product_id", "productId") or _pick(result, "product_id", "productId") or "")
    images = _images_of(_pick(multimedia, "image_urls", "imageUrls", "images"))
    variants = []
    for sku in aliexpress.items_of(sku_node, "ae_item_sku_info_d_t_o", "sku", "ae_item_sku_info_dto"):
        if isinstance(sku, dict):
            parsed = _parse_sku(sku, settings=settings)
            if parsed is not None:
                variants.append(parsed)
    prices = [v["price_cents"] for v in variants]
    # A product with no sellable SKU is not a product we can import; the
    # answer is not broken, it just has nothing for us.
    status_raw = str(_pick(base, "product_status_type", "productStatusType", "status") or "").lower()
    return {
        "product_id": product_id,
        "product_url": _pick(base, "detail_url", "product_detail_url", "productDetailUrl")
        or (f"https://www.aliexpress.com/item/{product_id}.html" if product_id else None),
        "title": str(_pick(base, "subject", "product_title", "title") or ""),
        "vendor": str(_pick(store, "store_name", "storeName") or "") or None,
        # onSelling / offline, per the DS documentation; anything else is
        # treated as on sale rather than hiding a product by mistake.
        "status": "INACTIVE" if status_raw in ("offline", "off_selling", "inactive") else "ACTIVE",
        "description_text": html_to_text(_pick(base, "detail", "description", "product_description")),
        "image_url": images[0] if images else None,
        "images": images[:20],
        "variants": variants,
        "min_price_cents": min(prices) if prices else None,
        "max_price_cents": max(prices) if prices else None,
        "currency": settings.target_currency,
    }


def _parse_search_item(item: dict, *, settings: AliexpressSettings) -> dict | None:
    """A search hit. The search answer has no SKUs: the price shown is the
    one AliExpress advertises, marked up with our rules, and the real prices
    per variant arrive with the preview (ds.product.get)."""
    product_id = _pick(item, "product_id", "productId", "itemId", "item_id")
    if product_id is None:
        return None
    sale = _decimal(
        _pick(item, "target_sale_price", "targetSalePrice", "sale_price", "app_sale_price", "min_price", "salePrice")
    )
    original = _decimal(
        _pick(item, "target_original_price", "targetOriginalPrice", "original_price", "originalPrice", "max_price")
    )
    base_price = sale or original or Decimal(0)
    price_cents = pricing.sale_price_cents(cost=sale, price=original or base_price, settings=settings)
    image = _pick(item, "product_main_image_url", "productMainImageUrl", "image_url", "itemMainPic", "main_image")
    return {
        "product_id": str(product_id),
        "product_url": _pick(item, "product_detail_url", "productDetailUrl", "item_url", "detail_url"),
        "title": str(_pick(item, "product_title", "productTitle", "title", "subject") or ""),
        "vendor": str(_pick(item, "store_name", "storeName", "shop_name") or "") or None,
        "status": "ACTIVE",
        "description_text": "",
        "image_url": str(image) if image else None,
        "images": [str(image)] if image else [],
        # Filled by the preview: a search hit has no SKU list.
        "variants": [],
        "min_price_cents": price_cents,
        "max_price_cents": price_cents,
        "currency": settings.target_currency,
        "source_sale_price": float(sale) if sale is not None else None,
        "evaluate_rate": _pick(item, "evaluate_rate", "evaluateRate", "rating"),
    }


async def search_catalog(
    db: AsyncSession, *, row: AliexpressSettings, keyword: str | None, cursor: str | None
) -> dict:
    """`cursor` is the page number as a string: the DS search paginates by
    index, but the shop screens speak the same cursor language everywhere."""
    if not keyword:
        raise AliexpressValidationError("Scrivi che cosa cercare nel catalogo AliExpress.")
    try:
        page = max(1, int(cursor)) if cursor else 1
    except ValueError:
        page = 1
    body = await aliexpress.text_search(row, keyword=keyword, page=page)
    node = aliexpress.first(
        body,
        ("aliexpress_ds_text_search_response", "data", "products"),
        ("aliexpress_ds_text_search_response", "resp_result", "result", "products"),
        ("aliexpress_ds_text_search_response", "result", "products"),
        ("data", "products"),
        ("result", "products"),
        ("products",),
    )
    raw_items = aliexpress.items_of(node, "selection_search_product", "product", "traffic_product_info")
    imported = {
        pid for pid in (
            await db.execute(
                select(AliexpressProduct.aliexpress_product_id).where(
                    AliexpressProduct.organization_id == row.organization_id
                )
            )
        ).scalars()
    }
    items = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        parsed = _parse_search_item(raw, settings=row)
        if parsed is None:
            continue
        parsed["already_imported"] = parsed["product_id"] in imported
        items.append(parsed)
    # Some answers say how many pages there are, others only how many hits:
    # a full page is taken as "there may be more", which is never wrong by
    # more than one empty page.
    total_pages = _pick(
        aliexpress.first(
            body,
            ("aliexpress_ds_text_search_response", "data"),
            ("aliexpress_ds_text_search_response", "resp_result", "result"),
            ("data",),
            ("result",),
        ) or {},
        "totalPage", "total_page", "total_pages",
    )
    try:
        has_next = page < int(total_pages) if total_pages is not None else len(items) >= 20
    except (TypeError, ValueError):
        has_next = len(items) >= 20
    return {"items": items, "next_cursor": str(page + 1) if items and has_next else None}


async def preview_product(db: AsyncSession, *, row: AliexpressSettings, product_id: str) -> dict:
    body = await aliexpress.product_get(row, product_id=product_id)
    parsed = _parse_product(body, settings=row)
    if not parsed["variants"]:
        raise AliexpressNotFoundError(
            "AliExpress non ha restituito nessuna variante acquistabile per questo prodotto."
        )
    return parsed


def _parse_freight(body: dict, *, settings: AliexpressSettings) -> list[dict]:
    node = aliexpress.first(
        body,
        ("aliexpress_ds_freight_query_response", "result", "delivery_options"),
        ("aliexpress_ds_freight_query_response", "resp_result", "result", "delivery_options"),
        ("result", "delivery_options"),
        ("delivery_options",),
        ("result",),
    )
    options = []
    for item in aliexpress.items_of(node, "delivery_option_dto", "delivery_option_d_t_o", "freight"):
        if not isinstance(item, dict):
            continue
        # Verificato dal vivo (Session 76): `shipping_fee_cent` **non porta
        # centesimi**, nonostante il nome. Il gateway DS risponde "1.99" per
        # una spedizione da 1,99 EUR, e dividere per 100 la leggeva 0,02.
        # Finché il numero serviva solo a informare l'amministratore era un
        # refuso innocuo; da quando decide quanto si addebita al cliente
        # sarebbe un buco: una spedizione da 12 EUR letta 0,12 farebbe
        # vendere a 5,90 di minimo, in perdita. Entrambi i campi si leggono
        # quindi come importo nella valuta della risposta.
        amount = _pick(item, "shipping_fee_amount", "shippingFeeAmount", "freight_amount")
        if isinstance(amount, dict):
            amount = _pick(amount, "value", "amount")
        if amount is None:
            amount = _pick(item, "shipping_fee_cent", "shippingFeeCent")
        fee = _decimal(amount)
        options.append({
            "service_name": _pick(item, "service_name", "serviceName", "delivery_provider_name"),
            "company": _pick(item, "company", "carrier", "delivery_provider_name"),
            "shipping_fee_amount": float(fee) if fee is not None else None,
            "shipping_fee_cents": pricing.to_eur_cents(fee, Decimal(settings.currency_rate)) if fee is not None else None,
            "currency": _pick(item, "shipping_fee_currency", "currency") or settings.target_currency,
            "min_days": _pick(item, "min_delivery_days", "minDeliveryDays"),
            "max_days": _pick(item, "max_delivery_days", "maxDeliveryDays"),
            "free_shipping": bool(_pick(item, "free_shipping", "freeShipping") or False),
            "tracking": bool(_pick(item, "tracking", "tracking_available") or False),
        })
    return options


async def freight_options(
    db: AsyncSession, *, row: AliexpressSettings, product_id: str, sku_id: str | None, quantity: int
) -> dict:
    """What AliExpress would charge to ship this product to Italy: shown to
    the administrator so the flat shipping in the settings is a decision and
    not a guess."""
    body = await aliexpress.freight_query(row, product_id=product_id, sku_id=sku_id, quantity=max(1, quantity))
    return {"options": _parse_freight(body, settings=row)}


# --- Prodotti importati --------------------------------------------------------------------------


async def _variants(db: AsyncSession, product_id: uuid.UUID) -> list[AliexpressVariant]:
    return list(
        (
            await db.execute(
                select(AliexpressVariant)
                .where(AliexpressVariant.product_id == product_id)
                .order_by(AliexpressVariant.created_at)
            )
        ).scalars()
    )


async def get_product(db: AsyncSession, *, organization_id: uuid.UUID, product_id: uuid.UUID) -> AliexpressProduct:
    product = await db.get(AliexpressProduct, product_id)
    if product is None or product.organization_id != organization_id:
        raise AliexpressNotFoundError("Prodotto non trovato.")
    return product


def _check_credit(value: int) -> int:
    try:
        return rules.check_credit_percentage(value)
    except rules.CreditPercentageError as exc:
        raise AliexpressValidationError(str(exc)) from exc


async def import_product(
    db: AsyncSession, *, row: AliexpressSettings, actor_user_id: uuid.UUID, product_id: str, name: str,
    description: str | None, credit_discount_percentage: int | None, markup_percentage: int | None,
    variant_ids: list[str] | None, activate: bool,
) -> AliexpressProduct:
    existing = (
        await db.execute(
            select(AliexpressProduct).where(
                AliexpressProduct.organization_id == row.organization_id,
                AliexpressProduct.aliexpress_product_id == product_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise AliexpressValidationError("Questo prodotto è già stato importato: lo trovi in Prodotti importati.")
    credit = _check_credit(
        row.default_credit_percentage if credit_discount_percentage is None else credit_discount_percentage
    )
    preview = await preview_product(db, row=row, product_id=product_id)
    chosen = [v for v in preview["variants"] if not variant_ids or v["variant_id"] in variant_ids]
    if not chosen:
        raise AliexpressValidationError("Scegli almeno una variante da vendere.")

    product = AliexpressProduct(
        organization_id=row.organization_id,
        aliexpress_product_id=product_id,
        product_url=preview["product_url"],
        name=name.strip() or (preview["title"] or "Prodotto")[:255],
        source_title=(preview["title"] or "")[:500] or None,
        vendor=(preview["vendor"] or "")[:255] or None,
        description=(description if description is not None else preview["description_text"])[:8000],
        image_url=preview["image_url"],
        images=preview["images"],
        status="ACTIVE" if activate else "INACTIVE",
        credit_discount_percentage=credit,
        markup_percentage=markup_percentage,
        last_synced_at=utcnow(),
        created_by_user_id=actor_user_id,
        updated_at=utcnow(),
    )
    db.add(product)
    await db.flush()
    for v in chosen:
        variant = AliexpressVariant(
            product_id=product.id,
            aliexpress_sku_id=v["variant_id"],
            sku_attr=v["sku_attr"],
            sku=v["sku"],
            label=v["label"],
            image_url=v["image_url"],
            cost_amount=_decimal(v["cost_amount"]),
            source_price_amount=_decimal(v["source_price_amount"]) or Decimal(0),
            price_cents=0,
            inventory=v["inventory"],
            last_synced_at=utcnow(),
        )
        variant.price_cents = _variant_price(variant, settings=row, product=product)
        db.add(variant)
    await audit_service.record(
        db, organization_id=row.organization_id, actor_user_id=actor_user_id,
        action="aliexpress.product_imported", entity_type="aliexpress_product", entity_id=str(product.id),
        new_value={"aliexpress_product_id": product_id, "variants": len(chosen)},
    )
    await db.commit()
    await db.refresh(product)
    return product


async def update_product(
    db: AsyncSession, *, row: AliexpressSettings, product: AliexpressProduct, updates: dict,
    actor_user_id: uuid.UUID,
) -> AliexpressProduct:
    if "credit_discount_percentage" in updates:
        _check_credit(updates["credit_discount_percentage"])
    reprice = "markup_percentage" in updates and updates["markup_percentage"] != product.markup_percentage
    for key, value in updates.items():
        setattr(product, key, value)
    product.updated_at = utcnow()
    if reprice:
        for variant in await _variants(db, product.id):
            variant.price_cents = _variant_price(variant, settings=row, product=product)
    await audit_service.record(
        db, organization_id=row.organization_id, actor_user_id=actor_user_id,
        action="aliexpress.product_updated", entity_type="aliexpress_product", entity_id=str(product.id),
        new_value={k: v for k, v in updates.items() if k != "description"},
    )
    await db.commit()
    await db.refresh(product)
    return product


async def update_variant(
    db: AsyncSession, *, organization_id: uuid.UUID, variant_id: uuid.UUID, updates: dict
) -> AliexpressVariant:
    variant = await db.get(AliexpressVariant, variant_id)
    product = await db.get(AliexpressProduct, variant.product_id) if variant else None
    if variant is None or product is None or product.organization_id != organization_id:
        raise AliexpressNotFoundError("Variante non trovata.")
    for key, value in updates.items():
        setattr(variant, key, value)
    await db.commit()
    await db.refresh(variant)
    return variant


#: Le risposte di ds.product.get che vogliono dire «questo prodotto non si
#: vende più», da distinguere da un errore passeggero: solo queste spengono
#: le varianti. Il 604 «All SKU Unsaleable» è verificato dal vivo (Session
#: 87, cinque prodotti); gli altri sono le formulazioni con cui AliExpress
#: dice «offline» o «non esiste». Da verificare dal vivo: i codici numerici
#: di queste ultime.
OFF_SALE_CODES = {"604"}
OFF_SALE_WORDS = ("unsaleable", "not exist", "offline", "off shelf", "not on sale", "invalid product")


def off_sale_reason(body: dict) -> str | None:
    """Il motivo per cui AliExpress non vende più il prodotto, o None.

    Il 604 arriva dentro `aliexpress_ds_product_get_response`, non come
    errore del gateway: per il client è una risposta riuscita senza
    prodotto, e fino alla Session 87 finiva come «AliExpress non ha
    restituito il prodotto» lasciando il prodotto in vendita."""
    node = body.get("aliexpress_ds_product_get_response") if isinstance(body, dict) else None
    if not isinstance(node, dict):
        return None
    code = str(node.get("rsp_code") or "")
    message = str(node.get("rsp_msg") or "")
    if code in OFF_SALE_CODES or any(word in message.lower() for word in OFF_SALE_WORDS):
        return f"Non più in vendita su AliExpress ({message or 'codice ' + code})."[:500]
    return None


#: Quanto può essere vecchia l'ultima lettura prima di richiederla ad
#: AliExpress: all'apertura della scheda e al momento dell'ordine. La sync
#: completa (ogni tre ore) tiene aggiornata la griglia; queste due tengono
#: aggiornato ciò che il cliente sta davvero per comprare.
LIVE_CHECK_ON_VIEW = timedelta(minutes=10)
LIVE_CHECK_ON_ORDER = timedelta(minutes=2)


async def refresh_if_stale(
    db: AsyncSession, *, row: AliexpressSettings, product: AliexpressProduct, max_age: timedelta
) -> AliexpressProduct:
    """Rilegge il prodotto da AliExpress se l'ultima lettura è più vecchia di
    `max_age`. Non fa mai fallire la pagina o l'ordine: se AliExpress non
    risponde si resta sull'ultima lettura buona, perché «non ho potuto
    chiedere» non è «non è disponibile»."""
    if not aliexpress.is_connected(row):
        return product
    if product.last_synced_at is not None and product.last_synced_at > utcnow() - max_age:
        return product
    try:
        return await sync_product(db, row=row, product=product)
    except Exception:
        logger.warning("Lettura dal vivo del prodotto AliExpress %s non riuscita", product.id, exc_info=True)
        await db.rollback()
        refreshed = await db.get(AliexpressProduct, product.id)
        return refreshed or product


async def refresh_order_lines(
    db: AsyncSession, *, organization_id: uuid.UUID, lines: list["OrderLine"]
) -> None:
    """Prima di creare l'ordine: i prodotti che il cliente sta comprando si
    rileggono da AliExpress, così nessuno paga una cosa che non c'è più. Se
    qualcosa è sparito, il preventivo subito dopo lo rifiuta con il suo
    messaggio, prima di JavCash e pagamento."""
    row = await get_settings_row(db, organization_id=organization_id)
    seen: set[uuid.UUID] = set()
    for line_variant_id, _quantity in lines:
        variant = await db.get(AliexpressVariant, line_variant_id)
        if variant is None or variant.product_id in seen:
            continue
        seen.add(variant.product_id)
        product = await db.get(AliexpressProduct, variant.product_id)
        if product is not None and product.organization_id == organization_id:
            await refresh_if_stale(db, row=row, product=product, max_age=LIVE_CHECK_ON_ORDER)


#: Il motivo scritto su un prodotto che AliExpress vende ma non spedisce in
#: Italia (Session 88). Come «Non più in vendita», non è un errore della sync.
NOT_SHIPPABLE_PREFIX = "Non spedibile in Italia"


async def ships_to_destination(*, row: AliexpressSettings, product: AliexpressProduct, variants: list) -> bool | None:
    """Se AliExpress spedisce questo prodotto in Italia (Session 88).

    Prima si scopriva solo al checkout, con «non si può spedire in Italia»
    dopo aver scelto variante e quantità. Si prova la spedizione di una
    variante vendibile alla volta, fino a tre: basta che una risponda con un
    prezzo. True = spedibile, False = AliExpress non offre nessuna spedizione
    per nessuna di quelle provate, None = non si è saputo (AliExpress non
    risponde) -- e allora non si cambia niente."""
    candidates = sorted(
        (v for v in variants if v.active and v.available_in_store and (v.inventory is None or v.inventory > 0)),
        key=variant_price,
    )[:3]
    if not candidates:
        return None
    unknown = False
    for variant in candidates:
        try:
            await supplier_shipping_cents(row=row, product=product, variant=variant, quantity=1)
            return True
        except AliexpressShippingUnavailableError as exc:
            if exc.temporary:
                unknown = True
    return None if unknown else False


async def sync_product(
    db: AsyncSession, *, row: AliexpressSettings, product: AliexpressProduct
) -> AliexpressProduct:
    """Refreshes cost, price and stock from AliExpress and re-prices. A SKU no
    longer offered is kept (orders point at it) but stops being sold; a
    product taken off AliExpress stops being sold altogether."""
    try:
        body = await aliexpress.product_get(row, product_id=product.aliexpress_product_id)
        off_sale = off_sale_reason(body)
        parsed = None if off_sale else _parse_product(body, settings=row)
    except (aliexpress.AliexpressApiError, AliexpressNotFoundError) as exc:
        product.sync_error = str(exc)[:500]
        product.last_synced_at = utcnow()
        await db.commit()
        await db.refresh(product)
        return product
    variants = await _variants(db, product.id)
    if parsed is None:
        # AliExpress dice chiaro e tondo che non si vende più: nessuna variante
        # resta comprabile. Tutto ciò che abbiamo scelto noi (nome, JavCash,
        # ricarico, prezzo a mano, acceso/spento, categorie) resta com'è, così
        # il prodotto torna da solo il giorno che AliExpress lo rimette in vendita.
        for variant in variants:
            variant.available_in_store = False
            variant.last_synced_at = utcnow()
        product.sync_error = off_sale
        product.last_synced_at = utcnow()
        product.updated_at = utcnow()
        await db.commit()
        await db.refresh(product)
        return product
    by_id = {v["variant_id"]: v for v in parsed["variants"]}
    product.source_title = (parsed["title"] or "")[:500] or product.source_title
    product.images = parsed["images"] or product.images
    on_sale = parsed["status"] == "ACTIVE"
    for variant in variants:
        fresh = by_id.get(variant.aliexpress_sku_id)
        variant.available_in_store = fresh is not None and on_sale
        if fresh is not None:
            variant.cost_amount = _decimal(fresh["cost_amount"])
            variant.source_price_amount = _decimal(fresh["source_price_amount"]) or variant.source_price_amount
            variant.inventory = fresh["inventory"]
            variant.sku_attr = fresh["sku_attr"] or variant.sku_attr
        variant.last_synced_at = utcnow()
        variant.price_cents = _variant_price(variant, settings=row, product=product)
    ships = await ships_to_destination(row=row, product=product, variants=variants) if on_sale and by_id else None
    if ships is False:
        # Si vende ma non arriva in Italia: per il cliente è come non esserci.
        # Torna da solo il giorno che AliExpress offre una spedizione.
        for variant in variants:
            variant.available_in_store = False
    if not on_sale:
        product.sync_error = "Il prodotto non è più in vendita su AliExpress."
    elif not by_id:
        product.sync_error = "AliExpress non ha restituito nessuna variante per questo prodotto."
    elif ships is False:
        product.sync_error = f"{NOT_SHIPPABLE_PREFIX}: AliExpress non offre nessuna spedizione."
    else:
        product.sync_error = None
    product.last_synced_at = utcnow()
    product.updated_at = utcnow()
    await db.commit()
    await db.refresh(product)
    return product


async def sync_all_products(db: AsyncSession, *, organization_id: uuid.UUID) -> int:
    row = await get_settings_row(db, organization_id=organization_id)
    if not aliexpress.is_connected(row):
        return 0
    products = await list_products(db, organization_id=organization_id, active_only=False)
    failed = 0
    for product in products:
        product = await sync_product(db, row=row, product=product)
        if product.sync_error and not product.sync_error.startswith(("Non più in vendita", NOT_SHIPPABLE_PREFIX)):
            failed += 1
    # Metà dei prodotti che non si leggono non è un prodotto sparito: è la
    # sync che non funziona (token scaduto, API cambiata). Lo staff deve
    # saperlo, non scoprirlo da un cliente come nella Session 87.
    if len(products) >= 5 and failed * 2 > len(products):
        await alert_sync_failure(
            db, organization_id=organization_id, job="products",
            error=f"{failed} prodotti su {len(products)} non si sono potuti leggere da AliExpress.",
        )
    return len(products)


SYNC_FAILED_NOTIFICATION = "ALIEXPRESS_SYNC_FAILED"


async def alert_sync_failure(db: AsyncSession, *, organization_id: uuid.UUID, job: str, error: str) -> None:
    """Avvisa lo staff che un lavoro automatico AliExpress non funziona, al
    massimo una volta al giorno per lavoro: la sync gira ogni tre ore e gli
    ordini ogni mezz'ora, e un avviso ogni giro verrebbe ignorato."""
    from sqlalchemy import func

    from app.domains.notifications.models import Notification

    recent = await db.execute(
        select(func.count()).select_from(Notification).where(
            Notification.organization_id == organization_id,
            Notification.type == SYNC_FAILED_NOTIFICATION,
            Notification.entity_id == job,
            Notification.created_at > utcnow() - timedelta(hours=24),
        )
    )
    if recent.scalar_one():
        return
    labels = {"products": "l'aggiornamento dei prodotti", "orders": "l'aggiornamento degli ordini",
              "retry": "il reinvio degli ordini"}
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_=SYNC_FAILED_NOTIFICATION, entity_type="aliexpress_job", entity_id=job,
        title=f"AliExpress: {labels.get(job, job)} non funziona",
        body=(error[:900] + " Controlla il collegamento in Shop AliExpress → Impostazioni."),
    )
    await db.commit()


def variant_price(variant: AliexpressVariant) -> int:
    return variant.price_override_cents or variant.price_cents


def variant_sellable(variant: AliexpressVariant) -> bool:
    return variant.active and variant.available_in_store and (variant.inventory is None or variant.inventory > 0)


async def _category_ids(
    db: AsyncSession, product: AliexpressProduct, category_ids: list[uuid.UUID] | None
) -> list[uuid.UUID]:
    """The categories shown on a product card. A list endpoint reads them
    for the whole page in one query and passes them in; the endpoints that
    answer with a single product leave it to None and pay one query."""
    if category_ids is not None:
        return category_ids
    return await shop_categories_service.category_ids_for_product(
        db, organization_id=product.organization_id, shop=SHOP, product_id=product.id
    )


async def product_admin_dict(
    db: AsyncSession, product: AliexpressProduct, *, category_ids: list[uuid.UUID] | None = None
) -> dict:
    variants = await _variants(db, product.id)
    sold = await db.execute(
        select(AliexpressOrder.id).where(
            AliexpressOrder.aliexpress_product_id == product.id, AliexpressOrder.status == "PAID"
        )
    )
    return {
        "id": product.id,
        #: The Shop categories (shop_categories, Session 73), so the grid
        #: can filter without a call per product.
        "category_ids": await _category_ids(db, product, category_ids),
        "aliexpress_product_id": product.aliexpress_product_id,
        "product_url": product.product_url,
        "name": product.name,
        "source_title": product.source_title,
        "vendor": product.vendor,
        "description": product.description,
        "image_url": product.image_url,
        "images": product.images or [],
        "status": product.status,
        "credit_discount_percentage": product.credit_discount_percentage,
        "markup_percentage": product.markup_percentage,
        "last_synced_at": product.last_synced_at,
        "sync_error": product.sync_error,
        "paid_orders": len(sold.all()),
        "created_at": product.created_at,
        "variants": [
            {
                "id": v.id,
                "aliexpress_sku_id": v.aliexpress_sku_id,
                "sku_attr": v.sku_attr,
                "sku": v.sku,
                "label": v.label,
                "image_url": v.image_url,
                "cost_amount": float(v.cost_amount) if v.cost_amount is not None else None,
                "source_price_amount": float(v.source_price_amount),
                "price_cents": v.price_cents,
                "price_override_cents": v.price_override_cents,
                "effective_price_cents": variant_price(v),
                "inventory": v.inventory,
                "active": v.active,
                "available_in_store": v.available_in_store,
            }
            for v in variants
        ],
    }


async def list_products(
    db: AsyncSession, *, organization_id: uuid.UUID, active_only: bool
) -> list[AliexpressProduct]:
    stmt = select(AliexpressProduct).where(AliexpressProduct.organization_id == organization_id)
    if active_only:
        stmt = stmt.where(AliexpressProduct.status == "ACTIVE")
    return list((await db.execute(stmt.order_by(AliexpressProduct.created_at.desc()))).scalars())


async def product_customer_dict(
    db: AsyncSession, product: AliexpressProduct, *, settings: AliexpressSettings,
    bank_transfer_discount_percentage: int, category_ids: list[uuid.UUID] | None = None,
) -> dict | None:
    """Same shape as the Shopify card: one Shop grid for every marketplace."""
    variants = [v for v in await _variants(db, product.id) if v.active and v.available_in_store]
    if not variants:
        return None
    prices = [variant_price(v) for v in variants]
    return {
        "id": product.id,
        #: The Shop categories (shop_categories, Session 73), so the grid
        #: can filter without a call per product.
        "category_ids": await _category_ids(db, product, category_ids),
        "name": product.name,
        "description": product.description,
        "image_url": product.image_url,
        "images": product.images or [],
        "min_price_cents": min(prices),
        "max_price_cents": max(prices),
        "credit_discount_percentage": product.credit_discount_percentage,
        "shipping_days": settings.shipping_days,
        "shipping_included": settings.shipping_mode == "INCLUDED",
        #: The shown prices are the full ones; bank transfer takes this much off.
        "bank_transfer_discount_percentage": bank_transfer_discount_percentage,
        "in_stock": any(variant_sellable(v) for v in variants),
        "variants": [
            {
                "id": v.id,
                "label": v.label,
                "image_url": v.image_url,
                "price_cents": variant_price(v),
                "in_stock": variant_sellable(v),
            }
            for v in variants
        ],
    }


# --- Checkout -------------------------------------------------------------------------------------


async def _sellable(
    db: AsyncSession, *, organization_id: uuid.UUID, variant_id: uuid.UUID
) -> tuple[AliexpressProduct, AliexpressVariant]:
    variant = await db.get(AliexpressVariant, variant_id)
    product = await db.get(AliexpressProduct, variant.product_id) if variant else None
    if variant is None or product is None or product.organization_id != organization_id or product.status != "ACTIVE":
        raise AliexpressValidationError("Prodotto non disponibile.")
    if not variant_sellable(variant):
        raise AliexpressValidationError("Questa variante al momento non è disponibile.")
    return product, variant


def max_creditable_cents(*, amount_cents: int, credit_discount_percentage: int) -> int:
    """Never the whole price, whatever is stored (marketplaces/rules.py)."""
    percentage = min(credit_discount_percentage, rules.MAX_CREDIT_PERCENTAGE)
    return min(round(amount_cents * percentage / 100), max(amount_cents - 1, 0))


def bank_transfer_total_cents(*, residual_cents: int, percentage: int) -> int:
    return residual_cents - rules.bank_transfer_discount_cents(residual_cents=residual_cents, percentage=percentage)


def taxable_base_cents(order: AliexpressOrder) -> int:
    """Quanto vale questa vendita al netto dell'IVA: il prezzo davvero
    incassato (importo meno lo sconto bonifico) meno l'imposta che porta.

    Dalla Session 78 l'IVA e' **aggiunta** al prezzo invece che contenuta,
    ma la formula non cambia: in entrambi i casi `amount_cents` la contiene
    e va tolta. I JavCash non si sottraggono -- sono un modo di pagare, non
    uno sconto: la vendita vale lo stesso. E' questa, non il lordo, la
    grandezza su cui si misura un margine: l'IVA non e' mai stata nostra."""
    return order.amount_cents - (order.bank_transfer_discount_cents or 0) - (order.vat_amount_cents or 0)


def amount_due_cents(order: AliexpressOrder) -> int:
    """What the customer pays in euro: residual after JavCash, minus the
    bank-transfer discount when paying by bank transfer."""
    return order.amount_cents - order.credit_applied_cents - (order.bank_transfer_discount_cents or 0)


async def freeze_bank_transfer_discount(db: AsyncSession, *, order: AliexpressOrder) -> None:
    """Lo sconto bonifico dell'ordine per il metodo di pagamento di adesso,
    dall'impostazione di oggi -- mai dal browser. Non fa commit.

    Dalla Session 78 non tocca piu' l'IVA: quella si congela alla creazione
    sull'imponibile pieno e non si ricalcola (opzione (a), scelta
    dell'utente). Cambiare metodo di pagamento cambia quanto si paga, non
    quanta imposta c'e' dentro."""
    if order.status != "AWAITING_PAYMENT":
        return
    if order.payment_method == "BANK_TRANSFER":
        percentage = await rules.get_bank_transfer_discount_percentage(db, organization_id=order.organization_id)
        order.bank_transfer_discount_cents = rules.bank_transfer_discount_cents(
            residual_cents=order.amount_cents - order.credit_applied_cents, percentage=percentage
        )
    else:
        order.bank_transfer_discount_cents = 0
    # The discount moved the taxable base, so the VAT follows in the same
    # breath -- here and nowhere else, so no caller has to remember to.


#: Per quanto si tiene buona una quotazione di spedizione. Mezz'ora come per
#: CJ: un cliente che alza e abbassa la quantità non deve costare una
#: chiamata ad AliExpress ogni volta, e mezz'ora è abbastanza poco perché al
#: checkout il numero sia ancora quello vero.
FREIGHT_CACHE_SECONDS = 1800


class AliexpressShippingUnavailableError(AliexpressValidationError):
    """Non si è potuto sapere quanto costa spedire (Session 76).

    Ha una classe sua perché è l'unico errore per cui **non** esiste un
    ripiego accettabile. Tutti gli altri si possono raccontare al cliente e
    andare avanti; questo no: proseguire vorrebbe dire o addebitare il
    minimo -- cioè decidere che AliExpress spedisce a meno di 5,90 senza
    averglielo chiesto, e incassare 5,90 su una spedizione da 20 euro -- o
    addebitare zero, che è peggio. Meglio non vendere che vendere in
    perdita: l'ordine si ferma qui."""

    #: True quando AliExpress non ha risposto: il prodotto potrebbe essere
    #: spedibile, semplicemente non lo sappiamo (Session 88).
    temporary: bool = False


def _cheapest_freight(options: list[dict]) -> dict | None:
    """L'opzione che costa meno fra quelle che un prezzo ce l'hanno. Le
    opzioni senza importo non sono gratis: sono opzioni di cui AliExpress
    non ha detto il prezzo, e prenderle per zero è esattamente l'errore da
    non fare."""
    priced = [o for o in options if o.get("shipping_fee_cents") is not None]
    return min(priced, key=lambda o: o["shipping_fee_cents"]) if priced else None


async def supplier_shipping_cents(
    *, row: AliexpressSettings, product: AliexpressProduct, variant: AliexpressVariant, quantity: int
) -> int:
    """Quanto AliExpress chiede per spedire questa riga in Italia, in
    centesimi di euro.

    La quotazione è per (prodotto, SKU, quantità, destinazione): sono gli
    stessi quattro elementi della chiave di cache, quindi cambiare variante
    o quantità produce una chiave diversa e una quotazione nuova, senza che
    nessuno debba ricordarsi di invalidare niente.

    Solleva AliexpressShippingUnavailableError se non si riesce a saperlo --
    API muta, nessuna opzione, nessun prezzo. Non restituisce mai zero per
    disperazione.
    """
    key = (
        f"aliexpress:freight:{row.organization_id}:{product.aliexpress_product_id}:"
        f"{variant.aliexpress_sku_id}:{quantity}:{row.ship_to_country}"
    )
    cached = await aliexpress.cache_get(key)
    if cached is not None:
        return int(cached)
    try:
        body = await aliexpress.freight_query(
            row, product_id=product.aliexpress_product_id,
            sku_id=variant.aliexpress_sku_id, quantity=max(1, quantity),
        )
    except aliexpress.AliexpressApiError as exc:
        logger.warning(
            "AliExpress freight query failed (product=%s sku=%s qty=%s): %s",
            product.aliexpress_product_id, variant.aliexpress_sku_id, quantity, exc,
        )
        error = AliexpressShippingUnavailableError(
            f"«{short_name(product.name)}»: non riusciamo a calcolare la spedizione in questo momento. "
            "Riprova tra poco."
        )
        # «AliExpress non ha risposto», non «non spedisce»: chi controlla se un
        # prodotto è spedibile (sync_product) non deve spegnerlo per questo.
        error.temporary = True
        raise error from exc
    option = _cheapest_freight(_parse_freight(body, settings=row))
    if option is None:
        logger.warning(
            "AliExpress freight query returned no priced option (product=%s sku=%s qty=%s)",
            product.aliexpress_product_id, variant.aliexpress_sku_id, quantity,
        )
        raise AliexpressShippingUnavailableError(
            f"«{short_name(product.name)}» al momento non si può spedire in Italia: scegli un altro articolo."
        )
    cents = int(option["shipping_fee_cents"])
    await aliexpress.cache_set(key, cents, FREIGHT_CACHE_SECONDS)
    return cents


async def payment_methods(db: AsyncSession, *, organization_id: uuid.UUID) -> dict:
    return {
        "bank_transfer": await organizations_service.is_bank_transfer_configured(db, organization_id=organization_id),
        "card": await organizations_service.is_stripe_configured(db, organization_id=organization_id),
    }


async def order_items(db: AsyncSession, order: AliexpressOrder) -> list[AliexpressOrderItem]:
    """Le righe di un ordine, nell'ordine in cui sono state aggiunte. Ogni
    ordine ne ha almeno una, anche quelli creati prima del carrello: la
    migrazione 0055 gliela ha costruita dalle colonne della testata."""
    rows = await db.execute(
        select(AliexpressOrderItem)
        .where(AliexpressOrderItem.order_id == order.id)
        .order_by(AliexpressOrderItem.created_at, AliexpressOrderItem.id)
    )
    return list(rows.scalars().all())


def _item_field(item, name: str):
    """Le righe arrivano ora come dizionari del preventivo, ora come righe
    del database: leggerle allo stesso modo evita di scrivere due volte
    ogni frase che le descrive."""
    return item[name] if isinstance(item, dict) else getattr(item, name)


def _items_summary(items: list) -> str:
    """Come si chiama un ordine in una riga sola -- l'oggetto di un'email,
    il titolo di una notifica: il primo prodotto, e quanti altri."""
    first = _item_field(items[0], "product_name")
    others = len(items) - 1
    return first if others <= 0 else f"{first} + altri {others}"


def _items_detail(items: list) -> str:
    """Tutte le righe per esteso, per il corpo di una notifica."""
    parts = []
    for item in items:
        label = _item_field(item, "variant_label")
        parts.append(
            f"{_item_field(item, 'quantity')} × {_item_field(item, 'product_name')}"
            + (f" ({label})" if label else "")
        )
    return " · ".join(parts)


#: Una riga di acquisto: quale variante e quante unità. È la forma che il
#: carrello passa al checkout, ed è anche quella che usa la vecchia finestra
#: a prodotto singolo -- con una riga sola.
OrderLine = tuple[uuid.UUID, int]


def _lines_from(variant_id: uuid.UUID | None, quantity: int, lines: list[OrderLine] | None) -> list[OrderLine]:
    """Accetta le due forme e ne restituisce una sola. `lines` è il carrello;
    `variant_id`/`quantity` è la finestra del singolo prodotto, rimasta
    perché comprare un articolo solo senza passare dal carrello deve
    continuare a funzionare esattamente come prima."""
    if lines is not None:
        if not lines:
            raise AliexpressValidationError("Il carrello è vuoto.")
        if len(lines) > MAX_ORDER_LINES:
            raise AliexpressValidationError(f"Al massimo {MAX_ORDER_LINES} articoli diversi per ordine.")
        return lines
    if variant_id is None:
        raise AliexpressValidationError("Nessun prodotto da ordinare.")
    return [(variant_id, quantity)]


def creditable_cents_per_line(items: list[dict]) -> list[int]:
    """Quanti JavCash porta ogni riga: la **sua** percentuale sul **suo**
    valore, quantità compresa. Il tetto dell'ordine è la loro somma.

    Due cose che questo calcolo non fa, entrambe volute.

    Non fa una media sull'ordine: la media andrebbe arrotondata a
    percentuale intera, e l'arrotondamento non rispetterebbe i singoli
    prodotti -- un articolo da 5 EUR al 99% accanto a uno da 500 EUR allo
    0% darebbe JavCash presi da un prodotto che non ne accetta.

    E **non conta la spedizione**: i JavCash scontano la merce, non il
    corriere. Così il tetto è esattamente quello che il cliente ottiene
    sommando a mano le percentuali dei prodotti che ha nel carrello, e un
    numero che si può rifare a mano è un numero di cui ci si fida."""
    return [
        round(item["line_total_cents"] * item["credit_discount_percentage"] / 100)
        for item in items
    ]


async def get_quote(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_user_id: uuid.UUID,
    variant_id: uuid.UUID | None = None,
    quantity: int = 1,
    lines: list[OrderLine] | None = None,
) -> dict:
    """Quanto costa questo acquisto, riga per riga e in totale.

    La spedizione si conta **una volta per ordine**, non per riga: è una
    spedizione sola, e farla pagare tre volte a chi compra tre articoli
    sarebbe un errore che il cliente vede subito."""
    row = await get_settings_row(db, organization_id=organization_id)
    if not row.enabled:
        raise AliexpressValidationError("Questo shop non è disponibile al momento.")

    items: list[dict] = []
    seen: set[uuid.UUID] = set()
    for line_variant_id, line_quantity in _lines_from(variant_id, quantity, lines):
        if line_quantity < 1 or line_quantity > MAX_QUANTITY:
            raise AliexpressValidationError(f"Quantità da 1 a {MAX_QUANTITY}.")
        if line_variant_id in seen:
            raise AliexpressValidationError("Lo stesso articolo compare due volte nell'ordine.")
        seen.add(line_variant_id)
        product, variant = await _sellable(db, organization_id=organization_id, variant_id=line_variant_id)
        if variant.inventory is not None and variant.inventory < line_quantity:
            raise AliexpressValidationError(
                f"«{short_name(product.name)}»: disponibili solo {variant.inventory} pezzi."
            )
        unit = variant_price(variant)
        # Il freight si chiede per riga perché AliExpress lo quota così:
        # prodotto, SKU, quantità, destinazione. Il totale dell'ordine è la
        # loro somma -- non esiste, nella DS API, una quotazione di carrello.
        line_shipping = (
            0 if row.shipping_mode == "INCLUDED"
            else await supplier_shipping_cents(row=row, product=product, variant=variant, quantity=line_quantity)
        )
        items.append(
            {
                "variant_id": variant.id,
                "supplier_shipping_cents": line_shipping,
                "product_id": product.id,
                "product_name": product.name,
                "variant_label": variant.label,
                "image_url": variant.image_url or product.image_url,
                "quantity": line_quantity,
                "unit_price_cents": unit,
                "line_total_cents": unit * line_quantity,
                "credit_discount_percentage": product.credit_discount_percentage,
            }
        )

    items_cents = sum(i["line_total_cents"] for i in items)
    # Il costo reale dell'ordine, e solo dopo il minimo: applicarlo riga per
    # riga farebbe pagare tre volte la spedizione minima a chi compra tre
    # articoli (5,90 × 3 = 17,70), che è il comportamento da non avere.
    supplier_cents = sum(i["supplier_shipping_cents"] for i in items)
    shipping_cents = pricing.charged_shipping_cents(supplier_cents=supplier_cents, settings=row)
    vat_percentage = await rules.get_vat_percentage(db, organization_id=organization_id)
    # Session 78: il prezzo esposto e' l'imponibile, l'IVA si somma.
    # Solo sulla merce: la spedizione resta fuori (scelta dell'utente).
    vat_cents = rules.vat_added_cents(net_cents=items_cents, percentage=vat_percentage)
    amount = items_cents + vat_cents + shipping_cents
    per_line = creditable_cents_per_line(items)
    for item, creditable in zip(items, per_line):
        item["max_creditable_cents"] = creditable
    # Mai l'intero ordine, qualunque cosa dicano le percentuali dei prodotti
    # (marketplaces/rules.py): un prodotto dei Marketplace non si compra tutto
    # in JavCash.
    creditable_cents = min(sum(per_line), max(amount - 1, 0))
    # La percentuale che si legge a schermo è quella che risulta sulla merce
    # -- la stessa base su cui il tetto è calcolato. Con una riga sola è
    # esattamente la percentuale di quel prodotto.
    credit_percentage = round(creditable_cents * 100 / items_cents) if items_cents > 0 else 0
    wallet = await wallets_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer_user_id)
    methods = await payment_methods(db, organization_id=organization_id)
    discount_percentage = await rules.get_bank_transfer_discount_percentage(db, organization_id=organization_id)
    user = await db.get(User, customer_user_id)
    first = items[0]
    return {
        "items": items,
        # Le chiavi di un tempo, che valgono quando la riga è una sola: la
        # finestra del singolo prodotto le legge ancora, e con più righe
        # descrivono la prima -- mai un totale, per non farle sembrare
        # qualcosa che non sono.
        "variant_id": first["variant_id"],
        "product_name": first["product_name"],
        "variant_label": first["variant_label"],
        "quantity": first["quantity"],
        "unit_price_cents": first["unit_price_cents"],
        "items_cents": items_cents,
        #: L'IVA aggiunta sopra la merce, gia' dentro amount_cents.
        "vat_cents": vat_cents,
        "vat_percentage": vat_percentage,
        "shipping_cents": shipping_cents,
        #: Session 76: cosa c'è dietro la spedizione addebitata -- quanto
        #: costa a noi, il minimo in vigore, e se è stato il minimo a
        #: decidere. Serve al pannello admin e al margine; al cliente si
        #: mostra solo `shipping_cents`.
        "supplier_shipping_cents": supplier_cents,
        "minimum_shipping_cents": row.shipping_minimum_cents or 0,
        "shipping_is_minimum": row.shipping_mode != "INCLUDED" and shipping_cents > supplier_cents,
        "shipping_included": row.shipping_mode == "INCLUDED",
        "shipping_days": row.shipping_days,
        "amount_cents": amount,
        "credit_discount_percentage": credit_percentage,
        "max_creditable_cents": creditable_cents,
        "customer_wallet_balance_cents": wallet.balance_cents if wallet else 0,
        "bank_transfer_discount_percentage": discount_percentage,
        "bank_transfer_amount_cents": bank_transfer_total_cents(residual_cents=amount, percentage=discount_percentage),
        "bank_transfer_available": methods["bank_transfer"],
        "card_available": methods["card"],
        "default_address": {
            "street": user.residence_street if user else None,
            "city": user.residence_city if user else None,
            "province": user.residence_province if user else None,
            "postal_code": user.residence_postal_code if user else None,
        },
    }


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
) -> AliexpressOrder:
    """Places the order with every amount computed here, never taken from the browser.

    Un ordine porta una o più righe (`aliexpress_order_items`); il denaro
    resta tutto sulla testata, ed è per questo che pagamento, webhook,
    Contabilità ed email non hanno dovuto cambiare."""
    order_lines = _lines_from(variant_id, quantity, lines)
    await refresh_order_lines(db, organization_id=organization_id, lines=order_lines)
    quote = await get_quote(
        db, organization_id=organization_id, customer_user_id=customer_user_id, lines=order_lines,
    )
    row = await get_settings_row(db, organization_id=organization_id)
    amount = quote["amount_cents"]
    if credit_applied_cents < 0 or credit_applied_cents > quote["max_creditable_cents"]:
        raise AliexpressValidationError(
            f"Puoi usare al massimo {quote['max_creditable_cents'] / 100:.2f} JavCash per questo ordine."
        )
    if credit_applied_cents > 0:
        from app.domains.auth import service as auth_service

        if not otp_code or not await auth_service.verify_spend_code(
            db, user_id=customer_user_id, code=otp_code
        ):
            raise InvalidOtpError("Codice o PIN di conferma mancante, non valido o scaduto.")
    if payment_method not in ALIEXPRESS_ORDER_PAYMENT_METHODS:
        raise AliexpressValidationError("Metodo di pagamento non valido.")
    methods = await payment_methods(db, organization_id=organization_id)
    if payment_method == "BANK_TRANSFER" and not methods["bank_transfer"]:
        raise AliexpressValidationError("Il pagamento con bonifico non è configurato.")
    if payment_method == "CARD" and not methods["card"]:
        raise AliexpressValidationError("Il pagamento con carta non è configurato.")

    wallet = None
    if credit_applied_cents > 0:
        wallet = await wallets_service.get_or_create_wallet(
            db, organization_id=organization_id, user_id=customer_user_id
        )
        if wallet.balance_cents < credit_applied_cents:
            raise wallets_service.InsufficientBalanceError("Saldo JavCash insufficiente.")

    first = quote["items"][0]
    first_variant = await db.get(AliexpressVariant, first["variant_id"])
    order = AliexpressOrder(
        organization_id=organization_id,
        customer_user_id=customer_user_id,
        # Le colonne di riga sulla testata descrivono la prima riga. Restano
        # perché ogni ordine fatto prima del carrello le ha, e riscriverle
        # non si fa; le righe vere stanno in aliexpress_order_items.
        aliexpress_product_id=first["product_id"],
        aliexpress_variant_id=first["variant_id"],
        created_by_user_id=actor_user_id,
        quantity=first["quantity"],
        unit_price_cents=first["unit_price_cents"],
        shipping_cents=quote["shipping_cents"],
        #: Session 76: quanto ci costa e quale minimo era in vigore. Il
        #: margine di spedizione è la differenza, e senza questi due numeri
        #: non sarebbe ricostruibile a posteriori.
        supplier_shipping_cents=quote["supplier_shipping_cents"],
        minimum_shipping_cents=quote["minimum_shipping_cents"],
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
        unit_cost_amount=pricing.base_amount(
            cost=first_variant.cost_amount, price=first_variant.source_price_amount, settings=row
        )
        if first_variant is not None
        else None,
        currency_rate=row.currency_rate,
    )
    db.add(order)
    await db.flush()
    for item in quote["items"]:
        variant = await db.get(AliexpressVariant, item["variant_id"])
        db.add(
            AliexpressOrderItem(
                order_id=order.id,
                aliexpress_product_id=item["product_id"],
                aliexpress_variant_id=item["variant_id"],
                quantity=item["quantity"],
                unit_price_cents=item["unit_price_cents"],
                unit_cost_amount=pricing.base_amount(
                    cost=variant.cost_amount, price=variant.source_price_amount, settings=row
                )
                if variant is not None
                else None,
                supplier_shipping_cents=item["supplier_shipping_cents"],
                product_name=item["product_name"][:255],
                variant_label=(item["variant_label"] or None) and item["variant_label"][:255],
                credit_discount_percentage=item["credit_discount_percentage"],
            )
        )
    order.out_order_id = out_order_id(order)
    await freeze_bank_transfer_discount(db, order=order)
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="ALIEXPRESS_ORDER_CREATED", entity_type="aliexpress_order", entity_id=order.id,
        title=f"Nuovo ordine AliExpress: {_items_summary(quote['items'])}",
        body=f"{amount / 100:.2f} EUR -- {_items_detail(quote['items'])}",
        exclude_user_id=actor_user_id,
    )
    if credit_applied_cents > 0:
        assert wallet is not None
        debit = await wallets_service.debit_wallet_for_aliexpress_purchase(
            db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=credit_applied_cents,
            reference_aliexpress_order_id=order.id, actor_user_id=actor_user_id,
            note=f"Acquisto {_items_summary(quote['items'])}",
            idempotency_key=f"aliexpress-order:{order.id}:credit",
        )
        order.credit_debit_transaction_id = debit.id
    await db.commit()
    await db.refresh(order)
    await _send_order_email(db, order=order)
    return order


async def after_paid(db: AsyncSession, *, order: AliexpressOrder) -> None:
    """A paid order goes to AliExpress by itself when the administrator chose
    so; otherwise it waits in "Marketplace AliExpress → Ordini" for
    "Invia ad AliExpress"."""
    row = await get_settings_row(db, organization_id=order.organization_id)
    if not row.auto_forward:
        return
    try:
        from app.celery_app import celery_app

        celery_app.send_task("app.celery_app.aliexpress_forward_order_task", args=[str(order.id)])
    except Exception:
        logger.exception("Could not queue AliExpress forwarding of order %s", order.id)


# --- Ordini: letture ----------------------------------------------------------------------------------


async def get_org_scoped(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID
) -> AliexpressOrder | None:
    order = await db.get(AliexpressOrder, order_id)
    if order is None or order.organization_id != organization_id:
        return None
    return order


async def get_owned(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID, order_id: uuid.UUID
) -> AliexpressOrder | None:
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None or order.customer_user_id != customer_user_id:
        return None
    return order


async def list_orders(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID | None = None,
    status_filter: str | None = None,
) -> list[AliexpressOrder]:
    stmt = select(AliexpressOrder).where(AliexpressOrder.organization_id == organization_id)
    if customer_user_id is not None:
        stmt = stmt.where(AliexpressOrder.customer_user_id == customer_user_id)
    if status_filter:
        stmt = stmt.where(AliexpressOrder.status == status_filter)
    return list((await db.execute(stmt.order_by(AliexpressOrder.created_at.desc()))).scalars())


def tracking_link(order: AliexpressOrder) -> str | None:
    if order.tracking_url:
        return order.tracking_url
    return f"https://t.17track.net/it#nums={order.tracking_number}" if order.tracking_number else None


def delivery_status(order: AliexpressOrder) -> str | None:
    """The only shipping state a customer ever sees, same values as the other shops."""
    if order.status != "PAID":
        return None
    if order.fulfillment_status == "CANCELLED":
        return "PROBLEM"
    if order.fulfillment_status == "DELIVERED":
        return "DELIVERED"
    if order.fulfillment_status == "SHIPPED":
        return "SHIPPED"
    if order.fulfillment_status == "SENT":
        return "PREPARING"
    return "RECEIVED"


async def order_read_dict(db: AsyncSession, order: AliexpressOrder, *, admin: bool) -> dict:
    from app.domains.imported_products.service import _resolve_display_name

    product = await db.get(AliexpressProduct, order.aliexpress_product_id)
    variant = await db.get(AliexpressVariant, order.aliexpress_variant_id)
    # Session 75: un ordine porta N righe. Le colonne di testata qui sotto
    # descrivono la prima e restano per gli ordini storici; `items` è ciò
    # che va letto per sapere davvero cosa è stato comprato.
    items = await order_items(db, order)
    out = {
        "id": order.id,
        "number": order.number,
        "order_code": order_code(order),
        "customer_user_id": order.customer_user_id,
        "customer_display_name": await _resolve_display_name(
            db, organization_id=order.organization_id, user_id=order.customer_user_id
        ),
        "aliexpress_product_id": order.aliexpress_product_id,
        "aliexpress_variant_id": order.aliexpress_variant_id,
        "product_name": product.name if product else "—",
        "product_image_url": (variant.image_url if variant and variant.image_url else None)
        or (product.image_url if product else None),
        "variant_label": variant.label if variant else None,
        "created_by_user_id": order.created_by_user_id,
        "quantity": order.quantity,
        "unit_price_cents": order.unit_price_cents,
        "shipping_cents": order.shipping_cents,
        "amount_cents": order.amount_cents,
        "credit_applied_cents": order.credit_applied_cents,
        "residual_amount_cents": order.amount_cents - order.credit_applied_cents,
        "bank_transfer_discount_cents": order.bank_transfer_discount_cents or 0,
        #: Session 74: the VAT contained in what is charged, frozen at the
        #: moment the order was placed -- "di cui IVA" in the Shop.
        "vat_percentage": order.vat_percentage or 0,
        "vat_amount_cents": order.vat_amount_cents or 0,
        #: INCLUDED sugli ordini di prima della Session 78, ADDED da li' in poi.
        "vat_mode": order.vat_mode,
        "bank_transfer_discount_percentage": await rules.get_bank_transfer_discount_percentage(
            db, organization_id=order.organization_id
        ),
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
        "items": [
            {
                "id": item.id,
                "product_id": item.aliexpress_product_id,
                "variant_id": item.aliexpress_variant_id,
                "product_name": item.product_name,
                "variant_label": item.variant_label,
                "quantity": item.quantity,
                "unit_price_cents": item.unit_price_cents,
                "line_total_cents": item.unit_price_cents * item.quantity,
                "supplier_shipping_cents": item.supplier_shipping_cents,
                # Il tracking è per riga perché il fornitore può spezzare un
                # ordine in più spedizioni; se non lo ha fatto, è lo stesso
                # numero su ogni riga.
                "tracking_number": item.tracking_number or order.tracking_number,
                "tracking_url": item.tracking_url or tracking_link(order),
            }
            for item in items
        ],
        "delivery_status": delivery_status(order),
        "tracking_number": order.tracking_number,
        "tracking_url": tracking_link(order),
        "shipped_at": order.shipped_at,
        "delivered_at": order.delivered_at,
    }
    if admin:
        # Il costo fornitore è la somma di tutte le righe. Prima del
        # carrello un ordine ne aveva una sola e bastava la testata; con due
        # righe quella formula avrebbe dichiarato un margine gonfiato,
        # perché contava i ricavi di tutte e i costi di una.
        per_line = [
            pricing.to_eur_cents(Decimal(item.unit_cost_amount) * item.quantity, Decimal(order.currency_rate))
            for item in items
            if item.unit_cost_amount is not None
        ]
        cost_cents = sum(per_line) if len(per_line) == len(items) and items else None
        out.update({
            "fulfillment_status": order.fulfillment_status,
            "aliexpress_order_id": order.aliexpress_order_id,
            "aliexpress_order_status": order.aliexpress_order_status,
            "out_order_id": order.out_order_id,
            "tracking_company": order.tracking_company,
            #: Session 76: la spedizione ha un margine suo, separato da
            #: quello sulla merce -- si addebita `max(reale, minimo)`, e
            #: quando decide il minimo la differenza resta a noi. `None` sugli
            #: ordini di prima, dove il costo reale non lo rilevava nessuno.
            "supplier_shipping_cents": order.supplier_shipping_cents,
            "minimum_shipping_cents": order.minimum_shipping_cents,
            "shipping_margin_cents": (
                order.shipping_cents - order.supplier_shipping_cents
                if order.supplier_shipping_cents is not None else None
            ),
            #: Un ordine Jav può corrispondere a più ordini AliExpress
            #: (venditori diversi): qui quale numero è finito su quale riga.
            "item_supplier_orders": [
                {"item_id": item.id, "product_name": item.product_name,
                 "aliexpress_order_id": item.aliexpress_order_id}
                for item in items
            ],
            "unit_cost_amount": float(order.unit_cost_amount) if order.unit_cost_amount is not None else None,
            "currency_rate": float(order.currency_rate),
            "supplier_cost_cents": cost_cents,
            #: Net of VAT: the taxable base (what is charged, less the
            #: bank-transfer discount and the tax inside it) minus the
            #: supplier cost. The VAT was never revenue, so never margin.
            #: Session 76: al netto anche di quanto ci costa spedire. Prima
            #: la spedizione addebitata entrava nei ricavi e il suo costo
            #: non usciva da nessuna parte, quindi il margine la contava
            #: tutta come guadagno.
            "estimated_margin_cents": (
                taxable_base_cents(order) - cost_cents - (order.supplier_shipping_cents or 0)
                if cost_cents is not None else None
            ),
            "attempt_count": order.attempt_count,
            "last_attempt_at": order.last_attempt_at,
            "next_retry_at": order.next_retry_at,
            "last_error_kind": order.last_error_kind,
            "forwarded_at": order.forwarded_at,
            "forward_error": order.forward_error,
            "last_sync_at": order.last_sync_at,
        })
    return out


# --- Ordini: pagamento (identico agli altri negozi) ---------------------------------------------------


async def _send_payment_receipt_email(
    db: AsyncSession, *, order: AliexpressOrder, items: list[AliexpressOrderItem], by_card: bool
) -> None:
    """La ricevuta di avvenuto pagamento (Session 75).

    È la seconda email, e ha un mestiere diverso dalla prima: quella di
    conferma dice *cosa hai ordinato e come pagarlo*, questa dice *abbiamo
    ricevuto i soldi, ecco cosa hai pagato*. Per questo ripete l'elenco
    degli articoli invece di rimandare alla precedente: una ricevuta che
    non si basta da sola non è una ricevuta.

    Le cifre non si ricalcolano: si leggono congelate dall'ordine, IVA
    compresa. Best-effort come ogni email che non sia un OTP o un reset
    password -- un invio fallito non deve far fallire l'incasso, che a
    questo punto è già avvenuto (CLAUDE.md §5).
    """
    user = await db.get(User, order.customer_user_id)
    if user is None:
        return
    code = order_code(order)
    title = _items_summary(items) if items else "il tuo ordine"
    rows = "".join(
        f"<tr>"
        f"<td style=\"padding:4px 0\">{html.escape(item.product_name)}"
        + (f"<br><small>{html.escape(item.variant_label)}</small>" if item.variant_label else "")
        + f"</td>"
        f"<td style=\"padding:4px 8px;text-align:center\">{item.quantity}</td>"
        f"<td style=\"padding:4px 0;text-align:right\">"
        f"{item.unit_price_cents * item.quantity / 100:.2f} &euro;</td>"
        f"</tr>"
        for item in items
    )
    body = (
        f"<p>Numero ordine: <strong>#{code}</strong></p>"
        f"<table style=\"width:100%;border-collapse:collapse;font-size:14px\">{rows}</table>"
        f"<p style=\"margin-top:12px\">Spedizione: {order.shipping_cents / 100:.2f} &euro;<br>"
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
        # Il prezzo è IVA inclusa: qui si dice solo quanta ne contiene, non
        # se ne aggiunge (marketplaces/rules.py).
        body += f"<p><small>IVA {order.vat_percentage}% inclusa nel prezzo: {order.vat_amount_cents / 100:.2f} &euro;</small></p>"
    body += (
        f"<p>Consegna a: {html.escape(order.recipient_name)}, {html.escape(order.address_line1)}, "
        f"{html.escape(order.postal_code)} {html.escape(order.city)} ({html.escape(order.province)})"
        + (f"<br>Consegna stimata in {html.escape(order.shipping_days)} giorni lavorativi" if order.shipping_days else "")
        + "</p>"
        "<p>Prepariamo la spedizione: ti avvisiamo appena parte, con il numero per seguirla.</p>"
    )
    send_html_email_best_effort(
        context=f"AliExpress payment receipt email (order={order.id})",
        to=user.email,
        subject=f"Pagamento ricevuto - ordine #{code} - Jav",
        html_body=render_email(
            preheader=f"Ricevuta di pagamento -- {title}",
            heading="Pagamento ricevuto, grazie",
            body_html=body,
            cta_label=None,
            cta_url=None,
        ),
        text_body=f"Pagamento ricevuto per l'ordine #{code}: {amount_due_cents(order) / 100:.2f} EUR.",
    )


async def _mark_paid(
    db: AsyncSession, *, order: AliexpressOrder, by_card: bool, actor_user_id: uuid.UUID | None
) -> None:
    order.status = "PAID"
    order.paid_by_user_id = actor_user_id
    order.paid_at = utcnow()
    items = await order_items(db, order)
    name = _items_summary(items) if items else "un prodotto"
    await notifications_service.notify_user(
        db, organization_id=order.organization_id, user_id=order.customer_user_id, type_="ORDER_PAID",
        entity_type="aliexpress_order", entity_id=order.id, title=f"Il tuo ordine per {name} è confermato",
        body="Ti avvisiamo appena viene spedito.",
    )
    await notifications_service.notify_roles(
        db, organization_id=order.organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="ALIEXPRESS_ORDER_PAID", entity_type="aliexpress_order", entity_id=order.id,
        title=f"{'Pagamento Stripe' if by_card else 'Bonifico'} confermato: {name}",
        body=f"{amount_due_cents(order) / 100:.2f} EUR -- da inviare ad AliExpress",
    )
    # La ricevuta parte qui e solo qui. Entrambi i punti che chiamano
    # _mark_paid rifiutano un ordine che non sia AWAITING_PAYMENT, quindi un
    # webhook Stripe ripetuto non manda una seconda ricevuta.
    await _send_payment_receipt_email(db, order=order, items=items, by_card=by_card)


async def confirm_payment(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID, actor_user_id: uuid.UUID
) -> AliexpressOrder:
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None:
        raise AliexpressNotFoundError("Ordine non trovato.")
    if order.status != "AWAITING_PAYMENT":
        raise AliexpressValidationError("Questo ordine non è in attesa di pagamento.")
    if order.payment_method == "CARD":
        raise AliexpressValidationError("Un ordine pagato con carta viene confermato automaticamente da Stripe.")
    await _mark_paid(db, order=order, by_card=False, actor_user_id=actor_user_id)
    await db.commit()
    await db.refresh(order)
    await after_paid(db, order=order)
    return order


async def mark_paid_via_stripe(
    db: AsyncSession, *, organization_id: uuid.UUID, stripe_checkout_session_id: str, order_id: str | None = None
) -> AliexpressOrder | None:
    """`order_id` comes from the session's metadata: a customer may pay
    through an older link (the confirmation email's) after a newer checkout
    replaced the session id stored on the order -- still this order."""
    order = (
        await db.execute(
            select(AliexpressOrder).where(
                AliexpressOrder.organization_id == organization_id,
                AliexpressOrder.stripe_checkout_session_id == stripe_checkout_session_id,
            )
        )
    ).scalar_one_or_none()
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


async def cancel_order(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID, reason: str, actor_user_id: uuid.UUID
) -> AliexpressOrder:
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None:
        raise AliexpressNotFoundError("Ordine non trovato.")
    if order.status != "AWAITING_PAYMENT":
        raise AliexpressValidationError("Si può annullare solo un ordine non ancora pagato.")
    if order.credit_debit_transaction_id is not None:
        await wallets_service.reverse_transaction(
            db, organization_id=organization_id, transaction_id=order.credit_debit_transaction_id,
            actor_user_id=actor_user_id, reason=f"Ordine annullato: {reason}",
            idempotency_key=f"aliexpress-order:{order.id}:cancel-refund",
        )
    order.status = "CANCELLED"
    order.cancelled_by_user_id = actor_user_id
    order.cancelled_at = utcnow()
    order.cancellation_reason = reason
    await db.commit()
    await db.refresh(order)
    return order


async def change_payment_method(
    db: AsyncSession, *, organization_id: uuid.UUID, order: AliexpressOrder, new_payment_method: str
) -> AliexpressOrder:
    if order.status != "AWAITING_PAYMENT":
        raise AliexpressValidationError("Il metodo di pagamento si cambia solo prima di pagare.")
    if new_payment_method not in ALIEXPRESS_ORDER_PAYMENT_METHODS:
        raise AliexpressValidationError("Metodo di pagamento non valido.")
    if new_payment_method != order.payment_method:
        methods = await payment_methods(db, organization_id=organization_id)
        if new_payment_method == "BANK_TRANSFER" and not methods["bank_transfer"]:
            raise AliexpressValidationError("Il pagamento con bonifico non è configurato.")
        if new_payment_method == "CARD" and not methods["card"]:
            raise AliexpressValidationError("Il pagamento con carta non è configurato.")
        if order.payment_method == "CARD":
            order.stripe_checkout_session_id = None
        order.payment_method = new_payment_method
        await freeze_bank_transfer_discount(db, order=order)
        await db.commit()
        await db.refresh(order)
    return order


async def upload_payment_proof(
    db: AsyncSession, *, organization_id: uuid.UUID, order: AliexpressOrder, file_bytes: bytes, content_type: str,
    original_filename: str, actor_user_id: uuid.UUID,
) -> AliexpressOrder:
    from app.core.storage import UploadValidationError
    from app.core.storage import upload_document as storage_upload_document

    if order.status != "AWAITING_PAYMENT" or order.payment_method != "BANK_TRANSFER":
        raise AliexpressValidationError("La ricevuta si carica solo per un ordine da pagare con bonifico.")
    try:
        storage_key = storage_upload_document(
            file_bytes=file_bytes, content_type=content_type,
            key_prefix=f"aliexpress-order-payment-proofs/{order.customer_user_id}",
        )
    except UploadValidationError as exc:
        raise AliexpressValidationError(str(exc)) from exc
    order.payment_proof_storage_key = storage_key
    order.payment_proof_original_filename = original_filename
    order.payment_proof_uploaded_at = utcnow()
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="ORDER_PAYMENT_PROOF_UPLOADED", entity_type="aliexpress_order", entity_id=order.id,
        title="Ricevuta di bonifico caricata: ordine AliExpress", body=None, exclude_user_id=actor_user_id,
    )
    await db.commit()
    await db.refresh(order)
    return order


def presigned_payment_proof_url(order: AliexpressOrder) -> str:
    from app.core.storage import generate_presigned_document_url

    assert order.payment_proof_storage_key is not None
    return generate_presigned_document_url(storage_key=order.payment_proof_storage_key, expires_in_seconds=300)


async def prepare_card_payment(db: AsyncSession, *, order: AliexpressOrder) -> int:
    """Before a Stripe checkout: the order becomes a card order, without the
    bank-transfer discount and with the VAT re-frozen on the base that
    change leaves, and the amount Stripe must charge is returned."""
    order.payment_method = "CARD"
    await freeze_bank_transfer_discount(db, order=order)
    await db.flush()
    return amount_due_cents(order)


async def attach_stripe_checkout_session(
    db: AsyncSession, *, order: AliexpressOrder, session_id: str
) -> AliexpressOrder:
    order.payment_method = "CARD"
    order.stripe_checkout_session_id = session_id
    await db.commit()
    await db.refresh(order)
    return order


async def _send_order_email(db: AsyncSession, *, order: AliexpressOrder) -> None:
    user = await db.get(User, order.customer_user_id)
    if user is None:
        return
    settings = get_settings()
    code = order_code(order)
    items = await order_items(db, order)
    title = _items_summary(items)
    # Una riga per articolo: i nomi sono quelli congelati sull'ordine, non
    # quelli di oggi, così una email ristampata fra un anno dice ancora cosa
    # è stato comprato davvero.
    rows = "".join(
        f"<br><strong>{html.escape(item.product_name)}</strong>"
        + (f" — {html.escape(item.variant_label)}" if item.variant_label else "")
        + f" × {item.quantity} — {item.unit_price_cents * item.quantity / 100:.2f} &euro;"
        for item in items
    )
    lines = (
        f"<p>Numero ordine: <strong>#{code}</strong></p>"
        f"<p>{rows.removeprefix('<br>')}<br>"
        f"Spedizione: {order.shipping_cents / 100:.2f} &euro;"
        + (f" (consegna stimata {html.escape(order.shipping_days)} giorni)" if order.shipping_days else "")
        + f"<br>Totale: <strong>{order.amount_cents / 100:.2f} &euro;</strong>"
        + (f" (di cui {order.credit_applied_cents / 100:.2f} JavCash)" if order.credit_applied_cents else "")
        # The price is VAT included, so this only says how much of it is tax
        # -- it is never added to the total (marketplaces/rules.py).
        + (
            f"<br><small>IVA {order.vat_percentage}% inclusa: {order.vat_amount_cents / 100:.2f} &euro;</small>"
            if order.vat_amount_cents
            else ""
        )
        + "</p>"
        f"<p>Consegna a: {html.escape(order.recipient_name)}, {html.escape(order.address_line1)}, "
        f"{html.escape(order.postal_code)} {html.escape(order.city)} ({html.escape(order.province)})</p>"
    )
    residual = order.amount_cents - order.credit_applied_cents
    cta_label = cta_url = None
    heading = "Completa il pagamento del tuo ordine"
    if order.payment_method == "CARD":
        from app.domains.payments import service as payments_service

        lines += f"<p>Da pagare con carta: <strong>{amount_due_cents(order) / 100:.2f} &euro;</strong></p>"
        try:
            cta_url = await payments_service.create_checkout_session_for_aliexpress_order(
                db, organization_id=order.organization_id, order=order,
                success_url=f"{settings.public_app_base_url}/customer?tab=orders",
                cancel_url=f"{settings.public_app_base_url}/customer?tab=orders",
            )
            cta_label = "Paga con carta"
        except (payments_service.StripeNotConfiguredError, stripe.error.StripeError):
            logger.exception("AliExpress order %s confirmation email sent without a Stripe link", order.id)
    else:
        bank = await organizations_service.get_settings(db, organization_id=order.organization_id)
        discount = order.bank_transfer_discount_cents or 0
        lines += f"<p>Da pagare con bonifico: <strong>{amount_due_cents(order) / 100:.2f} &euro;</strong>"
        if discount:
            lines += (
                f"<br><small>Include lo sconto per il pagamento con bonifico ({discount / 100:.2f} &euro;); "
                f"con carta sarebbero {residual / 100:.2f} &euro;.</small>"
            )
        lines += "</p>"
        if bank.get("bank_iban"):
            lines += (
                f"<p><strong>IBAN:</strong> {bank['bank_iban']}<br>"
                f"<strong>Intestatario:</strong> {bank.get('bank_account_holder') or 'Jav'}<br>"
                f"<strong>Causale:</strong> Ordine {code}</p>"
            )
    send_html_email_best_effort(
        context=f"AliExpress order confirmation email (order={order.id})",
        to=user.email,
        subject=f"Conferma ordine - {title} - Jav",
        html_body=render_email(
            preheader=f"Riepilogo del tuo ordine -- {title}", heading=heading, body_html=lines,
            cta_label=cta_label, cta_url=cta_url,
        ),
        text_body=f"{heading}: {title}, totale {order.amount_cents / 100:.2f} EUR.",
    )


# --- Evasione su AliExpress ----------------------------------------------------------------------
#
# A paid order becomes an AliExpress order: the SKU, the quantity, the
# customer's address, and our own reference as `out_order_id`.
#
# Never two orders on AliExpress, whatever fails:
# - one sender at a time: a conditional UPDATE claims the order (-> SENDING);
# - the order carries a deterministic `out_order_id`, so a request the
#   supplier received twice is the same order twice, not two.
#
# And one difference from Shopify, paid for deliberately: Shopify could be
# asked "do you already have an order with this tag of mine?", and a lost
# answer was simply looked up. The DS API gives us no such question, so when
# the answer to ds.order.create is lost we do NOT retry by ourselves -- the
# order may well exist on AliExpress, money included. It goes to ERROR, staff
# are told, and a human decides. Sending a second parcel is worse than
# waiting for a person.


def _schedule_retry(order: AliexpressOrder, kind: str, *, may_exist: bool = False) -> None:
    order.last_error_kind = kind
    if may_exist:
        # We do not know whether AliExpress took the order: never automatic.
        order.next_retry_at = None
    elif kind in ("TEMPORARY", "AUTHENTICATION") and order.attempt_count < MAX_ATTEMPTS:
        minutes = min(5 * 2 ** max(order.attempt_count - 1, 0), 360)
        order.next_retry_at = utcnow() + timedelta(minutes=minutes)
    else:
        order.next_retry_at = None


async def _staff_alert(db: AsyncSession, *, order: AliexpressOrder, type_: str, title: str, body: str) -> None:
    await notifications_service.notify_roles(
        db, organization_id=order.organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_=type_, entity_type="aliexpress_order", entity_id=order.id, title=title[:255], body=body[:1000],
    )


def _phone_digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")[:20]


async def _order_request(db: AsyncSession, order: AliexpressOrder) -> dict:
    """The body of ds.order.create. Names taken from the DS documentation's
    PlaceOrderRequest4OpenApiDTO; `sku_attr` is what identifies the SKU, and
    a variant imported without one cannot be ordered at all.

    `product_items` porta una voce per riga dell'ordine: l'API le accetta
    già tutte insieme. Se le righe sono di venditori diversi AliExpress non
    crea un ordine ma più d'uno, e li restituisce tutti -- vedi
    _order_ids_from_answer()."""
    product_items = []
    for item in await order_items(db, order):
        variant = await db.get(AliexpressVariant, item.aliexpress_variant_id)
        product = await db.get(AliexpressProduct, item.aliexpress_product_id)
        if variant is None or product is None:
            raise AliexpressValidationError(
                f"«{item.product_name}»: prodotto o variante dell'ordine non più presenti."
            )
        if not variant.sku_attr:
            raise AliexpressValidationError(
                f"«{item.product_name}» non ha l'identificativo SKU di AliExpress: "
                "risincronizza il prodotto prima di inviare."
            )
        product_items.append(
            {
                "product_count": item.quantity,
                "product_id": product.aliexpress_product_id,
                "sku_attr": variant.sku_attr,
                "order_memo": order_number(order),
            }
        )
    address = {
        "address": order.address_line1[:255],
        "address2": (order.address_line2 or "")[:255],
        "city": order.city[:100],
        "contact_person": order.recipient_name[:100],
        "country": order.country_code,
        "full_name": order.recipient_name[:100],
        "mobile_no": _phone_digits(order.recipient_phone),
        # Da verificare dal vivo: the DS address wants the dialling prefix
        # apart from the number, and only Italy is shipped to today.
        "phone_country": "+39" if order.country_code == "IT" else "",
        "province": order.province[:64],
        "zip": order.postal_code,
    }
    return {
        "logistics_address": address,
        "product_items": product_items,
        "out_order_id": order.out_order_id or out_order_id(order),
    }


def _order_ids_from_answer(body: dict) -> list[str]:
    """I numeri degli ordini creati, **tutti**.

    Documentato come result.order_list.number, una lista, e finché un
    ordine portava un articolo solo leggerne il primo bastava. Col
    carrello non basta più: articoli di venditori diversi diventano su
    AliExpress ordini diversi, e fermarsi al primo vorrebbe dire perdere
    di vista tutti gli altri -- niente tracking, niente stato, merce
    partita che da qui risulterebbe mai spedita.

    L'ordine dei numeri restituiti è quello della risposta: non è
    garantito che corrisponda alle nostre righe, quindi si conservano tutti
    sulla testata e si attribuiscono alla riga solo quando sono uno per
    riga (vedi forward_order)."""
    node = aliexpress.first(
        body,
        ("aliexpress_ds_order_create_response", "result", "order_list"),
        ("aliexpress_ds_order_create_response", "resp_result", "result", "order_list"),
        ("result", "order_list"),
        ("order_list",),
    )
    found: list[str] = []
    for value in aliexpress.items_of(node, "number", "order_id", "orderId"):
        if isinstance(value, dict):
            value = _pick(value, "order_id", "orderId", "number")
        if value not in (None, "") and str(value) not in found:
            found.append(str(value))
    if found:
        return found
    single = aliexpress.first(
        body,
        ("aliexpress_ds_order_create_response", "result", "order_id"),
        ("result", "order_id"),
        ("order_id",),
    )
    return [str(single)] if single not in (None, "", [], {}) else []


async def forward_order(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID, actor_user_id: uuid.UUID | None
) -> AliexpressOrder:
    """Places the paid order on AliExpress, once. Safe to call any number of
    times, by the automatic flow, the retry job or an administrator; a
    failure is recorded on the order, not raised."""
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None:
        raise AliexpressNotFoundError("Ordine non trovato.")
    if order.status != "PAID":
        raise AliexpressValidationError("Si invia ad AliExpress solo un ordine già pagato dal cliente.")
    if order.aliexpress_order_id:
        raise AliexpressValidationError("Questo ordine è già su AliExpress.")
    now = utcnow()
    claimed = await db.execute(
        update(AliexpressOrder)
        .where(
            AliexpressOrder.id == order.id,
            AliexpressOrder.aliexpress_order_id.is_(None),
            or_(
                AliexpressOrder.fulfillment_status.in_(("NOT_SENT", "ERROR")),
                and_(
                    AliexpressOrder.fulfillment_status == "SENDING",
                    AliexpressOrder.last_attempt_at < now - timedelta(minutes=10),
                ),
            ),
        )
        .values(fulfillment_status="SENDING", last_attempt_at=now, attempt_count=AliexpressOrder.attempt_count + 1)
    )
    await db.commit()
    if claimed.rowcount != 1:
        await db.refresh(order)
        raise AliexpressValidationError("Questo ordine è già in lavorazione proprio ora.")
    await db.refresh(order)
    row = await get_settings_row(db, organization_id=organization_id)
    sent = False
    try:
        request = await _order_request(db, order)
        order.out_order_id = request["out_order_id"]
        await db.commit()  # before sending: the reference survives a lost answer
        sent = True
        body = await aliexpress.order_create(row, request=request)
        supplier_order_ids = _order_ids_from_answer(body)
        if not supplier_order_ids:
            # The call succeeded and we cannot say what it created: exactly
            # the case that must never be retried by a machine.
            raise aliexpress.AliexpressApiError(
                "AliExpress ha accettato la richiesta senza restituire il numero d'ordine: "
                "controlla su AliExpress prima di riprovare.",
                "TEMPORARY",
            )
        # Sulla testata il primo, che è anche l'unico quando AliExpress non
        # ha spezzato nulla. Sulle righe uno ciascuna, ma solo se i numeri
        # sono tanti quante le righe: se sono meno, l'abbinamento sarebbe
        # un'ipotesi, e un tracking attribuito all'articolo sbagliato è
        # peggio di nessun tracking.
        items = await order_items(db, order)
        if len(supplier_order_ids) == len(items):
            for item, supplier_id in zip(items, supplier_order_ids):
                item.aliexpress_order_id = supplier_id[:128]
        elif len(supplier_order_ids) == 1:
            for item in items:
                item.aliexpress_order_id = supplier_order_ids[0][:128]
        else:
            await _staff_alert(
                db, order=order, type_="ALIEXPRESS_ORDER_SPLIT",
                title=f"Ordine AliExpress diviso dal fornitore: #{order_code(order)}",
                body=(
                    f"AliExpress ha creato {len(supplier_order_ids)} ordini per {len(items)} articoli "
                    f"({', '.join(supplier_order_ids)}): abbina i tracking a mano."
                ),
            )
        order.aliexpress_order_id = supplier_order_ids[0][:128]
        order.fulfillment_status = "SENT"
        order.forwarded_at = order.forwarded_at or utcnow()
        order.forwarded_by_user_id = actor_user_id
        order.forward_error = None
        order.last_error_kind = None
        order.next_retry_at = None
        await audit_service.record(
            db, organization_id=organization_id, actor_user_id=actor_user_id,
            action="aliexpress.order_created", entity_type="aliexpress_order", entity_id=str(order.id),
            new_value={
                "aliexpress_order_id": order.aliexpress_order_id,
                "aliexpress_order_ids": supplier_order_ids,
                "out_order_id": order.out_order_id,
            },
        )
        await db.commit()
    except (aliexpress.AliexpressApiError, AliexpressValidationError) as exc:
        kind = getattr(exc, "kind", "VALIDATION")
        may_exist = sent and kind == "TEMPORARY"
        logger.warning("AliExpress forwarding failed for order %s (%s): %s", order.id, kind, exc)
        order.fulfillment_status = "ERROR"
        order.forward_error = str(exc)[:500]
        _schedule_retry(order, kind, may_exist=may_exist)
        if order.next_retry_at is None:
            await _staff_alert(
                db, order=order, type_="ALIEXPRESS_ORDER_FAILED",
                title=f"Ordine #{order_code(order)}: serve un controllo su AliExpress",
                body=(
                    f"{exc}. "
                    + (
                        f"L'ordine potrebbe essere già stato creato: cercalo su AliExpress con il riferimento "
                        f"{order.out_order_id}. "
                        if may_exist else ""
                    )
                    + "Il cliente ha pagato e vede \"Ordine ricevuto\". Marketplace AliExpress → Ordini."
                ),
            )
        await db.commit()
    await db.refresh(order)
    return order


# --- Tracking -------------------------------------------------------------------------------------
#
# The DS tracking answers are the least uniform of the lot, so instead of
# guessing one shape they are walked through: the first plausible spelling
# of a waybill number, a carrier and a status wins, and the delivery is
# recognised both from a status and from the words of the last event.

TRACKING_NUMBER_KEYS = ("mail_no", "mailNo", "logistics_no", "logisticsNo", "tracking_number", "trackingNumber", "waybill_no")
TRACKING_URL_KEYS = ("official_website", "officialWebsite", "tracking_url", "trackingUrl", "track_url")
TRACKING_COMPANY_KEYS = (
    "logistics_service_name", "logisticsServiceName", "carrier", "company", "logistics_company", "service_name",
    "serviceName", "provider_name",
)
TRACKING_STATUS_KEYS = (
    "status", "logistics_status", "logisticsStatus", "package_status", "tracking_status", "current_status", "state",
)
TRACKING_EVENT_KEYS = ("event_desc", "eventDesc", "status_desc", "description", "track_content")
#: Both the API's own vocabulary and the words a carrier writes in Italian.
DELIVERED_WORDS = ("delivered", "signed", "sign_in", "signfor", "consegnat", "consegna effettuata")
SHIPPED_WORDS = ("shipped", "transit", "in_transit", "departed", "picked", "accepted", "spedit", "in viaggio")


def _walk(node, found: dict) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, (dict, list)):
                _walk(value, found)
                continue
            if value in (None, ""):
                continue
            text = str(value)
            if key in TRACKING_NUMBER_KEYS:
                found.setdefault("number", text)
            elif key in TRACKING_URL_KEYS and text.startswith("http"):
                found.setdefault("url", text)
            elif key in TRACKING_COMPANY_KEYS:
                found.setdefault("company", text)
            elif key in TRACKING_STATUS_KEYS:
                found.setdefault("status", text)
                found.setdefault("words", "")
                found["words"] += " " + text
            elif key in TRACKING_EVENT_KEYS:
                found.setdefault("words", "")
                found["words"] += " " + text
    elif isinstance(node, list):
        for item in node:
            _walk(item, found)


def _tracking_from_remote(body: dict) -> tuple[str | None, dict, str | None]:
    """(our fulfillment status or None when unchanged, tracking info, the
    supplier's own status word)."""
    found: dict = {}
    _walk(body, found)
    words = (found.get("words", "") + " " + found.get("status", "")).lower()
    tracking = {k: found.get(k) for k in ("number", "url", "company") if found.get(k)}
    if any(word in words for word in DELIVERED_WORDS):
        return "DELIVERED", tracking, found.get("status")
    if "cancel" in words or "annullat" in words:
        return "CANCELLED", tracking, found.get("status")
    if tracking.get("number") or any(word in words for word in SHIPPED_WORDS):
        return "SHIPPED", tracking, found.get("status")
    return None, tracking, found.get("status")


async def sync_orders(
    db: AsyncSession, *, organization_id: uuid.UUID, orders: list[AliexpressOrder] | None = None
) -> int:
    """Asks AliExpress about every order still moving: shipping, tracking,
    delivery. Tells the customer when their parcel leaves and when it
    arrives. Returns how many orders changed."""
    row = await get_settings_row(db, organization_id=organization_id)
    if not aliexpress.is_connected(row):
        return 0
    if orders is None:
        orders = list(
            (
                await db.execute(
                    select(AliexpressOrder).where(
                        AliexpressOrder.organization_id == organization_id,
                        AliexpressOrder.aliexpress_order_id.is_not(None),
                        AliexpressOrder.fulfillment_status.in_(FOLLOWED_FULFILLMENT),
                    )
                )
            ).scalars()
        )
    changed = 0
    for order in orders:
        if not order.aliexpress_order_id:
            continue
        try:
            body = await aliexpress.order_tracking(row, order_id=order.aliexpress_order_id)
        except aliexpress.AliexpressApiError as exc:
            # One unreachable order must not stop the others: the next run
            # asks again, and the administrator sees the last attempt.
            logger.info("AliExpress tracking unavailable for order %s: %s", order.id, exc)
            order.last_sync_at = utcnow()
            continue
        order.last_sync_at = utcnow()
        new_status, tracking, remote_status = _tracking_from_remote(body)
        previous = order.fulfillment_status
        previous_tracking = order.tracking_number
        if remote_status:
            order.aliexpress_order_status = remote_status[:64]
        if tracking:
            order.tracking_number = (tracking.get("number") or "")[:128] or order.tracking_number
            order.tracking_url = (tracking.get("url") or "")[:1000] or order.tracking_url
            order.tracking_company = (tracking.get("company") or "")[:128] or order.tracking_company
        if new_status and order.fulfillment_status != "SENDING":
            order.fulfillment_status = new_status
        if order.fulfillment_status == previous and order.tracking_number == previous_tracking:
            continue
        changed += 1
        if order.fulfillment_status == "SHIPPED" and previous != "SHIPPED":
            order.shipped_at = utcnow()
            await _notify_customer_shipping(db, order=order, delivered=False)
        elif order.fulfillment_status == "DELIVERED" and previous != "DELIVERED":
            order.delivered_at = utcnow()
            order.shipped_at = order.shipped_at or utcnow()
            await _notify_customer_shipping(db, order=order, delivered=True)
        elif order.fulfillment_status == "CANCELLED" and previous != "CANCELLED":
            await _staff_alert(
                db, order=order, type_="ALIEXPRESS_ORDER_FAILED",
                title=f"AliExpress ha annullato l'ordine {order_code(order)}",
                body="Il cliente ha già pagato: valuta rimborso o nuovo invio.",
            )
    await db.commit()
    return changed


async def retry_due_orders(db: AsyncSession, *, organization_id: uuid.UUID) -> int:
    """The safety net of the automatic flow: paid orders never sent, and
    temporary failures whose retry time has come (bounded attempts). An
    order whose answer was lost is never in here -- see forward_order."""
    row = await get_settings_row(db, organization_id=organization_id)
    if not aliexpress.is_connected(row) or not row.auto_forward:
        return 0
    now = utcnow()
    due = list(
        (
            await db.execute(
                select(AliexpressOrder)
                .where(
                    AliexpressOrder.organization_id == organization_id,
                    AliexpressOrder.status == "PAID",
                    AliexpressOrder.aliexpress_order_id.is_(None),
                    or_(
                        and_(
                            AliexpressOrder.fulfillment_status == "NOT_SENT",
                            AliexpressOrder.paid_at < now - timedelta(minutes=2),
                        ),
                        and_(
                            AliexpressOrder.fulfillment_status == "ERROR",
                            AliexpressOrder.next_retry_at.is_not(None),
                            AliexpressOrder.next_retry_at <= now,
                        ),
                        and_(
                            AliexpressOrder.fulfillment_status == "SENDING",
                            AliexpressOrder.last_attempt_at < now - timedelta(minutes=10),
                        ),
                    ),
                )
                .order_by(AliexpressOrder.paid_at)
            )
        ).scalars()
    )
    handled = 0
    for order in due:
        try:
            await forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=None)
            handled += 1
        except AliexpressError:
            continue
    return handled


async def _notify_customer_shipping(db: AsyncSession, *, order: AliexpressOrder, delivered: bool) -> None:
    # Il riepilogo di tutte le righe: su un ordine da tre articoli dire il
    # nome di uno solo farebbe credere che gli altri due siano rimasti
    # indietro (Session 75).
    items = await order_items(db, order)
    name = _items_summary(items) if items else "il tuo ordine"
    title = f"{name} è stato consegnato" if delivered else f"{name} è stato spedito"
    body = None if delivered else (f"Numero di tracking: {order.tracking_number}" if order.tracking_number else None)
    await notifications_service.notify_user(
        db, organization_id=order.organization_id, user_id=order.customer_user_id, type_="ORDER_SHIPPED",
        entity_type="aliexpress_order", entity_id=order.id, title=title, body=body,
    )
    user = await db.get(User, order.customer_user_id)
    if user is None:
        return
    link = tracking_link(order)
    body_html = (
        f"<p>Numero ordine: <strong>#{order_code(order)}</strong></p>"
        f"<p><strong>{html.escape(name)}</strong> {'è stato consegnato' if delivered else 'è in viaggio verso di te'}.</p>"
    )
    if not delivered and order.tracking_number:
        body_html += f"<p>Numero di tracking: <strong>{html.escape(order.tracking_number)}</strong></p>"
    send_html_email_best_effort(
        context=f"AliExpress order shipping email (order={order.id}, delivered={delivered})",
        to=user.email,
        subject=f"{'Consegnato' if delivered else 'Spedito'}: {name} - Jav",
        html_body=render_email(
            preheader=title, heading=title, body_html=body_html,
            cta_label=None if delivered or not link else "Segui la spedizione",
            cta_url=None if delivered else link,
        ),
        text_body=title + (f" Tracking: {order.tracking_number}" if order.tracking_number and not delivered else ""),
    )
