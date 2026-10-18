"""Le API dei treinador di più club (club/staff_clubs.py).

- `/club/staff/my-clubs`, `/club/staff/me/photo`   il treinador: i club tra
  cui scegliere entrando, la sua foto per il saluto;
- `/club/admin/coaches/...`                         la segreteria: chiedere un
  treinador di un altro club, toglierlo dal suo;
- `/clubs/coaches`, `/clubs/{id}/coaches/...`       il superadmin: chi allena
  dove, assegnare, togliere, approvare, la foto di un treinador.
"""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rate_limit import rate_limit
from app.core.storage import UploadValidationError, upload_media
from app.domains.club import service as club_service
from app.domains.club import staff_clubs
from app.domains.club.scope import CLUBS_MANAGE, ClubUser, require_club_permission
from app.domains.rbac.service import get_permission_codes_for_user
from app.domains.users.models import User

INSTRUCT = "club.instruct"
MANAGE = "club.manage"

staff_router = APIRouter(prefix="/club/staff", tags=["club-staff"])
admin_router = APIRouter(prefix="/club/admin/coaches", tags=["club-admin"])
platform_router = APIRouter(prefix="/clubs", tags=["clubs"])


def _raise(exc: club_service.ClubError) -> None:
    code = status.HTTP_404_NOT_FOUND if isinstance(exc, club_service.ClubNotFoundError) else status.HTTP_400_BAD_REQUEST
    raise HTTPException(code, str(exc)) from exc


async def _photo_url(file: UploadFile, user_id: uuid.UUID) -> str:
    try:
        return upload_media(file_bytes=await file.read(), content_type=file.content_type or "",
                            key_prefix=f"photos/staff/{user_id}")
    except UploadValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La foto deve essere un JPG, PNG o WebP di massimo 5 MB.") from exc


class CoachWrite(BaseModel):
    email: str | None = Field(default=None, max_length=255)
    user_id: uuid.UUID | None = None


class CoachRequestWrite(BaseModel):
    email: str = Field(min_length=3, max_length=255)


# --- Il treinador ---------------------------------------------------------------------------------


@staff_router.get("/my-clubs")
async def my_clubs(
    current_user: CurrentUser = Depends(require_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> dict:
    """Il saluto (nome, foto) e i club in cui posso entrare come treinador."""
    user = await db.get(User, current_user.user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account non trovato.")
    granted = await get_permission_codes_for_user(db, user_id=user.id, organization_id=user.organization_id)
    # Nel club dell'account si entra con il ruolo (segreteria o istruttore).
    home = user.club_id is not None and (MANAGE in granted or INSTRUCT in granted)
    return await staff_clubs.my_clubs(db, user=user, can_instruct_home=home)


@staff_router.put("/me/photo", dependencies=[Depends(rate_limit("staff-photo", max_requests=20, window_seconds=300))])
async def set_my_photo(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> dict:
    user = await db.get(User, current_user.user_id)
    user = await staff_clubs.set_photo(db, user=user, url=await _photo_url(file, user.id),
                                       actor_user_id=current_user.user_id)
    return {"photo_url": user.photo_url}


@staff_router.delete("/me/photo")
async def remove_my_photo(
    current_user: CurrentUser = Depends(require_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> dict:
    user = await db.get(User, current_user.user_id)
    await staff_clubs.set_photo(db, user=user, url=None, actor_user_id=current_user.user_id)
    return {"photo_url": None}


# --- La segreteria --------------------------------------------------------------------------------


@admin_router.post("/request", status_code=status.HTTP_201_CREATED)
async def request_coach(
    payload: CoachRequestWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> dict:
    """Un treinador che ha già l'account in un altro club: la richiesta va al
    superadmin."""
    try:
        row = await staff_clubs.request(db, organization_id=current_user.organization_id,
                                        club_id=current_user.club_id, actor_user_id=current_user.user_id,
                                        email=payload.email)
    except club_service.ClubError as exc:
        _raise(exc)
    return {"user_id": row.user_id, "status": row.status}


@admin_router.delete("/{user_id}")
async def remove_coach(
    user_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        await staff_clubs.remove(db, organization_id=current_user.organization_id, club_id=current_user.club_id,
                                 user_id=user_id, actor_user_id=current_user.user_id, by_secretary=True)
    except club_service.ClubError as exc:
        _raise(exc)
    return {"ok": True}


# --- Il superadmin --------------------------------------------------------------------------------


@platform_router.get("/coaches")
async def coaches_overview(
    current_user: CurrentUser = Depends(require_permission(CLUBS_MANAGE)), db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Ogni treinador con i club in cui allena (e le richieste in attesa)."""
    return await staff_clubs.coaches_overview(db, organization_id=current_user.organization_id)


@platform_router.post("/{club_id}/coaches", status_code=status.HTTP_201_CREATED)
async def assign_coach(
    club_id: uuid.UUID, payload: CoachWrite,
    current_user: CurrentUser = Depends(require_permission(CLUBS_MANAGE)), db: AsyncSession = Depends(get_db),
) -> dict:
    """Assegna un treinador al club, o approva la richiesta della segreteria."""
    if not payload.email and payload.user_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Indica il treinador (email).")
    try:
        row = await staff_clubs.assign(db, organization_id=current_user.organization_id, club_id=club_id,
                                       actor_user_id=current_user.user_id, email=payload.email,
                                       user_id=payload.user_id)
    except club_service.ClubError as exc:
        _raise(exc)
    return {"user_id": row.user_id, "club_id": row.club_id, "status": row.status}


@platform_router.delete("/{club_id}/coaches/{user_id}")
async def unassign_coach(
    club_id: uuid.UUID, user_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission(CLUBS_MANAGE)), db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        await staff_clubs.remove(db, organization_id=current_user.organization_id, club_id=club_id, user_id=user_id,
                                 actor_user_id=current_user.user_id, by_secretary=False)
    except club_service.ClubError as exc:
        _raise(exc)
    return {"ok": True}


@platform_router.put("/coaches/{user_id}/photo")
async def set_coach_photo(
    user_id: uuid.UUID, file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_permission(CLUBS_MANAGE)), db: AsyncSession = Depends(get_db),
) -> dict:
    """Il superadmin mette la foto di un treinador (quella che vede nel saluto)."""
    user = await db.get(User, user_id)
    if user is None or user.organization_id != current_user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account non trovato.")
    user = await staff_clubs.set_photo(db, user=user, url=await _photo_url(file, user.id),
                                       actor_user_id=current_user.user_id)
    return {"photo_url": user.photo_url}
