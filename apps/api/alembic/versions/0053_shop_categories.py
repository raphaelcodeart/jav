"""Le categorie dello Shop (Session 73).

Due tabelle, uno strato sopra i prodotti -- see
app/domains/shop_categories/models.py:

- shop_categories: the chips of one shop (internal / partner /
  dropshipping / aliexpress / cj / shopify), with their order and whether
  they are offered to the customer. Unique per organization and shop on
  lower(name), so "Casa" and "casa" cannot both exist in the same grid;
- shop_category_products: which products carry which category.

Nothing is added to the five product tables and `products.category` is left
alone (it decides which SHOP a catalog product belongs to, a different
concept). `shop_category_products.product_id` has no foreign key on purpose:
it points at a row in one of five tables, told apart by `shop` -- the price
of keeping this domain removable, and the reason the whole feature is undone
by dropping these two tables.

Revision ID: c3f8a51d2e07
Revises: b7d1f4a20c58
Create Date: 2026-09-20 10:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3f8a51d2e07"
down_revision: Union[str, None] = "b7d1f4a20c58"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "shop_categories",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("shop", sa.String(16), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", TS, nullable=True),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_shop_categories_organization_id", "shop_categories", ["organization_id"])
    # The duplicate name is refused by the database, not only by the service:
    # a functional index, because the comparison is case-insensitive.
    op.create_index(
        "uq_shop_categories_organization_id_shop_name",
        "shop_categories",
        ["organization_id", "shop", sa.text("lower(name)")],
        unique=True,
    )

    op.create_table(
        "shop_category_products",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column(
            "category_id",
            UUID,
            sa.ForeignKey("shop_categories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("shop", sa.String(16), nullable=False),
        # Polymorphic on purpose: products / imported_products / cj_products /
        # shopify_products / aliexpress_products, told apart by `shop`.
        sa.Column("product_id", UUID, nullable=False),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("category_id", "product_id", name="uq_shop_category_products_category_id"),
    )
    op.create_index("ix_shop_category_products_category_id", "shop_category_products", ["category_id"])
    # What every product list asks: the categories of a page of ids, in one
    # shop -- one query, never one per product.
    op.create_index(
        "ix_shop_category_products_organization_id_shop_product_id",
        "shop_category_products",
        ["organization_id", "shop", "product_id"],
    )


def downgrade() -> None:
    op.drop_table("shop_category_products")
    op.drop_table("shop_categories")
