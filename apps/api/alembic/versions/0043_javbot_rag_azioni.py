"""JAVBOT più intelligente spendendo meno (javbot/rag.py, javbot/actions.py,
javbot/llm.py): la base di conoscenza accoglie anche i regolamenti degli
eventi e le schede scritte dal gestionale (`source` EVENT / DATA,
`source_ref`; `storage_key` facoltativo); il regolamento PDF di ogni gara o
evento (`club_competitions.regulation_*`); le schede sotto una risposta
(`javbot_messages.cards`); il contatore delle risposte e dei token
(`javbot_usage`).

Revision ID: 0043
Revises: 0042
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0043'
down_revision: str | None = '0042'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('javbot_usage',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=True),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('route', sa.String(length=8), nullable=False),
    sa.Column('provider', sa.String(length=12), nullable=True),
    sa.Column('model', sa.String(length=60), nullable=True),
    sa.Column('calls', sa.Integer(), server_default='0', nullable=False),
    sa.Column('input_tokens', sa.Integer(), server_default='0', nullable=False),
    sa.Column('output_tokens', sa.Integer(), server_default='0', nullable=False),
    sa.Column('cached_tokens', sa.Integer(), server_default='0', nullable=False),
    sa.Column('intent', sa.String(length=40), nullable=True),
    sa.Column('ok', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("route IN ('RULES', 'ACTION', 'CACHE', 'RAG', 'AGENT', 'EXTRACT', 'ARTICLE')", name=op.f('ck_javbot_usage_route')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_javbot_usage_club_id_clubs'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_javbot_usage_organization_id_organizations')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_javbot_usage_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_javbot_usage'))
    )
    op.create_index('ix_javbot_usage_org_created', 'javbot_usage', ['organization_id', 'created_at'], unique=False)
    op.add_column('club_competitions', sa.Column('regulation_storage_key', sa.String(length=512), nullable=True))
    op.add_column('club_competitions', sa.Column('regulation_filename', sa.String(length=255), nullable=True))
    op.add_column('club_competitions', sa.Column('regulation_size', sa.Integer(), nullable=True))
    op.add_column('javbot_knowledge_documents', sa.Column('source', sa.String(length=8), server_default='UPLOAD', nullable=False))
    op.add_column('javbot_knowledge_documents', sa.Column('source_ref', sa.String(length=80), nullable=True))
    op.create_check_constraint(op.f('ck_javbot_knowledge_documents_source'), 'javbot_knowledge_documents',
                               "source IN ('UPLOAD', 'EVENT', 'DATA')")
    op.alter_column('javbot_knowledge_documents', 'storage_key',
               existing_type=sa.VARCHAR(length=512),
               nullable=True)
    op.create_index('uq_javbot_knowledge_documents_source_ref', 'javbot_knowledge_documents', ['source_ref'], unique=True, postgresql_where=sa.text('source_ref IS NOT NULL'))
    op.add_column('javbot_messages', sa.Column('cards', sa.dialects.postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False))


def downgrade() -> None:
    op.drop_constraint(op.f('ck_javbot_knowledge_documents_source'), 'javbot_knowledge_documents', type_='check')
    op.drop_column('javbot_messages', 'cards')
    op.drop_index('uq_javbot_knowledge_documents_source_ref', table_name='javbot_knowledge_documents', postgresql_where=sa.text('source_ref IS NOT NULL'))
    op.alter_column('javbot_knowledge_documents', 'storage_key',
               existing_type=sa.VARCHAR(length=512),
               nullable=False)
    op.drop_column('javbot_knowledge_documents', 'source_ref')
    op.drop_column('javbot_knowledge_documents', 'source')
    op.drop_column('club_competitions', 'regulation_size')
    op.drop_column('club_competitions', 'regulation_filename')
    op.drop_column('club_competitions', 'regulation_storage_key')
    op.drop_index('ix_javbot_usage_org_created', table_name='javbot_usage')
    op.drop_table('javbot_usage')
