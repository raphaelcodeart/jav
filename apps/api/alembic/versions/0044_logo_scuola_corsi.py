"""Il logo della scuola sui corsi JAV (`club_courses.venue_logo_url`): la
scheda del corso nel sito, nell'area della famiglia e del treinador.

Revision ID: 0044
Revises: 0043
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0044'
down_revision: str | None = '0043'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('club_courses', sa.Column('venue_logo_url', sa.String(length=1000), nullable=True))


def downgrade() -> None:
    op.drop_column('club_courses', 'venue_logo_url')
