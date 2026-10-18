"""I corsi esterni nelle scuole (domains/extcourses): un sistema a parte,
con tabelle sue e nessun legame con i club — corsi, gruppi, staff (treinador
e segreteria della scuola), partecipanti, mensilità, prove di pagamento,
presenze, turni, avvisi.

Revision ID: 0046
Revises: 0045
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0046'
down_revision: str | None = '0045'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('ext_courses',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('school_name', sa.String(length=200), nullable=False),
    sa.Column('school_address', sa.String(length=300), nullable=True),
    sa.Column('school_city', sa.String(length=120), nullable=True),
    sa.Column('school_logo_url', sa.String(length=1000), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('monthly_fee_cents', sa.BigInteger(), nullable=False),
    sa.Column('billing_months', sa.dialects.postgresql.ARRAY(sa.SmallInteger()), nullable=False),
    sa.Column('due_day', sa.SmallInteger(), nullable=False),
    sa.Column('starts_on', sa.Date(), nullable=False),
    sa.Column('ends_on', sa.Date(), nullable=False),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('published', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('public_coach_name', sa.String(length=80), nullable=True),
    sa.Column('created_by_user_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('due_day BETWEEN 1 AND 28', name=op.f('ck_ext_courses_due_day_range')),
    sa.CheckConstraint('monthly_fee_cents >= 0', name=op.f('ck_ext_courses_fee_non_negative')),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_ext_courses_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_ext_courses_organization_id_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ext_courses'))
    )
    op.create_index(op.f('ix_ext_courses_organization_id'), 'ext_courses', ['organization_id'], unique=False)
    op.create_table('ext_groups',
    sa.Column('course_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('min_age', sa.SmallInteger(), nullable=True),
    sa.Column('max_age', sa.SmallInteger(), nullable=True),
    sa.Column('weekday', sa.SmallInteger(), nullable=False),
    sa.Column('starts_at', sa.Time(), nullable=False),
    sa.Column('ends_at', sa.Time(), nullable=False),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('ends_at > starts_at', name=op.f('ck_ext_groups_times')),
    sa.CheckConstraint('weekday BETWEEN 0 AND 6', name=op.f('ck_ext_groups_weekday_range')),
    sa.ForeignKeyConstraint(['course_id'], ['ext_courses.id'], name=op.f('fk_ext_groups_course_id_ext_courses'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ext_groups'))
    )
    op.create_index(op.f('ix_ext_groups_course_id'), 'ext_groups', ['course_id'], unique=False)
    op.create_table('ext_notices',
    sa.Column('course_id', sa.UUID(), nullable=False),
    sa.Column('author_user_id', sa.UUID(), nullable=True),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['author_user_id'], ['users.id'], name=op.f('fk_ext_notices_author_user_id_users')),
    sa.ForeignKeyConstraint(['course_id'], ['ext_courses.id'], name=op.f('fk_ext_notices_course_id_ext_courses'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ext_notices'))
    )
    op.create_index(op.f('ix_ext_notices_course_id'), 'ext_notices', ['course_id'], unique=False)
    op.create_table('ext_proofs',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('course_id', sa.UUID(), nullable=False),
    sa.Column('parent_user_id', sa.UUID(), nullable=False),
    sa.Column('storage_key', sa.String(length=500), nullable=True),
    sa.Column('filename', sa.String(length=255), nullable=True),
    sa.Column('amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('method', sa.String(length=16), nullable=False),
    sa.Column('note', sa.String(length=500), nullable=True),
    sa.Column('status', sa.String(length=8), server_default='ACCEPTED', nullable=False),
    sa.Column('reviewed_by_user_id', sa.UUID(), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('rejection_reason', sa.String(length=500), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("method IN ('BANK_TRANSFER', 'MBWAY', 'CASH', 'POS')", name=op.f('ck_ext_proofs_method')),
    sa.CheckConstraint("status IN ('ACCEPTED', 'REJECTED')", name=op.f('ck_ext_proofs_status')),
    sa.ForeignKeyConstraint(['course_id'], ['ext_courses.id'], name=op.f('fk_ext_proofs_course_id_ext_courses')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_ext_proofs_organization_id_organizations')),
    sa.ForeignKeyConstraint(['parent_user_id'], ['users.id'], name=op.f('fk_ext_proofs_parent_user_id_users')),
    sa.ForeignKeyConstraint(['reviewed_by_user_id'], ['users.id'], name=op.f('fk_ext_proofs_reviewed_by_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ext_proofs'))
    )
    op.create_index(op.f('ix_ext_proofs_course_id'), 'ext_proofs', ['course_id'], unique=False)
    op.create_index(op.f('ix_ext_proofs_parent_user_id'), 'ext_proofs', ['parent_user_id'], unique=False)
    op.create_table('ext_staff',
    sa.Column('course_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('role', sa.String(length=8), nullable=False),
    sa.Column('share_pct', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("role IN ('COACH', 'SCHOOL')", name=op.f('ck_ext_staff_role')),
    sa.CheckConstraint('share_pct IS NULL OR share_pct BETWEEN 0 AND 100', name=op.f('ck_ext_staff_share_range')),
    sa.ForeignKeyConstraint(['course_id'], ['ext_courses.id'], name=op.f('fk_ext_staff_course_id_ext_courses'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_ext_staff_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ext_staff')),
    sa.UniqueConstraint('course_id', 'user_id', 'role', name='uq_ext_staff_course_user_role')
    )
    op.create_index(op.f('ix_ext_staff_course_id'), 'ext_staff', ['course_id'], unique=False)
    op.create_index(op.f('ix_ext_staff_user_id'), 'ext_staff', ['user_id'], unique=False)
    op.create_table('ext_work_sessions',
    sa.Column('course_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('ended_at IS NULL OR ended_at > started_at', name=op.f('ck_ext_work_sessions_times')),
    sa.ForeignKeyConstraint(['course_id'], ['ext_courses.id'], name=op.f('fk_ext_work_sessions_course_id_ext_courses')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_ext_work_sessions_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ext_work_sessions'))
    )
    op.create_index(op.f('ix_ext_work_sessions_course_id'), 'ext_work_sessions', ['course_id'], unique=False)
    op.create_index(op.f('ix_ext_work_sessions_user_id'), 'ext_work_sessions', ['user_id'], unique=False)
    op.create_table('ext_participants',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('course_id', sa.UUID(), nullable=False),
    sa.Column('group_id', sa.UUID(), nullable=True),
    sa.Column('parent_user_id', sa.UUID(), nullable=False),
    sa.Column('first_name', sa.String(length=80), nullable=False),
    sa.Column('last_name', sa.String(length=80), nullable=False),
    sa.Column('birth_date', sa.Date(), nullable=False),
    sa.Column('sex', sa.String(length=1), nullable=True),
    sa.Column('notes', sa.String(length=500), nullable=True),
    sa.Column('guardian_name', sa.String(length=160), nullable=True),
    sa.Column('guardian_phone', sa.String(length=40), nullable=True),
    sa.Column('status', sa.String(length=8), server_default='ACTIVE', nullable=False),
    sa.Column('joined_on', sa.Date(), nullable=False),
    sa.Column('left_on', sa.Date(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("status IN ('ACTIVE', 'LEFT')", name=op.f('ck_ext_participants_status')),
    sa.ForeignKeyConstraint(['course_id'], ['ext_courses.id'], name=op.f('fk_ext_participants_course_id_ext_courses')),
    sa.ForeignKeyConstraint(['group_id'], ['ext_groups.id'], name=op.f('fk_ext_participants_group_id_ext_groups'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_ext_participants_organization_id_organizations')),
    sa.ForeignKeyConstraint(['parent_user_id'], ['users.id'], name=op.f('fk_ext_participants_parent_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ext_participants'))
    )
    op.create_index(op.f('ix_ext_participants_course_id'), 'ext_participants', ['course_id'], unique=False)
    op.create_index(op.f('ix_ext_participants_group_id'), 'ext_participants', ['group_id'], unique=False)
    op.create_index(op.f('ix_ext_participants_parent_user_id'), 'ext_participants', ['parent_user_id'], unique=False)
    op.create_table('ext_attendances',
    sa.Column('course_id', sa.UUID(), nullable=False),
    sa.Column('participant_id', sa.UUID(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('present', sa.Boolean(), nullable=False),
    sa.Column('recorded_by_user_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['course_id'], ['ext_courses.id'], name=op.f('fk_ext_attendances_course_id_ext_courses')),
    sa.ForeignKeyConstraint(['participant_id'], ['ext_participants.id'], name=op.f('fk_ext_attendances_participant_id_ext_participants'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['recorded_by_user_id'], ['users.id'], name=op.f('fk_ext_attendances_recorded_by_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ext_attendances')),
    sa.UniqueConstraint('participant_id', 'date', name='uq_ext_attendances_participant_date')
    )
    op.create_index(op.f('ix_ext_attendances_course_id'), 'ext_attendances', ['course_id'], unique=False)
    op.create_index(op.f('ix_ext_attendances_participant_id'), 'ext_attendances', ['participant_id'], unique=False)
    op.create_table('ext_fees',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('course_id', sa.UUID(), nullable=False),
    sa.Column('participant_id', sa.UUID(), nullable=False),
    sa.Column('period', sa.String(length=7), nullable=False),
    sa.Column('amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('due_date', sa.Date(), nullable=False),
    sa.Column('status', sa.String(length=8), server_default='DUE', nullable=False),
    sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('method', sa.String(length=16), nullable=True),
    sa.Column('proof_id', sa.UUID(), nullable=True),
    sa.Column('recorded_by_user_id', sa.UUID(), nullable=True),
    sa.Column('coach_user_id', sa.UUID(), nullable=True),
    sa.Column('coach_share_pct', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("method IS NULL OR method IN ('BANK_TRANSFER', 'MBWAY', 'CASH', 'POS')", name=op.f('ck_ext_fees_method')),
    sa.CheckConstraint("status IN ('DUE', 'PAID', 'WAIVED')", name=op.f('ck_ext_fees_status')),
    sa.CheckConstraint('amount_cents >= 0', name=op.f('ck_ext_fees_amount_non_negative')),
    sa.ForeignKeyConstraint(['coach_user_id'], ['users.id'], name=op.f('fk_ext_fees_coach_user_id_users')),
    sa.ForeignKeyConstraint(['course_id'], ['ext_courses.id'], name=op.f('fk_ext_fees_course_id_ext_courses')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_ext_fees_organization_id_organizations')),
    sa.ForeignKeyConstraint(['participant_id'], ['ext_participants.id'], name=op.f('fk_ext_fees_participant_id_ext_participants'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['proof_id'], ['ext_proofs.id'], name=op.f('fk_ext_fees_proof_id_ext_proofs'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['recorded_by_user_id'], ['users.id'], name=op.f('fk_ext_fees_recorded_by_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ext_fees')),
    sa.UniqueConstraint('participant_id', 'period', name='uq_ext_fees_participant_period')
    )
    op.create_index('ix_ext_fees_course_status', 'ext_fees', ['course_id', 'status'], unique=False)
    op.create_index(op.f('ix_ext_fees_participant_id'), 'ext_fees', ['participant_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_ext_fees_participant_id'), table_name='ext_fees')
    op.drop_index('ix_ext_fees_course_status', table_name='ext_fees')
    op.drop_table('ext_fees')
    op.drop_index(op.f('ix_ext_attendances_participant_id'), table_name='ext_attendances')
    op.drop_index(op.f('ix_ext_attendances_course_id'), table_name='ext_attendances')
    op.drop_table('ext_attendances')
    op.drop_index(op.f('ix_ext_participants_parent_user_id'), table_name='ext_participants')
    op.drop_index(op.f('ix_ext_participants_group_id'), table_name='ext_participants')
    op.drop_index(op.f('ix_ext_participants_course_id'), table_name='ext_participants')
    op.drop_table('ext_participants')
    op.drop_index(op.f('ix_ext_work_sessions_user_id'), table_name='ext_work_sessions')
    op.drop_index(op.f('ix_ext_work_sessions_course_id'), table_name='ext_work_sessions')
    op.drop_table('ext_work_sessions')
    op.drop_index(op.f('ix_ext_staff_user_id'), table_name='ext_staff')
    op.drop_index(op.f('ix_ext_staff_course_id'), table_name='ext_staff')
    op.drop_table('ext_staff')
    op.drop_index(op.f('ix_ext_proofs_parent_user_id'), table_name='ext_proofs')
    op.drop_index(op.f('ix_ext_proofs_course_id'), table_name='ext_proofs')
    op.drop_table('ext_proofs')
    op.drop_index(op.f('ix_ext_notices_course_id'), table_name='ext_notices')
    op.drop_table('ext_notices')
    op.drop_index(op.f('ix_ext_groups_course_id'), table_name='ext_groups')
    op.drop_table('ext_groups')
    op.drop_index(op.f('ix_ext_courses_organization_id'), table_name='ext_courses')
    op.drop_table('ext_courses')
