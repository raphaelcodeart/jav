"""TikTok tra i social del club (`club_sites.tiktok_url`) e la biografia del
judoca più lunga (`club_athlete_public_profiles.bio` da 280 a 1500
caratteri). I social della rete JudoArteVida stanno in
`organizations.settings` (nessuna colonna).

Revision ID: 0030
Revises: 0029
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0030'
down_revision: str | None = '0029'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('club_sites', sa.Column('tiktok_url', sa.String(length=500), nullable=True))
    op.alter_column('club_athlete_public_profiles', 'bio', type_=sa.String(length=1500), existing_type=sa.String(length=280), existing_nullable=True)


def downgrade() -> None:
    op.execute("UPDATE club_athlete_public_profiles SET bio = left(bio, 280) WHERE length(bio) > 280")
    op.alter_column('club_athlete_public_profiles', 'bio', type_=sa.String(length=280), existing_type=sa.String(length=1500), existing_nullable=True)
    op.drop_column('club_sites', 'tiktok_url')
