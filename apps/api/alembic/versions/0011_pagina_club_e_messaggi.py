"""La pagina del club come una pagina tutta sua (i suoi colori) e i messaggi
dal sito pubblico.

Tre colonne su `club_sites` (`brand_primary`, `brand_secondary`,
`brand_accent`: "#RRGGBB" o vuote, un vincolo per colonna così nel CSS della
pagina non finisce altro che un colore) e una tabella nuova,
`contact_messages`: i messaggi scritti a un club dalla sua pagina o a
JudoArteVida da /contactos (club_id NULL). Nessun dato esistente cambia: i
colori nascono vuoti (= quelli di JudoArteVida). Regole in
docs/club-portal.md, "Sito pubblico" → "La pagina del club" e "Messaggi dal
sito".

Revision ID: 0011
Revises: 0010
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0011'
down_revision: str | None = '0010'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BRAND_COLUMNS = ('brand_primary', 'brand_secondary', 'brand_accent')


def upgrade() -> None:
    for column in BRAND_COLUMNS:
        op.add_column('club_sites', sa.Column(column, sa.String(length=7), nullable=True))
        op.create_check_constraint(
            op.f(f'ck_club_sites_{column}'), 'club_sites', f"{column} IS NULL OR {column} ~ '^#[0-9A-F]{{6}}$'",
        )

    op.create_table('contact_messages',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=True),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('phone', sa.String(length=40), nullable=True),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('locale', sa.String(length=5), server_default=sa.text("'pt'"), nullable=False),
    sa.Column('status', sa.String(length=10), server_default=sa.text("'NEW'"), nullable=False),
    sa.Column('consent_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ip_hash', sa.String(length=64), nullable=True),
    sa.Column('user_agent', sa.String(length=200), nullable=True),
    sa.Column('emailed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("status IN ('NEW', 'READ', 'ARCHIVED')", name=op.f('ck_contact_messages_status')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_contact_messages_club_id_clubs')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_contact_messages_organization_id_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_contact_messages'))
    )
    op.create_index(op.f('ix_contact_messages_club_id'), 'contact_messages', ['club_id'], unique=False)
    op.create_index(op.f('ix_contact_messages_organization_id'), 'contact_messages', ['organization_id'], unique=False)
    op.create_index(op.f('ix_contact_messages_status'), 'contact_messages', ['status'], unique=False)
    op.create_index('ix_contact_messages_ip_hash_created_at', 'contact_messages', ['ip_hash', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_table('contact_messages')
    for column in reversed(BRAND_COLUMNS):
        op.drop_constraint(op.f(f'ck_club_sites_{column}'), 'club_sites', type_='check')
        op.drop_column('club_sites', column)
