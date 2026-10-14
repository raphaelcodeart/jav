"""La contabilità del club: spese, costi fissi, tariffe orarie dello staff e
percentuale della piattaforma.

Quattro tabelle nuove, nessuna colonna sulle tabelle esistenti. Si salvano
solo i fatti che non si ricavano da altro (una spesa, un costo fisso, una
tariffa, una percentuale): incassi, debiti, costo dello staff, commissione
della piattaforma e risultato si calcolano a ogni lettura
(club/accounting.py, docs/club-portal.md "Contabilità"). Nessun club ha una
riga in `club_platform_fees` dopo questa migrazione: vale il 10% di default.

Revision ID: 0007
Revises: 0006
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0007'
down_revision: str | None = '0006'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('club_platform_fees',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('pct', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('valid_from', sa.Date(), nullable=False),
    sa.Column('set_by_user_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('EXTRACT(DAY FROM valid_from) = 1', name=op.f('ck_club_platform_fees_first_of_month')),
    sa.CheckConstraint('pct >= 0 AND pct <= 100', name=op.f('ck_club_platform_fees_pct_range')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_platform_fees_club_id_clubs')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_platform_fees_organization_id_organizations')),
    sa.ForeignKeyConstraint(['set_by_user_id'], ['users.id'], name=op.f('fk_club_platform_fees_set_by_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_platform_fees')),
    sa.UniqueConstraint('club_id', 'valid_from', name='uq_club_platform_fees_club_from')
    )
    op.create_index(op.f('ix_club_platform_fees_club_id'), 'club_platform_fees', ['club_id'], unique=False)
    op.create_index(op.f('ix_club_platform_fees_organization_id'), 'club_platform_fees', ['organization_id'], unique=False)

    op.create_table('club_recurring_expenses',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('category', sa.String(length=16), nullable=False),
    sa.Column('amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('description', sa.String(length=200), nullable=False),
    sa.Column('supplier', sa.String(length=200), nullable=True),
    sa.Column('payment_method', sa.String(length=16), nullable=False),
    sa.Column('day_of_month', sa.SmallInteger(), nullable=False),
    sa.Column('starts_on', sa.Date(), nullable=False),
    sa.Column('ends_on', sa.Date(), nullable=True),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_by_user_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("category IN ('RENT', 'STAFF', 'FEDERATION', 'INSURANCE', 'EQUIPMENT', 'TRANSPORT', 'EVENTS', 'UTILITIES', 'MARKETING', 'ADMIN', 'OTHER')", name=op.f('ck_club_recurring_expenses_category')),
    sa.CheckConstraint("payment_method IN ('BANK_TRANSFER', 'CASH', 'CARD', 'DIRECT_DEBIT', 'OTHER')", name=op.f('ck_club_recurring_expenses_payment_method')),
    sa.CheckConstraint('amount_cents > 0', name=op.f('ck_club_recurring_expenses_amount_positive')),
    sa.CheckConstraint('day_of_month BETWEEN 1 AND 28', name=op.f('ck_club_recurring_expenses_day_of_month_range')),
    sa.CheckConstraint('ends_on IS NULL OR ends_on >= starts_on', name=op.f('ck_club_recurring_expenses_date_range')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_recurring_expenses_club_id_clubs')),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_club_recurring_expenses_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_recurring_expenses_organization_id_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_recurring_expenses'))
    )
    op.create_index(op.f('ix_club_recurring_expenses_club_id'), 'club_recurring_expenses', ['club_id'], unique=False)
    op.create_index(op.f('ix_club_recurring_expenses_organization_id'), 'club_recurring_expenses', ['organization_id'], unique=False)

    op.create_table('club_staff_rates',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('hourly_rate_cents', sa.BigInteger(), nullable=False),
    sa.Column('valid_from', sa.Date(), nullable=False),
    sa.Column('set_by_user_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('hourly_rate_cents >= 0', name=op.f('ck_club_staff_rates_rate_non_negative')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_staff_rates_club_id_clubs')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_staff_rates_organization_id_organizations')),
    sa.ForeignKeyConstraint(['set_by_user_id'], ['users.id'], name=op.f('fk_club_staff_rates_set_by_user_id_users')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_club_staff_rates_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_staff_rates')),
    sa.UniqueConstraint('club_id', 'user_id', 'valid_from', name='uq_club_staff_rates_club_user_from')
    )
    op.create_index(op.f('ix_club_staff_rates_club_id'), 'club_staff_rates', ['club_id'], unique=False)
    op.create_index(op.f('ix_club_staff_rates_organization_id'), 'club_staff_rates', ['organization_id'], unique=False)
    op.create_index(op.f('ix_club_staff_rates_user_id'), 'club_staff_rates', ['user_id'], unique=False)

    op.create_table('club_expenses',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('spent_on', sa.Date(), nullable=False),
    sa.Column('category', sa.String(length=16), nullable=False),
    sa.Column('amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('description', sa.String(length=200), nullable=False),
    sa.Column('supplier', sa.String(length=200), nullable=True),
    sa.Column('payment_method', sa.String(length=16), nullable=False),
    sa.Column('receipt_storage_key', sa.String(length=500), nullable=True),
    sa.Column('receipt_filename', sa.String(length=255), nullable=True),
    sa.Column('receipt_content_type', sa.String(length=100), nullable=True),
    sa.Column('created_by_user_id', sa.UUID(), nullable=True),
    sa.Column('recurring_id', sa.UUID(), nullable=True),
    sa.Column('period', sa.String(length=7), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("category IN ('RENT', 'STAFF', 'FEDERATION', 'INSURANCE', 'EQUIPMENT', 'TRANSPORT', 'EVENTS', 'UTILITIES', 'MARKETING', 'ADMIN', 'OTHER')", name=op.f('ck_club_expenses_category')),
    sa.CheckConstraint("payment_method IN ('BANK_TRANSFER', 'CASH', 'CARD', 'DIRECT_DEBIT', 'OTHER')", name=op.f('ck_club_expenses_payment_method')),
    sa.CheckConstraint('(recurring_id IS NULL) = (period IS NULL)', name=op.f('ck_club_expenses_recurring_period')),
    sa.CheckConstraint('amount_cents > 0', name=op.f('ck_club_expenses_amount_positive')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_expenses_club_id_clubs')),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_club_expenses_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_expenses_organization_id_organizations')),
    sa.ForeignKeyConstraint(['recurring_id'], ['club_recurring_expenses.id'], name=op.f('fk_club_expenses_recurring_id_club_recurring_expenses')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_expenses')),
    sa.UniqueConstraint('recurring_id', 'period', name='uq_club_expenses_recurring_period')
    )
    op.create_index(op.f('ix_club_expenses_club_id'), 'club_expenses', ['club_id'], unique=False)
    op.create_index('ix_club_expenses_club_spent_on', 'club_expenses', ['club_id', 'spent_on'], unique=False)
    op.create_index(op.f('ix_club_expenses_organization_id'), 'club_expenses', ['organization_id'], unique=False)
    op.create_index(op.f('ix_club_expenses_recurring_id'), 'club_expenses', ['recurring_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_club_expenses_recurring_id'), table_name='club_expenses')
    op.drop_index(op.f('ix_club_expenses_organization_id'), table_name='club_expenses')
    op.drop_index('ix_club_expenses_club_spent_on', table_name='club_expenses')
    op.drop_index(op.f('ix_club_expenses_club_id'), table_name='club_expenses')
    op.drop_table('club_expenses')
    op.drop_index(op.f('ix_club_staff_rates_user_id'), table_name='club_staff_rates')
    op.drop_index(op.f('ix_club_staff_rates_organization_id'), table_name='club_staff_rates')
    op.drop_index(op.f('ix_club_staff_rates_club_id'), table_name='club_staff_rates')
    op.drop_table('club_staff_rates')
    op.drop_index(op.f('ix_club_recurring_expenses_organization_id'), table_name='club_recurring_expenses')
    op.drop_index(op.f('ix_club_recurring_expenses_club_id'), table_name='club_recurring_expenses')
    op.drop_table('club_recurring_expenses')
    op.drop_index(op.f('ix_club_platform_fees_organization_id'), table_name='club_platform_fees')
    op.drop_index(op.f('ix_club_platform_fees_club_id'), table_name='club_platform_fees')
    op.drop_table('club_platform_fees')
