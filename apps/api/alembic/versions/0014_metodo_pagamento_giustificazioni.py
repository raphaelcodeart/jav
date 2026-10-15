"""Come si è pagata una quota, e le giustificazioni per la scuola.

- `club_fees.payment_method` (bonifico, contanti, carta, credito del wallet)
  e, per i contanti, a chi sono stati dati (`cash_received_by_user_id`, e il
  nome congelato `cash_received_by_name`). Le quote già pagate con una prova
  ricevono il metodo della prova; quelle segnate a mano restano senza: non
  si sa com'erano state pagate.
- `club_payment_proofs.method`: una "prova" può essere anche la
  dichiarazione dei contanti consegnati, senza foto, con chi li ha ricevuti.
- `club_school_letters`: la giustificazione per la scuola di un atleta
  iscritto a una gara, testo e PDF (nel bucket privato), una per iscrizione.

Regole in docs/club-portal.md, "Come si paga una mensilità" e "La
giustificazione per la scuola".

Revision ID: 0014
Revises: 0013
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0014'
down_revision: str | None = '0013'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('club_fees', sa.Column('payment_method', sa.String(length=16), nullable=True))
    op.add_column('club_fees', sa.Column('cash_received_by_user_id', sa.UUID(), nullable=True))
    op.add_column('club_fees', sa.Column('cash_received_by_name', sa.String(length=120), nullable=True))
    op.create_foreign_key(
        op.f('fk_club_fees_cash_received_by_user_id_users'), 'club_fees', 'users', ['cash_received_by_user_id'], ['id']
    )
    op.create_check_constraint(
        op.f('ck_club_fees_payment_method'), 'club_fees',
        "payment_method IS NULL OR payment_method IN ('BANK_TRANSFER', 'CASH', 'CARD', 'WALLET')",
    )

    op.add_column('club_payment_proofs', sa.Column(
        'method', sa.String(length=16), server_default='BANK_TRANSFER', nullable=False
    ))
    op.add_column('club_payment_proofs', sa.Column('cash_received_by_user_id', sa.UUID(), nullable=True))
    op.add_column('club_payment_proofs', sa.Column('cash_received_by_name', sa.String(length=120), nullable=True))
    op.create_foreign_key(
        op.f('fk_club_payment_proofs_cash_received_by_user_id_users'), 'club_payment_proofs', 'users',
        ['cash_received_by_user_id'], ['id'],
    )
    op.create_check_constraint(
        op.f('ck_club_payment_proofs_method'), 'club_payment_proofs', "method IN ('BANK_TRANSFER', 'CASH')"
    )
    op.drop_constraint(op.f('ck_club_payment_proofs_file_or_credit'), 'club_payment_proofs', type_='check')
    op.create_check_constraint(
        op.f('ck_club_payment_proofs_file_or_credit'), 'club_payment_proofs',
        "storage_key IS NOT NULL OR credit_cents = amount_cents OR method = 'CASH'",
    )
    op.create_check_constraint(
        op.f('ck_club_payment_proofs_cash_receiver'), 'club_payment_proofs',
        "method <> 'CASH' OR cash_received_by_user_id IS NOT NULL OR cash_received_by_name IS NOT NULL",
    )

    # Le quote pagate con una prova: bonifico, o credito se il credito ha
    # coperto tutto (allora non c'era una ricevuta).
    op.execute(
        "UPDATE club_fees f SET payment_method = CASE WHEN p.storage_key IS NULL THEN 'WALLET' ELSE 'BANK_TRANSFER' END "
        "FROM club_payment_proofs p WHERE f.paid_via_proof_id = p.id AND f.status = 'PAID'"
    )

    op.create_table('club_school_letters',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('entry_id', sa.UUID(), nullable=False),
    sa.Column('competition_id', sa.UUID(), nullable=False),
    sa.Column('athlete_id', sa.UUID(), nullable=False),
    sa.Column('body_text', sa.Text(), nullable=False),
    sa.Column('storage_key', sa.String(length=500), nullable=False),
    sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('generated_by_user_id', sa.UUID(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['athlete_id'], ['club_athletes.id'], name=op.f('fk_club_school_letters_athlete_id_club_athletes')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_school_letters_club_id_clubs')),
    sa.ForeignKeyConstraint(['competition_id'], ['club_competitions.id'], name=op.f('fk_club_school_letters_competition_id_club_competitions')),
    sa.ForeignKeyConstraint(['entry_id'], ['club_competition_entries.id'], name=op.f('fk_club_school_letters_entry_id_club_competition_entries')),
    sa.ForeignKeyConstraint(['generated_by_user_id'], ['users.id'], name=op.f('fk_club_school_letters_generated_by_user_id_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_school_letters_organization_id_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_school_letters')),
    sa.UniqueConstraint('entry_id', name='uq_club_school_letters_entry_id'),
    )
    op.create_index(op.f('ix_club_school_letters_athlete_id'), 'club_school_letters', ['athlete_id'], unique=False)
    op.create_index(op.f('ix_club_school_letters_club_id'), 'club_school_letters', ['club_id'], unique=False)
    op.create_index(op.f('ix_club_school_letters_competition_id'), 'club_school_letters', ['competition_id'], unique=False)
    op.create_index(op.f('ix_club_school_letters_organization_id'), 'club_school_letters', ['organization_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_club_school_letters_organization_id'), table_name='club_school_letters')
    op.drop_index(op.f('ix_club_school_letters_competition_id'), table_name='club_school_letters')
    op.drop_index(op.f('ix_club_school_letters_club_id'), table_name='club_school_letters')
    op.drop_index(op.f('ix_club_school_letters_athlete_id'), table_name='club_school_letters')
    op.drop_table('club_school_letters')

    op.drop_constraint(op.f('ck_club_payment_proofs_cash_receiver'), 'club_payment_proofs', type_='check')
    op.drop_constraint(op.f('ck_club_payment_proofs_file_or_credit'), 'club_payment_proofs', type_='check')
    # Le dichiarazioni di contanti non hanno foto: senza di loro il vincolo
    # di prima non regge.
    op.execute("DELETE FROM club_payment_proof_fees WHERE proof_id IN (SELECT id FROM club_payment_proofs WHERE method = 'CASH')")
    op.execute("UPDATE club_fees SET paid_via_proof_id = NULL WHERE paid_via_proof_id IN (SELECT id FROM club_payment_proofs WHERE method = 'CASH')")
    op.execute("DELETE FROM club_payment_proofs WHERE method = 'CASH'")
    op.create_check_constraint(
        op.f('ck_club_payment_proofs_file_or_credit'), 'club_payment_proofs',
        'storage_key IS NOT NULL OR credit_cents = amount_cents',
    )
    op.drop_constraint(op.f('ck_club_payment_proofs_method'), 'club_payment_proofs', type_='check')
    op.drop_constraint(
        op.f('fk_club_payment_proofs_cash_received_by_user_id_users'), 'club_payment_proofs', type_='foreignkey'
    )
    op.drop_column('club_payment_proofs', 'cash_received_by_name')
    op.drop_column('club_payment_proofs', 'cash_received_by_user_id')
    op.drop_column('club_payment_proofs', 'method')

    op.drop_constraint(op.f('ck_club_fees_payment_method'), 'club_fees', type_='check')
    op.drop_constraint(op.f('fk_club_fees_cash_received_by_user_id_users'), 'club_fees', type_='foreignkey')
    op.drop_column('club_fees', 'cash_received_by_name')
    op.drop_column('club_fees', 'cash_received_by_user_id')
    op.drop_column('club_fees', 'payment_method')
