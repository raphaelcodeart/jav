"""Cursos JAV: i corsi extrascolastici di JudoArteVida nelle scuole.

Un tipo di club nuovo (`clubs.kind`: CLUB / JAV_COURSES, al massimo
un'unità JAV_COURSES per organizzazione), il luogo, il testo pubblico e la
percentuale del treinador sui corsi (`club_courses`), e sulle quote il corso,
il treinador e la percentuale congelati all'emissione (`club_fees`): così gli
incassi di un corso e la parte del suo treinador non cambiano se l'atleta
passa a un altro corso. Regole in docs/club-portal.md, "Cursos JAV".

Tutti i club esistenti restano CLUB; nessuna quota esistente ha un corso.

Revision ID: 0009
Revises: 0008
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0009'
down_revision: str | None = '0008'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('clubs', sa.Column('kind', sa.String(length=16), server_default='CLUB', nullable=False))
    op.create_check_constraint(op.f('ck_clubs_kind'), 'clubs', "kind IN ('CLUB', 'JAV_COURSES')")
    op.create_index(
        'uq_clubs_one_jav_courses_unit', 'clubs', ['organization_id'], unique=True,
        postgresql_where=sa.text("kind = 'JAV_COURSES'"),
    )

    op.add_column('club_courses', sa.Column('venue_name', sa.String(length=200), nullable=True))
    op.add_column('club_courses', sa.Column('venue_address', sa.String(length=300), nullable=True))
    op.add_column('club_courses', sa.Column('venue_city', sa.String(length=120), nullable=True))
    op.add_column('club_courses', sa.Column('public_description', sa.Text(), nullable=True))
    op.add_column('club_courses', sa.Column('public_coach_name', sa.String(length=80), nullable=True))
    op.add_column('club_courses', sa.Column('coach_share_pct', sa.Numeric(precision=5, scale=2), nullable=True))
    op.add_column('club_courses', sa.Column('published', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.create_check_constraint(
        op.f('ck_club_courses_coach_share_pct_range'), 'club_courses',
        'coach_share_pct IS NULL OR (coach_share_pct >= 0 AND coach_share_pct <= 100)',
    )

    op.add_column('club_fees', sa.Column('course_id', sa.UUID(), nullable=True))
    op.add_column('club_fees', sa.Column('coach_user_id', sa.UUID(), nullable=True))
    op.add_column('club_fees', sa.Column('coach_share_pct', sa.Numeric(precision=5, scale=2), nullable=True))
    op.create_check_constraint(
        op.f('ck_club_fees_coach_share_pct_range'), 'club_fees',
        'coach_share_pct IS NULL OR (coach_share_pct >= 0 AND coach_share_pct <= 100)',
    )
    op.create_index(op.f('ix_club_fees_course_id'), 'club_fees', ['course_id'], unique=False)
    op.create_index(op.f('ix_club_fees_coach_user_id'), 'club_fees', ['coach_user_id'], unique=False)
    op.create_foreign_key(op.f('fk_club_fees_course_id_club_courses'), 'club_fees', 'club_courses', ['course_id'], ['id'])
    op.create_foreign_key(op.f('fk_club_fees_coach_user_id_users'), 'club_fees', 'users', ['coach_user_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint(op.f('fk_club_fees_coach_user_id_users'), 'club_fees', type_='foreignkey')
    op.drop_constraint(op.f('fk_club_fees_course_id_club_courses'), 'club_fees', type_='foreignkey')
    op.drop_index(op.f('ix_club_fees_coach_user_id'), table_name='club_fees')
    op.drop_index(op.f('ix_club_fees_course_id'), table_name='club_fees')
    op.drop_constraint(op.f('ck_club_fees_coach_share_pct_range'), 'club_fees', type_='check')
    op.drop_column('club_fees', 'coach_share_pct')
    op.drop_column('club_fees', 'coach_user_id')
    op.drop_column('club_fees', 'course_id')
    op.drop_constraint(op.f('ck_club_courses_coach_share_pct_range'), 'club_courses', type_='check')
    for column in ('published', 'coach_share_pct', 'public_coach_name', 'public_description', 'venue_city',
                   'venue_address', 'venue_name'):
        op.drop_column('club_courses', column)
    op.drop_index('uq_clubs_one_jav_courses_unit', table_name='clubs')
    op.drop_constraint(op.f('ck_clubs_kind'), 'clubs', type_='check')
    op.drop_column('clubs', 'kind')
