"""Le API del personale del club (staff_work.py): l'area dello staff
(/club/staff/work, /club/staff/messages), la segreteria
(/club/admin/staff-work, /club/admin/staff-messages) e JudoArteVida
(/club-platform/staff-messages, i messaggi del canale JAV di tutti i club)."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, require_permission
from app.domains.club import service as club_service
from app.domains.club import staff_work
from app.domains.club.lessons import club_now
from app.domains.club.scope import CLUBS_MANAGE, ClubScope, ClubUser, require_club_permission

INSTRUCT = "club.instruct"
MANAGE = "club.manage"

staff_work_router = APIRouter(prefix="/club/staff", tags=["club-staff"])
admin_staff_work_router = APIRouter(prefix="/club/admin", tags=["club-admin"])
platform_staff_router = APIRouter(prefix="/club-platform", tags=["club-platform"])


class TaskWrite(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    done_on: date
    minutes: int | None = Field(default=None, gt=0, le=24 * 60)
    note: str | None = Field(default=None, max_length=500)


class AdminTaskWrite(TaskWrite):
    kind: str = Field(default="ODD_JOB", pattern="^(TASK|ODD_JOB)$")
    user_id: uuid.UUID | None = None
    person_name: str | None = Field(default=None, max_length=150)
    cost_cents: int = Field(default=0, ge=0, le=1_000_000)


class PayWrite(BaseModel):
    cost_cents: int | None = Field(default=None, gt=0, le=1_000_000)
    paid_on: date | None = None
    payment_method: str = Field(default="BANK_TRANSFER", pattern="^(BANK_TRANSFER|MBWAY|CASH|OTHER)$")


class MessageWrite(BaseModel):
    channel: str = Field(pattern="^(CLUB|JAV)$")
    body: str = Field(min_length=2, max_length=staff_work.MAX_BODY)


class ReplyWrite(BaseModel):
    body: str = Field(min_length=2, max_length=staff_work.MAX_BODY)


def _raise(exc: club_service.ClubError) -> None:
    code = status.HTTP_404_NOT_FOUND if isinstance(exc, club_service.ClubNotFoundError) else status.HTTP_400_BAD_REQUEST
    raise HTTPException(code, str(exc)) from exc


async def _today(db: AsyncSession, user: ClubUser) -> date:
    return (await club_now(db, club_id=user.club_id)).date()


def _month(value: str | None, today: date) -> str:
    return value or today.strftime("%Y-%m")


# --- L'area dello staff ---------------------------------------------------------------------------


@staff_work_router.get("/work")
async def my_work(
    month: str | None = Query(default=None, max_length=7),
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> dict:
    today = await _today(db, current_user)
    try:
        return await staff_work.my_month(db, scope=current_user.scope, user_id=current_user.user_id,
                                         month=_month(month, today), today=today)
    except club_service.ClubError as exc:
        _raise(exc)


@staff_work_router.post("/work/tasks", status_code=status.HTTP_201_CREATED)
async def add_my_task(
    payload: TaskWrite, current_user: ClubUser = Depends(require_club_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        row = await staff_work.add_task(db, scope=current_user.scope, actor_user_id=current_user.user_id, kind="TASK",
                                        user_id=current_user.user_id, today=await _today(db, current_user),
                                        **payload.model_dump())
    except club_service.ClubError as exc:
        _raise(exc)
    return staff_work.task_dict(row)


@staff_work_router.delete("/work/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_task(
    task_id: uuid.UUID, current_user: ClubUser = Depends(require_club_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await staff_work.delete_task(db, scope=current_user.scope, task_id=task_id, actor_user_id=current_user.user_id,
                                     own_user_id=current_user.user_id)
    except club_service.ClubError as exc:
        _raise(exc)


@staff_work_router.get("/messages")
async def my_messages(
    channel: str = Query(pattern="^(CLUB|JAV)$"),
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> list[dict]:
    rows = await staff_work.thread(db, club_id=current_user.club_id, staff_user_id=current_user.user_id,
                                   channel=channel, mark_read_from_staff=False)
    return [staff_work.message_dict(m) for m in rows]


@staff_work_router.post("/messages", status_code=status.HTTP_201_CREATED)
async def write_message(
    payload: MessageWrite, current_user: ClubUser = Depends(require_club_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        row = await staff_work.staff_write(db, scope=current_user.scope, staff_user_id=current_user.user_id,
                                           channel=payload.channel, body=payload.body)
    except club_service.ClubError as exc:
        _raise(exc)
    return staff_work.message_dict(row)


# --- La segreteria --------------------------------------------------------------------------------


@admin_staff_work_router.get("/staff-work")
async def admin_month(
    month: str | None = Query(default=None, max_length=7),
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> dict:
    today = await _today(db, current_user)
    try:
        return await staff_work.month_summary(db, scope=current_user.scope, month=_month(month, today), today=today)
    except club_service.ClubError as exc:
        _raise(exc)


@admin_staff_work_router.post("/staff-work/tasks", status_code=status.HTTP_201_CREATED)
async def admin_add_task(
    payload: AdminTaskWrite, current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        row = await staff_work.add_task(db, scope=current_user.scope, actor_user_id=current_user.user_id,
                                        today=await _today(db, current_user), **payload.model_dump())
    except club_service.ClubError as exc:
        _raise(exc)
    return staff_work.task_dict(row)


@admin_staff_work_router.post("/staff-work/tasks/{task_id}/pay")
async def admin_pay_task(
    task_id: uuid.UUID, payload: PayWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        row = await staff_work.pay_task(db, scope=current_user.scope, task_id=task_id, actor_user_id=current_user.user_id,
                                        **payload.model_dump())
    except club_service.ClubError as exc:
        _raise(exc)
    return staff_work.task_dict(row)


@admin_staff_work_router.delete("/staff-work/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_task(
    task_id: uuid.UUID, current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await staff_work.delete_task(db, scope=current_user.scope, task_id=task_id, actor_user_id=current_user.user_id)
    except club_service.ClubError as exc:
        _raise(exc)


@admin_staff_work_router.get("/staff-messages")
async def admin_inbox(
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> list[dict]:
    return await staff_work.inbox(db, channel="CLUB", club_id=current_user.club_id)


@admin_staff_work_router.get("/staff-messages/{staff_user_id}")
async def admin_thread(
    staff_user_id: uuid.UUID, current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> list[dict]:
    rows = await staff_work.thread(db, club_id=current_user.club_id, staff_user_id=staff_user_id, channel="CLUB",
                                   mark_read_from_staff=True)
    return [staff_work.message_dict(m) for m in rows]


@admin_staff_work_router.post("/staff-messages/{staff_user_id}", status_code=status.HTTP_201_CREATED)
async def admin_reply(
    staff_user_id: uuid.UUID, payload: ReplyWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        row = await staff_work.reply(db, scope=current_user.scope, staff_user_id=staff_user_id, channel="CLUB",
                                     body=payload.body, author_user_id=current_user.user_id)
    except club_service.ClubError as exc:
        _raise(exc)
    return staff_work.message_dict(row)


# --- JudoArteVida: il canale JAV di tutti i club ---------------------------------------------------


async def _platform_user(
    current_user: CurrentUser = Depends(require_permission(CLUBS_MANAGE)), db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    from app.domains.users.models import User

    user = await db.get(User, current_user.user_id)
    if user is None or user.club_id is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Questi messaggi li legge lo staff di JudoArteVida.")
    return current_user


@platform_staff_router.get("/staff-messages")
async def platform_inbox(user: CurrentUser = Depends(_platform_user), db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await staff_work.inbox(db, channel="JAV", organization_id=user.organization_id)


@platform_staff_router.get("/staff-messages/{club_id}/{staff_user_id}")
async def platform_thread(
    club_id: uuid.UUID, staff_user_id: uuid.UUID, user: CurrentUser = Depends(_platform_user), db: AsyncSession = Depends(get_db),
) -> list[dict]:
    rows = await staff_work.thread(db, club_id=club_id, staff_user_id=staff_user_id, channel="JAV", mark_read_from_staff=True)
    return [staff_work.message_dict(m) for m in rows if m.organization_id == user.organization_id]


@platform_staff_router.post("/staff-messages/{club_id}/{staff_user_id}", status_code=status.HTTP_201_CREATED)
async def platform_reply(
    club_id: uuid.UUID, staff_user_id: uuid.UUID, payload: ReplyWrite,
    user: CurrentUser = Depends(_platform_user), db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        row = await staff_work.reply(db, scope=ClubScope(organization_id=user.organization_id, club_id=club_id),
                                     staff_user_id=staff_user_id, channel="JAV", body=payload.body, author_user_id=user.user_id)
    except club_service.ClubError as exc:
        _raise(exc)
    return staff_work.message_dict(row)
