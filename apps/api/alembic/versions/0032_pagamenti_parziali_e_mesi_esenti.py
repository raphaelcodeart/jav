"""Pagamento parziale e mese esente delle quote del club (club/fee_splits.py):

- `club_fees.split_from_fee_id` / `split_reason`: il resto di una quota
  pagata in parte, legato alla quota da cui nasce, con il motivo;
- `club_fees.waive_kind`: NULL = condono, `EXEMPT` = «Isenta este mês»;
- il vincolo `ck_club_payment_proofs_file_or_credit` accetta anche una
  prova senza foto registrata dalla segreteria (`reviewed_by_user_id`): il
  «Segna pagato» con carta, MB Way o bonifico senza foto, che l'interfaccia
  permette, finiva in un errore 500.

Revision ID: 0032
Revises: 0031
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = '0032'
down_revision: str | None = '0031'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('club_fees', sa.Column('waive_kind', sa.String(length=16), nullable=True))
    op.add_column('club_fees', sa.Column('split_from_fee_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('club_fees', sa.Column('split_reason', sa.String(length=500), nullable=True))
    op.create_check_constraint(
        op.f('ck_club_fees_waive_kind'), 'club_fees', "waive_kind IS NULL OR waive_kind IN ('EXEMPT')"
    )
    op.create_foreign_key(
        op.f('fk_club_fees_split_from_fee_id_club_fees'), 'club_fees', 'club_fees', ['split_from_fee_id'], ['id']
    )
    op.create_index(op.f('ix_club_fees_split_from_fee_id'), 'club_fees', ['split_from_fee_id'], unique=False)
    op.drop_constraint(op.f('ck_club_payment_proofs_file_or_credit'), 'club_payment_proofs', type_='check')
    op.create_check_constraint(
        op.f('ck_club_payment_proofs_file_or_credit'), 'club_payment_proofs',
        "storage_key IS NOT NULL OR credit_cents = amount_cents OR method = 'CASH' OR reviewed_by_user_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_club_payment_proofs_file_or_credit'), 'club_payment_proofs', type_='check')
    op.create_check_constraint(
        op.f('ck_club_payment_proofs_file_or_credit'), 'club_payment_proofs',
        "storage_key IS NOT NULL OR credit_cents = amount_cents OR method = 'CASH'",
    )
    op.drop_index(op.f('ix_club_fees_split_from_fee_id'), table_name='club_fees')
    op.drop_constraint(op.f('fk_club_fees_split_from_fee_id_club_fees'), 'club_fees', type_='foreignkey')
    op.drop_constraint(op.f('ck_club_fees_waive_kind'), 'club_fees', type_='check')
    op.drop_column('club_fees', 'split_reason')
    op.drop_column('club_fees', 'split_from_fee_id')
    op.drop_column('club_fees', 'waive_kind')
