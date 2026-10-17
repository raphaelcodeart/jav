"""I relatórios degli eventi (club/event_reports.py): il racconto del
treinador, le spese divise per voce e le foto nel bucket privato
(`club_event_reports`, `club_event_report_costs`, `club_event_report_photos`).

Revision ID: 0033
Revises: 0032
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0033'
down_revision: str | None = '0032'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('club_event_reports',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('competition_id', sa.UUID(), nullable=False),
    sa.Column('author_user_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('narrative', sa.Text(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['author_user_id'], ['users.id'], name=op.f('fk_club_event_reports_author_user_id_users')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_event_reports_club_id_clubs')),
    sa.ForeignKeyConstraint(['competition_id'], ['club_competitions.id'], name=op.f('fk_club_event_reports_competition_id_club_competitions')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_event_reports_organization_id_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_event_reports')),
    sa.UniqueConstraint('club_id', 'competition_id', 'author_user_id', name='uq_club_event_reports_author')
    )
    op.create_index(op.f('ix_club_event_reports_organization_id'), 'club_event_reports', ['organization_id'], unique=False)
    op.create_index(op.f('ix_club_event_reports_club_id'), 'club_event_reports', ['club_id'], unique=False)
    op.create_index(op.f('ix_club_event_reports_competition_id'), 'club_event_reports', ['competition_id'], unique=False)
    op.create_table('club_event_report_costs',
    sa.Column('report_id', sa.UUID(), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('note', sa.String(length=300), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("kind IN ('HOTEL', 'TRAVEL', 'FUEL', 'FOOD', 'ENTRY_FEES', 'OTHER')", name=op.f('ck_club_event_report_costs_kind')),
    sa.CheckConstraint('amount_cents >= 0', name=op.f('ck_club_event_report_costs_amount_non_negative')),
    sa.ForeignKeyConstraint(['report_id'], ['club_event_reports.id'], name=op.f('fk_club_event_report_costs_report_id_club_event_reports'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_event_report_costs')),
    sa.UniqueConstraint('report_id', 'kind', name='uq_club_event_report_costs_report_kind')
    )
    op.create_index(op.f('ix_club_event_report_costs_report_id'), 'club_event_report_costs', ['report_id'], unique=False)
    op.create_table('club_event_report_photos',
    sa.Column('report_id', sa.UUID(), nullable=False),
    sa.Column('storage_key', sa.String(length=300), nullable=False),
    sa.Column('content_type', sa.String(length=50), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['report_id'], ['club_event_reports.id'], name=op.f('fk_club_event_report_photos_report_id_club_event_reports'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_event_report_photos'))
    )
    op.create_index(op.f('ix_club_event_report_photos_report_id'), 'club_event_report_photos', ['report_id'], unique=False)


def downgrade() -> None:
    op.drop_table('club_event_report_photos')
    op.drop_table('club_event_report_costs')
    op.drop_table('club_event_reports')
