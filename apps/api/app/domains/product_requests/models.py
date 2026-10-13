"""«Non hai trovato ciò che cercavi?» -- le richieste di prodotto dallo Shop.

Un sistema di ticket a sé, separato di proposito da `support` (Supporto &
Assistenza): chi cerca un prodotto non ha un problema da risolvere, e
mescolare le due code vorrebbe dire far aspettare un guasto dietro a una
richiesta di caffè in capsule, o viceversa. Stessa forma dei ticket --
una richiesta, una conversazione, uno stato -- ma tabelle proprie, così
si può cambiare (o spegnere) l'una senza toccare l'altra."""

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin

REQUEST_STATUSES = {"OPEN", "IN_PROGRESS", "FOUND", "NOT_FOUND", "CLOSED"}


class ProductRequest(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "product_requests"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    opened_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    # Fotografia, come Ticket.opened_by_role: un cambio di ruolo dopo non
    # riscrive chi ha fatto la richiesta.
    opened_by_role: Mapped[str] = mapped_column(String(32))
    product_name: Mapped[str] = mapped_column(String(255))
    # Facoltativo: il link a un prodotto visto altrove ("tipo questo").
    reference_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="OPEN", index=True)


class ProductRequestMessage(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "product_request_messages"

    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_requests.id"), index=True
    )
    author_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    author_role: Mapped[str] = mapped_column(String(32))
    body: Mapped[str] = mapped_column(Text)
