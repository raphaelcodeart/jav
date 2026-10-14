"""Anteprima provvigioni, e provvigioni rilasciate rata per rata.

Business rules pinned here:

- approving a contract (the act that sets commissions going) requires the
  administrator to accept a preview of them, which is stored as a log;
- paid in one go: one commission; paid in N instalments: N slices of 1/N,
  each released when that instalment is really paid -- i.e. when an
  administrator confirms its bank transfer -- and never before the contract
  is ACTIVE;
- however many confirmations arrive for the same instalment, it pays once,
  and the slices add up to exactly the whole commission.
"""

import uuid

import pytest
from sqlalchemy import func, select

from app.domains.commissions.models import CommissionMovement
from app.domains.commissions.services.preview import build_commission_preview
from app.domains.commissions.services.run_calculation import instalment_share
from app.domains.commissions.tasks.dispatch import process_pending_outbox_events
from app.domains.contracts import instalments as instalments_service
from app.domains.contracts import payment_plans
from app.domains.contracts import service as contract_service
from app.domains.contracts.models import ContractCommissionPlan
from tests.test_commission_engine_integration import _make_actor, _setup_contract_ready_to_activate


def test_instalment_slices_add_up_to_exactly_the_commission():
    for total in (4000, 500, 4001, 1, 0, 16000):
        for n in (1, 3, 12):
            assert sum(instalment_share(total, number=k, instalments=n) for k in range(1, n + 1)) == total
    assert instalment_share(4000, number=1, instalments=3) == 1333
    assert instalment_share(4000, number=3, instalments=3) == 1334


async def _under_review(db, organization_id):
    actor = await _make_actor(db, organization_id)
    contract, _sponsor = await _setup_contract_ready_to_activate(db, organization_id, actor)
    for step in ["SUBMITTED", "UNDER_REVIEW"]:
        contract = await contract_service.transition_contract(
            db, organization_id=organization_id, contract=contract, to_status=step,
            actor_user_id=actor, reason="test", notes=None, correlation_id=str(uuid.uuid4()),
        )
    return contract, actor


async def _pay_by_transfer(db, organization_id, contract, actor, *, plan_key: str):
    """The customer chose `plan_key` paying by transfer; an administrator
    confirms the first transfer arrived."""
    contract.payment_plan = plan_key
    contract.payment_method = "BANK_TRANSFER"
    await db.commit()
    await contract_service.record_transfer_payment(
        db, organization_id=organization_id, contract=contract, confirmed_by_user_id=actor
    )
    await db.refresh(contract)


async def _accept_and_approve(db, organization_id, contract, actor):
    preview = await build_commission_preview(db, organization_id=organization_id, contract=contract)
    await contract_service.accept_commission_plan(
        db, organization_id=organization_id, contract=contract, checksum=preview["checksum"], actor_user_id=actor,
    )
    contract = await contract_service.transition_contract(
        db, organization_id=organization_id, contract=contract, to_status="APPROVED",
        actor_user_id=actor, reason="test", notes=None, correlation_id=str(uuid.uuid4()),
    )
    await process_pending_outbox_events(db)
    return contract, preview


async def _amounts(db, contract) -> list[int]:
    rows = (await db.execute(
        select(CommissionMovement.amount_cents).where(CommissionMovement.contract_id == contract.id)
    )).scalars().all()
    return sorted(rows)


@pytest.mark.asyncio
async def test_the_preview_shows_the_real_chain_and_every_possible_split_when_unpaid(db, organization_id):
    contract, _actor = await _under_review(db, organization_id)
    preview = await build_commission_preview(db, organization_id=organization_id, contract=contract)

    assert [(b["role"], b["total_cents"]) for b in preview["beneficiaries"]] == [
        ("Promoter del cliente", 4000),
        ("Sponsor diretto", 500),
    ]
    assert preview["total_commission_cents"] == 4500
    assert preview["payment"]["paid"] is False
    assert {s["plan_key"]: s["commission_per_instalment_cents"] for s in preview["payment"]["scenarios"]} == {
        "FULL": 4500, "INSTALMENTS_3": 1333 + 166, "MONTHLY_12": 333 + 41,
    }
    again = await build_commission_preview(db, organization_id=organization_id, contract=contract)
    assert again["checksum"] == preview["checksum"]


@pytest.mark.asyncio
async def test_accepting_a_preview_that_changed_is_refused(db, organization_id):
    contract, actor = await _under_review(db, organization_id)
    with pytest.raises(contract_service.CommissionPreviewChangedError):
        await contract_service.accept_commission_plan(
            db, organization_id=organization_id, contract=contract, checksum="0" * 64, actor_user_id=actor,
        )
    assert not await contract_service.has_accepted_commission_plan(db, contract_id=contract.id)


@pytest.mark.asyncio
async def test_a_single_payment_pays_the_whole_commission_once(db, organization_id):
    contract, actor = await _under_review(db, organization_id)
    await _pay_by_transfer(db, organization_id, contract, actor, plan_key=payment_plans.PLAN_FULL)
    assert await _amounts(db, contract) == [], "nessuna provvigione prima dell'approvazione"

    contract, _preview = await _accept_and_approve(db, organization_id, contract, actor)
    assert contract.status == "ACTIVE"
    assert await _amounts(db, contract) == [500, 4000]

    # A second pass over the outbox (ContractActivated included) pays nothing more.
    await process_pending_outbox_events(db)
    assert await _amounts(db, contract) == [500, 4000]
    plan = (await db.execute(
        select(ContractCommissionPlan).where(ContractCommissionPlan.contract_id == contract.id)
    )).scalar_one()
    assert plan.total_commission_cents == 4500


@pytest.mark.asyncio
async def test_three_instalments_release_three_slices_one_payment_at_a_time(db, organization_id):
    contract, actor = await _under_review(db, organization_id)
    await _pay_by_transfer(db, organization_id, contract, actor, plan_key=payment_plans.PLAN_INSTALMENTS_3)

    contract, preview = await _accept_and_approve(db, organization_id, contract, actor)
    assert [row["commission_cents"] for row in preview["payment"]["schedule"]] == [1499, 1499, 1502]
    assert await _amounts(db, contract) == [166, 1333], "solo la prima quota"

    # Month two: confirmed once; a second confirmation of the same month is refused.
    await instalments_service.confirm_manually(db, contract=contract, number=2, actor_user_id=actor)
    with pytest.raises(instalments_service.InstalmentError):
        await instalments_service.confirm_manually(db, contract=contract, number=2, actor_user_id=actor)
    await process_pending_outbox_events(db)
    assert await _amounts(db, contract) == [166, 166, 1333, 1333]

    # Month three. A repeated recording of it (two administrators at once)
    # pays nothing more.
    await instalments_service.confirm_manually(db, contract=contract, number=3, actor_user_id=actor)
    assert await instalments_service.record_payment(
        db, contract=contract, source=instalments_service.SOURCE_ADMIN, number=3, actor_user_id=actor
    ) is None
    await process_pending_outbox_events(db)

    amounts = await _amounts(db, contract)
    assert len(amounts) == 6
    assert sum(amounts) == 4500, "le quote sommano esattamente la provvigione intera"
    rows = await instalments_service.list_instalments(db, contract_id=contract.id)
    assert [r.payment_source for r in rows] == ["ADMIN", "ADMIN", "ADMIN"]
    assert all(r.commission_released_at is not None for r in rows)


@pytest.mark.asyncio
async def test_instalments_paid_before_approval_are_released_together_at_activation(db, organization_id):
    contract, actor = await _under_review(db, organization_id)
    await _pay_by_transfer(db, organization_id, contract, actor, plan_key=payment_plans.PLAN_INSTALMENTS_3)
    await instalments_service.confirm_manually(db, contract=contract, number=2, actor_user_id=actor)
    await process_pending_outbox_events(db)
    assert await _amounts(db, contract) == []

    await _accept_and_approve(db, organization_id, contract, actor)
    assert await _amounts(db, contract) == [166, 166, 1333, 1333]


@pytest.mark.asyncio
async def test_an_approved_contract_without_an_accepted_preview_does_not_activate_on_payment(db, organization_id):
    contract, actor = await _under_review(db, organization_id)
    contract = await contract_service.transition_contract(
        db, organization_id=organization_id, contract=contract, to_status="APPROVED",
        actor_user_id=actor, reason="approvato prima dell'anteprima", notes=None, correlation_id=str(uuid.uuid4()),
    )
    assert contract.status == "PAYMENT_PENDING"

    await _pay_by_transfer(db, organization_id, contract, actor, plan_key=payment_plans.PLAN_FULL)
    assert contract.status == "PAYMENT_PENDING"
    assert contract.paid_at is not None
    assert await _amounts(db, contract) == []


@pytest.mark.asyncio
async def test_a_confirmed_bank_transfer_is_one_payment_and_one_commission(db, organization_id):
    contract, actor = await _under_review(db, organization_id)
    contract, _preview = await _accept_and_approve(db, organization_id, contract, actor)
    assert contract.status == "PAYMENT_PENDING"

    await contract_service.transition_contract(
        db, organization_id=organization_id, contract=contract, to_status="PAID",
        actor_user_id=actor, reason="bonifico ricevuto", notes=None, correlation_id=str(uuid.uuid4()),
    )
    await process_pending_outbox_events(db)
    assert await _amounts(db, contract) == [500, 4000]
    rows = await instalments_service.list_instalments(db, contract_id=contract.id)
    assert [(r.number, r.payment_source) for r in rows] == [(1, "ADMIN")]
    count = (await db.execute(
        select(func.count()).select_from(CommissionMovement).where(CommissionMovement.contract_id == contract.id)
    )).scalar_one()
    assert count == 2
