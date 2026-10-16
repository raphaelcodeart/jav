"""L'aiuto del club a un atleta: i costi pagati per lui
(`club_athlete_supports`, club/support.py).

Revision ID: 0026
Revises: 0025
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0026'
down_revision: str | None = '0025'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('club_athlete_supports',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('athlete_id', sa.UUID(), nullable=False),
    sa.Column('category', sa.String(length=16), nullable=False),
    sa.Column('amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('note', sa.String(length=300), nullable=True),
    sa.Column('paid_on', sa.Date(), nullable=False),
    sa.Column('recorded_by_user_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("category IN ('TRANSPORT', 'MATERIAL', 'COMPETITION', 'EXAM', 'TRAINING_CAMP', 'OTHER')", name=op.f('ck_club_athlete_supports_category')),
    sa.CheckConstraint('amount_cents > 0', name=op.f('ck_club_athlete_supports_amount_positive')),
    sa.ForeignKeyConstraint(['athlete_id'], ['club_athletes.id'], name=op.f('fk_club_athlete_supports_athlete_id_club_athletes')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_athlete_supports_club_id_clubs')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_athlete_supports_organization_id_organizations')),
    sa.ForeignKeyConstraint(['recorded_by_user_id'], ['users.id'], name=op.f('fk_club_athlete_supports_recorded_by_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_athlete_supports'))
    )
    op.create_index(op.f('ix_club_athlete_supports_club_id'), 'club_athlete_supports', ['club_id'], unique=False)
    op.create_index(op.f('ix_club_athlete_supports_athlete_id'), 'club_athlete_supports', ['athlete_id'], unique=False)


def downgrade() -> None:
    op.drop_table('club_athlete_supports')
