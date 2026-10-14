"""JAVBOT: l'assistente dell'area privata e del sito.

Tre tabelle nuove (conversazioni, battute, compiti in attesa di conferma) e
una colonna sulla pagina pubblica del club: `club_sites.show_prices`, la
scelta del club di far dire i prezzi dei piani a chi chiede sul sito.
Nasce spenta: nessun prezzo diventa pubblico con questa migrazione.

Revision ID: 0008
Revises: 0007
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = '0008'
down_revision: str | None = '0007'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('javbot_conversations',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=True),
    sa.Column('state', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_javbot_conversations_club_id_clubs')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_javbot_conversations_organization_id_organizations')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_javbot_conversations_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_javbot_conversations'))
    )
    op.create_index(op.f('ix_javbot_conversations_club_id'), 'javbot_conversations', ['club_id'], unique=False)
    op.create_index(op.f('ix_javbot_conversations_organization_id'), 'javbot_conversations', ['organization_id'], unique=False)
    op.create_index(op.f('ix_javbot_conversations_user_id'), 'javbot_conversations', ['user_id'], unique=False)

    op.create_table('javbot_messages',
    sa.Column('conversation_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=True),
    sa.Column('role', sa.String(length=8), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('actions', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('quick_replies', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('intent', sa.String(length=40), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_javbot_messages_club_id_clubs')),
    sa.ForeignKeyConstraint(['conversation_id'], ['javbot_conversations.id'], name=op.f('fk_javbot_messages_conversation_id_javbot_conversations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_javbot_messages_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_javbot_messages'))
    )
    op.create_index('ix_javbot_messages_conversation_created', 'javbot_messages', ['conversation_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_javbot_messages_user_id'), 'javbot_messages', ['user_id'], unique=False)

    op.create_table('javbot_tasks',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('conversation_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=True),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.String(length=16), server_default='PENDING', nullable=False),
    sa.Column('result_ref', sa.String(length=64), nullable=True),
    sa.Column('done_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_javbot_tasks_club_id_clubs')),
    sa.ForeignKeyConstraint(['conversation_id'], ['javbot_conversations.id'], name=op.f('fk_javbot_tasks_conversation_id_javbot_conversations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_javbot_tasks_organization_id_organizations')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_javbot_tasks_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_javbot_tasks')),
    sa.UniqueConstraint('result_ref', name=op.f('uq_javbot_tasks_result_ref'))
    )
    op.create_index(op.f('ix_javbot_tasks_conversation_id'), 'javbot_tasks', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_javbot_tasks_organization_id'), 'javbot_tasks', ['organization_id'], unique=False)
    op.create_index(op.f('ix_javbot_tasks_user_id'), 'javbot_tasks', ['user_id'], unique=False)

    op.add_column('club_sites', sa.Column('show_prices', sa.Boolean(), server_default=sa.text('false'), nullable=False))


def downgrade() -> None:
    op.drop_column('club_sites', 'show_prices')
    op.drop_table('javbot_tasks')
    op.drop_table('javbot_messages')
    op.drop_table('javbot_conversations')
