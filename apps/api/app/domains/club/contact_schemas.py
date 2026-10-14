"""I messaggi dal sito (club/contact.py): il modulo pubblico e le caselle."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ContactMessageWrite(BaseModel):
    """Il modulo del sito. Le lunghezze qui sono solo un tetto contro i
    corpi enormi: le regole vere (e i messaggi per chi scrive) sono in
    contact.clean_message."""

    name: str = Field(default="", max_length=200)
    email: str = Field(default="", max_length=300)
    phone: str | None = Field(default=None, max_length=60)
    message: str = Field(default="", max_length=6000)
    #: "Accetto di essere ricontattato": senza, il messaggio non si accetta.
    consent: bool = False
    locale: str | None = Field(default=None, max_length=5)
    #: Il campo trappola: nascosto alle persone, i robot lo riempiono.
    website: str | None = Field(default=None, max_length=300)


class ContactSentRead(BaseModel):
    ok: bool = True


class ContactClubRef(BaseModel):
    id: uuid.UUID
    name: str
    slug: str


class ContactMessageRead(BaseModel):
    id: uuid.UUID
    #: None = scritto a JudoArteVida.
    club: ContactClubRef | None
    name: str
    email: str
    phone: str | None
    message: str
    locale: str
    status: str
    created_at: datetime
    #: Quando è partita l'email di avviso; None se non è partita.
    emailed_at: datetime | None


class ContactInboxRead(BaseModel):
    items: list[ContactMessageRead]
    #: Quanti per stato (NEW, READ, ARCHIVED), per i contatori delle schede.
    counts: dict[str, int]


class ContactStatusWrite(BaseModel):
    status: str = Field(max_length=10)
