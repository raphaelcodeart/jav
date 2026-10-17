"""Il quaderno del treinador e i turni corretti da chi li ha fatti
(club/coach.py, club/workclock.py):

- `club_lesson_notes`: che cosa si è fatto in una lezione (corso + giorno);
- `club_athlete_notes`: le note personali dello staff su un atleta;
- `club_work_sessions.edited_at` / `edited_by_user_id` / `added_later`: il
  turno ritoccato dalla persona stessa, o scritto dopo a mano.

Revision ID: 0034
Revises: 0033
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0034'
down_revision: str | None = '0033'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('club_lesson_notes',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('course_id', sa.UUID(), nullable=False),
    sa.Column('lesson_date', sa.Date(), nullable=False),
    sa.Column('author_user_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=True),
    sa.Column('techniques', sa.String(length=500), nullable=True),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['author_user_id'], ['users.id'], name=op.f('fk_club_lesson_notes_author_user_id_users')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_lesson_notes_club_id_clubs')),
    sa.ForeignKeyConstraint(['course_id'], ['club_courses.id'], name=op.f('fk_club_lesson_notes_course_id_club_courses'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_lesson_notes_organization_id_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_lesson_notes'))
    )
    op.create_index(op.f('ix_club_lesson_notes_organization_id'), 'club_lesson_notes', ['organization_id'], unique=False)
    op.create_index(op.f('ix_club_lesson_notes_club_id'), 'club_lesson_notes', ['club_id'], unique=False)
    op.create_index('ix_club_lesson_notes_course_date', 'club_lesson_notes', ['course_id', 'lesson_date'], unique=False)
    op.create_table('club_athlete_notes',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('athlete_id', sa.UUID(), nullable=False),
    sa.Column('author_user_id', sa.UUID(), nullable=False),
    sa.Column('category', sa.String(length=16), server_default='OTHER', nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("category IN ('TECHNIQUE', 'BEHAVIOUR', 'HEALTH', 'GOAL', 'COMPETITION', 'OTHER')", name=op.f('ck_club_athlete_notes_category')),
    sa.ForeignKeyConstraint(['athlete_id'], ['club_athletes.id'], name=op.f('fk_club_athlete_notes_athlete_id_club_athletes'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['author_user_id'], ['users.id'], name=op.f('fk_club_athlete_notes_author_user_id_users')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_athlete_notes_club_id_clubs')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_athlete_notes_organization_id_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_athlete_notes'))
    )
    op.create_index(op.f('ix_club_athlete_notes_organization_id'), 'club_athlete_notes', ['organization_id'], unique=False)
    op.create_index(op.f('ix_club_athlete_notes_club_id'), 'club_athlete_notes', ['club_id'], unique=False)
    op.create_index(op.f('ix_club_athlete_notes_athlete_id'), 'club_athlete_notes', ['athlete_id'], unique=False)
    op.add_column('club_work_sessions', sa.Column('edited_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('club_work_sessions', sa.Column('edited_by_user_id', sa.UUID(), nullable=True))
    op.add_column('club_work_sessions', sa.Column('added_later', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.create_foreign_key(op.f('fk_club_work_sessions_edited_by_user_id_users'), 'club_work_sessions', 'users',
                          ['edited_by_user_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint(op.f('fk_club_work_sessions_edited_by_user_id_users'), 'club_work_sessions', type_='foreignkey')
    op.drop_column('club_work_sessions', 'added_later')
    op.drop_column('club_work_sessions', 'edited_by_user_id')
    op.drop_column('club_work_sessions', 'edited_at')
    op.drop_table('club_athlete_notes')
    op.drop_table('club_lesson_notes')
