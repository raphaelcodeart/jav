"""Un numero d'ordine leggibile, per il cliente (Session 76).

Fino a qui un ordine si chiamava con le prime otto cifre del suo UUID:
`JAV-7B3F2A91`. Va bene per un log, non per una persona -- non si detta
al telefono, non si ricorda, e due ordini vicini non si riconoscono
nemmeno a colpo d'occhio.

Da qui ogni ordine porta un **numero progressivo**, assegnato dal database
al momento dell'inserimento (`DEFAULT nextval`). Lo assegna il database e
non l'applicazione di proposito: una sequenza Postgres non salta e non
duplica nemmeno con due ordini creati nello stesso istante da due processi
diversi, che è esattamente la garanzia che serve a un numero d'ordine.

**Una sola sequenza per tutti i negozi.** Il cliente in "I miei Ordini"
vede insieme AliExpress, CJ e Shopify: se ogni negozio contasse per conto
suo esisterebbero tre "ordine 12" diversi, e al primo problema nessuno
saprebbe di quale si parla. `shop_order_number_seq` è condivisa, quindi
quando CJ e Shopify avranno il carrello basterà dare la stessa DEFAULT
alle loro tabelle.

Si parte da 1000 perché un "ordine 1" racconta al cliente quanti ordini
abbiamo ricevuto in tutto, e non è un'informazione da regalare.

Gli ordini già esistenti vengono numerati in ordine di creazione: sono
fatti loro, e rinumerarli in un altro modo renderebbe il numero inutile
proprio dove serve, cioè nel cercare un ordine vecchio.

Revision ID: a7e14b2c9f63
Revises: f6c32d9a4e57
Create Date: 2026-09-21 01:10:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7e14b2c9f63"
down_revision: Union[str, None] = "f6c32d9a4e57"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

START = 1000


def upgrade() -> None:
    op.execute(f"CREATE SEQUENCE IF NOT EXISTS shop_order_number_seq START WITH {START}")
    op.add_column("aliexpress_orders", sa.Column("number", sa.BigInteger(), nullable=True))
    # In ordine di creazione: il numero deve raccontare la cronologia vera.
    op.execute(
        f"""
        WITH ordered AS (
            SELECT id, row_number() OVER (ORDER BY created_at, id) AS rn FROM aliexpress_orders
        )
        UPDATE aliexpress_orders o
           SET number = {START - 1} + ordered.rn
          FROM ordered
         WHERE o.id = ordered.id
        """
    )
    # La sequenza riparte da dopo l'ultimo numero assegnato dal backfill.
    op.execute(
        f"""
        SELECT setval(
            'shop_order_number_seq',
            GREATEST({START - 1}, COALESCE((SELECT max(number) FROM aliexpress_orders), {START - 1}))
        )
        """
    )
    op.execute("ALTER TABLE aliexpress_orders ALTER COLUMN number SET DEFAULT nextval('shop_order_number_seq')")
    op.alter_column("aliexpress_orders", "number", nullable=False)
    op.create_unique_constraint("uq_aliexpress_orders_number", "aliexpress_orders", ["number"])


def downgrade() -> None:
    op.drop_constraint("uq_aliexpress_orders_number", "aliexpress_orders", type_="unique")
    op.drop_column("aliexpress_orders", "number")
    op.execute("DROP SEQUENCE IF EXISTS shop_order_number_seq")
