"""La bacheca del club per atleti e famiglie: le notizie (`club_news_posts`),
i documenti del club condivisi con i soci (`club_documents.shared_with_members`)
e chi nel club è anche árbitro (`club_referees`, il segno accanto al nome).
Regole in docs/club-portal.md, "La bacheca".

Revision ID: 0018
Revises: 0017
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0018'
down_revision: str | None = '0017'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('club_documents', sa.Column('shared_with_members', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.create_table('club_news_posts',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('image_url', sa.String(length=500), nullable=True),
    sa.Column('video_url', sa.String(length=500), nullable=True),
    sa.Column('link_url', sa.String(length=500), nullable=True),
    sa.Column('pinned', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('published', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('author_user_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['author_user_id'], ['users.id'], name=op.f('fk_club_news_posts_author_user_id_users')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_news_posts_club_id_clubs')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_news_posts_organization_id_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_news_posts'))
    )
    op.create_index(op.f('ix_club_news_posts_club_id'), 'club_news_posts', ['club_id'], unique=False)
    op.create_table('club_referees',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('athlete_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('(user_id IS NULL) <> (athlete_id IS NULL)', name=op.f('ck_club_referees_one_person')),
    sa.ForeignKeyConstraint(['athlete_id'], ['club_athletes.id'], name=op.f('fk_club_referees_athlete_id_club_athletes'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_referees_club_id_clubs')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_referees_organization_id_organizations')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_club_referees_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_referees')),
    sa.UniqueConstraint('club_id', 'athlete_id', name='uq_club_referees_club_athlete'),
    sa.UniqueConstraint('club_id', 'user_id', name='uq_club_referees_club_user')
    )
    op.create_index(op.f('ix_club_referees_club_id'), 'club_referees', ['club_id'], unique=False)
    op.create_index(op.f('ix_club_referees_organization_id'), 'club_referees', ['organization_id'], unique=False)


def downgrade() -> None:
    op.drop_table('club_referees')
    op.drop_table('club_news_posts')
    op.drop_column('club_documents', 'shared_with_members')
