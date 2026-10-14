"""Più club sulla stessa piattaforma.

La tabella `clubs`, e `club_id` su ogni tabella del dominio club e sugli
utenti (genitori, segreteria, istruttori di un club; NULL per lo staff della
piattaforma). Specifica: docs/club-portal.md, "Più club".

I dati che esistono già non restano senza club: per ogni organizzazione che
ne ha, si crea un club con il nome dell'organizzazione e ci si spostano
dentro atleti, quote, corsi, gare e gli account di genitori e istruttori.
Poi `club_id` diventa NOT NULL sulle tabelle del club.

Revision ID: 0002
Revises: 0001
"""
import re
import unicodedata
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Le tabelle del club che hanno `organization_id` e ora anche `club_id`.
CLUB_TABLES = (
    'club_plans',
    'club_athletes',
    'club_payment_proofs',
    'club_competitions',
    'club_fees',
    'club_medical_certificates',
    'club_belt_grades',
    'club_courses',
    'club_attendances',
    'club_competition_entries',
)


def _slugify(name: str) -> str:
    ascii_name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
    slug = re.sub(r'[^a-z0-9]+', '-', ascii_name.lower()).strip('-')[:80].strip('-')
    return slug if len(slug) >= 3 else 'club'


def upgrade() -> None:
    op.create_table('clubs',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('slug', sa.String(length=80), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('settings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name=op.f('ck_clubs_slug_format')),
    sa.CheckConstraint("status IN ('ACTIVE', 'SUSPENDED')", name=op.f('ck_clubs_status')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_clubs_organization_id_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_clubs')),
    sa.UniqueConstraint('organization_id', 'slug', name='uq_clubs_org_slug')
    )
    op.create_index(op.f('ix_clubs_organization_id'), 'clubs', ['organization_id'], unique=False)

    op.add_column('users', sa.Column('club_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_users_club_id'), 'users', ['club_id'], unique=False)
    op.create_foreign_key(op.f('fk_users_club_id_clubs'), 'users', 'clubs', ['club_id'], ['id'])
    for table in CLUB_TABLES:
        op.add_column(table, sa.Column('club_id', sa.UUID(), nullable=True))

    # I dati che ci sono già: un club per organizzazione che ne ha.
    bind = op.get_bind()
    used = " UNION ".join(f"SELECT organization_id FROM {t}" for t in CLUB_TABLES)
    orgs = bind.execute(sa.text(
        f"SELECT id, name FROM organizations WHERE id IN ({used}) "
        "OR id IN (SELECT ur.organization_id FROM user_roles ur JOIN roles r ON r.id = ur.role_id "
        "WHERE r.code IN ('CUSTOMER', 'INSTRUCTOR'))"
    )).all()
    for org_id, org_name in orgs:
        club_id = uuid.uuid4()
        bind.execute(
            sa.text(
                "INSERT INTO clubs (id, created_at, organization_id, name, slug, status, settings) "
                "VALUES (:id, now(), :org, :name, :slug, 'ACTIVE', '{}'::jsonb)"
            ),
            {"id": club_id, "org": org_id, "name": org_name, "slug": _slugify(org_name)},
        )
        for table in CLUB_TABLES:
            bind.execute(sa.text(f"UPDATE {table} SET club_id = :club WHERE organization_id = :org"),
                         {"club": club_id, "org": org_id})
        # Genitori e istruttori diventano del club; lo staff della
        # piattaforma (superadmin, admin) resta senza club.
        bind.execute(
            sa.text(
                "UPDATE users SET club_id = :club WHERE organization_id = :org AND id IN ("
                "SELECT ur.user_id FROM user_roles ur JOIN roles r ON r.id = ur.role_id "
                "WHERE r.code IN ('CUSTOMER', 'INSTRUCTOR'))"
            ),
            {"club": club_id, "org": org_id},
        )

    for table in CLUB_TABLES:
        op.alter_column(table, 'club_id', nullable=False)
        op.create_index(op.f(f'ix_{table}_club_id'), table, ['club_id'], unique=False)
        op.create_foreign_key(op.f(f'fk_{table}_club_id_clubs'), table, 'clubs', ['club_id'], ['id'])


def downgrade() -> None:
    for table in CLUB_TABLES:
        op.drop_constraint(op.f(f'fk_{table}_club_id_clubs'), table, type_='foreignkey')
        op.drop_index(op.f(f'ix_{table}_club_id'), table_name=table)
        op.drop_column(table, 'club_id')
    op.drop_constraint(op.f('fk_users_club_id_clubs'), 'users', type_='foreignkey')
    op.drop_index(op.f('ix_users_club_id'), table_name='users')
    op.drop_column('users', 'club_id')
    op.drop_index(op.f('ix_clubs_organization_id'), table_name='clubs')
    op.drop_table('clubs')
