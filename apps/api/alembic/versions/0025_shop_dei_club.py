"""Lo shop di ogni club: chi vende un prodotto e un ordine
(`jav_market_products.club_id`, `jav_market_orders.club_id`; NULL = lo shop
unico di JudoArteVida).

Revision ID: 0025
Revises: 0024
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0025'
down_revision: str | None = '0024'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ('jav_market_products', 'jav_market_orders'):
        op.add_column(table, sa.Column('club_id', sa.UUID(), nullable=True))
        op.create_index(op.f(f'ix_{table}_club_id'), table, ['club_id'], unique=False)
        op.create_foreign_key(op.f(f'fk_{table}_club_id_clubs'), table, 'clubs', ['club_id'], ['id'])


def downgrade() -> None:
    for table in ('jav_market_products', 'jav_market_orders'):
        op.drop_constraint(op.f(f'fk_{table}_club_id_clubs'), table, type_='foreignkey')
        op.drop_index(op.f(f'ix_{table}_club_id'), table_name=table)
        op.drop_column(table, 'club_id')
