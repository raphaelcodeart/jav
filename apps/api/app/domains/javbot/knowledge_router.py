"""Le API della base di conoscenza di JAVBOT (knowledge.py).

- `/club/admin/javbot/...`  la segreteria del club (`club.manage`, il club
  lo decide club/scope.py): i PDF e le istruzioni **del club**; i documenti
  e le istruzioni comuni li vede, non li tocca;
- `/javbot/admin/...`       la piattaforma (`clubs.manage`, chi crea e
  modifica i club): la base **comune** a tutti i club.

Stesse rotte, stesso codice: cambia solo il livello (`knowledge.Level`).
"""

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rate_limit import rate_limit
from app.domains.club.scope import CLUBS_MANAGE, ClubUser, require_club_permission
from app.domains.javbot import assistant, knowledge
from app.domains.javbot.schemas import DocumentLinkRead, InstructionsWrite, KnowledgeDocumentRead, KnowledgeRead
from app.domains.javbot.tools import MANAGE

club_knowledge_router = APIRouter(prefix="/club/admin/javbot", tags=["club-admin"])
platform_knowledge_router = APIRouter(prefix="/javbot/admin", tags=["javbot"])

_UPLOAD_LIMIT = rate_limit("javbot-knowledge-upload", max_requests=30, window_seconds=600)


def _raise(exc: knowledge.KnowledgeError) -> None:
    code = status.HTTP_404_NOT_FOUND if isinstance(exc, knowledge.KnowledgeNotFoundError) else status.HTTP_400_BAD_REQUEST
    raise HTTPException(code, str(exc)) from exc


def _docs(documents) -> list[KnowledgeDocumentRead]:
    return [KnowledgeDocumentRead(**knowledge.document_dict(d)) for d in documents]


async def _read(db: AsyncSession, level: knowledge.Level) -> KnowledgeRead:
    common = knowledge.Level(level.organization_id, None)
    is_club = level.club_id is not None
    return KnowledgeRead(
        documents=_docs(await knowledge.list_documents(db, level=level)),
        common_documents=_docs(await knowledge.list_documents(db, level=common)) if is_club else [],
        instructions=await knowledge.get_instructions(db, level=level),
        common_instructions=await knowledge.get_instructions(db, level=common) if is_club else "",
        assistant_enabled=assistant.enabled(),
    )


async def _upload(db, level, file: UploadFile, title: str | None, user_id: uuid.UUID) -> KnowledgeDocumentRead:
    try:
        document = await knowledge.add_document(
            db, level=level, file_bytes=await file.read(), content_type=file.content_type or "",
            filename=file.filename or "", title=title, actor_user_id=user_id,
        )
    except knowledge.KnowledgeError as exc:
        _raise(exc)
    return KnowledgeDocumentRead(**knowledge.document_dict(document))


async def _link(db, level, document_id: uuid.UUID) -> DocumentLinkRead:
    try:
        document = await knowledge.get_document(db, level=level, document_id=document_id)
    except knowledge.KnowledgeError as exc:
        _raise(exc)
    return DocumentLinkRead(url=knowledge.document_url(document))


async def _remove(db, level, document_id: uuid.UUID) -> None:
    try:
        await knowledge.remove_document(db, level=level, document_id=document_id)
    except knowledge.KnowledgeError as exc:
        _raise(exc)


async def _instructions(db, level, payload: InstructionsWrite, user_id: uuid.UUID) -> KnowledgeRead:
    try:
        await knowledge.set_instructions(db, level=level, text=payload.text, actor_user_id=user_id)
    except knowledge.KnowledgeError as exc:
        _raise(exc)
    return await _read(db, level)


# --- Il club --------------------------------------------------------------------------------------


def _club_level(user: ClubUser) -> knowledge.Level:
    return knowledge.Level(user.organization_id, user.club_id)


@club_knowledge_router.get("/knowledge", response_model=KnowledgeRead)
async def club_knowledge(
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> KnowledgeRead:
    return await _read(db, _club_level(current_user))


@club_knowledge_router.post(
    "/knowledge/documents", response_model=KnowledgeDocumentRead, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_UPLOAD_LIMIT)],
)
async def club_upload(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeDocumentRead:
    return await _upload(db, _club_level(current_user), file, title, current_user.user_id)


@club_knowledge_router.get("/knowledge/documents/{document_id}/link", response_model=DocumentLinkRead)
async def club_document_link(
    document_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> DocumentLinkRead:
    return await _link(db, _club_level(current_user), document_id)


@club_knowledge_router.delete("/knowledge/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def club_remove(
    document_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _remove(db, _club_level(current_user), document_id)


@club_knowledge_router.put("/knowledge/instructions", response_model=KnowledgeRead)
async def club_set_instructions(
    payload: InstructionsWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeRead:
    return await _instructions(db, _club_level(current_user), payload, current_user.user_id)


# --- La piattaforma: la base comune ---------------------------------------------------------------


def _common_level(user: CurrentUser) -> knowledge.Level:
    return knowledge.Level(user.organization_id, None)


@platform_knowledge_router.get("/knowledge", response_model=KnowledgeRead)
async def common_knowledge(
    current_user: CurrentUser = Depends(require_permission(CLUBS_MANAGE)), db: AsyncSession = Depends(get_db),
) -> KnowledgeRead:
    return await _read(db, _common_level(current_user))


@platform_knowledge_router.post(
    "/knowledge/documents", response_model=KnowledgeDocumentRead, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_UPLOAD_LIMIT)],
)
async def common_upload(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    current_user: CurrentUser = Depends(require_permission(CLUBS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeDocumentRead:
    return await _upload(db, _common_level(current_user), file, title, current_user.user_id)


@platform_knowledge_router.get("/knowledge/documents/{document_id}/link", response_model=DocumentLinkRead)
async def common_document_link(
    document_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission(CLUBS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> DocumentLinkRead:
    return await _link(db, _common_level(current_user), document_id)


@platform_knowledge_router.delete("/knowledge/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def common_remove(
    document_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission(CLUBS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _remove(db, _common_level(current_user), document_id)


@platform_knowledge_router.put("/knowledge/instructions", response_model=KnowledgeRead)
async def common_set_instructions(
    payload: InstructionsWrite,
    current_user: CurrentUser = Depends(require_permission(CLUBS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeRead:
    return await _instructions(db, _common_level(current_user), payload, current_user.user_id)
