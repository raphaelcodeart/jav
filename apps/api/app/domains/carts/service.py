"""Il carrello: cosa c'è dentro, quanto costa, e come diventa un ordine.

Questo dominio non conosce i prezzi. Sa quali righe ha un cliente e a quale
negozio appartengono; per sapere quanto costano chiede al negozio, che è
l'unico posto dove quel calcolo esiste (`jav_market.get_quote`). È la stessa
separazione che c'è fra i negozi e `marketplaces/rules.py`: le regole comuni
in un posto, il listino di ciascuno a casa propria.

Il registro `SHOPS` in fondo è l'unico punto da toccare per dare il
carrello a un negozio in più: la colonna che la riga usa, la funzione che
fa il preventivo, quella che crea l'ordine. Tutto il resto -- API, conteggi,
la finestra del carrello -- funziona già.

**Il carrello non conserva prezzi.** Ogni lettura li ricalcola dal listino
di adesso. Costa una query in più e in cambio nessuno può mettere qualcosa
nel carrello a gennaio e pretenderlo a quel prezzo a giugno, né manomettere
un importo dal browser (CLAUDE.md §5).
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.carts.models import CART_SHOPS, MAX_ITEM_QUANTITY, Cart, CartItem
from app.domains.jav_market import service as jav_market_service


class CartValidationError(ValueError):
    """Un messaggio già scritto per il cliente, in italiano (CLAUDE.md §6)."""


class CartNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class ShopBinding:
    """Come un negozio si attacca al carrello."""

    #: La colonna di `cart_items` che punta alla variante di questo negozio.
    column: str
    #: Il preventivo del negozio, chiamato con `lines=[(variant_id, qty), ...]`.
    quote: Callable[..., Awaitable[dict]]
    #: L'eccezione che quel negozio solleva quando una riga non è vendibile.
    errors: tuple[type[Exception], ...]


SHOPS: dict[str, ShopBinding] = {
    "jav_market": ShopBinding(
        column="jav_market_variant_id",
        quote=jav_market_service.get_quote,
        errors=(jav_market_service.JavMarketValidationError, jav_market_service.JavMarketNotFoundError),
    ),
}


def _binding(shop: str) -> ShopBinding:
    if shop not in CART_SHOPS:
        raise CartValidationError("Negozio sconosciuto.")
    binding = SHOPS.get(shop)
    if binding is None:
        raise CartValidationError("Il carrello non è ancora attivo su questo negozio.")
    return binding


# --- Il contenuto ---------------------------------------------------------------------------------


async def get_or_create_cart(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID, shop: str
) -> Cart:
    """Il carrello aperto del cliente su quel negozio, creato se non c'è.

    Il vincolo UNIQUE(customer_user_id, shop) è ciò che rende questa
    funzione sicura anche con due richieste contemporanee: la seconda
    fallisce sull'inserimento e rilegge quella della prima, invece di
    lasciare due carrelli e metà articoli in ciascuno."""
    _binding(shop)
    found = await db.execute(
        select(Cart).where(Cart.customer_user_id == customer_user_id, Cart.shop == shop)
    )
    cart = found.scalar_one_or_none()
    if cart is not None:
        return cart
    cart = Cart(organization_id=organization_id, customer_user_id=customer_user_id, shop=shop)
    db.add(cart)
    try:
        await db.flush()
    except Exception:
        await db.rollback()
        found = await db.execute(
            select(Cart).where(Cart.customer_user_id == customer_user_id, Cart.shop == shop)
        )
        cart = found.scalar_one_or_none()
        if cart is None:
            raise
    return cart


async def _items(db: AsyncSession, cart: Cart) -> list[CartItem]:
    rows = await db.execute(
        select(CartItem).where(CartItem.cart_id == cart.id).order_by(CartItem.created_at, CartItem.id)
    )
    return list(rows.scalars().all())


def _variant_id(item: CartItem, binding: ShopBinding) -> uuid.UUID:
    return getattr(item, binding.column)


async def add_item(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_user_id: uuid.UUID,
    shop: str,
    variant_id: uuid.UUID,
    quantity: int = 1,
) -> Cart:
    """Aggiunge o aumenta una riga.

    L'articolo si controlla **prima** di finire nel carrello, chiedendo al
    negozio un preventivo per quella riga: così un prodotto spento,
    esaurito o di un'altra organizzazione viene respinto subito, con il suo
    messaggio, invece di restare nel carrello e far fallire il checkout.
    """
    binding = _binding(shop)
    if quantity < 1:
        raise CartValidationError("La quantità deve essere almeno 1.")
    cart = await get_or_create_cart(
        db, organization_id=organization_id, customer_user_id=customer_user_id, shop=shop
    )
    existing = await db.execute(
        select(CartItem).where(
            CartItem.cart_id == cart.id, getattr(CartItem, binding.column) == variant_id
        )
    )
    item = existing.scalar_one_or_none()
    wanted = (item.quantity if item else 0) + quantity
    if wanted > MAX_ITEM_QUANTITY:
        raise CartValidationError(f"Al massimo {MAX_ITEM_QUANTITY} pezzi dello stesso articolo.")
    try:
        await binding.quote(
            db, organization_id=organization_id, customer_user_id=customer_user_id,
            lines=[(variant_id, wanted)],
        )
    except binding.errors as exc:
        raise CartValidationError(str(exc)) from exc
    if item is None:
        item = CartItem(cart_id=cart.id, quantity=wanted, **{binding.column: variant_id})
        db.add(item)
    else:
        item.quantity = wanted
    await db.commit()
    return cart


async def set_quantity(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_user_id: uuid.UUID,
    shop: str,
    item_id: uuid.UUID,
    quantity: int,
) -> None:
    """Cambia la quantità di una riga; a zero la riga sparisce, che è quello
    che un cliente si aspetta portando il contatore a zero."""
    binding = _binding(shop)
    item, _cart = await _owned_item(db, customer_user_id=customer_user_id, shop=shop, item_id=item_id)
    if quantity <= 0:
        await db.delete(item)
        await db.commit()
        return
    if quantity > MAX_ITEM_QUANTITY:
        raise CartValidationError(f"Al massimo {MAX_ITEM_QUANTITY} pezzi dello stesso articolo.")
    try:
        await binding.quote(
            db, organization_id=organization_id, customer_user_id=customer_user_id,
            lines=[(_variant_id(item, binding), quantity)],
        )
    except binding.errors as exc:
        raise CartValidationError(str(exc)) from exc
    item.quantity = quantity
    await db.commit()


async def remove_item(
    db: AsyncSession, *, customer_user_id: uuid.UUID, shop: str, item_id: uuid.UUID
) -> None:
    item, _ = await _owned_item(db, customer_user_id=customer_user_id, shop=shop, item_id=item_id)
    await db.delete(item)
    await db.commit()


async def clear(db: AsyncSession, *, customer_user_id: uuid.UUID, shop: str) -> None:
    found = await db.execute(select(Cart).where(Cart.customer_user_id == customer_user_id, Cart.shop == shop))
    cart = found.scalar_one_or_none()
    if cart is None:
        return
    for item in await _items(db, cart):
        await db.delete(item)
    await db.commit()


async def _owned_item(
    db: AsyncSession, *, customer_user_id: uuid.UUID, shop: str, item_id: uuid.UUID
) -> tuple[CartItem, Cart]:
    """La riga, ma solo se è davvero di chi la sta toccando. Il controllo è
    qui e non nel router perché è l'unico posto da cui si passa sempre."""
    item = await db.get(CartItem, item_id)
    cart = await db.get(Cart, item.cart_id) if item is not None else None
    if item is None or cart is None or cart.customer_user_id != customer_user_id or cart.shop != shop:
        raise CartNotFoundError("Articolo non presente nel carrello.")
    return item, cart


# --- Quanto costa ---------------------------------------------------------------------------------


async def shop_section(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID, shop: str
) -> dict | None:
    """Il carrello di un negozio, con i prezzi di adesso. `None` se è vuoto.

    Se una riga nel frattempo è diventata invendibile -- prodotto spento,
    variante esaurita -- il preventivo di gruppo fallisce. In quel caso si
    ripiega su un preventivo per riga, per **dire quale**: un carrello che
    si rifiuta di aprirsi senza spiegare perché è un vicolo cieco, e il
    cliente non ha modo di uscirne se non svuotando tutto.
    """
    binding = _binding(shop)
    found = await db.execute(select(Cart).where(Cart.customer_user_id == customer_user_id, Cart.shop == shop))
    cart = found.scalar_one_or_none()
    if cart is None:
        return None
    items = await _items(db, cart)
    if not items:
        return None

    lines = [(_variant_id(item, binding), item.quantity) for item in items]
    by_variant = {_variant_id(item, binding): item for item in items}
    try:
        quote = await binding.quote(
            db, organization_id=organization_id, customer_user_id=customer_user_id, lines=lines
        )
    except binding.errors:
        return await _section_with_problems(
            db, binding=binding, organization_id=organization_id, customer_user_id=customer_user_id,
            cart=cart, items=items,
        )
    for entry in quote["items"]:
        entry["cart_item_id"] = by_variant[entry["variant_id"]].id
        entry["available"] = True
        entry["unavailable_reason"] = None
    # Un negozio con l'ordine minimo («Fai la Spesa») lo dice nel
    # preventivo invece di rifiutarlo: il carrello resta apribile e spiega
    # quanto manca; è la creazione dell'ordine a bloccare davvero.
    problems: list[str] = []
    if quote.get("min_order_missing_cents", 0) > 0:
        problems.append(jav_market_service.min_order_message(quote["min_order_missing_cents"], quote["min_order_cents"]))
    return {"cart_id": cart.id, "shop": shop, "purchasable": not problems, "problems": problems, **quote}


async def _section_with_problems(
    db: AsyncSession,
    *,
    binding: ShopBinding,
    organization_id: uuid.UUID,
    customer_user_id: uuid.UUID,
    cart: Cart,
    items: list[CartItem],
) -> dict:
    """Riga per riga, per distinguere quelle ancora acquistabili da quelle
    che non lo sono più. Il carrello resta apribile e dice cosa togliere."""
    entries: list[dict] = []
    problems: list[str] = []
    good: list[tuple[uuid.UUID, int]] = []
    for item in items:
        variant_id = _variant_id(item, binding)
        try:
            one = await binding.quote(
                db, organization_id=organization_id, customer_user_id=customer_user_id,
                lines=[(variant_id, item.quantity)],
            )
        except binding.errors as exc:
            entries.append(
                {
                    "cart_item_id": item.id,
                    "variant_id": variant_id,
                    "product_name": "Articolo non più disponibile",
                    "variant_label": None,
                    "image_url": None,
                    "quantity": item.quantity,
                    "unit_price_cents": 0,
                    "line_total_cents": 0,
                    "credit_discount_percentage": 0,
                    "available": False,
                    "unavailable_reason": str(exc),
                }
            )
            problems.append(str(exc))
            continue
        entry = one["items"][0]
        entry["cart_item_id"] = item.id
        entry["available"] = True
        entry["unavailable_reason"] = None
        entries.append(entry)
        good.append((variant_id, item.quantity))

    totals: dict[str, Any] = {}
    if good:
        totals = await binding.quote(
            db, organization_id=organization_id, customer_user_id=customer_user_id, lines=good
        )
        totals.pop("items", None)
    return {
        "cart_id": cart.id,
        "shop": cart.shop,
        # Con una riga rotta non si paga: o la si toglie, o si cambia
        # quantità. Lasciar pagare il resto in silenzio vorrebbe dire
        # consegnare un ordine diverso da quello che il cliente ha composto.
        "purchasable": False,
        "problems": problems,
        "items": entries,
        **totals,
    }


async def summary(db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID) -> dict:
    """Tutto il carrello del cliente: una sezione per negozio, più i totali
    che vanno sull'icona in alto."""
    sections = []
    for shop in CART_SHOPS:
        if shop not in SHOPS:
            continue
        section = await shop_section(
            db, organization_id=organization_id, customer_user_id=customer_user_id, shop=shop
        )
        if section is not None:
            sections.append(section)
    return {
        "sections": sections,
        "item_count": sum(sum(i["quantity"] for i in s["items"]) for s in sections),
        "total_cents": sum(s.get("amount_cents", 0) for s in sections),
    }


async def checkout_lines(
    db: AsyncSession, *, customer_user_id: uuid.UUID, shop: str
) -> tuple[Cart, list[tuple[uuid.UUID, int]]]:
    """Le righe da passare al negozio per creare l'ordine. Non calcola
    nulla: il prezzo lo rifà il negozio, sul listino di quel momento, ed è
    quello che finisce congelato sull'ordine."""
    binding = _binding(shop)
    found = await db.execute(select(Cart).where(Cart.customer_user_id == customer_user_id, Cart.shop == shop))
    cart = found.scalar_one_or_none()
    items = await _items(db, cart) if cart is not None else []
    if cart is None or not items:
        raise CartValidationError("Il carrello è vuoto.")
    return cart, [(_variant_id(item, binding), item.quantity) for item in items]
