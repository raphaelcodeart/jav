"""Pagare un contratto prima dell'approvazione, e il cashback rata per rata.

Business decisions pinned here (Session 49):

- The catalog price of a Jav product is the MONTHLY canone: a
  "15 € /mese" product on a 12-month contract costs 180 € + IVA.
- A customer may pay straight after filling in the data, before any document
  is uploaded or approved. Paying does NOT activate anything: commissions
  still fire only once an administrator approves the documents.
- The JavCash credit is recognised when the money arrives. On an instalment
  plan it arrives one instalment at a time, and so does the credit.
"""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.security import hash_password
from app.domains.catalog import pricing
from app.domains.catalog.models import Product, ProductVersion
from app.domains.contracts import payment_plans
from app.domains.contracts import service as contract_service
from app.domains.contracts.models import Contract
from app.domains.contracts.schemas import ContractSelfServiceCreate
from app.domains.customers.models import Address, Customer, SupplyPoint
from app.domains.network import service as network_service
from app.domains.payments import service as payments_service
from app.domains.wallets.models import Wallet, WalletTransaction
from app.domains.users.models import User
from tests.test_contract_payment_plans import _configure_stripe, _signed

NOW = datetime(2026, 1, 1, tzinfo=UTC)


# --- Prezzo annuale e prezzo mensile (Session 84) -------------------------------


def _circolare(**overrides) -> ProductVersion:
    """«Energia circolare»: 149 € in unica soluzione, 18,30 € al mese a rate."""
    fields = dict(
        base_price_cents=149_00, monthly_price_cents=18_30, billing_period="MONTHLY",
        contract_duration_months=12, tax_configuration={"vat_percentage": 22.0},
    )
    fields.update(overrides)
    return ProductVersion(**fields)


def test_the_one_go_price_is_the_listed_price_and_the_rate_have_their_own():
    version = _circolare()
    assert pricing.contract_net_amount_cents(version, product_type="ENERGY_CONTRACT") == 149_00
    # Not 149 / 12: paying over time costs more.
    assert pricing.contract_instalments_net_amount_cents(version, product_type="ENERGY_CONTRACT") == 219_60


def test_a_private_customer_pays_no_vat_either_way():
    version = _circolare()
    one_go = pricing.compute_contract_price(version=version, customer_kind="PRIVATE", product_type="ENERGY_CONTRACT")
    rate = pricing.compute_contract_instalments_price(
        version=version, customer_kind="PRIVATE", product_type="ENERGY_CONTRACT"
    )
    assert one_go.gross_amount_cents == 149_00
    assert rate.gross_amount_cents == 219_60


def test_a_business_pays_vat_on_both_prices():
    """P.IVA: 249 € + IVA = 303,78 € in one go; 25 € + IVA = 30,50 € a month."""
    version = _circolare(base_price_cents=249_00, monthly_price_cents=25_00)
    one_go = pricing.compute_contract_price(version=version, customer_kind="COMPANY", product_type="ENERGY_CONTRACT")
    rate = pricing.compute_contract_instalments_price(
        version=version, customer_kind="COMPANY", product_type="ENERGY_CONTRACT"
    )
    assert one_go.gross_amount_cents == 303_78
    assert rate.gross_amount_cents == 366_00


def test_the_plans_split_the_rate_price_and_one_go_pays_the_listed_price():
    version = _circolare()
    contract = Contract(
        gross_amount_cents=149_00,
        instalments_gross_amount_cents=pricing.compute_contract_instalments_price(
            version=version, customer_kind="PRIVATE", product_type="ENERGY_CONTRACT"
        ).gross_amount_cents,
    )
    by_key = {b.plan.key: b for b in payment_plans.available_breakdowns(contract)}
    assert by_key[payment_plans.PLAN_FULL].total_cents == 149_00
    assert by_key[payment_plans.PLAN_MONTHLY_12].instalment_cents == 18_30
    assert by_key[payment_plans.PLAN_MONTHLY_12].total_cents == 219_60
    assert by_key[payment_plans.PLAN_INSTALMENTS_3].instalment_cents == 73_20


def test_the_one_go_discount_never_applies_on_top_of_a_rate_price():
    """With two prices the one-go advantage is already in them: 32% off the
    149 € would sell the package at 101 €. A package without a monthly price
    keeps the discount, as before Session 84."""
    with_rate = Contract(gross_amount_cents=149_00, instalments_gross_amount_cents=219_60)
    full = next(
        b for b in payment_plans.available_breakdowns(with_rate, full_payment_discount_percentage=32)
        if b.plan.key == payment_plans.PLAN_FULL
    )
    assert (full.total_cents, full.discount_cents) == (149_00, 0)

    legacy = Contract(gross_amount_cents=180_00, instalments_gross_amount_cents=None)
    full = next(
        b for b in payment_plans.available_breakdowns(legacy, full_payment_discount_percentage=32)
        if b.plan.key == payment_plans.PLAN_FULL
    )
    assert full.total_cents == 122_40


def test_without_a_monthly_price_the_rate_split_the_one_go_price():
    version = _circolare(monthly_price_cents=None)
    assert pricing.compute_contract_instalments_price(
        version=version, customer_kind="PRIVATE", product_type="ENERGY_CONTRACT"
    ) is None
    contract = Contract(gross_amount_cents=180_00, instalments_gross_amount_cents=None)
    by_key = {b.plan.key: b for b in payment_plans.available_breakdowns(contract)}
    assert by_key[payment_plans.PLAN_MONTHLY_12].instalment_cents == 15_00


def test_a_physical_or_digital_product_has_no_rate_price():
    """The admin form defaults every version to MONTHLY / 12 months: a t-shirt
    carries those values too, and must still cost exactly its price once."""
    tshirt = ProductVersion(
        base_price_cents=50_00, monthly_price_cents=5_00, billing_period="MONTHLY", contract_duration_months=12
    )
    for kind in ("PHYSICAL", "DIGITAL", None):
        assert pricing.contract_net_amount_cents(tshirt, product_type=kind) == 50_00
        assert pricing.contract_instalments_net_amount_cents(tshirt, product_type=kind) is None


def test_the_subscription_id_is_read_from_both_stripe_api_shapes():
    import stripe

    old_shape = stripe.StripeObject.construct_from({"id": "in_1", "subscription": "sub_old"}, "k")
    new_shape = stripe.StripeObject.construct_from(
        {"id": "in_2", "parent": {"subscription_details": {"subscription": "sub_new"}}}, "k"
    )
    one_off = stripe.StripeObject.construct_from({"id": "in_3", "parent": None}, "k")
    assert payments_service._invoice_subscription_id(old_shape) == "sub_old"
    assert payments_service._invoice_subscription_id(new_shape) == "sub_new"
    assert payments_service._invoice_subscription_id(one_off) is None


# --- I dati dell'intestatario --------------------------------------------------


def _wizard_payload(**overrides) -> dict:
    payload = {
        "product_version_id": str(uuid.uuid4()),
        "supply_point": {
            "energy_type": "ELECTRICITY", "pod_code": "IT001E12345678", "street": "Via Roma 1",
            "city": "Roma", "province": "RM", "postal_code": "00100",
        },
        "email": "mario@example.com",
        "holder_first_name": "  Mario ",
        "holder_last_name": "Rossi",
        "pec": "",
        "iban": "it60 x054 2811 1010 0000 0123 456",
    }
    payload.update(overrides)
    return payload


def test_the_wizard_payload_cleans_what_it_is_given():
    parsed = ContractSelfServiceCreate(**_wizard_payload())
    assert parsed.holder_first_name == "Mario"
    assert parsed.pec is None, "una PEC lasciata vuota non è una PEC non valida"
    assert parsed.iban == "IT60X0542811101000000123456"


def test_the_holder_name_is_required_and_a_bad_iban_or_pec_is_refused():
    with pytest.raises(ValidationError):
        ContractSelfServiceCreate(**_wizard_payload(holder_last_name="   "))
    with pytest.raises(ValidationError):
        ContractSelfServiceCreate(**_wizard_payload(iban="123"))
    with pytest.raises(ValidationError):
        ContractSelfServiceCreate(**_wizard_payload(pec="non-una-pec"))
    # IBAN is optional: it can still be added later from "I miei Contratti".
    assert ContractSelfServiceCreate(**_wizard_payload(iban=None)).iban is None


# --- Pagare prima dell'approvazione ------------------------------------------


async def _make_contract(db, organization_id, *, cashback_percentage: int = 100) -> tuple[Contract, User]:
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
    supply_point = SupplyPoint(
        organization_id=organization_id, customer_id=customer.id, energy_type="ELECTRICITY",
        supply_address_id=address.id,
    )
    db.add(supply_point)
    product = Product(
        organization_id=organization_id, code=f"P-{uuid.uuid4().hex[:6]}",
        energy_type="ELECTRICITY", customer_type="BOTH", category="INTERNAL",
    )
    db.add(product)
    await db.flush()
    version = ProductVersion(
        product_id=product.id, version_label="1.0", name="Luce Energia Circolare privati",
        base_price_cents=180_00, billing_period="MONTHLY", contract_duration_months=12,
        contract_cashback_percentage=cashback_percentage, valid_from=NOW,
    )
    db.add(version)
    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Prod", last_name="Uttore",
        promoter_code=f"PR-{uuid.uuid4().hex[:8]}", parent_agent_id=None,
    )
    await db.commit()

    contract = await contract_service.create_contract(
        db, organization_id=organization_id, customer_id=customer.id,
        supply_point_id=supply_point.id, product_version_id=version.id,
        producer_agent_id=agent.id, actor_user_id=user.id, correlation_id=str(uuid.uuid4()),
    )
    for step in ["SUBMITTED", "DOCUMENTS_PENDING"]:
        contract = await contract_service.transition_contract(
            db, organization_id=organization_id, contract=contract, to_status=step,
            actor_user_id=user.id, reason="test", notes=None, correlation_id=str(uuid.uuid4()),
        )
    return contract, user


async def _complete_checkout(
    db, organization_id, contract, *, plan_key: str, subscription: str | None = None, discount_cents: int = 0
):
    session_id = f"cs_{uuid.uuid4().hex[:10]}"
    await contract_service.attach_stripe_checkout_session(
        db, contract=contract, session_id=session_id, plan_key=plan_key, discount_cents=discount_cents
    )
    session = {"id": session_id, "metadata": {"kind": "contract"}}
    if subscription:
        session["subscription"] = subscription
    body, sig = _signed({
        "id": f"evt_{uuid.uuid4().hex[:10]}",
        "type": "checkout.session.completed",
        "data": {"object": session},
    })
    if subscription:
        # Setting cancel_at calls the real Stripe API; the test is not about that.
        original = payments_service._stop_subscription_after_last_instalment

        async def _noop(**_kwargs):
            return None

        payments_service._stop_subscription_after_last_instalment = _noop
        try:
            await payments_service.handle_webhook_event(
                db, organization_id=organization_id, payload=body, sig_header=sig
            )
        finally:
            payments_service._stop_subscription_after_last_instalment = original
    else:
        await payments_service.handle_webhook_event(
            db, organization_id=organization_id, payload=body, sig_header=sig
        )
    await db.refresh(contract)


async def _balance(db, user: User) -> int:
    wallet = (await db.execute(select(Wallet).where(Wallet.user_id == user.id))).scalar_one_or_none()
    return wallet.balance_cents if wallet else 0


async def _approve(db, organization_id, contract, user) -> Contract:
    contract = await contract_service.transition_contract(
        db, organization_id=organization_id, contract=contract, to_status="UNDER_REVIEW",
        actor_user_id=user.id, reason="test", notes=None, correlation_id=str(uuid.uuid4()),
    )
    return await contract_service.transition_contract(
        db, organization_id=organization_id, contract=contract, to_status="APPROVED",
        actor_user_id=user.id, reason="test", notes=None, correlation_id=str(uuid.uuid4()),
    )


@pytest.mark.asyncio
async def test_a_contract_without_documents_can_already_be_paid(db, organization_id):
    contract, _user = await _make_contract(db, organization_id)
    assert contract.status == "DOCUMENTS_PENDING"
    assert contract_service.is_payable(contract)


@pytest.mark.asyncio
async def test_paying_early_credits_the_cashback_but_activates_nothing(db, organization_id):
    await _configure_stripe(db, organization_id)
    contract, user = await _make_contract(db, organization_id)

    await _complete_checkout(db, organization_id, contract, plan_key=payment_plans.PLAN_FULL)

    assert contract.paid_at is not None
    assert contract.status == "DOCUMENTS_PENDING", "il pagamento non sostituisce l'approvazione dei documenti"
    assert contract.activated_at is None
    assert await _balance(db, user) == 180_00, "cashback del 100% dell'importo pagato"
    assert not contract_service.is_payable(contract), "un contratto pagato non si ripaga"


@pytest.mark.asyncio
async def test_approval_of_a_prepaid_contract_activates_it_and_credits_nothing_twice(db, organization_id):
    await _configure_stripe(db, organization_id)
    contract, user = await _make_contract(db, organization_id)
    await _complete_checkout(db, organization_id, contract, plan_key=payment_plans.PLAN_FULL)

    contract = await _approve(db, organization_id, contract, user)

    # APPROVED -> PAYMENT_PENDING -> (already paid) PAID -> ACTIVATION_PENDING
    # -> ACTIVE: the hop that generates commissions, only now.
    assert contract.status == "ACTIVE"
    assert contract.network_snapshot_id is not None
    assert await _balance(db, user) == 180_00


@pytest.mark.asyncio
async def test_an_unpaid_contract_still_stops_at_payment_pending_on_approval(db, organization_id):
    contract, user = await _make_contract(db, organization_id)
    contract = await _approve(db, organization_id, contract, user)
    assert contract.status == "PAYMENT_PENDING"
    assert contract.network_snapshot_id is None


@pytest.mark.asyncio
async def test_on_twelve_instalments_the_cashback_arrives_one_instalment_at_a_time(db, organization_id):
    await _configure_stripe(db, organization_id)
    contract, user = await _make_contract(db, organization_id)

    await _complete_checkout(
        db, organization_id, contract, plan_key=payment_plans.PLAN_MONTHLY_12, subscription="sub_pre_12"
    )
    assert contract.status == "DOCUMENTS_PENDING"
    assert await _balance(db, user) == 15_00, "solo la prima rata, non l'intero anno"

    # The first invoice's own invoice.paid must not credit the first month again.
    await contract_service.record_subscription_invoice(
        db, organization_id=organization_id, subscription_id="sub_pre_12", paid=True,
        amount_cents=15_00, invoice_id="in_first", billing_reason="subscription_create",
    )
    assert await _balance(db, user) == 15_00

    # The second month, delivered twice.
    for _ in range(2):
        await contract_service.record_subscription_invoice(
            db, organization_id=organization_id, subscription_id="sub_pre_12", paid=True,
            amount_cents=15_00, invoice_id="in_month_2", billing_reason="subscription_cycle",
        )
    assert await _balance(db, user) == 30_00

    # Approval afterwards must not add the whole contract on top.
    contract = await _approve(db, organization_id, contract, user)
    assert contract.status == "ACTIVE"
    assert await _balance(db, user) == 30_00

    credits = (await db.execute(
        select(func.count()).select_from(WalletTransaction).where(
            WalletTransaction.reference_contract_id == contract.id
        )
    )).scalar_one()
    assert credits == 2


@pytest.mark.asyncio
async def test_rejecting_a_paid_contract_tells_staff(db, organization_id, monkeypatch):
    await _configure_stripe(db, organization_id)
    contract, user = await _make_contract(db, organization_id)
    await _complete_checkout(db, organization_id, contract, plan_key=payment_plans.PLAN_FULL)

    sent: list[str] = []
    original = contract_service.notifications_service.notify_roles

    async def _capture(db, **kwargs):
        sent.append(kwargs["type_"])
        return await original(db, **kwargs)

    monkeypatch.setattr(contract_service.notifications_service, "notify_roles", _capture)
    await contract_service.transition_contract(
        db, organization_id=organization_id, contract=contract, to_status="REJECTED",
        actor_user_id=user.id, reason="test", notes=None, correlation_id=str(uuid.uuid4()),
    )
    assert "CONTRACT_PAID_REJECTED" in sent


@pytest.mark.asyncio
async def test_single_card_payment_discount_lowers_what_is_charged_and_the_cashback(db, organization_id, monkeypatch):
    """Session 64: 32% off when paying in one go. The Stripe session asks for
    the discounted amount, the contract keeps its list price and freezes the
    discount, the instalment row and the cashback follow what was paid."""
    import stripe

    from app.domains.contracts.models import ContractInstalment

    await _configure_stripe(db, organization_id)
    contract, user = await _make_contract(db, organization_id)
    assert contract.gross_amount_cents == 180_00
    created = []

    class _Session:
        id = "cs_discount_1"
        url = "https://stripe.example/cs_discount_1"

    def _create(**params):
        created.append(params)
        return _Session()

    monkeypatch.setattr(stripe.checkout.Session, "create", staticmethod(_create))
    await payments_service.create_checkout_session_for_contract(
        db, organization_id=organization_id, contract=contract, plan_key=payment_plans.PLAN_FULL,
        success_url="https://x/ok", cancel_url="https://x/ko",
    )
    assert created[0]["line_items"][0]["price_data"]["unit_amount"] == 122_40
    await db.refresh(contract)
    assert contract.payment_discount_cents == 57_60 and contract.gross_amount_cents == 180_00

    body, sig = _signed({
        "id": f"evt_{uuid.uuid4().hex[:10]}", "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_discount_1", "metadata": {"kind": "contract"}}},
    })
    await payments_service.handle_webhook_event(db, organization_id=organization_id, payload=body, sig_header=sig)
    await db.refresh(contract)
    assert contract.paid_at is not None
    rows = list((await db.execute(select(ContractInstalment).where(ContractInstalment.contract_id == contract.id))).scalars())
    assert [(r.number, r.amount_cents) for r in rows] == [(1, 122_40)]
    assert await _balance(db, user) == 122_40, "cashback del 100% di quanto pagato"


@pytest.mark.asyncio
async def test_instalments_are_never_discounted(db, organization_id, monkeypatch):
    import stripe

    await _configure_stripe(db, organization_id)
    contract, _user = await _make_contract(db, organization_id)
    created = []

    class _Session:
        id = "cs_twelve_1"
        url = "https://stripe.example/cs_twelve_1"

    monkeypatch.setattr(stripe.checkout.Session, "create", staticmethod(lambda **p: created.append(p) or _Session()))
    await payments_service.create_checkout_session_for_contract(
        db, organization_id=organization_id, contract=contract, plan_key=payment_plans.PLAN_MONTHLY_12,
        success_url="https://x/ok", cancel_url="https://x/ko",
    )
    assert created[0]["line_items"][0]["price_data"]["unit_amount"] == 15_00  # 180 / 12, no discount
    await db.refresh(contract)
    assert contract.payment_discount_cents == 0
