"""Le rotte del conto dell'atleta (club/athlete_access.py).

- `/club/athletes/{id}/login[...]`: il titolare crea, cambia e spegne
  l'accesso del suo atleta, e ne genera il QR (`club.family`);
- `/club/athlete-area[...]`: l'area dell'atleta, per l'atleta stesso o per il
  suo titolare (`club.athlete`, che hanno sia ATHLETE sia CUSTOMER).
"""

import uuid
from datetime import date, datetime, time

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.rate_limit import rate_limit
from app.domains.club import athlete_access, seasons
from app.domains.club import lessons as lessons_service
from app.domains.club import months as months_service
from app.domains.club import service as club_service
from app.domains.club.schemas import AthleteDetailRead, SeasonMonthsRead
from app.domains.club.scope import ClubUser, require_club_permission

router = APIRouter(prefix="/club", tags=["club-athlete"])

FAMILY = "club.family"
ATHLETE = "club.athlete"


def _raise(exc: club_service.ClubError) -> None:
    code = status.HTTP_404_NOT_FOUND if isinstance(exc, club_service.ClubNotFoundError) else status.HTTP_400_BAD_REQUEST
    raise HTTPException(code, str(exc)) from exc


class AthleteLoginRead(BaseModel):
    athlete_id: uuid.UUID
    has_login: bool
    is_self: bool
    username: str | None
    email: str | None
    active: bool
    qr_active_until: datetime | None


class AthleteLoginWrite(BaseModel):
    username: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=128)


class AthleteQrRead(AthleteLoginRead):
    #: Il link con il codice in chiaro, una volta sola (/entrar/<code>), e il
    #: QR già disegnato (SVG in un data URI: il browser lo mostra in un <img>,
    #: dove nessuno script gira).
    url: str
    qr_image: str


def _qr_image(url: str) -> str:
    import base64

    from reportlab.graphics import renderSVG
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing

    widget = QrCodeWidget(url, barLevel="M")
    x0, y0, x1, y1 = widget.getBounds()
    size = 320
    drawing = Drawing(size, size, transform=[size / (x1 - x0), 0, 0, size / (y1 - y0), 0, 0])
    drawing.add(widget)
    svg = renderSVG.drawToString(drawing)
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


class AreaAthleteRef(BaseModel):
    id: uuid.UUID
    name: str
    photo_url: str | None
    is_own: bool


class AreaLessonRead(BaseModel):
    date: date
    course_id: uuid.UUID
    course_name: str
    starts_at: time
    ends_at: time
    status: str


class AthleteAreaRead(AthleteDetailRead):
    age: int
    is_minor: bool
    viewer_is_athlete: bool
    can_manage: bool
    can_become_holder: bool
    #: Oggi all'ora del club (le lezioni di oggi si segnano solo oggi).
    today: date
    lessons: list[AreaLessonRead]
    month_present: int
    month_total: int


class AreaAttendanceWrite(BaseModel):
    course_id: uuid.UUID


class BecomeHolderWrite(BaseModel):
    email: str | None = Field(default=None, max_length=255)


# --- Il titolare: l'accesso del suo atleta ------------------------------------------------------


async def _owned(db: AsyncSession, user: ClubUser, athlete_id: uuid.UUID):
    try:
        return await club_service.get_owned_athlete(
            db, scope=user.scope, guardian_user_id=user.user_id, athlete_id=athlete_id,
        )
    except club_service.ClubError as exc:
        _raise(exc)


@router.get("/athletes/{athlete_id}/login", response_model=AthleteLoginRead)
async def get_login(
    athlete_id: uuid.UUID, current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> AthleteLoginRead:
    athlete = await _owned(db, current_user, athlete_id)
    return AthleteLoginRead(**await athlete_access.login_status(db, athlete=athlete))


@router.put(
    "/athletes/{athlete_id}/login", response_model=AthleteLoginRead,
    dependencies=[Depends(rate_limit("club-athlete-login", max_requests=20, window_seconds=300))],
)
async def put_login(
    athlete_id: uuid.UUID, payload: AthleteLoginWrite,
    current_user: ClubUser = Depends(require_club_permission(FAMILY)), db: AsyncSession = Depends(get_db),
) -> AthleteLoginRead:
    athlete = await _owned(db, current_user, athlete_id)
    try:
        row = await athlete_access.set_login(
            db, athlete=athlete, actor_user_id=current_user.user_id,
            username=payload.username, email=payload.email, password=payload.password,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return AthleteLoginRead(**row)


@router.delete("/athletes/{athlete_id}/login", response_model=AthleteLoginRead)
async def delete_login(
    athlete_id: uuid.UUID, current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> AthleteLoginRead:
    athlete = await _owned(db, current_user, athlete_id)
    try:
        row = await athlete_access.disable_login(db, athlete=athlete, actor_user_id=current_user.user_id)
    except club_service.ClubError as exc:
        _raise(exc)
    return AthleteLoginRead(**row)


@router.post(
    "/athletes/{athlete_id}/login/qr", response_model=AthleteQrRead,
    dependencies=[Depends(rate_limit("club-athlete-qr", max_requests=10, window_seconds=300))],
)
async def create_qr(
    athlete_id: uuid.UUID, current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> AthleteQrRead:
    athlete = await _owned(db, current_user, athlete_id)
    try:
        code, row = await athlete_access.create_qr(db, athlete=athlete, actor_user_id=current_user.user_id)
    except club_service.ClubError as exc:
        _raise(exc)
    from app.core.config import get_settings

    url = f"{get_settings().public_app_base_url.rstrip('/')}/entrar/{code}"
    return AthleteQrRead(**row, url=url, qr_image=_qr_image(url))


@router.delete("/athletes/{athlete_id}/login/qr", response_model=AthleteLoginRead)
async def delete_qr(
    athlete_id: uuid.UUID, current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> AthleteLoginRead:
    athlete = await _owned(db, current_user, athlete_id)
    return AthleteLoginRead(**await athlete_access.revoke_qr(db, athlete=athlete, actor_user_id=current_user.user_id))


# --- L'area dell'atleta -------------------------------------------------------------------------


@router.get("/athlete-area", response_model=list[AreaAthleteRef])
async def list_areas(
    current_user: ClubUser = Depends(require_club_permission(ATHLETE)), db: AsyncSession = Depends(get_db),
) -> list[AreaAthleteRef]:
    athletes = await athlete_access.area_athletes(db, user_id=current_user.user_id, club_id=current_user.club_id)
    return [
        AreaAthleteRef(id=a.id, name=f"{a.first_name} {a.last_name}", photo_url=a.photo_url,
                       is_own=a.user_id == current_user.user_id)
        for a in athletes
    ]


async def _area_athlete(db: AsyncSession, user: ClubUser, athlete_id: uuid.UUID):
    try:
        return await athlete_access.area_athlete(db, user_id=user.user_id, club_id=user.club_id, athlete_id=athlete_id)
    except club_service.ClubError as exc:
        _raise(exc)


@router.get("/athlete-area/{athlete_id}", response_model=AthleteAreaRead)
async def get_area(
    athlete_id: uuid.UUID, current_user: ClubUser = Depends(require_club_permission(ATHLETE)),
    db: AsyncSession = Depends(get_db),
) -> AthleteAreaRead:
    athlete = await _area_athlete(db, current_user, athlete_id)
    today = (await lessons_service.club_now(db, club_id=current_user.club_id)).date()
    return AthleteAreaRead(**await athlete_access.area(
        db, athlete=athlete, viewer_user_id=current_user.user_id, today=today,
    ))


@router.get("/athlete-area/{athlete_id}/months", response_model=SeasonMonthsRead)
async def get_area_months(
    athlete_id: uuid.UUID, current_user: ClubUser = Depends(require_club_permission(ATHLETE)),
    db: AsyncSession = Depends(get_db),
) -> SeasonMonthsRead:
    """Le mensilità dell'atleta mese per mese, in lettura: le paga il titolare."""
    athlete = await _area_athlete(db, current_user, athlete_id)
    today = (await lessons_service.club_now(db, club_id=current_user.club_id)).date()
    return SeasonMonthsRead(**await months_service.season_months(
        db, athlete=athlete, season=seasons.season_of(today), today=today,
    ))


@router.post("/athlete-area/{athlete_id}/attendance", status_code=status.HTTP_204_NO_CONTENT)
async def mark_present(
    athlete_id: uuid.UUID, payload: AreaAttendanceWrite,
    current_user: ClubUser = Depends(require_club_permission(ATHLETE)), db: AsyncSession = Depends(get_db),
) -> None:
    athlete = await _area_athlete(db, current_user, athlete_id)
    try:
        await athlete_access.mark_today(
            db, athlete=athlete, course_id=payload.course_id, present=True, actor_user_id=current_user.user_id,
        )
    except club_service.ClubError as exc:
        _raise(exc)


@router.delete("/athlete-area/{athlete_id}/attendance/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unmark_present(
    athlete_id: uuid.UUID, course_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(ATHLETE)), db: AsyncSession = Depends(get_db),
) -> None:
    athlete = await _area_athlete(db, current_user, athlete_id)
    try:
        await athlete_access.mark_today(
            db, athlete=athlete, course_id=course_id, present=False, actor_user_id=current_user.user_id,
        )
    except club_service.ClubError as exc:
        _raise(exc)


@router.post("/athlete-area/{athlete_id}/become-holder", status_code=status.HTTP_204_NO_CONTENT)
async def become_holder(
    athlete_id: uuid.UUID, payload: BecomeHolderWrite,
    current_user: ClubUser = Depends(require_club_permission(ATHLETE)), db: AsyncSession = Depends(get_db),
) -> None:
    athlete = await _area_athlete(db, current_user, athlete_id)
    today = (await lessons_service.club_now(db, club_id=current_user.club_id)).date()
    try:
        await athlete_access.become_holder(
            db, athlete=athlete, user_id=current_user.user_id, email=payload.email, today=today,
        )
    except club_service.ClubError as exc:
        _raise(exc)
