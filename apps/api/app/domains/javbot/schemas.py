"""Che cosa il browser manda a JAVBOT e che cosa riceve.

Il browser manda solo testo, la lingua e l'id di un compito da confermare:
mai un prezzo, una variante o un atleta (CLAUDE.md §5). Tutto ciò che un
compito esegue è già sul server, nel compito.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class BotAction(BaseModel):
    """Un bottone sotto una risposta. `type`: navigate (target = una
    sezione dell'area), open_pay (kind = fees | choose), confirm_task /
    cancel_task (task_id, task_status), link (href, solo sito), copy (value)."""

    type: str
    label: str
    #: `say`: il bottone manda `value` come se l'utente l'avesse scritto.
    target: str | None = None
    kind: str | None = None
    task_id: str | None = None
    task_status: str | None = None
    href: str | None = None
    value: str | None = None


class BotMessageRead(BaseModel):
    id: uuid.UUID
    role: str
    #: Testo con un Markdown minimo (**grassetto**, elenchi «- », link): il
    #: browser lo disegna.
    text: str
    actions: list[BotAction]
    quick_replies: list[str]
    #: Le schede sotto il testo: `event` (una gara con data, luogo, scadenza,
    #: quota, regolamento e bottoni `say`), `source` (una fonte del RAG).
    cards: list[dict] = []
    created_at: datetime


class ConversationRead(BaseModel):
    id: uuid.UUID
    messages: list[BotMessageRead]


class MessageWrite(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    #: La lingua dell'interfaccia (cookie `jav_lang`): pt, it o en.
    lang: str | None = Field(default=None, max_length=5)


class LangWrite(BaseModel):
    lang: str | None = Field(default=None, max_length=5)


class ExchangeRead(BaseModel):
    """La domanda salvata e la risposta: il browser le aggiunge in coda."""

    messages: list[BotMessageRead]


class PublicBotWrite(BaseModel):
    text: str = Field(default="", max_length=500)
    lang: str | None = Field(default=None, max_length=5)
    #: Lo slug del club se la pagina aperta è quella di un club: il
    #: contesto, non un permesso (sono comunque solo dati pubblici).
    club_slug: str | None = Field(default=None, max_length=120)


class PublicBotRead(BaseModel):
    text: str
    actions: list[BotAction]
    quick_replies: list[str]


# --- La base di conoscenza (knowledge_router.py) --------------------------------------------------


class KnowledgeDocumentRead(BaseModel):
    id: uuid.UUID
    title: str
    filename: str
    size_bytes: int
    page_count: int
    #: READY: l'assistente lo consulta; EMPTY: il PDF non ha testo (una scansione).
    status: str
    #: Della base comune a tutti i club.
    common: bool
    created_at: datetime
    #: UPLOAD (caricato), EVENT (regolamento di un evento), DATA (scheda scritta dal gestionale).
    source: str = "UPLOAD"
    source_ref: str | None = None
    has_file: bool = True


class KnowledgeRead(BaseModel):
    documents: list[KnowledgeDocumentRead]
    #: Per la segreteria di un club: i documenti comuni, da vedere e non da toccare.
    common_documents: list[KnowledgeDocumentRead] = []
    instructions: str
    #: Le istruzioni comuni, per chi scrive quelle del club: sa che cosa precisa.
    common_instructions: str = ""
    #: False se il server non ha la chiave del modello: JAVBOT risponde a parole chiave.
    assistant_enabled: bool
    #: Il fornitore del modello (openai / anthropic) e il modello, se c'è.
    provider: str | None = None
    model: str | None = None


class InstructionsWrite(BaseModel):
    text: str = Field(default="", max_length=8000)


class DocumentLinkRead(BaseModel):
    url: str
