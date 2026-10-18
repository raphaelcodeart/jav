"""Le API dell'area del treinador oltre a quelle storiche di router.py
(club/coach.py, club/workclock.py, club/news.py):

- `/club/staff/coach/...`  Início, quaderno (note delle lezioni e degli
  atleti), i miei atleti;
- `/club/staff/clock/sessions[...]`  i propri turni: correggere, togliere,
  aggiungere quello dimenticato;
- `/club/staff/board`, `/club/staff/news[...]`  la bacheca e i post del
  treinador;
- `/club/staff/ranking`  il Jav Ranking per lo staff (prima l'area del
  treinador chiamava quello della segreteria e riceveva un 403);
- `/club/admin/work-sessions/changes`  la segreteria: le modifiche ai turni.

Tutte con `club.instruct` (treinador, adjunto e segreteria); che cosa vede
ognuno lo decide il servizio con `manager` (chi ha anche `club.manage`).
"""

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db, utcnow
from app.core.rate_limit import rate_limit
from app.domains.club import coach, competitions as competitions_service, news
from app.domains.club import service as club_service
from app.domains.club import workclock
from app.domains.club.lessons import club_now
from app.domains.club.news_router import FeedItemRead, ImageRead, NewsPostRead
from app.domains.club.schemas import ClockRead, RankingRead
from app.domains.club.scope import ClubUser, require_club_permission
from app.domains.rbac.service import get_permission_codes_for_user

INSTRUCT = "club.instruct"
MANAGE = "club.manage"

coach_router = APIRouter(prefix="/club/staff", tags=["club-staff"])
admin_coach_router = APIRouter(prefix="/club/admin", tags=["club-admin"])


class SessionWrite(BaseModel):
    started_at: datetime
    ended_at: datetime
    note: str | None = Field(default=None, max_length=300)


class SessionUpdate(BaseModel):
    started_at: datetime | None = None
    ended_at: datetime | None = None
    note: str | None = Field(default=None, max_length=300)


class LessonNoteWrite(BaseModel):
    course_id: uuid.UUID
    lesson_date: date
    title: str | None = Field(default=None, max_length=200)
    techniques: list[str] | str | None = None
    body: str | None = Field(default=None, max_length=coach.MAX_BODY)


class LessonNoteUpdate(BaseModel):
    lesson_date: date | None = None
    title: str | None = Field(default=None, max_length=200)
    techniques: list[str] | str | None = None
    body: str | None = Field(default=None, max_length=coach.MAX_BODY)


class AthleteNoteWrite(BaseModel):
    category: str = Field(default="OTHER", max_length=16)
    body: str = Field(min_length=2, max_length=coach.MAX_BODY)


class AthleteNoteUpdate(BaseModel):
    category: str | None = Field(default=None, max_length=16)
    body: str | None = Field(default=None, min_length=2, max_length=coach.MAX_BODY)


class StaffPostCreate(BaseModel):
    title: str = Field(max_length=200)
    body: str | None = Field(default=None, max_length=10_000)
    image_url: str | None = Field(default=None, max_length=500)
    video_url: str | None = Field(default=None, max_length=500)
    link_url: str | None = Field(default=None, max_length=500)
    published: bool = True


class StaffPostUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, max_length=10_000)
    image_url: str | None = Field(default=None, max_length=500)
    video_url: str | None = Field(default=None, max_length=500)
    link_url: str | None = Field(default=None, max_length=500)
    published: bool | None = None


class StaffBoardRead(BaseModel):
    feed: list[FeedItemRead]
    mine: list[NewsPostRead]


def _raise(exc: club_service.ClubError) -> None:
    code = status.HTTP_404_NOT_FOUND if isinstance(exc, club_service.ClubNotFoundError) else status.HTTP_400_BAD_REQUEST
    raise HTTPException(code, str(exc)) from exc


async def _manager(db: AsyncSession, user: ClubUser) -> bool:
    # Nel club di un'altra appartenenza si è solo treinador (club/scope.py).
    if not user.home:
        return False
    granted = await get_permission_codes_for_user(db, user_id=user.user_id, organization_id=user.organization_id)
    return MANAGE in granted


async def _today(db: AsyncSession, user: ClubUser) -> date:
    return (await club_now(db, club_id=user.club_id)).date()


async def _who(db: AsyncSession, user: ClubUser) -> dict:
    return {"scope": user.scope, "user_id": user.user_id, "manager": await _manager(db, user)}


# --- Início ---------------------------------------------------------------------------------------


@coach_router.get("/coach/home")
async def coach_home(
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> dict:
    now = await club_now(db, club_id=current_user.club_id)
    try:
        return await coach.home(db, **await _who(db, current_user), now=now)
    except club_service.ClubError as exc:
        _raise(exc)


# --- Il Jav Ranking per lo staff -----------------------------------------------------------------


@coach_router.get("/ranking", response_model=RankingRead)
async def staff_ranking(
    season: int | None = None,
    sex: str | None = Query(default=None, pattern="^[MF]$"),
    age_band: str | None = None,
    club_only: bool = False,
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)),
    db: AsyncSession = Depends(get_db),
) -> RankingRead:
    season = season if season is not None else competitions_service.ranking_year(utcnow().date())
    try:
        rows = await competitions_service.ranking(
            db, scope=current_user.scope, season=season, sex=sex, age_band=age_band, club_only=club_only,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return RankingRead(season=season, season_label=competitions_service.ranking_label(season), sex=sex,
                       age_band=age_band, rows=rows)


# --- I propri turni -------------------------------------------------------------------------------


async def _clock(db: AsyncSession, user: ClubUser) -> ClockRead:
    return ClockRead(**await workclock.status(db, scope=user.scope, user_id=user.user_id))


@coach_router.get("/clock/sessions")
async def my_sessions(
    month: str | None = Query(default=None, max_length=7),
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> dict:
    """I propri turni di un mese (questo, se manca), da sfogliare e correggere."""
    try:
        return await workclock.my_sessions(db, scope=current_user.scope, user_id=current_user.user_id,
                                           month=month or utcnow().strftime("%Y-%m"))
    except club_service.ClubError as exc:
        _raise(exc)


@coach_router.post("/clock/sessions", response_model=ClockRead, status_code=status.HTTP_201_CREATED)
async def add_my_session(
    payload: SessionWrite, current_user: ClubUser = Depends(require_club_permission(INSTRUCT)),
    db: AsyncSession = Depends(get_db),
) -> ClockRead:
    try:
        await workclock.own_add(db, scope=current_user.scope, user_id=current_user.user_id, **payload.model_dump())
    except club_service.ClubError as exc:
        _raise(exc)
    return await _clock(db, current_user)


@coach_router.patch("/clock/sessions/{session_id}", response_model=ClockRead)
async def edit_my_session(
    session_id: uuid.UUID, payload: SessionUpdate,
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> ClockRead:
    try:
        await workclock.own_update(db, scope=current_user.scope, user_id=current_user.user_id, session_id=session_id,
                                   changes=payload.model_dump(exclude_unset=True))
    except club_service.ClubError as exc:
        _raise(exc)
    return await _clock(db, current_user)


@coach_router.delete("/clock/sessions/{session_id}", response_model=ClockRead)
async def delete_my_session(
    session_id: uuid.UUID, current_user: ClubUser = Depends(require_club_permission(INSTRUCT)),
    db: AsyncSession = Depends(get_db),
) -> ClockRead:
    try:
        await workclock.own_delete(db, scope=current_user.scope, user_id=current_user.user_id, session_id=session_id)
    except club_service.ClubError as exc:
        _raise(exc)
    return await _clock(db, current_user)


@admin_coach_router.get("/work-sessions/changes")
async def admin_session_changes(
    month: str | None = Query(default=None, max_length=7),
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Le modifiche ai turni del mese: chi ha cambiato che cosa, prima e dopo."""
    try:
        return await workclock.session_changes(
            db, scope=current_user.scope, month=month or (await _today(db, current_user)).strftime("%Y-%m"),
        )
    except club_service.ClubError as exc:
        _raise(exc)


# --- Il quaderno: le note delle lezioni ----------------------------------------------------------


@coach_router.get("/coach/lesson-notes")
async def list_lesson_notes(
    course_id: uuid.UUID | None = None,
    q: str | None = Query(default=None, max_length=100),
    technique: str | None = Query(default=None, max_length=60),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        return await coach.list_lesson_notes(
            db, **await _who(db, current_user), course_id=course_id, q=q, technique=technique,
            date_from=date_from, date_to=date_to, limit=limit, offset=offset,
        )
    except club_service.ClubError as exc:
        _raise(exc)


@coach_router.post("/coach/lesson-notes", status_code=status.HTTP_201_CREATED)
async def add_lesson_note(
    payload: LessonNoteWrite, current_user: ClubUser = Depends(require_club_permission(INSTRUCT)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    data = payload.model_dump()
    try:
        return await coach.add_lesson_note(
            db, **await _who(db, current_user), course_id=data.pop("course_id"), lesson_date=data.pop("lesson_date"),
            data=data, today=await _today(db, current_user),
        )
    except club_service.ClubError as exc:
        _raise(exc)


@coach_router.patch("/coach/lesson-notes/{note_id}")
async def update_lesson_note(
    note_id: uuid.UUID, payload: LessonNoteUpdate,
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        return await coach.update_lesson_note(
            db, **await _who(db, current_user), note_id=note_id, data=payload.model_dump(exclude_unset=True),
            today=await _today(db, current_user),
        )
    except club_service.ClubError as exc:
        _raise(exc)


@coach_router.delete("/coach/lesson-notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lesson_note(
    note_id: uuid.UUID, current_user: ClubUser = Depends(require_club_permission(INSTRUCT)),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await coach.delete_lesson_note(db, **await _who(db, current_user), note_id=note_id)
    except club_service.ClubError as exc:
        _raise(exc)


# --- I miei atleti e le loro note ----------------------------------------------------------------


@coach_router.get("/coach/athletes")
async def my_athletes(
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> list[dict]:
    return await coach.my_athletes(db, **await _who(db, current_user), today=await _today(db, current_user))


@coach_router.get("/coach/athletes/{athlete_id}")
async def athlete_sheet(
    athlete_id: uuid.UUID, current_user: ClubUser = Depends(require_club_permission(INSTRUCT)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        return await coach.athlete_sheet(db, **await _who(db, current_user), athlete_id=athlete_id,
                                         today=await _today(db, current_user))
    except club_service.ClubError as exc:
        _raise(exc)


@coach_router.post("/coach/athletes/{athlete_id}/notes", status_code=status.HTTP_201_CREATED)
async def add_athlete_note(
    athlete_id: uuid.UUID, payload: AthleteNoteWrite,
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        return await coach.add_athlete_note(db, **await _who(db, current_user), athlete_id=athlete_id,
                                            data=payload.model_dump())
    except club_service.ClubError as exc:
        _raise(exc)


@coach_router.patch("/coach/athlete-notes/{note_id}")
async def update_athlete_note(
    note_id: uuid.UUID, payload: AthleteNoteUpdate,
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        return await coach.update_athlete_note(db, **await _who(db, current_user), note_id=note_id,
                                               data=payload.model_dump(exclude_unset=True))
    except club_service.ClubError as exc:
        _raise(exc)


@coach_router.delete("/coach/athlete-notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_athlete_note(
    note_id: uuid.UUID, current_user: ClubUser = Depends(require_club_permission(INSTRUCT)),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await coach.delete_athlete_note(db, **await _who(db, current_user), note_id=note_id)
    except club_service.ClubError as exc:
        _raise(exc)


# --- La bacheca: leggere e scrivere ---------------------------------------------------------------


@coach_router.get("/board", response_model=StaffBoardRead)
async def staff_board(
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> StaffBoardRead:
    feed = await news.staff_feed(db, scope=current_user.scope, user_id=current_user.user_id,
                                 today=await _today(db, current_user))
    mine = await news.list_author_posts(db, scope=current_user.scope, author_user_id=current_user.user_id)
    return StaffBoardRead(feed=[FeedItemRead(**i) for i in feed], mine=[NewsPostRead(**p) for p in mine])


@coach_router.post("/news", response_model=NewsPostRead, status_code=status.HTTP_201_CREATED,
                   dependencies=[Depends(rate_limit("club-staff-news", max_requests=30, window_seconds=600))])
async def staff_create_post(
    payload: StaffPostCreate, current_user: ClubUser = Depends(require_club_permission(INSTRUCT)),
    db: AsyncSession = Depends(get_db),
) -> NewsPostRead:
    try:
        return NewsPostRead(**await news.create_staff_post(db, scope=current_user.scope,
                                                           actor_user_id=current_user.user_id, data=payload.model_dump()))
    except club_service.ClubError as exc:
        _raise(exc)


@coach_router.post("/news/image", response_model=ImageRead,
                   dependencies=[Depends(rate_limit("club-staff-news-image", max_requests=30, window_seconds=300))])
async def staff_post_image(
    file: UploadFile = File(...), current_user: ClubUser = Depends(require_club_permission(INSTRUCT)),
) -> ImageRead:
    try:
        return ImageRead(url=news.upload_image(scope=current_user.scope, file_bytes=await file.read(),
                                               content_type=file.content_type or ""))
    except club_service.ClubError as exc:
        _raise(exc)


@coach_router.patch("/news/{post_id}", response_model=NewsPostRead)
async def staff_update_post(
    post_id: uuid.UUID, payload: StaffPostUpdate,
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> NewsPostRead:
    try:
        return NewsPostRead(**await news.update_staff_post(
            db, scope=current_user.scope, post_id=post_id, actor_user_id=current_user.user_id,
            changes=payload.model_dump(exclude_unset=True),
        ))
    except club_service.ClubError as exc:
        _raise(exc)


@coach_router.delete("/news/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def staff_delete_post(
    post_id: uuid.UUID, current_user: ClubUser = Depends(require_club_permission(INSTRUCT)),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await news.delete_staff_post(db, scope=current_user.scope, post_id=post_id, actor_user_id=current_user.user_id)
    except club_service.ClubError as exc:
        _raise(exc)
