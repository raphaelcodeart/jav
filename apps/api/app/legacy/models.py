"""La corrispondenza tra le righe di un gestionale precedente e quelle di
Jav (docs/legacy-judo-aev.md, "Come si importa").

Una riga per riga importata: (fonte, tabella, id vecchio) → (tabella, id
nuovo). È ciò che rende l'importazione **rilanciabile**: chi rilancia
ritrova la riga già creata e la aggiorna, invece di crearne una seconda. La
chiave è UNIQUE, come vuole CLAUDE.md §5: l'idempotenza la garantisce il
database, non un controllo nel codice.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UUIDPKMixin, utcnow


class LegacyImportMap(UUIDPKMixin, Base):
    __tablename__ = "legacy_import_map"
    __table_args__ = (
        UniqueConstraint("source", "source_table", "source_id", name="uq_legacy_import_map_source_row"),
    )

    #: Il gestionale di provenienza ("judo-aev").
    source: Mapped[str] = mapped_column(String(32))
    source_table: Mapped[str] = mapped_column(String(64))
    #: L'id vecchio, come testo (o una chiave composta, "atleta:mese").
    source_id: Mapped[str] = mapped_column(String(100))
    target_table: Mapped[str] = mapped_column(String(64))
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    imported_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
