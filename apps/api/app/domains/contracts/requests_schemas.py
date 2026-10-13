import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from app.domains.contracts.schemas import ContractRead, _validate_email, _validate_iban


class ContractRequestAddress(BaseModel):
    street: str
    city: str
    province: str
    postal_code: str

    @field_validator("street", "city", "province", mode="before")
    @classmethod
    def required_text(cls, v: str | None) -> str:
        cleaned = " ".join((v or "").split())
        if not cleaned:
            raise ValueError("campo obbligatorio")
        return cleaned

    @field_validator("postal_code", mode="before")
    @classmethod
    def validate_postal_code(cls, v: str | None) -> str:
        cleaned = (v or "").strip()
        if len(cleaned) != 5 or not cleaned.isdigit():
            raise ValueError("CAP non valido: sono 5 cifre")
        return cleaned


class ContractRequestHolder(ContractRequestAddress):
    """Everything asked once, at the start of a pratica: the holder and the
    supply address. Name and email required; PEC and IBAN optional -- not
    everyone has a PEC, and an IBAN can be added later."""

    holder_first_name: str
    holder_last_name: str
    email: str
    pec: str | None = None
    iban: str | None = None
    #: Session 85: "il contratto è per": PRIVATE, or a business kind
    #: (COMPANY / SOLE_PROPRIETOR / CONDOMINIUM). Left out = the customer's
    #: kind. For a business, holder_first/last_name are the legal
    #: representative's, and company_name + legal_rep_fiscal_code are
    #: required (checked in contracts/requests.py, with the PEC).
    holder_kind: str | None = None
    company_name: str | None = None
    legal_rep_fiscal_code: str | None = None
    #: Session 89: a private holder's fiscal code, and the birth date and
    #: place (Belfiore code, from /contract-requests/birthplaces) of the
    #: holder or legal representative. Optional here so a page still open
    #: from before gets a clear message (contracts/requests.py) instead of a
    #: field error.
    holder_fiscal_code: str | None = None
    holder_birth_date: date | None = None
    holder_birth_place_code: str | None = None

    @field_validator("holder_kind", "company_name", "legal_rep_fiscal_code", "holder_fiscal_code", "holder_birth_place_code", mode="before")
    @classmethod
    def blank_kind_fields_to_none(cls, v: str | None) -> str | None:
        return " ".join((v or "").split()) or None

    @field_validator("holder_kind")
    @classmethod
    def validate_holder_kind(cls, v: str | None) -> str | None:
        if v is None:
            return None
        upper = v.upper()
        if upper not in {"PRIVATE", "SOLE_PROPRIETOR", "COMPANY", "CONDOMINIUM"}:
            raise ValueError("tipo di contratto non valido: privato o azienda")
        return upper

    @field_validator("holder_birth_date", mode="before")
    @classmethod
    def blank_date_to_none(cls, v: object) -> object:
        return None if v == "" else v

    @field_validator("legal_rep_fiscal_code", "holder_fiscal_code")
    @classmethod
    def validate_legal_rep_fiscal_code(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.replace(" ", "").upper()
        if len(cleaned) != 16 or not cleaned.isalnum():
            raise ValueError("codice fiscale non valido: sono 16 caratteri, lettere e numeri")
        return cleaned

    @field_validator("holder_first_name", "holder_last_name", mode="before")
    @classmethod
    def validate_name(cls, v: str | None) -> str:
        cleaned = " ".join((v or "").split())
        if not cleaned:
            raise ValueError("campo obbligatorio")
        return cleaned

    @field_validator("pec", "iban", mode="before")
    @classmethod
    def blank_to_none(cls, v: str | None) -> str | None:
        return (v or "").strip() or None

    @field_validator("pec")
    @classmethod
    def validate_pec(cls, v: str | None) -> str | None:
        return _validate_email(v)

    @field_validator("iban")
    @classmethod
    def validate_iban(cls, v: str | None) -> str | None:
        return _validate_iban(v)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        validated = _validate_email(v)
        if validated is None:
            raise ValueError("email obbligatoria")
        return validated


class ContractRequestCreate(ContractRequestHolder):
    #: Set by a promoter opening a pratica for one of their customers; left
    #: out by a customer opening their own.
    customer_id: uuid.UUID | None = None
    #: "Quanti POD hai?" (luce). `points_count` is the name this had before
    #: PDR existed, still accepted from an old page still open in a browser.
    pod_count: int | None = Field(default=None, ge=0)
    #: "Quanti PDR hai?" (gas).
    pdr_count: int = Field(default=0, ge=0)
    points_count: int = 1
    #: The contract the customer started from in the catalog, pre-chosen for
    #: every POD.
    product_version_id: uuid.UUID | None = None
    #: Staff only (Session 66): which promoter this pratica is attributed to.
    #: Left out, the customer's own referrer earns, as in self-service.
    producer_agent_id: uuid.UUID | None = None


class BirthplaceRead(BaseModel):
    #: Belfiore code: what the fiscal code carries (H501 = Roma, Z100 = Albania).
    code: str
    name: str
    #: Province, or EE for a foreign state.
    province: str
    foreign: bool
    #: False = a comune since suppressed or merged; `until` = the year.
    active: bool
    until: str | None = None


class ContractRequestPointsCount(BaseModel):
    #: POD (luce). `count` is the pre-PDR name, still accepted.
    pod_count: int | None = Field(default=None, ge=0)
    pdr_count: int | None = Field(default=None, ge=0)
    count: int | None = None


class ContractRequestNotes(BaseModel):
    notes: str | None = Field(default=None, max_length=2000)


class ContractRequestProductSet(BaseModel):
    product_version_id: uuid.UUID


class ContractRequestSummaryRead(BaseModel):
    id: uuid.UUID
    code: str
    customer_id: uuid.UUID
    customer_name: str | None = None
    #: The pratica's kind (Session 85: its own choice, else the customer's).
    customer_kind: str | None = None
    holder_kind: str | None = None
    #: DRAFT / SUBMITTED / CANCELLED
    status: str
    created_at: datetime
    submitted_at: datetime | None = None
    updated_at: datetime | None = None
    created_by_role: str | None = None
    #: The message left for the administration (Session 83).
    notes: str | None = None
    activated_by_promoter_id: uuid.UUID | None = None
    activated_by_promoter_name: str | None = None
    holder_name: str | None = None
    points_total: int = 0
    points_by_status: dict[str, int] = {}
    points_active: int = 0
    points_to_review: int = 0
    points_documents_pending: int = 0
    points_without_package: int = 0
    points_paid: int = 0
    points_payable: int = 0
    #: Sum of the frozen prices of the points still alive (not rejected or
    #: cancelled), VAT included where it applies.
    total_gross_cents: int = 0
    payment_plans: list[str] = []
    instalments_failed: int = 0
    #: Session 65: the customer announced a bank transfer, not yet confirmed.
    bank_transfer_pending: bool = False
    bank_transfer_total_cents: int | None = None
    bank_transfer_requested_at: datetime | None = None
    payment_proof_uploaded_at: datetime | None = None
    #: What was actually paid for the paid points (list price minus discounts).
    total_paid_cents: int = 0


class ContractRequestPointRead(ContractRead):
    #: 1-based order of the POD in the pratica: "POD 1", "POD 2"...
    position: int = 0
    #: "POD" (luce) or "PDR" (gas): what the point is called on screen.
    point_kind: str = "POD"
    meter_number: str | None = None
    street: str | None = None
    city: str | None = None
    province: str | None = None
    postal_code: str | None = None
    product_id: uuid.UUID | None = None
    documents_missing: int = 0
    documents_rejected: int = 0
    instalments_total: int | None = None
    instalments_paid: int = 0
    instalments_failed: int = 0
    billing_active: bool = False


class ContractRequestCheckoutRead(BaseModel):
    id: uuid.UUID
    created_at: datetime
    payment_plan: str
    total_cents: int
    instalment_cents: int
    contracts: int
    completed_at: datetime | None = None
    stripe_checkout_session_id: str
    stripe_subscription_id: str | None = None
    outcome: str | None = None


class ContractRequestDetailRead(ContractRequestSummaryRead):
    #: Document types the pratica still lacks before it may go on (identity,
    #: bill, visura / P.IVA for a business). Empty = documents done.
    documents_blocking: list[str] = []
    #: Who last wrote `notes` and when -- "Promoter Mario Bianchi", "Cliente (...)".
    notes_author: str | None = None
    notes_updated_at: datetime | None = None
    street: str | None = None
    city: str | None = None
    province: str | None = None
    postal_code: str | None = None
    holder_first_name: str | None = None
    holder_last_name: str | None = None
    email: str | None = None
    pec: str | None = None
    iban: str | None = None
    company_name: str | None = None
    legal_rep_fiscal_code: str | None = None
    holder_fiscal_code: str | None = None
    holder_birth_date: date | None = None
    holder_birth_place: str | None = None
    holder_birth_place_code: str | None = None
    #: Session 89: what in the fiscal code does not match the signer's data --
    #: shown as a warning, it never blocks the pratica.
    fiscal_code_problems: list[str] = []
    points: list[ContractRequestPointRead] = []
    #: Staff only -- empty for customers and promoters.
    checkouts: list[ContractRequestCheckoutRead] = []


class ContractRequestPaymentLineRead(BaseModel):
    contract_id: uuid.UUID
    label: str
    #: In one go.
    gross_cents: int
    #: Session 84: in rate (3 or 12, same total) -- monthly price x 12 + VAT.
    instalments_gross_cents: int = 0


class ContractRequestPaymentOptionRead(BaseModel):
    key: str
    label: str
    description: str
    instalments: int
    #: What the customer is charged each month (or once), all points together.
    instalment_cents: int
    total_cents: int
    rounding_difference_cents: int
    available: bool
    unavailable_reason: str | None = None
    #: Session 64: price before the one-go discount, the discount, and the
    #: JavCash this option earns (lower when discounted: it follows what is paid).
    list_total_cents: int = 0
    discount_percentage: int = 0
    discount_cents: int = 0
    cashback_cents: int = 0


class ContractRequestPaymentOptionsRead(BaseModel):
    contract_request_id: uuid.UUID
    card_available: bool
    #: The contracts this payment would cover: sent, priced, not yet paid.
    lines: list[ContractRequestPaymentLineRead]
    total_gross_cents: int
    #: Session 85: every amount on this screen is VAT included; True when
    #: there is VAT in it (a business pratica), so the page can say so.
    vat_included: bool = False
    options: list[ContractRequestPaymentOptionRead]
    points_paid: int
    #: What the customer earns in JavCash across these contracts.
    cashback_total_cents: int
    #: PER_INSTALMENT / UPFRONT -- on an instalment plan, whether that
    #: cashback arrives a slice per instalment or all at the first one.
    cashback_mode: str = "PER_INSTALMENT"
    #: Session 65: paying by bank transfer (single payment, same discount).
    bank_transfer_available: bool = False
    bank_transfer_pending: bool = False
    bank_transfer_total_cents: int | None = None
    bank_transfer_requested_at: datetime | None = None
    payment_proof_uploaded_at: datetime | None = None
    bank_iban: str | None = None
    bank_account_holder: str | None = None
    bank_transfer_instructions: str | None = None
    bank_transfer_reference: str | None = None


class ContractRequestCheckoutRequest(BaseModel):
    payment_plan: str
