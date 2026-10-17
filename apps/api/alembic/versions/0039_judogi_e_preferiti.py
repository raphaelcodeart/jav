"""I judogi del club (club/judogi.py): il listino come dato
(`club_judogi_prices`, caricato con quello del calcolatore vecchio in ogni
club), il conto congelato sull'ordine (`club_equipment_orders`: listino,
personalizzazione, permuta, codice del colore; un ordine uguale in attesa
una volta sola) e la lista dei desideri dell'atleta minorenne
(`club_wishlist_items`).

Revision ID: 0039
Revises: 0038
"""
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = '0039'
down_revision: str | None = '0038'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KIMONO_TYPES = "'FIJ_APPROVED', 'TRAINING', 'SEMI_COMPETITION', 'COMPETITION_NOT_APPROVED'"
COLORS = "'WHITE', 'BLUE', 'PINK', 'WHITE_PINK_STRIPES'"


def upgrade() -> None:
    op.add_column('club_equipment_orders', sa.Column('base_price_cents', sa.BigInteger(), nullable=True))
    op.add_column('club_equipment_orders', sa.Column('customization_cents', sa.BigInteger(), nullable=True))
    op.add_column('club_equipment_orders', sa.Column('trade_in_discount_cents', sa.BigInteger(), nullable=True))
    op.add_column('club_equipment_orders', sa.Column('color_code', sa.String(length=24), nullable=True))
    op.create_index('uq_club_equipment_orders_pending_same', 'club_equipment_orders',
                    ['athlete_id', 'kimono_type', 'color', 'brand', 'size_cm'], unique=True,
                    postgresql_where=sa.text("status = 'PENDING'"))

    op.create_table('club_judogi_prices',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('kimono_type', sa.String(length=24), nullable=False),
    sa.Column('brand', sa.String(length=60), nullable=False),
    sa.Column('color', sa.String(length=24), nullable=False),
    sa.Column('size_cm', sa.SmallInteger(), nullable=False),
    sa.Column('price_cents', sa.BigInteger(), nullable=False),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint(f'kimono_type IN ({KIMONO_TYPES})', name=op.f('ck_club_judogi_prices_kimono_type')),
    sa.CheckConstraint(f'color IN ({COLORS})', name=op.f('ck_club_judogi_prices_color')),
    sa.CheckConstraint('size_cm BETWEEN 80 AND 220', name=op.f('ck_club_judogi_prices_size_range')),
    sa.CheckConstraint('price_cents >= 0', name=op.f('ck_club_judogi_prices_price_non_negative')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_judogi_prices_club_id_clubs')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_judogi_prices_organization_id_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_judogi_prices')),
    sa.UniqueConstraint('club_id', 'kimono_type', 'brand', 'color', 'size_cm', name='uq_club_judogi_prices_item')
    )
    op.create_index(op.f('ix_club_judogi_prices_club_id'), 'club_judogi_prices', ['club_id'], unique=False)

    op.create_table('club_wishlist_items',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('athlete_id', sa.UUID(), nullable=False),
    sa.Column('requested_by_user_id', sa.UUID(), nullable=True),
    sa.Column('kind', sa.String(length=8), nullable=False),
    sa.Column('product_id', sa.UUID(), nullable=True),
    sa.Column('variant_id', sa.UUID(), nullable=True),
    sa.Column('config', sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('note', sa.String(length=300), nullable=True),
    sa.Column('status', sa.String(length=10), server_default='OPEN', nullable=False),
    sa.Column('equipment_order_id', sa.UUID(), nullable=True),
    sa.Column('jav_market_order_id', sa.UUID(), nullable=True),
    sa.Column('decided_by_user_id', sa.UUID(), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("kind IN ('PRODUCT', 'JUDOGI')", name=op.f('ck_club_wishlist_items_kind')),
    sa.CheckConstraint("status IN ('OPEN', 'ORDERED', 'DISMISSED')", name=op.f('ck_club_wishlist_items_status')),
    sa.CheckConstraint("(kind = 'PRODUCT' AND product_id IS NOT NULL) OR (kind = 'JUDOGI' AND config IS NOT NULL)",
                       name=op.f('ck_club_wishlist_items_target')),
    sa.ForeignKeyConstraint(['athlete_id'], ['club_athletes.id'], name=op.f('fk_club_wishlist_items_athlete_id_club_athletes'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_wishlist_items_club_id_clubs')),
    sa.ForeignKeyConstraint(['decided_by_user_id'], ['users.id'], name=op.f('fk_club_wishlist_items_decided_by_user_id_users')),
    sa.ForeignKeyConstraint(['equipment_order_id'], ['club_equipment_orders.id'], name=op.f('fk_club_wishlist_items_equipment_order_id_club_equipment_orders'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['jav_market_order_id'], ['jav_market_orders.id'], name=op.f('fk_club_wishlist_items_jav_market_order_id_jav_market_orders'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_wishlist_items_organization_id_organizations')),
    sa.ForeignKeyConstraint(['product_id'], ['jav_market_products.id'], name=op.f('fk_club_wishlist_items_product_id_jav_market_products'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['requested_by_user_id'], ['users.id'], name=op.f('fk_club_wishlist_items_requested_by_user_id_users')),
    sa.ForeignKeyConstraint(['variant_id'], ['jav_market_variants.id'], name=op.f('fk_club_wishlist_items_variant_id_jav_market_variants'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_wishlist_items'))
    )
    op.create_index(op.f('ix_club_wishlist_items_club_id'), 'club_wishlist_items', ['club_id'], unique=False)
    op.create_index(op.f('ix_club_wishlist_items_athlete_id'), 'club_wishlist_items', ['athlete_id'], unique=False)
    op.create_index(op.f('ix_club_wishlist_items_status'), 'club_wishlist_items', ['status'], unique=False)
    op.create_index('uq_club_wishlist_items_open_product', 'club_wishlist_items', ['athlete_id', 'product_id'],
                    unique=True, postgresql_where=sa.text("status = 'OPEN' AND kind = 'PRODUCT'"))
    op.create_index('uq_club_wishlist_items_open_judogi', 'club_wishlist_items', ['athlete_id'],
                    unique=True, postgresql_where=sa.text("status = 'OPEN' AND kind = 'JUDOGI'"))

    _seed_prices()


def _seed_prices() -> None:
    """Il listino del calcolatore vecchio in ogni club (non nell'unità dei
    Cursos JAV, che non vende judogi). È il listino di club/judogi.py:
    importato e non copiato, così c'è una fonte sola."""
    from app.domains.club.judogi import base_catalog

    bind = op.get_bind()
    clubs = bind.execute(sa.text("SELECT id, organization_id FROM clubs WHERE kind = 'CLUB'")).all()
    if not clubs:
        return
    table = sa.table(
        'club_judogi_prices', sa.column('id', sa.UUID()), sa.column('organization_id', sa.UUID()),
        sa.column('club_id', sa.UUID()), sa.column('kimono_type', sa.String()), sa.column('brand', sa.String()),
        sa.column('color', sa.String()), sa.column('size_cm', sa.SmallInteger()),
        sa.column('price_cents', sa.BigInteger()), sa.column('active', sa.Boolean()),
        sa.column('created_at', sa.DateTime(timezone=True)),
    )
    now = datetime.now(UTC)
    rows = [
        {"id": uuid.uuid4(), "organization_id": org_id, "club_id": club_id, "kimono_type": kind, "brand": brand,
         "color": color, "size_cm": size, "price_cents": cents, "active": True, "created_at": now}
        for club_id, org_id in clubs
        for kind, brand, color, size, cents in base_catalog()
    ]
    op.bulk_insert(table, rows)


def downgrade() -> None:
    op.drop_index('uq_club_wishlist_items_open_judogi', table_name='club_wishlist_items')
    op.drop_index('uq_club_wishlist_items_open_product', table_name='club_wishlist_items')
    op.drop_table('club_wishlist_items')
    op.drop_table('club_judogi_prices')
    op.drop_index('uq_club_equipment_orders_pending_same', table_name='club_equipment_orders')
    op.drop_column('club_equipment_orders', 'color_code')
    op.drop_column('club_equipment_orders', 'trade_in_discount_cents')
    op.drop_column('club_equipment_orders', 'customization_cents')
    op.drop_column('club_equipment_orders', 'base_price_cents')
