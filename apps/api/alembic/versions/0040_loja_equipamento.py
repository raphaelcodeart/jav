"""La Loja del club (club/loja.py): gli ordini del club diventano di due
tipi, judogi o prodotto dello shop del club, sempre uno per riga
(`club_equipment_orders.kind`, i campi del judogi facoltativi per un
prodotto), con l'armadio dei judogi dell'atleta (`origin` MANUAL,
`retired_on`); il carrello della Loja (`club_cart_items`); le foto dei
modelli di judogi (`club_judogi_models`); per chi è un prodotto del club
(`jav_market_products.audience_sex`, `high_competition_only`, `club_kit`,
`needs_name`; `jav_market_variants.max_height_cm`); l'alta competizione
(`club_athletes.high_competition`, possibile solo nei piani
`allows_high_competition`: lo diventano i «Grupo 3» che esistono già).

Revision ID: 0040
Revises: 0039
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0040'
down_revision: str | None = '0039'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KIMONO_TYPES = "'FIJ_APPROVED', 'TRAINING', 'SEMI_COMPETITION', 'COMPETITION_NOT_APPROVED'"
COLORS = "'WHITE', 'BLUE', 'PINK', 'WHITE_PINK_STRIPES'"


def upgrade() -> None:
    # --- Alta competizione ---
    op.add_column('club_plans', sa.Column('allows_high_competition', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('club_athletes', sa.Column('high_competition', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('club_athletes', sa.Column('high_competition_by_user_id', sa.UUID(), nullable=True))
    op.add_column('club_athletes', sa.Column('high_competition_at', sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(op.f('fk_club_athletes_high_competition_by_user_id_users'), 'club_athletes', 'users',
                          ['high_competition_by_user_id'], ['id'])
    # Il Grupo 3 (competição) è il gruppo dell'alta competizione: chi c'è già
    # può essere segnato da subito; gli altri piani la segreteria li apre a mano.
    op.execute("UPDATE club_plans SET allows_high_competition = true WHERE name ILIKE 'Grupo 3%'")

    # --- Per chi è un prodotto del club ---
    op.add_column('jav_market_products', sa.Column('audience_sex', sa.String(length=3), server_default='ALL', nullable=False))
    op.add_column('jav_market_products', sa.Column('high_competition_only', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('jav_market_products', sa.Column('club_kit', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('jav_market_products', sa.Column('needs_name', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.create_check_constraint(op.f('ck_jav_market_products_audience_sex'), 'jav_market_products',
                               "audience_sex IN ('ALL', 'F', 'M')")
    op.add_column('jav_market_variants', sa.Column('max_height_cm', sa.SmallInteger(), nullable=True))
    op.create_check_constraint(op.f('ck_jav_market_variants_max_height_range'), 'jav_market_variants',
                               'max_height_cm IS NULL OR max_height_cm BETWEEN 50 AND 230')

    # --- Gli ordini del club: judogi o prodotto ---
    op.add_column('club_equipment_orders', sa.Column('kind', sa.String(length=8), server_default='JUDOGI', nullable=False))
    op.add_column('club_equipment_orders', sa.Column('origin', sa.String(length=8), server_default='ORDER', nullable=False))
    op.add_column('club_equipment_orders', sa.Column('product_id', sa.UUID(), nullable=True))
    op.add_column('club_equipment_orders', sa.Column('variant_id', sa.UUID(), nullable=True))
    op.add_column('club_equipment_orders', sa.Column('product_name', sa.String(length=255), nullable=True))
    op.add_column('club_equipment_orders', sa.Column('variant_label', sa.String(length=255), nullable=True))
    op.add_column('club_equipment_orders', sa.Column('quantity', sa.SmallInteger(), server_default='1', nullable=False))
    op.add_column('club_equipment_orders', sa.Column('unit_price_cents', sa.BigInteger(), nullable=True))
    op.add_column('club_equipment_orders', sa.Column('retired_on', sa.Date(), nullable=True))
    op.add_column('club_equipment_orders', sa.Column('retired_reason', sa.String(length=16), nullable=True))
    for column in ('kimono_name', 'kimono_type', 'color', 'brand', 'size_cm'):
        op.alter_column('club_equipment_orders', column, nullable=True)
    op.create_foreign_key(op.f('fk_club_equipment_orders_product_id_jav_market_products'), 'club_equipment_orders',
                          'jav_market_products', ['product_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(op.f('fk_club_equipment_orders_variant_id_jav_market_variants'), 'club_equipment_orders',
                          'jav_market_variants', ['variant_id'], ['id'], ondelete='SET NULL')
    op.create_index(op.f('ix_club_equipment_orders_product_id'), 'club_equipment_orders', ['product_id'], unique=False)
    op.create_check_constraint(op.f('ck_club_equipment_orders_kind'), 'club_equipment_orders', "kind IN ('JUDOGI', 'PRODUCT')")
    op.create_check_constraint(op.f('ck_club_equipment_orders_origin'), 'club_equipment_orders', "origin IN ('ORDER', 'MANUAL')")
    op.create_check_constraint(op.f('ck_club_equipment_orders_retired_reason'), 'club_equipment_orders',
                               "retired_reason IN ('TRADED_IN', 'OUTGROWN', 'WORN_OUT', 'LOST')")
    op.create_check_constraint(op.f('ck_club_equipment_orders_quantity_positive'), 'club_equipment_orders', 'quantity >= 1')
    op.create_check_constraint(
        op.f('ck_club_equipment_orders_judogi_fields'), 'club_equipment_orders',
        "kind <> 'JUDOGI' OR (kimono_type IS NOT NULL AND color IS NOT NULL AND brand IS NOT NULL"
        " AND size_cm IS NOT NULL AND kimono_name IS NOT NULL)",
    )
    op.create_check_constraint(op.f('ck_club_equipment_orders_product_fields'), 'club_equipment_orders',
                               "kind <> 'PRODUCT' OR product_name IS NOT NULL")

    # --- I modelli di judogi con le foto ---
    op.create_table('club_judogi_models',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('kimono_type', sa.String(length=24), nullable=False),
    sa.Column('brand', sa.String(length=60), nullable=False),
    sa.Column('color', sa.String(length=24), nullable=False),
    sa.Column('description', sa.String(length=2000), nullable=True),
    sa.Column('image_url', sa.String(length=1000), nullable=True),
    sa.Column('images', sa.dialects.postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint(f'kimono_type IN ({KIMONO_TYPES})', name=op.f('ck_club_judogi_models_kimono_type')),
    sa.CheckConstraint(f'color IN ({COLORS})', name=op.f('ck_club_judogi_models_color')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_judogi_models_club_id_clubs')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_judogi_models_organization_id_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_judogi_models')),
    sa.UniqueConstraint('club_id', 'kimono_type', 'brand', 'color', name='uq_club_judogi_models_item')
    )
    op.create_index(op.f('ix_club_judogi_models_club_id'), 'club_judogi_models', ['club_id'], unique=False)
    # Una scheda per ogni modello del listino che c'è già: la segreteria
    # deve solo aggiungere le foto.
    op.execute("""
        INSERT INTO club_judogi_models (id, organization_id, club_id, kimono_type, brand, color, images,
                                        created_at, updated_at)
        SELECT gen_random_uuid(), organization_id, club_id, kimono_type, brand, color, '[]'::jsonb, now(), now()
        FROM (SELECT DISTINCT organization_id, club_id, kimono_type, brand, color FROM club_judogi_prices) p
    """)

    # --- Il carrello della Loja ---
    op.create_table('club_cart_items',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('athlete_id', sa.UUID(), nullable=False),
    sa.Column('kind', sa.String(length=8), nullable=False),
    sa.Column('product_id', sa.UUID(), nullable=True),
    sa.Column('variant_id', sa.UUID(), nullable=True),
    sa.Column('quantity', sa.SmallInteger(), server_default='1', nullable=False),
    sa.Column('config', sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("kind IN ('JUDOGI', 'PRODUCT')", name=op.f('ck_club_cart_items_kind')),
    sa.CheckConstraint('quantity BETWEEN 1 AND 20', name=op.f('ck_club_cart_items_quantity_range')),
    sa.CheckConstraint("(kind = 'PRODUCT' AND variant_id IS NOT NULL) OR (kind = 'JUDOGI' AND config IS NOT NULL)",
                       name=op.f('ck_club_cart_items_target')),
    sa.ForeignKeyConstraint(['athlete_id'], ['club_athletes.id'], name=op.f('fk_club_cart_items_athlete_id_club_athletes'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_cart_items_club_id_clubs')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_cart_items_organization_id_organizations')),
    sa.ForeignKeyConstraint(['product_id'], ['jav_market_products.id'], name=op.f('fk_club_cart_items_product_id_jav_market_products'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_club_cart_items_user_id_users')),
    sa.ForeignKeyConstraint(['variant_id'], ['jav_market_variants.id'], name=op.f('fk_club_cart_items_variant_id_jav_market_variants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_cart_items'))
    )
    op.create_index(op.f('ix_club_cart_items_athlete_id'), 'club_cart_items', ['athlete_id'], unique=False)
    op.create_index(op.f('ix_club_cart_items_club_id'), 'club_cart_items', ['club_id'], unique=False)
    op.create_index(op.f('ix_club_cart_items_user_id'), 'club_cart_items', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_table('club_cart_items')
    op.drop_table('club_judogi_models')
    for name in ('product_fields', 'judogi_fields', 'quantity_positive', 'retired_reason', 'origin', 'kind'):
        op.drop_constraint(op.f(f'ck_club_equipment_orders_{name}'), 'club_equipment_orders', type_='check')
    op.drop_index(op.f('ix_club_equipment_orders_product_id'), table_name='club_equipment_orders')
    op.drop_constraint(op.f('fk_club_equipment_orders_variant_id_jav_market_variants'), 'club_equipment_orders', type_='foreignkey')
    op.drop_constraint(op.f('fk_club_equipment_orders_product_id_jav_market_products'), 'club_equipment_orders', type_='foreignkey')
    op.execute("DELETE FROM club_equipment_orders WHERE kind <> 'JUDOGI'")
    for column in ('kimono_name', 'kimono_type', 'color', 'brand', 'size_cm'):
        op.alter_column('club_equipment_orders', column, nullable=False)
    for column in ('retired_reason', 'retired_on', 'unit_price_cents', 'quantity', 'variant_label', 'product_name',
                   'variant_id', 'product_id', 'origin', 'kind'):
        op.drop_column('club_equipment_orders', column)
    op.drop_constraint(op.f('ck_jav_market_variants_max_height_range'), 'jav_market_variants', type_='check')
    op.drop_column('jav_market_variants', 'max_height_cm')
    op.drop_constraint(op.f('ck_jav_market_products_audience_sex'), 'jav_market_products', type_='check')
    for column in ('needs_name', 'club_kit', 'high_competition_only', 'audience_sex'):
        op.drop_column('jav_market_products', column)
    op.drop_constraint(op.f('fk_club_athletes_high_competition_by_user_id_users'), 'club_athletes', type_='foreignkey')
    for column in ('high_competition_at', 'high_competition_by_user_id', 'high_competition'):
        op.drop_column('club_athletes', column)
    op.drop_column('club_plans', 'allows_high_competition')
