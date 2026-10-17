"""Il colore di ogni gruppo (piano) del club: `club_plans.color`, #RRGGBB,
la fascia della sua scheda in «Piani e prezzi». Vuoto = la tavolozza.

Revision ID: 0031
Revises: 0030
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0031'
down_revision: str | None = '0030'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('club_plans', sa.Column('color', sa.String(length=7), nullable=True))


def downgrade() -> None:
    op.drop_column('club_plans', 'color')
