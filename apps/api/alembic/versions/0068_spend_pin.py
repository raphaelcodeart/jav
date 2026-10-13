"""PIN per i JavCash al posto del codice via email (Session 87).

Il cliente può scegliere, dalle sue Impostazioni, di confermare l'uso dei
JavCash al checkout con un PIN di quattro cifre scelto da lui invece del
codice che gli arriva per email. Una tabella nuova, `spend_pins`, una riga
per utente: il PIN come hash (come la password), se è acceso, e il contatore
dei tentativi sbagliati con il blocco temporaneo che ne consegue.

Tabella a parte e non colonne su `users`: il PIN appartiene al denaro, non
all'anagrafica, e un cliente che non lo usa non ha nessuna riga.

Revision ID: f1a7c3d95e28
Revises: e9c4a7b13f50
Create Date: 2026-09-28 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "f1a7c3d95e28"
down_revision: Union[str, None] = "e9c4a7b13f50"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "spend_pins",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("pin_hash", sa.String(255), nullable=True),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", name="uq_spend_pins_user_id"),
    )
    op.create_index("ix_spend_pins_user_id", "spend_pins", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_spend_pins_user_id", table_name="spend_pins")
    op.drop_table("spend_pins")
