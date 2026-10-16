"""La vetrina del cliente a pagine, uguale per ogni negozio.

Restituire tutto il catalogo in una risposta non regge: un catalogo di
decine di migliaia di prodotti pesa decine di MB e mezzo GB di memoria del
server per ogni apertura. Ogni negozio dà quindi
al cliente `limit` schede per volta («Mostra altri prodotti»), con ricerca e
categoria filtrate qui, nel database, e non nel browser.

Un negozio passa il suo modello prodotto (con `organization_id`, `status`,
`name`, `description`, `created_at`) e una funzione che trasforma una lista
di prodotti in schede **allineate** (None per un prodotto che il cliente non
deve vedere, per esempio esaurito o non spedibile in Italia): le pagine si
riempiono comunque fino a `limit`, e `next_offset` dice da dove riprendere.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.shop_categories.models import ShopCategoryProduct

#: Quante schede riceve il cliente per volta.
PAGE_SIZE = 48
MAX_PAGE_SIZE = 96
MAX_READS_PER_PAGE = 5

CardBuilder = Callable[[list[Any]], Awaitable[Sequence[dict | None]]]


def empty_page(offset: int = 0, limit: int = PAGE_SIZE) -> dict:
    """Un negozio spento: nessuna scheda, e la scheda dello Shop sparisce
    perché `shop_total` è 0."""
    return {
        "items": [], "total": 0, "shop_total": 0, "offset": offset, "limit": limit,
        "next_offset": None, "category_ids": [],
    }


def _like(needle: str) -> str:
    # Il «%» o il «_» scritti dal cliente sono caratteri, non jolly.
    return "%" + needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


async def customer_page(
    db: AsyncSession,
    *,
    model: Any,
    shop: str,
    organization_id: uuid.UUID,
    build_cards: CardBuilder,
    offset: int = 0,
    limit: int = PAGE_SIZE,
    search: str | None = None,
    category_id: uuid.UUID | None = None,
    scope_filters: list | None = None,
) -> dict:
    """Una pagina della vetrina di un negozio. `scope_filters`: condizioni in
    più su che cosa fa parte della vetrina di chi guarda (lo shop del suo club
    e quello di JudoArteVida).

    `total` sono i prodotti accesi che rispondono a ricerca e categoria,
    `shop_total` quelli accesi senza filtri (la scheda dello Shop e il suo
    conteggio), `category_ids` le categorie con almeno un prodotto acceso.
    Entrambi i totali contano i prodotti accesi: uno che poi non dà scheda
    (esaurito, non spedibile) li supera di poco, mai il contrario."""
    offset = max(offset, 0)
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    in_shop = [model.organization_id == organization_id, model.status == "ACTIVE", *(scope_filters or [])]
    filters = list(in_shop)
    needle = (search or "").strip()
    if needle:
        like = _like(needle)
        filters.append(or_(model.name.ilike(like, escape="\\"), model.description.ilike(like, escape="\\")))
    if category_id is not None:
        filters.append(model.id.in_(
            select(ShopCategoryProduct.product_id).where(
                ShopCategoryProduct.organization_id == organization_id,
                ShopCategoryProduct.shop == shop,
                ShopCategoryProduct.category_id == category_id,
            )
        ))
    count = select(func.count()).select_from(model)
    shop_total = (await db.execute(count.where(*in_shop))).scalar_one()
    total = (await db.execute(count.where(*filters))).scalar_one() if len(filters) > len(in_shop) else shop_total
    category_ids = list((await db.execute(
        select(ShopCategoryProduct.category_id).distinct().where(
            ShopCategoryProduct.organization_id == organization_id,
            ShopCategoryProduct.shop == shop,
            ShopCategoryProduct.product_id.in_(select(model.id).where(*in_shop)),
        )
    )).scalars().all())

    # L'id rende stabile l'ordine: un import crea migliaia di prodotti con lo
    # stesso created_at, e una pagina non deve ripeterne o saltarne.
    ordered = select(model).where(*filters).order_by(model.created_at.desc(), model.id)
    items: list[dict] = []
    cursor = offset
    # Al massimo qualche lettura per pagina: con molti prodotti nascosti di
    # fila la pagina esce più corta e «Mostra altri» riprende da lì, invece
    # di scorrere tutto il catalogo in una richiesta.
    for _ in range(MAX_READS_PER_PAGE):
        batch = list((await db.execute(ordered.offset(cursor).limit(limit))).scalars().all())
        cards = await build_cards(batch)
        consumed = 0
        for card in cards:
            consumed += 1
            if card is not None:
                items.append(card)
                if len(items) == limit:
                    break
        cursor += consumed
        exhausted = len(batch) < limit
        if len(items) >= limit or exhausted:
            break
    else:
        exhausted = False
    # Altri prodotti dopo questa pagina, salvo aver letto l'ultima riga. Una
    # pagina piena può finire proprio sull'ultimo prodotto: lo si chiede al
    # database, perché «Mostra altri» non apra una pagina vuota.
    next_offset = None if exhausted and consumed == len(batch) else cursor
    if next_offset is not None and (await db.execute(
        select(model.id).where(*filters).order_by(model.created_at.desc(), model.id).offset(cursor).limit(1)
    )).first() is None:
        next_offset = None
    return {
        "items": items, "total": total, "shop_total": shop_total, "offset": offset, "limit": limit,
        "next_offset": next_offset, "category_ids": category_ids,
    }
