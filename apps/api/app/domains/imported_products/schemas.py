import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ImportProviderCreate(BaseModel):
    provider_type: str
    name: str = Field(min_length=1, max_length=128)
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, max_length=500)
    enabled: bool = True


class ImportProviderUpdate(BaseModel):
    """All optional -- only fields actually present in the request overwrite
    (exclude_unset, same discipline as organizations/service.py::
    update_payment_settings), so leaving api_key out of a PATCH that's only
    renaming the provider never blanks out an already-stored key."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, max_length=500)
    #: AliExpress DS app (Session 71), same masking discipline as api_key.
    app_key: str | None = Field(default=None, max_length=64)
    app_secret: str | None = Field(default=None, max_length=255)
    enabled: bool | None = None


class ImportProviderRead(BaseModel):
    """api_key is never returned raw -- same masked-last4 convention as
    organizations/service.py::get_payment_settings's Stripe secret key."""

    id: uuid.UUID
    provider_type: str
    name: str
    base_url: str | None
    api_key_configured: bool
    api_key_last4: str | None
    app_key: str | None
    app_secret_configured: bool
    app_secret_hint: str | None
    #: The seller account is authorised and the token is still usable.
    connected: bool
    account_label: str | None
    token_expires_at: datetime | None
    last_connected_at: datetime | None
    enabled: bool
    created_at: datetime


class AliexpressAuthorizeUrlRead(BaseModel):
    url: str
    #: The exact address to register in the AliExpress app ("Callback URL").
    callback_url: str


class AliexpressTestRead(BaseModel):
    provider: ImportProviderRead
    #: A few real category names, proof the DS permission is live.
    sample_categories: list[str]


class ImportedProductCreate(BaseModel):
    provider_id: uuid.UUID
    external_id: str | None = Field(default=None, max_length=255)
    external_url: str | None = Field(default=None, max_length=1000)
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=2000)
    image_url: str | None = Field(default=None, max_length=1000)
    price_cents: int = Field(gt=0)
    credit_discount_percentage: int = Field(default=30, ge=0, le=99)
    status: str = "ACTIVE"


class ImportedProductUpdate(BaseModel):
    external_id: str | None = Field(default=None, max_length=255)
    external_url: str | None = Field(default=None, max_length=1000)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    image_url: str | None = Field(default=None, max_length=1000)
    price_cents: int | None = Field(default=None, gt=0)
    credit_discount_percentage: int | None = Field(default=None, ge=0, le=99)
    status: str | None = None


class ImportedProductAdminRead(BaseModel):
    """Full detail, including the provider/external linkage -- admin catalog
    view only. See ImportedProductRead for the customer-facing shape."""

    id: uuid.UUID
    provider_id: uuid.UUID
    provider_name: str
    external_id: str | None
    external_url: str | None
    name: str
    description: str
    image_url: str | None
    price_cents: int
    credit_discount_percentage: int
    status: str
    created_at: datetime
    #: The Shop categories this product carries (shop_categories, Session
    #: 73). These rows are shown inside the AliExpress tab, so they are
    #: categorised under the "aliexpress" shop like everything else there.
    category_ids: list[uuid.UUID] = []


class ImportedProductRead(BaseModel):
    """Customer-facing shop card -- deliberately omits provider_id/
    external_id/external_url, so nothing in the API response hints these
    are AliExpress-sourced items (see models.py::ImportedProduct's
    docstring)."""

    id: uuid.UUID
    name: str
    description: str
    image_url: str | None
    price_cents: int
    credit_discount_percentage: int
    #: price_cents is the full (card) price; bank transfer takes this % off.
    bank_transfer_discount_percentage: int = 0
    #: See ImportedProductAdminRead.category_ids -- the customer filters the
    #: grid with these without a call per product.
    category_ids: list[uuid.UUID] = []


class ImportedOrderRead(BaseModel):
    """Same shape as orders/schemas.py::OrderRead minus every cashback
    field -- an imported-product order never has one."""

    id: uuid.UUID
    customer_user_id: uuid.UUID
    customer_display_name: str
    imported_product_id: uuid.UUID
    product_name: str
    product_image_url: str | None = None
    created_by_user_id: uuid.UUID
    amount_cents: int
    credit_applied_cents: int
    residual_amount_cents: int
    #: Taken off by bank transfer (frozen), and residual minus that discount.
    bank_transfer_discount_cents: int = 0
    amount_due_cents: int = 0
    bank_transfer_discount_percentage: int = 0
    #: Session 74: the VAT contained in what is charged, frozen on the order
    #: -- the price shown is VAT included, nothing is added to it.
    vat_percentage: int = 0
    vat_amount_cents: int = 0
    status: str
    payment_method: str
    stripe_checkout_session_id: str | None = None
    payment_proof_uploaded_at: datetime | None = None
    note: str | None
    paid_at: datetime | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    created_at: datetime


class ImportedOrderQuoteRead(BaseModel):
    imported_product_id: uuid.UUID
    product_name: str
    amount_cents: int
    credit_discount_percentage: int
    max_creditable_cents: int
    customer_wallet_balance_cents: int
    bank_transfer_available: bool
    card_available: bool
    bank_transfer_discount_percentage: int = 0
    #: amount_cents paid entirely by bank transfer, discount taken off.
    bank_transfer_amount_cents: int = 0


class ImportedOrderCreateRequest(BaseModel):
    customer_user_id: uuid.UUID
    imported_product_id: uuid.UUID
    credit_applied_cents: int = Field(default=0, ge=0)
    payment_method: str = "BANK_TRANSFER"
    note: str | None = Field(default=None, max_length=1000)


class ImportedOrderSelfCreateRequest(BaseModel):
    imported_product_id: uuid.UUID
    credit_applied_cents: int = Field(default=0, ge=0)
    payment_method: str = "BANK_TRANSFER"
    otp_code: str | None = None
    note: str | None = Field(default=None, max_length=1000)


class ImportedOrderCreditOtpRequest(BaseModel):
    imported_product_id: uuid.UUID
    credit_applied_cents: int = Field(gt=0)


class ImportedOrderCancelRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class ImportedOrderPaymentMethodUpdate(BaseModel):
    payment_method: str


class PaymentProofUrlRead(BaseModel):
    url: str


class CheckoutSessionRead(BaseModel):
    checkout_url: str
