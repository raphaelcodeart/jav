"""Catalog product purchases with an optional wallet-credit discount.
Deliberately not a Contract -- see orders/models.py. Covers the credit-cap enforcement, the
straight-to-PAID shortcut when credit covers 100%, cancellation refunding
the exact debit via a REVERSAL, and INTERNAL products being rejected."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.security import hash_otp_code, hash_password
from app.domains.auth import service as auth_service
from app.domains.auth.models import OtpCode
from app.domains.catalog import service as catalog_service
from app.domains.catalog.schemas import ProductCreate
from app.domains.orders import service as orders_service
from app.domains.organizations import service as organizations_service
from app.domains.organizations.schemas import OrganizationSettingsUpdate
from app.domains.rbac.models import Role, UserRole
from app.domains.users.models import User
from app.domains.wallets import service as wallet_service

VALID_OTP_CODE = "654321"


async def _seed_credit_spend_otp(db, user_id):
    """Same "seed the row directly, skip the email-sending request_otp()
    call" pattern as test_promoter_self_service.py::_apply_as_promoter --
    every test here that needs a valid code doesn't otherwise care about the
    email itself."""
    db.add(
        OtpCode(
            user_id=user_id,
            purpose=auth_service.WALLET_CREDIT_SPEND_OTP_PURPOSE,
            code_hash=hash_otp_code(VALID_OTP_CODE),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
    )
    await db.commit()


async def _configure_bank_transfer(db, organization_id):
    """Bank transfer is gated off by default (no IBAN configured) --
    tests exercising a residual paid by BANK_TRANSFER (the create_order
    default) need it explicitly configured first, same as a real deployment
    would via the admin settings panel."""
    await organizations_service.update_settings(
        db, organization_id=organization_id, payload=OrganizationSettingsUpdate(bank_iban="IT60X0542811101000000123456")
    )


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


async def _make_product_version(
    db, organization_id, actor_user_id, *, category="DROPSHIPPING", price_cents=5000, discount_pct=20,
    cashback_enabled=False,
):
    product = await catalog_service.create_product(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        payload=ProductCreate(
            code=f"ORD-{uuid.uuid4().hex[:6]}", customer_type="PRIVATE", category=category,
            name="Gadget", base_price_cents=price_cents, credit_discount_percentage=discount_pct,
            cashback_enabled=cashback_enabled,
        ),
    )
    _, versions = await catalog_service.get_product_with_versions(db, organization_id=organization_id, product_id=product.id)
    return versions[0]


@pytest.mark.asyncio
async def test_partial_credit_debits_wallet_and_leaves_residual_awaiting_payment(db, organization_id):
    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=20)

    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=2000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    quote = await orders_service.get_quote(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id
    )
    assert quote["max_creditable_cents"] == 1000  # 20% of 5000
    assert quote["customer_wallet_balance_cents"] == 2000

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=1000, actor_user_id=admin.id,
        require_otp_for_credit_spend=False,
    )
    assert order.status == "AWAITING_PAYMENT"
    assert order.amount_cents == 5000
    assert order.credit_applied_cents == 1000
    assert order.credit_debit_transaction_id is not None

    wallet_after = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert wallet_after.balance_cents == 1000  # 2000 - 1000

    confirmed = await orders_service.confirm_payment(
        db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
    )
    assert confirmed.status == "PAID"


@pytest.mark.asyncio
async def test_credit_covering_full_amount_skips_straight_to_paid(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=3000, discount_pct=100)

    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=3000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=3000, actor_user_id=admin.id,
        require_otp_for_credit_spend=False,
    )
    assert order.status == "PAID"  # no bank transfer needed
    assert order.paid_at is not None

    wallet_after = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert wallet_after.balance_cents == 0


@pytest.mark.asyncio
async def test_credit_over_cap_is_rejected(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=20)

    with pytest.raises(orders_service.InvalidCreditAmountError):
        await orders_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
            credit_applied_cents=1001, actor_user_id=admin.id,  # cap is 1000
            require_otp_for_credit_spend=False,
        )


@pytest.mark.asyncio
async def test_credit_exceeding_balance_raises_and_creates_no_order(db, organization_id):
    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=50)
    # customer has no wallet / zero balance -- cap (2500) exceeds it

    with pytest.raises(wallet_service.InsufficientBalanceError):
        await orders_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
            credit_applied_cents=2500, actor_user_id=admin.id,
            require_otp_for_credit_spend=False,
        )

    orders = await orders_service.list_orders(db, organization_id=organization_id)
    assert all(o.customer_user_id != customer.id for o in orders)


@pytest.mark.asyncio
async def test_cancel_refunds_the_exact_credit_debit(db, organization_id):
    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=10000, discount_pct=10)

    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=1000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=1000, actor_user_id=admin.id,
        require_otp_for_credit_spend=False,
    )
    mid_wallet = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert mid_wallet.balance_cents == 0

    cancelled = await orders_service.cancel_order(
        db, organization_id=organization_id, order_id=order.id, reason="Prodotto esaurito", actor_user_id=admin.id
    )
    assert cancelled.status == "CANCELLED"

    refunded_wallet = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert refunded_wallet.balance_cents == 1000  # fully refunded

    with pytest.raises(orders_service.InvalidOrderStateError):
        await orders_service.cancel_order(
            db, organization_id=organization_id, order_id=order.id, reason="again", actor_user_id=admin.id
        )
    with pytest.raises(orders_service.InvalidOrderStateError):
        await orders_service.confirm_payment(db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id)


@pytest.mark.asyncio
async def test_internal_category_product_is_not_orderable(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, category="INTERNAL", price_cents=3000, discount_pct=0)

    with pytest.raises(orders_service.ProductNotEligibleError):
        await orders_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
            credit_applied_cents=0, actor_user_id=admin.id,
            require_otp_for_credit_spend=False,
        )


@pytest.mark.asyncio
async def test_unconfigured_payment_method_is_rejected_and_creates_no_order(db, organization_id):
    """Bank transfer is off by default (an admin must configure an IBAN
    first) -- this is the server-side half of "the button isn't even
    clickable if it's not configured"."""
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=0)
    # deliberately NOT calling _configure_bank_transfer -- nothing is set up

    with pytest.raises(orders_service.PaymentMethodNotAvailableError):
        await orders_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
            credit_applied_cents=0, actor_user_id=admin.id, payment_method="BANK_TRANSFER",
        )

    orders = await orders_service.list_orders(db, organization_id=organization_id)
    assert all(o.customer_user_id != customer.id for o in orders)


@pytest.mark.asyncio
async def test_card_is_not_a_payment_method(db, organization_id):
    """Bank transfer is the only way to pay a residual: anything else is
    refused before an order exists, even with the bank transfer configured."""
    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=0)

    with pytest.raises(orders_service.InvalidPaymentMethodError):
        await orders_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
            credit_applied_cents=0, actor_user_id=admin.id, payment_method="CARD",
        )
    orders = await orders_service.list_orders(db, organization_id=organization_id)
    assert all(o.customer_user_id != customer.id for o in orders)


@pytest.mark.asyncio
async def test_full_credit_ignores_unconfigured_payment_method(db, organization_id):
    """residual == 0 means nothing is ever actually charged, so an
    unavailable (or even invalid) payment_method must not block the order --
    it's stored but never acted upon."""
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=3000, discount_pct=100)

    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=3000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=3000, actor_user_id=admin.id, payment_method="CARD",  # not a valid method, irrelevant here
        require_otp_for_credit_spend=False,
    )
    assert order.status == "PAID"


@pytest.mark.asyncio
async def test_create_order_notifies_staff_but_not_the_actor(db, organization_id):
    """New-order visibility for staff (task: "nuovo ordine -> notifica
    amministratore"), same STAFF_NOTIFY_ROLES convention as
    contracts/service.py::create_contract's CONTRACT_CREATED. The customer
    who placed it is excluded even though the order itself grants them no
    staff role (this only matters when an admin creates an order on a
    customer's behalf -- that admin shouldn't see their own action as a
    notification)."""
    from app.domains.notifications import service as notifications_service

    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    other_admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=0)

    await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=0, actor_user_id=admin.id,
        require_otp_for_credit_spend=False,
    )

    actor_notifications = await notifications_service.list_my_notifications(
        db, organization_id=organization_id, user_id=admin.id
    )
    assert not any(n.type == "ORDER_CREATED" for n in actor_notifications)

    other_notifications = await notifications_service.list_my_notifications(
        db, organization_id=organization_id, user_id=other_admin.id
    )
    assert any(n.type == "ORDER_CREATED" for n in other_notifications)


@pytest.mark.asyncio
async def test_confirm_payment_notifies_staff_and_sends_paid_email(db, organization_id):
    """Bank-transfer confirmation (task: "Rendi pagato") must notify staff
    and email the customer that payment is complete -- separate from the
    "ordine ricevuto" email sent at creation."""
    from unittest.mock import AsyncMock, patch

    from app.domains.notifications import service as notifications_service

    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    other_admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=0)

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=0, actor_user_id=customer.id,
        require_otp_for_credit_spend=False,
    )

    with patch.object(orders_service, "_send_order_paid_email", new_callable=AsyncMock) as mock_email:
        confirmed = await orders_service.confirm_payment(
            db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
        )

    assert confirmed.status == "PAID"
    mock_email.assert_awaited_once()
    assert mock_email.call_args.kwargs["order"].id == order.id

    other_notifications = await notifications_service.list_my_notifications(
        db, organization_id=organization_id, user_id=other_admin.id
    )
    assert any(n.type == "ORDER_PAID" for n in other_notifications)


@pytest.mark.asyncio
async def test_product_order_payment_never_touches_the_wallet(db, organization_id):
    """A normal product purchase, paid in full with no credit applied and no
    cashback requested, must leave the customer's wallet completely
    untouched all the way through payment confirmation."""
    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=10000, discount_pct=0)

    wallet_before = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    assert wallet_before.balance_cents == 0

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=0, actor_user_id=customer.id,
    )
    paid = await orders_service.confirm_payment(
        db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
    )
    assert paid.status == "PAID"

    wallet_after = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert wallet_after.balance_cents == 0  # a 100 EUR product paid in full credits the wallet exactly 0 EUR


@pytest.mark.asyncio
async def test_upload_payment_proof_stores_it_and_notifies_staff(db, organization_id):
    from app.domains.notifications import service as notifications_service

    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    other_admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=0)

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=0, actor_user_id=customer.id, payment_method="BANK_TRANSFER",
    )
    assert order.payment_proof_uploaded_at is None

    updated = await orders_service.upload_payment_proof(
        db, organization_id=organization_id, order=order, file_bytes=b"%PDF-1.4\nfake receipt",
        content_type="application/pdf", original_filename="bonifico.pdf", actor_user_id=customer.id,
    )
    assert updated.payment_proof_uploaded_at is not None
    assert updated.payment_proof_original_filename == "bonifico.pdf"

    url = orders_service.presigned_payment_proof_url(updated)
    assert url

    other_notifications = await notifications_service.list_my_notifications(
        db, organization_id=organization_id, user_id=other_admin.id
    )
    assert any(n.type == "ORDER_PAYMENT_PROOF_UPLOADED" for n in other_notifications)


# ---- Self-checkout OTP gate on spending existing wallet JavCash ----

@pytest.mark.asyncio
async def test_self_checkout_credit_spend_without_otp_is_rejected(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=20)
    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=2000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    with pytest.raises(orders_service.InvalidOtpError):
        await orders_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
            credit_applied_cents=1000, actor_user_id=customer.id,  # require_otp_for_credit_spend defaults True
        )


@pytest.mark.asyncio
async def test_self_checkout_credit_spend_with_wrong_otp_is_rejected(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=20)
    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=2000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )
    await _seed_credit_spend_otp(db, customer.id)

    with pytest.raises(orders_service.InvalidOtpError):
        await orders_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
            credit_applied_cents=1000, actor_user_id=customer.id, otp_code="000000",
        )


@pytest.mark.asyncio
async def test_self_checkout_credit_spend_with_valid_otp_succeeds(db, organization_id):
    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=20)
    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=2000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )
    await _seed_credit_spend_otp(db, customer.id)

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=1000, actor_user_id=customer.id, otp_code=VALID_OTP_CODE,
    )
    assert order.credit_applied_cents == 1000

    # verify_otp() consumes it -- a second order can't reuse the same code.
    with pytest.raises(orders_service.InvalidOtpError):
        await orders_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
            credit_applied_cents=500, actor_user_id=customer.id, otp_code=VALID_OTP_CODE,
        )


@pytest.mark.asyncio
async def test_admin_created_order_never_needs_an_otp(db, organization_id):
    """POST /orders (staff, wallet.manage-gated) passes
    require_otp_for_credit_spend=False -- an admin applying a customer's
    credit on their behalf can't complete an OTP that would be emailed to
    the CUSTOMER's inbox, and doesn't need to: this is already a
    permissioned, audited action."""
    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=20)
    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=2000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=1000, actor_user_id=admin.id, require_otp_for_credit_spend=False,
    )
    assert order.credit_applied_cents == 1000


# ---- "Riscuoti subito cashback" ----

@pytest.mark.asyncio
async def test_cashback_requires_the_product_to_allow_it(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=0, cashback_enabled=False)

    with pytest.raises(orders_service.CashbackNotAvailableError):
        await orders_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
            credit_applied_cents=0, actor_user_id=customer.id, cashback_requested=True,
            require_otp_for_credit_spend=False,
        )


@pytest.mark.asyncio
async def test_cashback_requires_a_real_residual_to_apply_to(db, organization_id):
    """100% credit-discount covering the whole price leaves nothing new to
    pay -- cashback (which pays back what was genuinely paid new) can't
    apply to an order like that."""
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(
        db, organization_id, admin.id, price_cents=3000, discount_pct=100, cashback_enabled=True
    )
    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=3000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )
    await _seed_credit_spend_otp(db, customer.id)

    with pytest.raises(orders_service.CashbackNotAvailableError):
        await orders_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
            credit_applied_cents=3000, actor_user_id=customer.id, cashback_requested=True, otp_code=VALID_OTP_CODE,
        )


@pytest.mark.asyncio
async def test_cashback_surcharge_and_credit_on_bank_transfer_confirm(db, organization_id):
    """The full, real-money happy path: a 100.00 EUR product, no credit
    discount used, cashback requested -- must charge 105.00 EUR (5% surcharge
    on the full residual) and, once an admin confirms the bank transfer,
    credit exactly 105.00 EUR back as two JavCash rows (100.00 base + 5.00
    bonus), never more than what was actually paid."""
    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(
        db, organization_id, admin.id, price_cents=10000, discount_pct=0, cashback_enabled=True
    )

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=0, actor_user_id=customer.id, cashback_requested=True,
        require_otp_for_credit_spend=False,
    )
    assert order.cashback_requested is True
    assert order.cashback_surcharge_cents == 500  # 5% of 10000
    row = await orders_service.to_read_dict(db, order)
    assert row["residual_amount_cents"] == 10500

    confirmed = await orders_service.confirm_payment(
        db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
    )
    assert confirmed.cashback_credited_at is not None

    wallet_after = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert wallet_after.balance_cents == 10500  # 100% + 5%, exactly what was paid


@pytest.mark.asyncio
async def test_cashback_base_is_computed_after_credit_discount_not_before(db, organization_id):
    """Spend 20.00 EUR of existing JavCash on a 100.00 EUR product (80.00
    EUR residual), then request cashback on top: the 5% surcharge and the
    cashback base must both be computed off the 80.00 EUR residual, never
    the original 100.00 EUR price -- crediting cashback off a higher base
    than what was genuinely paid NEW would let a customer manufacture credit
    out of credit already spent."""
    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(
        db, organization_id, admin.id, price_cents=10000, discount_pct=50, cashback_enabled=True
    )
    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=2000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )
    await _seed_credit_spend_otp(db, customer.id)

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=2000, actor_user_id=customer.id, cashback_requested=True, otp_code=VALID_OTP_CODE,
    )
    assert order.cashback_surcharge_cents == 400  # 5% of the 8000 residual, not of 10000
    row = await orders_service.to_read_dict(db, order)
    assert row["residual_amount_cents"] == 8400  # 8000 + 400

    await orders_service.confirm_payment(db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id)

    wallet_after = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    # Started with 2000, spent all 2000 (balance 0), then received back
    # 8000 + 400 = 8400 in cashback. Net: 2000 - 2000 + 8400 = 8400.
    assert wallet_after.balance_cents == 8400


# ---- Product-level cashback_enabled toggle (catalog domain) ----

@pytest.mark.asyncio
async def test_cashback_enabled_is_forced_false_for_an_internal_product(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    product = await catalog_service.create_product(
        db, organization_id=organization_id, actor_user_id=admin.id,
        payload=ProductCreate(
            code=f"INT-{uuid.uuid4().hex[:6]}", customer_type="PRIVATE", category="INTERNAL",
            name="Abbonamento mensile", base_price_cents=5000, cashback_enabled=True,
        ),
    )
    _, versions = await catalog_service.get_product_with_versions(db, organization_id=organization_id, product_id=product.id)
    assert versions[0].cashback_enabled is False


@pytest.mark.asyncio
async def test_switching_category_to_internal_clears_cashback_enabled(db, organization_id):
    from app.domains.catalog.schemas import ProductUpdate

    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    version = await _make_product_version(db, organization_id, admin.id, category="PARTNER", cashback_enabled=True)
    assert version.cashback_enabled is True

    await catalog_service.update_product(
        db, organization_id=organization_id, product_id=version.product_id,
        payload=ProductUpdate(category="INTERNAL"), actor_user_id=admin.id,
    )
    _, versions = await catalog_service.get_product_with_versions(
        db, organization_id=organization_id, product_id=version.product_id
    )
    assert versions[0].cashback_enabled is False


@pytest.mark.asyncio
async def test_the_audience_of_a_package_can_be_changed_after_creation(db, organization_id):
    """«A chi è rivolto» cambiato dal pannello deve arrivare al servizio:
    altrimenti un privato vedrebbe anche i pacchetti P.iva."""
    from app.domains.catalog.schemas import ProductUpdate

    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    product = await catalog_service.create_product(
        db, organization_id=organization_id, actor_user_id=admin.id,
        payload=ProductCreate(
            code=f"INT-{uuid.uuid4().hex[:6]}", customer_type="BOTH", category="INTERNAL",
            name="Abbonamento P.iva", base_price_cents=30000,
        ),
    )
    updated = await catalog_service.update_product(
        db, organization_id=organization_id, product_id=product.id, actor_user_id=admin.id,
        payload=ProductUpdate(customer_type="BUSINESS"),
    )
    assert updated.customer_type == "BUSINESS"
    # Un aggiornamento che non lo nomina non lo tocca.
    updated = await catalog_service.update_product(
        db, organization_id=organization_id, product_id=product.id, actor_user_id=admin.id,
        payload=ProductUpdate(status="ACTIVE"),
    )
    assert updated.customer_type == "BUSINESS"


@pytest.mark.asyncio
async def test_the_code_of_a_package_can_be_renamed_but_not_onto_another(db, organization_id):
    """«ANNUALE-COPY-COPY» dopo due duplicazioni si rinomina dal
    pannello; un codice già usato da un altro prodotto no."""
    from app.domains.catalog.schemas import ProductUpdate

    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    suffix = uuid.uuid4().hex[:6].upper()
    products = [
        await catalog_service.create_product(
            db, organization_id=organization_id, actor_user_id=admin.id,
            payload=ProductCreate(code=code, category="INTERNAL", name="Abbonamento", base_price_cents=100),
        )
        for code in (f"ANNUALE-{suffix}", f"ANNUALE-{suffix}-COPY-COPY")
    ]
    with pytest.raises(catalog_service.ProductCodeTakenError):
        await catalog_service.update_product(
            db, organization_id=organization_id, product_id=products[1].id, actor_user_id=admin.id,
            payload=ProductUpdate(code=f"annuale-{suffix}"),
        )
    updated = await catalog_service.update_product(
        db, organization_id=organization_id, product_id=products[1].id, actor_user_id=admin.id,
        payload=ProductUpdate(code=f"  ANNUALE-PRIVATI-{suffix} "),
    )
    assert updated.code == f"ANNUALE-PRIVATI-{suffix}"
