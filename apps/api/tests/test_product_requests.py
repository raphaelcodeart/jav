"""Richieste di prodotto dallo Shop: un sistema di ticket dedicato, separato
dal supporto. Copre il giro completo (il cliente chiede, lo staff risponde,
il cliente risponde), la visibilità (solo le proprie), le notifiche nelle
due direzioni, e la separazione dalle tabelle dei ticket."""

import uuid

import pytest
from sqlalchemy import func, select

from app.core.security import hash_password
from app.domains.notifications.models import Notification
from app.domains.product_requests import service
from app.domains.product_requests.schemas import (
    ProductRequestCreate,
    ProductRequestMessageCreate,
    ProductRequestStatusUpdate,
)
from app.domains.support.models import Ticket
from app.domains.users.models import User


async def _user(db, organization_id):
    user = User(
        organization_id=organization_id, email=f"u-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _open(db, organization_id, user, name="Caffè in capsule compatibili"):
    return await service.create_request(
        db, organization_id=organization_id, actor_user_id=user.id, actor_role="CUSTOMER",
        payload=ProductRequestCreate(product_name=name, message="Le cerco da 100 pezzi", reference_url=" "),
    )


@pytest.mark.asyncio
async def test_full_conversation(db, organization_id):
    customer = await _user(db, organization_id)
    staff = await _user(db, organization_id)
    request = await _open(db, organization_id, customer)
    assert request.status == "OPEN"
    assert request.reference_url is None  # uno spazio vuoto non e' un link

    await service.add_message(
        db, organization_id=organization_id, request_id=request.id, actor_user_id=staff.id,
        actor_role=service.STAFF_ROLE, requester_is_staff=True,
        payload=ProductRequestMessageCreate(body="Trovate, 18 euro la confezione"),
    )
    await service.add_message(
        db, organization_id=organization_id, request_id=request.id, actor_user_id=customer.id,
        actor_role="CUSTOMER", requester_is_staff=False, payload=ProductRequestMessageCreate(body="Perfetto!"),
    )

    detail = await service.get_detail(
        db, organization_id=organization_id, request_id=request.id,
        requester_user_id=customer.id, requester_is_staff=False,
    )
    assert detail["status"] == "IN_PROGRESS"  # la prima risposta dello staff
    assert [m["author_role"] for m in detail["messages"]] == ["CUSTOMER", "ADMIN", "CUSTOMER"]
    assert detail["last_author_role"] == "CUSTOMER"

    reply_note = (
        await db.execute(
            select(Notification).where(
                Notification.recipient_user_id == customer.id, Notification.type == "PRODUCT_REQUEST_REPLY"
            )
        )
    ).scalars().all()
    assert len(reply_note) == 1

    # Tabelle proprie: nessun ticket di assistenza e' stato creato.
    assert (await db.execute(select(func.count()).select_from(Ticket))).scalar_one() == 0


@pytest.mark.asyncio
async def test_customer_sees_only_own_requests(db, organization_id):
    alice = await _user(db, organization_id)
    bob = await _user(db, organization_id)
    request = await _open(db, organization_id, alice)

    assert await service.get_detail(
        db, organization_id=organization_id, request_id=request.id, requester_user_id=bob.id, requester_is_staff=False,
    ) is None
    assert await service.add_message(
        db, organization_id=organization_id, request_id=request.id, actor_user_id=bob.id, actor_role="CUSTOMER",
        requester_is_staff=False, payload=ProductRequestMessageCreate(body="intrusione"),
    ) is None
    assert await service.list_mine(db, organization_id=organization_id, user_id=bob.id) == []
    assert len(await service.list_mine(db, organization_id=organization_id, user_id=alice.id)) == 1


@pytest.mark.asyncio
async def test_closed_request_rejects_replies_and_only_concluded_ones_can_be_deleted(db, organization_id):
    customer = await _user(db, organization_id)
    staff = await _user(db, organization_id)
    request = await _open(db, organization_id, customer)

    with pytest.raises(service.ProductRequestDeletionError):
        await service.delete_request(db, organization_id=organization_id, request_id=request.id, actor_user_id=staff.id)

    await service.update_status(
        db, organization_id=organization_id, request_id=request.id, actor_user_id=staff.id,
        payload=ProductRequestStatusUpdate(status="CLOSED"),
    )
    with pytest.raises(service.ProductRequestClosedError):
        await service.add_message(
            db, organization_id=organization_id, request_id=request.id, actor_user_id=customer.id,
            actor_role="CUSTOMER", requester_is_staff=False, payload=ProductRequestMessageCreate(body="ancora?"),
        )
    assert await service.delete_request(
        db, organization_id=organization_id, request_id=request.id, actor_user_id=staff.id
    ) is True
