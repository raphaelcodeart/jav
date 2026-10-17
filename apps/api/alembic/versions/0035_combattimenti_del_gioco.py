"""JAV Games: i combattimenti decisi dal server (gare della carriera passo a
passo e randori del club) e i punti del randori dei giocatori. Tutto nello
schema `game` (docs/games.md), scritto a mano come 0021: l'autogenerate del
gestionale non vede queste tabelle.

Revision ID: 0035
Revises: 0034
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = '0035'
down_revision: str | None = '0034'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('players', sa.Column('randori_points', sa.Integer(), server_default='1000', nullable=False), schema='game')
    op.create_table('fights',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('player_id', sa.UUID(), nullable=False),
    sa.Column('kind', sa.String(length=10), nullable=False),
    sa.Column('mode', sa.String(length=4), nullable=False),
    sa.Column('context_key', sa.String(length=120), nullable=True),
    sa.Column('opponent_player_id', sa.UUID(), nullable=True),
    sa.Column('lang', sa.String(length=2), nullable=False),
    sa.Column('state', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('won', sa.Boolean(), nullable=True),
    sa.Column('points', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['player_id'], ['game.players.id'], name=op.f('fk_fights_player_id_players'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['opponent_player_id'], ['game.players.id'], name=op.f('fk_fights_opponent_player_id_players'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_fights')),
    sa.UniqueConstraint('player_id', 'context_key', name='uq_fights_player_context'),
    schema='game')
    op.create_index(op.f('ix_game_fights_player_id'), 'fights', ['player_id'], unique=False, schema='game')
    op.create_index(op.f('ix_game_fights_opponent_player_id'), 'fights', ['opponent_player_id'], unique=False, schema='game')
    op.create_index(op.f('ix_game_fights_created_at'), 'fights', ['created_at'], unique=False, schema='game')


def downgrade() -> None:
    op.drop_table('fights', schema='game')
    op.drop_column('players', 'randori_points', schema='game')
