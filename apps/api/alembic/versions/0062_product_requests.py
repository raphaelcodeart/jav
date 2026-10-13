"""Le richieste di prodotto dallo Shop: «Non hai trovato ciò che cercavi?».

Un sistema di ticket dedicato, separato da `tickets` / `ticket_messages`
(Supporto & Assistenza) di proposito: stessa forma -- una richiesta, una
conversazione, uno stato -- ma una coda sua, così una richiesta di prodotto
non si confonde con un guasto e viceversa. Vedi
app/domains/product_requests/models.py.

Revision ID: f3a91c07b6d2
Revises: e2c58a90d417
Create Date: 2026-09-24 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "f3a91c07b6d2"
down_revision: Union[str, None] = "e2c58a90d417"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "product_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("opened_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("opened_by_role", sa.String(32), nullable=False),
        sa.Column("product_name", sa.String(255), nullable=False),
        sa.Column("reference_url", sa.String(1000), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="OPEN"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_product_requests_organization_id", "product_requests", ["organization_id"])
    op.create_index("ix_product_requests_opened_by_user_id", "product_requests", ["opened_by_user_id"])
    op.create_index("ix_product_requests_status", "product_requests", ["status"])

    op.create_table(
        "product_request_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", UUID(as_uuid=True), sa.ForeignKey("product_requests.id"), nullable=False),
        sa.Column("author_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("author_role", sa.String(32), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_product_request_messages_request_id", "product_request_messages", ["request_id"])


def downgrade() -> None:
    op.drop_index("ix_product_request_messages_request_id", table_name="product_request_messages")
    op.drop_table("product_request_messages")
    op.drop_index("ix_product_requests_status", table_name="product_requests")
    op.drop_index("ix_product_requests_opened_by_user_id", table_name="product_requests")
    op.drop_index("ix_product_requests_organization_id", table_name="product_requests")
    op.drop_table("product_requests")
