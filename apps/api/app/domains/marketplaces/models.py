"""Ciò che i negozi con carrello condividono a livello di schema.

Oggi una cosa sola: la sequenza dei numeri d'ordine.

Sta qui e non dentro un negozio perché è di tutti: se un secondo negozio
nascesse contando per conto suo esisterebbero due "ordine 1042" diversi, e
al primo problema nessuno saprebbe di quale si parla.

Il numero lo assegna il database (`server_default=nextval`), non
l'applicazione: una sequenza Postgres non salta e non duplica nemmeno con
due ordini creati nello stesso istante da processi diversi, che è
esattamente la garanzia che serve a un numero d'ordine.
"""

from sqlalchemy import Sequence

from app.core.db import Base

#: Da 1000: un "ordine 1" racconta al cliente quanti ordini abbiamo
#: ricevuto in tutto, e non è un'informazione da regalare.
SHOP_ORDER_NUMBER_START = 1000

SHOP_ORDER_NUMBER_SEQ = Sequence(
    "shop_order_number_seq", start=SHOP_ORDER_NUMBER_START, metadata=Base.metadata
)
