"""Le API della segreteria per pagamento parziale, mese esente e relatórios
(club/fee_splits.py, club/money_reports.py). Tutte `club.manage`: la
segreteria del club, o il superadmin entrato nel club."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.rate_limit import rate_limit
from app.domains.club import family as family_service
from app.domains.club import fee_splits, money_reports
from app.domains.club import service as club_service
from app.domains.club.schemas import FeeRead
from app.domains.club.scope import ClubUser, require_club_permission

money_router = APIRouter(prefix="/club/admin", tags=["club-money"])

MANAGE = "club.manage"


class ExemptMonthWrite(BaseModel):
    athlete_id: uuid.UUID
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    reason: str = Field(min_length=3, max_length=500)


class PartialPaymentRead(BaseModel):
    proof_id: uuid.UUID
    receipt_number: str | None
    remainder: FeeRead


def _raise(exc: club_service.ClubError) -> None:
    code = status.HTTP_404_NOT_FOUND if isinstance(exc, club_service.ClubNotFoundError) else status.HTTP_400_BAD_REQUEST
    raise HTTPException(code, str(exc)) from exc


async def _today(db: AsyncSession, club_id: uuid.UUID) -> date:
    from app.domains.club.lessons import club_now

    return (await club_now(db, club_id=club_id)).date()


@money_router.post(
    "/fees/{fee_id}/partial-payment", response_model=PartialPaymentRead, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("club-staff-payment", max_requests=120, window_seconds=600))],
)
async def admin_partial_payment(
    fee_id: uuid.UUID,
    amount_cents: int = Form(..., gt=0),
    reason: str = Form(..., min_length=3, max_length=500),
    method: str = Form(..., pattern="^(BANK_TRANSFER|MBWAY|CASH|CARD)$"),
    note: str | None = Form(default=None, max_length=500),
    cash_received_by_user_id: uuid.UUID | None = Form(default=None),
    cash_received_by_name: str | None = Form(default=None, max_length=120),
    file: UploadFile | None = File(default=None),
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> PartialPaymentRead:
    """«Pagamento parziale»: quanto è stato pagato davvero, come, e perché
    non tutto. La parte pagata ha la sua ricevuta; il resto resta da pagare."""
    try:
        proof, remainder = await fee_splits.record_partial_payment(
            db, scope=current_user.scope, actor_user_id=current_user.user_id, fee_id=fee_id,
            amount_cents=amount_cents, reason=reason, method=method, note=note,
            cash_received_by_user_id=cash_received_by_user_id, cash_received_by_name=cash_received_by_name,
            file_bytes=await file.read() if file is not None else None,
            content_type=file.content_type if file is not None else None,
            original_filename=file.filename if file is not None else None,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return PartialPaymentRead(
        proof_id=proof.id, receipt_number=proof.receipt_number,
        remainder=FeeRead(**family_service.fee_dict(remainder, today=await _today(db, current_user.club_id))),
    )


@money_router.post("/fees/{fee_id}/undo-partial", response_model=FeeRead)
async def admin_undo_partial(
    fee_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> FeeRead:
    try:
        fee = await fee_splits.undo_partial_payment(
            db, scope=current_user.scope, fee_id=fee_id, actor_user_id=current_user.user_id,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return FeeRead(**family_service.fee_dict(fee, today=await _today(db, current_user.club_id)))


@money_router.post("/month/exempt", response_model=FeeRead)
async def admin_exempt_month(
    payload: ExemptMonthWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> FeeRead:
    """«Isenta este mês»: la mensilità di quel mese non si paga."""
    try:
        fee = await fee_splits.exempt_month(
            db, scope=current_user.scope, athlete_id=payload.athlete_id, period=payload.period,
            reason=payload.reason, actor_user_id=current_user.user_id,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return FeeRead(**family_service.fee_dict(fee, today=await _today(db, current_user.club_id)))


@money_router.post("/fees/{fee_id}/unexempt", response_model=FeeRead | None)
async def admin_unexempt_month(
    fee_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> FeeRead | None:
    """Annulla «Isenta este mês». `null`: era un mese futuro, la quota non
    c'è più (la emetterà il job)."""
    today = await _today(db, current_user.club_id)
    try:
        fee = await fee_splits.undo_exempt_month(
            db, scope=current_user.scope, fee_id=fee_id, actor_user_id=current_user.user_id, today=today,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return FeeRead(**family_service.fee_dict(fee, today=today)) if fee is not None else None


@money_router.get("/reports/{report}")
async def admin_report(
    report: str,
    season: int | None = Query(default=None, ge=2000, le=2100),
    year: int | None = Query(default=None, ge=2000, le=2100),
    format: str = Query(default="json", pattern="^(json|csv|xlsx)$"),
    lang: str | None = Query(default=None, max_length=5),
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """Un relatório (money_reports.REPORTS) per la stagione o l'anno, a
    schermo (`json`) o da scaricare (`csv`, `xlsx`)."""
    if report not in money_reports.REPORTS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Relatório non trovato.")
    today = await _today(db, current_user.club_id)
    try:
        period = money_reports.report_period(season=season, year=year, today=today)
        data = await money_reports.build(db, scope=current_user.scope, report=report, period=period, today=today)
    except club_service.ClubError as exc:
        _raise(exc)
    if format == "json":
        return data
    if format == "csv":
        body, media = money_reports.to_csv(data, lang=lang), "text/csv; charset=utf-8"
    else:
        body = money_reports.to_xlsx(data, lang=lang)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return Response(
        content=body, media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{money_reports.filename(data, format)}"'},
    )
