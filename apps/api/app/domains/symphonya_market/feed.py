"""Il rifornimento del «Marketplace SYMPHONYA» dall'API di Symphonya (Session 89).

Symphonya (symphonya.eu) è un grossista B2B di profumi e cosmetici: 30.000
articoli, ciascuno un EAN. L'API, una chiave personale nell'URL
(`https://www.symphonya.eu/api/<procedura>/<chiave>`), ha le procedure:

- `getProducts` -- tutto il catalogo in JSON: id, ean, nome (inglese),
  marca, categoria/sottocategoria, sesso, formato («Regular», «Tester»…),
  `price` (il nostro costo, IVA esclusa), `rrp` (prezzo consigliato al
  pubblico, IVA inclusa; non sempre c'è), foto, scorte;
- `getStock` -- solo prezzi e scorte, più leggero;
- `getProductDetails` -- POST `ids=[…]` (JSON): descrizione, modo d'uso e il
  nome tradotto in 24 lingue, italiano compreso;
- `createOrder`, `getOrderStatus` -- ordini: non usati, gli ordini si
  inseriscono a mano su symphonya.eu (minimo d'ordine 99 €, bonifico
  anticipato, la merce arriva a noi).

L'import trasforma ogni articolo nella forma di una riga del feed di Vaitto
(un prodotto con una sola variante), così il resto -- prezzi, JavCash dal
guadagno, prodotti in perdita, categorie, marche -- è lo stesso codice del
Marketplace VAITTO. Le regole restano quelle:

- **un prodotto nuovo nasce spento**: si accende per marca o categoria;
- **il prezzo al cliente è l'`rrp` di Symphonya, IVA inclusa**; dove manca,
  il costo più il 40% e l'IVA; sopra, l'eventuale ricarico nostro;
- l'import aggiorna solo ciò che decide Symphonya (costo, listino, scorte)
  e mai nome, descrizione, stato, JavCash o ricarico;
- un articolo che non c'è più smette di essere comprabile, non si cancella;
- un catalogo troncato (meno della metà degli articoli noti) non spegne
  niente.

Nome italiano e descrizione si chiedono a `getProductDetails` solo per gli
articoli nuovi, a blocchi.
"""

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.marketplaces import rules
from app.domains.rbac.models import Role, UserRole
from app.domains.shop_categories.models import ShopCategory, ShopCategoryProduct
from app.domains.symphonya_market import service
from app.domains.symphonya_market.models import (
    SHOP,
    SymphonyaMarketProducer,
    SymphonyaMarketProduct,
    SymphonyaMarketVariant,
)

logger = logging.getLogger(__name__)


class _HideApiKey(logging.Filter):
    """La chiave API sta nell'URL di ogni chiamata, e httpx scrive ogni URL
    nei log a livello INFO: lì la chiave non deve comparire."""

    _pattern = re.compile(r"(symphonya\.eu/api/[A-Za-z]+/)[A-Za-z0-9]+")

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if "symphonya.eu/api/" in message:
            record.msg = self._pattern.sub(r"\1***", message)
            record.args = ()
        return True


logging.getLogger("httpx").addFilter(_HideApiKey())

API_BASE = "https://www.symphonya.eu/api"
MAX_FEED_BYTES = 80 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 240
#: Quanti prodotti per transazione: un import completo non tiene aperta una
#: transazione sola su migliaia di righe.
BATCH = 300
#: Quanti articoli per chiamata a getProductDetails, e quante chiamate per
#: import al massimo: Symphonya ha un limite di richieste («Rate limit
#: exceeded»), quindi si va piano e i dettagli mancanti si completano a ogni
#: import successivo.
DETAILS_BATCH = 50  # il massimo che Symphonya accetta
DETAILS_MAX_CALLS = 700
DETAILS_PAUSE_SECONDS = 2.0
#: Dove l'`rrp` manca: il costo più questo ricarico (come il ricarico base
#: di Vaitto), poi l'IVA.
FALLBACK_MARKUP_PERCENT = 40
#: Symphonya rifiuta le richieste senza un browser dichiarato (403).
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Jav/1.0)"}

CATEGORY_IT = {
    "Fragrance": "Profumi", "Makeup": "Trucco", "Hair": "Capelli", "Skin": "Cura del viso",
    "Body": "Corpo", "Room Scents": "Profumi per la casa", "Fashion": "Moda", "Oral Care": "Igiene orale",
    "Parapharmacy": "Parafarmacia", "Men": "Uomo", "Accessories": "Accessori",
    "Clothing": "Abbigliamento", "Health & Personal Care": "Salute e benessere", "Home": "Casa", "Pets": "Animali",
}
#: Le sottocategorie restano come le scrive Symphonya: il router delle marche
#: e categorie (GET /facets) chiede questa tabella come per Vaitto, e senza
#: rispondeva 500 (Session 90).
SUBCATEGORY_IT: dict[str, str] = {}
GENDER_IT = {"For Women": "Donna", "For Men": "Uomo", "Unisex": "Unisex", "For Children": "Bambini"}


class SymphonyaFeedError(Exception):
    """Un messaggio già scritto per l'amministratore, in italiano."""


# --- Lettura ---------------------------------------------------------------------------------------


def _url(procedure: str, api_key: str) -> str:
    return f"{API_BASE}/{procedure}/{api_key}"


def _unwrap(response: httpx.Response) -> object:
    if response.status_code in (401, 403):
        raise SymphonyaFeedError("Symphonya rifiuta la richiesta: controlla la chiave API nelle impostazioni.")
    if response.status_code != 200:
        raise SymphonyaFeedError(f"Symphonya ha risposto con l'errore {response.status_code}.")
    try:
        data = response.json()
    except ValueError as exc:
        raise SymphonyaFeedError("Symphonya non ha risposto in JSON: chiave API sbagliata?") from exc
    if not isinstance(data, dict) or data.get("error"):
        message = data.get("errorMessage") if isinstance(data, dict) else None
        raise SymphonyaFeedError(f"Symphonya: {message or 'risposta non valida'}.")
    return data.get("response")


async def download_feed(api_key: str) -> bytes:
    """Il catalogo intero (`getProducts`), così come arriva."""
    try:
        async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT_SECONDS, headers=HEADERS) as http:
            response = await http.get(_url("getProducts", api_key))
    except httpx.HTTPError as exc:
        raise SymphonyaFeedError(f"Symphonya non risponde: {type(exc).__name__}. Riprova più tardi.") from exc
    if len(response.content) > MAX_FEED_BYTES:
        raise SymphonyaFeedError("Il catalogo è troppo grande per essere letto.")
    _unwrap(response)
    return response.content


async def fetch_details(api_key: str, ids: list[str]) -> dict[str, dict]:
    """Nome italiano e descrizione degli articoli `ids`, a blocchi. Un blocco
    che fallisce si salta: l'articolo nasce con il nome inglese e senza
    descrizione, e resta spento comunque."""
    out: dict[str, dict] = {}
    chunks = [ids[start:start + DETAILS_BATCH] for start in range(0, len(ids), DETAILS_BATCH)][:DETAILS_MAX_CALLS]
    async with httpx.AsyncClient(timeout=120, headers=HEADERS) as http:
        for number, chunk in enumerate(chunks):
            payload = None
            for attempt in range(4):
                if number or attempt:
                    await asyncio.sleep(DETAILS_PAUSE_SECONDS * (1 if attempt == 0 else 10 * attempt))
                try:
                    response = await http.post(
                        _url("getProductDetails", api_key), data={"ids": json.dumps([int(i) for i in chunk])}
                    )
                    payload = _unwrap(response)
                    break
                except SymphonyaFeedError as exc:
                    if "rate limit" not in str(exc).lower():
                        logger.warning("Symphonya details batch %s failed: %s", number, exc)
                        break
                except (httpx.HTTPError, ValueError) as exc:
                    logger.warning("Symphonya details batch %s failed: %s", number, exc)
                    break
            for item in (payload or {}).get("results", []) if isinstance(payload, dict) else []:
                out[str(item.get("id"))] = item
    return out


def parse_feed(content: bytes) -> dict[str, list[dict]]:
    """Gli articoli del catalogo, ciascuno come «prodotto con una riga» nella
    forma del feed di Vaitto (vedi il docstring del modulo)."""
    try:
        data = json.loads(content)
    except ValueError as exc:
        raise SymphonyaFeedError("Il file non è il catalogo JSON di Symphonya (getProducts).") from exc
    items = data.get("response") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise SymphonyaFeedError("Il file non è il catalogo JSON di Symphonya (getProducts).")
    groups: dict[str, list[dict]] = {}
    for item in items:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        product_id = str(item["id"]).strip()
        groups[product_id] = [_row(item)]
    if not groups:
        raise SymphonyaFeedError("Il catalogo non contiene nessun prodotto.")
    return groups


def _row(item: dict) -> dict:
    cost = _cents(str(item.get("price") or ""))
    rrp = _cents(str(item.get("rrp") or ""))
    images = [item.get("image")] + [item.get(f"image-{n}") for n in range(1, 6)]
    presentation = (item.get("presentation") or "").strip()
    return {
        "product_id": str(item["id"]),
        "variant_id": str(item["id"]),
        "brand": (item.get("brand") or "").strip(),
        "product_name": (item.get("name") or "").strip(),
        "name_en": (item.get("name") or "").strip(),
        "description": "",
        "sku": (item.get("ean") or "").strip(),
        "barcode": (item.get("clean-ean") or item.get("ean") or "").strip(),
        "wholesale_price": item.get("price"),
        "rrp": item.get("rrp"),
        "suggested_cents": rrp or _fallback_price(cost),
        "stock_qty": item.get("stock"),
        "availability": item.get("availability") or "",
        "category": item.get("category") or "",
        "subcategory": item.get("subcategory") or "",
        "gender": GENDER_IT.get((item.get("gender") or "").strip(), ""),
        "presentation": "" if presentation in ("", "Regular") else presentation,
        "images": [u.strip() for u in images if u and str(u).strip().startswith("https://")],
    }


def _fallback_price(cost: int | None) -> int | None:
    """Senza `rrp`: costo + 40%, poi l'IVA al 22% (il prezzo al cliente è
    sempre IVA inclusa)."""
    if not cost:
        return None
    return (cost * (100 + FALLBACK_MARKUP_PERCENT) * 122 + 5000) // 10000


def _cents(value: str | None) -> int | None:
    try:
        amount = Decimal((value or "").strip())
    except InvalidOperation:
        return None
    return int((amount * 100).quantize(Decimal(1))) if amount > 0 else None


def _label(row: dict) -> str:
    return row.get("presentation") or "Unica"


def _images(row: dict) -> list[str]:
    return list(dict.fromkeys(row.get("images") or []))[:10]


def _sellable_at_symphonya(row: dict) -> bool:
    return (row.get("availability") or "").strip().lower() != "out of stock" and _stock(row) > 0


def _stock(row: dict) -> int:
    try:
        return max(int(float(row.get("stock_qty") or 0)), 0)
    except (TypeError, ValueError):
        return 0


def _suggested(row: dict) -> int | None:
    """Il prezzo al cliente, IVA inclusa: l'`rrp` di Symphonya, o il costo
    più il 40% e l'IVA dove l'`rrp` manca."""
    return row.get("suggested_cents")


def category_label(row: dict) -> str | None:
    main = (row.get("category") or "").strip()
    return CATEGORY_IT.get(main, main) or None


def _apply_details(row: dict, item: dict) -> None:
    """Nome italiano e descrizione (getProductDetails) sulla riga del
    catalogo; il nome inglese resta in `name_en`."""
    italian = ((item.get("localisation") or {}).get("it") or "").strip()
    if italian:
        row["product_name"] = italian
    description = item.get("description") or {}
    parts = [(description.get("short_description") or "").strip()]
    if (description.get("how_to_use") or "").strip():
        parts.append("Come si usa: " + description["how_to_use"].strip())
    row["description"] = "\n\n".join(p for p in parts if p)


async def _fill_details(db: AsyncSession, *, organization_id: uuid.UUID, groups: dict, keys: list[str]) -> int:
    """Completa i prodotti già importati senza descrizione: la descrizione,
    e il nome italiano solo se il nome è ancora quello inglese di Symphonya
    (uno scritto dall'amministratore non si tocca)."""
    if not keys:
        return 0
    filled = 0
    products = (await db.execute(
        select(SymphonyaMarketProduct).where(
            SymphonyaMarketProduct.organization_id == organization_id,
            SymphonyaMarketProduct.symphonya_product_id.in_(keys),
        )
    )).scalars().all()
    for product in products:
        row = groups[product.symphonya_product_id][0]
        if not row.get("description") or product.description:
            continue
        product.description = row["description"][:8000]
        if product.name == (row.get("name_en") or "")[:255] and row.get("product_name"):
            product.name = row["product_name"][:255]
        filled += 1
    await db.commit()
    return filled


# --- Applicazione ----------------------------------------------------------------------------------


async def _system_actor(db: AsyncSession, organization_id: uuid.UUID) -> uuid.UUID:
    """Chi «crea» i prodotti di un import automatico: il primo
    amministratore dell'organizzazione. La colonna è obbligatoria, e un
    import notturno non ha un utente davanti."""
    found = await db.execute(
        select(UserRole.user_id)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.organization_id == organization_id, Role.code.in_(("SUPER_ADMIN", "ADMIN")))
        .order_by(UserRole.created_at)
        .limit(1)
    )
    user_id = found.scalar_one_or_none()
    if user_id is None:
        raise SymphonyaFeedError("Nessun amministratore a cui intestare i prodotti importati.")
    return user_id


async def import_feed(
    db: AsyncSession, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID | None = None,
    content: bytes | None = None,
) -> dict:
    """Legge il catalogo (dall'API o da `content`, un JSON di getProducts) e
    aggiorna il negozio. Restituisce il riepilogo, che resta anche sulle
    impostazioni."""
    settings = await service.get_settings_row(db, organization_id=organization_id)
    try:
        if content is None:
            if not settings.api_key:
                raise SymphonyaFeedError("Manca la chiave API di Symphonya nelle impostazioni.")
            content = await download_feed(settings.api_key)
        groups = parse_feed(content)
        lacking: list[str] = []
        if settings.api_key:
            known = dict(
                (await db.execute(
                    select(SymphonyaMarketProduct.symphonya_product_id, SymphonyaMarketProduct.description).where(
                        SymphonyaMarketProduct.organization_id == organization_id,
                        SymphonyaMarketProduct.symphonya_product_id.is_not(None),
                    )
                )).all()
            )
            fresh = [key for key in groups if key not in known]
            # Dettagli rifiutati in un import precedente (limite di richieste):
            # si completano adesso, dopo i nuovi.
            lacking = [key for key, description in known.items() if not description and key in groups]
            wanted = fresh + lacking
            details = await fetch_details(settings.api_key, wanted) if wanted else {}
            for key, item in details.items():
                if key in groups:
                    _apply_details(groups[key][0], item)
        summary = await _apply(
            db, settings=settings, groups=groups,
            actor_user_id=actor_user_id or await _system_actor(db, organization_id),
        )
        filled = await _fill_details(db, organization_id=organization_id, groups=groups, keys=lacking)
        if filled:
            summary["text"] += f" Nome italiano e descrizione aggiunti a {filled} prodotti."
    except SymphonyaFeedError as exc:
        await db.rollback()
        settings = await service.get_settings_row(db, organization_id=organization_id)
        settings.last_import_at = utcnow()
        settings.last_import_error = str(exc)[:500]
        await db.commit()
        raise
    settings = await service.get_settings_row(db, organization_id=organization_id)
    settings.last_import_at = utcnow()
    settings.last_import_error = None
    settings.last_import_summary = summary["text"][:500]
    await db.commit()
    return summary


async def _apply(
    db: AsyncSession, *, settings, groups: dict[str, list[dict]], actor_user_id: uuid.UUID
) -> dict:
    organization_id = settings.organization_id
    now = utcnow()
    existing = {
        p.symphonya_product_id: p
        for p in (await db.execute(
            select(SymphonyaMarketProduct).where(
                SymphonyaMarketProduct.organization_id == organization_id,
                SymphonyaMarketProduct.symphonya_product_id.is_not(None),
            )
        )).scalars().all()
    }
    variants_by_product, _ = await service._preload(db, list(existing.values()))
    producers = {p.name: p for p in await service.list_producers(db, organization_id=organization_id)}
    categories = {
        c.name: c
        for c in (await db.execute(
            select(ShopCategory).where(ShopCategory.organization_id == organization_id, ShopCategory.shop == SHOP)
        )).scalars().all()
    }

    vat = await rules.get_vat_percentage(db, organization_id=organization_id)
    # Session 89: i prezzi al cliente di Symphonya (rrp, o costo + 40% + IVA)
    # sono sempre IVA inclusa.
    settings.prices_include_vat = True
    created = updated = skipped = 0
    for index, (symphonya_id, rows) in enumerate(groups.items(), 1):
        first = rows[0]
        product = existing.get(symphonya_id)
        costs = [_cents(str(r.get("wholesale_price") or "")) for r in rows]
        if not any(costs):
            skipped += 1
            continue

        brand = (first.get("brand") or "").strip()
        producer = None
        if brand and brand.lower() != "unknown":
            producer = producers.get(brand[:160])
            if producer is None:
                producer = SymphonyaMarketProducer(
                    organization_id=organization_id, name=brand[:160], created_by_user_id=actor_user_id,
                    description="",
                )
                db.add(producer)
                await db.flush()
                producers[producer.name] = producer

        if product is None:
            images = _images(first)
            product = SymphonyaMarketProduct(
                organization_id=organization_id, created_by_user_id=actor_user_id,
                symphonya_product_id=symphonya_id,
                name=(first.get("product_name") or "").strip()[:255] or symphonya_id,
                description=(first.get("description") or "").strip()[:8000],
                image_url=images[0] if images else None, images=images,
                status="INACTIVE",
                # La percentuale JavCash del negozio (Session 88).
                credit_discount_percentage=settings.credit_percentage,
                producer_id=producer.id if producer else None,
            )
            db.add(product)
            await db.flush()
            variants_by_product[product.id] = []
            created += 1
            label = category_label(first)
            if label:
                category = categories.get(label[:120])
                if category is None:
                    category = ShopCategory(
                        organization_id=organization_id, shop=SHOP, name=label[:120],
                        position=len(categories), active=True,
                    )
                    db.add(category)
                    await db.flush()
                    categories[category.name] = category
                db.add(ShopCategoryProduct(
                    organization_id=organization_id, category_id=category.id, shop=SHOP, product_id=product.id,
                ))
        else:
            updated += 1
            if product.producer_id is None and producer is not None:
                product.producer_id = producer.id

        product.category_name = (first.get("category") or "").strip()[:64] or None
        product.subcategory = (first.get("subcategory") or "").strip()[:64] or None
        product.gender = (first.get("gender") or "").strip()[:16] or None
        product.source_url = None
        product.missing_from_feed = False
        product.last_synced_at = now

        markup = service.effective_markup(product, settings)
        known = {v.symphonya_variant_id: v for v in variants_by_product[product.id]}
        skus = {v.sku for v in variants_by_product[product.id] if v.sku}
        seen: set[str] = set()
        for row, cost in zip(rows, costs):
            variant_id = row["variant_id"].strip()
            if not cost or variant_id in seen:
                continue
            seen.add(variant_id)
            variant = known.get(variant_id)
            if variant is None:
                sku = (row.get("sku") or "").strip()[:128] or None
                if sku in skus:
                    sku = None
                skus.add(sku)
                variant = SymphonyaMarketVariant(
                    product_id=product.id, symphonya_variant_id=variant_id, label=_label(row)[:255], sku=sku,
                    image_url=(_images(row) or [None])[0],
                    price_cents=service.sale_price_cents(_suggested(row) or cost, markup),
                    active=True,
                )
                db.add(variant)
                variants_by_product[product.id].append(variant)
            variant.cost_cents = cost
            variant.suggested_price_cents = _suggested(row)
            variant.compare_at_cents = _cents(str(row.get("rrp") or ""))
            variant.barcode = (row.get("barcode") or "").strip()[:32] or None
            variant.inventory = _stock(row)
            variant.available_in_store = _sellable_at_symphonya(row)
            service.reprice_variant(variant, markup=markup)
        for variant in variants_by_product[product.id]:
            if variant.symphonya_variant_id and variant.symphonya_variant_id not in seen:
                variant.available_in_store = False
        # Session 88: con la regola «dal guadagno» la percentuale JavCash segue
        # costo e prezzo di questo import.
        service.apply_credit_rule(product, variants_by_product[product.id], settings, vat)

        if index % BATCH == 0:
            await db.commit()

    # I prodotti che il feed non porta più: non comprabili, non cancellati.
    gone = [p for key, p in existing.items() if key not in groups]
    truncated = len(existing) >= 20 and len(groups) < len(existing) / 2
    if not truncated:
        for product in gone:
            product.missing_from_feed = True
            for variant in variants_by_product.get(product.id, []):
                variant.available_in_store = False
    await db.commit()

    text = (
        f"{len(groups)} prodotti nel catalogo Symphonya: {created} nuovi (spenti), {updated} aggiornati"
        + (f", {skipped} senza prezzo saltati" if skipped else "")
        + (
            f", {len(gone)} non più nel feed e resi non comprabili" if gone and not truncated
            else f"; ATTENZIONE: il feed porta meno della metà dei prodotti noti, {len(gone)} mancanti "
                 "lasciati come erano" if gone else ""
        )
        + "."
    )
    return {
        "products_in_feed": len(groups), "created": created, "updated": updated, "skipped": skipped,
        "gone": len(gone), "truncated": truncated, "text": text,
    }


async def bulk_set_status(
    db: AsyncSession, *, organization_id: uuid.UUID, status: str,
    producer_id: uuid.UUID | None = None, subcategory: str | None = None, category_name: str | None = None,
) -> int:
    """Accende o spegne in blocco: tutti i prodotti di una marca, di una
    categoria, o di entrambe. Senza filtri non fa niente -- «accendi tutto»
    deve essere una scelta esplicita per marca o categoria, non un clic
    sbagliato su 3.500 prodotti."""
    if status not in ("ACTIVE", "INACTIVE"):
        raise service.SymphonyaMarketValidationError("Stato non valido.")
    if producer_id is None and not subcategory and not category_name:
        raise service.SymphonyaMarketValidationError("Scegli una marca o una categoria.")
    query = select(SymphonyaMarketProduct).where(SymphonyaMarketProduct.organization_id == organization_id)
    if producer_id is not None:
        query = query.where(SymphonyaMarketProduct.producer_id == producer_id)
    if subcategory:
        query = query.where(SymphonyaMarketProduct.subcategory == subcategory)
    if category_name:
        query = query.where(SymphonyaMarketProduct.category_name == category_name)
    products = list((await db.execute(query)).scalars().all())
    now: datetime = utcnow()
    for product in products:
        product.status = status
        product.updated_at = now
    await db.commit()
    return len(products)
