"""JAV Games: lo schema `game`, separato dal gestionale (app/game, docs/games.md).
Giocatori, tentativi dei quiz, esami di cintura del gioco, partite di Judo
Career. Nessuna chiave esterna verso le tabelle del gestionale: il solo
legame è `players.user_id`, senza FK.

Revision ID: 0021
Revises: 0020
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = '0021'
down_revision: str | None = '0020'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS game")
    op.create_table('players',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('display_name', sa.String(length=80), nullable=False),
    sa.Column('club_label', sa.String(length=120), nullable=True),
    sa.Column('quiz_xp', sa.BigInteger(), nullable=False),
    sa.Column('career_xp', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_players')),
    schema='game')
    op.create_index(op.f('ix_game_players_user_id'), 'players', ['user_id'], unique=True, schema='game')
    op.create_table('quiz_attempts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('player_id', sa.UUID(), nullable=False),
    sa.Column('quiz_id', sa.String(length=40), nullable=False),
    sa.Column('lang', sa.String(length=2), nullable=False),
    sa.Column('questions', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('answers', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('score', sa.Integer(), nullable=False),
    sa.Column('max_score', sa.Integer(), nullable=False),
    sa.Column('correct', sa.SmallInteger(), nullable=False),
    sa.Column('passed', sa.Boolean(), nullable=False),
    sa.Column('xp_earned', sa.Integer(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['player_id'], ['game.players.id'], name=op.f('fk_quiz_attempts_player_id_players'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_quiz_attempts')),
    schema='game')
    op.create_index(op.f('ix_game_quiz_attempts_player_id'), 'quiz_attempts', ['player_id'], unique=False, schema='game')
    op.create_index(op.f('ix_game_quiz_attempts_quiz_id'), 'quiz_attempts', ['quiz_id'], unique=False, schema='game')
    op.create_table('belt_exams',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('player_id', sa.UUID(), nullable=False),
    sa.Column('belt', sa.String(length=16), nullable=False),
    sa.Column('score_pct', sa.SmallInteger(), nullable=False),
    sa.Column('passed_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['player_id'], ['game.players.id'], name=op.f('fk_belt_exams_player_id_players'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_belt_exams')),
    sa.UniqueConstraint('player_id', 'belt', name='uq_belt_exams_player_belt'),
    schema='game')
    op.create_index(op.f('ix_game_belt_exams_player_id'), 'belt_exams', ['player_id'], unique=False, schema='game')
    op.create_table('careers',
    sa.Column('player_id', sa.UUID(), nullable=False),
    sa.Column('state', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('week', sa.Integer(), nullable=False),
    sa.Column('belt', sa.String(length=16), nullable=False),
    sa.Column('saves', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['player_id'], ['game.players.id'], name=op.f('fk_careers_player_id_players'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('player_id', name=op.f('pk_careers')),
    schema='game')


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS game CASCADE")
