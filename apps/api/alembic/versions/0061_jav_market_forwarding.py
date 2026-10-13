"""L'ordine che parte verso l'azienda produttrice (Session 80).

Su «Fai la Spesa con Jav» non c'è un fornitore con un'API: la merce la fa
un'azienda vera, e quello che le si manda è **una email**. Da qui un ordine
pagato può essere inoltrato -- a mano con un pulsante, come su AliExpress,
oppure da solo se l'amministratore accende l'automatismo.

Su `jav_market_settings`:

- `auto_forward`: l'ordine pagato parte da solo. Nasce **spento**, come su
  AliExpress dopo la Session 76: mandare una email a un'azienda vera è
  un'azione verso l'esterno, e la prima volta la si vuole guardare.

Su `jav_market_orders`, quel poco che serve a sapere cosa è successo:

- `forwarded_at` / `forwarded_by_user_id` -- quando e chi;
- `forward_error` -- perché non è partito, se non è partito.

Un ordine può contenere prodotti di **aziende diverse**: parte una email
per azienda, con dentro solo le sue righe. Non c'è quindi un solo
destinatario da registrare, e `forwarded_at` dice che il giro è stato
fatto, non a chi: i destinatari sono le aziende delle righe, e stanno già
lì. Chi vuole il dettaglio lo trova nell'audit.

Niente sulle righe: il rapporto con l'azienda è fuori da questo sistema —
non c'è un numero d'ordine del fornitore da conservare, come invece
succede con AliExpress.

Revision ID: e2c58a90d417
Revises: d1b46f8c2e93
Create Date: 2026-09-21 18:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "e2c58a90d417"
down_revision: Union[str, None] = "d1b46f8c2e93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jav_market_settings",
        sa.Column("auto_forward", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("jav_market_orders", sa.Column("forwarded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "jav_market_orders",
        sa.Column("forwarded_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.add_column("jav_market_orders", sa.Column("forward_error", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("jav_market_orders", "forward_error")
    op.drop_column("jav_market_orders", "forwarded_by_user_id")
    op.drop_column("jav_market_orders", "forwarded_at")
    op.drop_column("jav_market_settings", "auto_forward")
