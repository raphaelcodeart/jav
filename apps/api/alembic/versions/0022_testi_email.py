"""I testi delle email personalizzati dal superadmin
(`email_template_overrides`, app/domains/email_texts, docs/emails.md).

Revision ID: 0022
Revises: 0021
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0022'
down_revision: str | None = '0021'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('email_template_overrides',
    sa.Column('key', sa.String(length=40), nullable=False),
    sa.Column('subject', sa.String(length=200), nullable=False),
    sa.Column('heading', sa.String(length=200), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('cta_label', sa.String(length=80), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_by_user_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], name=op.f('fk_email_template_overrides_updated_by_user_id_users')),
    sa.PrimaryKeyConstraint('key', name=op.f('pk_email_template_overrides'))
    )


def downgrade() -> None:
    op.drop_table('email_template_overrides')
