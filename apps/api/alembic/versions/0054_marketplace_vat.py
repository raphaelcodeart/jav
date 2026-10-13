"""L'IVA esplicita sugli ordini dei Marketplace (Session 74).

Two columns on the order tables of the four shops of imported products
(imported_product_orders, cj_orders, shopify_orders, aliexpress_orders):

- `vat_percentage`: the rate that was in force the day the order was
  placed, `marketplace_vat_percentage` in `organizations.settings` (22 by
  default, marketplaces/rules.py);
- `vat_amount_cents`: the VAT **contained in** what is actually charged,
  not added to it -- the prices shown in the Shop are final, as Italian law
  wants a consumer price to be (Codice del Consumo art. 14-15). Nothing
  became more expensive: what changed is that the tax inside the total is
  now computed and frozen, like the bank-transfer discount next to it.

Both are NOT NULL with a server_default of "0", and **existing rows
legitimately keep 0**. They were sold before any of this existed: nobody
ever computed, showed or declared a VAT figure on them, and back-filling
one now -- by multiplying old totals by today's rate -- would be inventing
a fiscal fact about a closed sale. The zero says "not recorded", which is
the truth; every order created from this migration on carries the real
number.

Revision ID: d4a90b6e7c15
Revises: c3f8a51d2e07
Create Date: 2026-09-20 15:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4a90b6e7c15"
down_revision: Union[str, None] = "c3f8a51d2e07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ORDER_TABLES = ("imported_product_orders", "cj_orders", "shopify_orders", "aliexpress_orders")


def upgrade() -> None:
    for table in ORDER_TABLES:
        op.add_column(
            table, sa.Column("vat_percentage", sa.Integer(), nullable=False, server_default="0")
        )
        op.add_column(
            table, sa.Column("vat_amount_cents", sa.BigInteger(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    for table in ORDER_TABLES:
        op.drop_column(table, "vat_amount_cents")
        op.drop_column(table, "vat_percentage")
