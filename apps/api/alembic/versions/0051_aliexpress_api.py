"""Marketplace 3 (AliExpress): the Dropshipping API credentials.

Session 71. The provider row stops being just a name + a generic api_key:
an AliExpress DS app is an App Key + App Secret, and the authorisation of
the seller account gives an access token (and a refresh token) that expire.

Revision ID: a4c2e7f10b93
Revises: f3b8c1d9e274
Create Date: 2026-09-19 23:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a4c2e7f10b93"
down_revision: Union[str, None] = "f3b8c1d9e274"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TS = sa.DateTime(timezone=True)

COLUMNS = (
    sa.Column("app_key", sa.String(64), nullable=True),
    sa.Column("app_secret", sa.String(255), nullable=True),
    sa.Column("access_token", sa.String(500), nullable=True),
    sa.Column("refresh_token", sa.String(500), nullable=True),
    sa.Column("token_expires_at", TS, nullable=True),
    sa.Column("account_label", sa.String(255), nullable=True),
    sa.Column("last_connected_at", TS, nullable=True),
)


def upgrade() -> None:
    for column in COLUMNS:
        op.add_column("import_providers", column)


def downgrade() -> None:
    for column in reversed(COLUMNS):
        op.drop_column("import_providers", column.name)
