"""Internal EUR wallet: lazy per-user creation, admin top-up/cashback, and
peer-to-peer transfer by address. Covers the two concurrency-sensitive paths
(atomic compare-and-swap debit, idempotency-key replay) that make this
domain different from every other ledger in this codebase -- see
docs/business-rules.md#internal-wallet."""

import uuid

import pytest

from app.core.security import hash_password
from app.domains.rbac.models import Role, UserRole
from app.domains.users.models import User
from app.domains.wallets import service as wallet_service


async def _get_or_create_role(db, organization_id, *, role_code: str) -> Role:
    from sqlalchemy import select

    existing = (
        await db.execute(select(Role).where(Role.organization_id == organization_id, Role.code == role_code))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    role = Role(organization_id=organization_id, code=role_code, name=role_code.title())
    db.add(role)
    await db.flush()
    return role


async def _enable_transfer(db, wallet):
    """Peer-to-peer transfer is denied by default (Wallet.can_transfer)
    -- tests that exercise debit_and_transfer's OWN logic
    (insufficient balance, self-transfer, cross-org lookup, idempotency) opt
    the sender wallet in explicitly so they keep testing what they're named
    for, not the permission gate. See test_transfer_is_denied_by_default_
    and_can_be_enabled below for that gate itself."""
    wallet.can_transfer = True
    await db.commit()
    await db.refresh(wallet)
    return wallet


async def _make_user_with_role(db, organization_id, *, role_code: str = "CUSTOMER"):
    user = User(
        organization_id=organization_id, email=f"{role_code.lower()}-{uuid.uuid4().hex[:6]}@example.demo",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.flush()
    role = await _get_or_create_role(db, organization_id, role_code=role_code)
    db.add(UserRole(user_id=user.id, organization_id=organization_id, role_id=role.id))
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_get_or_create_wallet_is_lazy_and_idempotent(db, organization_id):
    user = await _make_user_with_role(db, organization_id)

    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=user.id)
    assert wallet.balance_cents == 0
    assert wallet.address.startswith("0x")
    assert len(wallet.address) == 42

    again = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=user.id)
    assert again.id == wallet.id


@pytest.mark.asyncio
async def test_admin_credit_increases_balance_and_notifies(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)

    txn = await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=5000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, note="Cashback ordine #123", idempotency_key=str(uuid.uuid4()),
    )
    assert txn.amount_cents == 5000
    assert txn.from_wallet_id is None
    assert txn.to_wallet_id == wallet.id

    refreshed = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert refreshed.balance_cents == 5000

    from app.domains.notifications import service as notifications_service

    notifications = await notifications_service.list_my_notifications(
        db, organization_id=organization_id, user_id=customer.id
    )
    assert any(n.type == "CASHBACK_RECEIVED" for n in notifications)


@pytest.mark.asyncio
async def test_credit_wallet_sends_email_for_a_plain_top_up(db, organization_id):
    """Admin "Ricarica" (no reference_order_id) must email the
    customer -- see wallets/service.py::credit_wallet's call to
    _send_wallet_credited_email."""
    from unittest.mock import AsyncMock, patch

    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)

    with patch.object(wallet_service, "_send_wallet_credited_email", new_callable=AsyncMock) as mock_email:
        await wallet_service.credit_wallet(
            db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=5000, type_="ADMIN_CREDIT",
            actor_user_id=admin.id, source="MANUAL_ADMIN", note="Ricarica", idempotency_key=str(uuid.uuid4()),
        )

    mock_email.assert_awaited_once()
    assert mock_email.call_args.kwargs["user_id"] == customer.id
    assert mock_email.call_args.kwargs["amount_cents"] == 5000


@pytest.mark.asyncio
async def test_transfer_happy_path_moves_balance_between_wallets(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    sender_user = await _make_user_with_role(db, organization_id)
    receiver_user = await _make_user_with_role(db, organization_id)
    sender_wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=sender_user.id)
    receiver_wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=receiver_user.id)
    await _enable_transfer(db, sender_wallet)

    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=sender_wallet.id, amount_cents=10000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    txn = await wallet_service.debit_and_transfer(
        db, organization_id=organization_id, from_wallet_id=sender_wallet.id, to_address=receiver_wallet.address,
        amount_cents=3000, actor_user_id=sender_user.id, idempotency_key=str(uuid.uuid4()),
    )
    assert txn.from_wallet_id == sender_wallet.id
    assert txn.to_wallet_id == receiver_wallet.id

    sender_after = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=sender_user.id)
    receiver_after = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=receiver_user.id)
    assert sender_after.balance_cents == 7000
    assert receiver_after.balance_cents == 3000


@pytest.mark.asyncio
async def test_transfer_with_insufficient_balance_leaves_both_wallets_untouched(db, organization_id):
    sender_user = await _make_user_with_role(db, organization_id)
    receiver_user = await _make_user_with_role(db, organization_id)
    sender_wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=sender_user.id)
    receiver_wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=receiver_user.id)
    await _enable_transfer(db, sender_wallet)

    with pytest.raises(wallet_service.InsufficientBalanceError):
        await wallet_service.debit_and_transfer(
            db, organization_id=organization_id, from_wallet_id=sender_wallet.id, to_address=receiver_wallet.address,
            amount_cents=100, actor_user_id=sender_user.id, idempotency_key=str(uuid.uuid4()),
        )

    sender_after = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=sender_user.id)
    receiver_after = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=receiver_user.id)
    assert sender_after.balance_cents == 0
    assert receiver_after.balance_cents == 0


@pytest.mark.asyncio
async def test_self_transfer_is_rejected(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    user = await _make_user_with_role(db, organization_id)
    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=user.id)
    await _enable_transfer(db, wallet)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=1000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    with pytest.raises(wallet_service.SelfTransferError):
        await wallet_service.debit_and_transfer(
            db, organization_id=organization_id, from_wallet_id=wallet.id, to_address=wallet.address,
            amount_cents=100, actor_user_id=user.id, idempotency_key=str(uuid.uuid4()),
        )


@pytest.mark.asyncio
async def test_transfer_is_denied_by_default_and_can_be_enabled(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    sender_user = await _make_user_with_role(db, organization_id)
    receiver_user = await _make_user_with_role(db, organization_id)
    sender_wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=sender_user.id)
    receiver_wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=receiver_user.id)
    assert sender_wallet.can_transfer is False

    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=sender_wallet.id, amount_cents=10000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )
    with pytest.raises(wallet_service.TransferNotAllowedError):
        await wallet_service.debit_and_transfer(
            db, organization_id=organization_id, from_wallet_id=sender_wallet.id, to_address=receiver_wallet.address,
            amount_cents=100, actor_user_id=sender_user.id, idempotency_key=str(uuid.uuid4()),
        )
    unchanged = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=sender_user.id)
    assert unchanged.balance_cents == 10000  # untouched -- the CAS update never ran

    enabled = await wallet_service.set_transfer_permission(
        db, organization_id=organization_id, user_id=sender_user.id, can_transfer=True
    )
    assert enabled.can_transfer is True
    txn = await wallet_service.debit_and_transfer(
        db, organization_id=organization_id, from_wallet_id=sender_wallet.id, to_address=receiver_wallet.address,
        amount_cents=100, actor_user_id=sender_user.id, idempotency_key=str(uuid.uuid4()),
    )
    assert txn.amount_cents == 100


@pytest.mark.asyncio
async def test_transfer_to_a_wallet_in_another_organization_is_not_found(db, organization_id):
    from app.domains.organizations.models import Organization

    other_org = Organization(name=f"Other Org {uuid.uuid4()}", status="ACTIVE")
    db.add(other_org)
    await db.commit()
    await db.refresh(other_org)

    sender_user = await _make_user_with_role(db, organization_id)
    other_org_user = await _make_user_with_role(db, other_org.id)
    sender_wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=sender_user.id)
    other_org_wallet = await wallet_service.get_or_create_wallet(db, organization_id=other_org.id, user_id=other_org_user.id)
    await _enable_transfer(db, sender_wallet)

    with pytest.raises(wallet_service.WalletNotFoundError):
        await wallet_service.debit_and_transfer(
            db, organization_id=organization_id, from_wallet_id=sender_wallet.id, to_address=other_org_wallet.address,
            amount_cents=100, actor_user_id=sender_user.id, idempotency_key=str(uuid.uuid4()),
        )


@pytest.mark.asyncio
async def test_idempotency_key_replay_does_not_double_credit(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    user = await _make_user_with_role(db, organization_id)
    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=user.id)
    key = str(uuid.uuid4())

    first = await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=2000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=key,
    )
    second = await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=2000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=key,
    )
    assert first.id == second.id

    refreshed = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=user.id)
    assert refreshed.balance_cents == 2000  # not 4000


@pytest.mark.asyncio
async def test_reverse_admin_credit_debits_back_and_leaves_no_destination(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    user = await _make_user_with_role(db, organization_id)
    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=user.id)
    credit = await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=1500, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    reversal = await wallet_service.reverse_transaction(
        db, organization_id=organization_id, transaction_id=credit.id, actor_user_id=admin.id,
        reason="Errore di importo", idempotency_key=str(uuid.uuid4()),
    )
    assert reversal.type == "REVERSAL"
    assert reversal.from_wallet_id == wallet.id
    assert reversal.to_wallet_id is None
    assert reversal.reverses_transaction_id == credit.id

    refreshed = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=user.id)
    assert refreshed.balance_cents == 0


@pytest.mark.asyncio
async def test_reversing_a_reversal_is_rejected(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    user = await _make_user_with_role(db, organization_id)
    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=user.id)
    credit = await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=1500, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )
    reversal = await wallet_service.reverse_transaction(
        db, organization_id=organization_id, transaction_id=credit.id, actor_user_id=admin.id,
        reason="Errore", idempotency_key=str(uuid.uuid4()),
    )

    with pytest.raises(wallet_service.WalletError):
        await wallet_service.reverse_transaction(
            db, organization_id=organization_id, transaction_id=reversal.id, actor_user_id=admin.id,
            reason="Non dovrebbe funzionare", idempotency_key=str(uuid.uuid4()),
        )


@pytest.mark.asyncio
async def test_crossed_transfers_do_not_deadlock():
    """A->B and B->A at the same instant, on two real connections (the
    savepoint `db` fixture cannot race). Each transfer touches both rows; if
    each locked them in its own from/to order, A would hold its row waiting
    for B's while B holds B's waiting for A's, and Postgres would abort one
    with a deadlock. `_lock_wallets` takes both rows in id order first, so
    the second transfer simply waits for the first."""
    import asyncio

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.domains.organizations.models import Organization
    from app.domains.wallets.models import Wallet
    from tests.conftest import TEST_DATABASE_URL

    engine = create_async_engine(TEST_DATABASE_URL)
    setup = AsyncSession(bind=engine, expire_on_commit=False)
    try:
        org = Organization(name=f"Wallet Race {uuid.uuid4()}", status="ACTIVE")
        setup.add(org)
        await setup.commit()
        wallets = []
        for _ in range(2):
            user = await _make_user_with_role(setup, org.id)
            wallet = await wallet_service.get_or_create_wallet(setup, organization_id=org.id, user_id=user.id)
            wallet.can_transfer = True
            wallet.balance_cents = 100_000
            wallets.append(wallet)
        await setup.commit()
        org_id = org.id
        (a_id, a_addr, a_user), (b_id, b_addr, b_user) = [(w.id, w.address, w.user_id) for w in wallets]
    finally:
        await setup.close()

    rounds = 15
    for _ in range(rounds):
        session_a = AsyncSession(bind=engine, expire_on_commit=False)
        session_b = AsyncSession(bind=engine, expire_on_commit=False)
        try:
            results = await asyncio.gather(
                wallet_service.debit_and_transfer(
                    session_a, organization_id=org_id, from_wallet_id=a_id, to_address=b_addr,
                    amount_cents=100, actor_user_id=a_user, idempotency_key=str(uuid.uuid4()),
                ),
                wallet_service.debit_and_transfer(
                    session_b, organization_id=org_id, from_wallet_id=b_id, to_address=a_addr,
                    amount_cents=100, actor_user_id=b_user, idempotency_key=str(uuid.uuid4()),
                ),
                return_exceptions=True,
            )
        finally:
            await session_a.close()
            await session_b.close()
        for result in results:
            assert not isinstance(result, Exception), f"debit_and_transfer raised: {result!r}"

    verify = AsyncSession(bind=engine, expire_on_commit=False)
    try:
        balances = (await verify.execute(select(Wallet.balance_cents).where(Wallet.id.in_([a_id, b_id])))).scalars().all()
    finally:
        await verify.close()
        await engine.dispose()
    assert sorted(balances) == [100_000, 100_000]
