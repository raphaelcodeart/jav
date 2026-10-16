"""Le API degli sponsor (sponsors.py):

- `GET /public-site/sponsors[/{slug}]`  chiunque: gli sponsor attivi;
- `/sponsors[...]`                     lo staff della piattaforma
  (`clubs.manage`, account senza club): elenco, creazione, modifica, logo.
"""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rate_limit import rate_limit
from app.domains.club import service as club_service
from app.domains.club import sponsors
from app.domains.club.scope import CLUBS_MANAGE
from app.domains.users.models import User

public_sponsors_router = APIRouter(prefix="/public-site", tags=["public-site"])
admin_sponsors_router = APIRouter(prefix="/sponsors", tags=["sponsors"])


class PublicSponsorRead(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    tagline: str | None
    description: str | None
    logo_url: str | None
    website_url: str | None
    color: str | None


class SponsorRead(PublicSponsorRead):
    sort_order: int
    active: bool


class SponsorWrite(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    tagline: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    logo_url: str | None = Field(default=None, max_length=500)
    website_url: str | None = Field(default=None, max_length=500)
    color: str | None = Field(default=None, max_length=7)
    sort_order: int | None = Field(default=None, ge=0, le=999)
    active: bool | None = None


class LogoRead(BaseModel):
    url: str


def _raise(exc: club_service.ClubError) -> None:
    code = status.HTTP_404_NOT_FOUND if isinstance(exc, club_service.ClubNotFoundError) else status.HTTP_400_BAD_REQUEST
    raise HTTPException(code, str(exc)) from exc


async def _platform_user(
    current_user: CurrentUser = Depends(require_permission(CLUBS_MANAGE)), db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """Lo staff della piattaforma: un account di un club non tocca gli sponsor della rete."""
    user = await db.get(User, current_user.user_id)
    if user is None or user.club_id is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Gli sponsor li gestisce lo staff di JudoArteVida.")
    return current_user


@public_sponsors_router.get("/sponsors", response_model=list[PublicSponsorRead])
async def public_list(db: AsyncSession = Depends(get_db)) -> list[PublicSponsorRead]:
    return [PublicSponsorRead(**sponsors.public_dict(s)) for s in await sponsors.public_sponsors(db)]


@public_sponsors_router.get("/sponsors/{slug}", response_model=PublicSponsorRead)
async def public_detail(slug: str, db: AsyncSession = Depends(get_db)) -> PublicSponsorRead:
    try:
        return PublicSponsorRead(**sponsors.public_dict(await sponsors.public_sponsor(db, slug=slug)))
    except club_service.ClubError as exc:
        _raise(exc)


@admin_sponsors_router.get("", response_model=list[SponsorRead])
async def admin_list(user: CurrentUser = Depends(_platform_user), db: AsyncSession = Depends(get_db)) -> list[SponsorRead]:
    rows = await sponsors.list_sponsors(db, organization_id=user.organization_id, only_active=False)
    return [SponsorRead(**sponsors.sponsor_dict(s)) for s in rows]


@admin_sponsors_router.post("", response_model=SponsorRead, status_code=status.HTTP_201_CREATED)
async def admin_create(
    payload: SponsorWrite, user: CurrentUser = Depends(_platform_user), db: AsyncSession = Depends(get_db),
) -> SponsorRead:
    try:
        s = await sponsors.create_sponsor(db, organization_id=user.organization_id, actor_user_id=user.user_id,
                                          data=payload.model_dump(exclude_unset=True))
    except club_service.ClubError as exc:
        _raise(exc)
    return SponsorRead(**sponsors.sponsor_dict(s))


@admin_sponsors_router.post("/logo", response_model=LogoRead,
                            dependencies=[Depends(rate_limit("sponsor-logo", max_requests=30, window_seconds=300))])
async def admin_upload_logo(file: UploadFile = File(...), user: CurrentUser = Depends(_platform_user)) -> LogoRead:
    try:
        url = sponsors.upload_logo(organization_id=user.organization_id, file_bytes=await file.read(),
                                   content_type=file.content_type or "")
    except club_service.ClubError as exc:
        _raise(exc)
    return LogoRead(url=url)


@admin_sponsors_router.patch("/{sponsor_id}", response_model=SponsorRead)
async def admin_update(
    sponsor_id: uuid.UUID, payload: SponsorWrite,
    user: CurrentUser = Depends(_platform_user), db: AsyncSession = Depends(get_db),
) -> SponsorRead:
    try:
        s = await sponsors.update_sponsor(db, organization_id=user.organization_id, sponsor_id=sponsor_id,
                                          actor_user_id=user.user_id, changes=payload.model_dump(exclude_unset=True))
    except club_service.ClubError as exc:
        _raise(exc)
    return SponsorRead(**sponsors.sponsor_dict(s))


@admin_sponsors_router.delete("/{sponsor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete(
    sponsor_id: uuid.UUID, user: CurrentUser = Depends(_platform_user), db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await sponsors.delete_sponsor(db, organization_id=user.organization_id, sponsor_id=sponsor_id,
                                      actor_user_id=user.user_id)
    except club_service.ClubError as exc:
        _raise(exc)
