"""La pagina del club diventa un mini-sito: anno di fondazione, sede, i
numeri che il club dice di sé, la storia, i pilastri (perché allenarsi qui), le novità e i video.

Due colonne semplici (`founded_year`, con un CHECK dal 1882, l'anno del
Kodokan, e `venue`) e cinque liste JSONB che nascono vuote (`highlights`,
`history`, `pillars`, `news`, `videos`). Nessun dato esistente cambia. Regole
in docs/club-portal.md, "Sito pubblico" → "La pagina del club".

Revision ID: 0012
Revises: 0011
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = '0012'
down_revision: str | None = '0011'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LIST_COLUMNS = ('highlights', 'history', 'pillars', 'news', 'videos')


def upgrade() -> None:
    op.add_column('club_sites', sa.Column('founded_year', sa.SmallInteger(), nullable=True))
    op.create_check_constraint(
        op.f('ck_club_sites_founded_year'), 'club_sites', 'founded_year IS NULL OR founded_year BETWEEN 1882 AND 2100',
    )
    op.add_column('club_sites', sa.Column('venue', sa.String(length=160), nullable=True))
    for column in LIST_COLUMNS:
        op.add_column('club_sites', sa.Column(
            column, postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False,
        ))


def downgrade() -> None:
    for column in reversed(LIST_COLUMNS):
        op.drop_column('club_sites', column)
    op.drop_column('club_sites', 'venue')
    op.drop_constraint(op.f('ck_club_sites_founded_year'), 'club_sites', type_='check')
    op.drop_column('club_sites', 'founded_year')
