"""API delle richieste di prodotto (vedi models.py per perché è separata
da `support`).

Chi chiede: qualsiasi utente autenticato, e vede solo le proprie. Chi
risponde: lo staff con `tickets.respond`, lo stesso permesso di chi
risponde ai ticket -- sono le stesse persone, e un permesso in più da
assegnare a mano sarebbe solo un modo per scoprire a sorpresa che nessuno
vede le richieste. Eliminare: `tickets.delete`."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, get_current_user, require_permission
from app.core.rate_limit import rate_limit
from app.domains.product_requests import service
from app.domains.product_requests.schemas import (
    ProductRequestCreate,
    ProductRequestDetailRead,
    ProductRequestMessageCreate,
    ProductRequestRead,
    ProductRequestStatusUpdate,
)

router = APIRouter(prefix="/product-requests", tags=["product-requests"])

STAFF = "tickets.respond"


# --- Cliente ---------------------------------------------------------------------------------------


@router.post(
    "",
    response_model=ProductRequestRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("product-request-create", max_requests=10, window_seconds=600))],
)
async def create_product_request(
    payload: ProductRequestCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProductRequestRead:
    request = await service.create_request(
        db, organization_id=current_user.organization_id, actor_user_id=current_user.user_id,
        actor_role=service.opener_role_for(current_user.roles), payload=payload,
    )
    return ProductRequestRead(**(await service.read_one(db, organization_id=current_user.organization_id, request=request)))


@router.get("/mine", response_model=list[ProductRequestRead])
async def list_my_product_requests(
    current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[ProductRequestRead]:
    rows = await service.list_mine(db, organization_id=current_user.organization_id, user_id=current_user.user_id)
    return [ProductRequestRead(**r) for r in rows]


@router.get("/mine/{request_id}", response_model=ProductRequestDetailRead)
async def get_my_product_request(
    request_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProductRequestDetailRead:
    row = await service.get_detail(
        db, organization_id=current_user.organization_id, request_id=request_id,
        requester_user_id=current_user.user_id, requester_is_staff=False,
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Richiesta non trovata.")
    return ProductRequestDetailRead(**row)


@router.post("/mine/{request_id}/messages", response_model=ProductRequestRead)
async def reply_to_my_product_request(
    request_id: uuid.UUID,
    payload: ProductRequestMessageCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProductRequestRead:
    try:
        request = await service.add_message(
            db, organization_id=current_user.organization_id, request_id=request_id,
            actor_user_id=current_user.user_id, actor_role=service.opener_role_for(current_user.roles),
            requester_is_staff=False, payload=payload,
        )
    except service.ProductRequestClosedError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Richiesta non trovata.")
    return ProductRequestRead(**(await service.read_one(db, organization_id=current_user.organization_id, request=request)))


# --- Staff -----------------------------------------------------------------------------------------


@router.get("", response_model=list[ProductRequestRead])
async def list_product_requests(
    current_user: CurrentUser = Depends(require_permission(STAFF)), db: AsyncSession = Depends(get_db)
) -> list[ProductRequestRead]:
    return [ProductRequestRead(**r) for r in await service.list_all(db, organization_id=current_user.organization_id)]


@router.get("/{request_id}", response_model=ProductRequestDetailRead)
async def get_product_request(
    request_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission(STAFF)),
    db: AsyncSession = Depends(get_db),
) -> ProductRequestDetailRead:
    row = await service.get_detail(
        db, organization_id=current_user.organization_id, request_id=request_id,
        requester_user_id=current_user.user_id, requester_is_staff=True,
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Richiesta non trovata.")
    return ProductRequestDetailRead(**row)


@router.post("/{request_id}/messages", response_model=ProductRequestRead)
async def reply_to_product_request(
    request_id: uuid.UUID,
    payload: ProductRequestMessageCreate,
    current_user: CurrentUser = Depends(require_permission(STAFF)),
    db: AsyncSession = Depends(get_db),
) -> ProductRequestRead:
    try:
        request = await service.add_message(
            db, organization_id=current_user.organization_id, request_id=request_id,
            actor_user_id=current_user.user_id, actor_role=service.STAFF_ROLE,
            requester_is_staff=True, payload=payload,
        )
    except service.ProductRequestClosedError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Richiesta non trovata.")
    return ProductRequestRead(**(await service.read_one(db, organization_id=current_user.organization_id, request=request)))


@router.patch("/{request_id}/status", response_model=ProductRequestRead)
async def update_product_request_status(
    request_id: uuid.UUID,
    payload: ProductRequestStatusUpdate,
    current_user: CurrentUser = Depends(require_permission(STAFF)),
    db: AsyncSession = Depends(get_db),
) -> ProductRequestRead:
    request = await service.update_status(
        db, organization_id=current_user.organization_id, request_id=request_id,
        actor_user_id=current_user.user_id, payload=payload,
    )
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Richiesta non trovata.")
    return ProductRequestRead(**(await service.read_one(db, organization_id=current_user.organization_id, request=request)))


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product_request(
    request_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("tickets.delete")),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        result = await service.delete_request(
            db, organization_id=current_user.organization_id, request_id=request_id,
            actor_user_id=current_user.user_id,
        )
    except service.ProductRequestDeletionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Richiesta non trovata.")
