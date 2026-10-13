"""From AliExpress' figure to what the customer pays in EUR.

    base  = the SKU's dropshipping price (what we pay AliExpress) or its
            list price, per AliexpressSettings.price_basis -- the list price
            when the answer carries no dropshipping price
    price = base x rate x (1 + markup%) + fixed markup
            then rounded UP to x,90 / x,99 (or to the cent)

La spedizione non è qui: dalla Session 76 è il costo reale che AliExpress
quota per quel carrello, con un minimo configurabile -- vedi
charged_shipping_cents() in fondo.

Same rules as shopify_dropshipping/pricing.py: rounding only goes up,
integer cents and Decimal, never a float.
"""

from decimal import ROUND_CEILING, Decimal

from app.domains.aliexpress_dropshipping.models import AliexpressSettings


def _round_up(cents: int, rounding: str) -> int:
    if rounding not in ("90", "99"):
        return cents
    target = int(rounding)
    euros, rest = divmod(cents, 100)
    return euros * 100 + target if rest <= target else (euros + 1) * 100 + target


def base_amount(*, cost: Decimal | None, price: Decimal, settings: AliexpressSettings) -> Decimal:
    if settings.price_basis == "COST" and cost is not None and Decimal(cost) > 0:
        return Decimal(cost)
    return Decimal(price)


def to_eur_cents(amount: Decimal | float | str, rate: Decimal) -> int:
    cents = Decimal(str(amount)) * Decimal(rate) * 100
    return int(cents.to_integral_value(rounding=ROUND_CEILING))


def sale_price_cents(
    *,
    cost: Decimal | None,
    price: Decimal,
    settings: AliexpressSettings,
    markup_percentage: int | None = None,
) -> int:
    """The price of one unit; `markup_percentage` overrides the organization's."""
    markup = settings.markup_percentage if markup_percentage is None else markup_percentage
    rate = Decimal(settings.currency_rate)
    base = base_amount(cost=cost, price=price, settings=settings)
    cents = base * rate * 100 * (Decimal(100 + markup) / 100) + Decimal(settings.markup_fixed_cents or 0)
    if settings.shipping_mode == "INCLUDED":
        # Col prezzo non si sa ancora la quantità né la destinazione, quindi
        # qui il minimo è l'unica stima disponibile: è il caso in cui la
        # spedizione è "inclusa nel prezzo" e al checkout non si addebita.
        cents += Decimal(settings.shipping_minimum_cents or 0)
    return _round_up(int(cents.to_integral_value(rounding=ROUND_CEILING)), settings.price_rounding)


def charged_shipping_cents(*, supplier_cents: int, settings: AliexpressSettings) -> int:
    """Quanto il cliente paga di spedizione su un ordine (Session 76).

        addebitata = max(costo reale AliExpress, minimo configurato)

    `supplier_cents` è il costo reale dell'**intero ordine**, già sommato
    riga per riga da chi chiama: il minimo si applica una volta sola sul
    totale, mai per articolo. Tre prodotti da 1,20 di spedizione fanno 3,60
    di costo reale e 5,90 addebitati, non 17,70.

    Con la spedizione inclusa nel prezzo non si addebita nulla: il minimo è
    già dentro il listino (vedi sale_price_cents).

    Il minimo non è un valore di ripiego: chi non riesce a sapere il costo
    reale non deve chiamare questa funzione con zero, deve fermarsi. Uno
    zero qui vorrebbe dire "AliExpress spedisce gratis", e si finirebbe a
    incassare 5,90 su una spedizione da 20 euro.
    """
    if settings.shipping_mode == "INCLUDED":
        return 0
    return max(int(supplier_cents), settings.shipping_minimum_cents or 0)
