"""Gli sponsor della rete (`sponsors`: la barra dei loghi della home e la
pagina di ogni sponsor) e l'argomento dei messaggi dal sito
(`contact_messages.topic`: domanda, sponsor, iscrizione, eventi, altro).
Regole in docs/club-portal.md, "Sponsor" e "Messaggi dal sito".

Revision ID: 0019
Revises: 0018
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0019'
down_revision: str | None = '0018'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('contact_messages', sa.Column('topic', sa.String(length=16), server_default=sa.text("'GENERAL'"), nullable=False))
    op.create_check_constraint(
        op.f('ck_contact_messages_topic'), 'contact_messages',
        "topic IN ('GENERAL', 'SPONSOR', 'ENROLMENT', 'EVENTS', 'OTHER')",
    )
    op.create_table('sponsors',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('slug', sa.String(length=80), nullable=False),
    sa.Column('tagline', sa.String(length=200), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('logo_url', sa.String(length=500), nullable=True),
    sa.Column('website_url', sa.String(length=500), nullable=True),
    sa.Column('color', sa.String(length=7), nullable=True),
    sa.Column('sort_order', sa.SmallInteger(), server_default=sa.text('0'), nullable=False),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("website_url IS NULL OR website_url ~* '^https?://'", name=op.f('ck_sponsors_website_url')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_sponsors_organization_id_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sponsors')),
    sa.UniqueConstraint('organization_id', 'slug', name='uq_sponsors_org_slug')
    )
    op.create_index(op.f('ix_sponsors_organization_id'), 'sponsors', ['organization_id'], unique=False)


def downgrade() -> None:
    op.drop_table('sponsors')
    op.drop_constraint(op.f('ck_contact_messages_topic'), 'contact_messages', type_='check')
    op.drop_column('contact_messages', 'topic')
