"""Le API dei risultati dal treinador, della scheda dell'evento e dei
relatórios (competition_staff.py, event_reports.py).

- `/club/staff/competitions/...`  treinador e segreteria (`club.instruct`):
  gli eventi con i loro iscritti e i contatti, peso, categoria e risultato;
- `/club/calendar/events/{id}`    atleti e famiglie (`club.athlete`): la
  scheda senza contatti;
- `/club/staff/event-reports/...` i relatórios (`club.instruct`; la
  segreteria con `club.manage` li vede e li modifica tutti);
- `/club/admin/event-reports/pdf` il PDF del periodo, solo `club.manage`.
"""

import uuid
from datetime import date, datetime, time
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db, utcnow
from app.domains.club import competition_staff, event_reports
from app.domains.club import service as club_service
from app.domains.club.models import Club
from app.domains.club.scope import ClubUser, require_club_permission
from app.domains.rbac.service import get_permission_codes_for_user

INSTRUCT = "club.instruct"
MANAGE = "club.manage"

staff_competitions_router = APIRouter(prefix="/club/staff/competitions", tags=["club-staff"])
member_events_router = APIRouter(prefix="/club/calendar/events", tags=["club"])
staff_reports_router = APIRouter(prefix="/club/staff/event-reports", tags=["club-staff"])
admin_reports_router = APIRouter(prefix="/club/admin/event-reports", tags=["club-admin"])


def _raise(exc: club_service.ClubError) -> None:
    code = status.HTTP_404_NOT_FOUND if isinstance(exc, club_service.ClubNotFoundError) else status.HTTP_400_BAD_REQUEST
    raise HTTPException(code, str(exc)) from exc


async def _can_manage(db: AsyncSession, user: ClubUser) -> bool:
    granted = await get_permission_codes_for_user(db, user_id=user.user_id, organization_id=user.organization_id)
    return MANAGE in granted


# --- Schemi ---------------------------------------------------------------------------------------


class EventRead(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    kind: str
    level: str
    status: str
    starts_on: date
    ends_on: date
    starts_at_time: time | None
    ends_at_time: time | None
    location: str | None
    organizer: str | None
    registration_deadline: date
    registration_deadline_time: time | None
    fee_cents: int
    min_age: int | None
    max_age: int | None
    age_groups: list[str]
    categories: str | None
    requires_agonistic_certificate: bool
    circular_url: str | None
    circular_filename: str | None
    image_url: str | None
    transport_mode: str
    transport_info: str | None
    network: bool
    club_name: str | None


class StaffEventRead(EventRead):
    entries_count: int
    results_count: int


class ContactRead(BaseModel):
    name: str | None
    email: str | None
    phone: str | None
    #: True: è l'encarregado (atleta minorenne, o adulto senza recapiti suoi).
    is_guardian: bool


class DetailEntryRead(BaseModel):
    entry_id: uuid.UUID
    athlete_id: uuid.UUID
    athlete_name: str
    photo_url: str | None
    category: str | None
    placement: int | None
    rank: int | None
    points: int
    # Solo per lo staff.
    sex: str | None = None
    age: int | None = None
    weight_kg: Decimal | None = None
    result_notes: str | None = None
    contact: ContactRead | None = None


class EventDetailRead(EventRead):
    entries: list[DetailEntryRead]


class EntryResultWrite(BaseModel):
    """Solo i campi presenti si cambiano: alla pesata peso e categoria, dopo
    la gara il risultato. `placement` null = nessun risultato."""

    weight_kg: Decimal | None = Field(default=None, gt=0, le=300)
    category: str | None = Field(default=None, max_length=120)
    placement: int | None = None
    rank: int | None = Field(default=None, ge=1, le=999)
    result_notes: str | None = Field(default=None, max_length=500)


class CostWrite(BaseModel):
    kind: str
    amount_cents: int = Field(default=0, ge=0, le=100_000_000)
    note: str | None = Field(default=None, max_length=300)


class ReportWrite(BaseModel):
    competition_id: uuid.UUID
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    narrative: str | None = Field(default=None, max_length=20000)
    costs: list[CostWrite] = []


class ReportUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    narrative: str | None = Field(default=None, max_length=20000)
    costs: list[CostWrite] | None = None


class CostRead(BaseModel):
    kind: str
    amount_cents: int
    note: str | None


class PhotoRead(BaseModel):
    id: uuid.UUID
    #: URL presigned di 15 minuti: si apre solo dopo il controllo di chi chiede.
    url: str | None


class ResultRowRead(BaseModel):
    athlete_id: uuid.UUID
    athlete_name: str
    category: str | None
    weight_kg: Decimal | None
    placement: int | None
    rank: int | None
    result_notes: str | None
    points: int


class ReportRead(BaseModel):
    id: uuid.UUID
    competition_id: uuid.UUID
    competition_name: str
    competition_kind: str
    competition_level: str
    starts_on: date
    ends_on: date
    location: str | None
    author_user_id: uuid.UUID
    author_name: str
    title: str
    description: str | None
    narrative: str | None
    costs: list[CostRead]
    total_cents: int
    photos: list[PhotoRead]
    results: list[ResultRowRead]
    created_at: datetime
    updated_at: datetime | None
    #: Chi guarda può modificarlo (autore o segreteria).
    can_edit: bool = True


# --- Eventi e risultati (staff) --------------------------------------------------------------------


@staff_competitions_router.get("", response_model=list[StaffEventRead])
async def staff_list(
    when: str = Query(default="upcoming", pattern="^(upcoming|past)$"),
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> list[StaffEventRead]:
    rows = await competition_staff.staff_competitions(
        db, scope=current_user.scope, past=when == "past", today=utcnow().date(),
    )
    return [StaffEventRead(**r) for r in rows]


@staff_competitions_router.get("/{competition_id}", response_model=EventDetailRead)
async def staff_detail(
    competition_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> EventDetailRead:
    try:
        data = await competition_staff.competition_detail(
            db, scope=current_user.scope, competition_id=competition_id, staff=True, today=utcnow().date(),
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return EventDetailRead(**data)


@staff_competitions_router.patch("/{competition_id}/entries/{entry_id}", response_model=DetailEntryRead)
async def staff_update_entry(
    competition_id: uuid.UUID, entry_id: uuid.UUID, payload: EntryResultWrite,
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> DetailEntryRead:
    try:
        await competition_staff.update_entry(
            db, scope=current_user.scope, competition_id=competition_id, entry_id=entry_id,
            actor_user_id=current_user.user_id, changes=payload.model_dump(exclude_unset=True),
        )
        data = await competition_staff.competition_detail(
            db, scope=current_user.scope, competition_id=competition_id, staff=True, today=utcnow().date(),
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return DetailEntryRead(**next(e for e in data["entries"] if e["entry_id"] == entry_id))


@member_events_router.get("/{competition_id}", response_model=EventDetailRead)
async def member_detail(
    competition_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission("club.athlete")), db: AsyncSession = Depends(get_db),
) -> EventDetailRead:
    try:
        data = await competition_staff.competition_detail(
            db, scope=current_user.scope, competition_id=competition_id, staff=False, today=utcnow().date(),
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return EventDetailRead(**data)


# --- Relatórios ------------------------------------------------------------------------------------


async def _report_read(db: AsyncSession, user: ClubUser, report, *, can_manage: bool) -> ReportRead:
    data = await event_reports.report_dict(db, scope=user.scope, report=report)
    return ReportRead(**data, can_edit=can_manage or report.author_user_id == user.user_id)


@staff_reports_router.get("", response_model=list[ReportRead])
async def list_reports(
    date_from: date | None = Query(default=None, alias="from"), date_to: date | None = Query(default=None, alias="to"),
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> list[ReportRead]:
    """La segreteria vede tutti i relatórios del club, un treinador i suoi."""
    manage = await _can_manage(db, current_user)
    pairs = await event_reports.list_reports(
        db, scope=current_user.scope, author_user_id=None if manage else current_user.user_id,
        date_from=date_from, date_to=date_to,
    )
    return [await _report_read(db, current_user, r, can_manage=manage) for r, _c in pairs]


@staff_reports_router.post("", response_model=ReportRead, status_code=status.HTTP_201_CREATED)
async def create_report(
    payload: ReportWrite,
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> ReportRead:
    try:
        report = await event_reports.create_report(
            db, scope=current_user.scope, competition_id=payload.competition_id,
            author_user_id=current_user.user_id, data=payload.model_dump(exclude={"competition_id"}),
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return await _report_read(db, current_user, report, can_manage=await _can_manage(db, current_user))


@staff_reports_router.get("/{report_id}", response_model=ReportRead)
async def get_report(
    report_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> ReportRead:
    manage = await _can_manage(db, current_user)
    try:
        report = await event_reports.get_report(db, scope=current_user.scope, report_id=report_id)
        event_reports._check_owner(report, user_id=current_user.user_id, can_manage=manage)
    except club_service.ClubError as exc:
        _raise(exc)
    return await _report_read(db, current_user, report, can_manage=manage)


@staff_reports_router.patch("/{report_id}", response_model=ReportRead)
async def update_report(
    report_id: uuid.UUID, payload: ReportUpdate,
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> ReportRead:
    manage = await _can_manage(db, current_user)
    data = payload.model_dump(exclude_unset=True)
    try:
        report = await event_reports.update_report(
            db, scope=current_user.scope, report_id=report_id, actor_user_id=current_user.user_id,
            can_manage=manage, data=data,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return await _report_read(db, current_user, report, can_manage=manage)


@staff_reports_router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(
    report_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> Response:
    try:
        await event_reports.delete_report(
            db, scope=current_user.scope, report_id=report_id, actor_user_id=current_user.user_id,
            can_manage=await _can_manage(db, current_user),
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@staff_reports_router.post("/{report_id}/photos", response_model=ReportRead, status_code=status.HTTP_201_CREATED)
async def add_photo(
    report_id: uuid.UUID, file: UploadFile = File(...),
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> ReportRead:
    manage = await _can_manage(db, current_user)
    content = await file.read(event_reports.MAX_PHOTO_BYTES + 1)
    try:
        await event_reports.add_photo(
            db, scope=current_user.scope, report_id=report_id, actor_user_id=current_user.user_id,
            can_manage=manage, file_bytes=content, content_type=file.content_type or "",
        )
        report = await event_reports.get_report(db, scope=current_user.scope, report_id=report_id)
    except club_service.ClubError as exc:
        _raise(exc)
    return await _report_read(db, current_user, report, can_manage=manage)


@staff_reports_router.delete("/{report_id}/photos/{photo_id}", response_model=ReportRead)
async def remove_photo(
    report_id: uuid.UUID, photo_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> ReportRead:
    manage = await _can_manage(db, current_user)
    try:
        await event_reports.remove_photo(
            db, scope=current_user.scope, report_id=report_id, photo_id=photo_id,
            actor_user_id=current_user.user_id, can_manage=manage,
        )
        report = await event_reports.get_report(db, scope=current_user.scope, report_id=report_id)
    except club_service.ClubError as exc:
        _raise(exc)
    return await _report_read(db, current_user, report, can_manage=manage)


@admin_reports_router.get("/pdf")
async def export_pdf(
    date_from: date = Query(alias="from"), date_to: date = Query(alias="to"),
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> Response:
    """Un PDF solo con tutti i relatórios degli eventi del periodo."""
    from app.core.storage import download_document

    def load(key: str) -> bytes | None:
        try:
            return download_document(storage_key=key)
        except Exception:  # noqa: BLE001 -- una foto sparita dal bucket non ferma il PDF
            return None

    try:
        reports = await event_reports.export_reports(
            db, scope=current_user.scope, date_from=date_from, date_to=date_to,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    club = await db.get(Club, current_user.club_id)
    pdf = event_reports.render_pdf(
        reports=reports, date_from=date_from, date_to=date_to, club_name=club.name if club else "JudoArteVida",
        generated_on=utcnow().date(), photo_loader=load,
    )
    name = f"relatorios-{date_from.isoformat()}-{date_to.isoformat()}.pdf"
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{name}"', "X-Report-Count": str(len(reports)),
    })
