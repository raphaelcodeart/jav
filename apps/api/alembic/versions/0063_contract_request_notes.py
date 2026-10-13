"""Le note della pratica per l'amministrazione (Session 83).

Il cliente, e soprattutto il promoter che compila la pratica a nome di
qualcuno, lascia un messaggio che lo staff legge nel pannello Pratiche:
«chiamare dopo le 18», «il contatore è in cantina». Chi l'ha scritto e
quando si tengono accanto, perché «nota del promoter» e «nota del cliente»
non si leggono allo stesso modo.

Revision ID: a4d2e8b61f93
Revises: f3a91c07b6d2
Create Date: 2026-09-25 10:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "a4d2e8b61f93"
down_revision: Union[str, None] = "f3a91c07b6d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("contract_requests", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column(
        "contract_requests",
        sa.Column("notes_updated_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.add_column("contract_requests", sa.Column("notes_updated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("contract_requests", "notes_updated_at")
    op.drop_column("contract_requests", "notes_updated_by_user_id")
    op.drop_column("contract_requests", "notes")
