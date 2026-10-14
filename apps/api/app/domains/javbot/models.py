"""JAVBOT: le conversazioni dell'assistente dell'area privata e i compiti
che aspettano una conferma.

Tre tabelle, e nessuna colonna su quelle degli altri domini: l'assistente
legge i dati del club e dello Shop attraverso i loro servizi, e qui tiene
solo ciò che è suo — che cosa si sono detti e che cosa ha promesso di fare.

**Un compito (`javbot_tasks`) è l'unico modo in cui JAVBOT scrive.** Un
ordine, un messaggio alla segreteria, una presenza: prima nasce un compito
`PENDING` con tutto ciò che serve a eseguirlo, l'utente lo vede e lo
conferma, e solo allora si esegue. La chiave di idempotenza è l'id del
compito, generato dal server: la conferma lo "prende" con un UPDATE
condizionato (`status = 'PENDING'`), e una seconda conferma — doppio tocco,
rete lenta, due schede aperte — trova il compito già `DONE` e non fa niente.
`result_ref` (l'ordine creato) è UNIQUE: lo stesso risultato non può essere
attribuito a due compiti.

**Conservazione**: una conversazione ferma da più di `RETENTION_DAYS` si
cancella con i suoi messaggi e i suoi compiti la prossima volta che lo
stesso utente apre JAVBOT (service.py::purge_old). Nessun job: chi non torna
non accumula niente che qualcuno legga.
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin, utcnow

#: Dopo quanti giorni di silenzio una conversazione si cancella.
RETENTION_DAYS = 90
#: Quanto vale una proposta non confermata: un prezzo di ieri non si conferma.
TASK_TTL_MINUTES = 30

MESSAGE_ROLES = ("user", "bot")
TASK_STATUSES = ("PENDING", "DONE", "CANCELLED")
#: Che cosa JAVBOT sa fare, una volta confermato.
TASK_KINDS = ("SHOP_ORDER", "CLUB_MESSAGE", "MARK_ATTENDANCE")


class JavbotConversation(UUIDPKMixin, TimestampMixin, Base):
    """Una conversazione di un utente. `state` è la memoria corta del
    pianificatore (in quale percorso si è, che cosa ha già chiesto): si
    azzera a fine percorso o quando l'utente cambia argomento."""

    __tablename__ = "javbot_conversations"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    #: Il club su cui lavorava l'utente quando l'ha aperta (club/scope.py);
    #: NULL per chi non è in un club (staff della piattaforma fuori dai club).
    club_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clubs.id"), nullable=True, index=True
    )
    state: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=sql_text("'{}'::jsonb"))
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class JavbotMessage(UUIDPKMixin, TimestampMixin, Base):
    """Una battuta: dell'utente o di JAVBOT. Le azioni (bottoni) e le
    risposte rapide si salvano con il testo, così riaprendo la chat si vede
    esattamente ciò che si era visto."""

    __tablename__ = "javbot_messages"
    __table_args__ = (Index("ix_javbot_messages_conversation_created", "conversation_id", "created_at"),)

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("javbot_conversations.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    club_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clubs.id"), nullable=True
    )
    #: "user" o "bot".
    role: Mapped[str] = mapped_column(String(8))
    text: Mapped[str] = mapped_column(Text)
    #: [{"type": "navigate", "target": "club", "label": "..."}, ...]
    actions: Mapped[list] = mapped_column(JSONB, default=list, server_default=sql_text("'[]'::jsonb"))
    quick_replies: Mapped[list] = mapped_column(JSONB, default=list, server_default=sql_text("'[]'::jsonb"))
    #: L'intenzione riconosciuta (solo per le battute dell'utente): serve a
    #: capire che cosa chiedono le famiglie e che cosa JAVBOT non capisce.
    intent: Mapped[str | None] = mapped_column(String(40), nullable=True)


class JavbotTask(UUIDPKMixin, TimestampMixin, Base):
    """Una cosa che JAVBOT farà solo dopo un "sì" esplicito. `payload`
    contiene già tutto (variante, atleta, indirizzo, testo del messaggio):
    la conferma non riceve niente dal browser se non l'id."""

    __tablename__ = "javbot_tasks"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("javbot_conversations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    club_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clubs.id"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", server_default="PENDING")
    #: Che cosa ha prodotto (l'id dell'ordine dello Shop): UNIQUE, un
    #: risultato appartiene a un compito solo.
    result_ref: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    done_at: Mapped[datetime | None] = mapped_column(nullable=True)
