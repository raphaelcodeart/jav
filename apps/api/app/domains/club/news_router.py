"""Le API della bacheca (news.py):

- `/club/admin/news[...]`: la segreteria scrive, corregge, fissa in cima e
  toglie le notizie, e ne carica la foto (`club.manage`);
- `/club/board[...]`: atleti e famiglie leggono le notizie pubblicate e i
  documenti del club condivisi con i soci (`club.athlete`, che hanno sia
  ATHLETE sia CUSTOMER).
"""

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.rate_limit import rate_limit
from app.domains.club import club_documents, news
from app.domains.club import service as club_service
from app.core.deps import CurrentUser, require_permission
from app.domains.club.scope import CLUBS_MANAGE, ClubUser, require_club_permission

admin_news_router = APIRouter(prefix="/club/admin/news", tags=["club-admin"])
board_router = APIRouter(prefix="/club/board", tags=["club"])

MANAGE = "club.manage"
MEMBER = "club.athlete"


class NewsPostRead(BaseModel):
    id: uuid.UUID
    title: str
    body: str | None
    image_url: str | None
    video_url: str | None
    link_url: str | None
    pinned: bool
    published: bool
    published_at: datetime
    author_name: str | None
    #: CLUB (solo i soci) o NETWORK (tutto il circuito).
    audience: str = "CLUB"
    #: Chi firma: il club, o JudoArteVida per i post della piattaforma.
    club: dict | None = None
    likes: int = 0
    liked: bool = False


class NewsPostCreate(BaseModel):
    title: str = Field(max_length=200)
    body: str | None = Field(default=None, max_length=10_000)
    image_url: str | None = Field(default=None, max_length=500)
    video_url: str | None = Field(default=None, max_length=500)
    link_url: str | None = Field(default=None, max_length=500)
    pinned: bool = False
    published: bool = True
    audience: str = Field(default="CLUB", pattern="^(CLUB|NETWORK)$")


class NewsPostUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, max_length=10_000)
    image_url: str | None = Field(default=None, max_length=500)
    video_url: str | None = Field(default=None, max_length=500)
    link_url: str | None = Field(default=None, max_length=500)
    pinned: bool | None = None
    published: bool | None = None
    audience: str | None = Field(default=None, pattern="^(CLUB|NETWORK)$")


class ImageRead(BaseModel):
    url: str


class BoardDocumentRead(BaseModel):
    id: uuid.UUID
    category: str
    title: str
    issued_on: date | None
    expires_on: date | None
    notes: str | None
    original_filename: str
    created_at: datetime


class FeedItemRead(BaseModel):
    """Un elemento del flusso: un post, o una prova in arrivo come post."""

    type: str
    date: datetime
    post: NewsPostRead | None
    event: dict | None


class BoardRead(BaseModel):
    news: list[NewsPostRead]
    documents: list[BoardDocumentRead]
    feed: list[FeedItemRead] = []


class LikeRead(BaseModel):
    likes: int
    liked: bool


class UrlRead(BaseModel):
    url: str


def _raise(exc: club_service.ClubError) -> None:
    code = status.HTTP_404_NOT_FOUND if isinstance(exc, club_service.ClubNotFoundError) else status.HTTP_400_BAD_REQUEST
    raise HTTPException(code, str(exc)) from exc


# --- La segreteria -------------------------------------------------------------------------------

@admin_news_router.get("", response_model=list[NewsPostRead])
async def admin_list_news(
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> list[NewsPostRead]:
    return [NewsPostRead(**p) for p in await news.list_posts(db, scope=current_user.scope, include_drafts=True)]


@admin_news_router.post("", response_model=NewsPostRead, status_code=status.HTTP_201_CREATED,
                        dependencies=[Depends(rate_limit("club-news", max_requests=60, window_seconds=600))])
async def admin_create_news(
    payload: NewsPostCreate,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> NewsPostRead:
    try:
        post = await news.create_post(db, scope=current_user.scope, actor_user_id=current_user.user_id,
                                      data=payload.model_dump())
    except club_service.ClubError as exc:
        _raise(exc)
    return NewsPostRead(**post)


@admin_news_router.post("/image", response_model=ImageRead,
                        dependencies=[Depends(rate_limit("club-news-image", max_requests=40, window_seconds=300))])
async def admin_upload_news_image(
    file: UploadFile = File(...),
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
) -> ImageRead:
    try:
        url = news.upload_image(scope=current_user.scope, file_bytes=await file.read(),
                                content_type=file.content_type or "")
    except club_service.ClubError as exc:
        _raise(exc)
    return ImageRead(url=url)


@admin_news_router.patch("/{post_id}", response_model=NewsPostRead)
async def admin_update_news(
    post_id: uuid.UUID, payload: NewsPostUpdate,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> NewsPostRead:
    try:
        post = await news.update_post(db, scope=current_user.scope, post_id=post_id,
                                      actor_user_id=current_user.user_id, changes=payload.model_dump(exclude_unset=True))
    except club_service.ClubError as exc:
        _raise(exc)
    return NewsPostRead(**post)


@admin_news_router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_news(
    post_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await news.delete_post(db, scope=current_user.scope, post_id=post_id, actor_user_id=current_user.user_id)
    except club_service.ClubError as exc:
        _raise(exc)


# --- Atleti e famiglie ---------------------------------------------------------------------------

@board_router.get("", response_model=BoardRead)
async def read_board(
    current_user: ClubUser = Depends(require_club_permission(MEMBER)), db: AsyncSession = Depends(get_db),
) -> BoardRead:
    from app.domains.club.lessons import club_now

    today = (await club_now(db, club_id=current_user.club_id)).date()
    items = await news.feed(db, scope=current_user.scope, user_id=current_user.user_id, today=today)
    posts = [i["post"] for i in items if i["post"]]
    docs = await club_documents.list_member_documents(db, scope=current_user.scope)
    return BoardRead(
        feed=[FeedItemRead(**i) for i in items],
        news=[NewsPostRead(**p) for p in posts],
        documents=[BoardDocumentRead(
            id=d.id, category=d.category, title=d.title, issued_on=d.issued_on, expires_on=d.expires_on,
            notes=d.notes, original_filename=d.original_filename, created_at=d.created_at,
        ) for d in docs],
    )


@board_router.get("/documents/{document_id}/url", response_model=UrlRead)
async def board_document_url(
    document_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MEMBER)), db: AsyncSession = Depends(get_db),
) -> UrlRead:
    try:
        doc = await club_documents.get_member_document(db, scope=current_user.scope, document_id=document_id)
    except club_service.ClubError as exc:
        _raise(exc)
    return UrlRead(url=club_service.presigned_url(doc.storage_key))


@board_router.post("/posts/{post_id}/like", response_model=LikeRead)
async def like_post(
    post_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MEMBER)), db: AsyncSession = Depends(get_db),
) -> LikeRead:
    """«Mi piace» (o lo toglie): uno per persona."""
    try:
        return LikeRead(**await news.toggle_like(db, scope=current_user.scope, post_id=post_id, user_id=current_user.user_id))
    except club_service.ClubError as exc:
        _raise(exc)


# --- JudoArteVida: i post della piattaforma per tutto il circuito ----------------------------------

platform_news_router = APIRouter(prefix="/platform-news", tags=["platform-news"])


async def _platform_owner(
    current_user: CurrentUser = Depends(require_permission(CLUBS_MANAGE)), db: AsyncSession = Depends(get_db),
) -> tuple[CurrentUser, news.Owner]:
    from app.domains.users.models import User

    user = await db.get(User, current_user.user_id)
    if user is None or user.club_id is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "I post di JudoArteVida li scrive lo staff della piattaforma.")
    return current_user, news.Owner(organization_id=current_user.organization_id, club_id=None)


@platform_news_router.get("", response_model=list[NewsPostRead])
async def platform_list(who=Depends(_platform_owner), db: AsyncSession = Depends(get_db)) -> list[NewsPostRead]:
    return [NewsPostRead(**p) for p in await news.list_owner_posts(db, owner=who[1])]


@platform_news_router.post("", response_model=NewsPostRead, status_code=status.HTTP_201_CREATED)
async def platform_create(payload: NewsPostCreate, who=Depends(_platform_owner), db: AsyncSession = Depends(get_db)) -> NewsPostRead:
    try:
        return NewsPostRead(**await news.create_post(db, scope=who[1], actor_user_id=who[0].user_id, data=payload.model_dump()))
    except club_service.ClubError as exc:
        _raise(exc)


@platform_news_router.post("/image", response_model=ImageRead)
async def platform_image(file: UploadFile = File(...), who=Depends(_platform_owner)) -> ImageRead:
    try:
        return ImageRead(url=news.upload_image(scope=who[1], file_bytes=await file.read(), content_type=file.content_type or ""))
    except club_service.ClubError as exc:
        _raise(exc)


@platform_news_router.patch("/{post_id}", response_model=NewsPostRead)
async def platform_update(post_id: uuid.UUID, payload: NewsPostUpdate, who=Depends(_platform_owner),
                          db: AsyncSession = Depends(get_db)) -> NewsPostRead:
    try:
        return NewsPostRead(**await news.update_post(db, scope=who[1], post_id=post_id, actor_user_id=who[0].user_id,
                                                     changes=payload.model_dump(exclude_unset=True)))
    except club_service.ClubError as exc:
        _raise(exc)


@platform_news_router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def platform_delete(post_id: uuid.UUID, who=Depends(_platform_owner), db: AsyncSession = Depends(get_db)) -> None:
    try:
        await news.delete_post(db, scope=who[1], post_id=post_id, actor_user_id=who[0].user_id)
    except club_service.ClubError as exc:
        _raise(exc)

