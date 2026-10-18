"""Le API del curriculum del treinador (club/coach_cv.py), tutte sotto
`/club/staff/cv` con `club.instruct`: ognuno vede e scrive solo il suo
(l'utente della richiesta), in qualunque club stia lavorando.

- `GET/PUT  /cv`                  il CV (ciò che scrive + ciò che il gestionale sa)
- `/cv/documents[...]`            l'archivio: dati, file (multipart), URL presigned
- `/cv/sport`, `/cv/sport/events` il Curriculum Sportivo e gli eventi dichiarati
- `GET  /cv/pdf?kind=CV|SPORT`    l'anteprima del PDF, non salvata
- `/cv/exports[...]`              le versioni PDF salvate
"""

import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db, utcnow
from app.core.deps import CurrentUser, require_permission
from app.core.rate_limit import rate_limit
from app.domains.club import coach_cv
from app.domains.club import service as club_service
from app.domains.users.models import User

INSTRUCT = "club.instruct"

router = APIRouter(prefix="/club/staff/cv", tags=["club-staff"])


def _raise(exc: club_service.ClubError) -> None:
    code = status.HTTP_404_NOT_FOUND if isinstance(exc, club_service.ClubNotFoundError) else status.HTTP_400_BAD_REQUEST
    raise HTTPException(code, str(exc)) from exc


async def _user(db: AsyncSession, current_user: CurrentUser) -> User:
    user = await db.get(User, current_user.user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account non trovato.")
    return user


# --- Lo schema del CV (coach_profiles.data) -----------------------------------------------------

Text200 = Field(default=None, max_length=200)


class Link(BaseModel):
    label: str | None = Field(default=None, max_length=60)
    url: str = Field(max_length=300)


class Experience(BaseModel):
    role: str = Field(max_length=150)
    organization: str | None = Text200
    city: str | None = Field(default=None, max_length=100)
    #: Mese e anno, "AAAA-MM".
    start: str | None = Field(default=None, pattern=r"^\d{4}(-\d{2})?$")
    end: str | None = Field(default=None, pattern=r"^\d{4}(-\d{2})?$")
    current: bool = False
    description: str | None = Field(default=None, max_length=2000)


class Education(BaseModel):
    title: str = Field(max_length=200)
    institution: str | None = Text200
    start: str | None = Field(default=None, pattern=r"^\d{4}(-\d{2})?$")
    end: str | None = Field(default=None, pattern=r"^\d{4}(-\d{2})?$")
    description: str | None = Field(default=None, max_length=2000)


class Skills(BaseModel):
    technical: list[str] = Field(default_factory=list, max_length=coach_cv.MAX_ITEMS)
    pedagogical: list[str] = Field(default_factory=list, max_length=coach_cv.MAX_ITEMS)
    organizational: list[str] = Field(default_factory=list, max_length=coach_cv.MAX_ITEMS)


class Language(BaseModel):
    name: str = Field(max_length=60)
    level: str | None = Field(default=None, max_length=60)


class CustomSection(BaseModel):
    title: str = Field(max_length=100)
    body: str = Field(max_length=4000)


class Show(BaseModel):
    """Che cosa entra nel PDF: la foto, la data di nascita, telefono, email,
    i club del gestionale."""

    photo: bool = True
    birth_date: bool = True
    phone: bool = True
    email: bool = True
    clubs: bool = True


class CvWrite(BaseModel):
    headline: str | None = Field(default=None, max_length=150)
    summary: str | None = Field(default=None, max_length=4000)
    birth_date: str | None = Field(default=None, max_length=20)
    nationality: str | None = Field(default=None, max_length=60)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    links: list[Link] = Field(default_factory=list, max_length=6)
    experiences: list[Experience] = Field(default_factory=list, max_length=coach_cv.MAX_ITEMS)
    education: list[Education] = Field(default_factory=list, max_length=coach_cv.MAX_ITEMS)
    skills: Skills = Field(default_factory=Skills)
    languages: list[Language] = Field(default_factory=list, max_length=12)
    specializations: list[str] = Field(default_factory=list, max_length=coach_cv.MAX_ITEMS)
    custom_sections: list[CustomSection] = Field(default_factory=list, max_length=10)
    show: Show = Field(default_factory=Show)


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    category: str | None = None
    issuer: str | None = Field(default=None, max_length=200)
    issued_on: date | None = None
    expires_on: date | None = None
    description: str | None = Field(default=None, max_length=2000)
    show_in_cv: bool | None = None


class EventWrite(BaseModel):
    title: str = Field(max_length=200)
    event_type: str
    role: str
    starts_on: date
    ends_on: date | None = None
    location: str | None = Text200
    organization_name: str | None = Text200
    level: str | None = None
    category: str | None = Field(default=None, max_length=120)
    placement: int | None = None
    result: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    document_id: uuid.UUID | None = None


class ExportWrite(BaseModel):
    kind: Literal["CV", "SPORT"]
    note: str | None = Field(default=None, max_length=200)


def _export_dict(e) -> dict:
    return {"id": e.id, "kind": e.kind, "filename": e.filename, "size_bytes": e.size_bytes, "note": e.note,
            "created_at": e.created_at}


# --- Il CV ----------------------------------------------------------------------------------------


@router.get("")
async def get_cv(current_user: CurrentUser = Depends(require_permission(INSTRUCT)), db: AsyncSession = Depends(get_db)) -> dict:
    return await coach_cv.cv(db, user=await _user(db, current_user))


@router.put("")
async def put_cv(payload: CvWrite, current_user: CurrentUser = Depends(require_permission(INSTRUCT)),
                 db: AsyncSession = Depends(get_db)) -> dict:
    user = await _user(db, current_user)
    await coach_cv.save_profile(db, user=user, data=payload.model_dump(mode="json"))
    return await coach_cv.cv(db, user=user)


# --- L'archivio -----------------------------------------------------------------------------------


@router.get("/documents")
async def list_documents(current_user: CurrentUser = Depends(require_permission(INSTRUCT)),
                         db: AsyncSession = Depends(get_db)) -> list[dict]:
    today = utcnow().date()
    return [coach_cv.document_dict(d, today=today) for d in await coach_cv.list_documents(db, user=await _user(db, current_user))]


@router.post("/documents", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(rate_limit("coach-documents", max_requests=60, window_seconds=600))])
async def create_document(
    title: str = Form(..., max_length=200), category: str = Form(...), issuer: str | None = Form(default=None),
    issued_on: date | None = Form(default=None), expires_on: date | None = Form(default=None),
    description: str | None = Form(default=None), show_in_cv: bool = Form(default=True),
    file: UploadFile | None = File(default=None),
    current_user: CurrentUser = Depends(require_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> dict:
    """Un documento nuovo, con il file facoltativo (PDF, JPG o PNG fino a 15 MB)."""
    user = await _user(db, current_user)
    blob = (await file.read(), file.content_type or "", file.filename or "") if file is not None and file.filename else None
    try:
        doc = await coach_cv.save_document(db, user=user, file=blob, data={
            "title": title, "category": category, "issuer": issuer, "issued_on": issued_on, "expires_on": expires_on,
            "description": description, "show_in_cv": show_in_cv,
        })
    except club_service.ClubError as exc:
        _raise(exc)
    return coach_cv.document_dict(doc, today=utcnow().date())


@router.patch("/documents/{document_id}")
async def update_document(document_id: uuid.UUID, payload: DocumentUpdate,
                          current_user: CurrentUser = Depends(require_permission(INSTRUCT)),
                          db: AsyncSession = Depends(get_db)) -> dict:
    user = await _user(db, current_user)
    try:
        doc = await coach_cv.get_document(db, user=user, document_id=document_id)
        doc = await coach_cv.save_document(db, user=user, data=payload.model_dump(exclude_unset=True), file=None,
                                           document=doc)
    except club_service.ClubError as exc:
        _raise(exc)
    return coach_cv.document_dict(doc, today=utcnow().date())


@router.put("/documents/{document_id}/file",
            dependencies=[Depends(rate_limit("coach-documents", max_requests=60, window_seconds=600))])
async def replace_file(document_id: uuid.UUID, file: UploadFile = File(...),
                       current_user: CurrentUser = Depends(require_permission(INSTRUCT)),
                       db: AsyncSession = Depends(get_db)) -> dict:
    """Il file nuovo di un documento (la scansione aggiornata, il rinnovo)."""
    user = await _user(db, current_user)
    try:
        doc = await coach_cv.get_document(db, user=user, document_id=document_id)
        doc = await coach_cv.save_document(db, user=user, data={}, document=doc,
                                           file=(await file.read(), file.content_type or "", file.filename or ""))
    except club_service.ClubError as exc:
        _raise(exc)
    return coach_cv.document_dict(doc, today=utcnow().date())


@router.get("/documents/{document_id}/url")
async def document_url(document_id: uuid.UUID, current_user: CurrentUser = Depends(require_permission(INSTRUCT)),
                       db: AsyncSession = Depends(get_db)) -> dict:
    """Un URL di pochi minuti per aprire o scaricare il file: solo al proprietario."""
    from app.core.storage import generate_presigned_document_url

    try:
        doc = await coach_cv.get_document(db, user=await _user(db, current_user), document_id=document_id)
    except club_service.ClubError as exc:
        _raise(exc)
    if doc.storage_key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Questo documento non ha un file.")
    return {"url": generate_presigned_document_url(storage_key=doc.storage_key), "filename": doc.original_filename}


@router.delete("/documents/{document_id}")
async def delete_document(document_id: uuid.UUID, current_user: CurrentUser = Depends(require_permission(INSTRUCT)),
                          db: AsyncSession = Depends(get_db)) -> dict:
    try:
        await coach_cv.delete_document(db, user=await _user(db, current_user), document_id=document_id)
    except club_service.ClubError as exc:
        _raise(exc)
    return {"ok": True}


# --- Il Curriculum Sportivo -----------------------------------------------------------------------


@router.get("/sport")
async def sport(current_user: CurrentUser = Depends(require_permission(INSTRUCT)), db: AsyncSession = Depends(get_db)) -> dict:
    return await coach_cv.sport_history(db, user=await _user(db, current_user))


@router.post("/sport/events", status_code=status.HTTP_201_CREATED)
async def add_event(payload: EventWrite, current_user: CurrentUser = Depends(require_permission(INSTRUCT)),
                    db: AsyncSession = Depends(get_db)) -> dict:
    try:
        event = await coach_cv.save_event(db, user=await _user(db, current_user), data=payload.model_dump())
    except club_service.ClubError as exc:
        _raise(exc)
    return coach_cv._manual_dict(event)


@router.put("/sport/events/{event_id}")
async def update_event(event_id: uuid.UUID, payload: EventWrite,
                       current_user: CurrentUser = Depends(require_permission(INSTRUCT)),
                       db: AsyncSession = Depends(get_db)) -> dict:
    try:
        event = await coach_cv.save_event(db, user=await _user(db, current_user), data=payload.model_dump(),
                                          event_id=event_id)
    except club_service.ClubError as exc:
        _raise(exc)
    return coach_cv._manual_dict(event)


@router.delete("/sport/events/{event_id}")
async def delete_event(event_id: uuid.UUID, current_user: CurrentUser = Depends(require_permission(INSTRUCT)),
                       db: AsyncSession = Depends(get_db)) -> dict:
    try:
        await coach_cv.delete_event(db, user=await _user(db, current_user), event_id=event_id)
    except club_service.ClubError as exc:
        _raise(exc)
    return {"ok": True}


# --- I PDF ----------------------------------------------------------------------------------------


@router.get("/pdf", dependencies=[Depends(rate_limit("coach-cv-pdf", max_requests=40, window_seconds=300))])
async def preview_pdf(kind: Literal["CV", "SPORT"] = Query(...),
                      current_user: CurrentUser = Depends(require_permission(INSTRUCT)),
                      db: AsyncSession = Depends(get_db)) -> Response:
    """Il PDF di adesso, da guardare o scaricare senza salvarlo."""
    try:
        content, filename = await coach_cv.pdf(db, user=await _user(db, current_user), kind=kind)
    except club_service.ClubError as exc:
        _raise(exc)
    return Response(content, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{filename}"'})


@router.get("/exports")
async def list_exports(current_user: CurrentUser = Depends(require_permission(INSTRUCT)),
                       db: AsyncSession = Depends(get_db)) -> list[dict]:
    return [_export_dict(e) for e in await coach_cv.list_exports(db, user=await _user(db, current_user))]


@router.post("/exports", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(rate_limit("coach-cv-pdf", max_requests=40, window_seconds=300))])
async def save_export(payload: ExportWrite, current_user: CurrentUser = Depends(require_permission(INSTRUCT)),
                      db: AsyncSession = Depends(get_db)) -> dict:
    try:
        row = await coach_cv.save_export(db, user=await _user(db, current_user), kind=payload.kind, note=payload.note)
    except club_service.ClubError as exc:
        _raise(exc)
    return _export_dict(row)


@router.get("/exports/{export_id}/url")
async def export_url(export_id: uuid.UUID, current_user: CurrentUser = Depends(require_permission(INSTRUCT)),
                     db: AsyncSession = Depends(get_db)) -> dict:
    from app.core.storage import generate_presigned_document_url

    try:
        row = await coach_cv.get_export(db, user=await _user(db, current_user), export_id=export_id)
    except club_service.ClubError as exc:
        _raise(exc)
    return {"url": generate_presigned_document_url(storage_key=row.storage_key), "filename": row.filename}


@router.delete("/exports/{export_id}")
async def delete_export(export_id: uuid.UUID, current_user: CurrentUser = Depends(require_permission(INSTRUCT)),
                        db: AsyncSession = Depends(get_db)) -> dict:
    try:
        await coach_cv.delete_export(db, user=await _user(db, current_user), export_id=export_id)
    except club_service.ClubError as exc:
        _raise(exc)
    return {"ok": True}
