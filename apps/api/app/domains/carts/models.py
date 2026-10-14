"""Il carrello dello Shop.

Fino a qui ogni acquisto dello Shop nasceva e moriva dentro una finestra:
si apriva il prodotto, si sceglieva la variante e si pagava, un prodotto
per ordine. Il carrello separa le due cose -- cosa voglio comprare, e
quando lo pago -- come fa qualunque ecommerce.

**Un carrello per negozio, non uno solo.** Non è una limitazione tecnica
ma la forma dei quattro negozi: i tre Marketplace hanno indirizzo di
consegna, spedizione, IVA congelata e sconto bonifico, il catalogo interno
(Prodotti Partner e Offerte Jav) non ha nulla di tutto questo e ha invece
il «riscuoti subito cashback», che nei Marketplace è vietato
(marketplaces/rules.py). Righe con regole che si escludono a vicenda non
possono stare nello stesso ordine, quindi non stanno nello stesso
carrello. Il cliente però ne vede uno solo, diviso in sezioni: il totale
in cima è la somma, il pulsante di pagamento è per sezione.

`shop` dice di quale negozio è il carrello; la riga punta alla variante di
quel negozio con una colonna sua, non con un uuid generico. Sono quattro
colonne nullable di cui esattamente una valorizzata (il vincolo
`exactly_one_reference` lo impone): costa una colonna in più per ogni
negozio nuovo, e in cambio il database conserva davvero le chiavi esterne
-- una variante cancellata si porta via le righe di carrello che la
citano, invece di lasciare un uuid che non punta più a niente.

**Nel carrello non ci sono prezzi.** Solo cosa e quanto. Il prezzo si
calcola al checkout, dal server, sui listini di quel momento, e si congela
sull'ordine: un prodotto messo nel carrello a marzo e pagato ad aprile si
paga al prezzo di aprile, che è anche l'unico che il cliente vede prima di
confermare. È la regola «ogni calcolo economico è server-side» di
CLAUDE.md §5, applicata alla lettera.
"""

import uuid

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin

#: I negozi che hanno un carrello. JAV_MARKET è lo Shop con catalogo scritto
#: dall'amministratore; CATALOG è il catalogo interno, dove "Prodotti Partner" e "Offerte Jav"
#: sono due schede della stessa tabella (catalog.products, categorie PARTNER
#: e DROPSHIPPING) e quindi un carrello solo: stesso ordine, stesso
#: pagamento, nessun motivo per farli pagare due volte.
CART_SHOPS = ("jav_market", "catalog")

#: Quante unità della stessa variante una riga può portare. Non è una regola
#: di magazzino -- quella la dà il fornitore al checkout -- ma il limite che
#: impedisce a un `quantity` sbagliato di diventare un ordine da mille pezzi.
MAX_ITEM_QUANTITY = 99


class Cart(UUIDPKMixin, TimestampMixin, Base):
    """Il carrello aperto di un cliente su un negozio. Ne esiste al massimo
    uno per (cliente, negozio): il vincolo UNIQUE è ciò che rende
    l'aggiunta al carrello idempotente senza flag applicativi, come vuole
    CLAUDE.md §5. Non viene mai cancellato dopo l'acquisto, si svuota: così
    l'id resta stabile e due richieste simultanee non ne creano due."""

    __tablename__ = "carts"
    __table_args__ = (
        UniqueConstraint("customer_user_id", "shop", name="uq_carts_customer_shop"),
        CheckConstraint(
            "shop IN ('jav_market', 'catalog')",
            name="shop",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    customer_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    shop: Mapped[str] = mapped_column(String(16))


class CartItem(UUIDPKMixin, TimestampMixin, Base):
    """Una riga di carrello: una variante e quante unità.

    `ondelete="CASCADE"` su ogni riferimento è voluto: se un amministratore
    cancella un prodotto o una variante, le righe di carrello che la citano
    spariscono con lei. Un ordine già fatto non si tocca -- quello ha i suoi
    dati congelati -- ma un carrello che rimanda a qualcosa che non esiste
    più è solo un errore in attesa di succedere al checkout.
    """

    __tablename__ = "cart_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint(f"quantity <= {MAX_ITEM_QUANTITY}", name="quantity_max"),
        # L'arco esclusivo: una riga appartiene a un negozio solo. Senza
        # questo vincolo una riga potrebbe citare insieme una variante dello
        # Shop e un prodotto del catalogo, e il checkout non saprebbe quale
        # ordinare.
        CheckConstraint(
            "num_nonnulls(jav_market_variant_id, product_version_id) = 1",
            name="exactly_one_reference",
        ),
        # Una riga per variante: aggiungere di nuovo lo stesso articolo
        # aumenta la quantità, non crea un doppione. Vincoli
        # separati perché un UNIQUE su colonne nullable in PostgreSQL non
        # vincola le righe che le lasciano NULL.
        UniqueConstraint("cart_id", "jav_market_variant_id", name="uq_cart_items_jav_market_variant"),
        UniqueConstraint("cart_id", "product_version_id", name="uq_cart_items_product_version"),
    )

    cart_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("carts.id", ondelete="CASCADE"), index=True
    )
    quantity: Mapped[int] = mapped_column(BigInteger, default=1)

    # --- L'arco esclusivo: esattamente una di queste due ---
    jav_market_variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jav_market_variants.id", ondelete="CASCADE"), nullable=True
    )
    #: Il catalogo interno non ha varianti: la "variante" è la versione di
    #: prodotto, che è anche ciò che orders.Order congela già oggi.
    product_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_versions.id", ondelete="CASCADE"), nullable=True
    )
