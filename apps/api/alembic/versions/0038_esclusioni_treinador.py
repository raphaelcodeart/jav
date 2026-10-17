"""Ogni treinador vede tutti i corsi del club, salvo quelli da cui la
segreteria lo esclude: `club_course_coach_exclusions`.

Revision ID: 0038
Revises: 0037
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0038'
down_revision: str | None = '0037'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('club_course_coach_exclusions',
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('course_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('created_by_user_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_course_coach_exclusions_club_id_clubs')),
    sa.ForeignKeyConstraint(['course_id'], ['club_courses.id'], name=op.f('fk_club_course_coach_exclusions_course_id_club_courses'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_club_course_coach_exclusions_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_club_course_coach_exclusions_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_course_coach_exclusions')),
    sa.UniqueConstraint('course_id', 'user_id', name='uq_club_course_coach_exclusions_course_user')
    )
    op.create_index(op.f('ix_club_course_coach_exclusions_club_id'), 'club_course_coach_exclusions', ['club_id'], unique=False)
    op.create_index(op.f('ix_club_course_coach_exclusions_course_id'), 'club_course_coach_exclusions', ['course_id'], unique=False)
    op.create_index(op.f('ix_club_course_coach_exclusions_user_id'), 'club_course_coach_exclusions', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_club_course_coach_exclusions_user_id'), table_name='club_course_coach_exclusions')
    op.drop_index(op.f('ix_club_course_coach_exclusions_course_id'), table_name='club_course_coach_exclusions')
    op.drop_index(op.f('ix_club_course_coach_exclusions_club_id'), table_name='club_course_coach_exclusions')
    op.drop_table('club_course_coach_exclusions')
