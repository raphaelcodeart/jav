"""PIN dei JavCash al posto del codice via email (Session 87).

Il cliente può scegliere un PIN di quattro cifre per confermare l'uso dei
JavCash al checkout. Qui si fissa ciò che lo rende sicuro quanto il codice
via email: serve la password per sceglierlo, niente PIN ovvi, blocco dopo
cinque errori, e il codice via email che resta sempre possibile.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.domains.auth import service as auth_service
from app.domains.auth.models import OtpCode
from app.domains.jav_market import service as market
from app.domains.wallets import service as wallet_service
from app.core.security import hash_password
from tests.test_jav_market import ADDRESS, OTP, _otp, _shop, _user, _variants

PASSWORD = "Password-di-prova-1"


async def _customer(db, organization_id):
    customer = await _user(db, organization_id)
    customer.password_hash = hash_password(PASSWORD)
    await db.commit()
    return customer


async def _otp_count(db, user_id) -> int:
    return (await db.execute(select(func.count()).select_from(OtpCode).where(OtpCode.user_id == user_id))).scalar_one()


@pytest.mark.asyncio
async def test_choosing_a_pin_needs_the_password_and_refuses_the_obvious_ones(db, organization_id):
    customer = await _customer(db, organization_id)
    with pytest.raises(auth_service.SpendPinError, match="password"):
        await auth_service.set_spend_pin(db, user=customer, pin="4827", password="sbagliata")
    for obvious in ("0000", "7777", "1234", "6789", "4321", "12a4", "123"):
        with pytest.raises(auth_service.SpendPinError):
            await auth_service.set_spend_pin(db, user=customer, pin=obvious, password=PASSWORD)
    assert auth_service.spend_pin_status(await auth_service.get_spend_pin(db, user_id=customer.id))["method"] == "EMAIL"

    pin = await auth_service.set_spend_pin(db, user=customer, pin="4827", password=PASSWORD)
    assert pin.pin_hash and pin.pin_hash != "4827"
    assert auth_service.spend_pin_status(pin) == {"enabled": True, "locked_until": None, "method": "PIN"}


@pytest.mark.asyncio
async def test_with_the_pin_on_no_email_leaves_unless_the_customer_asks(db, organization_id):
    customer = await _customer(db, organization_id)
    await auth_service.set_spend_pin(db, user=customer, pin="4827", password=PASSWORD)

    method = await auth_service.request_spend_code(db, user=customer, context_line="x")
    assert method == "PIN"
    assert await _otp_count(db, customer.id) == 0

    # «Non ricordo il PIN»: il codice via email resta sempre possibile.
    method = await auth_service.request_spend_code(db, user=customer, context_line="x", via_email=True)
    assert method == "EMAIL"
    assert await _otp_count(db, customer.id) == 1


@pytest.mark.asyncio
async def test_five_wrong_pins_lock_it_and_the_email_code_still_works(db, organization_id):
    customer = await _customer(db, organization_id)
    await auth_service.set_spend_pin(db, user=customer, pin="4827", password=PASSWORD)

    for _ in range(auth_service.SPEND_PIN_MAX_ATTEMPTS):
        assert not await auth_service.verify_spend_code(db, user_id=customer.id, code="1111")
    pin = await auth_service.get_spend_pin(db, user_id=customer.id)
    status = auth_service.spend_pin_status(pin)
    assert status["method"] == "EMAIL" and status["locked_until"] is not None
    # Bloccato: nemmeno il PIN giusto passa...
    assert not await auth_service.verify_spend_code(db, user_id=customer.id, code="4827")
    # ...e il checkout manda l'email da solo.
    assert await auth_service.request_spend_code(db, user=customer, context_line="x") == "EMAIL"

    await _otp(db, customer.id)
    assert await auth_service.verify_spend_code(db, user_id=customer.id, code=OTP)

    # Scaduto il blocco il PIN torna a valere, e un successo azzera gli errori.
    pin.locked_until = datetime.now(UTC) - timedelta(seconds=1)
    await db.commit()
    assert await auth_service.verify_spend_code(db, user_id=customer.id, code="4827")


@pytest.mark.asyncio
async def test_turning_it_off_deletes_the_pin(db, organization_id):
    customer = await _customer(db, organization_id)
    await auth_service.set_spend_pin(db, user=customer, pin="4827", password=PASSWORD)
    with pytest.raises(auth_service.SpendPinError):
        await auth_service.disable_spend_pin(db, user=customer, password="sbagliata")
    await auth_service.disable_spend_pin(db, user=customer, password=PASSWORD)

    pin = await auth_service.get_spend_pin(db, user_id=customer.id)
    assert pin.pin_hash is None and auth_service.spend_pin_status(pin)["method"] == "EMAIL"
    assert not await auth_service.verify_spend_code(db, user_id=customer.id, code="4827")


@pytest.mark.asyncio
async def test_a_marketplace_order_spends_javcash_with_the_pin(db, organization_id):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _customer(db, organization_id)
    _row, _p, pane, _m = await _shop(db, organization_id, admin, credit_percentage=50)
    variante = (await _variants(db, pane))[1]
    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=10000,
        type_="ADMIN_CREDIT", actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )
    await auth_service.set_spend_pin(db, user=customer, pin="4827", password=PASSWORD)
    quote = await market.get_quote(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variante.id, quantity=1
    )
    args = dict(
        organization_id=organization_id, customer_user_id=customer.id, variant_id=variante.id, quantity=1,
        address=ADDRESS, credit_applied_cents=quote["max_creditable_cents"], payment_method="BANK_TRANSFER",
        actor_user_id=customer.id, note=None,
    )
    with pytest.raises(market.InvalidOtpError):
        await market.create_order(db, otp_code="9999", **args)
    order = await market.create_order(db, otp_code="4827", **args)
    assert order.credit_applied_cents == quote["max_creditable_cents"]
