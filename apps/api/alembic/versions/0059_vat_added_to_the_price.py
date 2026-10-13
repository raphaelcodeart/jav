"""L'IVA si aggiunge al prezzo, non è più contenuta (Session 78).

Decisione dell'utente, dopo che gli era stato fatto presente che verso un
consumatore il Codice del Consumo (artt. 14-15) vuole il prezzo finale: il
prezzo esposto nei Marketplace è ora **l'imponibile**, e l'IVA si somma al
checkout. Su 17,90 il cliente paga 21,84 invece di 17,90.

Una colonna sola, `vat_mode`, sulle quattro tabelle degli ordini.

Serve perché le colonne che già ci sono cambiano significato: fino a ieri
`vat_amount_cents` era l'IVA **contenuta** in `amount_cents`, da oggi è
l'IVA **aggiunta** dentro `amount_cents`. Sullo stesso ordine da 17,90 la
prima vale 3,23 e la seconda 3,94: senza sapere quale delle due regole
valeva, ogni lettura di un ordine passato sarebbe un'ipotesi -- in fattura,
in Contabilità, in una email ristampata.

Gli ordini esistenti prendono `INCLUDED`, che è la verità di come sono
stati venduti, e **non vengono ricalcolati**: un ordine chiuso non si
riscrive (CLAUDE.md §5). Il default della colonna è `ADDED`, quindi ogni
ordine da qui in avanti nasce con la regola nuova senza che il codice debba
ricordarsene.

Nessun prezzo di catalogo cambia: `price_cents` resta quello che è, e da
imponibile diventa. Quello che cambia è quanto si somma sopra al checkout.

Revision ID: c9a37e15b402
Revises: b8f25c3d0a71
Create Date: 2026-09-21 10:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9a37e15b402"
down_revision: Union[str, None] = "b8f25c3d0a71"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ORDER_TABLES = ("imported_product_orders", "cj_orders", "shopify_orders", "aliexpress_orders")


def upgrade() -> None:
    for table in ORDER_TABLES:
        # server_default ADDED: i nuovi ordini nascono con la regola di oggi.
        op.add_column(
            table,
            sa.Column("vat_mode", sa.String(16), nullable=False, server_default="ADDED"),
        )
        # Gli ordini che c'erano gia' sono stati venduti a IVA inclusa, e
        # quella resta la loro verita'.
        op.execute(f"UPDATE {table} SET vat_mode = 'INCLUDED'")
        op.create_check_constraint(
            f"ck_{table}_vat_mode", table, "vat_mode IN ('INCLUDED', 'ADDED')"
        )


def downgrade() -> None:
    for table in ORDER_TABLES:
        op.drop_constraint(f"ck_{table}_vat_mode", table, type_="check")
        op.drop_column(table, "vat_mode")
