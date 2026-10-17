"""Il quaderno del treinador (club/coach.py): le note delle lezioni e le note
personali sugli atleti. Specifica: docs/club-portal.md, "Il quaderno del
treinador".

Stanno in un file loro, importato da club/models.py, perché sono dello staff
e di nessun altro: non le legge la famiglia, non le legge l'atleta.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin

#: Di che cosa parla una nota su un atleta: serve a filtrarle e a dare a
#: ognuna la sua icona.
ATHLETE_NOTE_CATEGORIES = ("TECHNIQUE", "BEHAVIOUR", "HEALTH", "GOAL", "COMPETITION", "OTHER")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class ClubLessonNote(UUIDPKMixin, TimestampMixin, Base):
    """Che cosa si è fatto in una lezione (corso + giorno): le tecniche, le
    situazioni, le osservazioni. Più note per la stessa lezione si possono
    avere (il titolare e l'adjunto scrivono ognuno la sua); la storia del
    corso è la loro sequenza per data."""

    __tablename__ = "club_lesson_notes"
    __table_args__ = (Index("ix_club_lesson_notes_course_date", "course_id", "lesson_date"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("club_courses.id", ondelete="CASCADE")
    )
    lesson_date: Mapped[date] = mapped_column(Date)
    author_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    #: Il tema della lezione, in una riga ("Ukemi e o-soto-gari").
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    #: Le tecniche lavorate, separate da virgole: diventano etichette e si cercano.
    techniques: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ClubAthleteNote(UUIDPKMixin, TimestampMixin, Base):
    """Una nota personale del treinador su un atleta: la vedono solo i
    treinadores dei corsi dell'atleta e la segreteria. Mai la famiglia."""

    __tablename__ = "club_athlete_notes"
    __table_args__ = (
        CheckConstraint(f"category IN ({_in(ATHLETE_NOTE_CATEGORIES)})", name="category"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    athlete_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("club_athletes.id", ondelete="CASCADE"), index=True
    )
    author_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    category: Mapped[str] = mapped_column(String(16), default="OTHER", server_default="OTHER")
    body: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)
