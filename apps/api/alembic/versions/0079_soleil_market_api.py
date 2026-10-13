"""«Market 7» (SoleilDrop): collegamento all'API affiliati v1.

SoleilDrop ha pubblicato l'API (v1 dell'08/10/2026): catalogo, ordini pagati
dal wallet prepagato, stato e tracking, webhook firmati. Qui le colonne per
la chiave e il segreto del webhook, lo stato dell'ordine su SoleilDrop e la
tabella che scarta le riprove dei webhook. Nessun dato esistente cambia: senza
chiave il negozio resta com'era, con l'Excel caricato a mano.

Revision ID: f2b6d8e0a417
Revises: e8a4c1f2d903
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "f2b6d8e0a417"
down_revision: Union[str, None] = "e8a4c1f2d903"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SETTINGS = "soleil_market_settings"
ORDERS = "soleil_market_orders"


def upgrade() -> None:
    op.add_column(SETTINGS, sa.Column("api_key", sa.String(255), nullable=True))
    op.add_column(SETTINGS, sa.Column("webhook_secret", sa.String(255), nullable=True))
    op.add_column(SETTINGS, sa.Column("auto_import", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column(SETTINGS, sa.Column("eshop_name", sa.String(160), nullable=True))
    op.add_column(SETTINGS, sa.Column("wallet_balance_cents", sa.BigInteger(), nullable=True))
    op.add_column(SETTINGS, sa.Column("last_api_check_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(SETTINGS, sa.Column("last_api_error", sa.String(500), nullable=True))
    op.add_column(SETTINGS, sa.Column("last_webhook_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(SETTINGS, sa.Column("last_order_sync_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column(ORDERS, sa.Column("soleil_order_number", sa.String(64), nullable=True))
    op.add_column(ORDERS, sa.Column("soleil_status_code", sa.String(64), nullable=True))
    op.add_column(ORDERS, sa.Column("soleil_status_label", sa.String(128), nullable=True))
    op.add_column(ORDERS, sa.Column("soleil_wallet_charged_cents", sa.BigInteger(), nullable=True))
    op.add_column(ORDERS, sa.Column("soleil_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_soleil_market_orders_soleil_order_number", ORDERS, ["soleil_order_number"])

    op.create_table(
        "soleil_market_webhook_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("delivery_id", sa.String(128), nullable=False),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("soleil_order_number", sa.String(64), nullable=True),
        sa.Column("external_ref", sa.String(64), nullable=True),
        sa.UniqueConstraint("organization_id", "delivery_id", name="uq_soleil_market_webhook_events_delivery"),
    )
    op.create_index(
        "ix_soleil_market_webhook_events_organization_id", "soleil_market_webhook_events", ["organization_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_soleil_market_webhook_events_organization_id", table_name="soleil_market_webhook_events")
    op.drop_table("soleil_market_webhook_events")
    op.drop_index("ix_soleil_market_orders_soleil_order_number", table_name=ORDERS)
    for column in (
        "soleil_synced_at", "soleil_wallet_charged_cents", "soleil_status_label", "soleil_status_code",
        "soleil_order_number",
    ):
        op.drop_column(ORDERS, column)
    for column in (
        "last_order_sync_at", "last_webhook_at", "last_api_error", "last_api_check_at", "wallet_balance_cents",
        "eshop_name", "auto_import", "webhook_secret", "api_key",
    ):
        op.drop_column(SETTINGS, column)
