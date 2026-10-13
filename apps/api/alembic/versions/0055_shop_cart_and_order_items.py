"""Il carrello dello Shop e gli ordini a più righe (Session 75).

Tre tabelle nuove e nessuna colonna tolta.

- `carts` / `cart_items`: il carrello, uno per (cliente, negozio). I
  quattro negozi hanno regole che si escludono a vicenda -- indirizzo,
  spedizione, IVA e sconto bonifico nei Marketplace, «riscuoti subito
  cashback» nel catalogo interno e mai nei Marketplace -- quindi righe di
  negozi diversi non possono finire nello stesso ordine. Il cliente ne
  vede comunque uno solo, diviso in sezioni (carts/models.py).

- `aliexpress_order_items`: le righe di un ordine AliExpress. Prodotto,
  variante, quantità e prezzo unitario si spostano qui; **sulla testata
  resta tutto il denaro**, ed è la ragione per cui pagamenti, webhook
  Stripe, Contabilità ed email non cambiano di una riga.

Il backfill crea una riga per ogni ordine già esistente, copiata dalle
colonne della testata: dopo questa migrazione ogni ordine ha almeno una
riga, i vecchi come i nuovi, e il codice non deve gestire il caso "ordine
senza righe". Le colonne della testata **restano dove sono** e continuano
a valere per gli ordini a riga sola: riscrivere un ordine chiuso non si fa
(CLAUDE.md §5), e servono da rete finché ogni schermata non legge dalle
righe.

`product_name`, `variant_label` e `credit_discount_percentage` sono
copiati sulla riga di proposito: un prodotto rinominato, ritirato o con il
tetto JavCash cambiato non deve alterare cosa dice un ordine passato.
Dove il prodotto nel frattempo è sparito il backfill non può inventarlo e
mette "Prodotto non più disponibile" -- è la verità, e non lascia un
NOT NULL da violare.

Revision ID: e5b21c8f3d46
Revises: d4a90b6e7c15
Create Date: 2026-09-20 18:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "e5b21c8f3d46"
down_revision: Union[str, None] = "d4a90b6e7c15"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "carts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("customer_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("shop", sa.String(16), nullable=False),
        sa.UniqueConstraint("customer_user_id", "shop", name="uq_carts_customer_shop"),
        sa.CheckConstraint("shop IN ('aliexpress', 'cj', 'shopify', 'catalog')", name="shop"),
    )
    op.create_index("ix_carts_organization_id", "carts", ["organization_id"])
    op.create_index("ix_carts_customer_user_id", "carts", ["customer_user_id"])

    op.create_table(
        "cart_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cart_id", UUID(as_uuid=True), sa.ForeignKey("carts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        sa.Column(
            "aliexpress_variant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("aliexpress_variants.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "cj_variant_id", UUID(as_uuid=True), sa.ForeignKey("cj_variants.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column(
            "shopify_variant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("shopify_variants.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "product_version_id",
            UUID(as_uuid=True),
            sa.ForeignKey("product_versions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.CheckConstraint("quantity > 0", name="quantity_positive"),
        sa.CheckConstraint("quantity <= 99", name="quantity_max"),
        sa.CheckConstraint(
            "num_nonnulls(aliexpress_variant_id, cj_variant_id, shopify_variant_id, product_version_id) = 1",
            name="exactly_one_reference",
        ),
        # UNIQUE su colonne nullable: PostgreSQL considera due NULL distinti,
        # quindi ciascuno di questi vincola solo le righe del proprio negozio.
        sa.UniqueConstraint("cart_id", "aliexpress_variant_id", name="uq_cart_items_aliexpress_variant"),
        sa.UniqueConstraint("cart_id", "cj_variant_id", name="uq_cart_items_cj_variant"),
        sa.UniqueConstraint("cart_id", "shopify_variant_id", name="uq_cart_items_shopify_variant"),
        sa.UniqueConstraint("cart_id", "product_version_id", name="uq_cart_items_product_version"),
    )
    op.create_index("ix_cart_items_cart_id", "cart_items", ["cart_id"])

    op.create_table(
        "aliexpress_order_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "order_id", UUID(as_uuid=True), sa.ForeignKey("aliexpress_orders.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "aliexpress_product_id", UUID(as_uuid=True), sa.ForeignKey("aliexpress_products.id"), nullable=False
        ),
        sa.Column(
            "aliexpress_variant_id", UUID(as_uuid=True), sa.ForeignKey("aliexpress_variants.id"), nullable=False
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price_cents", sa.BigInteger(), nullable=False),
        sa.Column("unit_cost_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("product_name", sa.String(255), nullable=False),
        sa.Column("variant_label", sa.String(255), nullable=True),
        sa.Column("credit_discount_percentage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("aliexpress_order_id", sa.String(128), nullable=True),
        sa.Column("tracking_number", sa.String(128), nullable=True),
        sa.Column("tracking_url", sa.String(1000), nullable=True),
        sa.Column("tracking_company", sa.String(128), nullable=True),
        sa.CheckConstraint("quantity > 0", name="quantity_positive"),
        sa.UniqueConstraint("order_id", "aliexpress_variant_id", name="uq_aliexpress_order_items_variant"),
    )
    op.create_index("ix_aliexpress_order_items_order_id", "aliexpress_order_items", ["order_id"])
    op.create_index(
        "ix_aliexpress_order_items_aliexpress_order_id", "aliexpress_order_items", ["aliexpress_order_id"]
    )

    # Una riga per ogni ordine esistente. LEFT JOIN e non JOIN: un ordine il
    # cui prodotto è stato cancellato deve comunque avere la sua riga,
    # altrimenti resterebbe l'unico ordine senza righe di tutta la tabella e
    # ogni lettura dovrebbe prevedere quel caso.
    op.execute(
        """
        INSERT INTO aliexpress_order_items (
            id, created_at, order_id, aliexpress_product_id, aliexpress_variant_id,
            quantity, unit_price_cents, unit_cost_amount,
            product_name, variant_label, credit_discount_percentage,
            aliexpress_order_id, tracking_number, tracking_url, tracking_company
        )
        SELECT
            gen_random_uuid(), o.created_at, o.id, o.aliexpress_product_id, o.aliexpress_variant_id,
            o.quantity, o.unit_price_cents, o.unit_cost_amount,
            COALESCE(p.name, 'Prodotto non più disponibile'), v.label,
            COALESCE(p.credit_discount_percentage, 0),
            o.aliexpress_order_id, o.tracking_number, o.tracking_url, o.tracking_company
        FROM aliexpress_orders o
        LEFT JOIN aliexpress_products p ON p.id = o.aliexpress_product_id
        LEFT JOIN aliexpress_variants v ON v.id = o.aliexpress_variant_id
        """
    )


def downgrade() -> None:
    op.drop_index("ix_aliexpress_order_items_aliexpress_order_id", table_name="aliexpress_order_items")
    op.drop_index("ix_aliexpress_order_items_order_id", table_name="aliexpress_order_items")
    op.drop_table("aliexpress_order_items")
    op.drop_index("ix_cart_items_cart_id", table_name="cart_items")
    op.drop_table("cart_items")
    op.drop_index("ix_carts_customer_user_id", table_name="carts")
    op.drop_index("ix_carts_organization_id", table_name="carts")
    op.drop_table("carts")
