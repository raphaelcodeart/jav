"""I testi delle email modificati dal superadmin (service.py). Una riga per
email: senza riga vale il testo predefinito del codice."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, utcnow


class EmailTemplateOverride(Base):
    __tablename__ = "email_template_overrides"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    subject: Mapped[str] = mapped_column(String(200))
    heading: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    cta_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
