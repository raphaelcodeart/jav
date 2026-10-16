"""Lo Shop -- «Fai la Spesa con Jav».

Il negozio con carrello, JavCash da spendere e mai da guadagnare, pagamento
con bonifico e IVA aggiunta al prezzo. I prodotti **non arrivano da un
fornitore**: li carica l'amministratore a mano, uno per uno.

Tabelle sue, come vuole `marketplaces/rules.py`: niente qui tocca
`catalog.products`, e spegnere questo negozio non disturba nessun altro.

**I produttori stanno in una tabella a parte.** Un'azienda produce molti
articoli, e scrivere i suoi dati dentro ogni prodotto vorrebbe dire
correggerli in venti posti quando cambia un indirizzo -- e ritrovarsi venti
versioni diverse della stessa azienda. Con una riga sola l'amministratore la
compila una volta e la sceglie da un elenco; il cliente la legge nella
scheda prodotto, ed è il motivo per cui questo negozio esiste: qui si sa chi
fa la merce.

Il prodotto **congela** il nome del produttore sull'ordine come congela il
proprio (vedi `JavMarketOrderItem`): un'azienda rinominata non deve
cambiare cosa dice un ordine di sei mesi fa.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin
from app.domains.marketplaces.models import SHOP_ORDER_NUMBER_SEQ

#: La chiave di questo negozio ovunque serva dirla: carrello, categorie,
#: etichette. "jav_market" e non "spesa": il nome che il cliente legge è
#: un'impostazione e può cambiare, la chiave no.
SHOP = "jav_market"

#: La spedizione la paga il cliente, oppure è già dentro il prezzo di
#: listino.
SHIPPING_MODES = ("CUSTOMER_PAYS", "INCLUDED")
PRODUCT_STATUSES = ("ACTIVE", "INACTIVE")
JAV_MARKET_ORDER_PAYMENT_METHODS = ("BANK_TRANSFER",)
MAX_QUANTITY = 10


class JavMarketSettings(UUIDPKMixin, TimestampMixin, Base):
    """Le impostazioni del negozio, una riga per organizzazione.

    Poche: non c'è un fornitore da collegare, né un cambio valuta, né un
    ricarico da applicare a un costo. Il prezzo lo scrive l'amministratore,
    ed è già quello di vendita."""

    __tablename__ = "jav_market_settings"
    __table_args__ = (UniqueConstraint("organization_id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    shipping_mode: Mapped[str] = mapped_column(String(16), default="CUSTOMER_PAYS")
    #: Quanto si addebita di spedizione, una volta per ordine. Qui è un
    #: importo e non un minimo: senza un fornitore da interrogare non
    #: esiste un costo reale da confrontare.
    shipping_flat_cents: Mapped[int] = mapped_column(Integer, default=0)
    shipping_days: Mapped[str | None] = mapped_column(String(32), nullable=True, default="3-5")
    #: Ottobre 2026 -- regole solo di questo negozio, decise dall'utente
    #: (80 € di minimo, spedizione 15 € gratis da 150 €). Entrambe si
    #: misurano sulla **merce IVA inclusa**: spedizione esclusa, prima dei
    #: JavCash (che sono un modo di pagare, non uno sconto). 0 = nessun
    #: minimo; NULL = nessuna spedizione gratuita.
    min_order_cents: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    free_shipping_threshold_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ship_to_country: Mapped[str] = mapped_column(String(2), default="IT")
    #: Un ordine pagato parte da solo verso l'azienda che
    #: produce la merce. Nasce spento: mandare una email a un'azienda vera è
    #: un'azione verso l'esterno, e la prima volta la si vuole guardare.
    auto_forward: Mapped[bool] = mapped_column(Boolean, default=False)
    #: Ottobre 2026 -- l'indirizzo da cui partono le email ai fornitori
    #: (es. info@...), che è anche il Reply-To e la copia nascosta: la
    #: risposta col tracking torna lì e la casella conserva ogni ordine
    #: mandato. NULL = il mittente predefinito dell'SMTP.
    supplier_email_from: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: La firma in fondo alla lettera al fornitore, testo semplice.
    supplier_email_signature: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class JavMarketProducer(UUIDPKMixin, TimestampMixin, Base):
    """L'azienda che produce la merce.

    Tabella sua e non campi sparsi sul prodotto: una stessa azienda fa più
    articoli, e i suoi dati si scrivono una volta. `name` è unico per
    organizzazione, così non nascono due schede della stessa azienda scritte
    in modo appena diverso."""

    __tablename__ = "jav_market_producers"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_jav_market_producers_name"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(160))
    #: Quello che il cliente legge nella scheda: chi sono, cosa fanno, dove.
    description: Mapped[str] = mapped_column(String(4000), default="")
    website_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    #: Dati di contatto e sede: servono all'amministrazione, non al cliente.
    vat_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)


class JavMarketProduct(UUIDPKMixin, TimestampMixin, Base):
    """Un prodotto del negozio, caricato a mano.

    Stessa forma di un prodotto importato da un fornitore -- nome,
    descrizione, foto, varianti, tetto JavCash -- perché al cliente deve
    comportarsi allo stesso modo. Quello che cambia è da dove vengono i
    dati: qui li scrive l'amministratore.

    `producer_id` è **nullable**: un prodotto può essere caricato prima di
    aver compilato la scheda dell'azienda, e obbligarlo bloccherebbe il
    lavoro invece di ordinarlo. Sulla scheda cliente il produttore si mostra
    solo quando c'è.
    """

    __tablename__ = "jav_market_products"
    __table_args__ = (
        CheckConstraint("credit_discount_percentage BETWEEN 0 AND 99", name="credit_percentage_range"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    #: Chi vende: un club (lo shop del club, lo gestisce la sua segreteria)
    #: o, NULL, JudoArteVida (lo shop unico di tutti i club, del superadmin).
    club_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clubs.id"), nullable=True, index=True
    )
    producer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jav_market_producers.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(8000), default="")
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    images: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    #: Quanta parte del prezzo si può pagare in JavCash. Mai il 100%: è la
    #: regola comune dei Marketplace (marketplaces/rules.py).
    credit_discount_percentage: Mapped[int] = mapped_column(Integer, default=30)
    #: Quanto ci costa la merce, se l'amministratore lo sa: serve solo al
    #: margine nel pannello, non si mostra mai al cliente.
    unit_cost_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)


class JavMarketVariant(UUIDPKMixin, TimestampMixin, Base):
    """Una variante vendibile: taglia, colore, formato.

    Un prodotto ne ha sempre almeno una, anche quando di varianti non ne
    ha: così il carrello, il preventivo e l'ordine puntano sempre a una
    variante e non devono distinguere due casi. Quella sola si chiama
    «Unica» e il cliente non la vede nemmeno."""

    __tablename__ = "jav_market_variants"
    __table_args__ = (
        CheckConstraint("price_cents > 0", name="price_positive"),
        UniqueConstraint("product_id", "sku", name="uq_jav_market_variants_sku"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jav_market_products.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(255), default="Unica")
    sku: Mapped[str | None] = mapped_column(String(128), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    price_cents: Mapped[int] = mapped_column(BigInteger)
    #: `None` = scorta non gestita, si vende sempre. Zero = esaurito.
    inventory: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class JavMarketOrder(UUIDPKMixin, TimestampMixin, Base):
    """Un ordine del negozio. «I miei Ordini», il pannello admin e la
    Contabilità lo mostrano nella stessa lista degli ordini del catalogo
    (CLAUDE.md §5).

    Le colonne di riga (prodotto, variante, quantità, prezzo unitario) non
    esistono qui: questo negozio nasce già multi-riga, quindi stanno tutte
    su `jav_market_order_items` e il denaro resta sulla testata."""

    __tablename__ = "jav_market_orders"
    __table_args__ = (
        CheckConstraint("credit_applied_cents >= 0", name="credit_applied_non_negative"),
        CheckConstraint("credit_applied_cents <= amount_cents", name="credit_applied_not_over_amount"),
        CheckConstraint("vat_mode IN ('INCLUDED', 'ADDED')", name="vat_mode"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    #: Chi vende (come per i prodotti): un ordine è di un venditore solo.
    club_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clubs.id"), nullable=True, index=True
    )
    customer_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    #: Per quale atleta della famiglia è il materiale (il judogi di chi?).
    #: Facoltativo: un genitore può comprare anche per sé, senza atleta.
    athlete_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("club_athletes.id"), nullable=True, index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    #: Il numero che legge il cliente, dalla sequenza condivisa da tutti i
    #: negozi: in "I miei Ordini" stanno nello stesso elenco.
    number: Mapped[int] = mapped_column(
        BigInteger, SHOP_ORDER_NUMBER_SEQ, server_default=SHOP_ORDER_NUMBER_SEQ.next_value(), unique=True
    )

    items_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    shipping_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    #: merce + IVA + spedizione.
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    credit_applied_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    bank_transfer_discount_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    #: L'IVA **aggiunta** alla merce, gia' dentro amount_cents, congelata
    #: alla creazione e mai ricalcolata (marketplaces/rules.py).
    vat_percentage: Mapped[int] = mapped_column(Integer, default=0)
    vat_amount_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    vat_mode: Mapped[str] = mapped_column(String(16), server_default="ADDED", default="ADDED")
    credit_debit_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wallet_transactions.id"), nullable=True
    )

    status: Mapped[str] = mapped_column(String(16), default="AWAITING_PAYMENT", index=True)
    payment_method: Mapped[str] = mapped_column(String(16), default="BANK_TRANSFER")
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    payment_proof_storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    payment_proof_original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_proof_uploaded_at: Mapped[datetime | None] = mapped_column(nullable=True)
    paid_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(nullable=True)
    cancelled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # --- Consegna ---
    recipient_name: Mapped[str] = mapped_column(String(128))
    recipient_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    address_line1: Mapped[str] = mapped_column(String(255))
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(128))
    province: Mapped[str] = mapped_column(String(64))
    postal_code: Mapped[str] = mapped_column(String(16))
    country_code: Mapped[str] = mapped_column(String(2), default="IT")
    shipping_days: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # --- Evasione, che qui è a mano ---
    #: Non c'è un fornitore a cui inoltrare: spedisce l'organizzazione, e
    #: l'amministratore segna quando parte e con quale tracking.
    fulfillment_status: Mapped[str] = mapped_column(String(16), default="NOT_SENT", index=True)
    #: Quando l'ordine è stato mandato alle aziende, chi lo ha
    #: mandato e cosa è andato storto. Un solo `forwarded_at` anche se le
    #: email sono più d'una: dice che il giro è stato fatto, non a chi --
    #: i destinatari sono le aziende delle righe, e stanno già lì.
    forwarded_at: Mapped[datetime | None] = mapped_column(nullable=True)
    forwarded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    forward_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tracking_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    tracking_company: Mapped[str | None] = mapped_column(String(128), nullable=True)
    shipped_at: Mapped[datetime | None] = mapped_column(nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(nullable=True)


class JavMarketOrderItem(UUIDPKMixin, TimestampMixin, Base):
    """Una riga d'ordine, con tutto quello che serve a rileggerla fra
    tre anni senza dipendere dal catalogo di oggi: nome del prodotto, della
    variante e **dell'azienda che lo produce**, prezzo unitario e tetto
    JavCash, tutti congelati."""

    __tablename__ = "jav_market_order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        UniqueConstraint("order_id", "variant_id", name="uq_jav_market_order_items_variant"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jav_market_orders.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("jav_market_products.id"))
    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("jav_market_variants.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price_cents: Mapped[int] = mapped_column(BigInteger)
    unit_cost_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    product_name: Mapped[str] = mapped_column(String(255))
    variant_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: Congelato come il resto: un'azienda rinominata non riscrive un ordine.
    producer_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    #: Il fornitore che deve preparare questa riga, congelato alla creazione
    #: (quello del prodotto o, se manca, della sua categoria: vedi
    #: `service.resolve_suppliers`). È la chiave con cui le righe di più
    #: ordini si raccolgono in una sola email al fornitore: spostare domani
    #: un prodotto su un'altra azienda non deve dirottare un ordine già fatto.
    producer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jav_market_producers.id"), nullable=True, index=True
    )
    #: L'email con cui questa riga è stata mandata al fornitore. NULL = ancora
    #: da mandare: è questo, e non un flag sull'ordine, a dire cosa resta da
    #: avvisare, perché un ordine con due fornitori può essere mandato a uno
    #: e non ancora all'altro. Si scrive solo dopo che l'email è partita.
    supplier_dispatch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jav_market_supplier_dispatches.id"), nullable=True, index=True
    )
    credit_discount_percentage: Mapped[int] = mapped_column(Integer, default=0)


#: Da dove è partita un'email al fornitore: dalla coda «Fornitori da
#: avvisare» (più ordini insieme, testo rivisto dall'amministratore), dal
#: pulsante sul singolo ordine, dall'invio automatico al pagamento, oppure
#: un invio fatto prima che esistesse questo storico (migrazione 0003).
DISPATCH_SOURCES = ("QUEUE", "ORDER", "AUTO", "LEGACY")


class JavMarketSupplierDispatch(UUIDPKMixin, TimestampMixin, Base):
    """Un'email partita verso un fornitore, con il testo esatto che è
    stato mandato.

    Esiste solo se l'email è partita davvero: un invio fallito non lascia
    una riga qui e non segna nessuna riga d'ordine, così quella merce resta
    nella coda e nessuno pensa che il fornitore la stia preparando. Le righe
    d'ordine che contiene puntano qui (`supplier_dispatch_id`)."""

    __tablename__ = "jav_market_supplier_dispatches"
    __table_args__ = (
        CheckConstraint(
            "source IN ('QUEUE', 'ORDER', 'AUTO', 'LEGACY')", name="source"
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    producer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jav_market_producers.id"), index=True
    )
    source: Mapped[str] = mapped_column(String(16))
    #: Destinatario, oggetto e testo come sono partiti: l'amministratore può
    #: averli corretti nell'anteprima, e la scheda del fornitore può cambiare.
    to_email: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    body_text: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime] = mapped_column()
    #: NULL per l'invio automatico al pagamento: non l'ha premuto nessuno.
    sent_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
