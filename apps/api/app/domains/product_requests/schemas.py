import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.domains.product_requests.models import REQUEST_STATUSES


class ProductRequestMessageRead(BaseModel):
    id: uuid.UUID
    request_id: uuid.UUID
    author_user_id: uuid.UUID
    author_role: str
    author_name: str | None = None
    body: str
    created_at: datetime


class ProductRequestRead(BaseModel):
    id: uuid.UUID
    opened_by_user_id: uuid.UUID
    opened_by_role: str
    opened_by_name: str | None = None
    product_name: str
    reference_url: str | None
    status: str
    created_at: datetime
    message_count: int = 0
    last_message_at: datetime | None = None
    # Chi ha scritto per ultimo: dice all'amministratore quali richieste
    # aspettano una sua risposta, e al cliente quali hanno una novità.
    last_author_role: str | None = None


class ProductRequestDetailRead(ProductRequestRead):
    messages: list[ProductRequestMessageRead] = []


class ProductRequestCreate(BaseModel):
    product_name: str = Field(min_length=2, max_length=255)
    message: str = Field(min_length=1, max_length=5000)
    reference_url: str | None = Field(default=None, max_length=1000)

    @field_validator("product_name", "message")
    @classmethod
    def strip_text(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Campo obbligatorio")
        return v

    @field_validator("reference_url")
    @classmethod
    def blank_url_is_none(cls, v: str | None) -> str | None:
        v = (v or "").strip()
        return v or None


class ProductRequestMessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class ProductRequestStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in REQUEST_STATUSES:
            raise ValueError(f"status must be one of {sorted(REQUEST_STATUSES)}")
        return v
