"""Pratica: data e luogo di nascita, codice fiscale del privato (Session 89).

Nel primo passo della pratica (cliente, promoter, amministrazione) chi firma
-- l'intestatario privato o il legale rappresentante -- dà anche data e
luogo di nascita, e il codice fiscale si controlla contro nome, cognome,
data e luogo (core/fiscal_code.py).

- `contract_requests.holder_fiscal_code` -- il codice fiscale di un
  intestatario privato (quello del legale rappresentante resta in
  `legal_rep_fiscal_code`).
- `contract_requests.holder_birth_date`, `holder_birth_place` («Roma (RM)»)
  e `holder_birth_place_code` (codice catastale, H501; Z… per gli Stati
  esteri).

Tutte vuote sulle pratiche aperte prima: una bozza non si invia finché non
le ha.

Revision ID: f2c8d4a61b93
Revises: e7b3c5d18a42
Create Date: 2026-10-01 09:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2c8d4a61b93"
down_revision: Union[str, None] = "e7b3c5d18a42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("contract_requests", sa.Column("holder_fiscal_code", sa.String(16), nullable=True))
    op.add_column("contract_requests", sa.Column("holder_birth_date", sa.Date(), nullable=True))
    op.add_column("contract_requests", sa.Column("holder_birth_place", sa.String(160), nullable=True))
    op.add_column("contract_requests", sa.Column("holder_birth_place_code", sa.String(4), nullable=True))


def downgrade() -> None:
    op.drop_column("contract_requests", "holder_birth_place_code")
    op.drop_column("contract_requests", "holder_birth_place")
    op.drop_column("contract_requests", "holder_birth_date")
    op.drop_column("contract_requests", "holder_fiscal_code")
