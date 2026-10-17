"""I judogi del club: il listino, il calcolatore, gli ordini e la lista dei
desideri. Specifica: docs/club-portal.md, "Judogi: calcolatore, ordini e
lista dei desideri".

Il calcolatore viene dal gestionale vecchio (judoartevida.com/jav/fatos):

    totale = max(0, listino[tipo][marca][colore][taglia]
                    + personalizzazione obbligatoria
                    − round(listino[judogi restituito] × permuta %))

con due differenze volute: il listino è una tabella che la segreteria
modifica (`club_judogi_prices`), non un array nel codice; e la taglia si
sceglie dall'altezza fra quelle che **esistono** per quel judogi (la decina
o il passo da 5 successivi, come in javbot/sizes.py), così un bambino di
95 cm trova il 100 invece di "nessuna marca disponibile".

Chi compra:
- il **titolare** del conto, per ognuno dei suoi atleti;
- l'**atleta maggiorenne** con il suo accesso, per sé;
- l'atleta minorenne vede tutto ma non compra: mette il judogi (o un
  prodotto dello Shop) nella **lista dei desideri** e il titolare riceve la
  notifica. Il titolare dal desiderio fa l'ordine vero, o lo rifiuta.

L'ordine diventa una quota `EQUIPMENT` dell'atleta (period = id
dell'ordine, quindi una sola per ordine): si paga come ogni altra quota,
con la prova di pagamento, in contanti o al POS.
"""

import csv
import io
import uuid
from datetime import date, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.club.athlete_access import ADULT_AGE, age_on
from app.domains.club.models import Club, ClubAthlete, ClubFee, ClubPaymentProofFee
from app.domains.club.operations_models import (
    EQUIPMENT_ORDER_STATUSES,
    JUDOGI_COLORS,
    KIMONO_TYPES,
    ClubEquipmentOrder,
    ClubJudogiPrice,
    ClubWishlistItem,
)
from app.domains.club.scope import ClubScope
from app.domains.club.service import ClubNotFoundError, ClubValidationError

DEFAULT_CUSTOMIZATION_CENTS = 3500
DEFAULT_TRADE_IN_PERCENT = 50
#: Sotto questa età sul judogi si ricama solo il nome proprio.
NAME_RULE_AGE = 13
#: La quota del judogi scade dopo due settimane dall'ordine.
FEE_DUE_DAYS = 14

TYPE_PT = {
    "FIJ_APPROVED": "Judogi FIJ Aprovado",
    "TRAINING": "Judogi de Treino",
    "SEMI_COMPETITION": "Judogi Semi-Competição",
    "COMPETITION_NOT_APPROVED": "Judogi de Competição (Não Aprovado)",
}
#: Il nome del colore che finisce sull'ordine: obligations.py lo legge
#: ("azul", "rosa", "branco").
COLOR_PT = {"WHITE": "Branco", "BLUE": "Azul", "PINK": "Rosa", "WHITE_PINK_STRIPES": "Branco Riscas Rosa"}
STATUS_PT = {"PENDING": "Pendente", "IN_PREPARATION": "Em preparação", "DELIVERED": "Entregue", "CANCELLED": "Cancelado"}


# --- Il listino di partenza -----------------------------------------------------------------------


def _steps(start: int, stop: int, step: int) -> list[int]:
    return list(range(start, stop + 1, step))


def _by_band(sizes: list[int], bands: list[tuple[int, int]]) -> dict[int, int]:
    """Prezzi a fasce: [(fino_a_cm, euro), ...]."""
    out = {}
    for size in sizes:
        out[size] = next(euro for top, euro in bands if size <= top)
    return out


def base_catalog() -> list[tuple[str, str, str, int, int]]:
    """Il listino del calcolatore vecchio (data/catalog.php), in centesimi:
    (tipo, marca, colore, taglia, prezzo). Due prezzi corretti: il bianco da
    Treino 100 e 110 cm di Tochi Gi e NKL era 13 e 14 € (refusi per 23 e
    24: in mezzo a 22 e 25)."""
    rows: list[tuple[str, str, str, int, int]] = []

    def add(kind: str, brand: str, color: str, prices: dict[int, int]) -> None:
        rows.extend((kind, brand, color, size, euro * 100) for size, euro in prices.items())

    fij = _steps(150, 200, 5)
    for brand, white, blue in (
        ("Matsuru", (150, 160, 165), (170, 180, 185)),
        ("Fight Art", (130, 140, 145), (140, 150, 155)),
        ("Mizuno", (175, 180, 185), (190, 195, 200)),
        ("Adidas", (150, 160, 165), (175, 185, 190)),
        ("Ippon Gear", (150, 160, 165), (170, 180, 185)),
    ):
        for color, euros in (("WHITE", white), ("BLUE", blue)):
            add("FIJ_APPROVED", brand, color, _by_band(fij, list(zip((165, 185, 200), euros, strict=True))))

    training = _steps(90, 200, 10)
    white_basic = [22, 23, 24, 25, 26, 28, 30, 32, 34, 36, 38, 41]
    matsuru_white = [25, 26, 27, 28, 29, 31, 33, 35, 37, 39, 41, 45]
    add("TRAINING", "Tochi Gi", "WHITE", dict(zip(training, white_basic, strict=True)))
    add("TRAINING", "Tochi Gi", "BLUE", dict(zip(training, [32, 34, 36, 38, 40, 42, 44, 46, 48, 50, 52, 54], strict=True)))
    add("TRAINING", "Tochi Gi", "PINK", dict(zip(training[:9], [34, 35, 37, 39, 42, 44, 46, 48, 50], strict=True)))
    add("TRAINING", "NKL", "WHITE", dict(zip(training, white_basic, strict=True)))
    add("TRAINING", "NKL", "BLUE", dict(zip(training, [34, 36, 38, 40, 42, 44, 46, 49, 52, 55, 57, 59], strict=True)))
    add("TRAINING", "Matsuru", "WHITE", dict(zip(training, matsuru_white, strict=True)))
    add("TRAINING", "Matsuru", "BLUE", dict(zip(training, [42, 44, 46, 48, 50, 52, 54, 56, 58, 60, 62, 64], strict=True)))
    add("TRAINING", "Matsuru Riscas Rosa", "WHITE_PINK_STRIPES", dict(zip(training, matsuru_white, strict=True)))

    semi = _steps(150, 200, 10)
    for brand in ("Tochi Gi Match", "Fight Art Bushi"):
        add("SEMI_COMPETITION", brand, "WHITE", _by_band(semi, [(170, 57), (200, 60)]))
        add("SEMI_COMPETITION", brand, "BLUE", _by_band(semi, [(170, 67), (200, 70)]))
    add("SEMI_COMPETITION", "Adidas 500", "WHITE", dict(zip(semi, [53, 56, 59, 63, 67, 70], strict=True)))
    add("SEMI_COMPETITION", "Mizuno Hayato", "WHITE", {s: 60 for s in semi})
    add("SEMI_COMPETITION", "Mizuno Hayato", "BLUE", {s: 70 for s in semi})

    contest = _steps(150, 200, 5)
    for brand, white, blue in (("Tochi Gi", 90, 100), ("Matsuru", 95, 105), ("Fight Art Keikogi", 90, 100),
                               ("Adidas Contest", 100, 110)):
        add("COMPETITION_NOT_APPROVED", brand, "WHITE", {s: white for s in contest})
        add("COMPETITION_NOT_APPROVED", brand, "BLUE", {s: blue for s in contest})
    return rows


async def seed_prices(db: AsyncSession, *, club: Club) -> int:
    """Carica il listino di partenza in un club che non ne ha. Non tocca un
    listino che c'è già (anche se la segreteria l'ha svuotato a metà).
    Non fa commit."""
    existing = (await db.execute(
        select(func.count()).select_from(ClubJudogiPrice).where(ClubJudogiPrice.club_id == club.id)
    )).scalar_one()
    if existing:
        return 0
    rows = base_catalog()
    for kind, brand, color, size, cents in rows:
        db.add(ClubJudogiPrice(organization_id=club.organization_id, club_id=club.id, kimono_type=kind,
                               brand=brand, color=color, size_cm=size, price_cents=cents, active=True))
    return len(rows)


# --- Impostazioni e listino -----------------------------------------------------------------------


def settings_of(club: Club) -> dict:
    raw = (club.settings or {}).get("judogi") or {}
    return {
        "customization_cents": int(raw.get("customization_cents", DEFAULT_CUSTOMIZATION_CENTS)),
        "trade_in_percent": int(raw.get("trade_in_percent", DEFAULT_TRADE_IN_PERCENT)),
    }


async def update_settings(db: AsyncSession, *, club: Club, actor_user_id: uuid.UUID, data: dict) -> dict:
    current = settings_of(club)
    custom = data.get("customization_cents", current["customization_cents"])
    pct = data.get("trade_in_percent", current["trade_in_percent"])
    if not (0 <= custom <= 100_000):
        raise ClubValidationError("La personalizzazione va da 0 a 1.000 €.")
    if not (0 <= pct <= 100):
        raise ClubValidationError("La permuta è una percentuale fra 0 e 100.")
    club.settings = {**(club.settings or {}), "judogi": {"customization_cents": custom, "trade_in_percent": pct}}
    await audit_service.record(
        db, organization_id=club.organization_id, actor_user_id=actor_user_id, action="club.judogi_settings_updated",
        entity_type="club", entity_id=str(club.id), previous_value=current, new_value=settings_of(club),
    )
    await db.commit()
    return settings_of(club)


async def price_rows(db: AsyncSession, *, club_id: uuid.UUID, active_only: bool = True) -> list[ClubJudogiPrice]:
    stmt = select(ClubJudogiPrice).where(ClubJudogiPrice.club_id == club_id)
    if active_only:
        stmt = stmt.where(ClubJudogiPrice.active.is_(True))
    stmt = stmt.order_by(ClubJudogiPrice.kimono_type, ClubJudogiPrice.color, ClubJudogiPrice.brand,
                         ClubJudogiPrice.size_cm)
    return list((await db.execute(stmt)).scalars())


def pick_size(sizes: list[int], height_cm: int | None) -> int | None:
    """La taglia per quell'altezza fra quelle che esistono: la prima che non
    è più piccola (il cotone si ritira, i bambini crescono); oltre l'ultima,
    l'ultima. Senza altezza, nessuna scelta."""
    if not sizes or not height_cm:
        return None
    ordered = sorted(sizes)
    return next((s for s in ordered if s >= height_cm), ordered[-1])


def price_tree(rows: list[ClubJudogiPrice], *, height_cm: int | None = None) -> list[dict]:
    """Il listino come lo percorre il calcolatore: tipo → colore → marca →
    taglie con il prezzo, con la taglia consigliata per l'altezza."""
    tree: dict[str, dict[str, dict[str, dict[int, int]]]] = {}
    for r in rows:
        tree.setdefault(r.kimono_type, {}).setdefault(r.color, {}).setdefault(r.brand, {})[r.size_cm] = r.price_cents
    out = []
    for kind in KIMONO_TYPES:
        if kind not in tree:
            continue
        colors = []
        for color in JUDOGI_COLORS:
            brands = tree[kind].get(color)
            if not brands:
                continue
            colors.append({"code": color, "label": COLOR_PT[color], "brands": [
                {
                    "name": brand,
                    "sizes": [{"size_cm": s, "price_cents": p} for s, p in sorted(sizes.items())],
                    "min_price_cents": min(sizes.values()),
                    "suggested_size_cm": pick_size(list(sizes), height_cm),
                    "suggested_price_cents": sizes.get(pick_size(list(sizes), height_cm) or 0),
                }
                for brand, sizes in sorted(brands.items())
            ]})
        out.append({"code": kind, "label": TYPE_PT[kind], "colors": colors,
                    "min_price_cents": min(b["min_price_cents"] for c in colors for b in c["brands"])})
    return out


async def _lookup(db: AsyncSession, *, club_id: uuid.UUID, kind: str, color: str, brand: str,
                  size_cm: int | None, height_cm: int | None, what: str) -> tuple[int, int]:
    """(taglia, prezzo) di un judogi del listino; la taglia, se manca o non
    esiste, è quella giusta per l'altezza (o per la taglia scritta)."""
    if kind not in KIMONO_TYPES:
        raise ClubValidationError(f"Scegli il tipo del {what}.")
    if color not in JUDOGI_COLORS:
        raise ClubValidationError(f"Scegli un colore valido per il {what}.")
    rows = list((await db.execute(select(ClubJudogiPrice).where(
        ClubJudogiPrice.club_id == club_id, ClubJudogiPrice.kimono_type == kind, ClubJudogiPrice.color == color,
        ClubJudogiPrice.brand == brand, ClubJudogiPrice.active.is_(True),
    ))).scalars())
    if not rows:
        raise ClubValidationError(f"Questa marca non c'è nel listino per il {what}: scegline un'altra.")
    prices = {r.size_cm: r.price_cents for r in rows}
    size = size_cm if size_cm in prices else pick_size(list(prices), size_cm or height_cm)
    if size is None:
        raise ClubValidationError(f"Scegli la taglia del {what}.")
    return size, prices[size]


async def quote(db: AsyncSession, *, club: Club, choice: dict, height_cm: int | None = None) -> dict:
    """Il conto del calcolatore, sempre sul server: il browser manda le
    scelte (tipo, colore, marca, taglia o altezza, judogi restituito), mai
    un importo."""
    cfg = settings_of(club)
    kind, color, brand = choice.get("kimono_type"), choice.get("color"), (choice.get("brand") or "").strip()
    size, base = await _lookup(db, club_id=club.id, kind=kind, color=color, brand=brand,
                               size_cm=choice.get("size_cm"), height_cm=height_cm, what="judogi")
    trade = choice.get("trade_in")
    trade_out = None
    discount = 0
    if trade:
        t_brand = (trade.get("brand") or "").strip()
        t_size, value = await _lookup(db, club_id=club.id, kind=trade.get("kimono_type"), color=trade.get("color"),
                                      brand=t_brand, size_cm=trade.get("size_cm"), height_cm=None,
                                      what="judogi restituito")
        # Mezzo centesimo per eccesso, come il round() del PHP.
        discount = (value * cfg["trade_in_percent"] + 50) // 100
        trade_out = {"kimono_type": trade["kimono_type"], "type_label": TYPE_PT[trade["kimono_type"]],
                     "color": trade["color"], "color_label": COLOR_PT[trade["color"]], "brand": t_brand,
                     "size_cm": t_size, "value_cents": value, "percent": cfg["trade_in_percent"],
                     "discount_cents": discount}
    subtotal = base + cfg["customization_cents"]
    return {
        "kimono_type": kind, "type_label": TYPE_PT[kind], "color": color, "color_label": COLOR_PT[color],
        "brand": brand, "size_cm": size, "base_price_cents": base, "customization_cents": cfg["customization_cents"],
        "subtotal_cents": subtotal, "trade_in": trade_out, "trade_in_discount_cents": discount,
        "total_cents": max(0, subtotal - discount),
    }


# --- Chi compra -----------------------------------------------------------------------------------


async def my_athletes(
    db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, today: date,
) -> list[tuple[ClubAthlete, str]]:
    """Gli atleti di chi guarda e che cosa può fare: BUY (il titolare, o
    l'atleta maggiorenne per sé) o WISH (l'atleta minorenne: la lista dei
    desideri)."""
    rows = (await db.execute(select(ClubAthlete).where(
        ClubAthlete.club_id == scope.club_id, ClubAthlete.status == "ACTIVE",
        or_(ClubAthlete.guardian_user_id == user_id, ClubAthlete.user_id == user_id),
    ).order_by(ClubAthlete.first_name))).scalars()
    out = []
    for a in rows:
        if a.guardian_user_id == user_id or age_on(a.birth_date, today) >= ADULT_AGE:
            out.append((a, "BUY"))
        else:
            out.append((a, "WISH"))
    return out


async def athlete_for(
    db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, athlete_id: uuid.UUID, today: date,
) -> tuple[ClubAthlete, str]:
    for a, mode in await my_athletes(db, scope=scope, user_id=user_id, today=today):
        if a.id == athlete_id:
            return a, mode
    raise ClubNotFoundError("Atleta non trovato.")


def name_prefill(athlete: ClubAthlete, today: date) -> str:
    name = (athlete.kimono_name or "").strip() or f"{athlete.first_name} {athlete.last_name}"
    return name.split()[0] if age_on(athlete.birth_date, today) < NAME_RULE_AGE else name


def check_name(name: str, athlete: ClubAthlete, today: date) -> str:
    clean = " ".join((name or "").split())
    if len(clean) < 2:
        raise ClubValidationError("Scrivi il nome da ricamare sul judogi.")
    if len(clean) > 100:
        raise ClubValidationError("Il nome da ricamare è troppo lungo (massimo 100 caratteri).")
    if age_on(athlete.birth_date, today) < NAME_RULE_AGE and len(clean.split()) > 1:
        raise ClubValidationError(
            "Atleta con meno di 13 anni: sul judogi si ricama solo il nome proprio (es.: Afonso)."
        )
    return clean


def athlete_dict(athlete: ClubAthlete, mode: str, today: date) -> dict:
    age = age_on(athlete.birth_date, today)
    return {
        "id": athlete.id, "name": f"{athlete.first_name} {athlete.last_name}", "first_name": athlete.first_name,
        "photo_url": athlete.photo_url, "sex": athlete.sex, "age": age, "height_cm": athlete.height_cm,
        "mode": mode, "kimono_name": name_prefill(athlete, today), "single_name_only": age < NAME_RULE_AGE,
    }


# --- Ordini ---------------------------------------------------------------------------------------


def order_dict(order: ClubEquipmentOrder, athlete: ClubAthlete | None = None, fee: ClubFee | None = None) -> dict:
    return {
        "id": order.id, "athlete_id": order.athlete_id,
        "athlete_name": f"{athlete.first_name} {athlete.last_name}" if athlete else None,
        "kimono_name": order.kimono_name, "kimono_type": order.kimono_type,
        "type_label": TYPE_PT.get(order.kimono_type, order.kimono_type),
        "color": order.color_code, "color_label": order.color, "brand": order.brand, "size_cm": order.size_cm,
        "price_cents": order.price_cents, "base_price_cents": order.base_price_cents,
        "customization_cents": order.customization_cents, "trade_in_discount_cents": order.trade_in_discount_cents,
        "trade_in": order.trade_in, "notes": order.notes, "status": order.status,
        "fee_id": order.fee_id, "fee_status": fee.status if fee else None,
        "delivered_on": order.delivered_on, "created_at": order.created_at,
    }


async def create_order(
    db: AsyncSession, *, scope: ClubScope, club: Club, athlete: ClubAthlete, actor_user_id: uuid.UUID,
    data: dict, today: date, wish: ClubWishlistItem | None = None,
) -> ClubEquipmentOrder:
    """L'ordine del judogi, con il conto rifatto qui e la quota EQUIPMENT
    da pagare. Chi può ordinare lo decide il chiamante (athlete_for: BUY, o
    la segreteria)."""
    q = await quote(db, club=club, choice=data, height_cm=data.get("height_cm") or athlete.height_cm)
    name = check_name(data.get("kimono_name") or "", athlete, today)
    order = ClubEquipmentOrder(
        **scope.columns(), athlete_id=athlete.id, requested_by_user_id=actor_user_id, kimono_name=name,
        kimono_type=q["kimono_type"], color=q["color_label"], color_code=q["color"], brand=q["brand"],
        size_cm=q["size_cm"], price_cents=q["total_cents"], base_price_cents=q["base_price_cents"],
        customization_cents=q["customization_cents"], trade_in_discount_cents=q["trade_in_discount_cents"],
        trade_in=q["trade_in"], notes=(data.get("notes") or "").strip()[:2000] or None, status="PENDING",
    )
    try:
        async with db.begin_nested():
            db.add(order)
            await db.flush()
    except IntegrityError as exc:
        raise ClubValidationError(
            "C'è già un ordine uguale in attesa per questo atleta: lo trovi negli ordini dei judogi."
        ) from exc
    if q["total_cents"] > 0:
        fee = ClubFee(
            **scope.columns(), athlete_id=athlete.id, kind="EQUIPMENT", period=str(order.id),
            description=f"Judogi {q['brand']} {q['color_label']} {q['size_cm']} cm"[:200],
            amount_cents=q["total_cents"], gross_amount_cents=q["subtotal_cents"],
            discount_cents=q["trade_in_discount_cents"],
            discount_note=(f"Devolução de judogi usado −{q['trade_in']['percent']}%" if q["trade_in"] else None),
            due_date=today + timedelta(days=FEE_DUE_DAYS), status="DUE",
        )
        db.add(fee)
        await db.flush()
        order.fee_id = fee.id
    if wish is not None:
        wish.status, wish.equipment_order_id = "ORDERED", order.id
        wish.decided_by_user_id, wish.decided_at = actor_user_id, utcnow()
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id, action="club.judogi_ordered",
        entity_type="club_equipment_order", entity_id=str(order.id),
        new_value={"athlete_id": str(athlete.id), "total_cents": q["total_cents"], "brand": q["brand"],
                   "size_cm": q["size_cm"], "wish_id": str(wish.id) if wish else None},
    )
    await db.commit()
    await db.refresh(order)
    from app.domains.club.clubs import notify_club_staff

    await notify_club_staff(
        db, scope=scope, type_="CLUB_JUDOGI_ORDER", entity_type="club_equipment_order", entity_id=order.id,
        title=f"Novo pedido de judogi: {athlete.first_name} {athlete.last_name}",
        body=f"{q['type_label']} · {q['brand']} {q['color_label']} {q['size_cm']} cm · {q['total_cents'] / 100:.2f} €",
    )
    return order


async def orders_of(db: AsyncSession, *, athlete_ids: list[uuid.UUID]) -> list[dict]:
    if not athlete_ids:
        return []
    rows = (await db.execute(
        select(ClubEquipmentOrder, ClubAthlete, ClubFee)
        .join(ClubAthlete, ClubAthlete.id == ClubEquipmentOrder.athlete_id)
        .outerjoin(ClubFee, ClubFee.id == ClubEquipmentOrder.fee_id)
        .where(ClubEquipmentOrder.athlete_id.in_(athlete_ids))
        .order_by(ClubEquipmentOrder.created_at.desc())
    )).all()
    return [order_dict(o, a, f) for o, a, f in rows]


async def admin_orders(
    db: AsyncSession, *, scope: ClubScope, status: str | None = None, search: str | None = None,
) -> list[dict]:
    stmt = (
        select(ClubEquipmentOrder, ClubAthlete, ClubFee)
        .join(ClubAthlete, ClubAthlete.id == ClubEquipmentOrder.athlete_id)
        .outerjoin(ClubFee, ClubFee.id == ClubEquipmentOrder.fee_id)
        .where(ClubEquipmentOrder.club_id == scope.club_id)
    )
    if status:
        stmt = stmt.where(ClubEquipmentOrder.status == status)
    needle = (search or "").strip()
    if needle:
        like = f"%{needle}%"
        stmt = stmt.where(or_(
            (ClubAthlete.first_name + " " + ClubAthlete.last_name).ilike(like),
            ClubEquipmentOrder.kimono_name.ilike(like), ClubEquipmentOrder.brand.ilike(like),
        ))
    rows = (await db.execute(stmt.order_by(ClubEquipmentOrder.created_at.desc()))).all()
    return [order_dict(o, a, f) for o, a, f in rows]


async def get_order(db: AsyncSession, *, scope: ClubScope, order_id: uuid.UUID) -> ClubEquipmentOrder:
    order = await db.get(ClubEquipmentOrder, order_id)
    if order is None or order.club_id != scope.club_id:
        raise ClubNotFoundError("Ordine non trovato.")
    return order


async def update_order(
    db: AsyncSession, *, scope: ClubScope, order_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict, today: date,
) -> ClubEquipmentOrder:
    """La segreteria porta avanti l'ordine (Pendente → Em preparação →
    Entregue) o lo annulla. Un ordine annullato non torna indietro; la sua
    quota, se non è pagata, se ne va con lui (una pagata resta: il rimborso
    lo decide la segreteria)."""
    from app.domains.notifications import service as notifications_service

    order = await get_order(db, scope=scope, order_id=order_id)
    old = order.status
    status = data.get("status")
    if status is not None and status != old:
        if status not in EQUIPMENT_ORDER_STATUSES:
            raise ClubValidationError("Stato non valido.")
        if old == "CANCELLED":
            raise ClubValidationError("Un ordine annullato non si riapre: creane uno nuovo.")
        if status != "CANCELLED" and order.price_cents is None:
            raise ClubValidationError("Prima di far avanzare l'ordine scrivi il prezzo del judogi.")
        order.status = status
        order.delivered_on = today if status == "DELIVERED" else order.delivered_on
        if status == "CANCELLED" and order.fee_id is not None:
            fee = await db.get(ClubFee, order.fee_id)
            in_proof = fee is not None and (await db.execute(
                select(ClubPaymentProofFee.id).where(ClubPaymentProofFee.fee_id == fee.id).limit(1)
            )).first() is not None
            if fee is not None and fee.status == "DUE" and not in_proof:
                order.fee_id = None
                await db.flush()
                await db.delete(fee)
        athlete = await db.get(ClubAthlete, order.athlete_id)
        if athlete is not None and status in ("IN_PREPARATION", "DELIVERED", "CANCELLED"):
            await notifications_service.notify_user(
                db, organization_id=scope.organization_id, user_id=athlete.guardian_user_id,
                type_="CLUB_JUDOGI_ORDER_STATUS", entity_type="club_equipment_order", entity_id=order.id,
                title=f"Judogi de {athlete.first_name}: {STATUS_PT[status].lower()}",
                body=f"{order.brand} {order.color} {order.size_cm} cm",
            )
    if "price_cents" in data and data["price_cents"] is not None:
        # Solo per gli ordini vecchi senza conto e senza quota: un prezzo
        # nato dal calcolatore non si riscrive.
        if order.fee_id is not None or order.base_price_cents is not None:
            raise ClubValidationError("Il prezzo di questo ordine è già fissato.")
        price = int(data["price_cents"])
        if price < 0:
            raise ClubValidationError("Il prezzo non può essere negativo.")
        order.price_cents = price
        if price > 0 and order.status != "CANCELLED":
            fee = ClubFee(
                **scope.columns(), athlete_id=order.athlete_id, kind="EQUIPMENT", period=str(order.id),
                description=f"Judogi {order.brand} {order.color} {order.size_cm} cm"[:200], amount_cents=price,
                gross_amount_cents=price, due_date=today + timedelta(days=FEE_DUE_DAYS), status="DUE",
            )
            db.add(fee)
            await db.flush()
            order.fee_id = fee.id
    if "internal_notes" in data:
        order.internal_notes = (data["internal_notes"] or "").strip()[:4000] or None
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id, action="club.judogi_order_updated",
        entity_type="club_equipment_order", entity_id=str(order.id),
        previous_value={"status": old}, new_value={"status": order.status, "fields": sorted(data)},
    )
    await db.commit()
    await db.refresh(order)
    return order


def orders_csv(rows: list[dict]) -> str:
    """Per il fornitore: chi, che cosa, che taglia, il nome da ricamare."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Data", "Atleta", "Nome a bordar", "Tipo", "Marca", "Cor", "Tamanho (cm)", "Valor (€)", "Estado",
                "Observações"])
    for r in rows:
        w.writerow([
            r["created_at"].strftime("%d/%m/%Y") if r["created_at"] else "", r["athlete_name"] or "",
            r["kimono_name"], r["type_label"], r["brand"], r["color_label"], r["size_cm"],
            f"{r['price_cents'] / 100:.2f}".replace(".", ",") if r["price_cents"] is not None else "",
            STATUS_PT.get(r["status"], r["status"]), r["notes"] or "",
        ])
    return buf.getvalue()


# --- La segreteria e il listino ---------------------------------------------------------------------


def price_dict(p: ClubJudogiPrice) -> dict:
    return {"id": p.id, "kimono_type": p.kimono_type, "type_label": TYPE_PT[p.kimono_type], "brand": p.brand,
            "color": p.color, "color_label": COLOR_PT[p.color], "size_cm": p.size_cm, "price_cents": p.price_cents,
            "active": p.active}


async def upsert_price(db: AsyncSession, *, scope: ClubScope, actor_user_id: uuid.UUID, data: dict) -> ClubJudogiPrice:
    kind, color, brand = data.get("kimono_type"), data.get("color"), " ".join((data.get("brand") or "").split())
    size, cents = data.get("size_cm"), data.get("price_cents")
    if kind not in KIMONO_TYPES or color not in JUDOGI_COLORS:
        raise ClubValidationError("Scegli tipo e colore.")
    if len(brand) < 2 or len(brand) > 60:
        raise ClubValidationError("Scrivi la marca (da 2 a 60 caratteri).")
    if not isinstance(size, int) or not 80 <= size <= 220:
        raise ClubValidationError("La taglia va da 80 a 220 cm.")
    if not isinstance(cents, int) or not 0 <= cents <= 10_000_000:
        raise ClubValidationError("Il prezzo non è valido.")
    row = (await db.execute(select(ClubJudogiPrice).where(
        ClubJudogiPrice.club_id == scope.club_id, ClubJudogiPrice.kimono_type == kind,
        ClubJudogiPrice.color == color, ClubJudogiPrice.brand == brand, ClubJudogiPrice.size_cm == size,
    ))).scalar_one_or_none()
    if row is None:
        row = ClubJudogiPrice(**scope.columns(), kimono_type=kind, color=color, brand=brand, size_cm=size,
                              price_cents=cents, active=True)
        db.add(row)
    else:
        row.price_cents, row.active = cents, data.get("active", True)
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id, action="club.judogi_price_set",
        entity_type="club", entity_id=str(scope.club_id),
        new_value={"kimono_type": kind, "color": color, "brand": brand, "size_cm": size, "price_cents": cents},
    )
    await db.commit()
    await db.refresh(row)
    return row


async def update_price(
    db: AsyncSession, *, scope: ClubScope, price_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict,
) -> ClubJudogiPrice:
    row = await db.get(ClubJudogiPrice, price_id)
    if row is None or row.club_id != scope.club_id:
        raise ClubNotFoundError("Prezzo non trovato.")
    if data.get("price_cents") is not None:
        cents = int(data["price_cents"])
        if not 0 <= cents <= 10_000_000:
            raise ClubValidationError("Il prezzo non è valido.")
        row.price_cents = cents
    if data.get("active") is not None:
        row.active = bool(data["active"])
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id, action="club.judogi_price_updated",
        entity_type="club", entity_id=str(scope.club_id),
        new_value={"price_id": str(row.id), "price_cents": row.price_cents, "active": row.active},
    )
    await db.commit()
    await db.refresh(row)
    return row


async def delete_price(db: AsyncSession, *, scope: ClubScope, price_id: uuid.UUID, actor_user_id: uuid.UUID) -> None:
    row = await db.get(ClubJudogiPrice, price_id)
    if row is None or row.club_id != scope.club_id:
        raise ClubNotFoundError("Prezzo non trovato.")
    await db.delete(row)
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id, action="club.judogi_price_deleted",
        entity_type="club", entity_id=str(scope.club_id),
        previous_value={"kimono_type": row.kimono_type, "brand": row.brand, "color": row.color, "size_cm": row.size_cm},
    )
    await db.commit()


# --- La lista dei desideri ----------------------------------------------------------------------------


async def _product(db: AsyncSession, *, scope: ClubScope, product_id: uuid.UUID):
    from app.domains.jav_market.models import JavMarketProduct

    product = await db.get(JavMarketProduct, product_id)
    if (product is None or product.organization_id != scope.organization_id or product.status != "ACTIVE"
            or product.club_id not in (None, scope.club_id)):
        raise ClubNotFoundError("Prodotto non trovato.")
    return product


async def add_wish(
    db: AsyncSession, *, scope: ClubScope, club: Club, athlete: ClubAthlete, actor_user_id: uuid.UUID, data: dict,
) -> ClubWishlistItem:
    """Il cuore sul prodotto (o «Quero este judogi»): il desiderio e la
    notifica al titolare. Lo stesso prodotto due volte resta uno; un judogi
    nuovo sostituisce quello di prima."""
    from app.domains.notifications import service as notifications_service

    kind = data.get("kind")
    note = (data.get("note") or "").strip()[:300] or None
    if kind == "PRODUCT":
        product = await _product(db, scope=scope, product_id=data.get("product_id"))
        existing = (await db.execute(select(ClubWishlistItem).where(
            ClubWishlistItem.athlete_id == athlete.id, ClubWishlistItem.kind == "PRODUCT",
            ClubWishlistItem.product_id == product.id, ClubWishlistItem.status == "OPEN",
        ))).scalar_one_or_none()
        if existing is not None:
            existing.variant_id = data.get("variant_id") or existing.variant_id
            existing.note = note or existing.note
            await db.commit()
            return existing
        wish = ClubWishlistItem(**scope.columns(), athlete_id=athlete.id, requested_by_user_id=actor_user_id,
                                kind="PRODUCT", product_id=product.id, variant_id=data.get("variant_id"), note=note)
        label = product.name
    elif kind == "JUDOGI":
        choice = data.get("judogi") or {}
        q = await quote(db, club=club, choice=choice, height_cm=athlete.height_cm)
        config = {"choice": {k: choice.get(k) for k in ("kimono_type", "color", "brand", "size_cm", "trade_in")},
                  "kimono_name": (choice.get("kimono_name") or "").strip()[:100] or None, "quote": q}
        existing = (await db.execute(select(ClubWishlistItem).where(
            ClubWishlistItem.athlete_id == athlete.id, ClubWishlistItem.kind == "JUDOGI",
            ClubWishlistItem.status == "OPEN",
        ))).scalar_one_or_none()
        label = f"{q['type_label']} {q['brand']} {q['color_label']} {q['size_cm']} cm"
        if existing is not None:
            existing.config, existing.note = config, note
            wish = existing
        else:
            wish = ClubWishlistItem(**scope.columns(), athlete_id=athlete.id, requested_by_user_id=actor_user_id,
                                    kind="JUDOGI", config=config, note=note)
    else:
        raise ClubValidationError("Che cosa vuoi aggiungere alla lista?")
    try:
        async with db.begin_nested():
            db.add(wish)
            await db.flush()
    except IntegrityError as exc:
        raise ClubValidationError("È già nella lista dei desideri.") from exc
    if actor_user_id != athlete.guardian_user_id:
        await notifications_service.notify_user(
            db, organization_id=scope.organization_id, user_id=athlete.guardian_user_id, type_="CLUB_WISHLIST_ADDED",
            entity_type="club_wishlist_item", entity_id=wish.id,
            title=f"{athlete.first_name} adicionou um desejo: {label}"[:200],
            body="Está na lista de desejos da Loja: pode encomendar ou recusar.",
        )
    await db.commit()
    await db.refresh(wish)
    return wish


async def list_wishes(db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, today: date) -> list[dict]:
    """I desideri degli atleti di chi guarda: aperti prima, poi gli ultimi
    decisi (90 giorni)."""
    from app.domains.jav_market.models import JavMarketProduct, JavMarketVariant

    mine = {a.id: (a, mode) for a, mode in await my_athletes(db, scope=scope, user_id=user_id, today=today)}
    if not mine:
        return []
    since = utcnow() - timedelta(days=90)
    rows = (await db.execute(
        select(ClubWishlistItem, JavMarketProduct, JavMarketVariant)
        .outerjoin(JavMarketProduct, JavMarketProduct.id == ClubWishlistItem.product_id)
        .outerjoin(JavMarketVariant, JavMarketVariant.id == ClubWishlistItem.variant_id)
        .where(ClubWishlistItem.athlete_id.in_(list(mine)),
               or_(ClubWishlistItem.status == "OPEN", ClubWishlistItem.created_at >= since))
        .order_by(ClubWishlistItem.status != "OPEN", ClubWishlistItem.created_at.desc())
    )).all()
    out = []
    for w, product, variant in rows:
        athlete, mode = mine[w.athlete_id]
        is_guardian = athlete.guardian_user_id == user_id
        out.append({
            "id": w.id, "kind": w.kind, "status": w.status, "note": w.note, "created_at": w.created_at,
            "athlete_id": athlete.id, "athlete_name": f"{athlete.first_name} {athlete.last_name}",
            "athlete_first_name": athlete.first_name,
            "product": {"id": product.id, "name": product.name, "image_url": product.image_url,
                        "available": product.status == "ACTIVE"} if product else None,
            "variant": {"id": variant.id, "label": variant.label, "price_cents": variant.price_cents} if variant else None,
            "judogi": w.config,
            "equipment_order_id": w.equipment_order_id, "jav_market_order_id": w.jav_market_order_id,
            "can_decide": is_guardian or mode == "BUY",
            "can_remove": w.status == "OPEN" and (is_guardian or w.requested_by_user_id == user_id),
        })
    return out


async def get_wish(
    db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, wish_id: uuid.UUID, today: date,
) -> tuple[ClubWishlistItem, ClubAthlete, str]:
    wish = await db.get(ClubWishlistItem, wish_id)
    if wish is None or wish.club_id != scope.club_id:
        raise ClubNotFoundError("Desiderio non trovato.")
    athlete, mode = await athlete_for(db, scope=scope, user_id=user_id, athlete_id=wish.athlete_id, today=today)
    return wish, athlete, mode


async def decide_wish(
    db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, wish_id: uuid.UUID, status: str, today: date,
) -> ClubWishlistItem:
    """Il titolare segna il desiderio «comprato» (fuori dall'app, o con un
    ordine già fatto) o lo rifiuta."""
    from app.domains.notifications import service as notifications_service

    wish, athlete, mode = await get_wish(db, scope=scope, user_id=user_id, wish_id=wish_id, today=today)
    if mode != "BUY":
        raise ClubValidationError("Lo decide chi paga: il titolare del conto.")
    if status not in ("ORDERED", "DISMISSED"):
        raise ClubValidationError("Scelta non valida.")
    if wish.status != "OPEN":
        raise ClubValidationError("Questo desiderio è già stato deciso.")
    wish.status, wish.decided_by_user_id, wish.decided_at = status, user_id, utcnow()
    if athlete.user_id and athlete.user_id != user_id:
        await notifications_service.notify_user(
            db, organization_id=scope.organization_id, user_id=athlete.user_id, type_="CLUB_WISHLIST_DECIDED",
            entity_type="club_wishlist_item", entity_id=wish.id,
            title="O teu desejo foi aceite!" if status == "ORDERED" else "O teu desejo ficou para outra vez",
        )
    await db.commit()
    await db.refresh(wish)
    return wish


async def remove_wish(db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, wish_id: uuid.UUID, today: date) -> None:
    wish, athlete, _mode = await get_wish(db, scope=scope, user_id=user_id, wish_id=wish_id, today=today)
    if wish.status != "OPEN" or (athlete.guardian_user_id != user_id and wish.requested_by_user_id != user_id):
        raise ClubValidationError("Questo desiderio non si può più togliere.")
    await db.delete(wish)
    await db.commit()


async def mark_products_ordered(
    db: AsyncSession, *, athlete_id: uuid.UUID, product_ids: set[uuid.UUID], order_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> None:
    """Un ordine dello Shop per un atleta chiude i suoi desideri di quei
    prodotti (jav_market/service.create_order). Non fa commit."""
    if not product_ids:
        return
    for wish in (await db.execute(select(ClubWishlistItem).where(
        ClubWishlistItem.athlete_id == athlete_id, ClubWishlistItem.kind == "PRODUCT",
        ClubWishlistItem.status == "OPEN", ClubWishlistItem.product_id.in_(product_ids),
    ))).scalars():
        wish.status, wish.jav_market_order_id = "ORDERED", order_id
        wish.decided_by_user_id, wish.decided_at = actor_user_id, utcnow()
