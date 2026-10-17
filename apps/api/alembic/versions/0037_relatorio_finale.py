"""Il relatório final di una prova: il breve articolo «di giornale» che
racconta com'è andata (risultati, spese, foto), scritto da un modello o
dall'IA e poi ritoccato a mano: `club_event_reports.article_*`.

Revision ID: 0037
Revises: 0036
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0037'
down_revision: str | None = '0036'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('club_event_reports', sa.Column('article_title', sa.String(length=200), nullable=True))
    op.add_column('club_event_reports', sa.Column('article', sa.Text(), nullable=True))
    op.add_column('club_event_reports', sa.Column('article_source', sa.String(length=8), nullable=True))
    op.add_column('club_event_reports', sa.Column('article_generated_at', sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        'ck_club_event_reports_article_source', 'club_event_reports',
        "article_source IS NULL OR article_source IN ('TEMPLATE', 'AI', 'MANUAL')",
    )


def downgrade() -> None:
    op.drop_constraint('ck_club_event_reports_article_source', 'club_event_reports', type_='check')
    op.drop_column('club_event_reports', 'article_generated_at')
    op.drop_column('club_event_reports', 'article_source')
    op.drop_column('club_event_reports', 'article')
    op.drop_column('club_event_reports', 'article_title')
