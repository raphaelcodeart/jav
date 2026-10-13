"""La spedizione AliExpress reale, con un minimo (Session 76).

Fino a qui la spedizione dei prodotti AliExpress era un forfait:
`shipping_flat_cents`, lo stesso importo per ogni ordine qualunque cosa
AliExpress chiedesse davvero. Il costo vero si sapeva già chiedere
(`aliexpress.ds.freight.query`, nel client dalla Session 71) ma serviva
solo a far scegliere il forfait all'amministratore: al checkout non lo
leggeva nessuno. Un articolo che costa 20 EUR di spedizione veniva quindi
venduto con 5,90 di spedizione, in perdita.

Da qui il campo cambia mestiere, e il nome con lui:

    shipping_flat_cents  ->  shipping_minimum_cents

Non è più quanto si paga, ma il **minimo** che si paga:

    spedizione addebitata = max(spedizione reale AliExpress, minimo)

Il minimo vale una volta per ordine, non per riga: tre articoli con 1,20
EUR di spedizione ciascuno fanno 3,60 di costo reale e 5,90 addebitati --
non 17,70.

Sull'ordine si congelano tre numeri invece di uno, perché "quanto ci è
costata" e "quanto l'abbiamo fatta pagare" sono due fatti diversi e il
margine di spedizione è la loro differenza:

- `supplier_shipping_cents`: quanto chiede AliExpress, in euro;
- `minimum_shipping_cents`: il minimo in vigore quel giorno;
- `shipping_cents` (già esistente): quanto ha pagato il cliente.

Lo stesso costo reale si congela anche **sulla riga**
(`aliexpress_order_items.supplier_shipping_cents`), perché il freight di
AliExpress si chiede per prodotto: è lì che il dato nasce, e sommarlo è
un'operazione nostra, non sua.

Le tre colonne nuove sono **nullable** e le righe esistenti restano a NULL.
NULL qui vuol dire "non rilevato", ed è la verità: quegli ordini sono stati
venduti quando il costo reale non lo chiedeva nessuno. Metterci uno zero
direbbe "la spedizione non ci è costata niente", che è falso, e
gonfierebbe il margine di ogni ordine passato.

Revision ID: f6c32d9a4e57
Revises: e5b21c8f3d46
Create Date: 2026-09-20 22:40:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f6c32d9a4e57"
down_revision: Union[str, None] = "e5b21c8f3d46"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Un rename, non una colonna nuova: il valore che l'amministratore ha già
    # configurato (5,90 per difetto) diventa il minimo senza che debba
    # ridigitarlo, ed è esattamente la semantica che assume.
    op.alter_column("aliexpress_settings", "shipping_flat_cents", new_column_name="shipping_minimum_cents")
    op.add_column("aliexpress_orders", sa.Column("supplier_shipping_cents", sa.BigInteger(), nullable=True))
    op.add_column("aliexpress_orders", sa.Column("minimum_shipping_cents", sa.BigInteger(), nullable=True))
    op.add_column("aliexpress_order_items", sa.Column("supplier_shipping_cents", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("aliexpress_order_items", "supplier_shipping_cents")
    op.drop_column("aliexpress_orders", "minimum_shipping_cents")
    op.drop_column("aliexpress_orders", "supplier_shipping_cents")
    op.alter_column("aliexpress_settings", "shipping_minimum_cents", new_column_name="shipping_flat_cents")
