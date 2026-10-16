"""I documenti del club: dichiarazioni, rivalidazione alla federazione,
atas, certidões delle Finanze e della Segurança Social, certificazioni
sportive, assicurazioni, statuto. Specifica: docs/club-portal.md,
"Documenti del club".

Li carica e li gestisce la segreteria del club (o la piattaforma entrando
nel club). Il file va nel bucket privato (CLAUDE.md §5) e si apre con un
URL presigned di pochi minuti. Una certidão scade: con una data di
scadenza, la segreteria riceve un avviso 30 giorni prima e il giorno in cui
scade (una volta sola per documento e momento: `club_reminders_sent`).

Un documento può essere condiviso con i soci (`shared_with_members`): il
regolamento interno, il calendario della stagione. Allora compare nella
bacheca di atleti e famiglie del club (news.py), che lo aprono con lo
stesso link di pochi minuti. Gli altri restano dello staff.
"""

import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import UploadValidationError, delete_document_object, upload_document
from app.domains.audit import service as audit_service
from app.domains.club.operations_models import CLUB_DOCUMENT_CATEGORIES, ClubDocument
from app.domains.club.scope import ClubScope
from app.domains.club.service import ClubNotFoundError, ClubValidationError

#: Quanti giorni prima della scadenza si avvisa (e il documento si mostra
#: "in scadenza").
EXPIRY_NOTICE_DAYS = 30
MAX_TITLE = 200
MAX_NOTES = 2000


def status_of(doc: ClubDocument, *, today: date) -> str:
    """NONE (senza scadenza), VALID, EXPIRING (entro 30 giorni), EXPIRED."""
    if doc.expires_on is None:
        return "NONE"
    if doc.expires_on < today:
        return "EXPIRED"
    if doc.expires_on <= today + timedelta(days=EXPIRY_NOTICE_DAYS):
        return "EXPIRING"
    return "VALID"


def document_dict(doc: ClubDocument, *, today: date) -> dict:
    return {
        "id": doc.id, "category": doc.category, "title": doc.title, "issued_on": doc.issued_on,
        "expires_on": doc.expires_on, "notes": doc.notes, "original_filename": doc.original_filename,
        "size_bytes": doc.size_bytes, "status": status_of(doc, today=today), "created_at": doc.created_at,
        "shared_with_members": doc.shared_with_members,
    }


def _clean(data: dict) -> dict:
    out = {}
    if "category" in data:
        if data["category"] not in CLUB_DOCUMENT_CATEGORIES:
            raise ClubValidationError("Scegli il tipo di documento.")
        out["category"] = data["category"]
    if "title" in data:
        title = " ".join((data["title"] or "").split())[:MAX_TITLE]
        if not title:
            raise ClubValidationError("Dai un titolo al documento (es. «Certidão de não dívida — Finanças 2026»).")
        out["title"] = title
    for key in ("issued_on", "expires_on"):
        if key in data:
            out[key] = data[key]
    if "notes" in data:
        out["notes"] = (data["notes"] or "").strip()[:MAX_NOTES] or None
    if data.get("shared_with_members") is not None:
        out["shared_with_members"] = bool(data["shared_with_members"])
    return out


def _check_dates(doc: ClubDocument) -> None:
    if doc.issued_on and doc.expires_on and doc.expires_on < doc.issued_on:
        raise ClubValidationError("La scadenza non può essere prima della data del documento.")


async def list_documents(db: AsyncSession, *, scope: ClubScope) -> list[ClubDocument]:
    stmt = select(ClubDocument).where(ClubDocument.club_id == scope.club_id)
    return list((await db.execute(stmt.order_by(ClubDocument.category, ClubDocument.created_at.desc()))).scalars())


async def get_document(db: AsyncSession, *, scope: ClubScope, document_id: uuid.UUID) -> ClubDocument:
    doc = await db.get(ClubDocument, document_id)
    if doc is None or doc.club_id != scope.club_id:
        raise ClubNotFoundError("Documento non trovato.")
    return doc


async def list_member_documents(db: AsyncSession, *, scope: ClubScope) -> list[ClubDocument]:
    """I documenti che il club ha condiviso con atleti e famiglie."""
    stmt = select(ClubDocument).where(ClubDocument.club_id == scope.club_id, ClubDocument.shared_with_members.is_(True))
    return list((await db.execute(stmt.order_by(ClubDocument.created_at.desc()))).scalars())


async def get_member_document(db: AsyncSession, *, scope: ClubScope, document_id: uuid.UUID) -> ClubDocument:
    doc = await get_document(db, scope=scope, document_id=document_id)
    if not doc.shared_with_members:
        raise ClubNotFoundError("Documento non trovato.")
    return doc


async def add_document(
    db: AsyncSession, *, scope: ClubScope, actor_user_id: uuid.UUID, data: dict, file_bytes: bytes,
    content_type: str, filename: str,
) -> ClubDocument:
    values = _clean({"category": data.get("category"), "title": data.get("title"), **{
        k: data.get(k) for k in ("issued_on", "expires_on", "notes", "shared_with_members")
    }})
    doc = ClubDocument(**scope.columns(), **values, storage_key="", original_filename=(filename or "documento")[:255],
                       content_type=content_type, size_bytes=len(file_bytes), uploaded_by_user_id=actor_user_id)
    _check_dates(doc)
    try:
        doc.storage_key = upload_document(
            file_bytes=file_bytes, content_type=content_type, key_prefix=f"club-documents/{scope.club_id}"
        )
    except UploadValidationError as exc:
        raise ClubValidationError("Carica un PDF o una foto (JPG o PNG), di massimo 15 MB.") from exc
    db.add(doc)
    await db.flush()
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id, action="club.document_added",
        entity_type="club_document", entity_id=str(doc.id), new_value={"category": doc.category, "title": doc.title},
    )
    await db.commit()
    await db.refresh(doc)
    return doc


async def update_document(
    db: AsyncSession, *, scope: ClubScope, document_id: uuid.UUID, actor_user_id: uuid.UUID, changes: dict,
) -> ClubDocument:
    doc = await get_document(db, scope=scope, document_id=document_id)
    for key, value in _clean(changes).items():
        setattr(doc, key, value)
    _check_dates(doc)
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id, action="club.document_updated",
        entity_type="club_document", entity_id=str(doc.id), new_value={k: str(v) for k, v in changes.items()},
    )
    await db.commit()
    await db.refresh(doc)
    return doc


async def remove_document(db: AsyncSession, *, scope: ClubScope, document_id: uuid.UUID, actor_user_id: uuid.UUID) -> None:
    doc = await get_document(db, scope=scope, document_id=document_id)
    key = doc.storage_key
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id, action="club.document_removed",
        entity_type="club_document", entity_id=str(doc.id), previous_value={"category": doc.category, "title": doc.title},
    )
    await db.delete(doc)
    await db.commit()
    delete_document_object(storage_key=key)


async def expiry_reminders(db: AsyncSession, *, scope: ClubScope, today: date) -> int:
    """Gli avvisi alla segreteria: 30 giorni prima e il giorno della
    scadenza. Idempotente per (documento, momento). Non committa: lo fa
    send_reminders (tasks.py), insieme agli altri promemoria."""
    from app.domains.club.clubs import notify_club_staff
    from app.domains.club.tasks import _claim_reminder

    docs = (await db.execute(select(ClubDocument).where(
        ClubDocument.club_id == scope.club_id, ClubDocument.expires_on.is_not(None),
        ClubDocument.expires_on <= today + timedelta(days=EXPIRY_NOTICE_DAYS),
        ClubDocument.expires_on >= today - timedelta(days=1),
    ))).scalars().all()
    sent = 0
    for doc in docs:
        stage = "expired" if doc.expires_on <= today else "soon"
        if not await _claim_reminder(db, organization_id=scope.organization_id, kind="CLUB_DOCUMENT",
                                     entity_id=str(doc.id), stage=stage):
            continue
        title = (f"Scade oggi: «{doc.title}»" if stage == "expired"
                 else f"«{doc.title}» scade il {doc.expires_on.strftime('%d/%m/%Y')}")
        await notify_club_staff(db, scope=scope, type_="CLUB_DOCUMENT_EXPIRING", entity_id=doc.id, title=title,
                                body="Caricane la versione nuova in Documenti del club.", entity_type="club_document")
        sent += 1
    return sent
