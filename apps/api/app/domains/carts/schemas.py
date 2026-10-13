"""Cosa il browser può dire al carrello: un articolo e una quantità.

Mai un prezzo, mai un totale. Il carrello li ricalcola a ogni lettura
(CLAUDE.md §5), quindi non c'è nulla da mandare e nulla da fidarsi.
"""

import uuid

from pydantic import BaseModel, Field

from app.domains.carts.models import MAX_ITEM_QUANTITY


class CartItemAddRequest(BaseModel):
    variant_id: uuid.UUID
    quantity: int = Field(default=1, ge=1, le=MAX_ITEM_QUANTITY)


class CartItemQuantityUpdate(BaseModel):
    #: Zero è ammesso e vuol dire "togli": è quello che si aspetta chi porta
    #: il contatore a zero, invece di vedersi rifiutare l'operazione.
    quantity: int = Field(ge=0, le=MAX_ITEM_QUANTITY)
