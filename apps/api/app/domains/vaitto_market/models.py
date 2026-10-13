"""Marketplace 6 -- «Marketplace VAITTO» (Session 88).

Clone di «Market Kappa» (`kappa_market`), con tabelle sue come ogni
Marketplace (`marketplaces/rules.py`): spegnerlo non tocca nessun altro
negozio. Al cliente si comporta come gli altri -- carrello, JavCash da
spendere e mai da guadagnare, IVA aggiunta al prezzo.

Quello che ha in più è il **rifornimento da Vaitto** (vaitto.com, moda di
lusso in dropshipping): il catalogo arriva dal feed «universal.csv» di
Vaitto, letto dall'URL con la chiave API ogni tre ore oppure caricato a mano
come file CSV. Una riga del feed è una variante (taglia × colore);
`product_id` la raggruppa in un prodotto.

Scelte dell'utente, che il codice rispetta:

- **tutto il catalogo si importa, ma spento**: un prodotto nuovo nasce
  INACTIVE e l'amministratore accende per marca, per categoria o uno a uno;
- **il prezzo è il costo all'ingrosso più il nostro ricarico**
  (`markup_percentage` sulle impostazioni, sovrascrivibile per prodotto),
  non il «retail» suggerito da Vaitto; il «compare_at» di Vaitto resta come
  prezzo di listino da mostrare barrato;
- **gli ordini non partono da soli**: nessuna API d'ordine, l'ordine pagato
  resta nel pannello con SKU, EAN e indirizzo congelati sulle righe, e
  l'amministratore lo inserisce su vaitto.com.

L'import aggiorna solo ciò che decide Vaitto (costo, scorte, disponibilità,
listino, foto) e mai ciò che decide l'amministratore (nome, descrizione,
acceso/spento, JavCash, ricarico del prodotto, prezzo messo a mano).

Le «aziende produttrici» del clone qui sono le **marche** del feed.
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
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin
from app.domains.marketplaces.models import SHOP_ORDER_NUMBER_SEQ

#: La chiave di questo negozio ovunque serva dirla: carrello, categorie,
#: etichette. "vaitto_market" e non "vaitto": il nome che il cliente legge è
#: un'impostazione e può cambiare, la chiave no.
SHOP = "vaitto_market"

#: Come per gli altri negozi: la spedizione la paga il cliente, oppure è
#: già dentro il prezzo di listino.
SHIPPING_MODES = ("CUSTOMER_PAYS", "INCLUDED")
PRODUCT_STATUSES = ("ACTIVE", "INACTIVE")
VAITTO_MARKET_ORDER_PAYMENT_METHODS = ("BANK_TRANSFER", "CARD")
MAX_QUANTITY = 10


class VaittoMarketSettings(UUIDPKMixin, TimestampMixin, Base):
    """Le impostazioni del negozio, una riga per organizzazione.

    Molte meno degli altri tre: non c'è un fornitore da collegare, né un
    cambio valuta, né un ricarico da applicare a un costo. Il prezzo lo
    scrive l'amministratore, ed è già quello di vendita."""

    __tablename__ = "vaitto_market_settings"
    __table_args__ = (
        UniqueConstraint("organization_id"),
        CheckConstraint("credit_percentage BETWEEN 0 AND 99", name="credit_percentage_range"),
        CheckConstraint("credit_mode IN ('FIXED', 'MARGIN')", name="credit_mode"),
        CheckConstraint("credit_margin_share BETWEEN 0 AND 100", name="credit_margin_share_range"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    shipping_mode: Mapped[str] = mapped_column(String(16), default="CUSTOMER_PAYS")
    #: Quanto si addebita di spedizione, una volta per ordine. Qui è un
    #: importo e non un minimo: senza un fornitore da interrogare non
    #: esiste un costo reale da confrontare (a differenza di AliExpress).
    shipping_flat_cents: Mapped[int] = mapped_column(Integer, default=0)
    shipping_days: Mapped[str | None] = mapped_column(String(32), nullable=True, default="3-5")
    ship_to_country: Mapped[str] = mapped_column(String(2), default="IT")
    #: Session 80 -- un ordine pagato parte da solo verso l'azienda che
    #: produce la merce. Nasce spento: mandare una email a un'azienda vera è
    #: un'azione verso l'esterno, e la prima volta la si vuole guardare.
    auto_forward: Mapped[bool] = mapped_column(Boolean, default=False)
    # --- Il feed di Vaitto (Session 88) ---
    #: L'URL del feed «universal.csv», che contiene la chiave API: non torna
    #: mai al browser (solo «configurato» e le ultime cifre), come gli altri
    #: segreti dei fornitori.
    feed_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    #: Rilegge il feed da solo ogni tre ore.
    auto_import: Mapped[bool] = mapped_column(Boolean, default=True)
    #: Il nostro ricarico, in percentuale, sopra il prezzo suggerito da Vaitto
    #: (dalla Session 88; prima era sul costo). Di norma 0: si vende al
    #: prezzo di Vaitto.
    markup_percentage: Mapped[int] = mapped_column(Integer, default=0)
    #: Session 88: quanta parte del prezzo si paga in JavCash, per tutti i
    #: prodotti del negozio salvo quelli personalizzati a mano
    #: (`VaittoMarketProduct.credit_locked`). Mai 100: la regola comune.
    credit_percentage: Mapped[int] = mapped_column(Integer, default=30)
    #: Come si decide la percentuale JavCash di ogni prodotto (Session 88):
    #: FIXED = `credit_percentage` per tutti; MARGIN = una quota del nostro
    #: guadagno su quel prodotto (prezzo al cliente − costo), cioè
    #: `credit_margin_share`% del margine in percentuale del prezzo.
    credit_mode: Mapped[str] = mapped_column(String(16), default="FIXED")
    credit_margin_share: Mapped[int] = mapped_column(Integer, default=50)
    #: Session 88, formula dell'utente: il prezzo di Vaitto al cliente (il
    #: prezzo del marchio, «Sell at brand RRP») ha già l'IVA dentro. Allora al
    #: checkout non si aggiunge niente -- si scorpora -- e il nostro costo si
    #: confronta con il prezzo dopo averci messo sopra spedizione e IVA.
    prices_include_vat: Mapped[bool] = mapped_column(Boolean, default=True)
    #: Quanto ci costa spedire un prodotto (5 € di norma): entra solo nel
    #: calcolo del guadagno, non nel prezzo al cliente.
    shipping_cost_cents: Mapped[int] = mapped_column(Integer, default=500)
    last_import_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_import_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_import_error: Mapped[str | None] = mapped_column(String(500), nullable=True)


class VaittoMarketProducer(UUIDPKMixin, TimestampMixin, Base):
    """L'azienda che produce la merce.

    Tabella sua e non campi sparsi sul prodotto: una stessa azienda fa più
    articoli, e i suoi dati si scrivono una volta. `name` è unico per
    organizzazione, così non nascono due schede della stessa azienda scritte
    in modo appena diverso."""

    __tablename__ = "vaitto_market_producers"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_vaitto_market_producers_name"),)

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


class VaittoMarketProduct(UUIDPKMixin, TimestampMixin, Base):
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

    __tablename__ = "vaitto_market_products"
    __table_args__ = (
        CheckConstraint("credit_discount_percentage BETWEEN 0 AND 99", name="credit_percentage_range"),
        # Un prodotto del feed una volta sola: è ciò che rende l'import
        # rilanciabile senza doppioni.
        UniqueConstraint("organization_id", "vaitto_product_id", name="uq_vaitto_market_products_vaitto_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    producer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vaitto_market_producers.id"), nullable=True, index=True
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
    # --- Dal feed Vaitto (Session 88); NULL su un prodotto caricato a mano ---
    vaitto_product_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    category_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subcategory: Mapped[str | None] = mapped_column(String(64), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(16), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    #: Il ricarico di questo prodotto, se diverso da quello del negozio.
    markup_percentage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Il prodotto non c'era nell'ultimo feed: nessuna variante è comprabile.
    missing_from_feed: Mapped[bool] = mapped_column(Boolean, default=False)
    #: La percentuale JavCash l'ha scelta l'amministratore per questo
    #: prodotto: cambiare quella del negozio non la tocca.
    credit_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(nullable=True)


class VaittoMarketVariant(UUIDPKMixin, TimestampMixin, Base):
    """Una variante vendibile: taglia, colore, formato.

    Un prodotto ne ha sempre almeno una, anche quando di varianti non ne
    ha: così il carrello, il preventivo e l'ordine puntano sempre a una
    variante e non devono distinguere due casi. Quella sola si chiama
    «Unica» e il cliente non la vede nemmeno."""

    __tablename__ = "vaitto_market_variants"
    __table_args__ = (
        CheckConstraint("price_cents > 0", name="price_positive"),
        UniqueConstraint("product_id", "sku", name="uq_vaitto_market_variants_sku"),
        UniqueConstraint("product_id", "vaitto_variant_id", name="uq_vaitto_market_variants_vaitto_id"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vaitto_market_products.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(255), default="Unica")
    sku: Mapped[str | None] = mapped_column(String(128), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    price_cents: Mapped[int] = mapped_column(BigInteger)
    #: `None` = scorta non gestita, si vende sempre. Zero = esaurito.
    inventory: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # --- Dal feed Vaitto (Session 88) ---
    vaitto_variant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: Il costo all'ingrosso («wholesale_price»): la base del nostro prezzo.
    cost_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    #: Il prezzo di listino («compare_at_price»), da mostrare barrato.
    compare_at_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    #: Il prezzo di vendita suggerito da Vaitto («retail_price», già con il
    #: loro ricarico): dalla Session 88 è la base del nostro prezzo, e il
    #: nostro ricarico -- 0 di norma -- si aggiunge sopra.
    suggested_price_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    #: Vaitto la vende ancora (è nel feed e non è «out of stock»).
    available_in_store: Mapped[bool] = mapped_column(Boolean, default=True)
    #: Il prezzo l'ha scritto l'amministratore: l'import non lo ricalcola.
    price_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    #: Il prezzo al cliente non copre costo + spedizione + IVA: la variante
    #: non si vende (decisione dell'utente), e torna da sola se i prezzi
    #: cambiano. Ricalcolato insieme alla percentuale JavCash.
    below_cost: Mapped[bool] = mapped_column(Boolean, default=False)


class VaittoMarketOrder(UUIDPKMixin, TimestampMixin, Base):
    """Un ordine del negozio. Stessa forma degli altri tre, perché la
    gestione è unificata: «I miei Ordini», il pannello admin e la
    Contabilità mostrano una lista sola (CLAUDE.md §5).

    Le colonne di riga (prodotto, variante, quantità, prezzo unitario) non
    esistono qui: questo negozio nasce già multi-riga, quindi stanno tutte
    su `vaitto_market_order_items` e il denaro resta sulla testata."""

    __tablename__ = "vaitto_market_orders"
    __table_args__ = (
        CheckConstraint("credit_applied_cents >= 0", name="credit_applied_non_negative"),
        CheckConstraint("credit_applied_cents <= amount_cents", name="credit_applied_not_over_amount"),
        CheckConstraint("vat_mode IN ('INCLUDED', 'ADDED')", name="vat_mode"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    customer_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
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
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
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
    #: Session 80 -- quando l'ordine è stato mandato alle aziende, chi lo ha
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


class VaittoMarketOrderItem(UUIDPKMixin, TimestampMixin, Base):
    """Una riga d'ordine, con tutto quello che serve a rileggerla fra
    tre anni senza dipendere dal catalogo di oggi: nome del prodotto, della
    variante e **dell'azienda che lo produce**, prezzo unitario e tetto
    JavCash, tutti congelati."""

    __tablename__ = "vaitto_market_order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        UniqueConstraint("order_id", "variant_id", name="uq_vaitto_market_order_items_variant"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vaitto_market_orders.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("vaitto_market_products.id"))
    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("vaitto_market_variants.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price_cents: Mapped[int] = mapped_column(BigInteger)
    unit_cost_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    product_name: Mapped[str] = mapped_column(String(255))
    variant_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: Congelato come il resto: un'azienda rinominata non riscrive un ordine.
    producer_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    #: Session 88: quello che serve per inserire l'ordine su vaitto.com,
    #: congelato come il resto -- il feed di domani può non averlo più.
    supplier_sku: Mapped[str | None] = mapped_column(String(128), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    supplier_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    credit_discount_percentage: Mapped[int] = mapped_column(Integer, default=0)
