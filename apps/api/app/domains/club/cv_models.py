"""L'archivio professionale del treinador: i suoi documenti (diplomi,
certificazioni, attestati), il suo Curriculum Vitae, gli eventi sportivi
che aggiunge a mano al Curriculum Sportivo e i PDF salvati. Specifica:
docs/club-portal.md, "Il curriculum del treinador"; codice in
club/coach_cv.py.

Tutto è della **persona** (`user_id`), non di un club: il treinador lo
porta con sé in ogni club in cui allena, e nessun club lo legge.

**Gli eventi aggiunti a mano stanno qui e solo qui.** Non sono gare del club
(`club_competitions`), non entrano nel calendario, nel ranking né nelle
statistiche: sono dichiarazioni personali per completare il curriculum, e
il curriculum le mostra come tali, distinte dai risultati ufficiali.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, ForeignKey, Index, SmallInteger, String, Text
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin, utcnow


def _in(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


#: Che documento è: il diploma di treinador (Nível 1, 2, 3…), una qualifica
#: federale, un attestato di corso o stage, il primo soccorso, un titolo di
#: studio, una qualifica professionale, un documento personale, altro.
COACH_DOCUMENT_CATEGORIES = (
    "COACH_DIPLOMA", "FEDERATION", "COURSE", "FIRST_AID", "ACADEMIC", "PROFESSIONAL", "PERSONAL", "OTHER",
)
#: Gli eventi che il treinador aggiunge a mano al Curriculum Sportivo.
SPORT_EVENT_TYPES = ("COMPETITION", "STAGE", "SEMINAR", "COURSE", "GRADING", "REFEREEING", "OTHER")
#: Il ruolo in quell'evento: la carriera agonistica (ATHLETE) e quella
#: tecnica (il resto) si raccontano separate.
SPORT_EVENT_ROLES = ("ATHLETE", "COACH", "ASSISTANT_COACH", "REFEREE", "ORGANIZER", "OTHER")
CV_EXPORT_KINDS = ("CV", "SPORT")


class CoachDocument(UUIDPKMixin, TimestampMixin, Base):
    """Un documento dell'archivio del treinador. Il file sta nel bucket
    privato (`storage_key`) e si apre solo con un URL presigned di pochi
    minuti, dato al proprietario."""

    __tablename__ = "coach_documents"
    __table_args__ = (
        CheckConstraint(f"category IN ({_in(COACH_DOCUMENT_CATEGORIES)})", name="category"),
        CheckConstraint("expires_on IS NULL OR issued_on IS NULL OR expires_on >= issued_on", name="dates"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(16))
    #: L'ente che l'ha rilasciato (la federazione, l'IPDJ, un'università).
    issuer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    issued_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    #: Il file, se c'è: un diploma si può scrivere anche senza scansione.
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    #: Compare nel CV (le certificazioni del CV si leggono da qui).
    show_in_cv: Mapped[bool] = mapped_column(Boolean, default=True, server_default=sql_text("true"))
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class CoachProfile(UUIDPKMixin, TimestampMixin, Base):
    """Il Curriculum Vitae del treinador: una riga per persona, il contenuto
    in `data` (presentazione, contatti, esperienze, formazione, competenze,
    lingue, specializzazioni, sezioni libere). Nome, foto, email e i club in
    cui allena vengono dal gestionale e non si duplicano qui."""

    __tablename__ = "coach_profiles"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True)
    data: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=sql_text("'{}'::jsonb"))
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class CoachSportEvent(UUIDPKMixin, TimestampMixin, Base):
    """Un evento che il treinador aggiunge a mano al Curriculum Sportivo
    (una gara di vent'anni fa, uno stage, un esame di Dan): resta una sua
    dichiarazione, fuori da gare, calendario, ranking e statistiche."""

    __tablename__ = "coach_sport_events"
    __table_args__ = (
        CheckConstraint(f"event_type IN ({_in(SPORT_EVENT_TYPES)})", name="event_type"),
        CheckConstraint(f"role IN ({_in(SPORT_EVENT_ROLES)})", name="role"),
        CheckConstraint("ends_on IS NULL OR ends_on >= starts_on", name="dates"),
        CheckConstraint("placement IS NULL OR placement IN (0, 1, 2, 3, 5, 7)", name="placement"),
        Index("ix_coach_sport_events_user_date", "user_id", "starts_on"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(200))
    event_type: Mapped[str] = mapped_column(String(16))
    role: Mapped[str] = mapped_column(String(16))
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    #: Il club o l'organizzazione (per chi gareggiava, per chi organizzava).
    organization_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    #: Il livello, con i codici delle gare (club.models.COMPETITION_LEVELS).
    level: Mapped[str | None] = mapped_column(String(24), nullable=True)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    #: Come le iscrizioni alle gare: 1, 2, 3, 5, 7; 0 = partecipazione.
    placement: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    result: Mapped[str | None] = mapped_column(String(300), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: L'attestato a sostegno, dall'archivio.
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("coach_documents.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class CoachCvExport(UUIDPKMixin, TimestampMixin, Base):
    """Una versione salvata di un curriculum in PDF (CV o Sportivo), nel
    bucket privato: quella mandata a un club resta com'era."""

    __tablename__ = "coach_cv_exports"
    __table_args__ = (CheckConstraint(f"kind IN ({_in(CV_EXPORT_KINDS)})", name="kind"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(8))
    storage_key: Mapped[str] = mapped_column(String(500))
    filename: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
