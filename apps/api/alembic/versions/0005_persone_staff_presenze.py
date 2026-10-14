"""Persone e staff del club, cartellino, presenze con nota, taxa de falta, investimenti.

- `club_functions`: treinador, treinador adjunto, monitor, monitor adjunto,
  su un account o su un atleta (una funzione per persona).
- `club_course_staff`: gli adjunto di un corso, oltre al titolare.
- `club_work_sessions`: il cartellino, un turno aperto per persona.
- `club_attendances`: nota per la segreteria e chi l'ha segnata (staff o
  famiglia).
- `club_fees.absence_adjustment`: la taxa de falta applicata dalla segreteria.
- `wallet_transactions.reference_club_athlete_id`: l'atleta di un
  investimento del club.

Revision ID: 0005
Revises: 0004
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('club_functions',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('function', sa.String(length=24), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('athlete_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("function IN ('COACH', 'ASSISTANT_COACH', 'MONITOR', 'ASSISTANT_MONITOR')", name=op.f('ck_club_functions_function')),
    sa.CheckConstraint('(user_id IS NULL) <> (athlete_id IS NULL)', name=op.f('ck_club_functions_one_person')),
    sa.ForeignKeyConstraint(['athlete_id'], ['club_athletes.id'], name=op.f('fk_club_functions_athlete_id_club_athletes')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_functions_club_id_clubs')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_functions_organization_id_organizations')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_club_functions_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_functions')),
    sa.UniqueConstraint('club_id', 'athlete_id', name='uq_club_functions_club_athlete'),
    sa.UniqueConstraint('club_id', 'user_id', name='uq_club_functions_club_user')
    )
    op.create_index(op.f('ix_club_functions_club_id'), 'club_functions', ['club_id'], unique=False)
    op.create_index(op.f('ix_club_functions_organization_id'), 'club_functions', ['organization_id'], unique=False)

    op.create_table('club_course_staff',
    sa.Column('course_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['course_id'], ['club_courses.id'], name=op.f('fk_club_course_staff_course_id_club_courses'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_club_course_staff_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_course_staff')),
    sa.UniqueConstraint('course_id', 'user_id', name='uq_club_course_staff_course_user')
    )
    op.create_index(op.f('ix_club_course_staff_course_id'), 'club_course_staff', ['course_id'], unique=False)
    op.create_index(op.f('ix_club_course_staff_user_id'), 'club_course_staff', ['user_id'], unique=False)

    op.create_table('club_work_sessions',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('note', sa.String(length=300), nullable=True),
    sa.Column('corrected_by_user_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('ended_at IS NULL OR ended_at > started_at', name=op.f('ck_club_work_sessions_time_range')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_work_sessions_club_id_clubs')),
    sa.ForeignKeyConstraint(['corrected_by_user_id'], ['users.id'], name=op.f('fk_club_work_sessions_corrected_by_user_id_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_work_sessions_organization_id_organizations')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_club_work_sessions_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_work_sessions'))
    )
    op.create_index(op.f('ix_club_work_sessions_club_id'), 'club_work_sessions', ['club_id'], unique=False)
    op.create_index(op.f('ix_club_work_sessions_organization_id'), 'club_work_sessions', ['organization_id'], unique=False)
    op.create_index(op.f('ix_club_work_sessions_started_at'), 'club_work_sessions', ['started_at'], unique=False)
    op.create_index(op.f('ix_club_work_sessions_user_id'), 'club_work_sessions', ['user_id'], unique=False)
    op.create_index('uq_club_work_sessions_one_open', 'club_work_sessions', ['user_id'], unique=True,
                    postgresql_where=sa.text('ended_at IS NULL'))

    op.add_column('club_attendances', sa.Column('note', sa.String(length=300), nullable=True))
    op.add_column('club_attendances', sa.Column('recorded_by_kind', sa.String(length=8), server_default='STAFF', nullable=False))

    op.add_column('club_fees', sa.Column('absence_adjustment', sa.String(length=8), nullable=True))
    op.create_check_constraint(op.f('ck_club_fees_absence_adjustment'), 'club_fees',
                               "absence_adjustment IS NULL OR absence_adjustment IN ('HALF', 'FULL')")

    op.add_column('wallet_transactions', sa.Column('reference_club_athlete_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_wallet_transactions_reference_club_athlete_id'), 'wallet_transactions', ['reference_club_athlete_id'], unique=False)
    op.create_foreign_key(op.f('fk_wallet_transactions_reference_club_athlete_id_club_athletes'), 'wallet_transactions',
                          'club_athletes', ['reference_club_athlete_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint(op.f('fk_wallet_transactions_reference_club_athlete_id_club_athletes'), 'wallet_transactions', type_='foreignkey')
    op.drop_index(op.f('ix_wallet_transactions_reference_club_athlete_id'), table_name='wallet_transactions')
    op.drop_column('wallet_transactions', 'reference_club_athlete_id')
    op.drop_constraint(op.f('ck_club_fees_absence_adjustment'), 'club_fees', type_='check')
    op.drop_column('club_fees', 'absence_adjustment')
    op.drop_column('club_attendances', 'recorded_by_kind')
    op.drop_column('club_attendances', 'note')
    op.drop_index('uq_club_work_sessions_one_open', table_name='club_work_sessions')
    op.drop_table('club_work_sessions')
    op.drop_table('club_course_staff')
    op.drop_table('club_functions')
