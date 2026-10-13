"""Il rifornimento del «Marketplace SOLEIL» dal catalogo di SoleilDrop (Session 90).

SoleilDrop (soleildrop.com) è un gestionale B2B con un portale per gli
affiliati in dropshipping: l'affiliato sceglie le referenze, fissa il suo
prezzo di vendita, e gli ordini li spedisce SoleilDrop al cliente. Un'API da
leggere non c'è (il suo «connettore» spinge il catalogo dentro un PrestaShop
o un WooCommerce, che noi non siamo). Il catalogo quindi arriva dal file
**Excel di «Il Mio Catalogo → Esporta → Excel generico (.xlsx)»**, caricato a
mano dal pannello, con le colonne:

    Codice, Nome, Marca, EAN, Categoria («A > B > C»), Prezzo Soleil (il
    nostro costo, IVA esclusa), Prezzo vendita (imponibile), IVA %, Prezzo
    vendita (ivato), Peso kg, Unità, Pubblicato, Disponibile («Sì»/«No»),
    Descrizione breve, Descrizione, Meta title, Meta description, Immagini
    (link separati da virgole)

Lo stesso file salvato come CSV va bene uguale. Ogni referenza diventa un
prodotto con una sola variante, nella forma di una riga del feed di Vaitto,
così il resto -- prezzi, JavCash dal guadagno, prodotti in perdita,
categorie, marche -- è lo stesso codice di «Shop Beauty» (Symphonya). Le
regole restano quelle (scelta dell'utente: «uguali per tutti i negozi»):

- **un prodotto nuovo nasce spento**: si accende per marca o categoria;
- **il prezzo al cliente è il «Prezzo vendita (ivato)»** del file, cioè il
  prezzo che l'affiliato ha messo nel portale; dove manca o è zero, il
  costo più il 40% e l'IVA; sopra, l'eventuale ricarico nostro;
- l'import aggiorna solo ciò che decide SoleilDrop (costo, listino,
  disponibilità) e mai nome, descrizione, stato, JavCash o ricarico;
- un articolo che non c'è più smette di essere comprabile, non si cancella;
- un catalogo troncato (meno della metà degli articoli noti) non spegne
  niente: per questo nel portale va esportato «Tutte quelle in elenco».
"""

import csv
import io
import logging
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.marketplaces import rules
from app.domains.rbac.models import Role, UserRole
from app.domains.shop_categories.models import ShopCategory, ShopCategoryProduct
from app.domains.soleil_market import service
from app.domains.soleil_market.models import (
    SHOP,
    SoleilMarketProducer,
    SoleilMarketProduct,
    SoleilMarketVariant,
)

logger = logging.getLogger(__name__)

MAX_FEED_BYTES = 80 * 1024 * 1024
#: Quanti prodotti per transazione: un import completo non tiene aperta una
#: transazione sola su migliaia di righe.
BATCH = 300
#: Dove il prezzo di vendita manca: il costo più questo ricarico (come il
#: ricarico base di Vaitto e Symphonya), poi l'IVA.
FALLBACK_MARKUP_PERCENT = 40
#: Le colonne senza le quali il file non è l'export di SoleilDrop.
REQUIRED_COLUMNS = ("Codice", "Nome", "Prezzo Soleil")
#: Le categorie del file sono già in italiano (sono quelle dell'affiliato):
#: niente da tradurre, ma il router delle marche/categorie la chiede.
SUBCATEGORY_IT: dict[str, str] = {}


class SoleilFeedError(Exception):
    """Un messaggio già scritto per l'amministratore, in italiano."""


# --- Lettura ---------------------------------------------------------------------------------------


def _xlsx_rows(content: bytes) -> list[list[object]]:
    from openpyxl import load_workbook

    try:
        book = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:  # openpyxl solleva tipi diversi per file rotti
        raise SoleilFeedError("Il file Excel non si apre: è rovinato o non è un .xlsx.") from exc
    try:
        sheet = book["Catalogo"] if "Catalogo" in book.sheetnames else book.worksheets[0]
        return [list(row) for row in sheet.iter_rows(values_only=True)]
    finally:
        book.close()


def _csv_rows(content: bytes) -> list[list[object]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("cp1252", errors="replace")
    first = text.split("\n", 1)[0]
    delimiter = max((";", ",", "\t"), key=first.count)
    return [list(row) for row in csv.reader(io.StringIO(text), delimiter=delimiter)]


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        # Un EAN in una cella numerica arriva come 8001234567890.0.
        return str(int(value))
    return str(value).strip()


def parse_feed(content: bytes) -> dict[str, list[dict]]:
    """Le referenze del file, ciascuna come «prodotto con una riga» nella
    forma del feed di Vaitto (vedi il docstring del modulo)."""
    # Un .xlsx è uno zip: comincia sempre con «PK». Tutto il resto è CSV.
    rows = _xlsx_rows(content) if content[:2] == b"PK" else _csv_rows(content)
    header_index = next(
        (i for i, row in enumerate(rows[:10]) if {_text(c) for c in row} >= set(REQUIRED_COLUMNS)), None
    )
    if header_index is None:
        raise SoleilFeedError(
            "Il file non è l'Excel del catalogo SoleilDrop: servono le colonne "
            + ", ".join(f"«{c}»" for c in REQUIRED_COLUMNS)
            + ". Nel portale: Il Mio Catalogo → Esporta → Excel generico (.xlsx)."
        )
    header = [_text(c) for c in rows[header_index]]
    groups: dict[str, list[dict]] = {}
    for raw in rows[header_index + 1:]:
        record = {name: _text(raw[i]) if i < len(raw) else "" for i, name in enumerate(header) if name}
        key = (record.get("Codice") or record.get("EAN") or "").strip()[:64]
        if not key or key in groups:
            continue
        groups[key] = [_row(key, record)]
    if not groups:
        raise SoleilFeedError("Il file non contiene nessuna referenza.")
    return groups


def _row(key: str, record: dict) -> dict:
    cost = _cents(record.get("Prezzo Soleil"))
    gross = _cents(record.get("Prezzo vendita (ivato)"))
    path = [p.strip() for p in (record.get("Categoria") or "").split(">") if p.strip()]
    unit = (record.get("Unità") or "").strip()
    short = (record.get("Descrizione breve") or "").strip()
    long = (record.get("Descrizione") or "").strip()
    return {
        "product_id": key,
        "variant_id": key,
        "brand": (record.get("Marca") or "").strip(),
        "product_name": (record.get("Nome") or "").strip(),
        "description": long or short,
        "sku": key,
        "barcode": (record.get("EAN") or "").strip(),
        "wholesale_price": record.get("Prezzo Soleil"),
        "rrp": record.get("Prezzo vendita (ivato)"),
        "suggested_cents": gross or _fallback_price(cost),
        "available": (record.get("Disponibile") or "").strip().lower() not in ("no", "0", "false"),
        "category": path[0] if path else "",
        "subcategory": path[-1] if len(path) > 1 else "",
        # «PZ» è il pezzo singolo; un'altra unità (cartone, strato) si dice
        # nell'etichetta della variante, così il cliente sa cosa compra.
        "presentation": "" if unit in ("", "PZ") or unit.startswith("PZ+") else unit,
        "images": [
            u.strip() for u in (record.get("Immagini") or "").split(",") if u.strip().startswith("https://")
        ],
    }


def _fallback_price(cost: int | None) -> int | None:
    """Senza prezzo di vendita: costo + 40%, poi l'IVA al 22% (il prezzo al
    cliente è sempre IVA inclusa)."""
    if not cost:
        return None
    return (cost * (100 + FALLBACK_MARKUP_PERCENT) * 122 + 5000) // 10000


def _cents(value: object) -> int | None:
    """Un importo del file in centesimi: 12.5, «12,50», «€ 1.234,56»."""
    text = _text(value).replace("€", "").replace(" ", "")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return None
    return int((amount * 100).quantize(Decimal(1))) if amount > 0 else None


def _label(row: dict) -> str:
    return row.get("presentation") or "Unica"


def _images(row: dict) -> list[str]:
    return list(dict.fromkeys(row.get("images") or []))[:10]


def _sellable_at_soleil(row: dict) -> bool:
    return bool(row.get("available"))


def _stock(row: dict) -> int | None:
    """Il file non dice quanti pezzi ci sono, solo se la referenza è
    disponibile: disponibile = nessun limite (None), altrimenti 0."""
    return None if row.get("available") else 0


def _suggested(row: dict) -> int | None:
    """Il prezzo al cliente, IVA inclusa: il prezzo di vendita ivato del
    file, o il costo più il 40% e l'IVA dove manca."""
    return row.get("suggested_cents")


def category_label(row: dict) -> str | None:
    return (row.get("category") or "").strip() or None


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
        raise SoleilFeedError("Nessun amministratore a cui intestare i prodotti importati.")
    return user_id


async def import_feed(
    db: AsyncSession, *, organization_id: uuid.UUID, content: bytes, actor_user_id: uuid.UUID | None = None,
) -> dict:
    """Legge il file del catalogo (`content`, l'Excel o il CSV di SoleilDrop)
    e aggiorna il negozio. Restituisce il riepilogo, che resta anche sulle
    impostazioni."""
    settings = await service.get_settings_row(db, organization_id=organization_id)
    try:
        groups = parse_feed(content)
        summary = await _apply(
            db, settings=settings, groups=groups,
            actor_user_id=actor_user_id or await _system_actor(db, organization_id),
        )
    except SoleilFeedError as exc:
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
    db: AsyncSession, *, settings, groups: dict[str, list[dict]], actor_user_id: uuid.UUID,
    allow_gone: bool = True, source: str = "catalogo SoleilDrop",
) -> dict:
    organization_id = settings.organization_id
    now = utcnow()
    existing = {
        p.soleil_product_id: p
        for p in (await db.execute(
            select(SoleilMarketProduct).where(
                SoleilMarketProduct.organization_id == organization_id,
                SoleilMarketProduct.soleil_product_id.is_not(None),
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
    # I prezzi al cliente di SoleilDrop (il prezzo ivato, o costo + 40% + IVA)
    # sono sempre IVA inclusa.
    settings.prices_include_vat = True
    created = updated = skipped = 0
    for index, (soleil_id, rows) in enumerate(groups.items(), 1):
        first = rows[0]
        product = existing.get(soleil_id)
        costs = [_cents(str(r.get("wholesale_price") or "")) for r in rows]
        if not any(costs):
            skipped += 1
            continue

        brand = (first.get("brand") or "").strip()
        producer = None
        if brand and brand.lower() != "unknown":
            producer = producers.get(brand[:160])
            if producer is None:
                producer = SoleilMarketProducer(
                    organization_id=organization_id, name=brand[:160], created_by_user_id=actor_user_id,
                    description="",
                )
                db.add(producer)
                await db.flush()
                producers[producer.name] = producer

        if product is None:
            images = _images(first)
            product = SoleilMarketProduct(
                organization_id=organization_id, created_by_user_id=actor_user_id,
                soleil_product_id=soleil_id,
                name=(first.get("product_name") or "").strip()[:255] or soleil_id,
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
        product.source_url = None
        product.missing_from_feed = False
        product.last_synced_at = now

        markup = service.effective_markup(product, settings)
        known = {v.soleil_variant_id: v for v in variants_by_product[product.id]}
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
                variant = SoleilMarketVariant(
                    product_id=product.id, soleil_variant_id=variant_id, label=_label(row)[:255], sku=sku,
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
            variant.available_in_store = _sellable_at_soleil(row)
            service.reprice_variant(variant, markup=markup)
        for variant in variants_by_product[product.id]:
            if variant.soleil_variant_id and variant.soleil_variant_id not in seen:
                variant.available_in_store = False
        # Session 88: con la regola «dal guadagno» la percentuale JavCash segue
        # costo e prezzo di questo import.
        service.apply_credit_rule(product, variants_by_product[product.id], settings, vat)

        if index % BATCH == 0:
            await db.commit()

    # I prodotti che il feed non porta più: non comprabili, non cancellati.
    gone = [p for key, p in existing.items() if key not in groups]
    # `allow_gone` falso: chi chiama sa già che le referenze non sono tutte
    # (l'API ne ha date meno di quante ne elenca), e allora non si spegne niente.
    truncated = not allow_gone or (len(existing) >= 20 and len(groups) < len(existing) / 2)
    if not truncated:
        for product in gone:
            product.missing_from_feed = True
            for variant in variants_by_product.get(product.id, []):
                variant.available_in_store = False
    await db.commit()

    text = (
        f"{len(groups)} referenze nel {source}: {created} nuovi (spenti), {updated} aggiornati"
        + (f", {skipped} senza prezzo saltati" if skipped else "")
        + (
            f", {len(gone)} non più nel file e rese non comprabili" if gone and not truncated
            else f"; ATTENZIONE: il {source} porta meno prodotti di quelli noti (arrivato solo in parte?), {len(gone)} mancanti "
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
        raise service.SoleilMarketValidationError("Stato non valido.")
    if producer_id is None and not subcategory and not category_name:
        raise service.SoleilMarketValidationError("Scegli una marca o una categoria.")
    query = select(SoleilMarketProduct).where(SoleilMarketProduct.organization_id == organization_id)
    if producer_id is not None:
        query = query.where(SoleilMarketProduct.producer_id == producer_id)
    if subcategory:
        query = query.where(SoleilMarketProduct.subcategory == subcategory)
    if category_name:
        query = query.where(SoleilMarketProduct.category_name == category_name)
    products = list((await db.execute(query)).scalars().all())
    now: datetime = utcnow()
    for product in products:
        product.status = status
        product.updated_at = now
    await db.commit()
    return len(products)
