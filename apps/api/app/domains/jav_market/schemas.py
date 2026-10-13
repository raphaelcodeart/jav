"""Cosa il browser può dire a «Fai la Spesa con Jav».

Mai un totale e mai un prezzo d'ordine: il checkout ricalcola tutto dal
catalogo (CLAUDE.md §5). I prezzi qui dentro compaiono solo dove è
l'amministratore a scriverli, cioè nel catalogo.
"""

import uuid

from pydantic import BaseModel, Field


class JavMarketSettingsRead(BaseModel):
    enabled: bool
    #: Session 80: l'ordine pagato parte da solo verso le aziende.
    auto_forward: bool
    shipping_mode: str
    shipping_flat_cents: int
    shipping_days: str | None
    ship_to_country: str
    #: Merce IVA inclusa sotto cui non si ordina; 0 = nessun minimo.
    min_order_cents: int
    #: Merce IVA inclusa da cui la spedizione è gratis; None = mai.
    free_shipping_threshold_cents: int | None


class JavMarketSettingsUpdate(BaseModel):
    enabled: bool | None = None
    auto_forward: bool | None = None
    shipping_mode: str | None = None
    shipping_flat_cents: int | None = Field(default=None, ge=0, le=100000)
    shipping_days: str | None = Field(default=None, max_length=32)
    ship_to_country: str | None = Field(default=None, min_length=2, max_length=2)
    min_order_cents: int | None = Field(default=None, ge=0, le=10_000_000)
    #: 0 spegne la spedizione gratuita (diventa NULL).
    free_shipping_threshold_cents: int | None = Field(default=None, ge=0, le=10_000_000)


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
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    image_url: str | None = Field(default=None, max_length=1000)
    images: list[str] | None = None
    status: str | None = None
    credit_discount_percentage: int | None = Field(default=None, ge=0, le=99)
    unit_cost_cents: int | None = Field(default=None, ge=0)
    producer_id: uuid.UUID | None = None


class JavMarketAddress(BaseModel):
    recipient_name: str = Field(min_length=2, max_length=128)
    recipient_phone: str | None = Field(default=None, max_length=32)
    address_line1: str = Field(min_length=3, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str = Field(min_length=1, max_length=128)
    province: str = Field(min_length=1, max_length=64)
    postal_code: str = Field(min_length=3, max_length=16)


class JavMarketOrderSelfCreateRequest(BaseModel):
    variant_id: uuid.UUID
    quantity: int = Field(ge=1, le=10)
    address: JavMarketAddress
    credit_applied_cents: int = Field(default=0, ge=0)
    payment_method: str = "BANK_TRANSFER"
    otp_code: str | None = None
    note: str | None = Field(default=None, max_length=1000)


class JavMarketCartOrderRequest(BaseModel):
    """Il checkout del carrello: cosa si compra lo dice il carrello sul
    server, non il browser."""

    address: JavMarketAddress
    credit_applied_cents: int = Field(default=0, ge=0)
    payment_method: str = "BANK_TRANSFER"
    otp_code: str | None = None
    note: str | None = Field(default=None, max_length=1000)


class JavMarketCartCreditOtpRequest(BaseModel):
    credit_applied_cents: int = Field(ge=1)


class JavMarketOrderCreditOtpRequest(BaseModel):
    variant_id: uuid.UUID
    quantity: int = Field(ge=1, le=10)
    credit_applied_cents: int = Field(ge=1)


class JavMarketOrderCancelRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class JavMarketOrderPaymentMethodUpdate(BaseModel):
    payment_method: str


class JavMarketShipRequest(BaseModel):
    tracking_number: str | None = Field(default=None, max_length=128)
    tracking_url: str | None = Field(default=None, max_length=1000)
    tracking_company: str | None = Field(default=None, max_length=128)


class CheckoutSessionRead(BaseModel):
    checkout_url: str
