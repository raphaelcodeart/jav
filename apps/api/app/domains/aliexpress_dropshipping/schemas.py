import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.domains.marketplaces.rules import MAX_CREDIT_PERCENTAGE


class AliexpressSettingsRead(BaseModel):
    """The App Secret and the tokens are never returned: only whether they
    are saved and the last four characters, as for the Stripe keys."""

    app_key: str | None
    app_secret_configured: bool
    app_secret_hint: str | None
    #: True once the seller account has been authorised (a token is stored).
    connected: bool
    account_label: str | None
    token_expires_at: datetime | None
    last_connected_at: datetime | None
    enabled: bool
    ship_to_country: str
    target_currency: str
    target_language: str
    currency_rate: float
    price_basis: str
    markup_percentage: int
    markup_fixed_cents: int
    price_rounding: str
    shipping_mode: str
    shipping_minimum_cents: int
    shipping_days: str | None
    default_credit_percentage: int
    max_credit_percentage: int
    auto_forward: bool


class AliexpressSettingsUpdate(BaseModel):
    """Only the fields sent are changed: a PATCH that moves the markup never
    blanks the stored App Secret."""

    app_key: str | None = Field(default=None, max_length=64)
    app_secret: str | None = Field(default=None, max_length=255)
    enabled: bool | None = None
    ship_to_country: str | None = Field(default=None, min_length=2, max_length=2)
    target_currency: str | None = Field(default=None, min_length=3, max_length=3)
    target_language: str | None = Field(default=None, min_length=2, max_length=8)
    currency_rate: float | None = Field(default=None, gt=0.001, lt=1000)
    price_basis: str | None = None
    markup_percentage: int | None = Field(default=None, ge=0, le=1000)
    markup_fixed_cents: int | None = Field(default=None, ge=0, le=100000)
    price_rounding: str | None = None
    shipping_mode: str | None = None
    #: La spesa di spedizione minima addebitata al cliente (Session 76):
    #: si paga il costo reale AliExpress, e questo quando è più basso.
    shipping_minimum_cents: int | None = Field(default=None, ge=0, le=100000)
    shipping_days: str | None = Field(default=None, max_length=32)
    default_credit_percentage: int | None = Field(default=None, ge=0, le=MAX_CREDIT_PERCENTAGE)
    auto_forward: bool | None = None


class AliexpressAuthorizeUrlRead(BaseModel):
    url: str
    #: The exact address to register in the AliExpress app ("Callback URL").
    callback_url: str


class AliexpressImportRequest(BaseModel):
    product_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    credit_discount_percentage: int | None = Field(default=None, ge=0, le=MAX_CREDIT_PERCENTAGE)
    markup_percentage: int | None = Field(default=None, ge=0, le=1000)
    variant_ids: list[str] | None = None
    activate: bool = True


class AliexpressProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    image_url: str | None = Field(default=None, max_length=1000)
    status: str | None = Field(default=None, pattern="^(ACTIVE|INACTIVE)$")
    credit_discount_percentage: int | None = Field(default=None, ge=0, le=MAX_CREDIT_PERCENTAGE)
    markup_percentage: int | None = Field(default=None, ge=0, le=1000)


class AliexpressVariantUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=255)
    active: bool | None = None
    price_override_cents: int | None = Field(default=None, gt=0)


class AliexpressAddress(BaseModel):
    recipient_name: str = Field(min_length=2, max_length=50)
    recipient_phone: str = Field(min_length=6, max_length=20)
    address_line1: str = Field(min_length=3, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str = Field(min_length=1, max_length=50)
    province: str = Field(min_length=1, max_length=50)
    postal_code: str = Field(min_length=3, max_length=12)


class AliexpressOrderCreditOtpRequest(BaseModel):
    variant_id: uuid.UUID
    quantity: int = Field(ge=1, le=10)
    credit_applied_cents: int = Field(gt=0)


class AliexpressOrderSelfCreateRequest(BaseModel):
    variant_id: uuid.UUID
    quantity: int = Field(ge=1, le=10)
    address: AliexpressAddress
    credit_applied_cents: int = Field(default=0, ge=0)
    payment_method: str = "BANK_TRANSFER"
    otp_code: str | None = None
    note: str | None = Field(default=None, max_length=1000)


class AliexpressCartOrderRequest(BaseModel):
    """Il checkout del carrello: nessun `variant_id`, nessuna `quantity`.
    Cosa si sta comprando lo dice il carrello sul server, non il browser."""

    address: AliexpressAddress
    credit_applied_cents: int = Field(default=0, ge=0)
    payment_method: str = "BANK_TRANSFER"
    otp_code: str | None = None
    note: str | None = Field(default=None, max_length=1000)


class AliexpressCartCreditOtpRequest(BaseModel):
    credit_applied_cents: int = Field(ge=1)


class AliexpressOrderCancelRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class AliexpressOrderPaymentMethodUpdate(BaseModel):
    payment_method: str


class CheckoutSessionRead(BaseModel):
    checkout_url: str


class PaymentProofUrlRead(BaseModel):
    url: str
