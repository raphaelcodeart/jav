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
    BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, Text,
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
    """Un "pedido de fato": il judogi che il club ordina al fornitore per un
    atleta, con il nome da ricamare. Il prezzo, quando la segreteria lo
    fissa, diventa la quota `EQUIPMENT` dell'atleta (`fee_id`)."""

    __tablename__ = "club_equipment_orders"
    __table_args__ = (
        CheckConstraint(f"kimono_type IN ({_in(KIMONO_TYPES)})", name="kimono_type"),
        CheckConstraint(f"status IN ({_in(EQUIPMENT_ORDER_STATUSES)})", name="status"),
        CheckConstraint("size_cm BETWEEN 80 AND 220", name="size_range"),
        CheckConstraint("price_cents IS NULL OR price_cents >= 0", name="price_non_negative"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    athlete_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("club_athletes.id"), index=True)
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    #: Il nome da ricamare (sotto i 13 anni solo il nome proprio).
    kimono_name: Mapped[str] = mapped_column(String(100))
    kimono_type: Mapped[str] = mapped_column(String(24))
    color: Mapped[str] = mapped_column(String(40))
    brand: Mapped[str] = mapped_column(String(60))
    size_cm: Mapped[int] = mapped_column(SmallInteger)
    #: Il prezzo fissato dalla segreteria (con la personalizzazione e
    #: l'eventuale permuta); NULL finché non lo fissa.
    price_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    #: Il judogi usato restituito, se c'è (tipo, colore, marca, taglia, valore).
    trade_in: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    internal_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", server_default="PENDING", index=True)
    fee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("club_fees.id"), nullable=True, unique=True
    )
    delivered_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


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
