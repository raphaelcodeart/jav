"""Cosa il browser può dire al «Marketplace SOLEIL».

Mai un totale e mai un prezzo d'ordine: il checkout ricalcola tutto dal
catalogo (CLAUDE.md §5).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SoleilMarketSettingsRead(BaseModel):
    enabled: bool
    markup_percentage: int = 0
    credit_percentage: int = 30
    #: FIXED = credit_percentage per tutti; MARGIN = credit_margin_share% del guadagno.
    credit_mode: str = "FIXED"
    credit_margin_share: int = 50
    #: il prezzo di vendita del file SoleilDrop ha già l'IVA dentro.
    prices_include_vat: bool = True
    #: Quanto ci costa spedire un prodotto: entra solo nel calcolo del guadagno.
    shipping_cost_cents: int = 500
    last_import_at: datetime | None = None
    last_import_summary: str | None = None
    last_import_error: str | None = None
    #: API affiliati SoleilDrop (13/10/2026). Mai la chiave né il segreto.
    api_configured: bool = False
    api_key_hint: str | None = None
    webhook_configured: bool = False
    #: L'indirizzo da incollare nell'area SoleilDrop, sezione Webhook.
    webhook_url: str | None = None
    auto_import: bool = True
    eshop_name: str | None = None
    wallet_balance_cents: int | None = None
    last_api_check_at: datetime | None = None
    last_api_error: str | None = None
    last_webhook_at: datetime | None = None
    last_order_sync_at: datetime | None = None
    #: Session 80: l'ordine pagato parte da solo verso le aziende.
    auto_forward: bool
    shipping_mode: str
    shipping_flat_cents: int
    shipping_days: str | None
    ship_to_country: str


class SoleilMarketSettingsUpdate(BaseModel):
    enabled: bool | None = None
    #: Stringa vuota = togli. Si scrivono, non tornano mai indietro.
    api_key: str | None = Field(default=None, max_length=255)
    webhook_secret: str | None = Field(default=None, max_length=255)
    auto_import: bool | None = None
    markup_percentage: int | None = Field(default=None, ge=0, le=500)
    #: La percentuale JavCash di tutti i prodotti non personalizzati. Mai 100.
    credit_percentage: int | None = Field(default=None, ge=0, le=99)
    credit_mode: str | None = Field(default=None, pattern="^(FIXED|MARGIN)$")
    credit_margin_share: int | None = Field(default=None, ge=0, le=100)
    prices_include_vat: bool | None = None
    shipping_cost_cents: int | None = Field(default=None, ge=0, le=100000)
    auto_forward: bool | None = None
    shipping_mode: str | None = None
    shipping_flat_cents: int | None = Field(default=None, ge=0, le=100000)
    shipping_days: str | None = Field(default=None, max_length=32)
    ship_to_country: str | None = Field(default=None, min_length=2, max_length=2)


class ProducerWrite(BaseModel):
    """L'azienda che produce la merce. `name` è l'unico obbligatorio: il
    resto si compila quando si sa, senza bloccare chi sta caricando."""

    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4000)
    website_url: str | None = Field(default=None, max_length=1000)
    logo_url: str | None = Field(default=None, max_length=1000)
    vat_number: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    address: str | None = Field(default=None, max_length=500)


class ProducerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    website_url: str | None = Field(default=None, max_length=1000)
    logo_url: str | None = Field(default=None, max_length=1000)
    vat_number: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    address: str | None = Field(default=None, max_length=500)
    active: bool | None = None


class VariantWrite(BaseModel):
    label: str = Field(default="Unica", max_length=255)
    sku: str | None = Field(default=None, max_length=128)
    image_url: str | None = Field(default=None, max_length=1000)
    price_cents: int = Field(gt=0, le=10_000_000)
    #: `None` = scorta non gestita. Zero = esaurito.
    inventory: int | None = Field(default=None, ge=0)
    active: bool = True


class VariantUpdate(BaseModel):
    #: False = il prezzo torna al costo più ricarico.
    price_locked: bool | None = None
    label: str | None = Field(default=None, max_length=255)
    sku: str | None = Field(default=None, max_length=128)
    image_url: str | None = Field(default=None, max_length=1000)
    price_cents: int | None = Field(default=None, gt=0, le=10_000_000)
    inventory: int | None = Field(default=None, ge=0)
    active: bool | None = None


class ProductWrite(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=8000)
    image_url: str | None = Field(default=None, max_length=1000)
    images: list[str] = Field(default_factory=list)
    status: str = "ACTIVE"
    #: Quanto del prezzo si paga in JavCash. Mai 100: è la regola comune.
    credit_discount_percentage: int = Field(default=30, ge=0, le=99)
    unit_cost_cents: int | None = Field(default=None, ge=0)
    producer_id: uuid.UUID | None = None
    #: Almeno una: un prodotto senza varianti non sarebbe comprabile.
    variants: list[VariantWrite] = Field(min_length=1)


class ProductUpdate(BaseModel):
    #: False = la percentuale JavCash torna a quella del negozio.
    credit_locked: bool | None = None
    #: Il ricarico di questo prodotto; null = quello del negozio.
    markup_percentage: int | None = Field(default=None, ge=0, le=500)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    image_url: str | None = Field(default=None, max_length=1000)
    images: list[str] | None = None
    status: str | None = None
    credit_discount_percentage: int | None = Field(default=None, ge=0, le=99)
    unit_cost_cents: int | None = Field(default=None, ge=0)
    producer_id: uuid.UUID | None = None


class SoleilMarketAddress(BaseModel):
    recipient_name: str = Field(min_length=2, max_length=128)
    recipient_phone: str | None = Field(default=None, max_length=32)
    address_line1: str = Field(min_length=3, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str = Field(min_length=1, max_length=128)
    province: str = Field(min_length=1, max_length=64)
    postal_code: str = Field(min_length=3, max_length=16)


class SoleilMarketOrderSelfCreateRequest(BaseModel):
    variant_id: uuid.UUID
    quantity: int = Field(ge=1, le=10)
    address: SoleilMarketAddress
    credit_applied_cents: int = Field(default=0, ge=0)
    payment_method: str = "BANK_TRANSFER"
    otp_code: str | None = None
    note: str | None = Field(default=None, max_length=1000)


class SoleilMarketCartOrderRequest(BaseModel):
    """Il checkout del carrello: cosa si compra lo dice il carrello sul
    server, non il browser."""

    address: SoleilMarketAddress
    credit_applied_cents: int = Field(default=0, ge=0)
    payment_method: str = "BANK_TRANSFER"
    otp_code: str | None = None
    note: str | None = Field(default=None, max_length=1000)


class SoleilMarketCartCreditOtpRequest(BaseModel):
    credit_applied_cents: int = Field(ge=1)


class SoleilMarketOrderCreditOtpRequest(BaseModel):
    variant_id: uuid.UUID
    quantity: int = Field(ge=1, le=10)
    credit_applied_cents: int = Field(ge=1)


class SoleilMarketOrderCancelRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class SoleilMarketOrderPaymentMethodUpdate(BaseModel):
    payment_method: str


class SoleilMarketShipRequest(BaseModel):
    tracking_number: str | None = Field(default=None, max_length=128)
    tracking_url: str | None = Field(default=None, max_length=1000)
    tracking_company: str | None = Field(default=None, max_length=128)


class CheckoutSessionRead(BaseModel):
    checkout_url: str


class BulkStatusRequest(BaseModel):
    """Accendi o spegni in blocco, per marca e/o categoria SoleilDrop."""

    status: str
    producer_id: uuid.UUID | None = None
    subcategory: str | None = Field(default=None, max_length=64)
    category_name: str | None = Field(default=None, max_length=64)
