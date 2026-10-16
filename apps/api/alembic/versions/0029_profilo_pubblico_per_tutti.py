"""Ogni atleta parte con la scheda pubblica (senza foto), con l'opposizione
della famiglia: `club_athlete_public_profiles.basis` e `opted_out_at`
(club/site.py, docs/club-portal.md «Chi compare sul sito»).

I dati: una scheda pubblicata (LEGITIMATE_INTEREST, senza foto) per ogni
atleta che non ne ha una; le schede con il consenso tornano pubblicate; una
riga senza consenso è un consenso ritirato, quindi diventa un'opposizione.

Revision ID: 0029
Revises: 0028
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0029'
down_revision: str | None = '0028'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('club_athlete_public_profiles', sa.Column('basis', sa.String(length=20), server_default=sa.text("'CONSENT'"), nullable=False))
    op.add_column('club_athlete_public_profiles', sa.Column('opted_out_at', sa.DateTime(timezone=True), nullable=True))
    op.execute("""
        UPDATE club_athlete_public_profiles SET opted_out_at = created_at WHERE consent_given_at IS NULL
    """)
    op.execute("""
        UPDATE club_athlete_public_profiles SET published = true WHERE consent_given_at IS NOT NULL
    """)
    op.execute("""
        INSERT INTO club_athlete_public_profiles
            (id, created_at, organization_id, club_id, athlete_id, consent_given_at, basis, show_photo, published)
        SELECT gen_random_uuid(), now(), a.organization_id, a.club_id, a.id, now(), 'LEGITIMATE_INTEREST', false, true
        FROM club_athletes a
        WHERE NOT EXISTS (SELECT 1 FROM club_athlete_public_profiles p WHERE p.athlete_id = a.id)
    """)


def downgrade() -> None:
    op.execute("DELETE FROM club_athlete_public_profiles WHERE basis = 'LEGITIMATE_INTEREST'")
    op.drop_column('club_athlete_public_profiles', 'opted_out_at')
    op.drop_column('club_athlete_public_profiles', 'basis')
