"""Lo Shop JAV sul sito pubblico, in sola lettura (docs/club-portal.md, "Lo
shop della rete"). Chi non ha un account vede i prodotti di JudoArteVida
(non quelli dei club) con il prezzo finale, IVA compresa; per comprare deve
essere socio di un club della rete, e la pagina lo porta all'elenco dei club.
Con lo shop spento la vetrina è vuota, come per i clienti.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.domains.jav_market import service
from app.domains.jav_market.models import SHOP
from app.domains.marketplaces import paging, rules
from app.domains.organizations.service import resolve_organization_id

public_shop_router = APIRouter(prefix="/public-site", tags=["public-site"])


def _gross(net: int, vat: int) -> int:
    return net + rules.vat_added_cents(net_cents=net, percentage=vat)


@public_shop_router.get("/shop")
async def public_shop(
    offset: int = Query(0, ge=0),
    limit: int = Query(24, ge=1, le=paging.MAX_PAGE_SIZE),
    q: str | None = Query(None, max_length=100),
    category_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.domains.shop_categories import service as categories_service

    org = await resolve_organization_id(db, None)
    page = await service.customer_products_page(
        db, organization_id=org, offset=offset, limit=limit, search=q, category_id=category_id, seller="JAV",
    )
    vat = await rules.get_vat_percentage(db, organization_id=org)
    items = [{
        "id": p["id"], "name": p["name"], "description": p["description"], "image_url": p["image_url"],
        "price_cents": _gross(p["min_price_cents"], vat), "max_price_cents": _gross(p["max_price_cents"], vat),
        "in_stock": p["in_stock"], "category_ids": p.get("category_ids") or [],
    } for p in page["items"]]
    categories = [] if not page["shop_total"] else [
        {"id": c.id, "name": c.name, "count": n}
        for c, n in await categories_service.list_categories(db, organization_id=org, shop=SHOP)
        if c.active and n > 0
    ]
    return {"items": items, "total": page["total"], "shop_total": page["shop_total"], "offset": page["offset"],
            "next_offset": page["next_offset"], "categories": categories}
