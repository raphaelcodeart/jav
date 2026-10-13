"""Marketplace 3: the Shopify dropshipping integration (Session 68).

The third shop of imported products, next to AliExpress (Marketplace 1,
`imported_products`) and CJ Dropshipping (Marketplace 2, `cj_dropshipping`),
built the same way as CJ and kept just as separate: its own tables, nothing
here touches catalog.products, orders, imported_products or cj_*, so it can
be switched off or removed without disturbing anything else.

The supplier is a Shopify store the organization controls, where a
dropshipping app (DSers, Syncee, Spocket...) keeps the catalog and fulfils
the orders. Through a Shopify custom app's Admin API token this integration
reads that catalog, the administrator imports products with our own price
(Shopify cost or price, converted and marked up), and a paid order is
created in the store as a completed draft order -- the store's dropshipping
app then sends it to the supplier. Shipping and tracking are read back from
the Shopify order's fulfillments.

To the customer it is simply another Shop tab ("Marketplace 3", name set in
marketplaces/rules.py): same checkout, same JavCash rules (spend only, never
the whole price), card +5%, same "I miei Ordini" and Contabilità.
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
#: What our price starts from: the variant's cost in Shopify (inventory item
#: unit cost, the dropshipping app usually fills it with the supplier price;
#: falls back to the price when missing), or the store's own selling price.
PRICE_BASES = ("COST", "PRICE")
#: Shipping: a flat amount added at checkout, or built into the price.
SHIPPING_MODES = ("CUSTOMER_PAYS", "INCLUDED")

SHOPIFY_PRODUCT_STATUSES = ("ACTIVE", "INACTIVE")
SHOPIFY_ORDER_STATUSES = ("AWAITING_PAYMENT", "PAID", "CANCELLED")
SHOPIFY_ORDER_PAYMENT_METHODS = ("BANK_TRANSFER", "CARD")

#: What happened to a paid order in the Shopify store.
#:   NOT_SENT   -- not created in the store yet
#:   SENDING    -- claimed by one sender; nobody else may send it
#:   SENT       -- order created in the store, not fulfilled yet
#:   SHIPPED    -- fulfilled (at least partly), tracking known when given
#:   DELIVERED  -- delivered
#:   ERROR      -- the store refused it: see forward_error
#:   CANCELLED  -- cancelled in the store
FULFILLMENT_STATUSES = ("NOT_SENT", "SENDING", "SENT", "SHIPPED", "DELIVERED", "ERROR", "CANCELLED")
ERROR_KINDS = ("TEMPORARY", "AUTHENTICATION", "VALIDATION", "FATAL")


class ShopifySettings(UUIDPKMixin, TimestampMixin, Base):
    """The Shopify store and the pricing rules of an organization -- one row.
    `access_token` is never returned by any endpoint (masked, like Stripe's)."""

    __tablename__ = "shopify_settings"
    __table_args__ = (UniqueConstraint("organization_id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    #: xxx.myshopify.com
    shop_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: Either a fixed Admin API token (legacy custom app, shpat_...) or, for an
    #: app made in the Dev Dashboard, its Client ID + secret: the client
    #: credentials grant then fills `access_token` with a 24-hour token,
    #: renewed by client.py when `token_expires_at` is near.
    access_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    api_version: Mapped[str] = mapped_column(String(16), default="2025-07")
    #: The customer-facing tab is shown only when enabled.
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    #: What the store reported at the last connection test.
    shop_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    shop_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    #: EUR per 1 unit of the store's currency (1 for a store in EUR).
    currency_rate: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal(1))
    price_basis: Mapped[str] = mapped_column(String(8), default="COST")
    markup_percentage: Mapped[int] = mapped_column(Integer, default=100)
    markup_fixed_cents: Mapped[int] = mapped_column(Integer, default=0)
    price_rounding: Mapped[str] = mapped_column(String(8), default="90")
    shipping_mode: Mapped[str] = mapped_column(String(16), default="CUSTOMER_PAYS")
    #: Flat shipping charged per order when the customer pays shipping.
    shipping_flat_cents: Mapped[int] = mapped_column(Integer, default=590)
    shipping_days: Mapped[str | None] = mapped_column(String(32), nullable=True, default="7-15")
    #: JavCash usable on a newly imported product (marketplaces/rules.py).
    default_credit_percentage: Mapped[int] = mapped_column(Integer, default=30)
    #: Create the order in the store by itself as soon as it is paid.
    auto_forward: Mapped[bool] = mapped_column(Boolean, default=True)
    last_connected_at: Mapped[datetime | None] = mapped_column(nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ShopifyProduct(UUIDPKMixin, TimestampMixin, Base):
    """A store product the administrator chose to sell, with the Italian name
    and description they gave it. Prices live on the variants."""

    __tablename__ = "shopify_products"
    __table_args__ = (
        UniqueConstraint("organization_id", "shopify_product_id"),
        CheckConstraint(
            "credit_discount_percentage >= 0 AND credit_discount_percentage <= 99",
            name="credit_discount_percentage_below_100",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    #: gid://shopify/Product/123
    shopify_product_id: Mapped[str] = mapped_column(String(128))
    handle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    #: The store's own title, kept to recognize the product there.
    source_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
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


class ShopifyVariant(UUIDPKMixin, TimestampMixin, Base):
    """One buyable version of a product. `cost_amount`/`source_price_amount`
    are in the store's currency; `price_cents` is what the customer pays,
    recomputed at every sync unless `price_override_cents` is set."""

    __tablename__ = "shopify_variants"
    __table_args__ = (UniqueConstraint("product_id", "shopify_variant_id"),)

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shopify_products.id"), index=True
    )
    #: gid://shopify/ProductVariant/456
    shopify_variant_id: Mapped[str] = mapped_column(String(128))
    sku: Mapped[str | None] = mapped_column(String(128), nullable=True)
    label: Mapped[str] = mapped_column(String(255), default="")
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    cost_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    source_price_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    price_cents: Mapped[int] = mapped_column(BigInteger)
    price_override_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    #: None when the store does not track stock for this variant.
    inventory: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    #: Still in the store at the last sync.
    available_in_store: Mapped[bool] = mapped_column(Boolean, default=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ShopifyOrder(UUIDPKMixin, TimestampMixin, Base):
    """A customer's purchase of one variant (in some quantity) -- the same
    checkout as CJ (JavCash with OTP, card or discounted bank transfer for
    the rest), a delivery address, and its life in the Shopify store until
    delivery. Every amount is frozen when the order is placed."""

    __tablename__ = "shopify_orders"
    __table_args__ = (
        CheckConstraint("credit_applied_cents >= 0", name="credit_applied_non_negative"),
        CheckConstraint("credit_applied_cents <= amount_cents", name="credit_applied_not_over_amount"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    customer_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    shopify_product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("shopify_products.id"))
    shopify_variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("shopify_variants.id"))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    #: Session 77 -- il numero d'ordine che legge il cliente, dalla sequenza
    #: condivisa da tutti i negozi: in "I miei Ordini" stanno nello stesso
    #: elenco, e due ordini con lo stesso numero non si distinguerebbero.
    number: Mapped[int] = mapped_column(
        BigInteger, SHOP_ORDER_NUMBER_SEQ, server_default=SHOP_ORDER_NUMBER_SEQ.next_value(), unique=True
    )

    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price_cents: Mapped[int] = mapped_column(BigInteger)
    shipping_cents: Mapped[int] = mapped_column(BigInteger, default=0)
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

    # --- Costo nel negozio al momento dell'ordine (valuta del negozio) ---
    unit_cost_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency_rate: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal(1))

    # --- Vita nel negozio Shopify ---
    fulfillment_status: Mapped[str] = mapped_column(String(16), default="NOT_SENT", index=True)
    #: gid://shopify/DraftOrder/... -- kept so a retry completes the same draft.
    shopify_draft_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    #: gid://shopify/Order/...
    shopify_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    #: The store's order name, e.g. "#1042".
    shopify_order_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    shopify_fulfillment_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
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


class ShopifyOrderItem(UUIDPKMixin, TimestampMixin, Base):
    """Una riga di un ordine Shopify (Session 77, il carrello).

    Stessa forma di `AliexpressOrderItem`: prodotto, variante, quantita' e
    prezzo unitario stanno qui, **il denaro resta sulla testata**. E' la
    ragione per cui pagamenti, webhook, Contabilita' ed email non sono
    cambiati quando un ordine ha smesso di contenere un articolo solo.

    Nome del prodotto, etichetta della variante e tetto JavCash sono
    **congelati**: un prodotto rinominato o ritirato non deve cambiare cosa
    dice un ordine di sei mesi fa.

    Il numero d'ordine del fornitore e il tracking stanno sulla riga perche'
    un ordine nostro puo' diventare piu' spedizioni: e' gia' cosi' su
    AliExpress, e su CJ lo diventa appena entrano in gioco due magazzini.
    """

    __tablename__ = "shopify_order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        UniqueConstraint("order_id", "variant_id", name="uq_shopify_order_items_variant"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shopify_orders.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("shopify_products.id"))
    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("shopify_variants.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price_cents: Mapped[int] = mapped_column(BigInteger)
    product_name: Mapped[str] = mapped_column(String(255))
    variant_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    credit_discount_percentage: Mapped[int] = mapped_column(Integer, default=0)
    supplier_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tracking_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    tracking_company: Mapped[str | None] = mapped_column(String(128), nullable=True)
    #: Quanto ci costa nel negozio Shopify, congelato sulla riga.
    unit_cost_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
