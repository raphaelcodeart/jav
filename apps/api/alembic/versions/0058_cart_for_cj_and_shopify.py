"""Il carrello su CJ e Shopify, e il numero d'ordine per tutti (Session 77).

Stessa forma della 0055 su AliExpress, ripetuta sui due negozi gemelli:
`cj_order_items` e `shopify_order_items`, con prodotto, variante, quantità
e prezzo unitario che si spostano sulla riga mentre **il denaro resta sulla
testata**. È la ragione per cui pagamenti, webhook Stripe, Contabilità ed
email non cambiano: cambia cosa c'è dentro un ordine, non come lo si paga.

Il backfill costruisce una riga per ogni ordine esistente, così nessun
ordine resta senza righe e il codice non deve prevedere quel caso.

CJ tiene sulla testata anche il magazzino di partenza (`origin_country`) e
il corriere (`logistic_name`), perché l'ordine verso CJ li vuole lì. Un
ordine con righe da magazzini diversi non sarebbe spedibile in una volta,
quindi il servizio si rifiuta di comporlo: oggi non succede mai (tutti i
prodotti attivi partono da CN) e se un domani succedesse il cliente
leggerebbe il motivo invece di vedersi creare un ordine che il fornitore
rifiuta. Per riconoscere il caso serve sapere da dove parte ogni riga:
`origin_country` è quindi anche sulla riga.

**Il numero d'ordine arriva a tutti e quattro i negozi.** La 0057 lo aveva
dato solo ad AliExpress; il cliente però in "I miei Ordini" li vede
insieme, e un elenco in cui un ordine si chiama 1042 e quello sotto
7B3F2A91 non si legge. Stessa sequenza condivisa `shop_order_number_seq`,
quindi i numeri non si ripetono fra negozi. Anche `imported_product_orders`
la riceve, pur non avendo il carrello: è nello stesso elenco.

Gli ordini esistenti vengono numerati **in ordine di creazione dentro
ciascun negozio**, un negozio dopo l'altro. Fra negozi diversi i numeri non
sono quindi in ordine cronologico: numerarli tutti insieme avrebbe richiesto
di fondere tre tabelle in una sola passata per poi riassegnare, e il numero
serve a identificare un ordine, non a datarlo -- la data ce l'ha già.

Revision ID: b8f25c3d0a71
Revises: a7e14b2c9f63
Create Date: 2026-09-21 02:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "b8f25c3d0a71"
down_revision: Union[str, None] = "a7e14b2c9f63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: I negozi che ricevono il numero d'ordine, con la tabella degli ordini.
NUMBERED = ("cj_orders", "shopify_orders", "imported_product_orders")


def _items_table(name: str, *, product_fk: str, variant_fk: str, extra: list | None = None) -> None:
    op.create_table(
        name,
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "order_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{name.replace('_items', 's')}.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("product_id", UUID(as_uuid=True), sa.ForeignKey(product_fk), nullable=False),
        sa.Column("variant_id", UUID(as_uuid=True), sa.ForeignKey(variant_fk), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price_cents", sa.BigInteger(), nullable=False),
        sa.Column("product_name", sa.String(255), nullable=False),
        sa.Column("variant_label", sa.String(255), nullable=True),
        sa.Column("credit_discount_percentage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("supplier_order_id", sa.String(128), nullable=True),
        sa.Column("tracking_number", sa.String(128), nullable=True),
        sa.Column("tracking_url", sa.String(1000), nullable=True),
        sa.Column("tracking_company", sa.String(128), nullable=True),
        *(extra or []),
        sa.CheckConstraint("quantity > 0", name="quantity_positive"),
        sa.UniqueConstraint("order_id", "variant_id", name=f"uq_{name}_variant"),
    )
    op.create_index(f"ix_{name}_order_id", name, ["order_id"])


def upgrade() -> None:
    # --- Le righe d'ordine dei due negozi gemelli ---
    _items_table(
        "cj_order_items",
        product_fk="cj_products.id",
        variant_fk="cj_variants.id",
        # Da dove parte questa riga: serve a riconoscere un ordine che
        # metterebbe insieme magazzini diversi, che CJ non saprebbe spedire.
        extra=[
            sa.Column("unit_cost_usd", sa.Numeric(12, 2), nullable=True),
            sa.Column("origin_country", sa.String(8), nullable=True),
        ],
    )
    _items_table(
        "shopify_order_items",
        product_fk="shopify_products.id",
        variant_fk="shopify_variants.id",
        extra=[sa.Column("unit_cost_amount", sa.Numeric(12, 2), nullable=True)],
    )

    op.execute(
        """
        INSERT INTO cj_order_items (
            id, created_at, order_id, product_id, variant_id, quantity, unit_price_cents,
            product_name, variant_label, credit_discount_percentage,
            supplier_order_id, tracking_number, tracking_company,
            unit_cost_usd, origin_country
        )
        SELECT gen_random_uuid(), o.created_at, o.id, o.cj_product_id, o.cj_variant_id,
               o.quantity, o.unit_price_cents,
               COALESCE(p.name, 'Prodotto non più disponibile'), v.label,
               COALESCE(p.credit_discount_percentage, 0),
               o.cj_order_id, o.tracking_number, o.tracking_provider,
               o.unit_cost_usd, o.origin_country
          FROM cj_orders o
          LEFT JOIN cj_products p ON p.id = o.cj_product_id
          LEFT JOIN cj_variants v ON v.id = o.cj_variant_id
        """
    )
    op.execute(
        """
        INSERT INTO shopify_order_items (
            id, created_at, order_id, product_id, variant_id, quantity, unit_price_cents,
            product_name, variant_label, credit_discount_percentage,
            supplier_order_id, tracking_number, tracking_url, tracking_company, unit_cost_amount
        )
        SELECT gen_random_uuid(), o.created_at, o.id, o.shopify_product_id, o.shopify_variant_id,
               o.quantity, o.unit_price_cents,
               COALESCE(p.name, 'Prodotto non più disponibile'), v.label,
               COALESCE(p.credit_discount_percentage, 0),
               o.shopify_order_id, o.tracking_number, o.tracking_url, o.tracking_company,
               o.unit_cost_amount
          FROM shopify_orders o
          LEFT JOIN shopify_products p ON p.id = o.shopify_product_id
          LEFT JOIN shopify_variants v ON v.id = o.shopify_variant_id
        """
    )

    # --- Il numero d'ordine anche sugli altri negozi ---
    for table in NUMBERED:
        op.add_column(table, sa.Column("number", sa.BigInteger(), nullable=True))

    # Numerati in ordine di creazione, tabella per tabella, partendo da dove
    # la sequenza e' arrivata. Non `SET number = nextval(...)`: in un UPDATE
    # la sequenza avanza riga per riga ma **nell'ordine in cui il motore
    # aggiorna**, che non e' quello della ORDER BY -- si otterrebbero numeri
    # tutti diversi ma mescolati rispetto alla cronologia. Con un'addizione
    # sul numero di riga l'assegnazione e' deterministica, e la setval dopo
    # riporta la sequenza oltre l'ultimo numero usato.
    for table in NUMBERED:
        op.execute(
            f"""
            WITH base AS (SELECT last_value AS b FROM shop_order_number_seq),
                 ordered AS (
                     SELECT id, row_number() OVER (ORDER BY created_at, id) AS rn FROM {table}
                 )
            UPDATE {table} o
               SET number = (SELECT b FROM base) + ordered.rn
              FROM ordered
             WHERE o.id = ordered.id
            """
        )
        op.execute(
            f"""
            SELECT setval(
                'shop_order_number_seq',
                GREATEST(
                    (SELECT last_value FROM shop_order_number_seq),
                    COALESCE((SELECT max(number) FROM {table}), 0)
                )
            )
            """
        )
        op.execute(f"ALTER TABLE {table} ALTER COLUMN number SET DEFAULT nextval('shop_order_number_seq')")
        op.alter_column(table, "number", nullable=False)
        op.create_unique_constraint(f"uq_{table}_number", table, ["number"])


def downgrade() -> None:
    for table in NUMBERED:
        op.drop_constraint(f"uq_{table}_number", table, type_="unique")
        op.drop_column(table, "number")
    for name in ("shopify_order_items", "cj_order_items"):
        op.drop_index(f"ix_{name}_order_id", table_name=name)
        op.drop_table(name)
