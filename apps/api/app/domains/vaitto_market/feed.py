"""Il rifornimento del «Marketplace VAITTO» dal feed di Vaitto (Session 88).

Vaitto pubblica il suo catalogo come «universal.csv»: una riga per variante
(taglia × colore), raggruppate in prodotti da `product_id`. Lo si legge
dall'URL del feed (che porta la chiave API) oppure da un file caricato a
mano nello stesso formato -- la strada è la stessa, cambia solo da dove
arrivano i byte.

Regole, scelte con l'utente:

- **un prodotto nuovo nasce spento** (INACTIVE): 3.500 articoli di lusso non
  vanno in vetrina senza che qualcuno li guardi; si accendono per marca o
  categoria dal pannello;
- **il prezzo è il suggerito da Vaitto × il nostro ricarico** (di norma 0,
  `service.sale_price_cents`; il costo resta per l'amministratore), rifatto a
  ogni import salvo che l'amministratore l'abbia scritto a mano;
- l'import aggiorna **solo ciò che decide Vaitto** -- costo, listino, scorte,
  disponibilità, categoria -- e mai nome, descrizione, foto scelte, stato,
  JavCash o ricarico del prodotto;
- una variante o un prodotto che non c'è più nel feed **smette di essere
  comprabile** ma non si cancella: gli ordini vecchi la citano, e se Vaitto
  lo rimette in catalogo torna da solo.

Un feed troncato (un download interrotto, un errore dal lato di Vaitto) non
deve spegnere mezzo catalogo: se porta meno della metà dei prodotti che
conosciamo, i mancanti non si toccano e il riepilogo lo dice.
"""

import csv
import io
import logging
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
from app.domains.vaitto_market import service
from app.domains.vaitto_market.models import (
    SHOP,
    VaittoMarketProducer,
    VaittoMarketProduct,
    VaittoMarketVariant,
)

logger = logging.getLogger(__name__)

MAX_FEED_BYTES = 60 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 180
#: Quanti prodotti per transazione: un import completo non tiene aperta una
#: transazione sola su migliaia di righe.
BATCH = 300

REQUIRED_COLUMNS = {
    "product_id", "variant_id", "brand", "product_name", "sku",
    "wholesale_price", "stock_qty", "availability",
}

#: Le sottocategorie di Vaitto come le legge il cliente. Una sottocategoria
#: nuova, non ancora qui, resta in inglese finché qualcuno non la aggiunge.
SUBCATEGORY_IT = {
    "Belts": "Cinture", "Blankets": "Plaid", "Gloves": "Guanti", "Hats": "Cappelli",
    "Scarves": "Sciarpe", "Sunglasses": "Occhiali da sole", "Ties": "Cravatte", "Wallets": "Portafogli",
    "Backpack": "Zaini", "Clutch": "Pochette", "Crossbody": "Borse a tracolla", "Handbags": "Borse a mano",
    "Shoulder": "Borse a spalla", "Tote": "Shopper", "Blazers": "Blazer", "Bodysuits": "Body",
    "Coats": "Cappotti", "Down Jackets": "Piumini", "Dresses": "Abiti", "Hoodies": "Felpe con cappuccio",
    "Hosiery": "Calze", "Jackets": "Giacche", "Jeans": "Jeans", "Jumpsuits": "Tute intere",
    "Knitwear": "Maglieria", "Leggings": "Leggings", "Pants": "Pantaloni", "Parka": "Parka",
    "Polo Shirts": "Polo", "Shirts": "Camicie", "Shorts": "Shorts", "Skirts": "Gonne", "Suits": "Completi",
    "Sweatshirts": "Felpe", "Swimwear": "Costumi", "T-shirts & Tops": "T-shirt e top",
    "Tracksuits": "Tute", "Trench": "Trench", "Underwear": "Intimo", "Vests": "Gilet",
    "Boots": "Stivali", "Flats": "Ballerine", "Heels": "Scarpe con tacco", "Loafers": "Mocassini",
    "Sandals": "Sandali", "Slides": "Ciabatte", "Sneakers": "Sneakers",
}
CATEGORY_IT = {"Clothing": "Abbigliamento", "Shoes": "Scarpe", "Bags": "Borse", "Accessories": "Accessori"}
COLOUR_IT = {
    "Black": "Nero", "Blue": "Blu", "White": "Bianco", "Brown": "Marrone", "Beige": "Beige", "Gray": "Grigio",
    "Grey": "Grigio", "Pink": "Rosa", "Green": "Verde", "Red": "Rosso", "Yellow": "Giallo", "Orange": "Arancione",
    "Ivory": "Avorio", "Purple": "Viola", "Silver": "Argento", "Gold": "Oro", "Multicolor": "Multicolore",
}


class VaittoFeedError(Exception):
    """Un messaggio già scritto per l'amministratore, in italiano."""


# --- Lettura ---------------------------------------------------------------------------------------


async def download_feed(url: str) -> bytes:
    try:
        async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True) as http:
            response = await http.get(url)
    except httpx.HTTPError as exc:
        raise VaittoFeedError(f"Vaitto non risponde: {type(exc).__name__}. Riprova più tardi.") from exc
    if response.status_code in (401, 403):
        raise VaittoFeedError("Vaitto rifiuta la chiave del feed: controlla l'indirizzo nelle impostazioni.")
    if response.status_code != 200:
        raise VaittoFeedError(f"Vaitto ha risposto con l'errore {response.status_code}.")
    if len(response.content) > MAX_FEED_BYTES:
        raise VaittoFeedError("Il feed è troppo grande per essere letto.")
    return response.content


def parse_feed(content: bytes) -> dict[str, list[dict]]:
    """Le righe del CSV raggruppate per prodotto, nell'ordine del file."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise VaittoFeedError("Il file non è un CSV in UTF-8 come quello di Vaitto.") from exc
    reader = csv.DictReader(io.StringIO(text))
    missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
    if missing:
        raise VaittoFeedError(
            "Il file non è nel formato «universal» di Vaitto: mancano le colonne " + ", ".join(sorted(missing)) + "."
        )
    groups: dict[str, list[dict]] = {}
    for row in reader:
        product_id = (row.get("product_id") or "").strip()
        if product_id and (row.get("variant_id") or "").strip():
            groups.setdefault(product_id, []).append(row)
    if not groups:
        raise VaittoFeedError("Il feed non contiene nessun prodotto.")
    return groups


def _cents(value: str | None) -> int | None:
    try:
        amount = Decimal((value or "").strip())
    except InvalidOperation:
        return None
    return int((amount * 100).quantize(Decimal(1))) if amount > 0 else None


def _label(row: dict) -> str:
    size = (row.get("size") or "").strip()
    colour = (row.get("colour") or "").strip()
    parts = []
    if size:
        parts.append("Taglia unica" if size.lower() in ("one size", "os", "unica") else f"Taglia {size}")
    if colour:
        parts.append(COLOUR_IT.get(colour, colour))
    return " · ".join(parts) or "Unica"


def _images(row: dict) -> list[str]:
    urls = [row.get("image_url"), row.get("image_url_2")]
    urls += (row.get("additional_image_urls") or "").split("|")
    return list(dict.fromkeys(u.strip() for u in urls if u and u.strip().startswith("https://")))[:10]


def _sellable_at_vaitto(row: dict) -> bool:
    return (
        (row.get("availability") or "").strip().lower() != "out of stock"
        and (row.get("dropship_available") or "true").strip().lower() == "true"
    )


def _stock(row: dict) -> int:
    try:
        return max(int(float(row.get("stock_qty") or 0)), 0)
    except ValueError:
        return 0


def _price_basis(groups: dict[str, list[dict]]) -> bool | None:
    """True se il feed è al prezzo del marchio (IVA inclusa), False se è al
    ricarico (IVA esclusa), None se non lo dice o è misto."""
    values = {
        (row.get("price_basis") or "").strip().lower() for rows in groups.values() for row in rows
    } - {""}
    if not values:
        return None
    if all("rrp" in v for v in values):
        return True
    if all("rrp" not in v for v in values):
        return False
    return None


def _suggested(row: dict) -> int | None:
    """Il prezzo al cliente che Vaitto ci propone. Dalla Session 88 la colonna
    giusta è `your_price` -- il prezzo che l'utente sceglie nel suo account
    Vaitto (ricarico, oppure «Sell at brand RRP» con o senza sconto), come ha
    spiegato il supporto di Vaitto. `retail_price` resta per i feed di prima,
    dove era lo stesso numero calcolato dal ricarico."""
    return _cents(row.get("your_price")) or _cents(row.get("retail_price"))


def category_label(row: dict) -> str | None:
    sub = (row.get("subcategory") or "").strip()
    if sub:
        return SUBCATEGORY_IT.get(sub, sub)
    main = (row.get("category") or "").strip()
    return CATEGORY_IT.get(main, main) or None


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
        raise VaittoFeedError("Nessun amministratore a cui intestare i prodotti importati.")
    return user_id


async def import_feed(
    db: AsyncSession, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID | None = None,
    content: bytes | None = None,
) -> dict:
    """Legge il feed (dall'URL o da `content`) e aggiorna il catalogo.
    Restituisce il riepilogo, che resta anche sulle impostazioni."""
    settings = await service.get_settings_row(db, organization_id=organization_id)
    try:
        if content is None:
            if not settings.feed_url:
                raise VaittoFeedError("Manca l'indirizzo del feed Vaitto nelle impostazioni.")
            content = await download_feed(settings.feed_url)
        groups = parse_feed(content)
        summary = await _apply(
            db, settings=settings, groups=groups,
            actor_user_id=actor_user_id or await _system_actor(db, organization_id),
        )
    except VaittoFeedError as exc:
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
        p.vaitto_product_id: p
        for p in (await db.execute(
            select(VaittoMarketProduct).where(
                VaittoMarketProduct.organization_id == organization_id,
                VaittoMarketProduct.vaitto_product_id.is_not(None),
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
    # Session 88: il feed dice da sé se `your_price` è il prezzo del marchio
    # (IVA dentro) o il prezzo dal ricarico (senza IVA, come tutti i prezzi di
    # Vaitto). L'utente ha scelto il prezzo del marchio sul suo account, ma
    # finché Vaitto non lo applica il feed resta «markup»: leggere quei prezzi
    # come IVA inclusa darebbe margini falsi e prodotti in perdita che non lo
    # sono. La casella nel pannello vale solo per un CSV senza la colonna.
    basis = _price_basis(groups)
    if basis is not None and settings.prices_include_vat != basis:
        settings.prices_include_vat = basis
    created = updated = skipped = 0
    for index, (vaitto_id, rows) in enumerate(groups.items(), 1):
        first = rows[0]
        product = existing.get(vaitto_id)
        costs = [_cents(r.get("wholesale_price")) for r in rows]
        if not any(costs):
            skipped += 1
            continue

        brand = (first.get("brand") or "").strip()
        producer = None
        if brand and brand.lower() != "unknown":
            producer = producers.get(brand[:160])
            if producer is None:
                producer = VaittoMarketProducer(
                    organization_id=organization_id, name=brand[:160], created_by_user_id=actor_user_id,
                    description="",
                )
                db.add(producer)
                await db.flush()
                producers[producer.name] = producer

        if product is None:
            images = _images(first)
            product = VaittoMarketProduct(
                organization_id=organization_id, created_by_user_id=actor_user_id,
                vaitto_product_id=vaitto_id,
                name=(first.get("product_name") or "").strip()[:255] or vaitto_id,
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
        product.source_url = (first.get("vaitto_product_url") or "").strip()[:1000] or None
        product.missing_from_feed = False
        product.last_synced_at = now

        markup = service.effective_markup(product, settings)
        known = {v.vaitto_variant_id: v for v in variants_by_product[product.id]}
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
                variant = VaittoMarketVariant(
                    product_id=product.id, vaitto_variant_id=variant_id, label=_label(row)[:255], sku=sku,
                    image_url=(_images(row) or [None])[0],
                    price_cents=service.sale_price_cents(_suggested(row) or cost, markup),
                    active=True,
                )
                db.add(variant)
                variants_by_product[product.id].append(variant)
            variant.cost_cents = cost
            variant.suggested_price_cents = _suggested(row)
            variant.compare_at_cents = _cents(row.get("rrp")) or _cents(row.get("compare_at_price"))
            variant.barcode = (row.get("barcode") or "").strip()[:32] or None
            variant.inventory = _stock(row)
            variant.available_in_store = _sellable_at_vaitto(row)
            service.reprice_variant(variant, markup=markup)
        for variant in variants_by_product[product.id]:
            if variant.vaitto_variant_id and variant.vaitto_variant_id not in seen:
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
        ("Prezzi del marchio, IVA inclusa. " if settings.prices_include_vat else "Prezzi dal ricarico, IVA esclusa. ")
        + f"{len(groups)} prodotti nel feed: {created} nuovi (spenti), {updated} aggiornati"
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
        raise service.VaittoMarketValidationError("Stato non valido.")
    if producer_id is None and not subcategory and not category_name:
        raise service.VaittoMarketValidationError("Scegli una marca o una categoria.")
    query = select(VaittoMarketProduct).where(VaittoMarketProduct.organization_id == organization_id)
    if producer_id is not None:
        query = query.where(VaittoMarketProduct.producer_id == producer_id)
    if subcategory:
        query = query.where(VaittoMarketProduct.subcategory == subcategory)
    if category_name:
        query = query.where(VaittoMarketProduct.category_name == category_name)
    products = list((await db.execute(query)).scalars().all())
    now: datetime = utcnow()
    for product in products:
        product.status = status
        product.updated_at = now
    await db.commit()
    return len(products)
