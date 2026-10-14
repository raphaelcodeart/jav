"""La scheda pubblica del judoca, in stile IJF: profilo IJF, tecnica
preferita, guardia, e le foto e i video della sua pagina.

Tre colonne su `club_athlete_public_profiles` (la tabella fatta per essere
letta dal sito, separata dai dati del gestionale) e una tabella nuova,
`club_athlete_media`, perché ogni foto e ogni video si pubblica a parte.
Nessun dato nuovo diventa pubblico con questa migrazione: le colonne nascono
vuote e i media non pubblicati. Regole in docs/club-portal.md, "Sito
pubblico" → "La scheda del judoca".

Revision ID: 0010
Revises: 0009
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0010'
down_revision: str | None = '0009'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('club_athlete_public_profiles', sa.Column('ijf_profile_url', sa.String(length=300), nullable=True))
    op.add_column('club_athlete_public_profiles', sa.Column('favorite_technique', sa.String(length=80), nullable=True))
    op.add_column('club_athlete_public_profiles', sa.Column('dominant_side', sa.String(length=5), nullable=True))
    op.create_check_constraint(
        op.f('ck_club_athlete_public_profiles_dominant_side'), 'club_athlete_public_profiles',
        "dominant_side IS NULL OR dominant_side IN ('LEFT', 'RIGHT')",
    )

    op.create_table('club_athlete_media',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('athlete_id', sa.UUID(), nullable=False),
    sa.Column('kind', sa.String(length=8), nullable=False),
    sa.Column('url', sa.String(length=500), nullable=True),
    sa.Column('youtube_id', sa.String(length=11), nullable=True),
    sa.Column('caption', sa.String(length=200), nullable=True),
    sa.Column('published', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('created_by_user_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("kind IN ('PHOTO', 'VIDEO')", name=op.f('ck_club_athlete_media_kind')),
    sa.CheckConstraint(
        "(kind = 'PHOTO' AND url IS NOT NULL AND youtube_id IS NULL)"
        " OR (kind = 'VIDEO' AND youtube_id IS NOT NULL AND url IS NULL)",
        name=op.f('ck_club_athlete_media_kind_payload'),
    ),
    sa.ForeignKeyConstraint(['athlete_id'], ['club_athletes.id'], name=op.f('fk_club_athlete_media_athlete_id_club_athletes')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_athlete_media_club_id_clubs')),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_club_athlete_media_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_athlete_media_organization_id_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_athlete_media')),
    sa.UniqueConstraint('athlete_id', 'youtube_id', name='uq_club_athlete_media_athlete_youtube')
    )
    op.create_index(op.f('ix_club_athlete_media_athlete_id'), 'club_athlete_media', ['athlete_id'], unique=False)
    op.create_index(op.f('ix_club_athlete_media_club_id'), 'club_athlete_media', ['club_id'], unique=False)
    op.create_index(op.f('ix_club_athlete_media_organization_id'), 'club_athlete_media', ['organization_id'], unique=False)


def downgrade() -> None:
    op.drop_table('club_athlete_media')
    op.drop_constraint(
        op.f('ck_club_athlete_public_profiles_dominant_side'), 'club_athlete_public_profiles', type_='check',
    )
    for column in ('dominant_side', 'favorite_technique', 'ijf_profile_url'):
        op.drop_column('club_athlete_public_profiles', column)
