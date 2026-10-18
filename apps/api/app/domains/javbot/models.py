"""JAVBOT: le conversazioni dell'assistente dell'area privata e i compiti
che aspettano una conferma.

Tre tabelle per le conversazioni, e nessuna colonna su quelle degli altri
domini: l'assistente legge i dati del club e dello Shop attraverso i loro
servizi, e qui tiene solo ciò che è suo — che cosa si sono detti e che cosa
ha promesso di fare. Più le tre della base di conoscenza (in fondo): i PDF,
i loro pezzi di testo e le istruzioni scritte da chi amministra.

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

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text
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
TASK_KINDS = ("SHOP_ORDER", "CLUB_MESSAGE", "MARK_ATTENDANCE", "COMPETITION_ENTRY", "STAFF_ATTENDANCE")


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
    #: Le schede sotto la risposta (una gara con «Inscrever», una fonte con il
    #: suo documento): dati strutturati che il browser disegna (planner.card).
    cards: Mapped[list] = mapped_column(JSONB, default=list, server_default=sql_text("'[]'::jsonb"))
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


# --- La base di conoscenza dell'assistente dell'area privata --------------------------------------
#
# I PDF che l'assistente consulta (knowledge.py). `club_id` NULL = la base
# **comune** a tutti i club, che carica la piattaforma; con un club = i
# documenti di quel club, che carica la sua segreteria. Un utente di un club
# vede sempre le due insieme, mai i documenti di un altro club.

#: Un documento si legge solo se ha testo: una scansione senza testo resta
#: in elenco come EMPTY, così chi l'ha caricata sa perché l'assistente non la usa.
KNOWLEDGE_STATUSES = ("READY", "EMPTY")


class JavbotKnowledgeDocument(UUIDPKMixin, TimestampMixin, Base):
    """Un PDF caricato. Il file resta nel bucket privato (`storage_key`), il
    testo estratto vive nei pezzi (`javbot_knowledge_chunks`)."""

    __tablename__ = "javbot_knowledge_documents"
    __table_args__ = (
        CheckConstraint("source IN ('UPLOAD', 'EVENT', 'DATA')", name="source"),
        Index("uq_javbot_knowledge_documents_source_ref", "source_ref", unique=True,
              postgresql_where=sql_text("source_ref IS NOT NULL")),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    club_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clubs.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    filename: Mapped[str] = mapped_column(String(255))
    #: Il PDF nel bucket privato; NULL per le schede scritte dal gestionale
    #: (`source` DATA), che non hanno un file.
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    #: Da dove viene: UPLOAD (caricato da chi amministra), EVENT (il
    #: regolamento di una gara o di un evento), DATA (una scheda che il
    #: gestionale scrive dai suoi dati: orari, piani e prezzi, eventi,
    #: contatti; rag.py la riscrive quando invecchia).
    source: Mapped[str] = mapped_column(String(8), default="UPLOAD", server_default="UPLOAD")
    #: Che cosa rappresenta, per ritrovarla e riscriverla: "event:<id>",
    #: "data:<club>:courses". UNIQUE quando c'è.
    source_ref: Mapped[str | None] = mapped_column(String(80), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    page_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    char_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String(16))
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class JavbotKnowledgeChunk(UUIDPKMixin, Base):
    """Un pezzo di testo di un documento, quello che la ricerca restituisce.
    `norm` è il testo minuscolo e senza accenti (intents.normalize): la
    ricerca a parole (`to_tsvector('simple', norm)`, indice GIN) trova
    "inscrição" scrivendo "inscricao", in ogni lingua, senza estensioni di
    Postgres da installare."""

    __tablename__ = "javbot_knowledge_chunks"
    __table_args__ = (
        Index("ix_javbot_knowledge_chunks_search", sql_text("to_tsvector('simple', norm)"), postgresql_using="gin"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("javbot_knowledge_documents.id", ondelete="CASCADE"), index=True
    )
    #: Ripetuti dal documento: la ricerca filtra per club senza un JOIN.
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    club_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clubs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    #: La pagina del PDF da cui inizia il pezzo (da 1), per citarla.
    page: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    norm: Mapped[str] = mapped_column(Text)


class JavbotInstructions(UUIDPKMixin, TimestampMixin, Base):
    """Il prompt scritto da chi amministra: come deve comportarsi
    l'assistente. Una riga comune (`club_id` NULL, della piattaforma) e al
    più una per club: valgono tutte e due, quella del club per ultima, così
    può precisare o correggere la comune per i suoi soci."""

    __tablename__ = "javbot_instructions"
    __table_args__ = (
        Index("uq_javbot_instructions_club", "club_id", unique=True, postgresql_where=sql_text("club_id IS NOT NULL")),
        Index(
            "uq_javbot_instructions_common", "organization_id", unique=True,
            postgresql_where=sql_text("club_id IS NULL"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    club_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clubs.id", ondelete="CASCADE"), nullable=True
    )
    text: Mapped[str] = mapped_column(Text, default="", server_default="")
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


#: Come è nata una risposta di JAVBOT (o un articolo): RULES (pianificatore,
#: zero token), ACTION (un'azione capita senza modello), CACHE (una risposta
#: già data, ripresa), RAG (documenti + una chiamata breve), AGENT (modello
#: con gli strumenti), EXTRACT (il modello capisce solo i dettagli di
#: un'azione), ARTICLE (un relatório final).
USAGE_ROUTES = ("RULES", "ACTION", "CACHE", "RAG", "AGENT", "EXTRACT", "ARTICLE")


class JavbotUsage(UUIDPKMixin, TimestampMixin, Base):
    """Una riga per risposta (o articolo): per dove è passata e quanti token
    ha speso. È il contatore dei costi: la console mostra quante risposte
    sono costate zero e quanto è costato il resto, per giorno e per club."""

    __tablename__ = "javbot_usage"
    __table_args__ = (
        CheckConstraint(f"route IN ({', '.join(repr(r) for r in USAGE_ROUTES)})", name="route"),
        Index("ix_javbot_usage_org_created", "organization_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    club_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clubs.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    route: Mapped[str] = mapped_column(String(8))
    provider: Mapped[str | None] = mapped_column(String(12), nullable=True)
    model: Mapped[str | None] = mapped_column(String(60), nullable=True)
    calls: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    #: L'intenzione o l'azione (fees_due, competition_entry…): per sapere che
    #: cosa si chiede di più.
    intent: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ok: Mapped[bool] = mapped_column(Boolean, default=True, server_default=sql_text("true"))
