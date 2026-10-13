"""Peer-to-peer wallet transfer (POST /wallets/transfer) is now denied by
default for every wallet -- customer or promoter alike -- and must be
enabled individually per promoter by an admin. See
docs/business-rules.md#internal-wallet.

Revision ID: d4b7f291a856
Revises: c9a1e4b6d2f3
Create Date: 2026-09-05 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4b7f291a856"
down_revision: Union[str, None] = "c9a1e4b6d2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "wallets",
        sa.Column("can_transfer", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("wallets", "can_transfer")
