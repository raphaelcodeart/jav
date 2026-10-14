"""Gli schemi della contabilità (club/accounting.py): club, piattaforma,
famiglia. Gli importi sono sempre in centesimi e sempre calcolati dal
server; il browser sceglie solo il periodo."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.domains.club.schemas import FeeRead


class FiguresRead(BaseModel):
    income_cents: int
    income_by_kind: dict[str, int]
    credit_cents: int
    issued_cents: int
    issued_paid_cents: int
    #: Percentuale (0-100) delle quote emesse nel periodo già pagate; null se non ne è stata emessa nessuna.
    collection_rate: int | None
    discounts_cents: int
    absence_cents: int
    waived_cents: int
    missed_cents: int
    expenses_cents: int
    expenses_by_category: dict[str, int]
    staff_cents: int
    staff_minutes: int
    #: Corsi JAV: la parte dei treinador delle mensilità pagate, e ciò che
    #: resta all'unità (la parte di JAV). 0 e = incasso nei club ufficiali.
    coach_share_cents: int = 0
    kept_cents: int = 0
    costs_cents: int
    platform_fee_cents: int
    result_cents: int


class SeriesPointRead(BaseModel):
    month: str
    income_cents: int
    costs_cents: int
    platform_fee_cents: int
    result_cents: int


class AgingBucketRead(BaseModel):
    cents: int
    count: int


class DebtorRead(BaseModel):
    user_id: uuid.UUID
    name: str
    due_cents: int
    overdue_cents: int
    fees: int
    oldest_due_date: date
    days_overdue: int


class DebtsRead(BaseModel):
    total_cents: int
    overdue_cents: int
    families: int
    aging: dict[str, AgingBucketRead]
    top: list[DebtorRead]


class ForecastRead(BaseModel):
    expected_cents: int
    income_cents: int
    platform_fee_cents: int
    result_cents: int


class ClubSummaryRead(BaseModel):
    period: str
    kind: str
    #: CLUB o JAV_COURSES (club/kinds.py).
    club_kind: str | None = None
    start: date
    end: date
    platform_fee_pct: Decimal
    totals: FiguresRead
    compared_months: list[str]
    current: FiguresRead
    previous: FiguresRead
    series: list[SeriesPointRead]
    ytd: FiguresRead | None
    ytd_previous: FiguresRead | None
    forecast: ForecastRead | None
    debts: DebtsRead


class LedgerRowRead(BaseModel):
    id: str
    date: date
    #: INCOME / EXPENSE / STAFF (dal cartellino) / PLATFORM_FEE (calcolata).
    type: str
    category: str
    description: str
    counterparty: str
    family: str
    #: Positivo le entrate, negativo le uscite.
    amount_cents: int
    method: str
    has_receipt: bool
    expense_id: uuid.UUID | None
    recurring: bool
    computed: bool


class LedgerRead(BaseModel):
    rows: list[LedgerRowRead]
    truncated: bool
    in_cents: int
    out_cents: int


class ExpenseRead(BaseModel):
    id: uuid.UUID
    spent_on: date
    category: str
    amount_cents: int
    description: str
    supplier: str | None
    payment_method: str
    has_receipt: bool
    receipt_filename: str | None
    recurring_id: uuid.UUID | None
    period: str | None
    created_at: datetime


class ExpenseWrite(BaseModel):
    spent_on: date | None = None
    category: str = Field(max_length=16)
    amount_cents: int = Field(gt=0, le=100_000_000)
    description: str = Field(min_length=2, max_length=200)
    supplier: str | None = Field(default=None, max_length=200)
    payment_method: str = Field(default="BANK_TRANSFER", max_length=16)


class ExpenseUpdate(BaseModel):
    spent_on: date | None = None
    category: str | None = Field(default=None, max_length=16)
    amount_cents: int | None = Field(default=None, gt=0, le=100_000_000)
    description: str | None = Field(default=None, min_length=2, max_length=200)
    supplier: str | None = Field(default=None, max_length=200)
    payment_method: str | None = Field(default=None, max_length=16)


class RecurringRead(BaseModel):
    id: uuid.UUID
    category: str
    amount_cents: int
    description: str
    supplier: str | None
    payment_method: str
    day_of_month: int
    starts_on: date
    ends_on: date | None
    active: bool


class RecurringWrite(ExpenseWrite):
    day_of_month: int = Field(default=1, ge=1, le=28)
    starts_on: date | None = None
    ends_on: date | None = None


class RecurringUpdate(ExpenseUpdate):
    day_of_month: int | None = Field(default=None, ge=1, le=28)
    starts_on: date | None = None
    ends_on: date | None = None
    active: bool | None = None


class StaffCostRead(BaseModel):
    user_id: uuid.UUID
    name: str
    minutes: int
    hourly_rate_cents: int | None
    rate_valid_from: date | None
    cost_cents: int


class StaffRateWrite(BaseModel):
    user_id: uuid.UUID
    hourly_rate_cents: int = Field(ge=0, le=100_000)
    valid_from: date | None = None


class PlatformFeeWrite(BaseModel):
    pct: Decimal = Field(ge=0, le=100, decimal_places=2)


class PlatformFeeRead(BaseModel):
    club_id: uuid.UUID
    pct: Decimal
    #: False nei corsi JAV: la percentuale è fissa a 0.
    editable: bool = True
    history: list[dict] = []


# --- Piattaforma ----------------------------------------------------------------------------------


class PlatformClubRead(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    status: str
    kind: str = "CLUB"
    platform_fee_pct: Decimal
    athletes_active: int
    families: int
    month: FiguresRead
    year: FiguresRead
    platform_fee_all_time_cents: int
    debt_cents: int
    overdue_cents: int
    aging: dict[str, AgingBucketRead]


class PlatformCoursesUnitRead(PlatformClubRead):
    """L'unità dei corsi JAV, a parte: ciò che JAV tiene dei suoi incassi."""

    kept_month_cents: int
    kept_month_forecast_cents: int
    kept_year_cents: int
    kept_all_time_cents: int


class PlatformTotalsRead(BaseModel):
    clubs_active: int
    athletes_active: int
    families: int
    month: FiguresRead
    year: FiguresRead
    debt_cents: int
    overdue_cents: int
    aging: dict[str, AgingBucketRead]


class EarningsPointRead(BaseModel):
    month: str
    platform_fee_cents: int
    income_cents: int
    costs_cents: int
    result_cents: int
    by_club: dict[str, int]
    courses_kept_cents: int = 0


class EarningsRead(BaseModel):
    month_cents: int
    month_forecast_cents: int
    year_cents: int
    all_time_cents: int
    #: La riga dei corsi JAV: incassi meno la parte dei treinador.
    courses_month_cents: int = 0
    courses_month_forecast_cents: int = 0
    courses_year_cents: int = 0
    courses_all_time_cents: int = 0
    series: list[EarningsPointRead]


class GrowthPointRead(BaseModel):
    month: str
    clubs: int
    athletes: int
    families: int


class ShopPointRead(BaseModel):
    month: str
    cents: int


class ShopRevenueRead(BaseModel):
    month_cents: int
    year_cents: int
    all_time_cents: int
    orders_year: int
    series: list[ShopPointRead]


class PlatformSummaryRead(BaseModel):
    year: int
    month: str
    year_months: list[str]
    clubs: list[PlatformClubRead]
    courses_unit: PlatformCoursesUnitRead | None = None
    totals: PlatformTotalsRead
    earnings: EarningsRead
    growth: list[GrowthPointRead]
    shop: ShopRevenueRead
    default_platform_fee_pct: Decimal


# --- Corsi JAV -----------------------------------------------------------------------------------


class CourseFiguresRead(BaseModel):
    """Un corso (o le quote senza corso: `course_id` null) nel periodo."""

    course_id: uuid.UUID | None
    name: str
    venue_name: str | None = None
    venue_city: str | None = None
    active: bool = True
    published: bool = False
    coach_user_id: uuid.UUID | None = None
    coach_name: str | None = None
    coach_share_pct: Decimal | None = None
    athletes: int
    attendances: int
    income_cents: int
    coach_share_cents: int
    jav_share_cents: int
    issued_cents: int
    pending_cents: int
    debt_cents: int
    overdue_cents: int


class CoursesReportRead(BaseModel):
    period: str
    start: date
    end: date
    courses: list[CourseFiguresRead]
    totals: CourseFiguresRead


class CoachEarningRowRead(BaseModel):
    month: str
    course_id: uuid.UUID | None
    course_name: str
    venue_name: str | None = None
    coach_share_pct: Decimal
    #: Incassato delle mensilità del corso, e quanto ne spetta al treinador.
    collected_cents: int
    earned_cents: int
    #: Emesse nel mese e non ancora pagate: la sua parte arriva quando entrano.
    pending_cents: int
    pending_earning_cents: int


class CoachEarningsRead(BaseModel):
    year: int
    rows: list[CoachEarningRowRead]
    earned_year_cents: int
    pending_cents: int


# --- Famiglia -------------------------------------------------------------------------------------


class PersonalNumbersRead(BaseModel):
    paid_year_cents: int
    paid_all_time_cents: int
    paid_by_kind: dict[str, int]
    due_cents: int
    overdue_cents: int
    upcoming_cents: int
    savings_year_cents: int


class PersonalPersonRead(PersonalNumbersRead):
    #: null: la quota socio della famiglia, che non è di un atleta.
    athlete_id: uuid.UUID | None
    name: str
    is_self: bool
    status: str
    shop_year_cents: int


class PersonalShopRead(BaseModel):
    year_cents: int
    all_time_cents: int
    orders_year: int
    credit_used_year_cents: int


class PersonalWalletRead(BaseModel):
    balance_cents: int
    referral_credits_cents: int
    investments_cents: int
    credit_spent_on_fees_cents: int
    credit_spent_on_shop_cents: int


class PersonalSeriesPointRead(BaseModel):
    month: str
    fees_cents: int
    shop_cents: int


class PersonalDiscountRead(FeeRead):
    saved_cents: int


class PersonalAccountRead(BaseModel):
    year: int
    has_children: bool
    is_athlete: bool
    totals: PersonalNumbersRead
    people: list[PersonalPersonRead]
    shop: PersonalShopRead
    wallet: PersonalWalletRead
    series: list[PersonalSeriesPointRead]
    next_payments: list[FeeRead]
    discounts: list[PersonalDiscountRead]
