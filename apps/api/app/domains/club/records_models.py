"""La ficha de inscrição e ciò che le gira intorno: i dati d'identità
dell'atleta, i suoi documenti, i consensi RGPD, le richieste di modifica
dei genitori e le domande d'iscrizione. Specifica: docs/club-portal.md,
"La ficha dell'atleta".

**Perché tabelle a parte e non colonne su `club_athletes`.** Documento
d'identità, passaporto, indirizzo e telefoni dei genitori sono i dati più
delicati del gestionale: li legge solo la segreteria (e la federazione e
l'assicurazione, attraverso gli export), mai la pagina dell'atleta, il
ranking o JAVBOT. In una tabella loro non finiscono per sbaglio in un
`select(ClubAthlete)` che poi diventa JSON.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, Integer, SmallInteger, String, Text
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin, utcnow


def _in(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


#: I documenti d'identità portoghesi più comuni; OTHER per il resto.
ID_DOCUMENT_TYPES = ("CITIZEN_CARD", "PASSPORT", "RESIDENCE_PERMIT", "BIRTH_CERTIFICATE", "OTHER")
#: Che cosa si archivia nella scheda dell'atleta. I certificati medici e le
#: giustificazioni per la scuola hanno già le loro tabelle.
ATHLETE_DOCUMENT_KINDS = (
    "SOCIAL_SECURITY", "MEDICAL_JUSTIFICATION", "SCHOOL_JUSTIFICATION", "CLUB_DECLARATION",
    "PARENTAL_AUTHORIZATION", "ID_DOCUMENT", "OTHER",
)
#: PRIVACY_POLICY è dell'account (chi accetta lo fa per tutti i suoi atleti),
#: PHOTOS di ogni atleta.
CONSENT_KINDS = ("PRIVACY_POLICY", "PHOTOS", "MARKETING")
CONSENT_SOURCES = ("PORTAL", "BACKOFFICE", "LEGACY")
#: I campi che un genitore può chiedere di cambiare: quelli che decide la
#: segreteria (o la federazione), non lui.
CHANGE_REQUEST_FIELDS = ("BELT", "WEIGHT_CATEGORY", "WEIGHT")
REQUEST_STATUSES = ("PENDING", "APPROVED", "REJECTED")
APPLICATION_STATUSES = ("PENDING", "APPROVED", "REJECTED", "CANCELLED")


class ClubAthleteRecord(Base):
    """I dati d'identità e di contatto di un atleta: uno per atleta, letto e
    scritto solo dalla segreteria."""

    __tablename__ = "club_athlete_records"
    __table_args__ = (
        CheckConstraint(
            f"id_document_type IS NULL OR id_document_type IN ({_in(ID_DOCUMENT_TYPES)})", name="id_document_type"
        ),
        CheckConstraint(
            f"guardian_id_document_type IS NULL OR guardian_id_document_type IN ({_in(ID_DOCUMENT_TYPES)})",
            name="guardian_id_document_type",
        ),
    )

    athlete_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("club_athletes.id", ondelete="CASCADE"), primary_key=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    # --- L'atleta ---
    address: Mapped[str | None] = mapped_column(String(250), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    mobile: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(150), nullable=True)
    marital_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    id_document_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    id_document_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    #: Le cifre di controllo del Cartão de Cidadão ("1ZZ4").
    id_document_check_digits: Mapped[str | None] = mapped_column(String(20), nullable=True)
    id_document_expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    passport_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    passport_country: Mapped[str | None] = mapped_column(String(60), nullable=True)
    passport_expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    # --- Il responsabile (encarregado de educação) ---
    guardian_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    guardian_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    father_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    mother_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    guardian_fiscal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    guardian_id_document_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    guardian_id_document_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    guardian_id_document_check_digits: Mapped[str | None] = mapped_column(String(20), nullable=True)
    guardian_id_document_expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    guardian_passport_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    guardian_passport_country: Mapped[str | None] = mapped_column(String(60), nullable=True)
    guardian_passport_expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: Note interne della segreteria.
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class ClubAthleteDocument(UUIDPKMixin, TimestampMixin, Base):
    """Un documento archiviato nella scheda dell'atleta (bucket privato:
    `storage_key`, mai un URL salvato). Si apre con un URL presigned dato
    dopo il controllo di chi lo chiede (CLAUDE.md §5)."""

    __tablename__ = "club_athlete_documents"
    __table_args__ = (CheckConstraint(f"kind IN ({_in(ATHLETE_DOCUMENT_KINDS)})", name="kind"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    athlete_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("club_athletes.id"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    description: Mapped[str | None] = mapped_column(String(250), nullable=True)
    storage_key: Mapped[str] = mapped_column(String(500))
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class ClubConsent(UUIDPKMixin, TimestampMixin, Base):
    """Un consenso dato o negato, con la versione della politica e da dove
    è arrivato. **Si aggiunge, non si sovrascrive**: lo storico è la prova
    (RGPD, art. 7). Lo stato attuale è la riga più recente non revocata per
    (account o atleta, tipo)."""

    __tablename__ = "club_consents"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_in(CONSENT_KINDS)})", name="kind"),
        CheckConstraint(f"source IN ({_in(CONSENT_SOURCES)})", name="source"),
        # La politica è dell'account, le foto di un atleta.
        CheckConstraint(
            "(kind = 'PRIVACY_POLICY' AND user_id IS NOT NULL) OR (kind <> 'PRIVACY_POLICY' AND athlete_id IS NOT NULL)",
            name="subject",
        ),
        Index("ix_club_consents_subject", "kind", "user_id", "athlete_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    #: L'account che ha dato il consenso (per la politica, il soggetto).
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    athlete_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("club_athletes.id"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    granted: Mapped[bool] = mapped_column(Boolean)
    policy_version: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(12))
    #: Chi l'ha registrato in segreteria (origine BACKOFFICE).
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    #: L'impronta dell'indirizzo IP (sha256), non l'indirizzo: basta a
    #: dimostrare, non a rintracciare.
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: Quando è stato dato davvero (per i consensi importati, la data del
    #: vecchio gestionale; per i nuovi coincide con created_at).
    given_at: Mapped[datetime] = mapped_column(default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ClubChangeRequest(UUIDPKMixin, TimestampMixin, Base):
    """Un genitore chiede di correggere un dato che decide la segreteria
    (cintura, categoria di peso, peso): la segreteria approva (e il dato
    cambia) o rifiuta."""

    __tablename__ = "club_change_requests"
    __table_args__ = (
        CheckConstraint(f"field IN ({_in(CHANGE_REQUEST_FIELDS)})", name="field"),
        CheckConstraint(f"status IN ({_in(REQUEST_STATUSES)})", name="status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    athlete_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("club_athletes.id"), index=True)
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    field: Mapped[str] = mapped_column(String(20))
    current_value: Mapped[str | None] = mapped_column(String(200), nullable=True)
    requested_value: Mapped[str] = mapped_column(String(200))
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="PENDING", server_default="PENDING", index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    resolution_note: Mapped[str | None] = mapped_column(String(500), nullable=True)


class ClubApplication(UUIDPKMixin, TimestampMixin, Base):
    """Una domanda d'iscrizione al club dal modulo pubblico (la ficha
    completa). `data` contiene il modulo così come è stato compilato: è un
    documento, non un atleta. All'approvazione nasce l'atleta
    (`athlete_id`) con il suo nº de sócio."""

    __tablename__ = "club_applications"
    __table_args__ = (CheckConstraint(f"status IN ({_in(APPLICATION_STATUSES)})", name="status"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    data: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=sql_text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(String(12), default="PENDING", server_default="PENDING", index=True)
    internal_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    athlete_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("club_athletes.id"), nullable=True
    )
    #: Chi ha invitato (programma "trás um amigo"), come l'ha scritto.
    referred_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    first_time: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    joined_year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(nullable=True)
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
