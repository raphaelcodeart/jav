"""La bacheca del circuito: i post di un club per tutti i club
(`club_news_posts.audience` = NETWORK), i post di JudoArteVida (club_id
NULL) e i «mi piace» (`club_news_likes`).

Revision ID: 0024
Revises: 0023
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0024'
down_revision: str | None = '0023'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('club_news_posts', sa.Column('audience', sa.String(length=8), server_default='CLUB', nullable=False))
    op.alter_column('club_news_posts', 'club_id', existing_type=sa.UUID(), nullable=True)
    op.create_check_constraint(op.f('ck_club_news_posts_audience'), 'club_news_posts', "audience IN ('CLUB', 'NETWORK')")
    op.create_check_constraint(op.f('ck_club_news_posts_platform_is_network'), 'club_news_posts',
                               "club_id IS NOT NULL OR audience = 'NETWORK'")
    op.create_table('club_news_likes',
    sa.Column('post_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['post_id'], ['club_news_posts.id'], name=op.f('fk_club_news_likes_post_id_club_news_posts'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_club_news_likes_user_id_users')),
    sa.PrimaryKeyConstraint('post_id', 'user_id', name=op.f('pk_club_news_likes'))
    )


def downgrade() -> None:
    op.drop_table('club_news_likes')
    op.drop_constraint(op.f('ck_club_news_posts_platform_is_network'), 'club_news_posts', type_='check')
    op.drop_constraint(op.f('ck_club_news_posts_audience'), 'club_news_posts', type_='check')
    op.execute("DELETE FROM club_news_posts WHERE club_id IS NULL")
    op.alter_column('club_news_posts', 'club_id', existing_type=sa.UUID(), nullable=False)
    op.drop_column('club_news_posts', 'audience')
