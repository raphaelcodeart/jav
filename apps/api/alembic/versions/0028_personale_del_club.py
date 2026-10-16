"""Il personale del club: compiti svolti e lavoretti occasionali
(`club_staff_tasks`) e le comunicazioni dello staff con il club o con
JudoArteVida (`club_staff_messages`), club/staff_work.py.

Revision ID: 0028
Revises: 0027
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0028'
down_revision: str | None = '0027'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('club_staff_tasks',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('person_name', sa.String(length=150), nullable=False),
    sa.Column('kind', sa.String(length=10), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('done_on', sa.Date(), nullable=False),
    sa.Column('minutes', sa.Integer(), nullable=True),
    sa.Column('cost_cents', sa.BigInteger(), server_default=sa.text('0'), nullable=False),
    sa.Column('note', sa.String(length=500), nullable=True),
    sa.Column('paid_on', sa.Date(), nullable=True),
    sa.Column('expense_id', sa.UUID(), nullable=True),
    sa.Column('recorded_by_user_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("kind IN ('TASK', 'ODD_JOB')", name=op.f('ck_club_staff_tasks_kind')),
    sa.CheckConstraint('cost_cents >= 0', name=op.f('ck_club_staff_tasks_cost_not_negative')),
    sa.CheckConstraint('minutes IS NULL OR minutes > 0', name=op.f('ck_club_staff_tasks_minutes_positive')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_staff_tasks_club_id_clubs')),
    sa.ForeignKeyConstraint(['expense_id'], ['club_expenses.id'], name=op.f('fk_club_staff_tasks_expense_id_club_expenses'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_staff_tasks_organization_id_organizations')),
    sa.ForeignKeyConstraint(['recorded_by_user_id'], ['users.id'], name=op.f('fk_club_staff_tasks_recorded_by_user_id_users')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_club_staff_tasks_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_staff_tasks'))
    )
    op.create_index(op.f('ix_club_staff_tasks_club_id'), 'club_staff_tasks', ['club_id'], unique=False)
    op.create_index(op.f('ix_club_staff_tasks_user_id'), 'club_staff_tasks', ['user_id'], unique=False)
    op.create_index(op.f('ix_club_staff_tasks_done_on'), 'club_staff_tasks', ['done_on'], unique=False)
    op.create_table('club_staff_messages',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('staff_user_id', sa.UUID(), nullable=False),
    sa.Column('channel', sa.String(length=8), nullable=False),
    sa.Column('from_staff', sa.Boolean(), nullable=False),
    sa.Column('author_user_id', sa.UUID(), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("channel IN ('CLUB', 'JAV')", name=op.f('ck_club_staff_messages_channel')),
    sa.ForeignKeyConstraint(['author_user_id'], ['users.id'], name=op.f('fk_club_staff_messages_author_user_id_users')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_staff_messages_club_id_clubs')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_staff_messages_organization_id_organizations')),
    sa.ForeignKeyConstraint(['staff_user_id'], ['users.id'], name=op.f('fk_club_staff_messages_staff_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_staff_messages'))
    )
    op.create_index(op.f('ix_club_staff_messages_club_id'), 'club_staff_messages', ['club_id'], unique=False)
    op.create_index(op.f('ix_club_staff_messages_staff_user_id'), 'club_staff_messages', ['staff_user_id'], unique=False)


def downgrade() -> None:
    op.drop_table('club_staff_messages')
    op.drop_table('club_staff_tasks')
