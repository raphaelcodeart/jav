"""Marketplace 3: integrazione AliExpress dropshipping (Session 71).

Four tables of their own, next to (and independent from) CJ and Shopify --
see app/domains/aliexpress_dropshipping/models.py:

- aliexpress_settings: the DS app (App Key + App Secret), the authorisation
  of the seller account (access/refresh token) and the pricing rules;
- aliexpress_products / aliexpress_variants: the products chosen for sale,
  with AliExpress' cost/price and the customer price in EUR;
- aliexpress_orders: a customer's purchase, its delivery address, frozen
  amounts (bank-transfer discount included) and its life at the supplier
  until delivery.

Plus wallet_transactions.reference_aliexpress_order_id, so the JavCash
spent on a Marketplace 3 order points at it like the other order tables.

Two things worth saying out loud:

1. `aliexpress_orders` and `wallet_transactions` reference each other. Same
   answer as 0050: the order table declares its FK to wallet_transactions
   inline (wallet_transactions already exists), and the column on
   wallet_transactions gets its FK added afterwards, once the order table
   is there.

2. The credentials are **copied**, not retyped. Session 71 first saved the
   AliExpress app on `import_providers` (App Key '547960' is in production
   already); the row is carried over here for every organization that has
   one, so nobody has to go and find the App Secret again. Nothing is
   dropped on the way: the old manual plugin keeps its columns and its
   tables and goes on working exactly as before.

Revision ID: b7d1f4a20c58
Revises: a4c2e7f10b93
Create Date: 2026-09-19 23:59:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7d1f4a20c58"
down_revision: Union[str, None] = "a4c2e7f10b93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)
TS = sa.DateTime(timezone=True)


def _ts() -> sa.Column:
    return sa.Column("created_at", TS, nullable=False, server_default=sa.func.now())


def upgrade() -> None:
    op.create_table(
        "aliexpress_settings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("app_key", sa.String(64), nullable=True),
        sa.Column("app_secret", sa.String(255), nullable=True),
        sa.Column("access_token", sa.String(500), nullable=True),
        sa.Column("refresh_token", sa.String(500), nullable=True),
        sa.Column("token_expires_at", TS, nullable=True),
        sa.Column("account_label", sa.String(255), nullable=True),
        sa.Column("last_connected_at", TS, nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("ship_to_country", sa.String(2), nullable=False, server_default="IT"),
        sa.Column("target_currency", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column("target_language", sa.String(8), nullable=False, server_default="it"),
        sa.Column("currency_rate", sa.Numeric(10, 6), nullable=False, server_default="1"),
        sa.Column("price_basis", sa.String(8), nullable=False, server_default="COST"),
        sa.Column("markup_percentage", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("markup_fixed_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("price_rounding", sa.String(8), nullable=False, server_default="90"),
        sa.Column("shipping_mode", sa.String(16), nullable=False, server_default="CUSTOMER_PAYS"),
        sa.Column("shipping_flat_cents", sa.Integer(), nullable=False, server_default="590"),
        sa.Column("shipping_days", sa.String(32), nullable=True, server_default="10-20"),
        sa.Column("default_credit_percentage", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("auto_forward", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", TS, nullable=True),
        _ts(),
        sa.UniqueConstraint("organization_id", name="uq_aliexpress_settings_organization_id"),
    )

    op.create_table(
        "aliexpress_products",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("aliexpress_product_id", sa.String(128), nullable=False),
        sa.Column("product_url", sa.String(1000), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("source_title", sa.String(500), nullable=True),
        sa.Column("vendor", sa.String(255), nullable=True),
        sa.Column("description", sa.String(8000), nullable=False, server_default=""),
        sa.Column("image_url", sa.String(1000), nullable=True),
        sa.Column("images", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("credit_discount_percentage", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("markup_percentage", sa.Integer(), nullable=True),
        sa.Column("last_synced_at", TS, nullable=True),
        sa.Column("sync_error", sa.String(500), nullable=True),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_at", TS, nullable=True),
        _ts(),
        # The convention in core/db.py names a unique constraint after its
        # first column, so this is what the models build too.
        sa.UniqueConstraint("organization_id", "aliexpress_product_id", name="uq_aliexpress_products_organization_id"),
        sa.CheckConstraint(
            "credit_discount_percentage >= 0 AND credit_discount_percentage <= 99",
            name="credit_discount_percentage_below_100",
        ),
    )
    op.create_index("ix_aliexpress_products_organization_id", "aliexpress_products", ["organization_id"])
    op.create_index("ix_aliexpress_products_status", "aliexpress_products", ["status"])

    op.create_table(
        "aliexpress_variants",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("product_id", UUID, sa.ForeignKey("aliexpress_products.id"), nullable=False),
        sa.Column("aliexpress_sku_id", sa.String(128), nullable=False),
        sa.Column("sku_attr", sa.String(500), nullable=True),
        sa.Column("sku", sa.String(128), nullable=True),
        sa.Column("label", sa.String(255), nullable=False, server_default=""),
        sa.Column("image_url", sa.String(1000), nullable=True),
        sa.Column("cost_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("source_price_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("price_cents", sa.BigInteger(), nullable=False),
        sa.Column("price_override_cents", sa.BigInteger(), nullable=True),
        sa.Column("inventory", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("available_in_store", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_synced_at", TS, nullable=True),
        _ts(),
        sa.UniqueConstraint("product_id", "aliexpress_sku_id", name="uq_aliexpress_variants_product_id"),
    )
    op.create_index("ix_aliexpress_variants_product_id", "aliexpress_variants", ["product_id"])

    op.create_table(
        "aliexpress_orders",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("customer_user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("aliexpress_product_id", UUID, sa.ForeignKey("aliexpress_products.id"), nullable=False),
        sa.Column("aliexpress_variant_id", UUID, sa.ForeignKey("aliexpress_variants.id"), nullable=False),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("unit_price_cents", sa.BigInteger(), nullable=False),
        sa.Column("shipping_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("credit_applied_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("bank_transfer_discount_cents", sa.BigInteger(), nullable=False, server_default="0"),
        # The first half of the cycle: wallet_transactions is already there,
        # so this side can be declared inline (see 0050).
        sa.Column("credit_debit_transaction_id", UUID, sa.ForeignKey("wallet_transactions.id"), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="AWAITING_PAYMENT"),
        sa.Column("payment_method", sa.String(16), nullable=False, server_default="BANK_TRANSFER"),
        sa.Column("stripe_checkout_session_id", sa.String(255), nullable=True),
        sa.Column("note", sa.String(1000), nullable=True),
        sa.Column("payment_proof_storage_key", sa.String(500), nullable=True),
        sa.Column("payment_proof_original_filename", sa.String(255), nullable=True),
        sa.Column("payment_proof_uploaded_at", TS, nullable=True),
        sa.Column("paid_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("paid_at", TS, nullable=True),
        sa.Column("cancelled_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("cancelled_at", TS, nullable=True),
        sa.Column("cancellation_reason", sa.String(500), nullable=True),
        sa.Column("recipient_name", sa.String(128), nullable=False),
        sa.Column("recipient_phone", sa.String(32), nullable=True),
        sa.Column("address_line1", sa.String(255), nullable=False),
        sa.Column("address_line2", sa.String(255), nullable=True),
        sa.Column("city", sa.String(128), nullable=False),
        sa.Column("province", sa.String(64), nullable=False),
        sa.Column("postal_code", sa.String(16), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False, server_default="IT"),
        sa.Column("shipping_days", sa.String(32), nullable=True),
        sa.Column("unit_cost_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency_rate", sa.Numeric(10, 6), nullable=False, server_default="1"),
        sa.Column("fulfillment_status", sa.String(16), nullable=False, server_default="NOT_SENT"),
        sa.Column("out_order_id", sa.String(64), nullable=True),
        sa.Column("aliexpress_order_id", sa.String(128), nullable=True),
        sa.Column("aliexpress_order_status", sa.String(64), nullable=True),
        sa.Column("forwarded_at", TS, nullable=True),
        sa.Column("forwarded_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("forward_error", sa.String(500), nullable=True),
        sa.Column("tracking_number", sa.String(128), nullable=True),
        sa.Column("tracking_url", sa.String(1000), nullable=True),
        sa.Column("tracking_company", sa.String(128), nullable=True),
        sa.Column("shipped_at", TS, nullable=True),
        sa.Column("delivered_at", TS, nullable=True),
        sa.Column("last_sync_at", TS, nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempt_at", TS, nullable=True),
        sa.Column("next_retry_at", TS, nullable=True),
        sa.Column("last_error_kind", sa.String(24), nullable=True),
        _ts(),
        sa.UniqueConstraint("stripe_checkout_session_id", name="uq_aliexpress_orders_stripe_checkout_session_id"),
        sa.CheckConstraint("credit_applied_cents >= 0", name="credit_applied_non_negative"),
        sa.CheckConstraint(
            "credit_applied_cents <= amount_cents", name="credit_applied_not_over_amount"
        ),
        sa.CheckConstraint("quantity > 0", name="quantity_positive"),
    )
    op.create_index("ix_aliexpress_orders_organization_id", "aliexpress_orders", ["organization_id"])
    op.create_index("ix_aliexpress_orders_customer_user_id", "aliexpress_orders", ["customer_user_id"])
    op.create_index("ix_aliexpress_orders_status", "aliexpress_orders", ["status"])
    op.create_index("ix_aliexpress_orders_fulfillment_status", "aliexpress_orders", ["fulfillment_status"])
    op.create_index("ix_aliexpress_orders_aliexpress_order_id", "aliexpress_orders", ["aliexpress_order_id"])
    op.create_index("ix_aliexpress_orders_out_order_id", "aliexpress_orders", ["out_order_id"])
    op.create_index("ix_aliexpress_orders_next_retry_at", "aliexpress_orders", ["next_retry_at"])

    # The other half of the cycle, now that aliexpress_orders exists.
    op.add_column("wallet_transactions", sa.Column("reference_aliexpress_order_id", UUID, nullable=True))
    op.create_foreign_key(
        "fk_wallet_transactions_reference_aliexpress_order_id_al_d92c", "wallet_transactions",
        "aliexpress_orders", ["reference_aliexpress_order_id"], ["id"],
    )

    # Le credenziali già salvate sul vecchio plugin, portate qui.
    # One settings row per organization that configured an ALIEXPRESS
    # provider, taking the most recently updated one when there are
    # several. Nothing is written for an organization that has none: its
    # row is created empty the first time the screen is opened.
    op.execute(
        """
        INSERT INTO aliexpress_settings (
            id, organization_id, app_key, app_secret, access_token, refresh_token,
            token_expires_at, account_label, last_connected_at, created_at
        )
        SELECT
            gen_random_uuid(), p.organization_id, p.app_key, p.app_secret, p.access_token,
            p.refresh_token, p.token_expires_at, p.account_label, p.last_connected_at, now()
        FROM (
            SELECT DISTINCT ON (organization_id) *
            FROM import_providers
            WHERE provider_type = 'ALIEXPRESS' AND app_key IS NOT NULL
            ORDER BY organization_id, created_at DESC
        ) AS p
        ON CONFLICT (organization_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_wallet_transactions_reference_aliexpress_order_id_al_d92c", "wallet_transactions",
        type_="foreignkey",
    )
    op.drop_column("wallet_transactions", "reference_aliexpress_order_id")
    op.drop_table("aliexpress_orders")
    op.drop_table("aliexpress_variants")
    op.drop_table("aliexpress_products")
    op.drop_table("aliexpress_settings")
