"""Marketplace 4 — «Fai la Spesa con Jav» (Session 79).

Il quarto negozio di prodotti importati, con tabelle sue come gli altri
tre: spegnerlo o rimuoverlo non disturba nessuno, ed è la ragione per cui
`marketplaces/rules.py` dice di clonare un dominio invece di allargarne uno.

Sei tabelle:

- `jav_market_settings` — una riga per organizzazione. Poche voci: non
  c'è un fornitore da collegare, né un cambio valuta, né un ricarico da
  applicare a un costo. Il prezzo lo scrive l'amministratore ed è già
  quello di vendita.
- `jav_market_producers` — **l'azienda che produce la merce**, in tabella
  a parte. Un'azienda fa molti articoli: scriverne i dati dentro ogni
  prodotto vorrebbe dire correggerli in venti posti quando cambia un
  indirizzo, e ritrovarsi venti versioni diverse della stessa azienda.
- `jav_market_products` / `jav_market_variants` — il catalogo, con la
  stessa forma di un prodotto importato da un fornitore, perché al cliente
  deve comportarsi allo stesso modo.
- `jav_market_orders` / `jav_market_order_items` — gli ordini. Nascono
  già multi-riga: nessuna colonna di riga sulla testata, dove resta solo il
  denaro, e nessun backfill da fare perché ordini vecchi non ce ne sono.

Più due innesti negli altri domini:

- `cart_items.jav_market_variant_id`, con l'arco esclusivo allargato a
  cinque colonne. Una colonna per negozio e non un uuid generico: è la
  chiave esterna a impedire che una riga di carrello sopravviva al prodotto
  che cita.
- `wallet_transactions.reference_jav_market_order_id`, per lo stesso
  motivo: un rimborso deve puntare a un ordine che esiste.

Il numero d'ordine viene dalla sequenza condivisa `shop_order_number_seq`,
quindi non si scontra con quelli degli altri negozi -- il cliente li vede
nello stesso elenco.

Nessuna tabella esistente perde niente: qui si aggiunge soltanto.

Revision ID: d1b46f8c2e93
Revises: c9a37e15b402
Create Date: 2026-09-21 15:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "d1b46f8c2e93"
down_revision: Union[str, None] = "c9a37e15b402"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "jav_market_settings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("shipping_mode", sa.String(16), nullable=False, server_default="CUSTOMER_PAYS"),
        sa.Column("shipping_flat_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("shipping_days", sa.String(32), nullable=True),
        sa.Column("ship_to_country", sa.String(2), nullable=False, server_default="IT"),
        sa.UniqueConstraint("organization_id", name="uq_jav_market_settings_organization_id"),
    )
    op.create_index("ix_jav_market_settings_organization_id", "jav_market_settings", ["organization_id"])

    op.create_table(
        "jav_market_producers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.String(4000), nullable=False, server_default=""),
        sa.Column("website_url", sa.String(1000), nullable=True),
        sa.Column("logo_url", sa.String(1000), nullable=True),
        sa.Column("vat_number", sa.String(32), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        # Un nome per organizzazione: due schede della stessa azienda scritte
        # in modo appena diverso sono il modo piu' rapido di perdere i dati.
        sa.UniqueConstraint("organization_id", "name", name="uq_jav_market_producers_name"),
    )
    op.create_index("ix_jav_market_producers_organization_id", "jav_market_producers", ["organization_id"])

    op.create_table(
        "jav_market_products",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        # Nullable: un prodotto si puo' caricare prima di aver compilato la
        # scheda dell'azienda, e obbligarlo bloccherebbe il lavoro.
        sa.Column("producer_id", UUID(as_uuid=True), sa.ForeignKey("jav_market_producers.id"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(8000), nullable=False, server_default=""),
        sa.Column("image_url", sa.String(1000), nullable=True),
        sa.Column("images", JSONB(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("credit_discount_percentage", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("unit_cost_cents", sa.BigInteger(), nullable=True),
        sa.Column("created_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("credit_discount_percentage BETWEEN 0 AND 99", name="credit_percentage_range"),
    )
    op.create_index("ix_jav_market_products_organization_id", "jav_market_products", ["organization_id"])
    op.create_index("ix_jav_market_products_producer_id", "jav_market_products", ["producer_id"])
    op.create_index("ix_jav_market_products_status", "jav_market_products", ["status"])

    op.create_table(
        "jav_market_variants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "product_id", UUID(as_uuid=True),
            sa.ForeignKey("jav_market_products.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("label", sa.String(255), nullable=False, server_default="Unica"),
        sa.Column("sku", sa.String(128), nullable=True),
        sa.Column("image_url", sa.String(1000), nullable=True),
        sa.Column("price_cents", sa.BigInteger(), nullable=False),
        sa.Column("inventory", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.CheckConstraint("price_cents > 0", name="price_positive"),
        sa.UniqueConstraint("product_id", "sku", name="uq_jav_market_variants_sku"),
    )
    op.create_index("ix_jav_market_variants_product_id", "jav_market_variants", ["product_id"])

    op.create_table(
        "jav_market_orders",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("customer_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "number", sa.BigInteger(), nullable=False,
            server_default=sa.text("nextval('shop_order_number_seq')"),
        ),
        sa.Column("items_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("shipping_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("credit_applied_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("bank_transfer_discount_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("vat_percentage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("vat_amount_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("vat_mode", sa.String(16), nullable=False, server_default="ADDED"),
        sa.Column(
            "credit_debit_transaction_id", UUID(as_uuid=True),
            sa.ForeignKey("wallet_transactions.id"), nullable=True,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="AWAITING_PAYMENT"),
        sa.Column("payment_method", sa.String(16), nullable=False, server_default="BANK_TRANSFER"),
        sa.Column("stripe_checkout_session_id", sa.String(255), nullable=True),
        sa.Column("note", sa.String(1000), nullable=True),
        sa.Column("payment_proof_storage_key", sa.String(500), nullable=True),
        sa.Column("payment_proof_original_filename", sa.String(255), nullable=True),
        sa.Column("payment_proof_uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.String(500), nullable=True),
        sa.Column("recipient_name", sa.String(128), nullable=False),
        sa.Column("recipient_phone", sa.String(32), nullable=True),
        sa.Column("address_line1", sa.String(255), nullable=False),
        sa.Column("address_line2", sa.String(255), nullable=True),
        sa.Column("city", sa.String(128), nullable=False),
        sa.Column("province", sa.String(64), nullable=False),
        sa.Column("postal_code", sa.String(16), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False, server_default="IT"),
        sa.Column("shipping_days", sa.String(32), nullable=True),
        sa.Column("fulfillment_status", sa.String(16), nullable=False, server_default="NOT_SENT"),
        sa.Column("tracking_number", sa.String(128), nullable=True),
        sa.Column("tracking_url", sa.String(1000), nullable=True),
        sa.Column("tracking_company", sa.String(128), nullable=True),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("credit_applied_cents >= 0", name="credit_applied_non_negative"),
        sa.CheckConstraint("credit_applied_cents <= amount_cents", name="credit_applied_not_over_amount"),
        sa.CheckConstraint("vat_mode IN ('INCLUDED', 'ADDED')", name="vat_mode"),
        sa.UniqueConstraint("number", name="uq_jav_market_orders_number"),
        sa.UniqueConstraint("stripe_checkout_session_id", name="uq_jav_market_orders_stripe_session"),
    )
    op.create_index("ix_jav_market_orders_organization_id", "jav_market_orders", ["organization_id"])
    op.create_index("ix_jav_market_orders_customer_user_id", "jav_market_orders", ["customer_user_id"])
    op.create_index("ix_jav_market_orders_status", "jav_market_orders", ["status"])
    op.create_index("ix_jav_market_orders_fulfillment_status", "jav_market_orders", ["fulfillment_status"])

    op.create_table(
        "jav_market_order_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "order_id", UUID(as_uuid=True),
            sa.ForeignKey("jav_market_orders.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("product_id", UUID(as_uuid=True), sa.ForeignKey("jav_market_products.id"), nullable=False),
        sa.Column("variant_id", UUID(as_uuid=True), sa.ForeignKey("jav_market_variants.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price_cents", sa.BigInteger(), nullable=False),
        sa.Column("unit_cost_cents", sa.BigInteger(), nullable=True),
        sa.Column("product_name", sa.String(255), nullable=False),
        sa.Column("variant_label", sa.String(255), nullable=True),
        # Congelato come il resto: un'azienda rinominata non riscrive un
        # ordine di sei mesi fa.
        sa.Column("producer_name", sa.String(160), nullable=True),
        sa.Column("credit_discount_percentage", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("quantity > 0", name="quantity_positive"),
        sa.UniqueConstraint("order_id", "variant_id", name="uq_jav_market_order_items_variant"),
    )
    op.create_index("ix_jav_market_order_items_order_id", "jav_market_order_items", ["order_id"])

    # --- Gli innesti negli altri domini ---
    op.add_column(
        "cart_items",
        sa.Column(
            "jav_market_variant_id", UUID(as_uuid=True),
            sa.ForeignKey("jav_market_variants.id", ondelete="CASCADE"), nullable=True,
        ),
    )
    op.create_unique_constraint(
        "uq_cart_items_jav_market_variant", "cart_items", ["cart_id", "jav_market_variant_id"]
    )
    # L'arco esclusivo passa da quattro colonne a cinque.
    op.drop_constraint("exactly_one_reference", "cart_items", type_="check")
    op.create_check_constraint(
        "exactly_one_reference",
        "cart_items",
        "num_nonnulls(aliexpress_variant_id, cj_variant_id, shopify_variant_id,"
        " jav_market_variant_id, product_version_id) = 1",
    )
    op.drop_constraint("shop", "carts", type_="check")
    op.create_check_constraint(
        "shop", "carts", "shop IN ('aliexpress', 'cj', 'shopify', 'jav_market', 'catalog')"
    )

    op.add_column(
        "wallet_transactions",
        sa.Column(
            "reference_jav_market_order_id", UUID(as_uuid=True),
            sa.ForeignKey("jav_market_orders.id"), nullable=True,
        ),
    )
    op.create_index(
        "ix_wallet_transactions_reference_jav_market_order_id",
        "wallet_transactions", ["reference_jav_market_order_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_wallet_transactions_reference_jav_market_order_id", table_name="wallet_transactions")
    op.drop_column("wallet_transactions", "reference_jav_market_order_id")

    op.drop_constraint("shop", "carts", type_="check")
    op.create_check_constraint("shop", "carts", "shop IN ('aliexpress', 'cj', 'shopify', 'catalog')")
    op.drop_constraint("exactly_one_reference", "cart_items", type_="check")
    op.create_check_constraint(
        "exactly_one_reference",
        "cart_items",
        "num_nonnulls(aliexpress_variant_id, cj_variant_id, shopify_variant_id, product_version_id) = 1",
    )
    op.drop_constraint("uq_cart_items_jav_market_variant", "cart_items", type_="unique")
    op.drop_column("cart_items", "jav_market_variant_id")

    for name in ("jav_market_order_items", "jav_market_orders", "jav_market_variants",
                 "jav_market_products", "jav_market_producers", "jav_market_settings"):
        op.drop_table(name)
