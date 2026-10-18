"""Il genitore resta collegato al figlio maggiorenne che prende il suo conto
(`club_athlete_links`, athlete_access.become_holder).

Revision ID: 0045
Revises: 0044
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0045'
down_revision: str | None = '0044'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('club_athlete_links',
    sa.Column('athlete_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['athlete_id'], ['club_athletes.id'], name=op.f('fk_club_athlete_links_athlete_id_club_athletes'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_club_athlete_links_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_athlete_links')),
    sa.UniqueConstraint('athlete_id', 'user_id', name='uq_club_athlete_links_athlete_user')
    )
    op.create_index(op.f('ix_club_athlete_links_athlete_id'), 'club_athlete_links', ['athlete_id'], unique=False)
    op.create_index(op.f('ix_club_athlete_links_user_id'), 'club_athlete_links', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_club_athlete_links_user_id'), table_name='club_athlete_links')
    op.drop_index(op.f('ix_club_athlete_links_athlete_id'), table_name='club_athlete_links')
    op.drop_table('club_athlete_links')
