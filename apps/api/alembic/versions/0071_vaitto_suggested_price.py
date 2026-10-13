"""Marketplace VAITTO: il prezzo suggerito da Vaitto (Session 88).

L'utente vuole vendere al prezzo che Vaitto suggerisce («retail_price» del
feed, che porta già il ricarico deciso da Vaitto) invece che al costo più
un ricarico nostro. Il ricarico nostro resta, di norma a 0, e si aggiunge
sopra il suggerito; il costo all'ingrosso resta salvato per l'amministratore.

- `vaitto_market_variants.suggested_price_cents` -- il prezzo suggerito,
  aggiornato a ogni import come il costo. NULL finché il prossimo import non
  lo porta: nel frattempo si ricava dal costo con il 40% di Vaitto.
- `vaitto_market_settings.markup_percentage` parte da 0 per un negozio nuovo
  (era 40 sul costo).

Revision ID: c8d2f0a51b39
Revises: b6c1e9f40a27
Create Date: 2026-09-29 14:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c8d2f0a51b39"
down_revision: Union[str, None] = "b6c1e9f40a27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("vaitto_market_variants", sa.Column("suggested_price_cents", sa.BigInteger(), nullable=True))
    # Il ricarico ora sta sopra il suggerito: per un negozio nuovo parte da 0.
    op.alter_column("vaitto_market_settings", "markup_percentage", server_default="0")


def downgrade() -> None:
    op.alter_column("vaitto_market_settings", "markup_percentage", server_default="40")
    op.drop_column("vaitto_market_variants", "suggested_price_cents")
