"""I documenti del club: dichiarazioni, rivalidazione alla federazione,
atas, certidões delle Finanze e della Segurança Social, certificazioni
sportive, assicurazioni, statuto (`club_documents`, file nel bucket
privato, scadenza facoltativa). Regole in docs/club-portal.md, "Documenti
del club".

Revision ID: 0017
Revises: 0016
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0017'
down_revision: str | None = '0016'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('club_documents',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('category', sa.String(length=20), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('issued_on', sa.Date(), nullable=True),
    sa.Column('expires_on', sa.Date(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('storage_key', sa.String(length=500), nullable=False),
    sa.Column('original_filename', sa.String(length=255), nullable=False),
    sa.Column('content_type', sa.String(length=100), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('uploaded_by_user_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("category IN ('DECLARATION', 'FEDERATION', 'MINUTES', 'TAX', 'SOCIAL_SECURITY', 'SPORTS', 'INSURANCE', 'STATUTES', 'OTHER')", name=op.f('ck_club_documents_category')),
    sa.CheckConstraint('expires_on IS NULL OR issued_on IS NULL OR expires_on >= issued_on', name=op.f('ck_club_documents_date_range')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_documents_club_id_clubs')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_documents_organization_id_organizations')),
    sa.ForeignKeyConstraint(['uploaded_by_user_id'], ['users.id'], name=op.f('fk_club_documents_uploaded_by_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_documents'))
    )
    op.create_index(op.f('ix_club_documents_club_id'), 'club_documents', ['club_id'], unique=False)
    op.create_index(op.f('ix_club_documents_expires_on'), 'club_documents', ['expires_on'], unique=False)


def downgrade() -> None:
    op.drop_table('club_documents')
