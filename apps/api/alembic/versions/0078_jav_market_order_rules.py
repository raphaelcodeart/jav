"""«Fai la Spesa con Jav»: minimo d'ordine e spedizione gratuita.

Regole solo di questo negozio, decise dall'utente il 13/10/2026: spedizione
fissa 15 €, ordine minimo 80 €, spedizione gratuita da 150 €, entrambe le
soglie sulla merce IVA inclusa. Le colonne nascono "spente" (0 / NULL) e le
righe già esistenti ricevono i valori decisi, così il negozio vivo li ha
dal momento del deploy; restano modificabili dalle Impostazioni.

Revision ID: e8a4c1f2d903
Revises: d7f3a2b9c1e4
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e8a4c1f2d903"
down_revision: Union[str, None] = "d7f3a2b9c1e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jav_market_settings",
        sa.Column("min_order_cents", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "jav_market_settings",
        sa.Column("free_shipping_threshold_cents", sa.Integer(), nullable=True),
    )
    op.execute(
        "UPDATE jav_market_settings SET shipping_mode = 'CUSTOMER_PAYS', shipping_flat_cents = 1500, "
        "min_order_cents = 8000, free_shipping_threshold_cents = 15000"
    )


def downgrade() -> None:
    op.drop_column("jav_market_settings", "free_shipping_threshold_cents")
    op.drop_column("jav_market_settings", "min_order_cents")
