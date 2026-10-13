"""Marketplace VAITTO: prezzo del marchio con l'IVA dentro (Session 88).

L'utente ha scelto nel suo account Vaitto «Sell at brand RRP»: il prezzo al
cliente è quello ufficiale del marchio, che ha già l'IVA dentro. E ha dato
la formula del guadagno: prezzo − (costo + 5 € di spedizione) × 1,22; metà
del guadagno è la parte pagabile in JavCash; un prodotto che non copre i
costi non si vende.

- `vaitto_market_settings.prices_include_vat` -- il prezzo ha l'IVA dentro:
  al checkout si scorpora invece di aggiungersi (ordini con vat_mode
  INCLUDED); vero di norma.
- `vaitto_market_settings.shipping_cost_cents` -- la nostra spedizione per
  prodotto, 500 di norma: solo nel calcolo del guadagno.
- `vaitto_market_variants.below_cost` -- la variante non copre costo +
  spedizione + IVA e non si vende.

Revision ID: e7b3c5d18a42
Revises: d4e9a1c62f80
Create Date: 2026-09-30 18:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e7b3c5d18a42"
down_revision: Union[str, None] = "d4e9a1c62f80"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vaitto_market_settings",
        sa.Column("prices_include_vat", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "vaitto_market_settings",
        sa.Column("shipping_cost_cents", sa.Integer(), nullable=False, server_default="500"),
    )
    op.add_column(
        "vaitto_market_variants",
        sa.Column("below_cost", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("vaitto_market_variants", "below_cost")
    op.drop_column("vaitto_market_settings", "shipping_cost_cents")
    op.drop_column("vaitto_market_settings", "prices_include_vat")
