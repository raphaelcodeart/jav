"""Marketplace 3: the AliExpress dropshipping integration (Session 71).

The third shop of imported products built on a supplier API, next to CJ
Dropshipping (Marketplace 1, `cj_dropshipping`) and Shopify (Marketplace 2,
`shopify_dropshipping`), and kept just as separate: its own tables, nothing
here touches catalog.products, orders, cj_* or shopify_*, so it can be
switched off or removed without disturbing anything else.

It does not touch `imported_products` either, and that is deliberate: the
old plugin (Session 34) stays exactly where it is, with its hand-typed
products, for the catalog an administrator keeps by hand. What is new here
is the AliExpress Open Platform DS API -- the catalog is searched, the
product is imported with its SKUs and its real cost, the price is recomputed
at every sync, and a paid order becomes an order on AliExpress, followed
until it is delivered.

The supplier is an authorised AliExpress seller/dropshipping account: an app
made on openservice.aliexpress.com (App Key + App Secret) and the account's
own authorisation, which gives the access token that every call carries.
Credentials live on `aliexpress_settings`, one row per organization; the
migration copied into it what was already saved on `import_providers`, so
nobody has to type the App Key again.

To the customer it is simply another Shop tab ("Marketplace 3", name set in
marketplaces/rules.py): same checkout, same JavCash rules (spend only,
never the whole price), bank transfer discounted, same "I miei Ordini" and
Contabilità.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin
from app.domains.marketplaces.models import SHOP_ORDER_NUMBER_SEQ

#: How the price a customer pays is rounded: up to x,90 / x,99, or not at all.
PRICE_ROUNDINGS = ("90", "99", "NONE")
#: What our price starts from: the dropshipping price of the SKU (what we
#: actually pay AliExpress, `offer_sale_price`; falls back to the sale price
#: when the answer does not carry it), or the SKU's own list price.
PRICE_BASES = ("COST", "PRICE")
#: Shipping: a flat amount added at checkout, or built into the price.
SHIPPING_MODES = ("CUSTOMER_PAYS", "INCLUDED")

ALIEXPRESS_PRODUCT_STATUSES = ("ACTIVE", "INACTIVE")
ALIEXPRESS_ORDER_STATUSES = ("AWAITING_PAYMENT", "PAID", "CANCELLED")
ALIEXPRESS_ORDER_PAYMENT_METHODS = ("BANK_TRANSFER", "CARD")

#: What happened to a paid order on AliExpress.
#:   NOT_SENT   -- not placed on AliExpress yet
#:   SENDING    -- claimed by one sender; nobody else may send it
#:   SENT       -- order placed on AliExpress, not shipped yet
#:   SHIPPED    -- shipped, tracking known when the supplier gives one
#:   DELIVERED  -- delivered
#:   ERROR      -- AliExpress refused it, or its answer was lost: forward_error
#:   CANCELLED  -- cancelled on AliExpress
FULFILLMENT_STATUSES = ("NOT_SENT", "SENDING", "SENT", "SHIPPED", "DELIVERED", "ERROR", "CANCELLED")
ERROR_KINDS = ("TEMPORARY", "AUTHENTICATION", "VALIDATION", "FATAL")


class AliexpressSettings(UUIDPKMixin, TimestampMixin, Base):
    """The AliExpress app, the authorised account and the pricing rules of an
    organization -- one row. `app_secret`, `access_token` and `refresh_token`
    are never returned by any endpoint (masked, like Stripe's)."""

    __tablename__ = "aliexpress_settings"
    __table_args__ = (UniqueConstraint("organization_id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    #: The app made on openservice.aliexpress.com (category "Drop Shipping").
    app_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    app_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: What authorising the seller account gives back: a token that expires
    #: and the refresh token client.py renews it with.
    access_token: Mapped[str | None] = mapped_column(String(500), nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(String(500), nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    #: The AliExpress account the token belongs to, as the API reports it.
    account_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_connected_at: Mapped[datetime | None] = mapped_column(nullable=True)
    #: The customer-facing tab is shown only when enabled.
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    #: What we ask AliExpress for on every catalog and order call. Prices come
    #: back already converted, which is why currency_rate is normally 1: it
    #: exists for the day an account can only answer in USD.
    ship_to_country: Mapped[str] = mapped_column(String(2), default="IT")
    target_currency: Mapped[str] = mapped_column(String(3), default="EUR")
    target_language: Mapped[str] = mapped_column(String(8), default="it")
    #: EUR per 1 unit of target_currency (1 when AliExpress answers in EUR).
    currency_rate: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal(1))
    price_basis: Mapped[str] = mapped_column(String(8), default="COST")
    markup_percentage: Mapped[int] = mapped_column(Integer, default=100)
    markup_fixed_cents: Mapped[int] = mapped_column(Integer, default=0)
    price_rounding: Mapped[str] = mapped_column(String(8), default="90")
    shipping_mode: Mapped[str] = mapped_column(String(16), default="CUSTOMER_PAYS")
    #: Session 76 -- la **spesa di spedizione minima** addebitata al cliente,
    #: non più un forfait: si paga il costo reale che AliExpress chiede per
    #: quel carrello, e questo importo quando quello è più basso
    #: (`max(reale, minimo)`, una volta per ordine). Con
    #: shipping_mode=INCLUDED resta quanto si incorpora nel prezzo al
    #: momento del listino, dove la quantità non si sa ancora.
    shipping_minimum_cents: Mapped[int] = mapped_column(Integer, default=590)
    shipping_days: Mapped[str | None] = mapped_column(String(32), nullable=True, default="10-20")
    #: JavCash usable on a newly imported product (marketplaces/rules.py).
    default_credit_percentage: Mapped[int] = mapped_column(Integer, default=30)
    #: Place the order on AliExpress by itself as soon as it is paid.
    auto_forward: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)


class AliexpressProduct(UUIDPKMixin, TimestampMixin, Base):
    """An AliExpress product the administrator chose to sell, with the Italian
    name and description they gave it. Prices live on the variants."""

    __tablename__ = "aliexpress_products"
    __table_args__ = (
        UniqueConstraint("organization_id", "aliexpress_product_id"),
        CheckConstraint(
            "credit_discount_percentage >= 0 AND credit_discount_percentage <= 99",
            name="credit_discount_percentage_below_100",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    #: AliExpress' own numeric product id, kept as text (it is long).
    aliexpress_product_id: Mapped[str] = mapped_column(String(128))
    #: The product page on AliExpress -- Shopify's `handle` has no equivalent,
    #: and this is what an administrator actually wants to open.
    product_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    #: AliExpress' own title, kept to recognize the product there.
    source_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    #: The seller's store name.
    vendor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str] = mapped_column(String(8000), default="")
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    images: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    credit_discount_percentage: Mapped[int] = mapped_column(Integer, default=30)
    #: Overrides the organization's markup for this product only.
    markup_percentage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(nullable=True)
    sync_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)


class AliexpressVariant(UUIDPKMixin, TimestampMixin, Base):
    """One buyable SKU of a product. `cost_amount`/`source_price_amount` are in
    the settings' target currency; `price_cents` is what the customer pays,
    recomputed at every sync unless `price_override_cents` is set.

    `sku_attr` is not decoration: it is the string AliExpress wants back when
    the order is placed, and a SKU cannot be ordered without it."""

    __tablename__ = "aliexpress_variants"
    __table_args__ = (UniqueConstraint("product_id", "aliexpress_sku_id"),)

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aliexpress_products.id"), index=True
    )
    aliexpress_sku_id: Mapped[str] = mapped_column(String(128))
    #: e.g. "14:193;5:100014064" -- what ds.order.create identifies the SKU by.
    sku_attr: Mapped[str | None] = mapped_column(String(500), nullable=True)
    #: The seller's own code, when they publish one.
    sku: Mapped[str | None] = mapped_column(String(128), nullable=True)
    label: Mapped[str] = mapped_column(String(255), default="")
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    cost_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    source_price_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    price_cents: Mapped[int] = mapped_column(BigInteger)
    price_override_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    #: None when AliExpress does not report a stock for this SKU.
    inventory: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    #: Still on sale on AliExpress at the last sync.
    available_in_store: Mapped[bool] = mapped_column(Boolean, default=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(nullable=True)


class AliexpressOrder(UUIDPKMixin, TimestampMixin, Base):
    """A customer's purchase of one variant (in some quantity) -- the same
    checkout as the other shops (JavCash with OTP, card or discounted bank
    transfer for the rest), a delivery address, and its life on AliExpress
    until delivery. Every amount is frozen when the order is placed."""

    __tablename__ = "aliexpress_orders"
    __table_args__ = (
        CheckConstraint("credit_applied_cents >= 0", name="credit_applied_non_negative"),
        CheckConstraint("credit_applied_cents <= amount_cents", name="credit_applied_not_over_amount"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    customer_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    aliexpress_product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aliexpress_products.id")
    )
    aliexpress_variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aliexpress_variants.id")
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))

    #: Session 76 -- il numero d'ordine che legge il cliente. Lo assegna il
    #: database da `shop_order_number_seq`, una sequenza sola per tutti i
    #: negozi: in "I miei Ordini" i tre Marketplace stanno insieme, e tre
    #: "ordine 12" diversi non si potrebbero distinguere. Assegnarlo qui e
    #: non in Python è ciò che lo rende unico anche con due ordini creati
    #: nello stesso istante da processi diversi.
    number: Mapped[int] = mapped_column(
        BigInteger, SHOP_ORDER_NUMBER_SEQ, server_default=SHOP_ORDER_NUMBER_SEQ.next_value(), unique=True
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price_cents: Mapped[int] = mapped_column(BigInteger)
    #: Quanto ha pagato il cliente di spedizione: max(reale, minimo).
    shipping_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    #: Session 76 -- quanto la spedizione costa a noi su AliExpress, e il
    #: minimo in vigore quel giorno. Due fatti distinti da `shipping_cents`:
    #: il margine di spedizione è `shipping_cents - supplier_shipping_cents`.
    #: NULL sugli ordini venduti prima che il costo reale lo chiedesse
    #: qualcuno -- "non rilevato", che è la verità; uno zero direbbe che non
    #: ci è costata niente e gonfierebbe ogni margine passato.
    supplier_shipping_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    minimum_shipping_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    #: unit_price_cents x quantity + shipping_cents.
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    credit_applied_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    #: Taken off the residual when paid by bank transfer (marketplaces/rules.py),
    #: 0 for a card. Paid in euro = amount - credit_applied - bank_transfer_discount.
    bank_transfer_discount_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    #: Session 74 -- the VAT *contained in* what is charged, never added to
    #: it: the prices of the Shop are VAT-inclusive (marketplaces/rules.py).
    #: Frozen together with the discount, on the taxable base
    #: amount_cents - bank_transfer_discount_cents; 0 on the orders that
    #: predate the rule, which were sold before it existed.
    vat_percentage: Mapped[int] = mapped_column(Integer, default=0)
    vat_amount_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    #: Session 78 -- quale regola IVA valeva per questo ordine. `INCLUDED`
    #: (l'IVA era dentro il prezzo) fino alla Session 77, `ADDED` da qui in
    #: avanti. Senza, le due colonne qui sopra avrebbero significato opposto
    #: fra ordini vecchi e nuovi, e ogni lettura sarebbe un'ipotesi.
    vat_mode: Mapped[str] = mapped_column(String(16), server_default="ADDED", default="ADDED")
    credit_debit_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wallet_transactions.id"), nullable=True
    )

    status: Mapped[str] = mapped_column(String(16), default="AWAITING_PAYMENT", index=True)
    payment_method: Mapped[str] = mapped_column(String(16), default="BANK_TRANSFER")
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    payment_proof_storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    payment_proof_original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_proof_uploaded_at: Mapped[datetime | None] = mapped_column(nullable=True)
    paid_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(nullable=True)
    cancelled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # --- Consegna ---
    recipient_name: Mapped[str] = mapped_column(String(128))
    recipient_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    address_line1: Mapped[str] = mapped_column(String(255))
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(128))
    province: Mapped[str] = mapped_column(String(64))
    postal_code: Mapped[str] = mapped_column(String(16))
    country_code: Mapped[str] = mapped_column(String(2), default="IT")
    shipping_days: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # --- Costo su AliExpress al momento dell'ordine (valuta richiesta) ---
    unit_cost_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency_rate: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal(1))

    # --- Vita su AliExpress ---
    fulfillment_status: Mapped[str] = mapped_column(String(16), default="NOT_SENT", index=True)
    #: Our own reference, sent as `out_order_id` so the same order is never
    #: placed twice and an administrator can find it on AliExpress by hand.
    out_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    #: AliExpress' order number.
    aliexpress_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    #: The supplier's own words for where the order is (esito grezzo).
    aliexpress_order_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    forwarded_at: Mapped[datetime | None] = mapped_column(nullable=True)
    forwarded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    forward_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tracking_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    tracking_company: Mapped[str | None] = mapped_column(String(128), nullable=True)
    shipped_at: Mapped[datetime | None] = mapped_column(nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)
    last_error_kind: Mapped[str | None] = mapped_column(String(24), nullable=True)


class AliexpressOrderItem(UUIDPKMixin, TimestampMixin, Base):
    """Una riga di un ordine AliExpress (Session 75, il carrello).

    Fino alla Session 74 un ordine era un prodotto solo, e prodotto,
    variante, quantità e prezzo unitario stavano sulla testata. Col
    carrello un ordine ne porta più d'uno: quelle colonne si spostano qui,
    una riga per variante, mentre **sulla testata resta tutto il denaro** --
    `amount_cents`, `shipping_cents`, `vat_amount_cents`,
    `bank_transfer_discount_cents`, `credit_applied_cents`, la sessione
    Stripe. È la ragione per cui pagamenti, webhook, Contabilità, email e
    pannello ordini non hanno dovuto cambiare: cambia cosa c'è dentro un
    ordine, non come lo si paga.

    Le colonne vecchie della testata restano, valorizzate con la prima
    riga, finché ogni schermata non legge da qui: un ordine storico non si
    riscrive mai (CLAUDE.md §5).

    `aliexpress_order_id` sta **sulla riga** e non solo sulla testata
    perché AliExpress, quando il carrello mette insieme articoli di
    venditori diversi, non crea un ordine ma più d'uno: la risposta di
    `aliexpress.ds.order.create` porta `order_list`, che è una lista. Un
    ordine Jav può quindi corrispondere a due o tre ordini AliExpress, con
    tracking diversi -- e il tracking, per lo stesso motivo, è per riga.
    """

    __tablename__ = "aliexpress_order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        UniqueConstraint("order_id", "aliexpress_variant_id", name="uq_aliexpress_order_items_variant"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aliexpress_orders.id", ondelete="CASCADE"), index=True
    )
    aliexpress_product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aliexpress_products.id")
    )
    aliexpress_variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aliexpress_variants.id")
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1)

    # --- Congelati alla creazione dell'ordine ---
    #: Il prezzo di listino del pezzo il giorno dell'acquisto.
    unit_price_cents: Mapped[int] = mapped_column(BigInteger)
    #: Quanto ci costa su AliExpress: serve al margine, non al cliente.
    unit_cost_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    #: Session 76 -- il freight AliExpress di **questa riga**, in euro. Il
    #: costo reale di un ordine è la somma di questi: AliExpress il freight
    #: lo quota per prodotto, sommarlo è un'operazione nostra.
    supplier_shipping_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    #: Il nome del prodotto come si chiamava quel giorno. Ridondante di
    #: proposito: un prodotto rinominato o tolto dal catalogo non deve
    #: cambiare cosa dice l'ordine di sei mesi fa, e nemmeno la sua email.
    product_name: Mapped[str] = mapped_column(String(255))
    variant_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: Il tetto JavCash del prodotto quel giorno: il massimo spendibile
    #: sull'ordine è la somma di questi, riga per riga, non una percentuale
    #: del totale (un prodotto al 10% e uno al 90% darebbero un cap falso).
    credit_discount_percentage: Mapped[int] = mapped_column(Integer, default=0)

    # --- Vita su AliExpress, per riga (vedi il docstring) ---
    aliexpress_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    tracking_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tracking_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    tracking_company: Mapped[str | None] = mapped_column(String(128), nullable=True)
