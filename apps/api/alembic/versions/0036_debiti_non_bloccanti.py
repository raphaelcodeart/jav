"""Una quota scaduta impedisce di iscriversi alle gare, salvo quando la
segreteria la segna «non bloccante»: `club_fees.non_blocking`.

Revision ID: 0036
Revises: 0035
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0036'
down_revision: str | None = '0035'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('club_fees', sa.Column('non_blocking', sa.Boolean(), server_default=sa.text('false'), nullable=False))


def downgrade() -> None:
    op.drop_column('club_fees', 'non_blocking')
