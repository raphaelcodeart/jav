"""Marketplace VAITTO: JavCash calcolato dal nostro guadagno (Session 88).

L'utente vuole che la percentuale JavCash di ogni prodotto Vaitto si
calcoli da sola dal guadagno: prezzo al cliente (il suggerito da Vaitto)
meno quanto lo paghiamo, in percentuale del prezzo, e di questo una quota
(la metà di norma) diventa la parte pagabile in JavCash. Costa 80,
si vende a 100: guadagno 20% → 10% in JavCash.

- `credit_mode` -- FIXED (la percentuale del negozio per tutti, come fino a
  qui: resta il default, nessun prodotto cambia con questa migrazione) o
  MARGIN (dal guadagno);
- `credit_margin_share` -- la quota del guadagno, 50 di norma.

Revision ID: d4e9a1c62f80
Revises: c8d2f0a51b39
Create Date: 2026-09-29 20:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e9a1c62f80"
down_revision: Union[str, None] = "c8d2f0a51b39"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vaitto_market_settings",
        sa.Column("credit_mode", sa.String(16), nullable=False, server_default="FIXED"),
    )
    op.add_column(
        "vaitto_market_settings",
        sa.Column("credit_margin_share", sa.Integer(), nullable=False, server_default="50"),
    )
    op.create_check_constraint("credit_mode", "vaitto_market_settings", "credit_mode IN ('FIXED', 'MARGIN')")
    op.create_check_constraint(
        "credit_margin_share_range", "vaitto_market_settings", "credit_margin_share BETWEEN 0 AND 100"
    )


def downgrade() -> None:
    op.drop_constraint("credit_margin_share_range", "vaitto_market_settings", type_="check")
    op.drop_constraint("credit_mode", "vaitto_market_settings", type_="check")
    op.drop_column("vaitto_market_settings", "credit_margin_share")
    op.drop_column("vaitto_market_settings", "credit_mode")
