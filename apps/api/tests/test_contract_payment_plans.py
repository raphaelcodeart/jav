"""Pagamento del contratto: soluzione unica, 3 rate, 12 rate, con bonifico.

Contracts only -- the Shop's own checkout is a separate flow and is not
touched by any of this.

Two things these pin down. The arithmetic, because an instalment plan that is
a few euro off is worse than no instalment plan; and the confirmation,
because only an administrator confirming the transfer marks anything paid,
and confirming the same thing twice must pay it once.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.domains.catalog.models import Product, ProductVersion
from app.domains.contracts import payment_plans
from app.domains.contracts import service as contract_service
from app.domains.contracts.models import Contract
from app.domains.customers.models import Address, Customer
from app.domains.network import service as network_service
from app.domains.users.models import User

NOW = datetime(2026, 1, 1, tzinfo=UTC)


# --- L'aritmetica delle rate -------------------------------------------------


def test_a_price_that_divides_evenly_has_no_rounding_at_all():
    """The case that matters most: 249,00 is the contract the business keeps
    describing, and it divides exactly by both 3 and 12."""
    for key, expected_instalment in (
        (payment_plans.PLAN_FULL, 249_00),
        (payment_plans.PLAN_INSTALMENTS_3, 83_00),
        (payment_plans.PLAN_MONTHLY_12, 20_75),
    ):
        plan = payment_plans.plan_by_key(key)
        b = payment_plans.breakdown_for(plan, 249_00)
        assert b.instalment_cents == expected_instalment
        assert b.total_cents == 249_00
        assert b.rounding_difference_cents == 0


def test_a_price_that_does_not_divide_reports_the_difference_instead_of_hiding_it():
    plan = payment_plans.plan_by_key(payment_plans.PLAN_MONTHLY_12)
    b = payment_plans.breakdown_for(plan, 100_00)
    assert b.instalment_cents == 8_33
    assert b.total_cents == 99_96
    assert b.contract_total_cents == 100_00
    # Never silently absorbed: the customer is shown this figure.
    assert b.rounding_difference_cents == -4


def test_the_rounding_difference_can_never_be_large():
    """Whatever the price, splitting it must never move the total by more
    than a few cents -- that is what makes showing the figure honest rather
    than alarming."""
    for total in range(100, 100_000, 137):
        for plan in payment_plans.PAYMENT_PLANS:
            b = payment_plans.breakdown_for(plan, total)
            assert abs(b.rounding_difference_cents) <= plan.instalments // 2


def test_a_single_payment_is_never_discounted():
    """Paying by bank transfer carries no discount (business decision): one
    go is the contract's own total."""
    full = payment_plans.plan_by_key(payment_plans.PLAN_FULL)
    b = payment_plans.breakdown_for(full, 180_00)
    assert (b.total_cents, b.instalment_cents) == (180_00, 180_00)
    assert payment_plans.contract_breakdown(full, Contract(gross_amount_cents=180_00)).total_cents == 180_00


def test_an_amount_too_small_to_split_drops_that_option():
    """"12 rate da 0,00" on a very small contract would be nonsense."""
    from app.domains.contracts import requests as requests_service

    options = {o.plan.key: o for o in requests_service.plan_options([Contract(gross_amount_cents=5)])}
    assert options[payment_plans.PLAN_FULL].available
    assert not options[payment_plans.PLAN_MONTHLY_12].available


# --- La conferma del bonifico ---------------------------------------------------



async def _make_payable_contract(db, organization_id, *, gross_cents: int = 249_00) -> Contract:
    user = User(
        organization_id=organization_id, email=f"c-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.flush()
    customer = Customer(
        organization_id=organization_id, kind="PRIVATE", user_id=user.id,
        email=f"c-{uuid.uuid4().hex[:8]}@example.com",
    )
    db.add(customer)
    await db.flush()
    address = Address(
        organization_id=organization_id, customer_id=customer.id, kind="SUPPLY",
        street="Via Test 1", city="Roma", province="RM", postal_code="00100",
    )
    db.add(address)
    await db.flush()
    product = Product(
        organization_id=organization_id, code=f"P-{uuid.uuid4().hex[:6]}",
        customer_type="BOTH", category="INTERNAL",
    )
    db.add(product)
    await db.flush()
    version = ProductVersion(
        product_id=product.id, version_label="1.0", name="Abbonamento annuale",
        base_price_cents=gross_cents, valid_from=NOW,
    )
    db.add(version)
    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Prod", last_name="Uttore",
        promoter_code=f"PR-{uuid.uuid4().hex[:8]}", parent_agent_id=None,
    )
    await db.commit()

    contract = await contract_service.create_contract(
        db, organization_id=organization_id, customer_id=customer.id,
        product_version_id=version.id,
        producer_agent_id=agent.id, actor_user_id=user.id, correlation_id=str(uuid.uuid4()),
    )
    for step in ["SUBMITTED", "UNDER_REVIEW", "APPROVED"]:
        contract = await contract_service.transition_contract(
            db, organization_id=organization_id, contract=contract, to_status=step,
            actor_user_id=user.id, reason="test", notes=None, correlation_id=str(uuid.uuid4()),
        )
    # APPROVED auto-cascades to PAYMENT_PENDING -- the point a customer can pay.
    assert contract.status == "PAYMENT_PENDING"
    # An approved contract activates on payment only once an
    # administrator has accepted the commission preview.
    from app.domains.commissions.services.preview import build_commission_preview

    preview = await build_commission_preview(db, organization_id=organization_id, contract=contract)
    await contract_service.accept_commission_plan(
        db, organization_id=organization_id, contract=contract, checksum=preview["checksum"],
        actor_user_id=user.id,
    )
    return contract


async def _admin(db, organization_id) -> uuid.UUID:
    user = User(
        organization_id=organization_id, email=f"admin-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.commit()
    return user.id


async def _announce(db, contract, plan_key: str) -> None:
    """What the customer's «Paga con bonifico» writes on each contract."""
    contract.payment_plan = plan_key
    contract.payment_method = "BANK_TRANSFER"
    await db.commit()


@pytest.mark.asyncio
async def test_a_confirmed_transfer_activates_the_contract(db, organization_id):
    contract = await _make_payable_contract(db, organization_id)
    admin = await _admin(db, organization_id)
    await _announce(db, contract, payment_plans.PLAN_FULL)

    contract = await contract_service.record_transfer_payment(
        db, organization_id=organization_id, contract=contract, confirmed_by_user_id=admin
    )

    # PAID auto-cascades through ACTIVATION_PENDING into ACTIVE -- the same
    # hop that triggers commissions for every other contract.
    assert contract.status == "ACTIVE"
    assert contract.paid_at is not None


@pytest.mark.asyncio
async def test_the_same_transfer_confirmed_twice_changes_nothing(db, organization_id):
    from app.domains.contracts.models import ContractInstalment

    contract = await _make_payable_contract(db, organization_id)
    admin = await _admin(db, organization_id)
    await _announce(db, contract, payment_plans.PLAN_FULL)
    for _ in range(2):
        contract = await contract_service.record_transfer_payment(
            db, organization_id=organization_id, contract=contract, confirmed_by_user_id=admin
        )
    rows = list((await db.execute(select(ContractInstalment).where(ContractInstalment.contract_id == contract.id))).scalars())
    assert [(r.number, r.status) for r in rows] == [(1, "PAID")]
    assert contract.status == "ACTIVE"


@pytest.mark.asyncio
async def test_choosing_to_pay_is_not_what_marks_a_contract_paid(db, organization_id):
    """The customer announcing a transfer is a promise. Only an
    administrator confirming it moves a contract to PAID."""
    contract = await _make_payable_contract(db, organization_id)
    await _announce(db, contract, payment_plans.PLAN_MONTHLY_12)
    await db.refresh(contract)
    assert contract.status == "PAYMENT_PENDING"
    assert contract.paid_at is None


@pytest.mark.asyncio
async def test_an_approved_contract_paid_in_instalments_keeps_its_plan(db, organization_id):
    """Regression: paying an already approved contract went
    through the PAID transition with paid_at still empty, which is how a
    transfer confirmed from the contract list looks -- the plan was
    rewritten to FULL and a 12-instalment plan got one row."""
    from app.domains.contracts.models import ContractInstalment

    contract = await _make_payable_contract(db, organization_id, gross_cents=180_00)
    admin = await _admin(db, organization_id)
    await _announce(db, contract, payment_plans.PLAN_MONTHLY_12)
    contract = await contract_service.record_transfer_payment(
        db, organization_id=organization_id, contract=contract, confirmed_by_user_id=admin
    )
    assert contract.payment_plan == payment_plans.PLAN_MONTHLY_12
    assert contract.payment_method == "BANK_TRANSFER"
    rows = list((await db.execute(select(ContractInstalment).where(ContractInstalment.contract_id == contract.id))).scalars())
    assert len(rows) == 12 and rows[0].amount_cents == 15_00 and rows[0].status == "PAID"
    assert all(r.status == "SCHEDULED" for r in rows[1:]), "le rate successive le conferma l'amministratore"


@pytest.mark.asyncio
async def test_staff_marking_paid_keeps_the_plan_the_customer_announced(db, organization_id):
    """«Pagato» from the contract list honours the plan announced from the
    pratica; with none announced it is one payment of the whole amount."""
    contract = await _make_payable_contract(db, organization_id, gross_cents=180_00)
    admin = await _admin(db, organization_id)
    await _announce(db, contract, payment_plans.PLAN_INSTALMENTS_3)
    contract = await contract_service.transition_contract(
        db, organization_id=organization_id, contract=contract, to_status="PAID",
        actor_user_id=admin, reason="bonifico ricevuto", notes=None, correlation_id=str(uuid.uuid4()),
    )
    assert contract.payment_plan == payment_plans.PLAN_INSTALMENTS_3

    other = await _make_payable_contract(db, organization_id, gross_cents=180_00)
    other = await contract_service.transition_contract(
        db, organization_id=organization_id, contract=other, to_status="PAID",
        actor_user_id=admin, reason="bonifico ricevuto", notes=None, correlation_id=str(uuid.uuid4()),
    )
    assert (other.payment_plan, other.payment_method) == (payment_plans.PLAN_FULL, "BANK_TRANSFER")
