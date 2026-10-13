"""Il prezzo mensile dei contratti, separato dal prezzo annuale (Session 84).

Fino a qui `product_versions.base_price_cents` di un contratto era il canone
mensile e il contratto costava canone x 12, sia in unica soluzione sia a
rate. Ma pagare a rate costa di più: «Energia circolare» privati è 149 € in
unica soluzione e 18,30 € al mese per 12 rate (219,60 €), che non è 149 / 12.

Da qui `base_price_cents` è il prezzo dell'intero contratto pagato in una
volta, e `monthly_price_cents` la rata mensile. Il contratto congela entrambi
i prezzi alla creazione (`instalments_*_amount_cents` accanto agli importi di
sempre), perché la modalità di pagamento si sceglie dopo.

I prodotti esistenti vengono convertiti senza cambiare nessun prezzo:
prezzo in unica soluzione = vecchio canone x periodi, prezzo mensile vuoto.
Senza prezzo mensile un pacchetto si comporta esattamente come prima -- le
rate dividono il prezzo, lo sconto per il pagamento unico si applica --
finché l'amministratore non compila i due prezzi dal pannello Prodotti.

Revision ID: b5e3f9c72a14
Revises: a4d2e8b61f93
Create Date: 2026-09-25 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b5e3f9c72a14"
down_revision: Union[str, None] = "a4d2e8b61f93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Same arithmetic as catalog/pricing.py::contract_billing_periods, written
# out in SQL: a migration must not import application code that will change.
_PERIODS = """
    (CASE upper(v.billing_period) WHEN 'MONTHLY' THEN 1 WHEN 'QUARTERLY' THEN 3 WHEN 'ANNUAL' THEN 12 END)
"""
_RECURRING = """
    FROM products p
    WHERE p.id = v.product_id
      AND upper(p.product_type) IN ('ENERGY_CONTRACT', 'SUBSCRIPTION')
      AND coalesce(v.contract_duration_months, 0) > 0
      AND upper(v.billing_period) IN ('MONTHLY', 'QUARTERLY', 'ANNUAL')
"""


def upgrade() -> None:
    op.add_column("product_versions", sa.Column("monthly_price_cents", sa.BigInteger(), nullable=True))
    for column in ("instalments_net_amount_cents", "instalments_vat_amount_cents", "instalments_gross_amount_cents"):
        op.add_column("contracts", sa.Column(column, sa.BigInteger(), nullable=True))
    # The one-go price becomes what the whole term cost until now;
    # greatest(1, ...) as in the Python. No monthly price: see the docstring.
    op.execute(
        f"""
        UPDATE product_versions v
        SET base_price_cents = v.base_price_cents * greatest(1, v.contract_duration_months / {_PERIODS})
        {_RECURRING}
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE product_versions v
        SET base_price_cents = v.base_price_cents / greatest(1, v.contract_duration_months / {_PERIODS})
        {_RECURRING}
        """
    )
    for column in ("instalments_gross_amount_cents", "instalments_vat_amount_cents", "instalments_net_amount_cents"):
        op.drop_column("contracts", column)
    op.drop_column("product_versions", "monthly_price_cents")
