"""La pratica: N contratti indipendenti, documenti comuni una
volta, un pagamento solo.

What these pin down, in the order a pratica lives it:

- every contract has its own package and frozen price, and nothing past
  DRAFT may lack a package;
- documents uploaded on the pratica fill every contract's slots;
- one bank transfer pays every contract, each exactly as if paid alone, and
  only once an administrator confirms it arrived;
- on an instalment plan each later month is confirmed contract by contract,
  once;
- a contract created outside a pratica still belongs to one.
"""

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.domains.auth import service as auth_service
from app.domains.auth.schemas import RegisterRequest
from app.domains.catalog.models import Product, ProductVersion
from app.domains.contracts import payment_plans
from app.domains.contracts import requests as requests_service
from app.domains.contracts import service as contracts_service
from app.domains.contracts.models import (
    Contract,
    ContractAttribution,
    ContractInstalment,
    ContractRequest,
)
from app.domains.customers.models import Customer
from app.domains.documents import service as documents_service
from app.domains.network import service as network_service
from app.domains.notifications.models import Notification
from app.domains.rbac.models import Role, UserRole
from app.domains.referral import service as referral_service
from app.domains.users.models import User
from app.domains.wallets.models import WalletTransaction

NOW = datetime(2026, 1, 1, tzinfo=UTC)


# --- Preparazione --------------------------------------------------------------


async def _customer(db, organization_id, *, email: str | None = None):
    db.add(Role(organization_id=organization_id, code="CUSTOMER", name="Customer"))
    await db.commit()
    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Pro", last_name="Moter",
        promoter_code=f"REF-{uuid.uuid4().hex[:8]}", parent_agent_id=None,
    )
    code = await referral_service.get_or_create_promoter_code(db, organization_id=organization_id, agent_id=agent.id)
    user = await auth_service.register_with_referral(
        db, organization_id=organization_id,
        payload=RegisterRequest(
            organization_id=str(organization_id), referral_code=code.code,
            email=email or f"pratica-{uuid.uuid4().hex[:8]}@example.demo",
            password="correct-horse-battery-staple", kind="PRIVATE", first_name="Mario", last_name="Rossi",
            accept_privacy=True,
        ),
    )
    customer = (await db.execute(select(Customer).where(Customer.user_id == user.id))).scalar_one()
    return user, customer


async def _package(db, organization_id, *, name: str, price_cents: int, cashback: int = 0):
    product = Product(
        organization_id=organization_id, code=f"P-{uuid.uuid4().hex[:6]}",
        customer_type="BOTH", category="INTERNAL",
    )
    db.add(product)
    await db.flush()
    version = ProductVersion(
        product_id=product.id, version_label="1.0", name=name, base_price_cents=price_cents,
        billing_period="ANNUAL", contract_duration_months=12, valid_from=NOW,
        contract_cashback_percentage=cashback,
    )
    db.add(version)
    await db.commit()
    return version


ADDRESS = requests_service.AddressData(street="Via Roma 1", city="Roma", province="RM", postal_code="00100")
#: Whoever signs gives birth date and place, and the fiscal code
#: must match them -- Mario Rossi, born in Roma on 1 January 1980.
MARIO = dict(fiscal_code="RSSMRA80A01H501U", birth_date=date(1980, 1, 1), birth_place_code="H501")
CARLA = dict(fiscal_code="CLNCRL85C55F205X", birth_date=date(1985, 3, 15), birth_place_code="F205")


async def _open(
    db, organization_id, user, customer, *, points: int = 1, product_version_id=None
) -> ContractRequest:
    return await requests_service.create_request(
        db, organization_id=organization_id, customer_id=customer.id,
        holder=requests_service.HolderData(
            first_name="Mario", last_name="Rossi", email="mario@example.demo", pec=None,
            iban="IT60X0542811101000000123456", address=ADDRESS, **MARIO,
        ),
        actor_user_id=user.id, actor_role="CUSTOMER", promoter_agent_id=None,
        points_count=points, product_version_id=product_version_id,
    )


async def _minimum_documents(db, organization_id, user, request) -> None:
    """What a pratica cannot be sent without: one page of the
    identity document. Not the fiscal code -- that one still only holds each
    contract back from review, not the pratica."""
    for document_type in ("IDENTITY",):
        await documents_service.upload_document(
            db, organization_id=organization_id, contract_request_id=request.id,
            document_type=document_type, file_bytes=b"%PDF-1.4\nfake", content_type="application/pdf",
            original_filename=f"{document_type}.pdf", actor_user_id=user.id, actor_role="CUSTOMER",
        )


async def _pratica_with_three_points(db, organization_id):
    user, customer = await _customer(db, organization_id)
    pkg_a = await _package(db, organization_id, name="Pacchetto A", price_cents=120_00, cashback=100)
    pkg_b = await _package(db, organization_id, name="Pacchetto B", price_cents=240_00)
    pkg_c = await _package(db, organization_id, name="Pacchetto C", price_cents=60_00)
    request = await _open(db, organization_id, user, customer, points=3)
    c1, c2, c3 = await requests_service.list_points(db, request=request)
    for contract, version in ((c1, pkg_a), (c2, pkg_b), (c3, pkg_c)):
        await requests_service.set_point_product(
            db, request=request, contract=contract, product_version_id=version.id, actor_user_id=user.id
        )
    return user, customer, request, [c1, c2, c3]


# --- I contratti della pratica ------------------------------------------------


@pytest.mark.asyncio
async def test_a_pratica_creates_that_many_contracts_each_with_its_own_package_and_price(db, organization_id):
    user, customer, request, (c1, c2, c3) = await _pratica_with_three_points(db, organization_id)

    for contract in (c1, c2, c3):
        await db.refresh(contract)
        assert contract.contract_request_id == request.id
        assert contract.customer_id == customer.id
        assert contract.status == "DRAFT"
        assert contract.holder_last_name == "Rossi"
        assert contract.iban == "IT60X0542811101000000123456"
    assert (c1.gross_amount_cents, c2.gross_amount_cents, c3.gross_amount_cents) == (120_00, 240_00, 60_00)

    await _minimum_documents(db, organization_id, user, request)
    request = await requests_service.submit_request(db, request=request, actor_user_id=user.id)
    assert request.status == "SUBMITTED"
    for contract in (c1, c2, c3):
        await db.refresh(contract)
        assert contract.status == "DOCUMENTS_PENDING"


@pytest.mark.asyncio
async def test_changing_the_count_adds_or_drops_empty_contracts_first(db, organization_id):
    user, customer = await _customer(db, organization_id)
    pkg = await _package(db, organization_id, name="Pacchetto", price_cents=100_00)
    request = await _open(db, organization_id, user, customer, points=2)
    first, second = await requests_service.list_points(db, request=request)
    await requests_service.set_point_product(
        db, request=request, contract=first, product_version_id=pkg.id, actor_user_id=user.id
    )

    points = await requests_service.set_points_count(db, request=request, count=4, actor_user_id=user.id)
    assert len(points) == 4
    points = await requests_service.set_points_count(db, request=request, count=1, actor_user_id=user.id)
    assert [p.id for p in points] == [first.id], "si tolgono prima i contratti senza pacchetto scelto"
    with pytest.raises(requests_service.ContractRequestError, match="almeno un contratto"):
        await requests_service.set_points_count(db, request=request, count=0, actor_user_id=user.id)


@pytest.mark.asyncio
async def test_the_same_package_for_all_lands_on_every_draft_contract(db, organization_id):
    user, customer = await _customer(db, organization_id)
    pkg = await _package(db, organization_id, name="Pacchetto", price_cents=50_00)
    request = await _open(db, organization_id, user, customer, points=3)
    assert await requests_service.set_product_for_all(
        db, request=request, product_version_id=pkg.id, actor_user_id=user.id
    ) == 3
    detail = await requests_service.detail(db, request=request)
    assert [p["position"] for p in detail["points"]] == [1, 2, 3]
    assert [p["product_version_id"] for p in detail["points"]] == [pkg.id, pkg.id, pkg.id]


@pytest.mark.asyncio
async def test_starting_from_a_package_chooses_it_for_every_contract(db, organization_id):
    user, customer = await _customer(db, organization_id)
    pkg = await _package(db, organization_id, name="Pacchetto", price_cents=100_00)
    request = await _open(db, organization_id, user, customer, points=3, product_version_id=pkg.id)
    assert {p.product_version_id for p in await requests_service.list_points(db, request=request)} == {pkg.id}


@pytest.mark.asyncio
async def test_a_pratica_cannot_be_sent_while_a_contract_has_no_package(db, organization_id):
    user, customer = await _customer(db, organization_id)
    request = await _open(db, organization_id, user, customer)
    with pytest.raises(requests_service.ContractRequestError, match="Scegli il pacchetto"):
        await _minimum_documents(db, organization_id, user, request)
        await requests_service.submit_request(db, request=request, actor_user_id=user.id)


@pytest.mark.asyncio
async def test_the_database_refuses_a_contract_past_draft_without_a_package(db, organization_id):
    user, customer = await _customer(db, organization_id)
    request = await _open(db, organization_id, user, customer)
    [contract] = await requests_service.list_points(db, request=request)
    contract.status = "SUBMITTED"
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


@pytest.mark.asyncio
async def test_a_removed_point_is_cancelled_and_no_longer_part_of_the_pratica(db, organization_id):
    user, customer, request, (c1, c2, c3) = await _pratica_with_three_points(db, organization_id)
    await requests_service.remove_point(db, request=request, contract=c2, actor_user_id=user.id)
    await db.refresh(c2)
    assert c2.status == "CANCELLED"
    assert [c.id for c in await requests_service.list_points(db, request=request)] == [c1.id, c3.id]
    [summary] = await requests_service.summaries(db, [request])
    assert summary["points_total"] == 2
    assert summary["total_gross_cents"] == 180_00


@pytest.mark.asyncio
async def test_a_sent_pratica_cannot_be_changed(db, organization_id):
    user, customer, request, (c1, _c2, _c3) = await _pratica_with_three_points(db, organization_id)
    await _minimum_documents(db, organization_id, user, request)
    await requests_service.submit_request(db, request=request, actor_user_id=user.id)
    with pytest.raises(requests_service.ContractRequestError, match="già stata inviata"):
        await requests_service.add_point(db, request=request, actor_user_id=user.id)
    with pytest.raises(requests_service.ContractRequestError, match="già stata inviata"):
        await requests_service.remove_point(db, request=request, contract=c1, actor_user_id=user.id)


@pytest.mark.asyncio
async def test_staff_fix_the_package_of_a_sent_pratica_but_never_of_a_paid_contract(db, organization_id):
    """The customer chose the wrong package (or none) and the
    pratica is already sent -- an administrator corrects it, and the price
    follows. Once that contract is paid, nobody moves it any more."""
    user, customer, request, (c1, c2, _c3) = await _pratica_with_three_points(db, organization_id)
    other = await _package(db, organization_id, name="Pacchetto D", price_cents=300_00)
    await _minimum_documents(db, organization_id, user, request)
    await requests_service.submit_request(db, request=request, actor_user_id=user.id)

    # The customer's own route is still closed on a sent pratica.
    with pytest.raises(requests_service.ContractRequestError):
        await requests_service.set_point_product(
            db, request=request, contract=c1, product_version_id=other.id, actor_user_id=user.id
        )

    fixed = await requests_service.staff_set_point_product(
        db, request=request, contract=c1, product_version_id=other.id, actor_user_id=user.id
    )
    assert fixed.product_version_id == other.id
    assert fixed.gross_amount_cents == 300_00

    c2.paid_at = NOW
    await db.commit()
    with pytest.raises(requests_service.ContractRequestError, match="già pagato"):
        await requests_service.staff_set_point_product(
            db, request=request, contract=c2, product_version_id=other.id, actor_user_id=user.id
        )


# --- Documenti -----------------------------------------------------------------


async def _upload(db, organization_id, user, *, document_type: str, contract_id=None, contract_request_id=None):
    return await documents_service.upload_document(
        db, organization_id=organization_id, contract_id=contract_id, contract_request_id=contract_request_id,
        document_type=document_type, file_bytes=b"%PDF-1.4\nfake", content_type="application/pdf",
        original_filename=f"{document_type}.pdf", actor_user_id=user.id, actor_role="CUSTOMER",
    )


@pytest.mark.asyncio
async def test_documents_uploaded_once_on_the_pratica_fill_every_contract(db, organization_id):
    user, customer, request, contracts = await _pratica_with_three_points(db, organization_id)
    for document_type in ("IDENTITY", "FISCAL_CODE"):
        await _upload(db, organization_id, user, document_type=document_type, contract_request_id=request.id)

    await _minimum_documents(db, organization_id, user, request)
    await requests_service.submit_request(db, request=request, actor_user_id=user.id)
    for contract in contracts:
        await db.refresh(contract)
        assert contract.status == "UNDER_REVIEW", "i documenti della pratica valgono per ogni contratto"
        slots = await documents_service.get_contract_documents_status(
            db, organization_id=organization_id, contract=contract, customer_kind="PRIVATE"
        )
        assert all(slot["document"] is not None for slot in slots if slot["required"])


@pytest.mark.asyncio
async def test_a_contract_own_document_wins_over_the_shared_one(db, organization_id):
    user, customer, request, (c1, c2, _c3) = await _pratica_with_three_points(db, organization_id)
    shared = await _upload(db, organization_id, user, document_type="IDENTITY", contract_request_id=request.id)
    own = await _upload(db, organization_id, user, document_type="IDENTITY", contract_id=c1.id)

    def identity(slots):
        return next(s["document"] for s in slots if s["document_type"] == "IDENTITY")

    assert identity(await documents_service.get_contract_documents_status(
        db, organization_id=organization_id, contract=c1, customer_kind="PRIVATE"
    )).id == own.id
    assert identity(await documents_service.get_contract_documents_status(
        db, organization_id=organization_id, contract=c2, customer_kind="PRIVATE"
    )).id == shared.id


@pytest.mark.asyncio
async def test_a_document_belongs_to_a_contract_or_a_pratica_never_both(db, organization_id):
    user, customer, request, (c1, _c2, _c3) = await _pratica_with_three_points(db, organization_id)
    with pytest.raises(documents_service.DocumentValidationError):
        await _upload(db, organization_id, user, document_type="IDENTITY", contract_id=c1.id, contract_request_id=request.id)


# --- Pagamento -----------------------------------------------------------------


def test_the_monthly_figure_is_each_contract_split_on_its_own_then_added_up():
    contracts = [Contract(gross_amount_cents=cents, status="UNDER_REVIEW") for cents in (100_00, 249_00)]
    by_key = {o.plan.key: o for o in requests_service.plan_options(contracts)}
    # 100,00 / 12 rounds to 8,33 and 249,00 / 12 is exactly 20,75.
    assert by_key[payment_plans.PLAN_MONTHLY_12].instalment_cents == 8_33 + 20_75
    assert by_key[payment_plans.PLAN_MONTHLY_12].rounding_difference_cents == -4
    assert by_key[payment_plans.PLAN_FULL].total_cents == 349_00


def test_no_plan_is_discounted():
    """Paying by bank transfer never carries a discount: one go is the list
    price, the rate split the same total."""
    contracts = [Contract(gross_amount_cents=cents, status="UNDER_REVIEW") for cents in (180_00, 249_00)]
    by_key = {o.plan.key: o for o in requests_service.plan_options(contracts)}
    assert by_key[payment_plans.PLAN_FULL].total_cents == 429_00
    for key in (payment_plans.PLAN_INSTALMENTS_3, payment_plans.PLAN_MONTHLY_12):
        assert by_key[key].total_cents == 429_00 + by_key[key].rounding_difference_cents


def test_many_contracts_can_still_be_paid_in_instalments():
    """There is no ceiling on how many contracts a pratica pays in rate."""
    contracts = [Contract(gross_amount_cents=120_00, status="UNDER_REVIEW") for _ in range(30)]
    by_key = {o.plan.key: o for o in requests_service.plan_options(contracts)}
    assert all(o.available for o in by_key.values())


async def _configure_bank(db, organization_id) -> None:
    from app.domains.organizations.models import Organization

    org = await db.get(Organization, organization_id)
    org.settings = {**(org.settings or {}), "bank_iban": "IT60X0542811101000000123456", "bank_account_holder": "Jav"}
    await db.commit()


async def _pay_by_transfer(db, organization_id, request, user, *, plan_key: str) -> list[Contract]:
    """The customer announces the transfer with `plan_key`; an administrator
    confirms the (first) transfer arrived."""
    await _configure_bank(db, organization_id)
    await requests_service.request_bank_transfer(db, request=request, actor_user_id=user.id, plan_key=plan_key)
    return await requests_service.confirm_bank_transfer(db, request=request, actor_user_id=user.id)


async def _confirm_month(db, organization_id, user, contract, number: int) -> None:
    """What POST /contracts/{id}/instalments/{n}/confirm does."""
    from app.domains.contracts import instalments as instalments_service

    await instalments_service.confirm_manually(db, contract=contract, number=number, actor_user_id=user.id)
    await contracts_service.credit_contract_instalment_cashback(
        db, organization_id=organization_id, contract=contract, instalment_number=number
    )


async def _sent_pratica(db, organization_id):
    user, customer, request, contracts = await _pratica_with_three_points(db, organization_id)
    await _minimum_documents(db, organization_id, user, request)
    await requests_service.submit_request(db, request=request, actor_user_id=user.id)
    for contract in contracts:
        await db.refresh(contract)
    return user, customer, request, contracts


@pytest.mark.asyncio
async def test_one_transfer_pays_every_contract_of_the_pratica_each_as_if_alone(db, organization_id):
    user, customer, request, contracts = await _sent_pratica(db, organization_id)

    paid = await _pay_by_transfer(db, organization_id, request, user, plan_key=payment_plans.PLAN_FULL)
    assert len(paid) == 3
    for contract in contracts:
        await db.refresh(contract)
        assert contract.paid_at is not None
        assert contract.payment_plan == payment_plans.PLAN_FULL
        # Paid before approval: still waiting for its own documents review.
        assert contract.status == "DOCUMENTS_PENDING"
        rows = list((await db.execute(
            select(ContractInstalment).where(ContractInstalment.contract_id == contract.id)
        )).scalars())
        assert [(r.number, r.status, r.amount_cents) for r in rows] == [(1, "PAID", contract.gross_amount_cents)]

    # Only Pacchetto A earns cashback (100%), on what was paid.
    credits = list((await db.execute(
        select(WalletTransaction).where(WalletTransaction.reference_contract_id.in_([c.id for c in contracts]))
    )).scalars())
    assert [(t.reference_contract_id, t.amount_cents) for t in credits] == [(contracts[0].id, 120_00)]


@pytest.mark.asyncio
async def test_on_twelve_instalments_each_month_reaches_each_contract_once(db, organization_id):
    user, customer, request, contracts = await _sent_pratica(db, organization_id)

    await _configure_bank(db, organization_id)
    request = await requests_service.request_bank_transfer(
        db, request=request, actor_user_id=user.id, plan_key=payment_plans.PLAN_MONTHLY_12
    )
    # 120 / 12 = 10,00 ; 240 / 12 = 20,00 ; 60 / 12 = 5,00: the first transfer.
    assert request.bank_transfer_total_cents == 35_00
    await requests_service.confirm_bank_transfer(db, request=request, actor_user_id=user.id)

    for contract in contracts:
        await db.refresh(contract)
        await _confirm_month(db, organization_id, user, contract, 2)
        rows = list((await db.execute(
            select(ContractInstalment)
            .where(ContractInstalment.contract_id == contract.id)
            .order_by(ContractInstalment.number)
        )).scalars())
        assert len(rows) == 12
        assert [r.status for r in rows[:3]] == ["PAID", "PAID", "SCHEDULED"]
        assert {r.payment_source for r in rows[:2]} == {"ADMIN"}

    # Pacchetto A: 100% cashback on each 10,00 instalment -- first month and second, never twice.
    await contracts_service.credit_contract_instalment_cashback(
        db, organization_id=organization_id, contract=contracts[0], instalment_number=2
    )
    credits = list((await db.execute(
        select(WalletTransaction.amount_cents).where(WalletTransaction.reference_contract_id == contracts[0].id)
    )).scalars())
    assert sorted(credits) == [10_00, 10_00]


# --- Contratti fuori da una pratica ------------------------------------------------


@pytest.mark.asyncio
async def test_a_contract_created_on_its_own_gets_a_pratica_of_one(db, organization_id):
    user, customer = await _customer(db, organization_id)
    pkg = await _package(db, organization_id, name="Pacchetto", price_cents=100_00)

    contract = await contracts_service.create_contract_self_service(
        db, organization_id=organization_id, customer_user_id=user.id, product_version_id=pkg.id,
        email="mario@example.demo", holder_first_name="Mario", holder_last_name="Rossi",
    )
    request = await db.get(ContractRequest, contract.contract_request_id)
    assert request is not None
    assert request.customer_id == customer.id
    assert request.status == "SUBMITTED", "la pratica di un solo contratto segue il suo invio"
    [summary] = await requests_service.summaries(db, [request])
    assert summary["points_total"] == 1


# --- Le rotte HTTP ------------------------------------------------------------------
#
# The services above are what the business rules live in; these go through
# FastAPI itself -- routing, schemas, access checks -- because a NameError or a
# response_model mismatch in a router is invisible to every service test and
# surfaces as a 500 on the first real customer.


def _client(db, user_id, organization_id, roles):
    import httpx

    from app.core.db import get_db
    from app.core.deps import CurrentUser, get_current_user
    from app.main import app

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=user_id, organization_id=organization_id, roles=roles
    )
    return app, httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/api")


@pytest.mark.asyncio
async def test_the_pratica_routes_work_end_to_end_for_the_customer(db, organization_id):
    user, customer = await _customer(db, organization_id)
    pkg = await _package(db, organization_id, name="Pacchetto", price_cents=120_00)
    pkg_c = await _package(db, organization_id, name="Pacchetto C", price_cents=60_00)
    app, client = _client(db, user.id, organization_id, ["CUSTOMER"])
    try:
        async with client:
            res = await client.post("/contract-requests", json={
                "holder_first_name": " Mario ", "holder_last_name": "Rossi", "email": "mario@example.demo",
                "pec": "", "iban": "IT60 X054 2811 1010 0000 0123 456",
                "street": "Via Roma 1", "city": "Roma", "province": "rm", "postal_code": "00100",
                "holder_fiscal_code": "rssmra 80a01 h501u", "holder_birth_date": "1980-01-01",
                "holder_birth_place_code": "H501",
                "points_count": 2,
            })
            assert res.status_code == 201, res.text
            request_id = res.json()["id"]
            assert res.json()["iban"] == "IT60X0542811101000000123456"
            points = res.json()["points"]
            assert [p["position"] for p in points] == [1, 2]

            res = await client.post(f"/contract-requests/{request_id}/submit")
            assert res.status_code == 400, "un contratto senza pacchetto blocca l'invio"

            for point, version in zip(points, (pkg, pkg_c), strict=True):
                res = await client.put(
                    f"/contract-requests/{request_id}/points/{point['id']}/product",
                    json={"product_version_id": str(version.id)},
                )
                assert res.status_code == 200, res.text

            res = await client.put(
                f"/contract-requests/{request_id}/points-count", json={"count": 0}
            )
            assert res.status_code == 422

            res = await client.post(f"/contract-requests/{request_id}/submit")
            assert res.status_code == 400 and "Documento d'identità" in res.text, "senza documenti non si invia"
            request_row = await db.get(ContractRequest, uuid.UUID(request_id))
            await _minimum_documents(db, organization_id, user, request_row)

            res = await client.get(f"/contract-requests/{request_id}/documents")
            assert res.status_code == 200, res.text
            assert res.json()["blocking_missing"] == []
            assert {r["document_type"] for r in res.json()["required"]} >= {"IDENTITY", "FISCAL_CODE"}

            res = await client.post(f"/contract-requests/{request_id}/submit")
            assert res.status_code == 200, res.text
            detail = res.json()
            assert detail["status"] == "SUBMITTED"
            assert detail["points_total"] == 2
            assert detail["total_gross_cents"] == 180_00

            res = await client.get(f"/contract-requests/{request_id}/payment-options")
            assert res.status_code == 200, res.text
            options = {o["key"]: o for o in res.json()["options"]}
            assert options["MONTHLY_12"]["instalment_cents"] == 10_00 + 5_00
            assert len(res.json()["lines"]) == 2

            res = await client.get("/contract-requests/mine")
            assert [r["id"] for r in res.json()] == [request_id]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_another_customer_cannot_see_or_touch_a_pratica(db, organization_id):
    user, customer = await _customer(db, organization_id)
    request = await _open(db, organization_id, user, customer)
    other_user, _ = await _customer_without_role(db, organization_id)
    app, client = _client(db, other_user.id, organization_id, ["CUSTOMER"])
    try:
        async with client:
            assert (await client.get(f"/contract-requests/{request.id}")).status_code == 404
            res = await client.put(f"/contract-requests/{request.id}/points-count", json={"count": 3})
            assert res.status_code == 404
    finally:
        app.dependency_overrides.clear()


async def _customer_without_role(db, organization_id):
    """A second customer in the same organization (the CUSTOMER role already
    exists from the first)."""
    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Altro", last_name="Promoter",
        promoter_code=f"REF-{uuid.uuid4().hex[:8]}", parent_agent_id=None,
    )
    code = await referral_service.get_or_create_promoter_code(db, organization_id=organization_id, agent_id=agent.id)
    user = await auth_service.register_with_referral(
        db, organization_id=organization_id,
        payload=RegisterRequest(
            organization_id=str(organization_id), referral_code=code.code,
            email=f"altro-{uuid.uuid4().hex[:8]}@example.demo", password="correct-horse-battery-staple",
            kind="PRIVATE", first_name="Luigi", last_name="Verdi", accept_privacy=True,
        ),
    )
    customer = (await db.execute(select(Customer).where(Customer.user_id == user.id))).scalar_one()
    return user, customer


@pytest.mark.asyncio
async def test_a_paid_contract_shows_in_accounting_with_its_instalments(db, organization_id):
    """Paying a contract used to leave no real-money trace in
    "Contabilità" -- only its cashback. Every paid instalment is now a row,
    counted in the totals and opening the contract's own detail."""
    from app.domains.accounting import details as accounting_details
    from app.domains.accounting import service as accounting_service

    user, customer, request, contracts = await _sent_pratica(db, organization_id)
    await _pay_by_transfer(db, organization_id, request, user, plan_key=payment_plans.PLAN_MONTHLY_12)

    movements = await accounting_service.list_my_movements(db, organization_id=organization_id, user_id=user.id)
    payments = [m for m in movements if m["kind"] == "CONTRACT_PAYMENT"]
    assert sorted(m["amount_cents"] for m in payments) == [5_00, 10_00, 20_00]
    assert all(m["payment_method"] == "BANK_TRANSFER" and m["contract_request_id"] == request.id for m in payments)

    summary = await accounting_service.my_summary(db, organization_id=organization_id, user_id=user.id)
    assert summary["spent_contracts_cents"] == 35_00
    assert summary["next_instalment_cents"] == 35_00, "la prossima rata di tutti i contratti insieme"

    detail = await accounting_details.build_detail(
        db, organization_id=organization_id, ref=f"contract:{contracts[0].id}", owner_user_id=user.id
    )
    assert detail["kind"] == "CONTRACT"
    assert len(detail["instalments"]) == 12
    assert detail["instalments"][0]["status"] == "PAID"
    assert detail["instalments"][0]["paid_at"] is not None
    assert any(e["label"].startswith("Prossima rata 2/12") for e in detail["timeline"])


# --- Il promoter compila per il cliente ----------------------------------


async def _promoter_and_customer(db, organization_id):
    """A promoter with a login, who is ALSO a customer (joined through "Lavora
    con noi"), and a customer of their own attributed to their referral code."""
    from app.core.security import hash_password
    from app.domains.users.models import User

    db.add(Role(organization_id=organization_id, code="CUSTOMER", name="Customer"))
    await db.commit()
    promoter_user = User(
        organization_id=organization_id, email=f"promo-{uuid.uuid4().hex[:6]}@example.demo",
        password_hash=hash_password("irrelevant"),
    )
    db.add(promoter_user)
    await db.commit()
    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Paola", last_name="Promoter",
        promoter_code=f"REF-{uuid.uuid4().hex[:8]}", parent_agent_id=None, user_id=promoter_user.id,
    )
    code = await referral_service.get_or_create_promoter_code(db, organization_id=organization_id, agent_id=agent.id)
    customer_user = await auth_service.register_with_referral(
        db, organization_id=organization_id,
        payload=RegisterRequest(
            organization_id=str(organization_id), referral_code=code.code,
            email=f"cliente-{uuid.uuid4().hex[:6]}@example.demo", password="correct-horse-battery-staple",
            kind="PRIVATE", first_name="Carla", last_name="Cliente", accept_privacy=True,
        ),
    )
    customer = (await db.execute(select(Customer).where(Customer.user_id == customer_user.id))).scalar_one()
    return promoter_user, agent, customer_user, customer


@pytest.mark.asyncio
async def test_a_promoter_who_is_also_a_customer_can_handle_their_customers_documents(db, organization_id):
    """"Lavora con noi" keeps the CUSTOMER role, and the document check used to
    read only the first role of the token: the promoter was refused the
    documents of the very contracts they had just filled in."""
    from fastapi import HTTPException

    from app.core.deps import CurrentUser
    from app.domains.documents.router import _assert_contract_document_access

    promoter_user, agent, customer_user, customer = await _promoter_and_customer(db, organization_id)
    pkg = await _package(db, organization_id, name="Pacchetto", price_cents=100_00)
    request = await requests_service.create_request(
        db, organization_id=organization_id, customer_id=customer.id,
        holder=requests_service.HolderData(
            first_name="Carla", last_name="Cliente", email="carla@example.demo", pec=None, iban=None, address=ADDRESS,
            **CARLA,
        ),
        actor_user_id=promoter_user.id, actor_role="PROMOTER", promoter_agent_id=agent.id,
        points_count=2, product_version_id=pkg.id,
    )
    contract, _ = await requests_service.list_points(db, request=request)
    assert contract.activated_by_promoter_id == agent.id

    as_promoter = CurrentUser(user_id=promoter_user.id, organization_id=organization_id, roles=["CUSTOMER", "PROMOTER"])
    assert await _assert_contract_document_access(
        db, current_user=as_promoter, contract=contract, actor_role="CUSTOMER"
    ) == "PROMOTER"
    as_customer = CurrentUser(user_id=customer_user.id, organization_id=organization_id, roles=["CUSTOMER"])
    assert await _assert_contract_document_access(
        db, current_user=as_customer, contract=contract, actor_role="CUSTOMER"
    ) == "CUSTOMER"

    stranger_user, _ = await _customer_without_role(db, organization_id)
    as_stranger = CurrentUser(user_id=stranger_user.id, organization_id=organization_id, roles=["CUSTOMER"])
    with pytest.raises(HTTPException):
        await _assert_contract_document_access(db, current_user=as_stranger, contract=contract, actor_role="CUSTOMER")


@pytest.mark.asyncio
async def test_the_customer_is_told_when_their_promoter_sends_a_pratica(db, organization_id):
    from app.domains.notifications.models import Notification

    promoter_user, agent, customer_user, customer = await _promoter_and_customer(db, organization_id)
    pkg = await _package(db, organization_id, name="Pacchetto", price_cents=100_00)
    request = await requests_service.create_request(
        db, organization_id=organization_id, customer_id=customer.id,
        holder=requests_service.HolderData(
            first_name="Carla", last_name="Cliente", email="carla@example.demo", pec=None, iban=None, address=ADDRESS,
            **CARLA,
        ),
        actor_user_id=promoter_user.id, actor_role="PROMOTER", promoter_agent_id=agent.id,
        points_count=1, product_version_id=pkg.id,
    )
    await _minimum_documents(db, organization_id, promoter_user, request)
    await requests_service.submit_request(db, request=request, actor_user_id=promoter_user.id)

    notes = list((await db.execute(
        select(Notification).where(Notification.recipient_user_id == customer_user.id)
    )).scalars())
    assert any("Paola Promoter" in (n.body or "") for n in notes)
    [summary] = await requests_service.summaries(db, [request])
    assert summary["activated_by_promoter_name"] == "Paola Promoter"
    assert summary["customer_id"] == customer.id


# --- Cashback dei contratti a rate, intero in anticipo o rata per rata ---------


async def _set_cashback_mode(db, organization_id, mode: str) -> None:
    from app.domains.organizations.models import Organization

    org = await db.get(Organization, organization_id)
    org.settings = {**(org.settings or {}), "contract_instalment_cashback_mode": mode}
    await db.commit()


async def _pay_first_instalment_of_12(db, organization_id):
    user, customer, request, contracts = await _sent_pratica(db, organization_id)
    await _pay_by_transfer(db, organization_id, request, user, plan_key=payment_plans.PLAN_MONTHLY_12)
    for contract in contracts:
        await db.refresh(contract)
    return user, contracts


async def _second_month(db, organization_id, user, contracts):
    for contract in contracts:
        await _confirm_month(db, organization_id, user, contract, 2)


async def _credits(db, contract):
    return sorted((await db.execute(
        select(WalletTransaction.amount_cents).where(WalletTransaction.reference_contract_id == contract.id)
    )).scalars())


@pytest.mark.asyncio
async def test_upfront_mode_credits_the_whole_cashback_at_the_first_instalment_and_nothing_after(db, organization_id):
    await _set_cashback_mode(db, organization_id, "UPFRONT")
    user, contracts = await _pay_first_instalment_of_12(db, organization_id)
    # Pacchetto A: 120,00 with 100% cashback -- all of it, at once.
    assert await _credits(db, contracts[0]) == [120_00]

    await _second_month(db, organization_id, user, contracts)
    assert await _credits(db, contracts[0]) == [120_00], "nessun altro accredito sulle rate successive"


@pytest.mark.asyncio
async def test_a_contract_credited_in_advance_is_not_credited_again_if_the_setting_changes(db, organization_id):
    await _set_cashback_mode(db, organization_id, "UPFRONT")
    user, contracts = await _pay_first_instalment_of_12(db, organization_id)
    await _set_cashback_mode(db, organization_id, "PER_INSTALMENT")
    await _second_month(db, organization_id, user, contracts)
    assert await _credits(db, contracts[0]) == [120_00]


@pytest.mark.asyncio
async def test_a_month_credited_twice_earns_cashback_once(db, organization_id):
    user, contracts = await _pay_first_instalment_of_12(db, organization_id)
    assert await _credits(db, contracts[0]) == [10_00], "per rata è il comportamento predefinito"

    await _second_month(db, organization_id, user, contracts)
    await contracts_service.credit_contract_instalment_cashback(
        db, organization_id=organization_id, contract=contracts[0], instalment_number=2
    )
    assert await _credits(db, contracts[0]) == [10_00, 10_00]


# --- Bonifico -----------------------------------------------------------


@pytest.mark.asyncio
async def test_a_pratica_paid_by_bank_transfer_is_paid_only_when_an_admin_confirms(db, organization_id):
    await _configure_bank(db, organization_id)
    user, customer, request, contracts = await _sent_pratica(db, organization_id)

    request = await requests_service.request_bank_transfer(db, request=request, actor_user_id=user.id)
    # No discount for paying by bank transfer: the full price is due.
    assert request.bank_transfer_total_cents == 120_00 + 240_00 + 60_00
    for contract in contracts:
        await db.refresh(contract)
        assert contract.paid_at is None
        assert (contract.payment_plan, contract.payment_method) == (payment_plans.PLAN_FULL, "BANK_TRANSFER")
    [summary] = await requests_service.summaries(db, [request])
    assert summary["bank_transfer_pending"] is True and summary["points_payable"] == 3

    admin_id = user.id  # the permission is checked by the router; the service records who confirmed
    paid = await requests_service.confirm_bank_transfer(db, request=request, actor_user_id=admin_id)
    assert len(paid) == 3
    for contract in contracts:
        await db.refresh(contract)
        assert contract.paid_at is not None and contract.payment_method == "BANK_TRANSFER"
        rows = list((await db.execute(
            select(ContractInstalment).where(ContractInstalment.contract_id == contract.id)
        )).scalars())
        assert [(r.status, r.amount_cents, r.payment_source) for r in rows] == [
            ("PAID", contract.gross_amount_cents, "ADMIN")
        ]
    credits = list((await db.execute(
        select(WalletTransaction).where(WalletTransaction.reference_contract_id.in_([c.id for c in contracts]))
    )).scalars())
    assert [t.amount_cents for t in credits] == [120_00]  # Pacchetto A, 100% of what was paid
    [summary] = await requests_service.summaries(db, [request])
    assert summary["bank_transfer_pending"] is False and summary["points_paid"] == 3
    with pytest.raises(requests_service.BankTransferError):
        await requests_service.confirm_bank_transfer(db, request=request, actor_user_id=admin_id)


@pytest.mark.asyncio
async def test_bank_transfer_needs_an_iban_configured(db, organization_id):
    user, _customer, request, _contracts = await _sent_pratica(db, organization_id)
    with pytest.raises(requests_service.BankTransferError):
        await requests_service.request_bank_transfer(db, request=request, actor_user_id=user.id)


# --- Pratiche compilate dall'amministrazione ------------------------------


@pytest.mark.asyncio
async def test_an_admin_can_open_a_pratica_for_a_customer_and_attribute_it_to_a_promoter(db, organization_id):
    """Same pratica as the customer's and the promoter's, only filled in by
    staff: the promoter chosen earns, the customer pays."""
    user, customer = await _customer(db, organization_id)
    package = await _package(db, organization_id, name="Pacchetto Admin", price_cents=180_00)
    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Ada", last_name="Venditrice",
        promoter_code=f"PR-{uuid.uuid4().hex[:8]}", parent_agent_id=None,
    )
    await db.commit()

    request = await requests_service.create_request(
        db, organization_id=organization_id, customer_id=customer.id,
        holder=requests_service.HolderData(
            first_name="Mario", last_name="Rossi", email="mario@example.com", pec=None,
            iban="IT60X0542811101000000123456",
            address=requests_service.AddressData(street="Via Roma 1", city="Roma", province="RM", postal_code="00100"),
            **MARIO,
        ),
        actor_user_id=user.id, actor_role="ADMIN", promoter_agent_id=agent.id, points_count=2,
    )
    assert request.created_by_role == "ADMIN" and request.activated_by_promoter_id == agent.id
    points = await requests_service.list_points(db, request=request)
    assert len(points) == 2
    for contract in points:
        attribution = await db.get(ContractAttribution, contract.contract_attribution_id)
        assert attribution.producer_agent_id == agent.id
        assert contract.activated_by_promoter_id == agent.id
        await requests_service.set_point_product(
            db, request=request, contract=contract, product_version_id=package.id, actor_user_id=user.id
        )

    await _minimum_documents(db, organization_id, user, request)
    request = await requests_service.submit_request(db, request=request, actor_user_id=user.id)
    assert request.status == "SUBMITTED"
    # The customer is told it is waiting for their payment, as when a promoter fills it in.
    notes = list((await db.execute(
        select(Notification).where(Notification.recipient_user_id == user.id, Notification.type == "CONTRACT_CREATED")
    )).scalars())
    assert any("pronti da pagare" in n.title for n in notes)
    # And it is payable by the customer, at the list price.
    payable = requests_service.payable_points(await requests_service.list_points(db, request=request))
    assert len(payable) == 2
    by_key = {o.plan.key: o for o in requests_service.plan_options(payable)}
    assert by_key[payment_plans.PLAN_FULL].total_cents == 2 * 180_00



# --- PEC per le aziende e note della pratica --------------------


@pytest.mark.asyncio
async def test_a_business_pratica_needs_a_pec_a_private_one_does_not(db, organization_id):
    user, customer = await _customer(db, organization_id)
    assert (await _open(db, organization_id, user, customer)).pec is None, "un privato non la deve dare"

    customer.kind = "COMPANY"
    await db.commit()
    company = {"company_name": "Rossi Srl", "legal_rep_fiscal_code": "RSSMRA80A01H501U"}
    with pytest.raises(requests_service.ContractRequestError, match="PEC è obbligatoria"):
        await requests_service.create_request(
            db, organization_id=organization_id, customer_id=customer.id, holder=_holder(**company),
            actor_user_id=user.id, actor_role="CUSTOMER", promoter_agent_id=None,
        )

    request = await requests_service.create_request(
        db, organization_id=organization_id, customer_id=customer.id,
        holder=_holder(pec="azienda@pec.it", **company),
        actor_user_id=user.id, actor_role="CUSTOMER", promoter_agent_id=None,
    )
    assert request.holder_kind == "COMPANY", "senza scelta, il tipo è quello del cliente"
    with pytest.raises(requests_service.ContractRequestError, match="PEC è obbligatoria"):
        await requests_service.update_holder(
            db, request=request, actor_user_id=user.id, holder=_holder(pec="  ", iban=None, **company),
        )



@pytest.mark.asyncio
async def test_notes_are_kept_signed_and_reach_the_staff_notification(db, organization_id):
    user, customer, request, _points = await _pratica_with_three_points(db, organization_id)
    await requests_service.set_notes(
        db, request=request, notes="  Chiamare dopo le 18, il contatore è in cantina.  ", actor_user_id=user.id
    )
    detail = await requests_service.detail(db, request=request)
    assert detail["notes"] == "Chiamare dopo le 18, il contatore è in cantina."
    assert detail["notes_author"].startswith("Cliente")

    with pytest.raises(requests_service.ContractRequestError, match="2000"):
        await requests_service.set_notes(db, request=request, notes="x" * 2001, actor_user_id=user.id)

    # Uno staff che riceva la notifica: la nota deve arrivargli dentro.
    staff = User(organization_id=organization_id, email=f"staff-{uuid.uuid4().hex[:6]}@example.demo", password_hash="x")
    admin_role = Role(organization_id=organization_id, code="ADMIN", name="Admin")
    db.add_all([staff, admin_role])
    await db.flush()
    db.add(UserRole(organization_id=organization_id, user_id=staff.id, role_id=admin_role.id))
    await db.commit()

    await _minimum_documents(db, organization_id, user, request)
    await requests_service.submit_request(db, request=request, actor_user_id=user.id)
    bodies = (
        await db.execute(
            select(Notification.body).where(Notification.type == "CONTRACT_CREATED", Notification.recipient_user_id == staff.id)
        )
    ).scalars().all()
    assert any("contatore è in cantina" in (b or "") for b in bodies)

    with pytest.raises(requests_service.ContractRequestError, match="già stata inviata"):
        await requests_service.set_notes(db, request=request, notes="dopo", actor_user_id=user.id)


# --- Prezzo annuale e prezzo mensile -------------------------------


@pytest.mark.asyncio
async def test_rate_charge_the_monthly_price_and_one_go_the_yearly_price(db, organization_id):
    """«Abbonamento annuale» privati: 149 € in unica soluzione, 12 rate da 18,30 €
    (219,60 €), 3 rate da 73,20 € -- not 149 / 12."""
    user, customer = await _customer(db, organization_id)
    version = await _package(db, organization_id, name="Circolare", price_cents=149_00, cashback=100)
    version.billing_period = "MONTHLY"
    version.monthly_price_cents = 18_30
    await db.commit()
    request = await _open(db, organization_id, user, customer, points=1, product_version_id=version.id)
    await _minimum_documents(db, organization_id, user, request)
    await requests_service.submit_request(db, request=request, actor_user_id=user.id)
    [contract] = await requests_service.list_points(db, request=request)
    assert (contract.gross_amount_cents, contract.instalments_gross_amount_cents) == (149_00, 219_60)

    options = {o.plan.key: o for o in requests_service.plan_options([contract])}
    assert (options["FULL"].total_cents, options["FULL"].instalment_cents) == (149_00, 149_00)
    assert (options["MONTHLY_12"].total_cents, options["MONTHLY_12"].instalment_cents) == (219_60, 18_30)
    assert (options["INSTALMENTS_3"].total_cents, options["INSTALMENTS_3"].instalment_cents) == (219_60, 73_20)

    await _pay_by_transfer(db, organization_id, request, user, plan_key=payment_plans.PLAN_MONTHLY_12)
    await db.refresh(request)
    assert request.bank_transfer_total_cents == 18_30, "il primo bonifico è la prima rata"
    await db.refresh(contract)
    rows = list((await db.execute(
        select(ContractInstalment).where(ContractInstalment.contract_id == contract.id).order_by(ContractInstalment.number)
    )).scalars())
    assert [r.amount_cents for r in rows] == [18_30] * 12
    # 100% cashback, per instalment (the default): on the rata actually paid.
    assert await _credits(db, contract) == [18_30]


# --- Pratica da privato o da azienda ---------------------------------


def _holder(**overrides) -> requests_service.HolderData:
    fields = dict(
        first_name="Mario", last_name="Rossi", email="mario@example.demo", pec=None,
        iban="IT60X0542811101000000123456", address=ADDRESS, **MARIO,
    )
    fields.update(overrides)
    return requests_service.HolderData(**fields)


@pytest.mark.asyncio
async def test_a_business_pratica_needs_company_name_legal_rep_fiscal_code_and_pec(db, organization_id):
    user, customer = await _customer(db, organization_id)
    for missing in (
        {"company_name": None, "legal_rep_fiscal_code": "RSSMRA80A01H501U", "pec": "a@pec.it"},
        {"company_name": "Rossi Srl", "legal_rep_fiscal_code": None, "pec": "a@pec.it"},
        {"company_name": "Rossi Srl", "legal_rep_fiscal_code": "RSSMRA80A01H501U", "pec": None},
    ):
        with pytest.raises(requests_service.ContractRequestError):
            await requests_service.create_request(
                db, organization_id=organization_id, customer_id=customer.id,
                holder=_holder(kind="COMPANY", **missing), actor_user_id=user.id, actor_role="CUSTOMER",
                promoter_agent_id=None,
            )
    # A private pratica asks for none of it.
    request = await requests_service.create_request(
        db, organization_id=organization_id, customer_id=customer.id, holder=_holder(kind="PRIVATE"),
        actor_user_id=user.id, actor_role="CUSTOMER", promoter_agent_id=None,
    )
    assert request.holder_kind == "PRIVATE" and request.company_name is None


@pytest.mark.asyncio
async def test_the_pratica_kind_not_the_customer_decides_vat_and_changing_it_reprices(db, organization_id):
    """A private customer opens a pratica for their company: VAT applies to
    that pratica's contracts. Switched back to privato while still a draft,
    the chosen package is priced again without VAT."""
    user, customer = await _customer(db, organization_id)
    version = await _package(db, organization_id, name="Pacchetto", price_cents=249_00)
    version.tax_configuration = {"vat_percentage": 22.0}
    await db.commit()
    business = _holder(
        kind="COMPANY", company_name="Rossi Srl", legal_rep_fiscal_code="rssmra80a01h501u", pec="rossi@pec.it"
    )
    request = await requests_service.create_request(
        db, organization_id=organization_id, customer_id=customer.id, holder=business,
        actor_user_id=user.id, actor_role="CUSTOMER", promoter_agent_id=None, product_version_id=version.id,
    )
    assert request.legal_rep_fiscal_code == "RSSMRA80A01H501U"
    [contract] = await requests_service.list_points(db, request=request)
    assert (contract.customer_kind, contract.gross_amount_cents) == ("COMPANY", 303_78)
    assert customer.kind == "PRIVATE", "il cliente resta privato: il tipo è della pratica"

    await requests_service.update_holder(db, request=request, holder=_holder(kind="PRIVATE"), actor_user_id=user.id)
    await db.refresh(contract)
    assert (contract.customer_kind, contract.gross_amount_cents) == ("PRIVATE", 249_00)
    assert request.company_name is None


# --- Data e luogo di nascita, codice fiscale controllato --------------


@pytest.mark.asyncio
async def test_the_fiscal_code_is_checked_but_a_mismatch_only_warns(db, organization_id):
    user, customer = await _customer(db, organization_id)
    for wrong, says in (
        ({"fiscal_code": None}, "codice fiscale"),
        ({"birth_date": None}, "data e luogo di nascita"),
        ({"birth_place_code": None}, "data e luogo di nascita"),
        ({"birth_place_code": "XXXX"}, "Luogo di nascita non riconosciuto"),
        ({"birth_date": date.today().replace(year=date.today().year - 10)}, "maggiorenne"),
    ):
        with pytest.raises(requests_service.ContractRequestError, match=says):
            await requests_service.create_request(
                db, organization_id=organization_id, customer_id=customer.id, holder=_holder(**wrong),
                actor_user_id=user.id, actor_role="CUSTOMER", promoter_agent_id=None,
            )
    # A code that does not match is saved anyway: the user chose a warning.
    for wrong, says in (
        ({"fiscal_code": "RSSMRA80A01H501A"}, "carattere"),
        ({"birth_date": date(1980, 1, 2)}, "la data di nascita non corrisponde"),
        ({"birth_place_code": "F205"}, "il luogo di nascita non corrisponde"),
        ({"first_name": "Luigi"}, "il nome non corrisponde"),
    ):
        request = await requests_service.create_request(
            db, organization_id=organization_id, customer_id=customer.id, holder=_holder(**wrong),
            actor_user_id=user.id, actor_role="CUSTOMER", promoter_agent_id=None,
        )
        [problem] = requests_service.fiscal_code_problems(request)
        assert says in problem
    # Omocodia (a digit swapped for a letter) is still Mario Rossi.
    request = await requests_service.create_request(
        db, organization_id=organization_id, customer_id=customer.id,
        holder=_holder(fiscal_code="RSSMRA80A01HR01P"), actor_user_id=user.id, actor_role="CUSTOMER",
        promoter_agent_id=None,
    )
    assert requests_service.fiscal_code_problems(request) == []
    assert (request.holder_fiscal_code, request.holder_birth_place, request.holder_birth_place_code) == (
        "RSSMRA80A01HR01P", "Roma (RM)", "H501",
    )


@pytest.mark.asyncio
async def test_a_business_pratica_checks_the_legal_reps_fiscal_code_and_a_foreign_birthplace(db, organization_id):
    user, customer = await _customer(db, organization_id)
    business = dict(kind="COMPANY", company_name="Rossi Srl", pec="rossi@pec.it", fiscal_code=None)
    request = await requests_service.create_request(
        db, organization_id=organization_id, customer_id=customer.id,
        holder=_holder(**business, legal_rep_fiscal_code="CLNCRL85C55F205X"),
        actor_user_id=user.id, actor_role="CUSTOMER", promoter_agent_id=None,
    )
    assert "il cognome non corrisponde al codice fiscale" in requests_service.fiscal_code_problems(request)
    # Born abroad: the code carries the state (Z100 = Albania).
    request = await requests_service.create_request(
        db, organization_id=organization_id, customer_id=customer.id,
        holder=_holder(
            **business, first_name="Nicolò", last_name="D'Angelo", legal_rep_fiscal_code="DNGNCL50E71Z100P",
            birth_date=date(1950, 5, 31), birth_place_code="Z100",
        ),
        actor_user_id=user.id, actor_role="CUSTOMER", promoter_agent_id=None,
    )
    assert request.holder_fiscal_code is None
    assert (request.legal_rep_fiscal_code, request.holder_birth_place) == ("DNGNCL50E71Z100P", "Albania (estero)")
    assert requests_service.fiscal_code_problems(request) == []


@pytest.mark.asyncio
async def test_a_draft_from_before_cannot_be_sent_without_birth_data(db, organization_id):
    user, customer = await _customer(db, organization_id)
    version = await _package(db, organization_id, name="Pacchetto", price_cents=99_00)
    request = await _open(db, organization_id, user, customer, product_version_id=version.id)
    await _minimum_documents(db, organization_id, user, request)
    request.holder_birth_date = None
    request.holder_birth_place_code = None
    await db.commit()
    with pytest.raises(requests_service.ContractRequestError, match="data e luogo di nascita"):
        await requests_service.submit_request(db, request=request, actor_user_id=user.id)


@pytest.mark.asyncio
async def test_the_birthplace_search_finds_comuni_suppressed_ones_and_states(db, organization_id):
    user, _customer_row = await _customer(db, organization_id)
    app, client = _client(db, user.id, organization_id, ["CUSTOMER"])
    try:
        async with client:
            res = await client.get("/contract-requests/birthplaces", params={"q": "roma"})
            assert res.status_code == 200, res.text
            assert res.json()[0] == {
                "code": "H501", "name": "Roma", "province": "RM", "foreign": False, "active": True, "until": None,
            }
            res = await client.get("/contract-requests/birthplaces", params={"q": "germania"})
            assert res.json()[0]["code"] == "Z112" and res.json()[0]["foreign"]
            res = await client.get("/contract-requests/birthplaces", params={"q": "abano"})
            assert any(not p["active"] and p["until"] for p in res.json()), "anche i comuni soppressi"
    finally:
        app.dependency_overrides.clear()


# --- Sblocca pratica -----------------------------------------------------


@pytest.mark.asyncio
async def test_an_unpaid_sent_pratica_can_be_unlocked_repackaged_and_sent_again(db, organization_id):
    user, customer = await _customer(db, organization_id)
    pkg = await _package(db, organization_id, name="Pacchetto", price_cents=149_00)
    pkg_219 = await _package(db, organization_id, name="Pacchetto 219", price_cents=219_00)
    request = await _open(db, organization_id, user, customer, product_version_id=pkg.id)
    await _minimum_documents(db, organization_id, user, request)
    request = await requests_service.submit_request(db, request=request, actor_user_id=user.id)
    [point] = await requests_service.list_points(db, request=request)
    # The customer had announced a transfer at the old price.
    request.bank_transfer_requested_at = datetime.now(UTC)
    await db.commit()

    with pytest.raises(requests_service.ContractRequestError, match="Si sblocca solo"):
        draft = await _open(db, organization_id, user, customer)
        await requests_service.unlock_request(db, request=draft, actor_user_id=user.id)

    request = await requests_service.unlock_request(db, request=request, actor_user_id=user.id)
    await db.refresh(point)
    assert (request.status, point.status, request.bank_transfer_requested_at) == ("DRAFT", "DRAFT", None)

    await requests_service.set_point_product(
        db, request=request, contract=point, product_version_id=pkg_219.id, actor_user_id=user.id
    )
    request = await requests_service.submit_request(db, request=request, actor_user_id=user.id)
    await db.refresh(point)
    assert request.status == "SUBMITTED" and point.gross_amount_cents == 219_00
    assert point.status in ("DOCUMENTS_PENDING", "UNDER_REVIEW")


@pytest.mark.asyncio
async def test_a_paid_pratica_cannot_be_unlocked(db, organization_id):
    user, customer = await _customer(db, organization_id)
    pkg = await _package(db, organization_id, name="Pacchetto", price_cents=149_00)
    request = await _open(db, organization_id, user, customer, product_version_id=pkg.id)
    await _minimum_documents(db, organization_id, user, request)
    request = await requests_service.submit_request(db, request=request, actor_user_id=user.id)
    [point] = await requests_service.list_points(db, request=request)
    point.paid_at = datetime.now(UTC)
    await db.commit()
    with pytest.raises(requests_service.ContractRequestError, match="già pagata"):
        await requests_service.unlock_request(db, request=request, actor_user_id=user.id)
    point.paid_at = None
    request.bank_transfer_requested_at = request.payment_proof_uploaded_at = datetime.now(UTC)
    await db.commit()
    with pytest.raises(requests_service.ContractRequestError, match="ricevuta del bonifico"):
        await requests_service.unlock_request(db, request=request, actor_user_id=user.id)
