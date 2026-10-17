"""Le API del Calendário JudoArteVida (calendar.py): l'elenco delle prove di
un periodo e il PDF da stampare. Per lo staff del club (`club.instruct`:
segreteria e istruttori) e per atleti e famiglie (`club.athlete`)."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.domains.club import calendar
from app.domains.club import service as club_service
from app.domains.club.lessons import club_now
from app.domains.club.models import Club
from app.domains.club.scope import ClubUser, require_club_permission

staff_calendar_router = APIRouter(prefix="/club/staff/calendar", tags=["club-staff"])
member_calendar_router = APIRouter(prefix="/club/calendar", tags=["club"])


class CalendarEventRead(BaseModel):
    id: str
    name: str
    kind: str
    level: str
    status: str
    starts_on: date
    ends_on: date
    location: str | None
    organizer: str | None
    age_groups: list[str]
    description: str | None
    image_url: str | None
    registration_deadline: date
    fee_cents: int
    club_name: str | None
    network: bool
    circular_url: str | None


def _raise(exc: club_service.ClubError) -> None:
    raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


async def _events(db: AsyncSession, user: ClubUser, date_from: date, date_to: date) -> list[CalendarEventRead]:
    try:
        rows = await calendar.calendar_events(db, scope=user.scope, date_from=date_from, date_to=date_to)
    except club_service.ClubError as exc:
        _raise(exc)
    return [CalendarEventRead(**{**r, "id": str(r["id"])}) for r in rows]


async def _pdf(db: AsyncSession, user: ClubUser, date_from: date, date_to: date) -> Response:
    try:
        rows = await calendar.calendar_events(db, scope=user.scope, date_from=date_from, date_to=date_to)
    except club_service.ClubError as exc:
        _raise(exc)
    club = await db.get(Club, user.club_id)
    today = (await club_now(db, club_id=user.club_id)).date()
    pdf = calendar.render_pdf(events=rows, date_from=date_from, date_to=date_to,
                              club_name=club.name if club else "JudoArteVida", generated_on=today)
    name = f"calendario-judoartevida-{date_from.isoformat()}-{date_to.isoformat()}.pdf"
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@staff_calendar_router.get("", response_model=list[CalendarEventRead])
async def staff_events(
    date_from: date = Query(alias="from"), date_to: date = Query(alias="to"),
    current_user: ClubUser = Depends(require_club_permission("club.instruct")), db: AsyncSession = Depends(get_db),
) -> list[CalendarEventRead]:
    return await _events(db, current_user, date_from, date_to)


@staff_calendar_router.get("/pdf")
async def staff_pdf(
    date_from: date = Query(alias="from"), date_to: date = Query(alias="to"),
    current_user: ClubUser = Depends(require_club_permission("club.instruct")), db: AsyncSession = Depends(get_db),
) -> Response:
    return await _pdf(db, current_user, date_from, date_to)


async def _flyer(db: AsyncSession, user: ClubUser, year: int, month: int) -> Response:
    import calendar as stdcal

    first = date(year, month, 1)
    last = date(year, month, stdcal.monthrange(year, month)[1])
    rows = await calendar.calendar_events(db, scope=user.scope, date_from=first, date_to=last)
    club = await db.get(Club, user.club_id)
    today = (await club_now(db, club_id=user.club_id)).date()
    from app.core.config import get_settings
    from app.domains.organizations.service import network_socials

    pdf = calendar.render_flyer(events=rows, year=year, month=month,
                                club_name=club.name if club else "JudoArteVida", generated_on=today,
                                socials=await network_socials(db, organization_id=user.organization_id),
                                site_url=get_settings().public_app_base_url)
    name = f"flyer-judoartevida-{year:04d}-{month:02d}.pdf"
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@staff_calendar_router.get("/flyer")
async def staff_flyer(
    year: int = Query(ge=2000, le=2100), month: int = Query(ge=1, le=12),
    current_user: ClubUser = Depends(require_club_permission("club.instruct")), db: AsyncSession = Depends(get_db),
) -> Response:
    return await _flyer(db, current_user, year, month)


@member_calendar_router.get("/flyer")
async def member_flyer(
    year: int = Query(ge=2000, le=2100), month: int = Query(ge=1, le=12),
    current_user: ClubUser = Depends(require_club_permission("club.athlete")), db: AsyncSession = Depends(get_db),
) -> Response:
    """Il flyer del mese (calendar.render_flyer): una pagina da condividere."""
    return await _flyer(db, current_user, year, month)


@member_calendar_router.get("", response_model=list[CalendarEventRead])
async def member_events(
    date_from: date = Query(alias="from"), date_to: date = Query(alias="to"),
    current_user: ClubUser = Depends(require_club_permission("club.athlete")), db: AsyncSession = Depends(get_db),
) -> list[CalendarEventRead]:
    return await _events(db, current_user, date_from, date_to)


@member_calendar_router.get("/pdf")
async def member_pdf(
    date_from: date = Query(alias="from"), date_to: date = Query(alias="to"),
    current_user: ClubUser = Depends(require_club_permission("club.athlete")), db: AsyncSession = Depends(get_db),
) -> Response:
    return await _pdf(db, current_user, date_from, date_to)
