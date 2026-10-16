"""I messaggi scritti dal sito pubblico: "Envie uma mensagem ao clube" in
fondo alla pagina di ogni club, e il modulo di /contactos per JudoArteVida.
Specifica: docs/club-portal.md, "Sito pubblico" → "Messaggi dal sito".

Una tabella a parte, e non in site_models.py: quelle tabelle sono fatte per
essere lette da chiunque, queste righe invece sono dati personali di chi
scrive (nome, email, telefono) e le legge solo chi le riceve.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin

CONTACT_STATUSES = ("NEW", "READ", "ARCHIVED")
#: Di che cosa scrive: una domanda qualunque, diventare sponsor, iscriversi,
#: gare ed eventi, altro. Lo sceglie chi scrive; la casella lo mostra e filtra.
CONTACT_TOPICS = ("GENERAL", "SPONSOR", "ENROLMENT", "EVENTS", "NEW_CLUB", "OTHER")


class ContactMessage(UUIDPKMixin, TimestampMixin, Base):
    """Un messaggio dal sito. `club_id` dice a chi è scritto: un club, o
    (NULL) JudoArteVida. Lo vede la segreteria di quel club, o lo staff della
    piattaforma per quelli a JAV: il perimetro lo decide club/scope.py come
    per tutto il resto, mai un id che arriva dal browser."""

    __tablename__ = "contact_messages"
    __table_args__ = (
        CheckConstraint("status IN ('NEW', 'READ', 'ARCHIVED')", name="status"),
        CheckConstraint("topic IN ('GENERAL', 'SPONSOR', 'ENROLMENT', 'EVENTS', 'NEW_CLUB', 'OTHER')", name="topic"),
        # Il limite per mittente (contact.py, quanti messaggi in un'ora) si
        # legge da qui: niente scansione della tabella a ogni invio.
        Index("ix_contact_messages_ip_hash_created_at", "ip_hash", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    #: NULL = a JudoArteVida (il modulo di /contactos).
    club_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clubs.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    topic: Mapped[str] = mapped_column(String(16), default="GENERAL", server_default=text("'GENERAL'"))
    #: La lingua del sito quando ha scritto: in quella gli si risponde.
    locale: Mapped[str] = mapped_column(String(5), default="pt", server_default=text("'pt'"))
    status: Mapped[str] = mapped_column(String(10), default="NEW", server_default=text("'NEW'"), index=True)
    #: Quando ha spuntato "accetto di essere ricontattato" (GDPR): senza, il
    #: messaggio non si salva nemmeno.
    consent_at: Mapped[datetime] = mapped_column()
    #: L'impronta dell'indirizzo IP (sha256 con il segreto del server), mai
    #: l'indirizzo: basta per contare i messaggi di uno stesso mittente.
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(200), nullable=True)
    #: Quando è partita l'email di avviso. NULL: non è partita (SMTP non
    #: configurato, nessun indirizzo, server di posta giù): il messaggio è
    #: comunque nella casella "Messaggi", che è ciò che conta.
    emailed_at: Mapped[datetime | None] = mapped_column(nullable=True)
