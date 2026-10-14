"""Le API della contabilità (club/accounting.py), negli stessi tre gruppi del
resto del club:

- `/club/admin/accounting/...` la segreteria (`club.manage`), sul suo club;
- `/clubs/accounting/...`      il superadmin: tutti i club insieme e la
  percentuale della piattaforma (`clubs.enter` per vedere, `clubs.manage`
  per cambiarla);
- `/club/accounting/...`       la famiglia (`club.family`), solo i suoi conti.

Il browser sceglie solo il periodo: ogni importo nasce qui.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db, utcnow
from app.core.deps import CurrentUser, require_permission
from app.core.rate_limit import rate_limit
from app.domains.club import accounting
from app.domains.club import service as club_service
from app.domains.club.accounting_schemas import (
    ClubSummaryRead,
    DebtsRead,
    ExpenseRead,
    ExpenseUpdate,
    ExpenseWrite,
    LedgerRead,
    PersonalAccountRead,
    PlatformFeeRead,
    PlatformFeeWrite,
    PlatformSummaryRead,
    RecurringRead,
    RecurringUpdate,
    RecurringWrite,
    StaffCostRead,
    StaffRateWrite,
)
from app.domains.club.schemas import JobResultRead, UrlRead
from app.domains.club.scope import CLUBS_ENTER, CLUBS_MANAGE, ClubUser, require_club_permission

admin_accounting_router = APIRouter(prefix="/club/admin/accounting", tags=["club-accounting"])
platform_accounting_router = APIRouter(prefix="/clubs", tags=["clubs-accounting"])
family_accounting_router = APIRouter(prefix="/club/accounting", tags=["club-accounting"])

MANAGE = "club.manage"
FAMILY = "club.family"


def _raise(exc: club_service.ClubError) -> None:
    code = status.HTTP_404_NOT_FOUND if isinstance(exc, club_service.ClubNotFoundError) else status.HTTP_400_BAD_REQUEST
    raise HTTPException(code, str(exc)) from exc


def _today() -> date:
    return utcnow().date()


def _period(value: str | None) -> accounting.Period:
    try:
        return accounting.parse_period(value, today=_today())
    except club_service.ClubError as exc:
        _raise(exc)
        raise  # per il type checker: _raise solleva sempre


# --- La segreteria ---------------------------------------------------------------------------------


@admin_accounting_router.get("/summary", response_model=ClubSummaryRead)
async def club_summary(
    period: str | None = Query(default=None, max_length=7),
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ClubSummaryRead:
    """Il conto del mese (`2026-10`) o dell'anno (`2026`): incassi, costi,
    commissione, risultato, andamento, confronto, previsione, debiti."""
    return ClubSummaryRead(**await accounting.club_summary(
        db, scope=current_user.scope, period=_period(period), today=_today()
    ))


@admin_accounting_router.get("/ledger", response_model=LedgerRead)
async def club_ledger(
    period: str | None = Query(default=None, max_length=7),
    kind: str | None = Query(default=None, pattern="^(INCOME|EXPENSE|COMPUTED)$"),
    q: str | None = Query(default=None, max_length=100),
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> LedgerRead:
    return LedgerRead(**await accounting.ledger(db, scope=current_user.scope, period=_period(period), kind=kind, q=q))


@admin_accounting_router.get("/debts", response_model=DebtsRead)
async def club_debts(
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> DebtsRead:
    """Tutte le famiglie che devono qualcosa, dalla più in ritardo."""
    return DebtsRead(**await accounting.debts(db, scope=current_user.scope, today=_today(), limit=None))


@admin_accounting_router.get("/expenses", response_model=list[ExpenseRead])
async def list_expenses(
    period: str | None = Query(default=None, max_length=7),
    category: str | None = Query(default=None, max_length=16),
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[ExpenseRead]:
    rows = await accounting.list_expenses(db, scope=current_user.scope, period=_period(period), category=category)
    return [ExpenseRead(**accounting.expense_dict(e)) for e in rows]


@admin_accounting_router.post("/expenses", response_model=ExpenseRead, status_code=status.HTTP_201_CREATED)
async def create_expense(
    payload: ExpenseWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ExpenseRead:
    try:
        expense = await accounting.create_expense(
            db, scope=current_user.scope, actor_user_id=current_user.user_id, data=payload.model_dump(),
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return ExpenseRead(**accounting.expense_dict(expense))


@admin_accounting_router.patch("/expenses/{expense_id}", response_model=ExpenseRead)
async def update_expense(
    expense_id: uuid.UUID,
    payload: ExpenseUpdate,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ExpenseRead:
    try:
        expense = await accounting.update_expense(
            db, scope=current_user.scope, expense_id=expense_id, actor_user_id=current_user.user_id,
            data=payload.model_dump(exclude_unset=True),
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return ExpenseRead(**accounting.expense_dict(expense))


@admin_accounting_router.delete("/expenses/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_expense(
    expense_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await accounting.delete_expense(db, scope=current_user.scope, expense_id=expense_id, actor_user_id=current_user.user_id)
    except club_service.ClubError as exc:
        _raise(exc)


@admin_accounting_router.post(
    "/expenses/{expense_id}/receipt", response_model=ExpenseRead,
    dependencies=[Depends(rate_limit("club-expense-receipt", max_requests=30, window_seconds=300))],
)
async def upload_receipt(
    expense_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ExpenseRead:
    try:
        expense = await accounting.attach_receipt(
            db, scope=current_user.scope, expense_id=expense_id, actor_user_id=current_user.user_id,
            file_bytes=await file.read(), content_type=file.content_type, original_filename=file.filename,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return ExpenseRead(**accounting.expense_dict(expense))


@admin_accounting_router.get("/expenses/{expense_id}/receipt-url", response_model=UrlRead)
async def receipt_url(
    expense_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> UrlRead:
    try:
        key = await accounting.receipt_key(db, scope=current_user.scope, expense_id=expense_id)
    except club_service.ClubError as exc:
        _raise(exc)
    return UrlRead(url=club_service.presigned_url(key))


@admin_accounting_router.get("/recurring", response_model=list[RecurringRead])
async def list_recurring(
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[RecurringRead]:
    return [RecurringRead(**accounting.recurring_dict(r)) for r in await accounting.list_recurring(db, scope=current_user.scope)]


@admin_accounting_router.post("/recurring", response_model=RecurringRead, status_code=status.HTTP_201_CREATED)
async def create_recurring(
    payload: RecurringWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> RecurringRead:
    """Un costo fisso: le spese dei mesi da `starts_on` a oggi si registrano
    subito, quelle dei mesi seguenti da sole."""
    try:
        recurring = await accounting.create_recurring(
            db, scope=current_user.scope, actor_user_id=current_user.user_id, data=payload.model_dump(),
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return RecurringRead(**accounting.recurring_dict(recurring))


@admin_accounting_router.patch("/recurring/{recurring_id}", response_model=RecurringRead)
async def update_recurring(
    recurring_id: uuid.UUID,
    payload: RecurringUpdate,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> RecurringRead:
    try:
        recurring = await accounting.update_recurring(
            db, scope=current_user.scope, recurring_id=recurring_id, actor_user_id=current_user.user_id,
            data=payload.model_dump(exclude_unset=True),
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return RecurringRead(**accounting.recurring_dict(recurring))


@admin_accounting_router.delete("/recurring/{recurring_id}")
async def delete_recurring(
    recurring_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """`deleted` falso: aveva già mesi registrati, ed è stato fermato."""
    try:
        deleted = await accounting.delete_recurring(
            db, scope=current_user.scope, recurring_id=recurring_id, actor_user_id=current_user.user_id,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return {"deleted": deleted}


@admin_accounting_router.post("/jobs/recurring", response_model=JobResultRead)
async def run_recurring(
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> JobResultRead:
    """Lo stesso lavoro del job notturno, a mano: idempotente."""
    created = await accounting.materialise_recurring(db, scope=current_user.scope, today=_today())
    return JobResultRead(created=created)


@admin_accounting_router.get("/staff-costs", response_model=list[StaffCostRead])
async def staff_costs(
    period: str | None = Query(default=None, max_length=7),
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[StaffCostRead]:
    rows = await accounting.staff_costs(db, scope=current_user.scope, period=_period(period), today=_today())
    return [StaffCostRead(**r) for r in rows]


@admin_accounting_router.put("/staff-rates", status_code=status.HTTP_204_NO_CONTENT)
async def set_staff_rate(
    payload: StaffRateWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await accounting.set_staff_rate(
            db, scope=current_user.scope, user_id=payload.user_id, hourly_rate_cents=payload.hourly_rate_cents,
            valid_from=payload.valid_from, actor_user_id=current_user.user_id,
        )
    except club_service.ClubError as exc:
        _raise(exc)


# --- La piattaforma --------------------------------------------------------------------------------


@platform_accounting_router.get("/accounting", response_model=PlatformSummaryRead)
async def platform_summary(
    year: int | None = Query(default=None, ge=2000, le=2100),
    current_user: CurrentUser = Depends(require_permission(CLUBS_ENTER)),
    db: AsyncSession = Depends(get_db),
) -> PlatformSummaryRead:
    today = _today()
    return PlatformSummaryRead(**await accounting.platform_summary(
        db, organization_id=current_user.organization_id, year=year or today.year, today=today,
    ))


@platform_accounting_router.get("/{club_id}/platform-fee", response_model=PlatformFeeRead)
async def get_platform_fee(
    club_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission(CLUBS_ENTER)),
    db: AsyncSession = Depends(get_db),
) -> PlatformFeeRead:
    try:
        return PlatformFeeRead(**await accounting.club_options(
            db, organization_id=current_user.organization_id, club_id=club_id,
        ))
    except club_service.ClubError as exc:
        _raise(exc)


@platform_accounting_router.put("/{club_id}/platform-fee", response_model=PlatformFeeRead)
async def set_platform_fee(
    club_id: uuid.UUID,
    payload: PlatformFeeWrite,
    current_user: CurrentUser = Depends(require_permission(CLUBS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> PlatformFeeRead:
    """Solo il superadmin: la percentuale vale dal mese in corso."""
    try:
        await accounting.set_platform_fee(
            db, organization_id=current_user.organization_id, club_id=club_id, pct=payload.pct,
            actor_user_id=current_user.user_id,
        )
        return PlatformFeeRead(**await accounting.club_options(
            db, organization_id=current_user.organization_id, club_id=club_id,
        ))
    except club_service.ClubError as exc:
        _raise(exc)


# --- La famiglia -----------------------------------------------------------------------------------


@family_accounting_router.get("/mine", response_model=PersonalAccountRead)
async def my_account(
    year: int | None = Query(default=None, ge=2000, le=2100),
    current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> PersonalAccountRead:
    today = _today()
    return PersonalAccountRead(**await accounting.personal_account(
        db, scope=current_user.scope, user_id=current_user.user_id, year=year or today.year, today=today,
    ))
