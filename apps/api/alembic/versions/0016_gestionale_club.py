"""Ciò che serve per accogliere il gestionale che i club usano oggi
(docs/legacy-judo-aev.md): la ficha de inscrição, MB Way, le quote a rate,
le esenzioni e lo sconto personale, le multe, il calendario della rete, i
documenti dell'atleta, i consensi RGPD, le richieste di modifica, le
domande d'iscrizione, gli ordini di judogi, le pulizie, i compensi dei
treinadores esterni, i relatori e la corrispondenza dell'importazione.

- `club_athletes`: nº de sócio (unico nel club), nome sul judogi, altezza,
  nazionalità, categoria di peso, anno di rivalidazione della licenza;
  esenzioni (`exempt_monthly`, `exempt_annual`) e sconto personale
  (`custom_discount_*`); escalão D.
- `club_athlete_records`: i dati d'identità (documento, passaporto,
  indirizzo, contatti e documento del responsabile), uno per atleta.
- `club_fees`: tipi FINE ed EQUIPMENT, rate (`installment_no`,
  `installments_total`, periodo "2026/2"), metodo MBWAY.
- `club_payment_proofs`: metodo MBWAY, numero di ricevuta unico nel club
  (`club_receipt_counters`), giorno del pagamento dichiarato.
- `club_competitions`: `club_id` NULL = evento della rete; i livelli
  portoghesi (zonal, opens, Taça da Europa, Europei, Mondiali, Olimpiadi);
  tipi arbitragem, formação, reunião, outro; orari, posti, escalões,
  circolare, trasporto. `club_transport_requests` diventa una per (evento,
  club). `club_competition_entries`: posizione vera e note del risultato.
- `club_belt_grades`: le cinture intermedie portoghesi (bianca con le barre,
  verde-blu, blu-marrone).
- `club_expenses` / `club_recurring_expenses`: categorie collaboratori,
  pulizie, treinadores esterni; metodi MB Way e assegno.
- Tabelle nuove: `club_athlete_documents`, `club_consents`,
  `club_change_requests`, `club_applications`, `club_equipment_orders`,
  `club_cleaning_logs`, `club_external_coach_fees`, `club_reports`,
  `club_receipt_counters`, `legacy_import_map`.

Revision ID: 0016
Revises: 0015
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = '0016'
down_revision: str | None = '0015'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: I vincoli CHECK che cambiano (autogenerate non li vede): tabella, nome,
#: condizione nuova. Scritti per esteso: una migrazione non dipende dal
#: codice di oggi.
CHECKS = [
    ('club_athletes', 'social_tier', "social_tier IS NULL OR social_tier IN ('A', 'B', 'C', 'D')"),
    ('club_athletes', 'custom_discount_kind', "custom_discount_kind IS NULL OR custom_discount_kind IN ('PERCENT', 'FIXED')"),
    ('club_athletes', 'custom_discount_scope', "custom_discount_scope IN ('MONTHLY', 'ANNUAL', 'BOTH')"),
    ('club_athletes', 'custom_discount_value', "custom_discount_kind IS NULL OR (custom_discount_value > 0 AND (custom_discount_kind <> 'PERCENT' OR custom_discount_value <= 100))"),
    ('club_athletes', 'height_range', 'height_cm IS NULL OR (height_cm > 40 AND height_cm < 250)'),
    ('club_fees', 'kind', "kind IN ('MONTHLY', 'ENROLLMENT', 'COMPETITION', 'MEMBERSHIP', 'FINE', 'EQUIPMENT')"),
    ('club_fees', 'payment_method', "payment_method IS NULL OR payment_method IN ('BANK_TRANSFER', 'MBWAY', 'CASH', 'CARD', 'WALLET')"),
    ('club_fees', 'installments', '(installment_no IS NULL AND installments_total IS NULL) OR (installment_no >= 1 AND installments_total >= 2 AND installment_no <= installments_total)'),
    ('club_payment_proofs', 'method', "method IN ('BANK_TRANSFER', 'MBWAY', 'CASH')"),
    ('club_competitions', 'level', "level IN ('CLUB', 'REGIONAL', 'ZONAL', 'OPENS', 'NATIONAL', 'INTERNATIONAL', 'EUROPEAN_CUP', 'EUROPEAN_CHAMPIONSHIP', 'WORLD_CHAMPIONSHIP', 'OLYMPIC_GAMES')"),
    ('club_competitions', 'kind', "kind IN ('COMPETITION', 'STAGE', 'REFEREEING', 'EDUCATION', 'MEETING', 'OTHER')"),
    ('club_competitions', 'transport_mode', "transport_mode IN ('CLUB', 'OWN', 'TBC')"),
    ('club_competitions', 'places_positive', 'places IS NULL OR places > 0'),
    ('club_belt_grades', 'grade', "grade IN ('WHITE', 'WHITE_BARS_3', 'WHITE_BARS_6', 'WHITE_BARS_9', 'WHITE_BARS_12', 'WHITE_YELLOW', 'YELLOW', 'YELLOW_ORANGE', 'ORANGE', 'ORANGE_GREEN', 'GREEN', 'GREEN_BLUE', 'BLUE', 'BLUE_BROWN', 'BROWN', 'BLACK_1', 'BLACK_2', 'BLACK_3', 'BLACK_4', 'BLACK_5', 'BLACK_6', 'BLACK_7', 'BLACK_8', 'BLACK_9', 'BLACK_10')"),
    ('club_expenses', 'category', "category IN ('RENT', 'STAFF', 'FEDERATION', 'INSURANCE', 'EQUIPMENT', 'TRANSPORT', 'EVENTS', 'UTILITIES', 'MARKETING', 'ADMIN', 'COLLABORATORS', 'CLEANING', 'EXTERNAL_COACH', 'OTHER')"),
    ('club_expenses', 'payment_method', "payment_method IN ('BANK_TRANSFER', 'MBWAY', 'CASH', 'CARD', 'DIRECT_DEBIT', 'CHEQUE', 'OTHER')"),
    ('club_recurring_expenses', 'category', "category IN ('RENT', 'STAFF', 'FEDERATION', 'INSURANCE', 'EQUIPMENT', 'TRANSPORT', 'EVENTS', 'UTILITIES', 'MARKETING', 'ADMIN', 'COLLABORATORS', 'CLEANING', 'EXTERNAL_COACH', 'OTHER')"),
    ('club_recurring_expenses', 'payment_method', "payment_method IN ('BANK_TRANSFER', 'MBWAY', 'CASH', 'CARD', 'DIRECT_DEBIT', 'CHEQUE', 'OTHER')"),
]

#: Le condizioni di prima, per il downgrade (solo quelle che esistevano).
OLD_CHECKS = [
    ('club_athletes', 'social_tier', "social_tier IS NULL OR social_tier IN ('A', 'B', 'C')"),
    ('club_fees', 'kind', "kind IN ('MONTHLY', 'ENROLLMENT', 'COMPETITION', 'MEMBERSHIP')"),
    ('club_fees', 'payment_method', "payment_method IS NULL OR payment_method IN ('BANK_TRANSFER', 'CASH', 'CARD', 'WALLET')"),
    ('club_payment_proofs', 'method', "method IN ('BANK_TRANSFER', 'CASH')"),
    ('club_competitions', 'level', "level IN ('CLUB', 'REGIONAL', 'NATIONAL', 'INTERNATIONAL')"),
    ('club_competitions', 'kind', "kind IN ('COMPETITION', 'STAGE')"),
    ('club_belt_grades', 'grade', "grade IN ('WHITE', 'WHITE_YELLOW', 'YELLOW', 'YELLOW_ORANGE', 'ORANGE', 'ORANGE_GREEN', 'GREEN', 'BLUE', 'BROWN', 'BLACK_1', 'BLACK_2', 'BLACK_3', 'BLACK_4', 'BLACK_5', 'BLACK_6', 'BLACK_7', 'BLACK_8', 'BLACK_9', 'BLACK_10')"),
    ('club_expenses', 'category', "category IN ('RENT', 'STAFF', 'FEDERATION', 'INSURANCE', 'EQUIPMENT', 'TRANSPORT', 'EVENTS', 'UTILITIES', 'MARKETING', 'ADMIN', 'OTHER')"),
    ('club_expenses', 'payment_method', "payment_method IN ('BANK_TRANSFER', 'CASH', 'CARD', 'DIRECT_DEBIT', 'OTHER')"),
    ('club_recurring_expenses', 'category', "category IN ('RENT', 'STAFF', 'FEDERATION', 'INSURANCE', 'EQUIPMENT', 'TRANSPORT', 'EVENTS', 'UTILITIES', 'MARKETING', 'ADMIN', 'OTHER')"),
    ('club_recurring_expenses', 'payment_method', "payment_method IN ('BANK_TRANSFER', 'CASH', 'CARD', 'DIRECT_DEBIT', 'OTHER')"),
]


def _replace_checks(checks) -> None:
    for table, name, condition in checks:
        constraint = f"ck_{table}_{name}"
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint}")
        op.create_check_constraint(op.f(constraint), table, condition)


def upgrade() -> None:
    op.create_table('legacy_import_map',
    sa.Column('source', sa.String(length=32), nullable=False),
    sa.Column('source_table', sa.String(length=64), nullable=False),
    sa.Column('source_id', sa.String(length=100), nullable=False),
    sa.Column('target_table', sa.String(length=64), nullable=False),
    sa.Column('target_id', sa.UUID(), nullable=False),
    sa.Column('imported_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_legacy_import_map')),
    sa.UniqueConstraint('source', 'source_table', 'source_id', name='uq_legacy_import_map_source_row')
    )
    op.create_index(op.f('ix_legacy_import_map_target_id'), 'legacy_import_map', ['target_id'], unique=False)
    op.create_table('club_receipt_counters',
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('prefix', sa.String(length=4), nullable=False),
    sa.Column('year', sa.SmallInteger(), nullable=False),
    sa.Column('last_number', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_receipt_counters_club_id_clubs')),
    sa.PrimaryKeyConstraint('club_id', 'prefix', 'year', name=op.f('pk_club_receipt_counters'))
    )
    op.create_table('club_reports',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('period_start', sa.Date(), nullable=False),
    sa.Column('period_end', sa.Date(), nullable=False),
    sa.Column('storage_key', sa.String(length=500), nullable=False),
    sa.Column('download_name', sa.String(length=200), nullable=False),
    sa.Column('params', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('created_by_user_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("kind IN ('ACTIVITIES')", name=op.f('ck_club_reports_kind')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_reports_club_id_clubs')),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_club_reports_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_reports_organization_id_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_reports'))
    )
    op.create_index(op.f('ix_club_reports_club_id'), 'club_reports', ['club_id'], unique=False)
    op.create_table('club_applications',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('full_name', sa.String(length=200), nullable=False),
    sa.Column('birth_date', sa.Date(), nullable=True),
    sa.Column('email', sa.String(length=200), nullable=True),
    sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('status', sa.String(length=12), server_default='PENDING', nullable=False),
    sa.Column('internal_notes', sa.Text(), nullable=True),
    sa.Column('athlete_id', sa.UUID(), nullable=True),
    sa.Column('referred_by', sa.String(length=200), nullable=True),
    sa.Column('first_time', sa.Boolean(), nullable=True),
    sa.Column('joined_year', sa.SmallInteger(), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('decided_by_user_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("status IN ('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED')", name=op.f('ck_club_applications_status')),
    sa.ForeignKeyConstraint(['athlete_id'], ['club_athletes.id'], name=op.f('fk_club_applications_athlete_id_club_athletes')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_applications_club_id_clubs')),
    sa.ForeignKeyConstraint(['decided_by_user_id'], ['users.id'], name=op.f('fk_club_applications_decided_by_user_id_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_applications_organization_id_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_applications'))
    )
    op.create_index(op.f('ix_club_applications_club_id'), 'club_applications', ['club_id'], unique=False)
    op.create_index(op.f('ix_club_applications_status'), 'club_applications', ['status'], unique=False)
    op.create_table('club_athlete_documents',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('athlete_id', sa.UUID(), nullable=False),
    sa.Column('kind', sa.String(length=24), nullable=False),
    sa.Column('description', sa.String(length=250), nullable=True),
    sa.Column('storage_key', sa.String(length=500), nullable=False),
    sa.Column('original_filename', sa.String(length=255), nullable=False),
    sa.Column('content_type', sa.String(length=100), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('uploaded_by_user_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("kind IN ('SOCIAL_SECURITY', 'MEDICAL_JUSTIFICATION', 'SCHOOL_JUSTIFICATION', 'CLUB_DECLARATION', 'PARENTAL_AUTHORIZATION', 'ID_DOCUMENT', 'OTHER')", name=op.f('ck_club_athlete_documents_kind')),
    sa.ForeignKeyConstraint(['athlete_id'], ['club_athletes.id'], name=op.f('fk_club_athlete_documents_athlete_id_club_athletes')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_athlete_documents_club_id_clubs')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_athlete_documents_organization_id_organizations')),
    sa.ForeignKeyConstraint(['uploaded_by_user_id'], ['users.id'], name=op.f('fk_club_athlete_documents_uploaded_by_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_athlete_documents'))
    )
    op.create_index(op.f('ix_club_athlete_documents_athlete_id'), 'club_athlete_documents', ['athlete_id'], unique=False)
    op.create_index(op.f('ix_club_athlete_documents_club_id'), 'club_athlete_documents', ['club_id'], unique=False)
    op.create_table('club_athlete_records',
    sa.Column('athlete_id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('address', sa.String(length=250), nullable=True),
    sa.Column('postal_code', sa.String(length=20), nullable=True),
    sa.Column('city', sa.String(length=100), nullable=True),
    sa.Column('phone', sa.String(length=30), nullable=True),
    sa.Column('mobile', sa.String(length=30), nullable=True),
    sa.Column('email', sa.String(length=150), nullable=True),
    sa.Column('marital_status', sa.String(length=30), nullable=True),
    sa.Column('id_document_type', sa.String(length=20), nullable=True),
    sa.Column('id_document_number', sa.String(length=50), nullable=True),
    sa.Column('id_document_check_digits', sa.String(length=20), nullable=True),
    sa.Column('id_document_expires_on', sa.Date(), nullable=True),
    sa.Column('passport_number', sa.String(length=50), nullable=True),
    sa.Column('passport_country', sa.String(length=60), nullable=True),
    sa.Column('passport_expires_on', sa.Date(), nullable=True),
    sa.Column('guardian_name', sa.String(length=200), nullable=True),
    sa.Column('guardian_phone', sa.String(length=30), nullable=True),
    sa.Column('father_phone', sa.String(length=30), nullable=True),
    sa.Column('mother_phone', sa.String(length=30), nullable=True),
    sa.Column('guardian_fiscal_code', sa.String(length=20), nullable=True),
    sa.Column('guardian_id_document_type', sa.String(length=20), nullable=True),
    sa.Column('guardian_id_document_number', sa.String(length=50), nullable=True),
    sa.Column('guardian_id_document_check_digits', sa.String(length=20), nullable=True),
    sa.Column('guardian_id_document_expires_on', sa.Date(), nullable=True),
    sa.Column('guardian_passport_number', sa.String(length=50), nullable=True),
    sa.Column('guardian_passport_country', sa.String(length=60), nullable=True),
    sa.Column('guardian_passport_expires_on', sa.Date(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_by_user_id', sa.UUID(), nullable=True),
    sa.CheckConstraint("guardian_id_document_type IS NULL OR guardian_id_document_type IN ('CITIZEN_CARD', 'PASSPORT', 'RESIDENCE_PERMIT', 'BIRTH_CERTIFICATE', 'OTHER')", name=op.f('ck_club_athlete_records_guardian_id_document_type')),
    sa.CheckConstraint("id_document_type IS NULL OR id_document_type IN ('CITIZEN_CARD', 'PASSPORT', 'RESIDENCE_PERMIT', 'BIRTH_CERTIFICATE', 'OTHER')", name=op.f('ck_club_athlete_records_id_document_type')),
    sa.ForeignKeyConstraint(['athlete_id'], ['club_athletes.id'], name=op.f('fk_club_athlete_records_athlete_id_club_athletes'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_athlete_records_club_id_clubs')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_athlete_records_organization_id_organizations')),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], name=op.f('fk_club_athlete_records_updated_by_user_id_users')),
    sa.PrimaryKeyConstraint('athlete_id', name=op.f('pk_club_athlete_records'))
    )
    op.create_index(op.f('ix_club_athlete_records_club_id'), 'club_athlete_records', ['club_id'], unique=False)
    op.create_table('club_change_requests',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('athlete_id', sa.UUID(), nullable=False),
    sa.Column('requested_by_user_id', sa.UUID(), nullable=True),
    sa.Column('field', sa.String(length=20), nullable=False),
    sa.Column('current_value', sa.String(length=200), nullable=True),
    sa.Column('requested_value', sa.String(length=200), nullable=False),
    sa.Column('note', sa.String(length=500), nullable=True),
    sa.Column('status', sa.String(length=12), server_default='PENDING', nullable=False),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resolved_by_user_id', sa.UUID(), nullable=True),
    sa.Column('resolution_note', sa.String(length=500), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("field IN ('BELT', 'WEIGHT_CATEGORY', 'WEIGHT')", name=op.f('ck_club_change_requests_field')),
    sa.CheckConstraint("status IN ('PENDING', 'APPROVED', 'REJECTED')", name=op.f('ck_club_change_requests_status')),
    sa.ForeignKeyConstraint(['athlete_id'], ['club_athletes.id'], name=op.f('fk_club_change_requests_athlete_id_club_athletes')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_change_requests_club_id_clubs')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_change_requests_organization_id_organizations')),
    sa.ForeignKeyConstraint(['requested_by_user_id'], ['users.id'], name=op.f('fk_club_change_requests_requested_by_user_id_users')),
    sa.ForeignKeyConstraint(['resolved_by_user_id'], ['users.id'], name=op.f('fk_club_change_requests_resolved_by_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_change_requests'))
    )
    op.create_index(op.f('ix_club_change_requests_athlete_id'), 'club_change_requests', ['athlete_id'], unique=False)
    op.create_index(op.f('ix_club_change_requests_club_id'), 'club_change_requests', ['club_id'], unique=False)
    op.create_index(op.f('ix_club_change_requests_status'), 'club_change_requests', ['status'], unique=False)
    op.create_table('club_consents',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('athlete_id', sa.UUID(), nullable=True),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('granted', sa.Boolean(), nullable=False),
    sa.Column('policy_version', sa.String(length=20), nullable=False),
    sa.Column('source', sa.String(length=12), nullable=False),
    sa.Column('recorded_by_user_id', sa.UUID(), nullable=True),
    sa.Column('ip_hash', sa.String(length=64), nullable=True),
    sa.Column('given_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("(kind = 'PRIVACY_POLICY' AND user_id IS NOT NULL) OR (kind <> 'PRIVACY_POLICY' AND athlete_id IS NOT NULL)", name=op.f('ck_club_consents_subject')),
    sa.CheckConstraint("kind IN ('PRIVACY_POLICY', 'PHOTOS', 'MARKETING')", name=op.f('ck_club_consents_kind')),
    sa.CheckConstraint("source IN ('PORTAL', 'BACKOFFICE', 'LEGACY')", name=op.f('ck_club_consents_source')),
    sa.ForeignKeyConstraint(['athlete_id'], ['club_athletes.id'], name=op.f('fk_club_consents_athlete_id_club_athletes')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_consents_club_id_clubs')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_consents_organization_id_organizations')),
    sa.ForeignKeyConstraint(['recorded_by_user_id'], ['users.id'], name=op.f('fk_club_consents_recorded_by_user_id_users')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_club_consents_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_consents'))
    )
    op.create_index(op.f('ix_club_consents_athlete_id'), 'club_consents', ['athlete_id'], unique=False)
    op.create_index(op.f('ix_club_consents_club_id'), 'club_consents', ['club_id'], unique=False)
    op.create_index('ix_club_consents_subject', 'club_consents', ['kind', 'user_id', 'athlete_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_club_consents_user_id'), 'club_consents', ['user_id'], unique=False)
    op.create_table('club_cleaning_logs',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('performed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('person_name', sa.String(length=150), nullable=False),
    sa.Column('hours', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('hourly_rate_cents', sa.BigInteger(), nullable=False),
    sa.Column('total_cents', sa.BigInteger(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('signature_storage_key', sa.String(length=500), nullable=True),
    sa.Column('paid_on', sa.Date(), nullable=True),
    sa.Column('expense_id', sa.UUID(), nullable=True),
    sa.Column('created_by_user_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('hourly_rate_cents > 0', name=op.f('ck_club_cleaning_logs_rate_positive')),
    sa.CheckConstraint('hours > 0', name=op.f('ck_club_cleaning_logs_hours_positive')),
    sa.CheckConstraint('total_cents >= 0', name=op.f('ck_club_cleaning_logs_total_non_negative')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_cleaning_logs_club_id_clubs')),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_club_cleaning_logs_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['expense_id'], ['club_expenses.id'], name=op.f('fk_club_cleaning_logs_expense_id_club_expenses')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_cleaning_logs_organization_id_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_cleaning_logs')),
    sa.UniqueConstraint('expense_id', name=op.f('uq_club_cleaning_logs_expense_id'))
    )
    op.create_index(op.f('ix_club_cleaning_logs_club_id'), 'club_cleaning_logs', ['club_id'], unique=False)
    op.create_index(op.f('ix_club_cleaning_logs_performed_at'), 'club_cleaning_logs', ['performed_at'], unique=False)
    op.create_table('club_equipment_orders',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('athlete_id', sa.UUID(), nullable=False),
    sa.Column('requested_by_user_id', sa.UUID(), nullable=True),
    sa.Column('kimono_name', sa.String(length=100), nullable=False),
    sa.Column('kimono_type', sa.String(length=24), nullable=False),
    sa.Column('color', sa.String(length=40), nullable=False),
    sa.Column('brand', sa.String(length=60), nullable=False),
    sa.Column('size_cm', sa.SmallInteger(), nullable=False),
    sa.Column('price_cents', sa.BigInteger(), nullable=True),
    sa.Column('trade_in', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('internal_notes', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=16), server_default='PENDING', nullable=False),
    sa.Column('fee_id', sa.UUID(), nullable=True),
    sa.Column('delivered_on', sa.Date(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("kimono_type IN ('FIJ_APPROVED', 'TRAINING', 'SEMI_COMPETITION', 'COMPETITION_NOT_APPROVED')", name=op.f('ck_club_equipment_orders_kimono_type')),
    sa.CheckConstraint("status IN ('PENDING', 'IN_PREPARATION', 'DELIVERED', 'CANCELLED')", name=op.f('ck_club_equipment_orders_status')),
    sa.CheckConstraint('price_cents IS NULL OR price_cents >= 0', name=op.f('ck_club_equipment_orders_price_non_negative')),
    sa.CheckConstraint('size_cm BETWEEN 80 AND 220', name=op.f('ck_club_equipment_orders_size_range')),
    sa.ForeignKeyConstraint(['athlete_id'], ['club_athletes.id'], name=op.f('fk_club_equipment_orders_athlete_id_club_athletes')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_equipment_orders_club_id_clubs')),
    sa.ForeignKeyConstraint(['fee_id'], ['club_fees.id'], name=op.f('fk_club_equipment_orders_fee_id_club_fees')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_equipment_orders_organization_id_organizations')),
    sa.ForeignKeyConstraint(['requested_by_user_id'], ['users.id'], name=op.f('fk_club_equipment_orders_requested_by_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_equipment_orders')),
    sa.UniqueConstraint('fee_id', name=op.f('uq_club_equipment_orders_fee_id'))
    )
    op.create_index(op.f('ix_club_equipment_orders_athlete_id'), 'club_equipment_orders', ['athlete_id'], unique=False)
    op.create_index(op.f('ix_club_equipment_orders_club_id'), 'club_equipment_orders', ['club_id'], unique=False)
    op.create_index(op.f('ix_club_equipment_orders_status'), 'club_equipment_orders', ['status'], unique=False)
    op.create_table('club_external_coach_fees',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('coach_name', sa.String(length=150), nullable=False),
    sa.Column('month', sa.Date(), nullable=False),
    sa.Column('weekday_hours', sa.Numeric(precision=6, scale=2), nullable=False),
    sa.Column('weekday_rate_cents', sa.BigInteger(), nullable=False),
    sa.Column('weekend_hours', sa.Numeric(precision=6, scale=2), nullable=False),
    sa.Column('weekend_rate_cents', sa.BigInteger(), nullable=False),
    sa.Column('students', sa.Integer(), nullable=False),
    sa.Column('per_student_cents', sa.BigInteger(), nullable=False),
    sa.Column('total_cents', sa.BigInteger(), nullable=False),
    sa.Column('status', sa.String(length=10), server_default='PENDING', nullable=False),
    sa.Column('paid_cents', sa.BigInteger(), nullable=True),
    sa.Column('paid_on', sa.Date(), nullable=True),
    sa.Column('payment_method', sa.String(length=16), nullable=True),
    sa.Column('reference', sa.String(length=100), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('expense_id', sa.UUID(), nullable=True),
    sa.Column('created_by_user_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("status IN ('PENDING', 'PAID', 'PARTIAL', 'EXEMPT')", name=op.f('ck_club_external_coach_fees_status')),
    sa.CheckConstraint('paid_cents IS NULL OR paid_cents >= 0', name=op.f('ck_club_external_coach_fees_paid_non_negative')),
    sa.CheckConstraint('total_cents >= 0', name=op.f('ck_club_external_coach_fees_total_non_negative')),
    sa.CheckConstraint('weekday_hours >= 0 AND weekend_hours >= 0 AND students >= 0', name=op.f('ck_club_external_coach_fees_quantities_non_negative')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_external_coach_fees_club_id_clubs')),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_club_external_coach_fees_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['expense_id'], ['club_expenses.id'], name=op.f('fk_club_external_coach_fees_expense_id_club_expenses')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_external_coach_fees_organization_id_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_external_coach_fees')),
    sa.UniqueConstraint('expense_id', name=op.f('uq_club_external_coach_fees_expense_id'))
    )
    op.create_index(op.f('ix_club_external_coach_fees_club_id'), 'club_external_coach_fees', ['club_id'], unique=False)
    op.create_index(op.f('ix_club_external_coach_fees_month'), 'club_external_coach_fees', ['month'], unique=False)
    op.add_column('club_athletes', sa.Column('member_number', sa.String(length=20), nullable=True))
    op.add_column('club_athletes', sa.Column('kimono_name', sa.String(length=100), nullable=True))
    op.add_column('club_athletes', sa.Column('height_cm', sa.SmallInteger(), nullable=True))
    op.add_column('club_athletes', sa.Column('nationality', sa.String(length=80), nullable=True))
    op.add_column('club_athletes', sa.Column('weight_category', sa.String(length=30), nullable=True))
    op.add_column('club_athletes', sa.Column('federation_renewal_year', sa.SmallInteger(), nullable=True))
    op.add_column('club_athletes', sa.Column('exempt_monthly', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('club_athletes', sa.Column('exempt_annual', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('club_athletes', sa.Column('custom_discount_kind', sa.String(length=8), nullable=True))
    op.add_column('club_athletes', sa.Column('custom_discount_value', sa.Integer(), nullable=True))
    op.add_column('club_athletes', sa.Column('custom_discount_scope', sa.String(length=8), server_default='MONTHLY', nullable=False))
    op.add_column('club_athletes', sa.Column('custom_discount_note', sa.String(length=200), nullable=True))
    op.create_index('uq_club_athletes_club_member_number', 'club_athletes', ['club_id', 'member_number'], unique=True, postgresql_where=sa.text('member_number IS NOT NULL'))
    op.add_column('club_competition_entries', sa.Column('rank', sa.SmallInteger(), nullable=True))
    op.add_column('club_competition_entries', sa.Column('result_notes', sa.String(length=500), nullable=True))
    op.add_column('club_competitions', sa.Column('transport_mode', sa.String(length=8), server_default='TBC', nullable=False))
    op.add_column('club_competitions', sa.Column('transport_info', sa.String(length=300), nullable=True))
    op.add_column('club_competitions', sa.Column('starts_at_time', sa.Time(), nullable=True))
    op.add_column('club_competitions', sa.Column('ends_at_time', sa.Time(), nullable=True))
    op.add_column('club_competitions', sa.Column('registration_deadline_time', sa.Time(), nullable=True))
    op.add_column('club_competitions', sa.Column('places', sa.Integer(), nullable=True))
    op.add_column('club_competitions', sa.Column('age_groups', postgresql.ARRAY(sa.String(length=20)), server_default=sa.text("'{}'::varchar[]"), nullable=False))
    op.add_column('club_competitions', sa.Column('circular_url', sa.String(length=500), nullable=True))
    op.add_column('club_competitions', sa.Column('circular_filename', sa.String(length=255), nullable=True))
    op.alter_column('club_competitions', 'club_id',
               existing_type=sa.UUID(),
               nullable=True)
    op.alter_column('club_competitions', 'level', existing_type=sa.VARCHAR(length=16),
                    type_=sa.String(length=24), existing_nullable=False)
    op.add_column('club_fees', sa.Column('installment_no', sa.SmallInteger(), nullable=True))
    op.add_column('club_fees', sa.Column('installments_total', sa.SmallInteger(), nullable=True))
    op.alter_column('club_fees', 'period',
               existing_type=sa.VARCHAR(length=36),
               type_=sa.String(length=40),
               existing_nullable=False)
    op.add_column('club_payment_proofs', sa.Column('receipt_number', sa.String(length=24), nullable=True))
    op.add_column('club_payment_proofs', sa.Column('paid_on', sa.Date(), nullable=True))
    op.create_index('uq_club_payment_proofs_club_receipt', 'club_payment_proofs', ['club_id', 'receipt_number'], unique=True, postgresql_where=sa.text('receipt_number IS NOT NULL'))
    op.drop_constraint(op.f('uq_club_transport_requests_competition_id'), 'club_transport_requests', type_='unique')
    op.create_unique_constraint('uq_club_transport_requests_competition_club', 'club_transport_requests', ['competition_id', 'club_id'])
    _replace_checks(CHECKS)


def downgrade() -> None:
    old = {(t, n) for t, n, _c in OLD_CHECKS}
    for table, name, _condition in CHECKS:
        if (table, name) not in old:
            op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS ck_{table}_{name}")
    _replace_checks(OLD_CHECKS)
    op.drop_constraint('uq_club_transport_requests_competition_club', 'club_transport_requests', type_='unique')
    op.create_unique_constraint(op.f('uq_club_transport_requests_competition_id'), 'club_transport_requests', ['competition_id'], postgresql_nulls_not_distinct=False)
    op.drop_index('uq_club_payment_proofs_club_receipt', table_name='club_payment_proofs', postgresql_where=sa.text('receipt_number IS NOT NULL'))
    op.drop_column('club_payment_proofs', 'paid_on')
    op.drop_column('club_payment_proofs', 'receipt_number')
    op.alter_column('club_fees', 'period',
               existing_type=sa.String(length=40),
               type_=sa.VARCHAR(length=36),
               existing_nullable=False)
    op.drop_column('club_fees', 'installments_total')
    op.drop_column('club_fees', 'installment_no')
    op.alter_column('club_competitions', 'level', existing_type=sa.String(length=24),
                    type_=sa.VARCHAR(length=16), existing_nullable=False)
    op.alter_column('club_competitions', 'club_id',
               existing_type=sa.UUID(),
               nullable=False)
    op.drop_column('club_competitions', 'circular_filename')
    op.drop_column('club_competitions', 'circular_url')
    op.drop_column('club_competitions', 'age_groups')
    op.drop_column('club_competitions', 'places')
    op.drop_column('club_competitions', 'registration_deadline_time')
    op.drop_column('club_competitions', 'ends_at_time')
    op.drop_column('club_competitions', 'starts_at_time')
    op.drop_column('club_competitions', 'transport_info')
    op.drop_column('club_competitions', 'transport_mode')
    op.drop_column('club_competition_entries', 'result_notes')
    op.drop_column('club_competition_entries', 'rank')
    op.drop_index('uq_club_athletes_club_member_number', table_name='club_athletes', postgresql_where=sa.text('member_number IS NOT NULL'))
    op.drop_column('club_athletes', 'custom_discount_note')
    op.drop_column('club_athletes', 'custom_discount_scope')
    op.drop_column('club_athletes', 'custom_discount_value')
    op.drop_column('club_athletes', 'custom_discount_kind')
    op.drop_column('club_athletes', 'exempt_annual')
    op.drop_column('club_athletes', 'exempt_monthly')
    op.drop_column('club_athletes', 'federation_renewal_year')
    op.drop_column('club_athletes', 'weight_category')
    op.drop_column('club_athletes', 'nationality')
    op.drop_column('club_athletes', 'height_cm')
    op.drop_column('club_athletes', 'kimono_name')
    op.drop_column('club_athletes', 'member_number')
    op.drop_index(op.f('ix_club_external_coach_fees_month'), table_name='club_external_coach_fees')
    op.drop_index(op.f('ix_club_external_coach_fees_club_id'), table_name='club_external_coach_fees')
    op.drop_table('club_external_coach_fees')
    op.drop_index(op.f('ix_club_equipment_orders_status'), table_name='club_equipment_orders')
    op.drop_index(op.f('ix_club_equipment_orders_club_id'), table_name='club_equipment_orders')
    op.drop_index(op.f('ix_club_equipment_orders_athlete_id'), table_name='club_equipment_orders')
    op.drop_table('club_equipment_orders')
    op.drop_index(op.f('ix_club_cleaning_logs_performed_at'), table_name='club_cleaning_logs')
    op.drop_index(op.f('ix_club_cleaning_logs_club_id'), table_name='club_cleaning_logs')
    op.drop_table('club_cleaning_logs')
    op.drop_index(op.f('ix_club_consents_user_id'), table_name='club_consents')
    op.drop_index('ix_club_consents_subject', table_name='club_consents')
    op.drop_index(op.f('ix_club_consents_club_id'), table_name='club_consents')
    op.drop_index(op.f('ix_club_consents_athlete_id'), table_name='club_consents')
    op.drop_table('club_consents')
    op.drop_index(op.f('ix_club_change_requests_status'), table_name='club_change_requests')
    op.drop_index(op.f('ix_club_change_requests_club_id'), table_name='club_change_requests')
    op.drop_index(op.f('ix_club_change_requests_athlete_id'), table_name='club_change_requests')
    op.drop_table('club_change_requests')
    op.drop_index(op.f('ix_club_athlete_records_club_id'), table_name='club_athlete_records')
    op.drop_table('club_athlete_records')
    op.drop_index(op.f('ix_club_athlete_documents_club_id'), table_name='club_athlete_documents')
    op.drop_index(op.f('ix_club_athlete_documents_athlete_id'), table_name='club_athlete_documents')
    op.drop_table('club_athlete_documents')
    op.drop_index(op.f('ix_club_applications_status'), table_name='club_applications')
    op.drop_index(op.f('ix_club_applications_club_id'), table_name='club_applications')
    op.drop_table('club_applications')
    op.drop_index(op.f('ix_club_reports_club_id'), table_name='club_reports')
    op.drop_table('club_reports')
    op.drop_table('club_receipt_counters')
    op.drop_index(op.f('ix_legacy_import_map_target_id'), table_name='legacy_import_map')
    op.drop_table('legacy_import_map')
