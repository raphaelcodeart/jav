"""Sconti, iscrizione annuale con quota socio, credito nel wallet, eventi e trasporto.

- Atleti: escalão (A/B/C) e judo adattato, che danno lo sconto sulla
  mensilità (club/pricing.py).
- Quote: il listino e lo sconto applicato, congelati sulla quota; la quota
  socio del genitore (MEMBERSHIP), legata al genitore e non a un atleta, una
  per famiglia e per anno.
- Prove di pagamento: la parte pagata con il credito del wallet (inviti); la
  ricevuta diventa facoltativa quando il credito copre tutto. Il movimento del
  wallet punta alla prova (`reference_club_proof_id`).
- Eventi: gara o stage, e i dati della richiesta di trasporto; la tabella
  `club_transport_requests` con la lettera, una per evento.

Revision ID: 0004
Revises: 0003
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Atleti ---
    op.add_column('club_athletes', sa.Column('social_tier', sa.String(length=1), nullable=True))
    op.add_column('club_athletes', sa.Column('adapted_judo', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.create_check_constraint(op.f('ck_club_athletes_social_tier'), 'club_athletes', "social_tier IS NULL OR social_tier IN ('A', 'B', 'C')")

    # --- Quote ---
    op.alter_column('club_fees', 'athlete_id', nullable=True)
    op.add_column('club_fees', sa.Column('guardian_user_id', sa.UUID(), nullable=True))
    op.add_column('club_fees', sa.Column('gross_amount_cents', sa.BigInteger(), nullable=True))
    op.add_column('club_fees', sa.Column('discount_cents', sa.BigInteger(), server_default=sa.text('0'), nullable=False))
    op.add_column('club_fees', sa.Column('discount_note', sa.String(length=200), nullable=True))
    op.create_index(op.f('ix_club_fees_guardian_user_id'), 'club_fees', ['guardian_user_id'], unique=False)
    op.create_foreign_key(op.f('fk_club_fees_guardian_user_id_users'), 'club_fees', 'users', ['guardian_user_id'], ['id'])
    op.drop_constraint(op.f('ck_club_fees_kind'), 'club_fees', type_='check')
    op.create_check_constraint(op.f('ck_club_fees_kind'), 'club_fees', "kind IN ('MONTHLY', 'ENROLLMENT', 'COMPETITION', 'MEMBERSHIP')")
    op.create_check_constraint(op.f('ck_club_fees_discount_non_negative'), 'club_fees', 'discount_cents >= 0')
    op.create_check_constraint(
        op.f('ck_club_fees_owner'), 'club_fees',
        "(kind = 'MEMBERSHIP' AND athlete_id IS NULL AND guardian_user_id IS NOT NULL)"
        " OR (kind <> 'MEMBERSHIP' AND athlete_id IS NOT NULL)",
    )
    op.create_index(
        'uq_club_fees_guardian_membership', 'club_fees', ['club_id', 'guardian_user_id', 'period'],
        unique=True, postgresql_where=sa.text("kind = 'MEMBERSHIP'"),
    )

    # --- Prove di pagamento ---
    op.alter_column('club_payment_proofs', 'storage_key', nullable=True)
    op.alter_column('club_payment_proofs', 'original_filename', nullable=True)
    op.alter_column('club_payment_proofs', 'content_type', nullable=True)
    op.add_column('club_payment_proofs', sa.Column('credit_cents', sa.BigInteger(), server_default=sa.text('0'), nullable=False))
    op.create_check_constraint(op.f('ck_club_payment_proofs_credit_range'), 'club_payment_proofs', 'credit_cents >= 0 AND credit_cents <= amount_cents')
    op.create_check_constraint(op.f('ck_club_payment_proofs_file_or_credit'), 'club_payment_proofs', 'storage_key IS NOT NULL OR credit_cents = amount_cents')
    op.add_column('wallet_transactions', sa.Column('reference_club_proof_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_wallet_transactions_reference_club_proof_id'), 'wallet_transactions', ['reference_club_proof_id'], unique=False)
    op.create_foreign_key(
        op.f('fk_wallet_transactions_reference_club_proof_id_club_payment_proofs'), 'wallet_transactions',
        'club_payment_proofs', ['reference_club_proof_id'], ['id'],
    )

    # --- Eventi e trasporto ---
    op.add_column('club_competitions', sa.Column('kind', sa.String(length=16), server_default='COMPETITION', nullable=False))
    op.add_column('club_competitions', sa.Column('transport_needed', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('club_competitions', sa.Column('transport_entity_name', sa.String(length=200), nullable=True))
    op.add_column('club_competitions', sa.Column('transport_entity_email', sa.String(length=255), nullable=True))
    op.add_column('club_competitions', sa.Column('transport_departure', sa.String(length=300), nullable=True))
    op.add_column('club_competitions', sa.Column('transport_return', sa.String(length=300), nullable=True))
    op.add_column('club_competitions', sa.Column('transport_companions', sa.Integer(), server_default=sa.text('0'), nullable=False))
    op.add_column('club_competitions', sa.Column('transport_notes', sa.Text(), nullable=True))
    op.add_column('club_competitions', sa.Column('transport_auto_send', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.create_check_constraint(op.f('ck_club_competitions_kind'), 'club_competitions', "kind IN ('COMPETITION', 'STAGE')")
    op.create_check_constraint(op.f('ck_club_competitions_transport_companions_non_negative'), 'club_competitions', 'transport_companions >= 0')

    op.create_table('club_transport_requests',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('competition_id', sa.UUID(), nullable=False),
    sa.Column('to_email', sa.String(length=255), nullable=True),
    sa.Column('subject', sa.String(length=300), nullable=False),
    sa.Column('body_text', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('athletes_count', sa.Integer(), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('sent_by_user_id', sa.UUID(), nullable=True),
    sa.Column('last_error', sa.String(length=500), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("status IN ('DRAFT', 'SENT')", name=op.f('ck_club_transport_requests_status')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_transport_requests_club_id_clubs')),
    sa.ForeignKeyConstraint(['competition_id'], ['club_competitions.id'], name=op.f('fk_club_transport_requests_competition_id_club_competitions')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_transport_requests_organization_id_organizations')),
    sa.ForeignKeyConstraint(['sent_by_user_id'], ['users.id'], name=op.f('fk_club_transport_requests_sent_by_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_transport_requests')),
    sa.UniqueConstraint('competition_id', name='uq_club_transport_requests_competition_id')
    )
    op.create_index(op.f('ix_club_transport_requests_club_id'), 'club_transport_requests', ['club_id'], unique=False)
    op.create_index(op.f('ix_club_transport_requests_organization_id'), 'club_transport_requests', ['organization_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_club_transport_requests_organization_id'), table_name='club_transport_requests')
    op.drop_index(op.f('ix_club_transport_requests_club_id'), table_name='club_transport_requests')
    op.drop_table('club_transport_requests')
    op.drop_constraint(op.f('ck_club_competitions_transport_companions_non_negative'), 'club_competitions', type_='check')
    op.drop_constraint(op.f('ck_club_competitions_kind'), 'club_competitions', type_='check')
    for column in ('transport_auto_send', 'transport_notes', 'transport_companions', 'transport_return',
                   'transport_departure', 'transport_entity_email', 'transport_entity_name', 'transport_needed', 'kind'):
        op.drop_column('club_competitions', column)
    op.drop_constraint(op.f('fk_wallet_transactions_reference_club_proof_id_club_payment_proofs'), 'wallet_transactions', type_='foreignkey')
    op.drop_index(op.f('ix_wallet_transactions_reference_club_proof_id'), table_name='wallet_transactions')
    op.drop_column('wallet_transactions', 'reference_club_proof_id')
    op.drop_constraint(op.f('ck_club_payment_proofs_file_or_credit'), 'club_payment_proofs', type_='check')
    op.drop_constraint(op.f('ck_club_payment_proofs_credit_range'), 'club_payment_proofs', type_='check')
    op.drop_column('club_payment_proofs', 'credit_cents')
    op.drop_index('uq_club_fees_guardian_membership', table_name='club_fees')
    op.execute("DELETE FROM club_fees WHERE kind = 'MEMBERSHIP'")
    op.drop_constraint(op.f('ck_club_fees_owner'), 'club_fees', type_='check')
    op.drop_constraint(op.f('ck_club_fees_discount_non_negative'), 'club_fees', type_='check')
    op.drop_constraint(op.f('ck_club_fees_kind'), 'club_fees', type_='check')
    op.create_check_constraint(op.f('ck_club_fees_kind'), 'club_fees', "kind IN ('MONTHLY', 'ENROLLMENT', 'COMPETITION')")
    op.drop_constraint(op.f('fk_club_fees_guardian_user_id_users'), 'club_fees', type_='foreignkey')
    op.drop_index(op.f('ix_club_fees_guardian_user_id'), table_name='club_fees')
    for column in ('discount_note', 'discount_cents', 'gross_amount_cents', 'guardian_user_id'):
        op.drop_column('club_fees', column)
    op.alter_column('club_fees', 'athlete_id', nullable=False)
    op.drop_constraint(op.f('ck_club_athletes_social_tier'), 'club_athletes', type_='check')
    op.drop_column('club_athletes', 'adapted_judo')
    op.drop_column('club_athletes', 'social_tier')
