"""Le API dei documenti del club (club_documents.py): la segreteria del club
(`club.manage`; il club lo decide club/scope.py, anche per la piattaforma
entrata nel club)."""

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.rate_limit import rate_limit
from app.domains.club import club_documents
from app.domains.club import service as club_service
from app.domains.club.lessons import club_now
from app.domains.club.scope import ClubUser, require_club_permission

router = APIRouter(prefix="/club/admin/club-documents", tags=["club-admin"])

MANAGE = "club.manage"


class ClubDocumentRead(BaseModel):
    id: uuid.UUID
    category: str
    title: str
    issued_on: date | None
    expires_on: date | None
    notes: str | None
    original_filename: str
    size_bytes: int
    #: NONE (senza scadenza), VALID, EXPIRING (entro 30 giorni), EXPIRED.
    status: str
    created_at: datetime


class ClubDocumentUpdate(BaseModel):
    category: str | None = None
    title: str | None = Field(default=None, max_length=200)
    issued_on: date | None = None
    expires_on: date | None = None
    notes: str | None = Field(default=None, max_length=2000)


class DocumentUrlRead(BaseModel):
    url: str


def _raise(exc: club_service.ClubError) -> None:
    code = status.HTTP_404_NOT_FOUND if isinstance(exc, club_service.ClubNotFoundError) else status.HTTP_400_BAD_REQUEST
    raise HTTPException(code, str(exc)) from exc


async def _today(db: AsyncSession, user: ClubUser) -> date:
    return (await club_now(db, club_id=user.club_id)).date()


@router.get("", response_model=list[ClubDocumentRead])
async def list_club_documents(
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> list[ClubDocumentRead]:
    today = await _today(db, current_user)
    return [ClubDocumentRead(**club_documents.document_dict(d, today=today))
            for d in await club_documents.list_documents(db, scope=current_user.scope)]


@router.post("", response_model=ClubDocumentRead, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(rate_limit("club-documents", max_requests=40, window_seconds=600))])
async def upload_club_document(
    file: UploadFile = File(...),
    category: str = Form(...),
    title: str = Form(..., max_length=200),
    issued_on: date | None = Form(default=None),
    expires_on: date | None = Form(default=None),
    notes: str | None = Form(default=None, max_length=2000),
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ClubDocumentRead:
    try:
        doc = await club_documents.add_document(
            db, scope=current_user.scope, actor_user_id=current_user.user_id,
            data={"category": category, "title": title, "issued_on": issued_on, "expires_on": expires_on, "notes": notes},
            file_bytes=await file.read(), content_type=file.content_type or "", filename=file.filename or "",
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return ClubDocumentRead(**club_documents.document_dict(doc, today=await _today(db, current_user)))


@router.patch("/{document_id}", response_model=ClubDocumentRead)
async def update_club_document(
    document_id: uuid.UUID, payload: ClubDocumentUpdate,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> ClubDocumentRead:
    try:
        doc = await club_documents.update_document(
            db, scope=current_user.scope, document_id=document_id, actor_user_id=current_user.user_id,
            changes=payload.model_dump(exclude_unset=True),
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return ClubDocumentRead(**club_documents.document_dict(doc, today=await _today(db, current_user)))


@router.get("/{document_id}/url", response_model=DocumentUrlRead)
async def club_document_url(
    document_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> DocumentUrlRead:
    try:
        doc = await club_documents.get_document(db, scope=current_user.scope, document_id=document_id)
    except club_service.ClubError as exc:
        _raise(exc)
    return DocumentUrlRead(url=club_service.presigned_url(doc.storage_key))


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_club_document(
    document_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await club_documents.remove_document(db, scope=current_user.scope, document_id=document_id,
                                             actor_user_id=current_user.user_id)
    except club_service.ClubError as exc:
        _raise(exc)
