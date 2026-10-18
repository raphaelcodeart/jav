"""I corsi esterni: judo nelle scuole pubbliche e private, per diffondere il
judo come arte di vita. Specifica: docs/club-portal.md, "Corsi esterni".

**Un sistema a parte, con tabelle sue.** Nessuna riga qui tocca i club:
niente `club_athletes`, quote, cinture, gare, ranking, Shop, wallet,
promoter o JAVBOT. Un bambino di un corso esterno è un **partecipante**
(`ext_participants`), non un atleta; chi è già atleta di un club e vuole
fare anche il corso si iscrive di nuovo, e così per ogni corso: ogni corso
ha la sua anagrafica. Se un partecipante vuole entrare in un club, si
iscrive al club come chiunque.

Le persone che lavorano sui corsi sono account (`users`) collegati al corso
da `ext_staff`: il treinador (COACH, con la sua percentuale delle
mensilità) e la segreteria della scuola (SCHOOL, che vede iscritti,
pagamenti e presenze del suo corso). Il genitore è l'account che ha
iscritto i figli (`ext_participants.parent_user_id`).

Il denaro: una mensilità per partecipante e per mese (`ext_fees`, UNIQUE),
emessa nei mesi del corso; la prova di pagamento caricata dal genitore la
segna pagata subito (come nei club). Ogni mensilità porta **congelati** il
treinador e la sua percentuale del momento: la parte del treinador e quella
di JudoArteVida si calcolano dalle mensilità pagate.
"""

import uuid
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Date, ForeignKey, Index, Numeric, SmallInteger, String, Text, Time,
    UniqueConstraint,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin, utcnow


def _in(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


STAFF_ROLES = ("COACH", "SCHOOL")
PARTICIPANT_STATUSES = ("ACTIVE", "LEFT")
FEE_STATUSES = ("DUE", "PAID", "WAIVED")
PAYMENT_METHODS = ("BANK_TRANSFER", "MBWAY", "CASH", "POS")
PROOF_STATUSES = ("ACCEPTED", "REJECTED")
#: Settembre/ottobre–luglio: l'anno scolastico.
DEFAULT_BILLING_MONTHS = [10, 11, 12, 1, 2, 3, 4, 5, 6, 7]


class ExtCourse(UUIDPKMixin, TimestampMixin, Base):
    """Un corso esterno in una scuola: dove, da quando a quando, quanto costa."""

    __tablename__ = "ext_courses"
    __table_args__ = (
        CheckConstraint("monthly_fee_cents >= 0", name="fee_non_negative"),
        CheckConstraint("due_day BETWEEN 1 AND 28", name="due_day_range"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(150))
    school_name: Mapped[str] = mapped_column(String(200))
    school_address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    school_city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    #: Il logo della scuola (bucket pubblico).
    school_logo_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    monthly_fee_cents: Mapped[int] = mapped_column(BigInteger, default=2500)
    #: I mesi (1–12) in cui si emette la mensilità.
    billing_months: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger), default=lambda: list(DEFAULT_BILLING_MONTHS))
    due_day: Mapped[int] = mapped_column(SmallInteger, default=10)
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=sql_text("true"))
    #: Sul sito, con il modulo d'iscrizione.
    published: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sql_text("false"))
    #: Il nome del treinador come compare sul sito (scritto a mano).
    public_coach_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


class ExtGroup(UUIDPKMixin, TimestampMixin, Base):
    """Un gruppo del corso: le età e l'orario della lezione."""

    __tablename__ = "ext_groups"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_range"),
        CheckConstraint("ends_at > starts_at", name="times"),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ext_courses.id", ondelete="CASCADE"),
                                                 index=True)
    name: Mapped[str] = mapped_column(String(120))
    min_age: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    max_age: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    weekday: Mapped[int] = mapped_column(SmallInteger)
    starts_at: Mapped[time] = mapped_column(Time)
    ends_at: Mapped[time] = mapped_column(Time)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=sql_text("true"))


class ExtStaff(UUIDPKMixin, TimestampMixin, Base):
    """Chi lavora sul corso: il treinador (con la sua percentuale) o la
    segreteria della scuola."""

    __tablename__ = "ext_staff"
    __table_args__ = (
        UniqueConstraint("course_id", "user_id", "role", name="uq_ext_staff_course_user_role"),
        CheckConstraint(f"role IN ({_in(STAFF_ROLES)})", name="role"),
        CheckConstraint("share_pct IS NULL OR share_pct BETWEEN 0 AND 100", name="share_range"),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ext_courses.id", ondelete="CASCADE"),
                                                 index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(8))
    #: COACH: la percentuale delle mensilità pagate (default 50).
    share_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=sql_text("true"))


class ExtParticipant(UUIDPKMixin, TimestampMixin, Base):
    """Un bambino iscritto a un corso esterno: un'anagrafica del corso, non
    un atleta di un club."""

    __tablename__ = "ext_participants"
    __table_args__ = (CheckConstraint(f"status IN ({_in(PARTICIPANT_STATUSES)})", name="status"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ext_courses.id"), index=True)
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ext_groups.id", ondelete="SET NULL"), nullable=True, index=True
    )
    parent_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str] = mapped_column(String(80))
    birth_date: Mapped[date] = mapped_column(Date)
    sex: Mapped[str | None] = mapped_column(String(1), nullable=True)
    #: Per la scuola e il treinador: allergie, chi viene a prenderlo.
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    guardian_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    guardian_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(8), default="ACTIVE", server_default="ACTIVE")
    joined_on: Mapped[date] = mapped_column(Date)
    left_on: Mapped[date | None] = mapped_column(Date, nullable=True)


class ExtFee(UUIDPKMixin, TimestampMixin, Base):
    """La mensilità di un partecipante, una per mese."""

    __tablename__ = "ext_fees"
    __table_args__ = (
        UniqueConstraint("participant_id", "period", name="uq_ext_fees_participant_period"),
        CheckConstraint(f"status IN ({_in(FEE_STATUSES)})", name="status"),
        CheckConstraint(f"method IS NULL OR method IN ({_in(PAYMENT_METHODS)})", name="method"),
        CheckConstraint("amount_cents >= 0", name="amount_non_negative"),
        Index("ix_ext_fees_course_status", "course_id", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ext_courses.id"))
    participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ext_participants.id", ondelete="CASCADE"), index=True
    )
    #: "AAAA-MM".
    period: Mapped[str] = mapped_column(String(7))
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(8), default="DUE", server_default="DUE")
    paid_at: Mapped[datetime | None] = mapped_column(nullable=True)
    method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    proof_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ext_proofs.id", ondelete="SET NULL"), nullable=True
    )
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    #: Congelati all'emissione: chi insegnava e con che percentuale.
    coach_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    coach_share_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)


class ExtProof(UUIDPKMixin, TimestampMixin, Base):
    """Una prova di pagamento caricata dal genitore (file nel bucket privato)."""

    __tablename__ = "ext_proofs"
    __table_args__ = (
        CheckConstraint(f"status IN ({_in(PROOF_STATUSES)})", name="status"),
        CheckConstraint(f"method IN ({_in(PAYMENT_METHODS)})", name="method"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ext_courses.id"), index=True)
    parent_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    method: Mapped[str] = mapped_column(String(16), default="BANK_TRANSFER")
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(8), default="ACCEPTED", server_default="ACCEPTED")
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class ExtAttendance(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "ext_attendances"
    __table_args__ = (UniqueConstraint("participant_id", "date", name="uq_ext_attendances_participant_date"),)

    course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ext_courses.id"), index=True)
    participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ext_participants.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[date] = mapped_column(Date)
    present: Mapped[bool] = mapped_column(Boolean, default=True)
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


class ExtWorkSession(UUIDPKMixin, TimestampMixin, Base):
    """L'entrata e l'uscita del treinador nel corso (il suo lavoro)."""

    __tablename__ = "ext_work_sessions"
    __table_args__ = (CheckConstraint("ended_at IS NULL OR ended_at > started_at", name="times"),)

    course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ext_courses.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ExtNotice(UUIDPKMixin, TimestampMixin, Base):
    """Un avviso alle famiglie del corso («lunedì niente lezione»)."""

    __tablename__ = "ext_notices"

    course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ext_courses.id", ondelete="CASCADE"),
                                                 index=True)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
