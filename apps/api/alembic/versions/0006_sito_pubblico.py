"""Il sito pubblico JudoArteVida: la pagina di ogni club e i profili pubblici
dei judoca, con il consenso della famiglia.

Due tabelle nuove, nessuna colonna sulle tabelle esistenti: ciò che il sito
mostra sta separato dai dati del gestionale (docs/club-portal.md, "Sito
pubblico"). Nessun club e nessun atleta diventa pubblico con questa
migrazione: le pagine nascono non pubblicate e il consenso lo dà la famiglia.

Revision ID: 0006
Revises: 0005
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = '0006'
down_revision: str | None = '0005'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('club_sites',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('tagline', sa.String(length=200), nullable=True),
    sa.Column('about', sa.Text(), nullable=True),
    sa.Column('city', sa.String(length=120), nullable=True),
    sa.Column('hero_image_url', sa.String(length=500), nullable=True),
    sa.Column('logo_url', sa.String(length=500), nullable=True),
    sa.Column('gallery', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('coaches', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('contact_phone', sa.String(length=40), nullable=True),
    sa.Column('contact_email', sa.String(length=255), nullable=True),
    sa.Column('address', sa.String(length=300), nullable=True),
    sa.Column('map_url', sa.String(length=500), nullable=True),
    sa.Column('instagram_url', sa.String(length=500), nullable=True),
    sa.Column('facebook_url', sa.String(length=500), nullable=True),
    sa.Column('youtube_url', sa.String(length=500), nullable=True),
    sa.Column('website_url', sa.String(length=500), nullable=True),
    sa.Column('published', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_sites_club_id_clubs')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_sites_organization_id_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_sites')),
    sa.UniqueConstraint('club_id', name=op.f('uq_club_sites_club_id'))
    )
    op.create_index(op.f('ix_club_sites_organization_id'), 'club_sites', ['organization_id'], unique=False)

    op.create_table('club_athlete_public_profiles',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('athlete_id', sa.UUID(), nullable=False),
    sa.Column('consent_given_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('consent_by_user_id', sa.UUID(), nullable=True),
    sa.Column('show_photo', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('bio', sa.String(length=280), nullable=True),
    sa.Column('published', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['athlete_id'], ['club_athletes.id'], name=op.f('fk_club_athlete_public_profiles_athlete_id_club_athletes')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_athlete_public_profiles_club_id_clubs')),
    sa.ForeignKeyConstraint(['consent_by_user_id'], ['users.id'], name=op.f('fk_club_athlete_public_profiles_consent_by_user_id_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_athlete_public_profiles_organization_id_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_athlete_public_profiles')),
    sa.UniqueConstraint('athlete_id', name=op.f('uq_club_athlete_public_profiles_athlete_id'))
    )
    op.create_index(op.f('ix_club_athlete_public_profiles_club_id'), 'club_athlete_public_profiles', ['club_id'], unique=False)
    op.create_index(op.f('ix_club_athlete_public_profiles_organization_id'), 'club_athlete_public_profiles', ['organization_id'], unique=False)


def downgrade() -> None:
    op.drop_table('club_athlete_public_profiles')
    op.drop_table('club_sites')
