"""Rules shared by the shops with a cart -- today the Shop (`jav_market`,
catalog written by the administrator) -- kept apart from the shop itself so
a second shop added later inherits them instead of copying them.

Each shop keeps its own tables; what the customer is promised is the same
everywhere, and lives here:

- **No discount for paying by bank transfer** (business decision: "non
  possiamo fare sconto se paghi con bonifico"): bank transfer is the only
  method and the price is the same for everyone. The
  `bank_transfer_discount_cents` columns stay on the orders, always 0. See
  docs/business-rules.md#marketplace.
- **JavCash only partly.** These products never earn cashback, they only
  let the customer spend it, and never for the whole price: a new product
  starts at DEFAULT_CREDIT_PERCENTAGE, the administrator may raise it up to
  MAX_CREDIT_PERCENTAGE.
- **Il prezzo esposto e' l'imponibile: l'IVA si aggiunge** (decisione
  dell'utente). In vetrina si
  legge «17,90 € + IVA» e al checkout il preventivo porta la riga dell'IVA
  fra gli addendi: 17,90 + 3,94 = 21,84. Gli era stato fatto presente che
  verso un consumatore il Codice del Consumo (artt. 14-15) vuole il prezzo
  finale; la scelta e' sua, ed e' per questo che il «+ IVA» accanto al
  prezzo non e' facoltativo: e' cio' che evita al cliente la sorpresa del
  22% al momento di pagare.
  **La spedizione resta fuori dall'IVA** (scelta dell'utente; l'art. 12 DPR
  633/72 vorrebbe che seguisse l'aliquota del bene).
  **Ne' i JavCash ne' lo sconto bonifico abbassano l'imponibile**: l'IVA si
  calcola sulla merce a prezzo pieno e si congela alla creazione
  dell'ordine, le due riduzioni agiscono sul pagamento e non sul prezzo.
  E' l'opzione (a) scelta il 21/09/2026, coerente con il trattamento che i
  JavCash avevano gia'.
  Gli ordini creati prima di questo cambio hanno l'IVA **contenuta** nel
  totale: `vat_mode` sull'ordine dice quale delle due regole vale, perche'
  le stesse colonne hanno altrimenti significato opposto.
- **Names in the Shop** are settings, with the defaults in DEFAULT_LABELS.

Organization-level settings, in `organizations.settings` (JSONB):
`marketplace_vat_percentage`, `marketplace_labels`.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.organizations.models import Organization

#: No discount for a bank transfer, anywhere -- see the docstring.
#: Kept as a named 0 so every shop still reads it from one place.
DEFAULT_BANK_TRANSFER_DISCOUNT_PERCENTAGE = 0
MAX_BANK_TRANSFER_DISCOUNT_PERCENTAGE = 0
#: The ordinary Italian rate, added to the price shown -- see the module
#: docstring.
DEFAULT_VAT_PERCENTAGE = 22
#: No Italian rate comes anywhere near this; the ceiling is here so a typo
#: in the admin form cannot restate every order of the shop.
MAX_VAT_PERCENTAGE = 30
#: JavCash usable on a new Shop product, percent of its price.
DEFAULT_CREDIT_PERCENTAGE = 30
#: Never 100: a Shop product is never bought entirely with JavCash.
MAX_CREDIT_PERCENTAGE = 99

#: Lo Shop, con il catalogo scritto a mano dall'amministratore.
JAV_MARKET = "jav_market"
MARKETPLACES = (JAV_MARKET,)
DEFAULT_LABELS = {
    JAV_MARKET: "Fai la Spesa con Jav",
}

#: The Shop's own sections -- the ones backed by `catalog.products`,
#: not by a shop with its own tables. Each can be switched off and renamed from
#: the admin, exactly like the shop tabs, because an organization may simply
#: not sell one of them. The keys are the `Product.category` values
#: in lower case; the INTERNAL section is the Jav contracts.
INTERNAL = "internal"
PARTNER = "partner"
DROPSHIPPING = "dropshipping"
SECTIONS = (INTERNAL, PARTNER, DROPSHIPPING)
DEFAULT_SECTION_LABELS = {
    INTERNAL: "Jav",
    PARTNER: "Prodotti Partner",
    DROPSHIPPING: "Offerte Jav",
}


class CreditPercentageError(ValueError):
    pass


def check_credit_percentage(value: int) -> int:
    """Refuses a JavCash share a Shop product may not have."""
    if value < 0 or value > MAX_CREDIT_PERCENTAGE:
        raise CreditPercentageError(
            f"Sui prodotti dello Shop il JavCash può coprire al massimo il {MAX_CREDIT_PERCENTAGE}% del prezzo."
        )
    return value


def bank_transfer_discount_cents(*, residual_cents: int, percentage: int) -> int:
    """What paying by bank transfer takes off: nothing,
    whatever percentage a caller or an old stored setting passes in."""
    return 0


def vat_included_cents(*, gross_cents: int, percentage: int) -> int:
    """The VAT *contained in* a VAT-inclusive amount: gross x pct / (100 +
    pct), rounded half up to the cent the way an Italian invoice rounds
    (18,20 EUR at 22% -> 3,28 EUR). Not gross x pct / 100: the price the
    customer reads already includes the tax, so dividing by 100 would
    invent VAT that was never charged.

    Integer arithmetic, like the discount above: floor((2n + d) / 2d) is
    half-up on n/d, and no binary float ever gets near a fiscal figure.
    Nothing on a zero amount or a zero rate."""
    if gross_cents <= 0 or percentage <= 0:
        return 0
    denominator = 100 + percentage
    return (2 * gross_cents * percentage + denominator) // (2 * denominator)


#: Come l'IVA si rapporta al prezzo su un ordine. Sta sull'ordine perche' la
#: regola e' cambiata nel tempo e gli ordini passati non si riscrivono:
#: `INCLUDED` e' la regola precedente, `ADDED` quella di oggi.
VAT_MODES = ("INCLUDED", "ADDED")
DEFAULT_VAT_MODE = "ADDED"


def vat_added_cents(*, net_cents: int, percentage: int) -> int:
    """L'IVA da **aggiungere** a un imponibile: net x pct / 100, arrotondata
    a mezzo centesimo per eccesso come fa una fattura italiana (17,90 al 22%
    -> 3,94).

    Speculare a `vat_included_cents`, che resta per rileggere gli ordini
    creati quando il prezzo esposto era quello finale. Le due non si possono
    confondere: su 17,90 questa da' 3,94 e quella 3,23. E' il motivo per cui
    ogni ordine porta il suo `vat_mode`.

    Aritmetica intera, come la gemella: nessun decimale binario si avvicina
    a una cifra fiscale."""
    if net_cents <= 0 or percentage <= 0:
        return 0
    return (2 * net_cents * percentage + 100) // 200


async def _settings(db: AsyncSession, organization_id: uuid.UUID) -> dict:
    org = await db.get(Organization, organization_id)
    return dict(org.settings or {}) if org is not None else {}


async def get_bank_transfer_discount_percentage(db: AsyncSession, *, organization_id: uuid.UUID) -> int:
    """Always 0, whatever `organizations.settings` still
    holds from before: there is no discount for paying by bank transfer."""
    return 0


async def get_vat_percentage(db: AsyncSession, *, organization_id: uuid.UUID) -> int:
    """The VAT rate added to the Shop prices, 22 until an
    administrator says otherwise. Same shape as the discount above: a
    stored value that no longer makes sense falls back to the default
    rather than making every order of the shop unsellable."""
    value = (await _settings(db, organization_id)).get("marketplace_vat_percentage")
    if value is None:
        return DEFAULT_VAT_PERCENTAGE
    try:
        return max(0, min(MAX_VAT_PERCENTAGE, int(value)))
    except (TypeError, ValueError):
        return DEFAULT_VAT_PERCENTAGE


async def get_labels(db: AsyncSession, *, organization_id: uuid.UUID) -> dict[str, str]:
    stored = (await _settings(db, organization_id)).get("marketplace_labels") or {}
    return {
        key: (str(stored.get(key)).strip() if stored.get(key) and str(stored.get(key)).strip() else DEFAULT_LABELS[key])
        for key in MARKETPLACES
    }


async def get_sections(db: AsyncSession, *, organization_id: uuid.UUID) -> dict[str, dict]:
    """Name and on/off of each Shop section. Everything is on until an
    administrator says otherwise: a new organization must see its own
    catalog without configuring anything first."""
    stored = (await _settings(db, organization_id)).get("shop_sections") or {}
    sections = {}
    for key in SECTIONS:
        saved = stored.get(key) if isinstance(stored.get(key), dict) else {}
        label = str(saved.get("label") or "").strip()
        sections[key] = {
            "label": label or DEFAULT_SECTION_LABELS[key],
            "enabled": bool(saved.get("enabled", True)),
        }
    return sections


async def get_config(db: AsyncSession, *, organization_id: uuid.UUID) -> dict:
    return {
        "labels": await get_labels(db, organization_id=organization_id),
        "sections": await get_sections(db, organization_id=organization_id),
        "bank_transfer_discount_percentage": await get_bank_transfer_discount_percentage(
            db, organization_id=organization_id
        ),
        "vat_percentage": await get_vat_percentage(db, organization_id=organization_id),
        "default_credit_percentage": DEFAULT_CREDIT_PERCENTAGE,
        "max_credit_percentage": MAX_CREDIT_PERCENTAGE,
    }


async def update_config(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    labels: dict[str, str] | None,
    bank_transfer_discount_percentage: int | None,
    sections: dict[str, dict] | None = None,
    vat_percentage: int | None = None,
) -> dict:
    org = await db.get(Organization, organization_id)
    if org is None:
        raise ValueError("Organization not found")
    settings = dict(org.settings or {})
    if labels is not None:
        current = dict(settings.get("marketplace_labels") or {})
        for key, value in labels.items():
            if key in MARKETPLACES:
                current[key] = (value or "").strip()[:40] or DEFAULT_LABELS[key]
        settings["marketplace_labels"] = current
    if sections is not None:
        current_sections = dict(settings.get("shop_sections") or {})
        for key, value in sections.items():
            if key not in SECTIONS or not isinstance(value, dict):
                continue
            saved = dict(current_sections.get(key) or {})
            if "label" in value:
                saved["label"] = (str(value["label"] or "")).strip()[:40] or DEFAULT_SECTION_LABELS[key]
            if "enabled" in value:
                saved["enabled"] = bool(value["enabled"])
            current_sections[key] = saved
        settings["shop_sections"] = current_sections
    if vat_percentage is not None:
        # Clamped here as well as in the router: the rate reaches the orders
        # created from tomorrow on, and nothing else re-reads it.
        settings["marketplace_vat_percentage"] = max(0, min(MAX_VAT_PERCENTAGE, int(vat_percentage)))
    # A new dict: in-place mutation of a JSONB column is not tracked.
    org.settings = settings
    await db.commit()
    return await get_config(db, organization_id=organization_id)
