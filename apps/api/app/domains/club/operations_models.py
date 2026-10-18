"""La gestione del club fuori dalle quote: gli ordini di judogi, le pulizie
della palestra, i compensi dei treinadores esterni, l'archivio dei
relatori e i documenti del club. Specifica: docs/club-portal.md, "Gestione".

Il denaro di queste righe passa dai posti di sempre: un judogi si paga con
una quota `EQUIPMENT` (e quindi con la stessa prova di pagamento di tutto il
resto); pulizie e compensi, quando si pagano, diventano una spesa
(`club_expenses`, `expense_id`). Qui resta solo ciò che è loro: che cosa,
quante ore, chi ha firmato.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, SmallInteger, String,
    Text, UniqueConstraint,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin, utcnow


def _in(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


#: I judogi che i club ordinano per i loro atleti.
KIMONO_TYPES = ("FIJ_APPROVED", "TRAINING", "SEMI_COMPETITION", "COMPETITION_NOT_APPROVED")
EQUIPMENT_ORDER_STATUSES = ("PENDING", "IN_PREPARATION", "DELIVERED", "CANCELLED")
#: I colori del listino dei judogi (club/judogi.py), con il nome che finisce
#: sull'ordine: obligations.py riconosce il colore da quel nome.
JUDOGI_COLORS = ("WHITE", "BLUE", "PINK", "WHITE_PINK_STRIPES")
#: La lista dei desideri dell'atleta minorenne: un prodotto dello Shop o un
#: judogi configurato con il calcolatore.
WISHLIST_KINDS = ("PRODUCT", "JUDOGI")
#: Che cosa ordina un ordine del club (e porta una riga del carrello della
#: Loja): un judogi del listino o un prodotto dello shop del club.
EQUIPMENT_ORDER_KINDS = ("JUDOGI", "PRODUCT")
#: Da dove viene: un ordine vero, o un judogi che l'atleta aveva già e che la
#: segreteria o il treinador hanno messo nel suo armadio.
EQUIPMENT_ORDER_ORIGINS = ("ORDER", "MANUAL")
#: Perché un judogi esce dall'armadio dell'atleta.
JUDOGI_RETIRE_REASONS = ("TRADED_IN", "OUTGROWN", "WORN_OUT", "LOST")
WISHLIST_STATUSES = ("OPEN", "ORDERED", "DISMISSED")
EXTERNAL_COACH_FEE_STATUSES = ("PENDING", "PAID", "PARTIAL", "EXEMPT")
REPORT_KINDS = ("ACTIVITIES",)
#: I documenti del club: dichiarazioni, affiliazione/rivalidazione alla
#: federazione, atas (verbali di assemblea e direzione), certidões delle
#: Finanze e della Segurança Social, certificazioni sportive (IPDJ, utilità
#: pubblica), assicurazioni, statuto.
CLUB_DOCUMENT_CATEGORIES = (
    "DECLARATION", "FEDERATION", "MINUTES", "TAX", "SOCIAL_SECURITY", "SPORTS", "INSURANCE", "STATUTES", "OTHER",
)


class ClubEquipmentOrder(UUIDPKMixin, TimestampMixin, Base):
    """Un ordine della Loja del club: un judogi (`kind` JUDOGI: tipo, marca,
    colore, taglia e il nome da ricamare) o un prodotto dello shop del club
    (`kind` PRODUCT: la variante, il nome se il prodotto lo vuole). Ognuno è
    un ordine a sé, anche quando nasce dallo stesso carrello: la segreteria
    lo prepara e lo consegna da solo. Il prezzo diventa la quota `EQUIPMENT`
    dell'atleta (`fee_id`), una per ordine.

    I judogi consegnati e non ritirati sono l'armadio dell'atleta (i judogi
    che ha), che la segreteria e il treinador guardano prima delle gare; un
    judogi che aveva già ci entra come `origin` MANUAL, senza prezzo."""

    __tablename__ = "club_equipment_orders"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_in(EQUIPMENT_ORDER_KINDS)})", name="kind"),
        CheckConstraint(f"origin IN ({_in(EQUIPMENT_ORDER_ORIGINS)})", name="origin"),
        CheckConstraint(f"kimono_type IN ({_in(KIMONO_TYPES)})", name="kimono_type"),
        CheckConstraint(f"status IN ({_in(EQUIPMENT_ORDER_STATUSES)})", name="status"),
        CheckConstraint(f"retired_reason IN ({_in(JUDOGI_RETIRE_REASONS)})", name="retired_reason"),
        CheckConstraint("size_cm BETWEEN 80 AND 220", name="size_range"),
        CheckConstraint("price_cents IS NULL OR price_cents >= 0", name="price_non_negative"),
        CheckConstraint("quantity >= 1", name="quantity_positive"),
        CheckConstraint(
            "kind <> 'JUDOGI' OR (kimono_type IS NOT NULL AND color IS NOT NULL AND brand IS NOT NULL"
            " AND size_cm IS NOT NULL AND kimono_name IS NOT NULL)",
            name="judogi_fields",
        ),
        CheckConstraint("kind <> 'PRODUCT' OR product_name IS NOT NULL", name="product_fields"),
        # Due clic su «Encomendar» non fanno due judogi: lo stesso judogi per
        # lo stesso atleta può essere in attesa una volta sola.
        Index(
            "uq_club_equipment_orders_pending_same", "athlete_id", "kimono_type", "color", "brand", "size_cm",
            unique=True, postgresql_where=sql_text("status = 'PENDING'"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    athlete_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("club_athletes.id"), index=True)
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(8), default="JUDOGI", server_default="JUDOGI")
    origin: Mapped[str] = mapped_column(String(8), default="ORDER", server_default="ORDER")
    #: Il nome da ricamare (sotto i 13 anni solo il nome proprio); per un
    #: prodotto, il nome da stampare se il prodotto lo chiede.
    kimono_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    kimono_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    color: Mapped[str | None] = mapped_column(String(40), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(60), nullable=True)
    size_cm: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    #: Il prezzo fissato dalla segreteria (con la personalizzazione e
    #: l'eventuale permuta); NULL finché non lo fissa.
    price_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    #: Il judogi usato restituito, se c'è (tipo, colore, marca, taglia, valore;
    #: `owned_order_id` se è uno dell'armadio, che esce alla consegna).
    trade_in: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    internal_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", server_default="PENDING", index=True)
    fee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("club_fees.id"), nullable=True, unique=True
    )
    delivered_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    # --- Il conto del calcolatore (club/judogi.py), congelato all'ordine:
    # listino + personalizzazione − permuta = price_cents. NULL negli ordini
    # nati prima del calcolatore (importati dal gestionale vecchio). ---
    base_price_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    customization_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    trade_in_discount_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    #: Il codice del colore del listino (JUDOGI_COLORS); `color` ne è il nome.
    color_code: Mapped[str | None] = mapped_column(String(24), nullable=True)
    # --- Un prodotto dello shop del club, congelato all'ordine come le righe
    # degli ordini dello Shop: il nome e il prezzo restano quelli di allora. ---
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jav_market_products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jav_market_variants.id", ondelete="SET NULL"), nullable=True
    )
    product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    variant_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[int] = mapped_column(SmallInteger, default=1, server_default="1")
    unit_price_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # --- L'armadio: quando un judogi non c'è più (restituito con la permuta,
    # piccolo, rovinato, perso). ---
    retired_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    retired_reason: Mapped[str | None] = mapped_column(String(16), nullable=True)


class ClubJudogiPrice(UUIDPKMixin, TimestampMixin, Base):
    """Il listino dei judogi del club: una riga per tipo, marca, colore e
    taglia. È un dato che la segreteria modifica, non un elenco nel codice
    (il calcolatore del gestionale vecchio aveva i prezzi scritti in PHP).
    Il prezzo è quello del judogi; la personalizzazione obbligatoria si
    aggiunge sopra (Club.settings["judogi"])."""

    __tablename__ = "club_judogi_prices"
    __table_args__ = (
        UniqueConstraint("club_id", "kimono_type", "brand", "color", "size_cm", name="uq_club_judogi_prices_item"),
        CheckConstraint(f"kimono_type IN ({_in(KIMONO_TYPES)})", name="kimono_type"),
        CheckConstraint(f"color IN ({_in(JUDOGI_COLORS)})", name="color"),
        CheckConstraint("size_cm BETWEEN 80 AND 220", name="size_range"),
        CheckConstraint("price_cents >= 0", name="price_non_negative"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    kimono_type: Mapped[str] = mapped_column(String(24))
    brand: Mapped[str] = mapped_column(String(60))
    color: Mapped[str] = mapped_column(String(24))
    size_cm: Mapped[int] = mapped_column(SmallInteger)
    price_cents: Mapped[int] = mapped_column(BigInteger)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=sql_text("true"))


class ClubWishlistItem(UUIDPKMixin, TimestampMixin, Base):
    """Un desiderio dell'atleta minorenne: vede lo Shop e il calcolatore dei
    judogi ma non compra; mette un prodotto (o un judogi configurato) nella
    sua lista e il titolare riceve la notifica. Il titolare lo trasforma in
    un ordine vero (ricalcolato sul server: `config` serve solo a mostrarlo)
    o lo rifiuta."""

    __tablename__ = "club_wishlist_items"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_in(WISHLIST_KINDS)})", name="kind"),
        CheckConstraint(f"status IN ({_in(WISHLIST_STATUSES)})", name="status"),
        CheckConstraint(
            "(kind = 'PRODUCT' AND product_id IS NOT NULL) OR (kind = 'JUDOGI' AND config IS NOT NULL)",
            name="target",
        ),
        # Lo stesso prodotto aperto una volta sola per atleta; un solo judogi
        # desiderato alla volta (uno nuovo sostituisce il precedente).
        Index(
            "uq_club_wishlist_items_open_product", "athlete_id", "product_id",
            unique=True, postgresql_where=sql_text("status = 'OPEN' AND kind = 'PRODUCT'"),
        ),
        Index(
            "uq_club_wishlist_items_open_judogi", "athlete_id",
            unique=True, postgresql_where=sql_text("status = 'OPEN' AND kind = 'JUDOGI'"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    athlete_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("club_athletes.id", ondelete="CASCADE"), index=True
    )
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(8))
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jav_market_products.id", ondelete="CASCADE"), nullable=True
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jav_market_variants.id", ondelete="SET NULL"), nullable=True
    )
    #: Il judogi scelto (tipo, colore, marca, taglia, permuta) e il conto
    #: visto dall'atleta: solo per mostrarlo, l'ordine si ricalcola.
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="OPEN", server_default="OPEN", index=True)
    #: L'ordine nato dal desiderio (judogi o Shop), quando il titolare compra.
    equipment_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("club_equipment_orders.id", ondelete="SET NULL"), nullable=True
    )
    jav_market_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jav_market_orders.id", ondelete="SET NULL"), nullable=True
    )
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ClubCleaningLog(UUIDPKMixin, TimestampMixin, Base):
    """Le ore di pulizia della palestra, firmate da chi le ha fatte. Il
    totale si calcola sul server (ore × €/ora) e si congela. La firma è
    un'immagine PNG nel bucket privato, non una stringa nel database."""

    __tablename__ = "club_cleaning_logs"
    __table_args__ = (
        CheckConstraint("hours > 0", name="hours_positive"),
        CheckConstraint("hourly_rate_cents > 0", name="rate_positive"),
        CheckConstraint("total_cents >= 0", name="total_non_negative"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    performed_at: Mapped[datetime] = mapped_column(index=True)
    person_name: Mapped[str] = mapped_column(String(150))
    hours: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    hourly_rate_cents: Mapped[int] = mapped_column(BigInteger)
    total_cents: Mapped[int] = mapped_column(BigInteger)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    signature_storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    paid_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: La spesa nata quando è stata pagata.
    expense_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("club_expenses.id"), nullable=True, unique=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class ClubExternalCoachFee(UUIDPKMixin, TimestampMixin, Base):
    """Il compenso del mese di un treinador esterno che usa la palestra o
    allena per il club: ore feriali, ore di weekend, allievi. Il totale lo
    calcola il server con le tariffe della riga (default del club) e lo
    congela."""

    __tablename__ = "club_external_coach_fees"
    __table_args__ = (
        CheckConstraint(f"status IN ({_in(EXTERNAL_COACH_FEE_STATUSES)})", name="status"),
        CheckConstraint("weekday_hours >= 0 AND weekend_hours >= 0 AND students >= 0", name="quantities_non_negative"),
        CheckConstraint("total_cents >= 0", name="total_non_negative"),
        CheckConstraint("paid_cents IS NULL OR paid_cents >= 0", name="paid_non_negative"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    coach_name: Mapped[str] = mapped_column(String(150))
    #: Il mese di riferimento (il primo del mese).
    month: Mapped[date] = mapped_column(Date, index=True)
    weekday_hours: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0)
    weekday_rate_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    weekend_hours: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0)
    weekend_rate_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    students: Mapped[int] = mapped_column(Integer, default=0)
    per_student_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    total_cents: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(10), default="PENDING", server_default="PENDING")
    paid_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    paid_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    expense_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("club_expenses.id"), nullable=True, unique=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class ClubReport(UUIDPKMixin, TimestampMixin, Base):
    """Un relatório generato (PDF nel bucket privato), con i parametri per
    rigenerarlo uguale o corretto."""

    __tablename__ = "club_reports"
    __table_args__ = (CheckConstraint(f"kind IN ({_in(REPORT_KINDS)})", name="kind"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    storage_key: Mapped[str] = mapped_column(String(500))
    download_name: Mapped[str] = mapped_column(String(200))
    #: I testi liberi e le opzioni con cui è stato generato.
    params: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=sql_text("'{}'::jsonb"))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class ClubDocument(UUIDPKMixin, TimestampMixin, Base):
    """Un documento del club (non di un atleta): la certidão delle Finanze,
    l'ata dell'assemblea, la rivalidazione alla federazione. Il file sta nel
    bucket privato (`storage_key`) e si apre con un URL presigned; lo vedono
    la segreteria del club e la piattaforma. Con una scadenza, il club è
    avvisato quando manca poco."""

    __tablename__ = "club_documents"
    __table_args__ = (
        CheckConstraint(f"category IN ({_in(CLUB_DOCUMENT_CATEGORIES)})", name="category"),
        CheckConstraint("expires_on IS NULL OR issued_on IS NULL OR expires_on >= issued_on", name="date_range"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    category: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    issued_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_key: Mapped[str] = mapped_column(String(500))
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    #: Visibile nella bacheca di atleti e famiglie del club (un regolamento,
    #: il calendario della stagione): lo decide la segreteria, documento per
    #: documento. Spento, lo vede solo lo staff.
    shared_with_members: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sql_text("false")
    )


class ClubNewsPost(UUIDPKMixin, TimestampMixin, Base):
    """Una notizia del club nella bacheca di atleti e famiglie, come un post:
    titolo, testo, una foto, un video (YouTube, Vimeo) o un link. La scrive la
    segreteria; si vede solo nell'area riservata, non sul sito pubblico. La
    foto sta nel bucket dei media come quelle della pagina del club."""

    __tablename__ = "club_news_posts"
    __table_args__ = (
        CheckConstraint("audience IN ('CLUB', 'NETWORK')", name="audience"),
        # Un post della piattaforma (club_id NULL) è sempre per tutto il circuito.
        CheckConstraint("club_id IS NOT NULL OR audience = 'NETWORK'", name="platform_is_network"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    #: NULL = un post di JudoArteVida (l'amministratore), per tutto il circuito.
    club_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True, nullable=True)
    #: CLUB: solo per i soci del club; NETWORK: per tutti i club del circuito.
    audience: Mapped[str] = mapped_column(String(8), default="CLUB", server_default="CLUB")
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    video_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    link_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    #: In cima alla bacheca, prima delle altre.
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sql_text("false"))
    #: Spento è una bozza: la vede solo la segreteria.
    published: Mapped[bool] = mapped_column(Boolean, default=True, server_default=sql_text("true"))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class ClubNewsLike(Base):
    """Un «mi piace» a un post della bacheca: uno per persona."""

    __tablename__ = "club_news_likes"

    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("club_news_posts.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)



#: Che cosa il club ha pagato per un atleta.
SUPPORT_CATEGORIES = ("TRANSPORT", "MATERIAL", "COMPETITION", "EXAM", "TRAINING_CAMP", "OTHER")


class ClubAthleteSupport(UUIDPKMixin, TimestampMixin, Base):
    """Un costo che il club ha pagato per un atleta (trasporto, materiale,
    iscrizione a una gara, esame, stage...): l'aiuto del club, visibile
    alla famiglia. Nel wallet della famiglia diventa una ricarica seguita
    subito dall'addebito del costo (club/support.py): il saldo non cambia,
    ma lo storico dice quando e quanto il club l'ha aiutata."""

    __tablename__ = "club_athlete_supports"
    __table_args__ = (
        CheckConstraint(f"category IN ({_in(SUPPORT_CATEGORIES)})", name="category"),
        CheckConstraint("amount_cents > 0", name="amount_positive"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    athlete_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("club_athletes.id"), index=True)
    category: Mapped[str] = mapped_column(String(16))
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    paid_on: Mapped[date] = mapped_column(Date)
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


#: Il lavoro dello staff oltre alle ore del cartellino: un compito svolto
#: (lo scrive chi l'ha fatto) o un lavoretto occasionale (lo scrive la
#: segreteria, anche per chi non ha un account).
STAFF_TASK_KINDS = ("TASK", "ODD_JOB")
STAFF_MESSAGE_CHANNELS = ("CLUB", "JAV")


class ClubStaffTask(UUIDPKMixin, TimestampMixin, Base):
    """Un compito svolto o un lavoretto occasionale (club/staff_work.py).
    Il costo, se c'è, quando si paga diventa una spesa COLLABORATORS
    (`club_expenses`, `expense_id`): la contabilità lo vede come tutto il resto."""

    __tablename__ = "club_staff_tasks"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_in(STAFF_TASK_KINDS)})", name="kind"),
        CheckConstraint("cost_cents >= 0", name="cost_not_negative"),
        CheckConstraint("minutes IS NULL OR minutes > 0", name="minutes_positive"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    person_name: Mapped[str] = mapped_column(String(150))
    kind: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(200))
    done_on: Mapped[date] = mapped_column(Date, index=True)
    minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_cents: Mapped[int] = mapped_column(BigInteger, default=0, server_default=sql_text("0"))
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    paid_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    expense_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("club_expenses.id", ondelete="SET NULL"), nullable=True,
    )
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


class ClubStaffMessage(UUIDPKMixin, TimestampMixin, Base):
    """Le comunicazioni tra una persona dello staff e il suo club (canale
    CLUB, la segreteria) o JudoArteVida (canale JAV, lo staff della
    piattaforma). Una conversazione per persona e canale; `from_staff` dice
    da che parte viene il messaggio, `read_at` se l'altra parte l'ha letto."""

    __tablename__ = "club_staff_messages"
    __table_args__ = (
        CheckConstraint(f"channel IN ({_in(STAFF_MESSAGE_CHANNELS)})", name="channel"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    staff_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    channel: Mapped[str] = mapped_column(String(8))
    from_staff: Mapped[bool] = mapped_column(Boolean)
    author_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ClubJudogiModel(UUIDPKMixin, TimestampMixin, Base):
    """Un modello di judogi della Loja (tipo + marca + colore), con le foto e
    la descrizione: la vetrina dei judogi. I prezzi per taglia restano nel
    listino (`club_judogi_prices`), che è l'unica fonte del conto: qui c'è
    solo come si presenta. Nasce da solo per ogni combinazione del listino."""

    __tablename__ = "club_judogi_models"
    __table_args__ = (
        UniqueConstraint("club_id", "kimono_type", "brand", "color", name="uq_club_judogi_models_item"),
        CheckConstraint(f"kimono_type IN ({_in(KIMONO_TYPES)})", name="kimono_type"),
        CheckConstraint(f"color IN ({_in(JUDOGI_COLORS)})", name="color"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    kimono_type: Mapped[str] = mapped_column(String(24))
    brand: Mapped[str] = mapped_column(String(60))
    color: Mapped[str] = mapped_column(String(24))
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    images: Mapped[list] = mapped_column(JSONB, default=list, server_default=sql_text("'[]'::jsonb"))
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class ClubCartItem(UUIDPKMixin, TimestampMixin, Base):
    """Una riga del carrello della Loja: un judogi configurato (`config`: le
    scelte del calcolatore e il nome) o una variante di un prodotto del club,
    per un atleta. Il carrello non tiene prezzi: si ricalcola a ogni lettura
    e all'ordine (CLAUDE.md §5). All'ordine ogni riga diventa un ordine a sé
    (`club_equipment_orders`) e il carrello si svuota."""

    __tablename__ = "club_cart_items"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_in(EQUIPMENT_ORDER_KINDS)})", name="kind"),
        CheckConstraint("quantity BETWEEN 1 AND 20", name="quantity_range"),
        CheckConstraint(
            "(kind = 'PRODUCT' AND variant_id IS NOT NULL) OR (kind = 'JUDOGI' AND config IS NOT NULL)",
            name="target",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    athlete_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("club_athletes.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(8))
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jav_market_products.id", ondelete="CASCADE"), nullable=True
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jav_market_variants.id", ondelete="CASCADE"), nullable=True
    )
    quantity: Mapped[int] = mapped_column(SmallInteger, default=1, server_default="1")
    #: Il judogi (kimono_type, color, brand, size_cm, trade_in) e il nome da
    #: ricamare o stampare: solo scelte, mai importi.
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
