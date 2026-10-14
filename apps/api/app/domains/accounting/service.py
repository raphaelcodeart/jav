import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.catalog.models import ProductVersion
from app.domains.orders import service as orders_service
from app.domains.orders.models import Order
from app.domains.wallets import service as wallets_service


async def _product_name_lookups(db: AsyncSession, wallet_txns: list[dict]) -> dict[uuid.UUID, str]:
    """Batched (not N+1) resolution of "what this WALLET row is about", for
    both list_my_movements and list_all_movements: the product name of the
    order a row paid (part of) or was credited for."""
    order_ids = {t["reference_order_id"] for t in wallet_txns if t["reference_order_id"] is not None}
    product_name_by_order_id: dict[uuid.UUID, str] = {}
    if order_ids:
        orders = (await db.execute(select(Order).where(Order.id.in_(order_ids)))).scalars().all()
        version_ids = {o.product_version_id for o in orders}
        versions = {
            v.id: v
            for v in (
                await db.execute(select(ProductVersion).where(ProductVersion.id.in_(version_ids)))
            ).scalars()
        }
        for order in orders:
            version = versions.get(order.product_version_id)
            if version is not None:
                product_name_by_order_id[order.id] = version.name
    return product_name_by_order_id


#: Every contract instalment is a bank transfer an administrator confirmed
#: by hand -- the only way real money reaches the platform.
INSTALMENT_PAYMENT_METHOD = "BANK_TRANSFER"


async def _contract_product_names(db: AsyncSession, contract_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    from app.domains.contracts.models import Contract

    if not contract_ids:
        return {}
    rows = (
        await db.execute(
            select(Contract.id, ProductVersion.name)
            .join(ProductVersion, ProductVersion.id == Contract.product_version_id)
            .where(Contract.id.in_(contract_ids))
        )
    ).all()
    return {row.id: row.name for row in rows}


async def contract_payment_movements(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID | None
) -> list[dict]:
    """Every paid instalment of a Jav contract, as a real-money row,
    so paying a contract leaves a trace in "Contabilità" -- not only the
    JavCash cashback it earned. One row per
    instalment, because that is what was actually charged: a single payment
    is one row, 12 rate are twelve, each at the time it was collected."""
    from app.domains.contracts.models import Contract, ContractInstalment
    from app.domains.customers.models import Customer
    from app.domains.wallets.service import _resolve_display_names

    stmt = (
        select(ContractInstalment, Contract, Customer.user_id)
        .join(Contract, Contract.id == ContractInstalment.contract_id)
        .join(Customer, Customer.id == Contract.customer_id)
        .where(ContractInstalment.organization_id == organization_id, ContractInstalment.status == "PAID")
    )
    if customer_user_id is not None:
        stmt = stmt.where(Customer.user_id == customer_user_id)
    rows = (await db.execute(stmt)).all()
    if not rows:
        return []
    names = await _contract_product_names(db, {c.id for _, c, _ in rows})
    user_ids = {uid for _, _, uid in rows if uid}
    display = await _resolve_display_names(db, organization_id=organization_id, user_ids=user_ids) if user_ids else {}
    out = []
    for instalment, contract, user_id in rows:
        plan = f"rata {instalment.number} di {instalment.instalments_total}" if instalment.instalments_total > 1 else None
        out.append({
            "id": f"instalment-{instalment.id}",
            "kind": "CONTRACT_PAYMENT",
            "type": None,
            "source": instalment.payment_source,
            "payment_method": INSTALMENT_PAYMENT_METHOD,
            "amount_cents": instalment.amount_cents,
            "currency": "EUR",
            "product_name": names.get(contract.id),
            "order_id": None,
            "contract_id": contract.id,
            "contract_request_id": contract.contract_request_id,
            "note": plan,
            "customer_user_id": user_id,
            "customer_display_name": display.get(user_id) if user_id else None,
            "created_at": instalment.paid_at or instalment.created_at,
        })
    return out


def _order_payment_row(row: dict) -> dict | None:
    """The real-money leg of a PAID order -- what was actually paid by bank
    transfer, excluding any JavCash applied (shown separately as its own
    PURCHASE_DEBIT WALLET row) and with any cashback surcharge added back in
    (it's part of what was genuinely charged). None when credit alone
    covered the whole price -- nothing real-money to show."""
    paid_amount_cents = (
        row["amount_cents"] - row["credit_applied_cents"] + row.get("cashback_surcharge_cents", 0)
    )
    if paid_amount_cents <= 0:
        return None
    return {
        "id": f"order-{row['id']}",
        "kind": "ORDER_PAYMENT",
        "type": None,
        "source": None,
        "payment_method": row["payment_method"],
        "amount_cents": paid_amount_cents,
        "currency": "EUR",
        "product_name": row["product_name"],
        "order_id": row["id"],
        "contract_id": None,
        "contract_request_id": None,
        "note": None,
        "customer_user_id": row["customer_user_id"],
        "customer_display_name": row["customer_display_name"],
        "created_at": row["paid_at"] or row["created_at"],
    }


async def list_my_movements(db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID) -> list[dict]:
    """Merges this user's own WalletTransaction rows (JavCash -- every
    movement in/out of their internal wallet) with their own PAID orders'
    and paid contract instalments' real-money payments (EUR, by bank
    transfer), newest first. Read-only, computed fresh on every call -- no
    new table, every underlying source stays each domain's own single
    source of truth."""
    wallet = await wallets_service.get_or_create_wallet(db, organization_id=organization_id, user_id=user_id)
    wallet_txns = await wallets_service.list_transactions_for_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, limit=500
    )
    product_name_by_order_id = await _product_name_lookups(db, wallet_txns)
    contract_names = await _contract_product_names(
        db, {t["reference_contract_id"] for t in wallet_txns if t["reference_contract_id"]}
    )

    movements = []
    for t in wallet_txns:
        is_outgoing = t["from_wallet_id"] == wallet.id
        order_id = t["reference_order_id"]
        product_name = None
        if order_id:
            product_name = product_name_by_order_id.get(order_id)
        elif t["reference_contract_id"]:
            product_name = contract_names.get(t["reference_contract_id"])
        movements.append(
            {
                "id": str(t["id"]),
                "kind": "WALLET",
                "type": t["type"],
                "source": t["source"],
                "payment_method": None,
                "amount_cents": -t["amount_cents"] if is_outgoing else t["amount_cents"],
                "currency": "JAVCASH",
                "product_name": product_name,
                "order_id": order_id,
                "contract_id": t["reference_contract_id"],
                "contract_request_id": None,
                "note": t["note"],
                "customer_user_id": user_id,
                "customer_display_name": None,
                "created_at": t["created_at"],
            }
        )

    orders_mine = await orders_service.list_orders_for_customer(
        db, organization_id=organization_id, customer_user_id=user_id
    )
    paid_orders = [o for o in orders_mine if o.status == "PAID"]
    order_rows = await orders_service.hydrate(db, paid_orders)
    for row in order_rows:
        movement = _order_payment_row(row)
        if movement is not None:
            movements.append(movement)

    movements.extend(await contract_payment_movements(db, organization_id=organization_id, customer_user_id=user_id))

    movements.sort(key=lambda m: m["created_at"], reverse=True)
    return movements


async def list_all_movements(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID | None = None
) -> list[dict]:
    """Admin-wide "Contabilità" -- every customer's movements merged into
    one list, optionally filtered to a single customer (customer_user_id).
    Same sources and unification as list_my_movements, from an org-wide
    vantage point instead of one wallet's.

    Attribution for a WALLET row: the receiving wallet's owner when there
    is one (to_wallet_id set -- an incoming credit), otherwise the sending
    wallet's owner (an outgoing PURCHASE_DEBIT/REVERSAL-from). A
    peer-to-peer TRANSFER between two different customers is therefore
    shown once here, from the receiver's side only -- an accepted
    simplification for this higher-level summary; the admin Wallets tab
    (admin-wallets-panel.tsx) already shows the full two-sided raw ledger
    for that case."""
    wallet_txns = await wallets_service.list_all_transactions_for_org(
        db, organization_id=organization_id, user_id=customer_user_id, limit=2000
    )
    product_name_by_order_id = await _product_name_lookups(db, wallet_txns)
    contract_names = await _contract_product_names(
        db, {t["reference_contract_id"] for t in wallet_txns if t["reference_contract_id"]}
    )

    movements = []
    for t in wallet_txns:
        if t.get("to_wallet_id"):
            cust_id, cust_name, is_outgoing = t.get("to_user_id"), t.get("to_display_name"), False
        else:
            cust_id, cust_name, is_outgoing = t.get("from_user_id"), t.get("from_display_name"), True
        order_id = t["reference_order_id"]
        product_name = None
        if order_id:
            product_name = product_name_by_order_id.get(order_id)
        elif t["reference_contract_id"]:
            product_name = contract_names.get(t["reference_contract_id"])
        movements.append(
            {
                "id": str(t["id"]),
                "kind": "WALLET",
                "type": t["type"],
                "source": t["source"],
                "payment_method": None,
                "amount_cents": -t["amount_cents"] if is_outgoing else t["amount_cents"],
                "currency": "JAVCASH",
                "product_name": product_name,
                "order_id": order_id,
                "contract_id": t["reference_contract_id"],
                "contract_request_id": None,
                "note": t["note"],
                "customer_user_id": cust_id,
                "customer_display_name": cust_name,
                "created_at": t["created_at"],
            }
        )

    orders_all = await orders_service.list_orders(db, organization_id=organization_id, status_filter="PAID")
    if customer_user_id is not None:
        orders_all = [o for o in orders_all if o.customer_user_id == customer_user_id]
    order_rows = await orders_service.hydrate(db, orders_all)
    for row in order_rows:
        movement = _order_payment_row(row)
        if movement is not None:
            movements.append(movement)

    movements.extend(
        await contract_payment_movements(db, organization_id=organization_id, customer_user_id=customer_user_id)
    )

    movements.sort(key=lambda m: m["created_at"], reverse=True)
    return movements


CASHBACK_SOURCES = frozenset({"ORDER_CASHBACK_BASE", "ORDER_CASHBACK_BONUS", "CONTRACT_CASHBACK"})
REAL_MONEY_KINDS = frozenset({"ORDER_PAYMENT", "CONTRACT_PAYMENT"})


async def my_summary(db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID) -> dict:
    """The totals at the top of "Contabilità": what was paid
    and how, JavCash in and out, contracts, and -- for someone who is also
    a promoter -- commissions. Built from list_my_movements so the cards can
    never tell a different story from the list below them."""
    from datetime import UTC, datetime

    from app.domains.commissions.models import CommissionMovement
    from app.domains.commissions.services.admin_ledger import PAYABLE_STATUSES
    from app.domains.contracts.models import Contract, ContractInstalment
    from app.domains.customers.models import Customer
    from app.domains.network.models import AgentProfile

    movements = await list_my_movements(db, organization_id=organization_id, user_id=user_id)
    now = datetime.now(UTC)
    payments = [m for m in movements if m["kind"] in REAL_MONEY_KINDS]
    wallet_rows = [m for m in movements if m["kind"] == "WALLET"]

    def total(rows, predicate=lambda m: True):
        return sum(abs(m["amount_cents"]) for m in rows if predicate(m))

    wallet = await wallets_service.get_or_create_wallet(db, organization_id=organization_id, user_id=user_id)
    out = {
        "spent_total_cents": total(payments),
        "spent_bank_transfer_cents": total(payments, lambda m: m["payment_method"] == "BANK_TRANSFER"),
        "spent_this_month_cents": total(
            payments, lambda m: m["created_at"].year == now.year and m["created_at"].month == now.month
        ),
        "spent_orders_cents": total(payments, lambda m: m["kind"] == "ORDER_PAYMENT"),
        "spent_contracts_cents": total(payments, lambda m: m["kind"] == "CONTRACT_PAYMENT"),
        "payments_count": len(payments),
        "javcash_balance_cents": wallet.balance_cents,
        "javcash_received_cents": total(wallet_rows, lambda m: m["amount_cents"] > 0),
        "javcash_spent_cents": total(wallet_rows, lambda m: m["amount_cents"] < 0),
        "cashback_received_cents": total(
            wallet_rows, lambda m: m["amount_cents"] > 0 and (m["source"] or "") in CASHBACK_SOURCES
        ),
        "instalments_paid": sum(1 for m in payments if m["kind"] == "CONTRACT_PAYMENT"),
    }

    customer = (
        await db.execute(select(Customer).where(Customer.organization_id == organization_id, Customer.user_id == user_id))
    ).scalar_one_or_none()
    if customer is not None:
        contracts = list((await db.execute(select(Contract).where(Contract.customer_id == customer.id))).scalars())
        out["contracts_active"] = sum(1 for c in contracts if c.status in ("ACTIVE", "RENEWED"))
        billing = [c.id for c in contracts if c.status not in ("REJECTED", "CANCELLED")]
        if billing:
            next_row = (
                await db.execute(
                    select(ContractInstalment)
                    .where(ContractInstalment.contract_id.in_(billing), ContractInstalment.status == "SCHEDULED")
                    .order_by(ContractInstalment.due_date)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if next_row is not None:
                same_day = (
                    await db.execute(
                        select(ContractInstalment.amount_cents).where(
                            ContractInstalment.contract_id.in_(billing),
                            ContractInstalment.status == "SCHEDULED",
                            ContractInstalment.due_date == next_row.due_date,
                        )
                    )
                ).scalars()
                out["next_instalment_due_date"] = next_row.due_date.isoformat()
                out["next_instalment_cents"] = sum(same_day)

    agent_id = (
        await db.execute(
            select(AgentProfile.id).where(AgentProfile.organization_id == organization_id, AgentProfile.user_id == user_id)
        )
    ).scalar_one_or_none()
    if agent_id is not None:
        rows = (
            await db.execute(
                select(CommissionMovement.amount_cents, CommissionMovement.status).where(
                    CommissionMovement.organization_id == organization_id, CommissionMovement.agent_id == agent_id
                )
            )
        ).all()
        live = [r for r in rows if r.status not in ("REVERSED", "CANCELLED")]
        out["commissions_total_cents"] = sum(r.amount_cents for r in live)
        out["commissions_to_collect_cents"] = sum(r.amount_cents for r in live if r.status in PAYABLE_STATUSES)
        out["commissions_paid_cents"] = sum(r.amount_cents for r in live if r.status == "PAID")
        out["commissions_count"] = len(live)
    return out
