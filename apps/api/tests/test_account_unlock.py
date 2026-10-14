"""Sblocco dell'account da parte del superadmin.

Un cliente fermo davanti ai controlli d'ingresso -- email da confermare,
privacy da accettare, profilo da completare -- può essere sbloccato dal
superadmin. Email e privacy si segnano come fatte; codice fiscale e
indirizzo no: vanno scritti, e il sistema propone quelli che conosce già.
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.domains.audit.models import AuditLog
from app.domains.contracts.models import ContractRequest
from app.domains.customers.models import Customer
from app.domains.users import service as users_service
from app.domains.users.models import User
from app.domains.users.schemas import ProfileUpdate


async def _blocked_customer(db, organization_id):
    user = User(
        organization_id=organization_id, email=f"bloccato-{uuid.uuid4().hex[:6]}@example.demo",
        password_hash=hash_password("x"),
    )
    db.add(user)
    await db.flush()
    customer = Customer(
        organization_id=organization_id, user_id=user.id, kind="PRIVATE", email=user.email,
        fiscal_code="rssmra80a01h501u",
    )
    db.add(customer)
    await db.flush()
    db.add(ContractRequest(
        organization_id=organization_id, customer_id=customer.id,
        street="Via Roma 1", city="Milano", province="MI", postal_code="20100",
    ))
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_status_says_what_blocks_and_suggests_what_we_already_know(db, organization_id):
    user = await _blocked_customer(db, organization_id)
    status = await users_service.account_status(db, organization_id=organization_id, user_id=user.id)
    assert (status["email_verified"], status["privacy_accepted"], status["profile_complete"]) == (False, False, False)
    assert "codice fiscale" in status["missing_profile_fields"]
    assert status["suggested_profile"]["fiscal_code"] == "RSSMRA80A01H501U"
    assert status["suggested_profile"]["residence_street"] == "Via Roma 1"
    assert status["suggested_profile"]["residence_postal_code"] == "20100"


@pytest.mark.asyncio
async def test_unlock_needs_the_profile_and_then_opens_everything(db, organization_id):
    user = await _blocked_customer(db, organization_id)
    admin = User(organization_id=organization_id, email=f"sa-{uuid.uuid4().hex[:6]}@example.demo", password_hash="x")
    db.add(admin)
    await db.commit()

    with pytest.raises(users_service.UserLifecycleError, match="codice fiscale"):
        await users_service.unlock_account(
            db, organization_id=organization_id, user_id=user.id, actor_user_id=admin.id, profile=None,
        )
    unlocked = await users_service.unlock_account(
        db, organization_id=organization_id, user_id=user.id, actor_user_id=admin.id,
        profile=ProfileUpdate(
            fiscal_code="RSSMRA80A01H501U", residence_street="Via Roma 1", residence_city="Milano",
            residence_province="mi", residence_postal_code="20100",
        ),
    )
    assert unlocked.email_verified_at is not None and unlocked.privacy_accepted_at is not None
    assert users_service.is_profile_complete(unlocked) and unlocked.residence_province == "MI"

    audit = (await db.execute(select(AuditLog).where(
        AuditLog.entity_id == str(user.id), AuditLog.action == "user.account_unlocked",
    ))).scalar_one()
    assert audit.actor_user_id == admin.id
    assert audit.new_value == {"profile": True, "email_verified": True, "privacy_accepted": True}

    # Già sbloccato: un secondo giro non cambia niente e non chiede il profilo.
    again = await users_service.unlock_account(
        db, organization_id=organization_id, user_id=user.id, actor_user_id=admin.id, profile=None,
    )
    assert again.email_verified_at == unlocked.email_verified_at
