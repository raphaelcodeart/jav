"""Richieste di prodotto dallo Shop: la stessa meccanica dei ticket di
`support` (una richiesta, una conversazione, uno stato), su tabelle proprie.

Differenze volute rispetto ai ticket:

- ogni risposta dello staff avvisa il cliente (notifica in app + email):
  chi chiede un prodotto non torna a controllare ogni giorno, e una
  risposta che nessuno legge è una vendita persa;
- ogni risposta del cliente avvisa lo staff, per lo stesso motivo al
  contrario;
- gli stati parlano di prodotti, non di guasti: «Trovato», «Non trovato».
"""

import html
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.email import send_html_email_best_effort
from app.core.email_templates import render_email
from app.domains.audit import service as audit_service
from app.domains.notifications import service as notifications_service
from app.domains.organizations import service as organizations_service
from app.domains.product_requests.models import ProductRequest, ProductRequestMessage
from app.domains.product_requests.schemas import (
    ProductRequestCreate,
    ProductRequestMessageCreate,
    ProductRequestStatusUpdate,
)
from app.domains.support.service import _display_names_for_users
from app.domains.users.models import User

STAFF_ROLE = "ADMIN"
# Dopo questi stati la richiesta e' conclusa: si puo' eliminare.
DELETABLE_STATUSES = {"FOUND", "NOT_FOUND", "CLOSED"}
STATUS_LABELS = {
    "OPEN": "Aperta",
    "IN_PROGRESS": "In lavorazione",
    "FOUND": "Trovato",
    "NOT_FOUND": "Non trovato",
    "CLOSED": "Chiusa",
}


class ProductRequestDeletionError(Exception):
    pass


class ProductRequestClosedError(Exception):
    pass


def opener_role_for(roles: list[str]) -> str:
    if "CUSTOMER" in roles:
        return "CUSTOMER"
    if "PROMOTER" in roles:
        return "PROMOTER"
    return STAFF_ROLE


async def _enrich(db: AsyncSession, *, organization_id: uuid.UUID, requests: list[ProductRequest]) -> list[dict]:
    if not requests:
        return []
    ids = [r.id for r in requests]
    names = await _display_names_for_users(
        db, organization_id=organization_id, user_ids={r.opened_by_user_id for r in requests}
    )
    stats = {
        row[0]: (row[1], row[2])
        for row in (
            await db.execute(
                select(ProductRequestMessage.request_id, func.count(), func.max(ProductRequestMessage.created_at))
                .where(ProductRequestMessage.request_id.in_(ids))
                .group_by(ProductRequestMessage.request_id)
            )
        ).all()
    }
    last_roles: dict[uuid.UUID, str] = {}
    for request_id, role in (
        await db.execute(
            select(ProductRequestMessage.request_id, ProductRequestMessage.author_role)
            .where(ProductRequestMessage.request_id.in_(ids))
            .order_by(ProductRequestMessage.request_id, ProductRequestMessage.created_at.desc())
            .distinct(ProductRequestMessage.request_id)
        )
    ).all():
        last_roles[request_id] = role

    result = []
    for r in requests:
        count, last_at = stats.get(r.id, (0, None))
        result.append(
            {
                "id": r.id,
                "opened_by_user_id": r.opened_by_user_id,
                "opened_by_role": r.opened_by_role,
                "opened_by_name": names.get(r.opened_by_user_id),
                "product_name": r.product_name,
                "reference_url": r.reference_url,
                "status": r.status,
                "created_at": r.created_at,
                "message_count": count,
                "last_message_at": last_at,
                "last_author_role": last_roles.get(r.id),
            }
        )
    result.sort(key=lambda x: x["last_message_at"] or x["created_at"], reverse=True)
    return result


async def _get(db: AsyncSession, *, organization_id: uuid.UUID, request_id: uuid.UUID) -> ProductRequest | None:
    request = await db.get(ProductRequest, request_id)
    if request is None or request.organization_id != organization_id:
        return None
    return request


async def read_one(db: AsyncSession, *, organization_id: uuid.UUID, request: ProductRequest) -> dict:
    return (await _enrich(db, organization_id=organization_id, requests=[request]))[0]


async def create_request(
    db: AsyncSession, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID, actor_role: str,
    payload: ProductRequestCreate,
) -> ProductRequest:
    request = ProductRequest(
        organization_id=organization_id, opened_by_user_id=actor_user_id, opened_by_role=actor_role,
        product_name=payload.product_name, reference_url=payload.reference_url, status="OPEN",
    )
    db.add(request)
    await db.flush()
    db.add(
        ProductRequestMessage(
            request_id=request.id, author_user_id=actor_user_id, author_role=actor_role, body=payload.message
        )
    )
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="product_request.created", entity_type="product_request", entity_id=str(request.id),
        new_value={"product_name": payload.product_name},
    )
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="PRODUCT_REQUEST_CREATED", entity_type="product_request", entity_id=request.id,
        title=f"Richiesta prodotto: {payload.product_name}", body=payload.message[:200],
        exclude_user_id=actor_user_id,
    )
    await db.commit()
    await db.refresh(request)
    await _email_staff_new_request(db, organization_id=organization_id, request=request, message=payload.message)
    return request


async def _email_staff_new_request(
    db: AsyncSession, *, organization_id: uuid.UUID, request: ProductRequest, message: str
) -> None:
    """Best-effort, dopo il commit: una email che non parte non deve far
    sparire una richiesta già salvata (la notifica in app c'è comunque)."""
    admin_email = await organizations_service.get_admin_notification_email(db, organization_id=organization_id)
    name = html.escape(request.product_name)
    link = f'<p><strong>Link:</strong> {html.escape(request.reference_url)}</p>' if request.reference_url else ""
    send_html_email_best_effort(
        context=f"Product-request admin email (request={request.id})",
        to=admin_email,
        subject=f"[Jav] Richiesta prodotto: {request.product_name}",
        html_body=render_email(
            preheader=f"Un cliente cerca: {request.product_name}",
            heading="Nuova richiesta di prodotto",
            body_html=(
                f"<p><strong>Prodotto cercato:</strong> {name}</p>{link}"
                f"<p style=\"white-space:pre-wrap;\">{html.escape(message[:1000])}</p>"
            ),
            cta_label="Apri la richiesta",
            cta_url=f"{get_settings().public_app_base_url}/admin",
        ),
        text_body=f"Un cliente cerca: {request.product_name}\n\n{message[:1000]}",
    )


async def list_all(db: AsyncSession, *, organization_id: uuid.UUID) -> list[dict]:
    rows = (await db.execute(select(ProductRequest).where(ProductRequest.organization_id == organization_id))).scalars()
    return await _enrich(db, organization_id=organization_id, requests=list(rows))


async def list_mine(db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID) -> list[dict]:
    rows = (
        await db.execute(
            select(ProductRequest).where(
                ProductRequest.organization_id == organization_id, ProductRequest.opened_by_user_id == user_id
            )
        )
    ).scalars()
    return await _enrich(db, organization_id=organization_id, requests=list(rows))


async def get_detail(
    db: AsyncSession, *, organization_id: uuid.UUID, request_id: uuid.UUID,
    requester_user_id: uuid.UUID, requester_is_staff: bool,
) -> dict | None:
    """Lo staff vede tutte le richieste dell'organizzazione, gli altri solo
    le proprie -- una richiesta altrui risponde 404, non 403, per non dire
    nemmeno che esiste."""
    request = await _get(db, organization_id=organization_id, request_id=request_id)
    if request is None or (not requester_is_staff and request.opened_by_user_id != requester_user_id):
        return None
    detail = await read_one(db, organization_id=organization_id, request=request)
    messages = (
        await db.execute(
            select(ProductRequestMessage)
            .where(ProductRequestMessage.request_id == request_id)
            .order_by(ProductRequestMessage.created_at)
        )
    ).scalars().all()
    names = await _display_names_for_users(
        db, organization_id=organization_id, user_ids={m.author_user_id for m in messages}
    )
    detail["messages"] = [
        {
            "id": m.id, "request_id": m.request_id, "author_user_id": m.author_user_id,
            "author_role": m.author_role, "author_name": names.get(m.author_user_id),
            "body": m.body, "created_at": m.created_at,
        }
        for m in messages
    ]
    return detail


async def add_message(
    db: AsyncSession, *, organization_id: uuid.UUID, request_id: uuid.UUID, actor_user_id: uuid.UUID,
    actor_role: str, requester_is_staff: bool, payload: ProductRequestMessageCreate,
) -> ProductRequest | None:
    request = await _get(db, organization_id=organization_id, request_id=request_id)
    if request is None or (not requester_is_staff and request.opened_by_user_id != actor_user_id):
        return None
    if request.status == "CLOSED":
        raise ProductRequestClosedError("Questa richiesta è chiusa: aprine una nuova dallo Shop.")
    body = payload.body.strip()
    if not body:
        raise ProductRequestClosedError("Il messaggio è vuoto.")

    db.add(ProductRequestMessage(request_id=request_id, author_user_id=actor_user_id, author_role=actor_role, body=body))
    if requester_is_staff:
        # Come nei ticket: la prima risposta dello staff dice al cliente
        # che qualcuno ci sta lavorando, senza un clic in più sullo stato.
        if request.status == "OPEN":
            request.status = "IN_PROGRESS"
        await notifications_service.notify_user(
            db, organization_id=organization_id, user_id=request.opened_by_user_id,
            type_="PRODUCT_REQUEST_REPLY", entity_type="product_request", entity_id=request.id,
            title=f"Risposta alla tua richiesta: {request.product_name}", body=body[:200],
        )
    else:
        await notifications_service.notify_roles(
            db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
            type_="PRODUCT_REQUEST_CUSTOMER_REPLY", entity_type="product_request", entity_id=request.id,
            title=f"Il cliente ha risposto: {request.product_name}", body=body[:200],
            exclude_user_id=actor_user_id,
        )
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="product_request.message_added", entity_type="product_request", entity_id=str(request_id),
        new_value={"author_role": actor_role},
    )
    await db.commit()
    await db.refresh(request)
    if requester_is_staff:
        await _email_opener_reply(db, request=request, body=body)
    return request


async def _email_opener_reply(db: AsyncSession, *, request: ProductRequest, body: str) -> None:
    user = await db.get(User, request.opened_by_user_id)
    if user is None or not user.email:
        return
    send_html_email_best_effort(
        context=f"Product-request reply email (request={request.id})",
        to=user.email,
        subject=f"Risposta alla tua richiesta: {request.product_name}",
        html_body=render_email(
            preheader=f"Ti abbiamo risposto su «{request.product_name}»",
            heading="Abbiamo una risposta per te",
            body_html=(
                f"<p>Sulla tua richiesta <strong>«{html.escape(request.product_name)}»</strong> "
                "ti abbiamo scritto:</p>"
                f"<p style=\"white-space:pre-wrap;\">{html.escape(body[:1000])}</p>"
                "<p>Puoi rispondere dall'area clienti, in «Le mie richieste».</p>"
            ),
            cta_label="Leggi e rispondi",
            cta_url=f"{get_settings().public_app_base_url}/customer?tab=product-requests",
        ),
        text_body=f"Sulla tua richiesta «{request.product_name}» ti abbiamo scritto:\n\n{body[:1000]}",
    )


async def update_status(
    db: AsyncSession, *, organization_id: uuid.UUID, request_id: uuid.UUID, actor_user_id: uuid.UUID,
    payload: ProductRequestStatusUpdate,
) -> ProductRequest | None:
    request = await _get(db, organization_id=organization_id, request_id=request_id)
    if request is None:
        return None
    previous = request.status
    request.status = payload.status
    if previous != payload.status:
        await notifications_service.notify_user(
            db, organization_id=organization_id, user_id=request.opened_by_user_id,
            type_="PRODUCT_REQUEST_REPLY", entity_type="product_request", entity_id=request.id,
            title=f"«{request.product_name}»: {STATUS_LABELS.get(payload.status, payload.status)}",
        )
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="product_request.status_changed", entity_type="product_request", entity_id=str(request_id),
        previous_value={"status": previous}, new_value={"status": payload.status},
    )
    await db.commit()
    await db.refresh(request)
    return request


async def delete_request(
    db: AsyncSession, *, organization_id: uuid.UUID, request_id: uuid.UUID, actor_user_id: uuid.UUID
) -> bool | None:
    request = await _get(db, organization_id=organization_id, request_id=request_id)
    if request is None:
        return None
    if request.status not in DELETABLE_STATUSES:
        raise ProductRequestDeletionError("Si può eliminare solo una richiesta conclusa (trovato, non trovato o chiusa).")
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="product_request.deleted", entity_type="product_request", entity_id=str(request_id),
        previous_value={"product_name": request.product_name, "status": request.status},
    )
    await db.execute(delete(ProductRequestMessage).where(ProductRequestMessage.request_id == request_id))
    await db.delete(request)
    await db.commit()
    return True
