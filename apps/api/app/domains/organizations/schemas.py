import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.normalization import normalize_email


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: str


class OrganizationSettingsRead(BaseModel):
    """Subset of Organization.settings (JSONB) that has a typed shape --
    admin-editable company configuration, starting with the bank account
    customers wire bonifico payments to (orders, Shop orders, contracts).
    Deliberately NOT the whole raw
    settings dict: only fields with a real schema here are ever
    read/written through this endpoint, so an admin can't accidentally
    stuff arbitrary JSON into it."""

    bank_iban: str | None
    bank_account_holder: str | None
    # Free-text shown alongside the IBAN wherever a customer is told to pay
    # by bank transfer (an order's residual, a contract) -- e.g.
    # "Includi il codice fattura nella causale" or bank-specific notes. Kept
    # separate from the IBAN itself so an admin can update the wording
    # without re-typing the account number.
    bank_transfer_instructions: str | None
    # Where the "a new ticket was opened" admin alert email goes (see
    # support/service.py::create_ticket). Falls back to a placeholder when
    # unset -- see organizations/service.py::get_admin_notification_email.
    admin_notification_email: str | None
    #: PER_INSTALMENT (default) / UPFRONT -- how a contract paid in
    #: instalments earns its cashback; see organizations/service.py.
    contract_instalment_cashback_mode: str | None = None
    #: Discount (%) on a contract paid in one go; None = default (32).


class OrganizationSettingsUpdate(BaseModel):
    bank_iban: str | None = Field(default=None, max_length=42)
    bank_account_holder: str | None = Field(default=None, max_length=255)
    bank_transfer_instructions: str | None = Field(default=None, max_length=2000)
    admin_notification_email: str | None = Field(default=None, max_length=255)
    contract_instalment_cashback_mode: Literal["PER_INSTALMENT", "UPFRONT"] | None = None

    @field_validator("admin_notification_email", mode="before")
    @classmethod
    def normalize_email_field(cls, v: object) -> object:
        return normalize_email(v) if isinstance(v, str) else v


class PaymentInfoRead(BaseModel):
    """GET /organizations/me/payment-info -- what any signed-in user may know
    to pay by bank transfer. `iban` null means not configured yet: the UI
    shows "contatta l'amministrazione" instead of an IBAN."""

    iban: str | None
    holder: str | None
    instructions: str | None
