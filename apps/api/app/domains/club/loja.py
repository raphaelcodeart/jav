"""La Loja del club: judogi ed equipaggiamento in un carrello solo.
Specifica: docs/club-portal.md, "La Loja del club".

- **Per chi è**. Ogni prodotto dello shop del club dice per chi è
  (`jav_market_products.audience_sex`, `high_competition_only`): un atleta
  vede la versione del suo sesso e quelle per tutti; l'equipaggiamento di
  alta competizione lo vedono tutti, lo compra solo chi lo è. Per i judogi:
  l'aprovado FIJ (con il backnumber oficial PT) è di alta competizione, il
  rosa e le righe rosa sono solo per le ragazze — si vedono, non si
  comprano. Le regole valgono **all'ordine**, sul server: nascondere un
  bottone non basta.
- **Alta competizione**: un segno sull'atleta (`club_athletes.high_competition`)
  che mettono e tolgono la segreteria e il treinador, solo per gli atleti di
  un piano che la permette (il Grupo 3: `club_plans.allows_high_competition`).
  Vale finché l'atleta resta in quel piano.
- **Il carrello** (`club_cart_items`): judogi configurati e prodotti, per uno
  o più atleti, senza prezzi (si ricalcolano a ogni lettura). All'ordine
  ogni riga diventa un ordine a sé (`club_equipment_orders`) con la sua
  quota `EQUIPMENT`: la segreteria li prepara uno per uno, la famiglia li
  paga tutti insieme con una prova (o più tardi, dalla home).
- **Il kit del club**: i prodotti `club_kit` più il judogi bianco, con
  «Já tem» / «Encomendado» / «Em falta» per ogni atleta.
- **L'armadio dei judogi**: i judogi consegnati e non ritirati di ogni
  atleta (più quelli che aveva già, messi a mano), per la segreteria e il
  treinador prima delle gare: chi ha il bianco, l'azul, il FIJ, che cosa
  manca per la prossima prova.
"""

import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.club import judogi
from app.domains.club.models import (
    Club, ClubAthlete, ClubCompetition, ClubCompetitionEntry, ClubFee, ClubPlan,
)
from app.domains.club.operations_models import (
    JUDOGI_COLORS, JUDOGI_RETIRE_REASONS, KIMONO_TYPES, ClubCartItem, ClubEquipmentOrder, ClubWishlistItem,
)
from app.domains.club.scope import ClubScope
from app.domains.club.service import ClubNotFoundError, ClubValidationError
from app.domains.jav_market.models import JavMarketProduct, JavMarketVariant

#: I judogi che solo l'alta competizione può comprare.
HIGH_COMPETITION_TYPES = ("FIJ_APPROVED",)
#: I colori che solo le ragazze possono comprare.
GIRLS_ONLY_COLORS = ("PINK", "WHITE_PINK_STRIPES")
#: Quante righe al massimo in un carrello: un ordine di famiglia, non un magazzino.
MAX_CART_LINES = 30

LOCK_MESSAGES = {
    "HIGH_COMPETITION": "È equipaggiamento di alta competizione: lo comprano solo gli atleti che la segreteria o il "
                        "treinador hanno segnato come tali.",
    "GIRLS_ONLY": "Questo judogi è solo per le ragazze.",
    "SEX": "Questo modello non è per questo atleta: scegli la versione giusta.",
}


# --- Alta competizione --------------------------------------------------------------------------


async def high_competition_map(db: AsyncSession, athletes: list[ClubAthlete]) -> dict[uuid.UUID, bool]:
    """Chi è di alta competizione davvero: il segno e un piano che la permette."""
    plan_ids = {a.plan_id for a in athletes if a.high_competition and a.plan_id}
    allowed = set((await db.execute(select(ClubPlan.id).where(
        ClubPlan.id.in_(plan_ids), ClubPlan.allows_high_competition.is_(True),
    ))).scalars()) if plan_ids else set()
    return {a.id: bool(a.high_competition and a.plan_id in allowed) for a in athletes}


async def is_high_competition(db: AsyncSession, athlete: ClubAthlete) -> bool:
    return (await high_competition_map(db, [athlete]))[athlete.id]


async def plan_allows(db: AsyncSession, athlete: ClubAthlete) -> bool:
    if athlete.plan_id is None:
        return False
    plan = await db.get(ClubPlan, athlete.plan_id)
    return bool(plan and plan.allows_high_competition)


async def set_high_competition(
    db: AsyncSession, *, scope: ClubScope, athlete: ClubAthlete, actor_user_id: uuid.UUID, value: bool,
) -> ClubAthlete:
    """La segreteria o il treinador (che lo vede) segnano o tolgono l'alta
    competizione. Si segna solo chi è in un piano che la permette."""
    if value and not await plan_allows(db, athlete):
        raise ClubValidationError(
            "L'alta competizione è solo per gli atleti del Grupo 3: prima cambia il piano dell'atleta "
            "(o permetti l'alta competizione nel suo piano)."
        )
    previous = athlete.high_competition
    athlete.high_competition = value
    athlete.high_competition_by_user_id, athlete.high_competition_at = actor_user_id, utcnow()
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.athlete_high_competition", entity_type="club_athlete", entity_id=str(athlete.id),
        previous_value={"high_competition": previous}, new_value={"high_competition": value},
    )
    await db.commit()
    await db.refresh(athlete)
    return athlete


# --- Per chi è ------------------------------------------------------------------------------------


def judogi_lock(athlete: ClubAthlete, *, high_competition: bool, kimono_type: str, color: str) -> str | None:
    if kimono_type in HIGH_COMPETITION_TYPES and not high_competition:
        return "HIGH_COMPETITION"
    if color in GIRLS_ONLY_COLORS and athlete.sex != "F":
        return "GIRLS_ONLY"
    return None


def product_visible(athlete: ClubAthlete, product: JavMarketProduct) -> bool:
    """La versione dell'altro sesso non si mostra (sarebbe la stessa t-shirt
    due volte); l'alta competizione sì, chiusa."""
    return product.high_competition_only or product.audience_sex in ("ALL", athlete.sex)


def product_lock(athlete: ClubAthlete, *, high_competition: bool, product: JavMarketProduct) -> str | None:
    if product.audience_sex not in ("ALL", athlete.sex):
        return "SEX"
    if product.high_competition_only and not high_competition:
        return "HIGH_COMPETITION"
    return None


async def check_judogi(db: AsyncSession, *, athlete: ClubAthlete, kimono_type: str, color: str) -> None:
    lock = judogi_lock(athlete, high_competition=await is_high_competition(db, athlete),
                       kimono_type=kimono_type, color=color)
    if lock:
        raise ClubValidationError(LOCK_MESSAGES[lock])


def suggested_variant(variants: list[JavMarketVariant], height_cm: int | None) -> JavMarketVariant | None:
    """La prima taglia che arriva all'altezza dell'atleta, come per i judogi."""
    sized = sorted((v for v in variants if v.max_height_cm), key=lambda v: v.max_height_cm or 0)
    if not sized or not height_cm:
        return None
    return next((v for v in sized if (v.max_height_cm or 0) >= height_cm), sized[-1])


# --- La vetrina -----------------------------------------------------------------------------------


async def _club_products(db: AsyncSession, *, scope: ClubScope) -> list[tuple[JavMarketProduct, list[JavMarketVariant]]]:
    products = list((await db.execute(select(JavMarketProduct).where(
        JavMarketProduct.organization_id == scope.organization_id, JavMarketProduct.club_id == scope.club_id,
        JavMarketProduct.status == "ACTIVE",
    ).order_by(JavMarketProduct.club_kit.desc(), JavMarketProduct.name))).scalars())
    if not products:
        return []
    variants: dict[uuid.UUID, list[JavMarketVariant]] = {}
    for v in (await db.execute(select(JavMarketVariant).where(
        JavMarketVariant.product_id.in_([p.id for p in products]), JavMarketVariant.active.is_(True),
    ).order_by(JavMarketVariant.max_height_cm.nulls_last(), JavMarketVariant.price_cents, JavMarketVariant.label))).scalars():
        variants.setdefault(v.product_id, []).append(v)
    return [(p, variants[p.id]) for p in products if variants.get(p.id)]


def _variant_dict(v: JavMarketVariant) -> dict:
    return {"id": v.id, "label": v.label, "price_cents": v.price_cents, "max_height_cm": v.max_height_cm,
            "image_url": v.image_url, "in_stock": v.inventory is None or v.inventory > 0}


def _product_dict(athlete: ClubAthlete, product: JavMarketProduct, variants: list[JavMarketVariant], *,
                  high_competition: bool) -> dict:
    suggested = suggested_variant(variants, athlete.height_cm)
    return {
        "id": product.id, "name": product.name, "description": product.description,
        "image_url": product.image_url, "images": product.images or [],
        "audience_sex": product.audience_sex, "high_competition_only": product.high_competition_only,
        "club_kit": product.club_kit, "needs_name": product.needs_name,
        "variants": [_variant_dict(v) for v in variants],
        "suggested_variant_id": suggested.id if suggested else None,
        "min_price_cents": min(v.price_cents for v in variants),
        "lock": product_lock(athlete, high_competition=high_competition, product=product),
    }


async def _kit(db: AsyncSession, *, athlete: ClubAthlete, products: list[JavMarketProduct],
               high_competition: bool) -> list[dict]:
    """Il kit del club per l'atleta: il judogi bianco e i prodotti `club_kit`
    che sono per lui. Un ordine consegnato = «Já tem», uno in corso =
    «Encomendado»."""
    orders = list((await db.execute(select(ClubEquipmentOrder).where(
        ClubEquipmentOrder.athlete_id == athlete.id, ClubEquipmentOrder.status != "CANCELLED",
        ClubEquipmentOrder.retired_on.is_(None),
    ))).scalars())

    def state(match) -> str:
        mine = [o for o in orders if match(o)]
        if any(o.status == "DELIVERED" for o in mine):
            return "HAS"
        return "ORDERED" if mine else "MISSING"

    white = state(lambda o: o.kind == "JUDOGI" and (o.color_code == "WHITE" or (o.color or "").lower() == "branco"))
    kit = [{"code": "WHITE_JUDOGI", "product_id": None, "name": None,
            "state": "HAS" if athlete.white_judogi and white == "MISSING" else white}]
    for p in products:
        if p.club_kit and p.audience_sex in ("ALL", athlete.sex) and (high_competition or not p.high_competition_only):
            kit.append({"code": "PRODUCT", "product_id": p.id, "name": p.name,
                        "state": state(lambda o, pid=p.id: o.kind == "PRODUCT" and o.product_id == pid)})
    return kit


async def shop(db: AsyncSession, *, scope: ClubScope, club: Club, user_id: uuid.UUID, athlete_id: uuid.UUID,
               today: date) -> dict:
    """La Loja per un atleta: i judogi (modelli con foto, prezzo per la sua
    taglia, se può comprarli), l'equipaggiamento del club che è per lui, il
    suo kit."""
    athlete, mode = await judogi.athlete_for(db, scope=scope, user_id=user_id, athlete_id=athlete_id, today=today)
    hc = await is_high_competition(db, athlete)
    rows = await judogi.price_rows(db, club_id=club.id)
    models = await judogi.models_of(db, club_id=club.id)
    tree = judogi.price_tree(rows, height_cm=athlete.height_cm, models=models)
    judogis = []
    for t in tree:
        for c in t["colors"]:
            for b in c["brands"]:
                judogis.append({
                    "kimono_type": t["code"], "type_label": t["label"], "color": c["code"], "color_label": c["label"],
                    "brand": b["name"], "model_id": b["model_id"], "image_url": b["image_url"], "images": b["images"],
                    "description": b["description"], "min_price_cents": b["min_price_cents"],
                    "suggested_size_cm": b["suggested_size_cm"], "suggested_price_cents": b["suggested_price_cents"],
                    "lock": judogi_lock(athlete, high_competition=hc, kimono_type=t["code"], color=c["code"]),
                })
    pairs = await _club_products(db, scope=scope)
    products = [_product_dict(athlete, p, vs, high_competition=hc) for p, vs in pairs if product_visible(athlete, p)]
    owned = await wardrobe(db, athletes=[athlete])
    return {
        "athlete": judogi.athlete_dict(athlete, mode, today, high_competition=hc),
        "settings": judogi.settings_of(club),
        "judogi_types": tree,
        "judogis": judogis,
        "products": products,
        "kit": await _kit(db, athlete=athlete, products=[p for p, _ in pairs], high_competition=hc),
        "wardrobe": owned.get(athlete.id, []),
    }


# --- Il carrello ----------------------------------------------------------------------------------


async def _buyer_athlete(db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, athlete_id: uuid.UUID,
                         today: date) -> ClubAthlete:
    athlete, mode = await judogi.athlete_for(db, scope=scope, user_id=user_id, athlete_id=athlete_id, today=today)
    if mode != "BUY":
        raise ClubValidationError(
            "Lo compra chi paga: mettilo nella lista dei desideri e lo vedrà il titolare del conto."
        )
    return athlete


async def _product_variant(db: AsyncSession, *, scope: ClubScope, variant_id) -> tuple[JavMarketProduct, JavMarketVariant]:
    variant = await db.get(JavMarketVariant, variant_id)
    product = await db.get(JavMarketProduct, variant.product_id) if variant else None
    if (variant is None or product is None or product.club_id != scope.club_id or product.status != "ACTIVE"
            or not variant.active):
        raise ClubNotFoundError("Prodotto non trovato nella Loja del club.")
    return product, variant


def _clean_name(product: JavMarketProduct, name: str | None) -> str | None:
    if not product.needs_name:
        return None
    clean = " ".join((name or "").split())
    if len(clean) < 2:
        raise ClubValidationError(f"Scrivi il nome da mettere su «{product.name}».")
    if len(clean) > 100:
        raise ClubValidationError("Il nome è troppo lungo (massimo 100 caratteri).")
    return clean


def _judogi_config(data: dict) -> dict:
    choice = data.get("judogi") or {}
    trade = choice.get("trade_in")
    return {
        "kimono_type": choice.get("kimono_type"), "color": choice.get("color"), "brand": choice.get("brand"),
        "size_cm": choice.get("size_cm"), "height_cm": choice.get("height_cm"),
        "kimono_name": (choice.get("kimono_name") or "").strip()[:100] or None,
        "notes": (choice.get("notes") or "").strip()[:2000] or None,
        "trade_in": ({k: trade.get(k) for k in ("kimono_type", "color", "brand", "size_cm", "owned_order_id")}
                     if trade else None),
        # Il desiderio dell'atleta da cui nasce, chiuso quando parte l'ordine.
        "wish_id": str(choice["wish_id"]) if choice.get("wish_id") else None,
    }


async def _validate_line(db: AsyncSession, *, scope: ClubScope, club: Club, athlete: ClubAthlete, kind: str,
                         config: dict | None, variant_id, quantity: int, today: date) -> dict:
    """Una riga del carrello come la vede la famiglia, ricalcolata ora: il
    prezzo, il titolo, e se si può ancora ordinare (`problem`)."""
    hc = await is_high_competition(db, athlete)
    if kind == "JUDOGI":
        q = await judogi.quote(db, club=club, choice=config or {}, height_cm=(config or {}).get("height_cm")
                               or athlete.height_cm, athlete_id=athlete.id)
        judogi.check_name((config or {}).get("kimono_name") or "", athlete, today)
        lock = judogi_lock(athlete, high_competition=hc, kimono_type=q["kimono_type"], color=q["color"])
        models = await judogi.models_of(db, club_id=club.id)
        model = models.get((q["kimono_type"], q["brand"], q["color"]))
        return {"title": f"{q['type_label']} · {q['brand']}", "image_url": model.image_url if model else None,
                "price_cents": q["total_cents"], "quote": q, "lock": lock}
    product, variant = await _product_variant(db, scope=scope, variant_id=variant_id)
    lock = product_lock(athlete, high_competition=hc, product=product)
    if variant.inventory is not None and variant.inventory < quantity:
        raise ClubValidationError(
            f"«{product.name}» ({variant.label}): ne restano {variant.inventory}." if variant.inventory
            else f"«{product.name}» ({variant.label}) è esaurito."
        )
    _clean_name(product, (config or {}).get("name"))
    return {"title": product.name, "variant_label": variant.label, "image_url": variant.image_url or product.image_url,
            "price_cents": variant.price_cents * quantity, "unit_price_cents": variant.price_cents, "lock": lock}


async def cart(db: AsyncSession, *, scope: ClubScope, club: Club, user_id: uuid.UUID, today: date) -> dict:
    items = list((await db.execute(select(ClubCartItem).where(
        ClubCartItem.club_id == scope.club_id, ClubCartItem.user_id == user_id,
    ).order_by(ClubCartItem.created_at))).scalars())
    athletes = {a.id: a for a in (await db.execute(select(ClubAthlete).where(
        ClubAthlete.id.in_({i.athlete_id for i in items}),
    ))).scalars()} if items else {}
    lines = []
    for item in items:
        athlete = athletes.get(item.athlete_id)
        line = {"id": item.id, "kind": item.kind, "athlete_id": item.athlete_id,
                "athlete_name": f"{athlete.first_name} {athlete.last_name}" if athlete else None,
                "quantity": item.quantity, "config": item.config, "product_id": item.product_id,
                "variant_id": item.variant_id, "problem": None}
        try:
            if athlete is None:
                raise ClubValidationError("Atleta non trovato.")
            line.update(await _validate_line(db, scope=scope, club=club, athlete=athlete, kind=item.kind,
                                             config=item.config, variant_id=item.variant_id,
                                             quantity=item.quantity, today=today))
            if line.get("lock"):
                line["problem"] = LOCK_MESSAGES[line["lock"]]
        except (ClubValidationError, ClubNotFoundError) as exc:
            line.update({"title": None, "price_cents": 0, "problem": str(exc)})
        lines.append(line)
    ok = [line for line in lines if not line["problem"]]
    return {"items": lines, "count": len(lines), "total_cents": sum(line["price_cents"] for line in ok),
            "can_checkout": bool(lines) and len(ok) == len(lines)}


async def add_to_cart(db: AsyncSession, *, scope: ClubScope, club: Club, user_id: uuid.UUID, data: dict,
                      today: date) -> ClubCartItem:
    """Aggiunge al carrello dopo aver verificato che si possa ordinare: un
    judogi chiuso o un prodotto esaurito si scopre qui, non alla cassa."""
    athlete = await _buyer_athlete(db, scope=scope, user_id=user_id, athlete_id=data.get("athlete_id"), today=today)
    count = len(list((await db.execute(select(ClubCartItem.id).where(
        ClubCartItem.club_id == scope.club_id, ClubCartItem.user_id == user_id,
    ))).scalars()))
    if count >= MAX_CART_LINES:
        raise ClubValidationError(f"Il carrello ha già {MAX_CART_LINES} articoli: ordina questi prima.")
    kind = data.get("kind")
    quantity = int(data.get("quantity") or 1)
    if not 1 <= quantity <= 20:
        raise ClubValidationError("La quantità va da 1 a 20.")
    if kind == "JUDOGI":
        config = _judogi_config(data)
        quantity = 1
        line = await _validate_line(db, scope=scope, club=club, athlete=athlete, kind=kind, config=config,
                                    variant_id=None, quantity=1, today=today)
        # Si congelano la taglia scelta dal server e la permuta letta dall'armadio.
        config["size_cm"] = line["quote"]["size_cm"]
        item = ClubCartItem(**scope.columns(), user_id=user_id, athlete_id=athlete.id, kind=kind, config=config)
    elif kind == "PRODUCT":
        config = {"name": (data.get("name") or "").strip()[:100] or None}
        line = await _validate_line(db, scope=scope, club=club, athlete=athlete, kind=kind, config=config,
                                    variant_id=data.get("variant_id"), quantity=quantity, today=today)
        product, variant = await _product_variant(db, scope=scope, variant_id=data.get("variant_id"))
        item = ClubCartItem(**scope.columns(), user_id=user_id, athlete_id=athlete.id, kind=kind,
                            product_id=product.id, variant_id=variant.id, quantity=quantity, config=config)
    else:
        raise ClubValidationError("Che cosa vuoi aggiungere al carrello?")
    if line["lock"]:
        raise ClubValidationError(LOCK_MESSAGES[line["lock"]])
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def _cart_item(db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, item_id: uuid.UUID) -> ClubCartItem:
    item = await db.get(ClubCartItem, item_id)
    if item is None or item.club_id != scope.club_id or item.user_id != user_id:
        raise ClubNotFoundError("Articolo non trovato nel carrello.")
    return item


async def update_cart_item(db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, item_id: uuid.UUID,
                           quantity: int) -> None:
    item = await _cart_item(db, scope=scope, user_id=user_id, item_id=item_id)
    if item.kind == "JUDOGI":
        raise ClubValidationError("Un judogi è uno per riga: per un secondo, configuralo di nuovo.")
    if not 1 <= quantity <= 20:
        raise ClubValidationError("La quantità va da 1 a 20.")
    item.quantity = quantity
    await db.commit()


async def remove_cart_item(db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, item_id: uuid.UUID) -> None:
    await db.delete(await _cart_item(db, scope=scope, user_id=user_id, item_id=item_id))
    await db.commit()


# --- L'ordine -------------------------------------------------------------------------------------


async def place_product_order(
    db: AsyncSession, *, scope: ClubScope, athlete: ClubAthlete, actor_user_id: uuid.UUID, variant_id,
    quantity: int, name: str | None, today: date, check_rules: bool = True,
) -> ClubEquipmentOrder:
    """Un prodotto del club ordinato per un atleta: il prezzo dalla variante,
    la scorta che scende, la quota da pagare. Non fa commit."""
    product, variant = await _product_variant(db, scope=scope, variant_id=variant_id)
    if check_rules:
        lock = product_lock(athlete, high_competition=await is_high_competition(db, athlete), product=product)
        if lock:
            raise ClubValidationError(LOCK_MESSAGES[lock])
    if variant.inventory is not None:
        if variant.inventory < quantity:
            raise ClubValidationError(f"«{product.name}» ({variant.label}) non è più disponibile in questa quantità.")
        variant.inventory -= quantity
    price = variant.price_cents * quantity
    order = ClubEquipmentOrder(
        **scope.columns(), athlete_id=athlete.id, requested_by_user_id=actor_user_id, kind="PRODUCT",
        product_id=product.id, variant_id=variant.id, product_name=product.name[:255],
        variant_label=(variant.label or "")[:255] or None, quantity=quantity, unit_price_cents=variant.price_cents,
        kimono_name=_clean_name(product, name), price_cents=price, status="PENDING",
    )
    db.add(order)
    await db.flush()
    fee = ClubFee(
        **scope.columns(), athlete_id=athlete.id, kind="EQUIPMENT", period=str(order.id),
        description=judogi.order_title(order)[:200], amount_cents=price, gross_amount_cents=price,
        due_date=today + timedelta(days=judogi.FEE_DUE_DAYS), status="DUE",
    )
    db.add(fee)
    await db.flush()
    order.fee_id = fee.id
    # Il desiderio dell'atleta per questo prodotto è esaudito.
    await judogi.mark_products_ordered(db, athlete_id=athlete.id, product_ids={product.id}, order_id=None,
                                       actor_user_id=actor_user_id, equipment_order_id=order.id)
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id, action="club.loja_product_ordered",
        entity_type="club_equipment_order", entity_id=str(order.id),
        new_value={"athlete_id": str(athlete.id), "product_id": str(product.id), "variant_id": str(variant.id),
                   "quantity": quantity, "total_cents": price},
    )
    return order


async def _place(db: AsyncSession, *, scope: ClubScope, club: Club, athlete: ClubAthlete, user_id: uuid.UUID,
                 kind: str, config: dict | None, variant_id, quantity: int, today: date) -> ClubEquipmentOrder:
    if kind == "JUDOGI":
        wish = None
        if (config or {}).get("wish_id"):
            wish = await db.get(ClubWishlistItem, uuid.UUID(config["wish_id"]))
            if wish is None or wish.athlete_id != athlete.id or wish.kind != "JUDOGI" or wish.status != "OPEN":
                wish = None
        order, _q = await judogi.place_order(db, scope=scope, club=club, athlete=athlete, actor_user_id=user_id,
                                             data=config or {}, today=today, wish=wish)
        return order
    return await place_product_order(db, scope=scope, athlete=athlete, actor_user_id=user_id, variant_id=variant_id,
                                     quantity=quantity, name=(config or {}).get("name"), today=today)


async def _after_orders(db: AsyncSession, *, scope: ClubScope, orders: list[ClubEquipmentOrder]) -> dict:
    from app.domains.club.clubs import notify_club_staff

    athletes = {a.id: a for a in (await db.execute(select(ClubAthlete).where(
        ClubAthlete.id.in_({o.athlete_id for o in orders}),
    ))).scalars()}
    total = sum(o.price_cents or 0 for o in orders)
    names = ", ".join(sorted({f"{athletes[o.athlete_id].first_name} {athletes[o.athlete_id].last_name}" for o in orders}))
    await notify_club_staff(
        db, scope=scope, type_="CLUB_JUDOGI_ORDER", entity_type="club_equipment_order", entity_id=orders[0].id,
        title=(f"Nova encomenda da Loja: {names}" if len(orders) == 1
               else f"{len(orders)} encomendas da Loja: {names}")[:200],
        body=(" · ".join(judogi.order_title(o) for o in orders) + f" · {total / 100:.2f} €")[:500],
    )
    return {
        "orders": [judogi.order_dict(o, athletes.get(o.athlete_id)) for o in orders],
        "fee_ids": [o.fee_id for o in orders if o.fee_id],
        "total_cents": total,
    }


async def checkout(db: AsyncSession, *, scope: ClubScope, club: Club, user_id: uuid.UUID,
                   item_ids: list[uuid.UUID] | None, today: date) -> dict:
    """Il carrello (o le righe scelte) diventa un ordine per riga, tutti o
    nessuno: se una riga non si può più ordinare, non parte niente e la
    famiglia vede perché."""
    stmt = select(ClubCartItem).where(ClubCartItem.club_id == scope.club_id, ClubCartItem.user_id == user_id)
    if item_ids:
        stmt = stmt.where(ClubCartItem.id.in_(item_ids))
    items = list((await db.execute(stmt.order_by(ClubCartItem.created_at))).scalars())
    if not items:
        raise ClubValidationError("Il carrello è vuoto.")
    orders = []
    for item in items:
        athlete = await _buyer_athlete(db, scope=scope, user_id=user_id, athlete_id=item.athlete_id, today=today)
        orders.append(await _place(db, scope=scope, club=club, athlete=athlete, user_id=user_id, kind=item.kind,
                                   config=item.config, variant_id=item.variant_id, quantity=item.quantity,
                                   today=today))
        await db.delete(item)
    await db.commit()
    for o in orders:
        await db.refresh(o)
    return await _after_orders(db, scope=scope, orders=orders)


async def buy_now(db: AsyncSession, *, scope: ClubScope, club: Club, user_id: uuid.UUID, data: dict,
                  today: date) -> dict:
    """«Comprar já»: un articolo ordinato subito, senza passare dal carrello."""
    athlete = await _buyer_athlete(db, scope=scope, user_id=user_id, athlete_id=data.get("athlete_id"), today=today)
    kind = data.get("kind")
    if kind == "JUDOGI":
        config = _judogi_config(data)
        order = await _place(db, scope=scope, club=club, athlete=athlete, user_id=user_id, kind=kind, config=config,
                             variant_id=None, quantity=1, today=today)
    elif kind == "PRODUCT":
        quantity = int(data.get("quantity") or 1)
        if not 1 <= quantity <= 20:
            raise ClubValidationError("La quantità va da 1 a 20.")
        order = await _place(db, scope=scope, club=club, athlete=athlete, user_id=user_id, kind=kind,
                             config={"name": data.get("name")}, variant_id=data.get("variant_id"),
                             quantity=quantity, today=today)
    else:
        raise ClubValidationError("Che cosa vuoi comprare?")
    await db.commit()
    await db.refresh(order)
    return await _after_orders(db, scope=scope, orders=[order])


# --- L'armadio dei judogi -------------------------------------------------------------------------


def _owned_dict(o: ClubEquipmentOrder, athlete: ClubAthlete) -> dict:
    color = o.color_code or judogi.COLOR_FROM_PT.get((o.color or "").lower())
    return {
        "id": o.id, "kimono_type": o.kimono_type, "type_label": judogi.TYPE_PT.get(o.kimono_type or "", o.kimono_type),
        "color": color, "color_label": o.color, "brand": o.brand, "size_cm": o.size_cm, "kimono_name": o.kimono_name,
        "status": o.status, "origin": o.origin, "delivered_on": o.delivered_on, "created_at": o.created_at,
        # Il cotone si ritira e i bambini crescono: un judogi più corto
        # dell'altezza attuale è da cambiare.
        "small": bool(athlete.height_cm and o.size_cm and o.size_cm < athlete.height_cm),
    }


async def wardrobe(db: AsyncSession, *, athletes: list[ClubAthlete]) -> dict[uuid.UUID, list[dict]]:
    """I judogi di ogni atleta: consegnati e non ritirati, più quelli in
    arrivo (ordinati, in preparazione)."""
    by_id = {a.id: a for a in athletes}
    if not by_id:
        return {}
    out: dict[uuid.UUID, list[dict]] = {}
    for o in (await db.execute(select(ClubEquipmentOrder).where(
        ClubEquipmentOrder.athlete_id.in_(list(by_id)), ClubEquipmentOrder.kind == "JUDOGI",
        ClubEquipmentOrder.status != "CANCELLED", ClubEquipmentOrder.retired_on.is_(None),
    ).order_by(ClubEquipmentOrder.delivered_on.desc().nulls_first(), ClubEquipmentOrder.created_at.desc()))).scalars():
        out.setdefault(o.athlete_id, []).append(_owned_dict(o, by_id[o.athlete_id]))
    return out


def _best(items: list[dict], match) -> dict | None:
    """Il judogi che conta per una colonna: uno consegnato e della taglia
    giusta prima, poi uno consegnato, poi uno in arrivo."""
    mine = [i for i in items if match(i)]
    for rank in (lambda i: i["status"] == "DELIVERED" and not i["small"], lambda i: i["status"] == "DELIVERED",
                 lambda i: True):
        found = next((i for i in mine if rank(i)), None)
        if found:
            return found
    return None


async def _visible_athletes(db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, manager: bool) -> list[ClubAthlete]:
    """Gli atleti che chi guarda vede: tutti gli attivi per la segreteria,
    quelli dei suoi corsi (e gli attivi senza corso) per un treinador."""
    from app.domains.club import coach

    ids = [a["id"] for a in await coach.my_athletes(db, scope=scope, user_id=user_id, manager=manager,
                                                     today=utcnow().date())]
    if not ids:
        return []
    return list((await db.execute(select(ClubAthlete).where(ClubAthlete.id.in_(ids))
                                  .order_by(ClubAthlete.first_name, ClubAthlete.last_name))).scalars())


async def staff_athlete(db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, manager: bool,
                        athlete_id: uuid.UUID) -> ClubAthlete:
    from app.domains.club import coach

    return await coach._athlete(db, scope=scope, user_id=user_id, manager=manager, athlete_id=athlete_id)


async def staff_judogis(db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, manager: bool,
                        competition_id: uuid.UUID | None, today: date) -> dict:
    """L'armadio dei judogi per la segreteria e il treinador. Con una prova:
    solo i suoi iscritti, e che cosa manca (il treinador porta il judogi
    del club a chi non ha il bianco o l'azul)."""
    athletes = await _visible_athletes(db, scope=scope, user_id=user_id, manager=manager)
    upcoming = list((await db.execute(
        select(ClubCompetition).join(ClubCompetitionEntry, ClubCompetitionEntry.competition_id == ClubCompetition.id)
        .where(ClubCompetitionEntry.club_id == scope.club_id, ClubCompetitionEntry.status == "REGISTERED",
               ClubCompetition.ends_on >= today)
        .distinct().order_by(ClubCompetition.starts_on).limit(12)
    )).scalars())
    competition = None
    if competition_id is not None:
        competition = next((c for c in upcoming if c.id == competition_id), None) or await db.get(ClubCompetition, competition_id)
        if competition is None:
            raise ClubNotFoundError("Prova non trovata.")
        entered = set((await db.execute(select(ClubCompetitionEntry.athlete_id).where(
            ClubCompetitionEntry.competition_id == competition.id, ClubCompetitionEntry.club_id == scope.club_id,
            ClubCompetitionEntry.status == "REGISTERED",
        ))).scalars())
        athletes = [a for a in athletes if a.id in entered]
    owned = await wardrobe(db, athletes=athletes)
    hc = await high_competition_map(db, athletes)
    allowed_plans = set((await db.execute(select(ClubPlan.id).where(
        ClubPlan.club_id == scope.club_id, ClubPlan.allows_high_competition.is_(True),
    ))).scalars())
    rows = []
    for a in athletes:
        items = owned.get(a.id, [])
        white = _best(items, lambda i: i["color"] == "WHITE")
        blue = _best(items, lambda i: i["color"] == "BLUE")
        fij = [i for i in items if i["kimono_type"] == "FIJ_APPROVED"]
        white_ok = bool(white and white["status"] == "DELIVERED") or (white is None and a.white_judogi)
        blue_ok = bool(blue and blue["status"] == "DELIVERED")
        rows.append({
            "athlete_id": a.id, "first_name": a.first_name, "last_name": a.last_name, "photo_url": a.photo_url,
            "sex": a.sex, "height_cm": a.height_cm, "white_judogi_declared": a.white_judogi,
            "high_competition": hc.get(a.id, False), "high_competition_flag": a.high_competition,
            "high_competition_allowed": a.plan_id in allowed_plans,
            "white": white, "blue": blue, "fij": fij, "judogis": items,
            "missing": [code for code, ok in (("WHITE", white_ok), ("BLUE", blue_ok)) if not ok],
        })
    return {
        "competitions": [{"id": c.id, "name": c.name, "starts_on": c.starts_on, "location": c.location}
                         for c in upcoming],
        "competition": ({"id": competition.id, "name": competition.name, "starts_on": competition.starts_on,
                         "location": competition.location} if competition else None),
        "rows": rows,
        "totals": {"athletes": len(rows), "ready": sum(1 for r in rows if not r["missing"]),
                   "missing_white": sum(1 for r in rows if "WHITE" in r["missing"]),
                   "missing_blue": sum(1 for r in rows if "BLUE" in r["missing"])},
    }


async def add_owned_judogi(db: AsyncSession, *, scope: ClubScope, athlete: ClubAthlete, actor_user_id: uuid.UUID,
                           data: dict, today: date) -> ClubEquipmentOrder:
    """Un judogi che l'atleta aveva già (comprato fuori, ereditato): entra
    nell'armadio senza prezzo e senza quota."""
    kind, color = data.get("kimono_type"), data.get("color")
    brand = " ".join((data.get("brand") or "").split())
    size = data.get("size_cm")
    if kind not in KIMONO_TYPES or color not in JUDOGI_COLORS:
        raise ClubValidationError("Scegli il tipo e il colore del judogi.")
    if not 2 <= len(brand) <= 60:
        raise ClubValidationError("Scrivi la marca del judogi.")
    if not isinstance(size, int) or not 80 <= size <= 220:
        raise ClubValidationError("La taglia va da 80 a 220 cm.")
    name = " ".join((data.get("kimono_name") or "").split())[:100] or judogi.name_prefill(athlete, today)
    order = ClubEquipmentOrder(
        **scope.columns(), athlete_id=athlete.id, requested_by_user_id=actor_user_id, kind="JUDOGI", origin="MANUAL",
        kimono_name=name, kimono_type=kind, color=judogi.COLOR_PT[color], color_code=color, brand=brand,
        size_cm=size, status="DELIVERED", delivered_on=today,
        notes=(data.get("notes") or "").strip()[:2000] or None,
    )
    db.add(order)
    await db.flush()
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id, action="club.judogi_owned_added",
        entity_type="club_equipment_order", entity_id=str(order.id),
        new_value={"athlete_id": str(athlete.id), "kimono_type": kind, "color": color, "brand": brand, "size_cm": size},
    )
    await db.commit()
    await db.refresh(order)
    return order


async def retire_judogi(db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, manager: bool,
                        order_id: uuid.UUID, reason: str, today: date) -> ClubEquipmentOrder:
    """Un judogi esce dall'armadio (piccolo, rovinato, perso)."""
    if reason not in JUDOGI_RETIRE_REASONS:
        raise ClubValidationError("Perché esce dall'armadio?")
    order = await db.get(ClubEquipmentOrder, order_id)
    if order is None or order.club_id != scope.club_id or order.kind != "JUDOGI":
        raise ClubNotFoundError("Judogi non trovato.")
    await staff_athlete(db, scope=scope, user_id=user_id, manager=manager, athlete_id=order.athlete_id)
    if order.status != "DELIVERED" or order.retired_on is not None:
        raise ClubValidationError("Esce dall'armadio solo un judogi consegnato e ancora in uso.")
    order.retired_on, order.retired_reason = today, reason
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=user_id, action="club.judogi_retired",
        entity_type="club_equipment_order", entity_id=str(order.id), new_value={"reason": reason},
    )
    await db.commit()
    await db.refresh(order)
    return order
