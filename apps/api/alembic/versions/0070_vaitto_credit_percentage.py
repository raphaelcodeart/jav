"""Marketplace VAITTO: percentuale JavCash del negozio (Session 88).

L'utente vuole impostare una volta sola, accanto al ricarico, quanta parte
del prezzo dei prodotti Vaitto si può pagare in JavCash, e personalizzarla
prodotto per prodotto quando serve. Stessa logica del prezzo scritto a mano
(`price_locked`):

- `vaitto_market_settings.credit_percentage` -- la percentuale del negozio,
  30 come ogni Marketplace finché nessuno la cambia; mai 100 (CHECK);
- `vaitto_market_products.credit_locked` -- la percentuale del prodotto è
  stata scelta a mano: cambiare quella del negozio non la tocca.

Revision ID: b6c1e9f40a27
Revises: a3b8d2e7f614
Create Date: 2026-09-29 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b6c1e9f40a27"
down_revision: Union[str, None] = "a3b8d2e7f614"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vaitto_market_settings",
        sa.Column("credit_percentage", sa.Integer(), nullable=False, server_default="30"),
    )
    op.create_check_constraint(
        "credit_percentage_range", "vaitto_market_settings", "credit_percentage BETWEEN 0 AND 99"
    )
    op.add_column(
        "vaitto_market_products",
        sa.Column("credit_locked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("vaitto_market_products", "credit_locked")
    op.drop_constraint("credit_percentage_range", "vaitto_market_settings", type_="check")
    op.drop_column("vaitto_market_settings", "credit_percentage")
