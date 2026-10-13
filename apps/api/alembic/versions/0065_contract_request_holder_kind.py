"""Pratica da privato o da azienda, con ragione sociale e legale rappresentante (Session 85).

Il modulo dati della pratica chiede ora se il contratto è per un privato o
per un'azienda. Per un'azienda servono anche la ragione sociale e il codice
fiscale del legale rappresentante (nome e cognome sono quelli
dell'intestatario). Il tipo sta sulla pratica e non sul cliente: la stessa
persona può attivare la luce di casa e quella della sua ditta. Vuoto (le
pratiche già aperte) = il tipo del cliente, come prima.

Revision ID: c7a2d4e91b35
Revises: b5e3f9c72a14
Create Date: 2026-09-25 18:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c7a2d4e91b35"
down_revision: Union[str, None] = "b5e3f9c72a14"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("contract_requests", sa.Column("holder_kind", sa.String(32), nullable=True))
    op.add_column("contract_requests", sa.Column("company_name", sa.String(255), nullable=True))
    op.add_column("contract_requests", sa.Column("legal_rep_fiscal_code", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("contract_requests", "legal_rep_fiscal_code")
    op.drop_column("contract_requests", "company_name")
    op.drop_column("contract_requests", "holder_kind")
