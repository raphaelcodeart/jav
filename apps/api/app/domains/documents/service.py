import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import generate_presigned_document_url
from app.core.storage import upload_document as storage_upload_document
from app.domains.audit import service as audit_service
from app.domains.contracts.models import Contract, ContractRequest
from app.domains.documents.models import (
    DOCUMENT_TYPE_OTHER,
    DOCUMENT_TYPES,
    MAX_DOCUMENT_DESCRIPTION_LENGTH,
    MIN_DOCUMENT_DESCRIPTION_LENGTH,
    Document,
)

# Every contract needs these two regardless of customer type -- a company
# additionally needs its chamber-of-commerce registration. Kept as a plain
# constant (not read from ProductVersion.required_documents) for this first
# version -- that JSONB column exists for a future per-product override but
# nothing populates it yet, so a hardcoded sane default is more honest than
# pretending it's configurable today.
BASE_REQUIRED_DOCUMENT_TYPES = ["IDENTITY", "FISCAL_CODE"]
# Every partita IVA must prove it: a company or a ditta with its visura
# camerale, a libero professionista -- who is not in the Registro Imprese
# and has no visura -- with the certificato di attribuzione della partita
# IVA. One slot takes either (CHAMBER_OF_COMMERCE, labelled "Visura camerale
# / Certificato di attribuzione P.IVA"), so nobody is asked for a document
# they cannot have, and nobody gets through without one of the two.
COMPANY_LIKE_KINDS = {"COMPANY", "CONDOMINIUM", "SOLE_PROPRIETOR"}
CHAMBER_OF_COMMERCE_OPTIONAL_KINDS: set[str] = set()

#: Pages one document may have: front and back of an ID, a visura of 4 or
#: of 20 pages. Beyond this it is a different document, not a longer one.
MAX_PAGES_PER_DOCUMENT = 20

#: What a pratica cannot go past the documents step without:
#: the holder's identity, and for a partita IVA the visura / P.IVA
#: certificate. At least one page each.
PRATICA_BLOCKING_TYPES = ("IDENTITY", "CHAMBER_OF_COMMERCE")


class DocumentValidationError(Exception):
    pass


@dataclass(frozen=True)
class DocumentSlot:
    """One named place to upload, on this contract, for this customer kind."""

    document_type: str
    #: False for a slot that is shown and accepted but does not hold the
    #: contract back -- see CHAMBER_OF_COMMERCE_OPTIONAL_KINDS.
    required: bool


def document_slots_for(customer_kind: str) -> list[DocumentSlot]:
    slots = [DocumentSlot(document_type=t, required=True) for t in BASE_REQUIRED_DOCUMENT_TYPES]
    if customer_kind in COMPANY_LIKE_KINDS:
        slots.append(DocumentSlot(document_type="CHAMBER_OF_COMMERCE", required=True))
    elif customer_kind in CHAMBER_OF_COMMERCE_OPTIONAL_KINDS:
        slots.append(DocumentSlot(document_type="CHAMBER_OF_COMMERCE", required=False))
    return slots


#: Slots that describe the holder, not one contract: the same for every
#: contract of a pratica, so a pratica collects them once.
REQUEST_LEVEL_DOCUMENT_TYPES = frozenset({"IDENTITY", "FISCAL_CODE", "CHAMBER_OF_COMMERCE"})


def request_document_slots_for(customer_kind: str) -> list[DocumentSlot]:
    """What a pratica asks for once, for all its contracts: the holder's
    slots."""
    return [slot for slot in document_slots_for(customer_kind) if slot.document_type in REQUEST_LEVEL_DOCUMENT_TYPES]


def required_document_types_for(customer_kind: str) -> list[str]:
    """Only the types that actually block the contract. Everything that is
    merely offered (optional slots, extra attachments) is deliberately not
    here: this is the list `maybe_advance_to_under_review` gates on."""
    return [slot.document_type for slot in document_slots_for(customer_kind) if slot.required]


def normalize_document_description(description: str | None) -> str:
    """The label an uploader gives an extra attachment. Whitespace is
    collapsed so "  Delega    firmata " and "Delega firmata" are the same
    string in the admin's list, and the length is bounded on the way in
    rather than truncated on the way out."""
    cleaned = " ".join((description or "").split())
    if len(cleaned) < MIN_DOCUMENT_DESCRIPTION_LENGTH:
        raise DocumentValidationError(
            "Indica di che documento si tratta (almeno "
            f"{MIN_DOCUMENT_DESCRIPTION_LENGTH} caratteri)."
        )
    if len(cleaned) > MAX_DOCUMENT_DESCRIPTION_LENGTH:
        raise DocumentValidationError(
            f"La descrizione del documento non può superare i {MAX_DOCUMENT_DESCRIPTION_LENGTH} caratteri."
        )
    return cleaned


async def upload_document(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    contract_id: uuid.UUID | None = None,
    contract_request_id: uuid.UUID | None = None,
    document_type: str,
    file_bytes: bytes,
    content_type: str,
    original_filename: str,
    actor_user_id: uuid.UUID,
    actor_role: str,
    description: str | None = None,
) -> Document:
    """Attaches a document to one contract, or -- with `contract_request_id`
    -- to a whole pratica, where it counts for every contract in it."""
    if (contract_id is None) == (contract_request_id is None):
        raise DocumentValidationError("Un documento appartiene a un contratto oppure a una pratica.")
    if document_type not in DOCUMENT_TYPES:
        raise DocumentValidationError(f"document_type must be one of {sorted(DOCUMENT_TYPES)}")

    # Only an extra attachment carries a label, and it must carry one:
    # a slot document is already named by its type, and accepting a
    # caller-supplied label there would let "Documento d'identità" arrive
    # calling itself something else.
    description = normalize_document_description(description) if document_type == DOCUMENT_TYPE_OTHER else None

    if document_type != DOCUMENT_TYPE_OTHER:
        owner = Document.contract_id == contract_id if contract_id else Document.contract_request_id == contract_request_id
        pages = (
            await db.execute(select(func.count()).select_from(Document).where(owner, Document.document_type == document_type))
        ).scalar_one()
        if pages >= MAX_PAGES_PER_DOCUMENT:
            raise DocumentValidationError(
                f"Questo documento ha già {MAX_PAGES_PER_DOCUMENT} pagine, il massimo: "
                "togline una prima di aggiungerne un'altra."
            )

    storage_key = storage_upload_document(
        file_bytes=file_bytes, content_type=content_type,
        key_prefix=f"documents/{contract_id}" if contract_id else f"documents/requests/{contract_request_id}",
    )

    document = Document(
        organization_id=organization_id,
        contract_id=contract_id,
        contract_request_id=contract_request_id,
        document_type=document_type,
        description=description,
        original_filename=original_filename,
        storage_key=storage_key,
        content_type=content_type,
        size_bytes=len(file_bytes),
        uploaded_by_user_id=actor_user_id,
        uploaded_by_role=actor_role,
        status="PENDING_REVIEW",
    )
    db.add(document)
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="document.uploaded", entity_type="document", entity_id=str(contract_id or contract_request_id),
        new_value={
            "document_type": document_type,
            "uploaded_by_role": actor_role,
            **({"description": description} if description else {}),
        },
    )
    await db.commit()
    await db.refresh(document)

    if contract_id is not None:
        contract_ids = [contract_id]
    else:
        contract_ids = list(
            (await db.execute(select(Contract.id).where(Contract.contract_request_id == contract_request_id))).scalars()
        )
    for target_id in contract_ids:
        await maybe_advance_to_under_review(
            db, organization_id=organization_id, contract_id=target_id, actor_user_id=actor_user_id
        )
    return document


async def maybe_advance_to_under_review(
    db: AsyncSession, *, organization_id: uuid.UUID, contract_id: uuid.UUID, actor_user_id: uuid.UUID
) -> None:
    """Once every required document type has at least one uploaded document
    (any status -- staff still reviews/approves/rejects each one, this just
    signals "the customer is done, ready for a human to look"), the contract
    advances itself from SUBMITTED/DOCUMENTS_PENDING to UNDER_REVIEW. Part of
    the self-service contract flow -- see
    business-rules.md#contract-self-service. A staff-created contract that
    happens to have its documents uploaded via this same endpoint gets the
    exact same courtesy advance; there's nothing self-service-specific about
    the check itself."""
    from app.domains.contracts import service as contracts_service

    contract = await db.get(Contract, contract_id)
    if contract is None or contract.status not in ("SUBMITTED", "DOCUMENTS_PENDING"):
        return

    from app.domains.contracts.requests import contract_kind

    customer_kind = await contract_kind(db, contract)
    rows = await get_contract_documents_status(
        db, organization_id=organization_id, contract=contract, customer_kind=customer_kind
    )
    # Only the required slots gate the advance -- an offered-but-optional
    # one (and any extra attachment) must never be the reason a contract
    # sits waiting for a document nobody actually needs.
    if not all(row["document"] is not None for row in rows if row["required"]):
        return

    if contract.status == "SUBMITTED":
        contract = await contracts_service.transition_contract(
            db, organization_id=organization_id, contract=contract, to_status="DOCUMENTS_PENDING",
            actor_user_id=actor_user_id, reason=None, notes=None, correlation_id=str(uuid.uuid4()),
        )
    await contracts_service.transition_contract(
        db, organization_id=organization_id, contract=contract, to_status="UNDER_REVIEW",
        actor_user_id=actor_user_id, reason="Tutti i documenti richiesti sono stati caricati", notes=None,
        correlation_id=str(uuid.uuid4()),
    )


async def list_documents_for_contract(
    db: AsyncSession, *, organization_id: uuid.UUID, contract_id: uuid.UUID
) -> list[Document]:
    """The contract's own documents only, newest first -- not its pratica's."""
    stmt = (
        select(Document)
        .where(Document.organization_id == organization_id, Document.contract_id == contract_id)
        .order_by(Document.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def list_documents_for_request(
    db: AsyncSession, *, organization_id: uuid.UUID, contract_request_id: uuid.UUID
) -> list[Document]:
    """The documents uploaded once for a whole pratica, newest first."""
    stmt = (
        select(Document)
        .where(Document.organization_id == organization_id, Document.contract_request_id == contract_request_id)
        .order_by(Document.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


def _latest_by_type(docs: list[Document]) -> dict[str, Document]:
    latest: dict[str, Document] = {}
    for doc in sorted(docs, key=lambda d: d.created_at, reverse=True):
        latest.setdefault(doc.document_type, doc)
    return latest


def _pages_by_type(docs: list[Document]) -> dict[str, list[Document]]:
    """Every page of each document, oldest first: a slot is no
    longer one file that the next upload replaces, but the pages of one
    document -- an ID front and back, a 20-page visura."""
    pages: dict[str, list[Document]] = {}
    for doc in sorted(docs, key=lambda d: d.created_at):
        pages.setdefault(doc.document_type, []).append(doc)
    return pages


async def get_contract_documents_status(
    db: AsyncSession, *, organization_id: uuid.UUID, contract: Contract, customer_kind: str
) -> list[dict]:
    """One row per document slot: its pages (every file uploaded for it,
    oldest first), the latest of them as `document` -- None when nothing has
    been uploaded yet -- and whether the slot is required or merely offered.
    A rejected page does not disappear: the customer adds a good one, and
    both stay visible so the reviewer sees what happened.

    A document uploaded on the contract's pratica fills the same slot here:
    identity and fiscal code are uploaded once for ten
    contracts, and each of the ten sees them. When both exist, the
    contract's own wins -- it is the more specific one."""
    own = _pages_by_type(
        await list_documents_for_contract(db, organization_id=organization_id, contract_id=contract.id)
    )
    shared = _pages_by_type(
        await list_documents_for_request(
            db, organization_id=organization_id, contract_request_id=contract.contract_request_id
        )
    )
    rows = []
    for slot in document_slots_for(customer_kind):
        pages = own.get(slot.document_type) or shared.get(slot.document_type) or []
        rows.append({
            "document_type": slot.document_type,
            "required": slot.required,
            "document": pages[-1] if pages else None,
            "pages": pages,
        })
    return rows


async def get_request_documents_status(
    db: AsyncSession, *, organization_id: uuid.UUID, request: ContractRequest, customer_kind: str
) -> list[dict]:
    """Same shape as get_contract_documents_status, for the slots a pratica
    collects once (request_document_slots_for). The PRATICA_BLOCKING_TYPES
    are required here: a pratica does not go past its
    documents without them."""
    shared = _pages_by_type(
        await list_documents_for_request(db, organization_id=organization_id, contract_request_id=request.id)
    )
    rows = []
    for slot in request_document_slots_for(customer_kind):
        pages = shared.get(slot.document_type, [])
        rows.append({
            "document_type": slot.document_type,
            "required": slot.required or slot.document_type in PRATICA_BLOCKING_TYPES,
            "document": pages[-1] if pages else None,
            "pages": pages,
        })
    return rows


async def pratica_blocking_missing(
    db: AsyncSession, *, request: ContractRequest, customer_kind: str
) -> list[str]:
    """The document types a pratica still lacks before it may go on: the
    holder's identity and -- for a partita IVA -- the visura / P.IVA
    certificate, at least one page each."""
    from app.domains.documents.schemas import DOCUMENT_TYPE_LABELS

    shared = _pages_by_type(
        await list_documents_for_request(db, organization_id=request.organization_id, contract_request_id=request.id)
    )
    wanted = {slot.document_type for slot in request_document_slots_for(customer_kind) if slot.required}
    missing = []
    for document_type in PRATICA_BLOCKING_TYPES:
        if document_type in wanted and not shared.get(document_type):
            missing.append(DOCUMENT_TYPE_LABELS[document_type])
    return missing


async def get_extra_documents_for_request(
    db: AsyncSession, *, organization_id: uuid.UUID, request: ContractRequest, customer_kind: str
) -> list[Document]:
    slot_types = {slot.document_type for slot in request_document_slots_for(customer_kind)}
    docs = await list_documents_for_request(db, organization_id=organization_id, contract_request_id=request.id)
    return [doc for doc in reversed(docs) if doc.document_type not in slot_types]


async def get_extra_documents_for_contract(
    db: AsyncSession, *, organization_id: uuid.UUID, contract: Contract, customer_kind: str
) -> list[Document]:
    """Everything attached to this contract that no slot accounts for.

    That is every OTHER attachment (all of them, oldest first -- unlike a
    slot, a second extra document does not supersede the first), and also
    any document whose type simply has no slot for this customer kind --
    a visura uploaded back when the customer was registered as a company,
    say. Those would otherwise vanish from the screen while still sitting in
    the bucket, which is the one thing a documents list must not do."""
    slot_types = {slot.document_type for slot in document_slots_for(customer_kind)}
    docs = await list_documents_for_contract(db, organization_id=organization_id, contract_id=contract.id)
    return [doc for doc in reversed(docs) if doc.document_type not in slot_types]


async def get_document(db: AsyncSession, *, organization_id: uuid.UUID, document_id: uuid.UUID) -> Document | None:
    document = await db.get(Document, document_id)
    if document is None or document.organization_id != organization_id:
        return None
    return document


async def get_presigned_url_for_document(document: Document) -> str:
    return generate_presigned_document_url(storage_key=document.storage_key)


class DocumentDeletionError(Exception):
    pass


async def delete_document(db: AsyncSession, *, document: Document, actor_user_id: uuid.UUID) -> None:
    """Takes one page out of a document -- the blurry photo, the wrong page.
    Never an approved one: that is part of what the contract was checked
    against. Access is the caller's job, as for every function here."""
    from app.core.storage import delete_document_object

    if document.status == "APPROVED":
        raise DocumentDeletionError("Un documento già approvato non si può togliere.")
    await audit_service.record(
        db, organization_id=document.organization_id, actor_user_id=actor_user_id,
        action="document.deleted", entity_type="document", entity_id=str(document.id),
        previous_value={
            "document_type": document.document_type, "original_filename": document.original_filename,
            "status": document.status,
        },
    )
    storage_key = document.storage_key
    await db.delete(document)
    await db.commit()
    delete_document_object(storage_key=storage_key)


async def review_document(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    new_status: str,
    review_note: str | None,
    actor_user_id: uuid.UUID,
) -> Document | None:
    document = await get_document(db, organization_id=organization_id, document_id=document_id)
    if document is None:
        return None

    previous_status = document.status
    document.status = new_status
    document.review_note = review_note
    document.reviewed_by_user_id = actor_user_id
    document.reviewed_at = datetime.now(UTC)

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="document.reviewed", entity_type="document", entity_id=str(document_id),
        previous_value={"status": previous_status}, new_value={"status": new_status},
        reason=review_note,
    )
    await db.commit()
    await db.refresh(document)
    return document
