"""Il curriculum del treinador (club/coach_cv.py): l'archivio dei suoi
documenti (`coach_documents`, file nel bucket privato), il suo Curriculum
Vitae (`coach_profiles.data`), gli eventi sportivi aggiunti a mano
(`coach_sport_events`, fuori da gare, calendario e ranking del club) e le
versioni PDF salvate (`coach_cv_exports`). Tutto della persona, non del club.

Revision ID: 0042
Revises: 0041
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0042'
down_revision: str | None = '0041'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('coach_cv_exports',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('kind', sa.String(length=8), nullable=False),
    sa.Column('storage_key', sa.String(length=500), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('note', sa.String(length=200), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("kind IN ('CV', 'SPORT')", name=op.f('ck_coach_cv_exports_kind')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_coach_cv_exports_organization_id_organizations')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_coach_cv_exports_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_coach_cv_exports'))
    )
    op.create_index(op.f('ix_coach_cv_exports_user_id'), 'coach_cv_exports', ['user_id'], unique=False)
    op.create_table('coach_documents',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('category', sa.String(length=16), nullable=False),
    sa.Column('issuer', sa.String(length=200), nullable=True),
    sa.Column('issued_on', sa.Date(), nullable=True),
    sa.Column('expires_on', sa.Date(), nullable=True),
    sa.Column('description', sa.String(length=2000), nullable=True),
    sa.Column('storage_key', sa.String(length=500), nullable=True),
    sa.Column('original_filename', sa.String(length=255), nullable=True),
    sa.Column('content_type', sa.String(length=100), nullable=True),
    sa.Column('size_bytes', sa.BigInteger(), nullable=True),
    sa.Column('show_in_cv', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("category IN ('COACH_DIPLOMA', 'FEDERATION', 'COURSE', 'FIRST_AID', 'ACADEMIC', 'PROFESSIONAL', 'PERSONAL', 'OTHER')", name=op.f('ck_coach_documents_category')),
    sa.CheckConstraint('expires_on IS NULL OR issued_on IS NULL OR expires_on >= issued_on', name=op.f('ck_coach_documents_dates')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_coach_documents_organization_id_organizations')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_coach_documents_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_coach_documents'))
    )
    op.create_index(op.f('ix_coach_documents_user_id'), 'coach_documents', ['user_id'], unique=False)
    op.create_table('coach_profiles',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('data', sa.dialects.postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_coach_profiles_organization_id_organizations')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_coach_profiles_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_coach_profiles')),
    sa.UniqueConstraint('user_id', name=op.f('uq_coach_profiles_user_id'))
    )
    op.create_table('coach_sport_events',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('event_type', sa.String(length=16), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('starts_on', sa.Date(), nullable=False),
    sa.Column('ends_on', sa.Date(), nullable=True),
    sa.Column('location', sa.String(length=200), nullable=True),
    sa.Column('organization_name', sa.String(length=200), nullable=True),
    sa.Column('level', sa.String(length=24), nullable=True),
    sa.Column('category', sa.String(length=120), nullable=True),
    sa.Column('placement', sa.SmallInteger(), nullable=True),
    sa.Column('result', sa.String(length=300), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('document_id', sa.UUID(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("event_type IN ('COMPETITION', 'STAGE', 'SEMINAR', 'COURSE', 'GRADING', 'REFEREEING', 'OTHER')", name=op.f('ck_coach_sport_events_event_type')),
    sa.CheckConstraint("role IN ('ATHLETE', 'COACH', 'ASSISTANT_COACH', 'REFEREE', 'ORGANIZER', 'OTHER')", name=op.f('ck_coach_sport_events_role')),
    sa.CheckConstraint('ends_on IS NULL OR ends_on >= starts_on', name=op.f('ck_coach_sport_events_dates')),
    sa.CheckConstraint('placement IS NULL OR placement IN (0, 1, 2, 3, 5, 7)', name=op.f('ck_coach_sport_events_placement')),
    sa.ForeignKeyConstraint(['document_id'], ['coach_documents.id'], name=op.f('fk_coach_sport_events_document_id_coach_documents'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_coach_sport_events_organization_id_organizations')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_coach_sport_events_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_coach_sport_events'))
    )
    op.create_index('ix_coach_sport_events_user_date', 'coach_sport_events', ['user_id', 'starts_on'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_coach_sport_events_user_date', table_name='coach_sport_events')
    op.drop_table('coach_sport_events')
    op.drop_table('coach_profiles')
    op.drop_index(op.f('ix_coach_documents_user_id'), table_name='coach_documents')
    op.drop_table('coach_documents')
    op.drop_index(op.f('ix_coach_cv_exports_user_id'), table_name='coach_cv_exports')
    op.drop_table('coach_cv_exports')
