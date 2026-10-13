"""Riscatto fattura con carta: JavCash subito, controllo della fattura dopo (Session 89).

Scelta dell'utente: chi paga il 5% con carta riceve i JavCash appena Stripe
conferma il pagamento, sull'importo che ha dichiarato, senza aspettare
l'amministratore. L'amministratore controlla la fattura dopo e la approva
o la rifiuta; un rifiuto non tocca il wallet (lo storno, se serve, lo fa a
mano lo staff) e il 5% pagato non si rimborsa. Il bonifico resta com'era:
verifica dell'amministratore, bonifico, conferma, poi la ricarica.

- `invoice_redemptions.review_status` -- NULL per i riscatti verificati
  prima del pagamento (bonifico, o carta dopo la verifica: già controllati);
  PENDING quando la carta ha accreditato senza verifica, poi APPROVED o
  REJECTED.
- `reviewed_by_user_id`, `reviewed_at`, `review_note` (il motivo del
  rifiuto).

Revision ID: c4a9e2f71d58
Revises: b5e1f9c3a7d2
Create Date: 2026-10-04 09:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4a9e2f71d58"
down_revision: Union[str, None] = "b5e1f9c3a7d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("invoice_redemptions", sa.Column("review_status", sa.String(16), nullable=True))
    op.add_column(
        "invoice_redemptions",
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.add_column("invoice_redemptions", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("invoice_redemptions", sa.Column("review_note", sa.String(500), nullable=True))
    op.create_check_constraint(
        "review_status",
        "invoice_redemptions",
        "review_status IS NULL OR review_status IN ('PENDING', 'APPROVED', 'REJECTED')",
    )


def downgrade() -> None:
    op.drop_constraint("review_status", "invoice_redemptions", type_="check")
    op.drop_column("invoice_redemptions", "review_note")
    op.drop_column("invoice_redemptions", "reviewed_at")
    op.drop_column("invoice_redemptions", "reviewed_by_user_id")
    op.drop_column("invoice_redemptions", "review_status")
