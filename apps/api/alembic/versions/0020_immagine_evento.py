"""La foto o la locandina di un evento (`club_competitions.image_url`):
accanto al nome negli elenchi delle prove; senza, l'icona del tipo.

Revision ID: 0020
Revises: 0019
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0020'
down_revision: str | None = '0019'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('club_competitions', sa.Column('image_url', sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column('club_competitions', 'image_url')
