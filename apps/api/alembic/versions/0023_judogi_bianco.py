"""Il judogi bianco per le gare (`club_athletes.white_judogi`), uno degli
obblighi della scheda dell'atleta (club/obligations.py).

Revision ID: 0023
Revises: 0022
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0023'
down_revision: str | None = '0022'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('club_athletes', sa.Column('white_judogi', sa.Boolean(), server_default=sa.text('false'), nullable=False))


def downgrade() -> None:
    op.drop_column('club_athletes', 'white_judogi')
