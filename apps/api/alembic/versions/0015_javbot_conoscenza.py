"""La base di conoscenza di JAVBOT dell'area privata.

- `javbot_knowledge_documents`: i PDF caricati, nel bucket privato;
  `club_id` NULL = la base comune a tutti i club (la carica la piattaforma),
  con un club = i documenti di quel club (li carica la sua segreteria);
- `javbot_knowledge_chunks`: il testo dei PDF a pezzi, normalizzato
  (`norm`), con l'indice full-text GIN su `to_tsvector('simple', norm)`;
- `javbot_instructions`: il prompt scritto da chi amministra, uno comune e
  al più uno per club (due indici UNIQUE parziali).

Regole in docs/club-portal.md, "JAVBOT" → "L'assistente dell'area
riservata".

Revision ID: 0015
Revises: 0014
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0015'
down_revision: str | None = '0014'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('javbot_knowledge_documents',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=True),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('storage_key', sa.String(length=512), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('page_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('char_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('uploaded_by_user_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_javbot_knowledge_documents_club_id_clubs')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_javbot_knowledge_documents_organization_id_organizations')),
    sa.ForeignKeyConstraint(['uploaded_by_user_id'], ['users.id'], name=op.f('fk_javbot_knowledge_documents_uploaded_by_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_javbot_knowledge_documents'))
    )
    op.create_index(op.f('ix_javbot_knowledge_documents_club_id'), 'javbot_knowledge_documents', ['club_id'], unique=False)
    op.create_index(op.f('ix_javbot_knowledge_documents_organization_id'), 'javbot_knowledge_documents', ['organization_id'], unique=False)

    op.create_table('javbot_knowledge_chunks',
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=True),
    sa.Column('ordinal', sa.Integer(), nullable=False),
    sa.Column('page', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('norm', sa.Text(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_javbot_knowledge_chunks_club_id_clubs'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['document_id'], ['javbot_knowledge_documents.id'], name=op.f('fk_javbot_knowledge_chunks_document_id_javbot_knowledge_documents'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_javbot_knowledge_chunks_organization_id_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_javbot_knowledge_chunks'))
    )
    op.create_index(op.f('ix_javbot_knowledge_chunks_club_id'), 'javbot_knowledge_chunks', ['club_id'], unique=False)
    op.create_index(op.f('ix_javbot_knowledge_chunks_document_id'), 'javbot_knowledge_chunks', ['document_id'], unique=False)
    op.create_index(
        'ix_javbot_knowledge_chunks_search', 'javbot_knowledge_chunks', [sa.text("to_tsvector('simple', norm)")],
        unique=False, postgresql_using='gin',
    )

    op.create_table('javbot_instructions',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=True),
    sa.Column('text', sa.Text(), server_default='', nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_by_user_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_javbot_instructions_club_id_clubs'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_javbot_instructions_organization_id_organizations')),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], name=op.f('fk_javbot_instructions_updated_by_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_javbot_instructions'))
    )
    op.create_index(
        'uq_javbot_instructions_club', 'javbot_instructions', ['club_id'], unique=True,
        postgresql_where=sa.text('club_id IS NOT NULL'),
    )
    op.create_index(
        'uq_javbot_instructions_common', 'javbot_instructions', ['organization_id'], unique=True,
        postgresql_where=sa.text('club_id IS NULL'),
    )


def downgrade() -> None:
    op.drop_table('javbot_instructions')
    op.drop_table('javbot_knowledge_chunks')
    op.drop_table('javbot_knowledge_documents')
