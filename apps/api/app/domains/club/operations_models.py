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

from sqlalchemy import BigInteger, CheckConstraint, Date, ForeignKey, Integer, Numeric, SmallInteger, String, Text
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

