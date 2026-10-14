"""Il dettaglio di un movimento, e di ciò a cui si riferisce.

"Contabilità" lists movements; clicking one -- or the order or contract it
points to -- opens everything there is to know about it: what, how much,
how it was paid, and a timeline with the exact time of every step and who
did it (created, receipt uploaded, payment confirmed by an administrator,
cashback credited...).

One entry point, `build_detail(ref)`, for one shape (AccountingDetailRead),
whatever the ref names:

- ``wallet:<transaction id>`` -- a JavCash movement;
- ``order:<id>`` -- a Shop order;
- ``contract:<id>`` -- a Jav contract and its instalments.

`owner_user_id` scopes everything to one customer's own things; None is the
administrator's view. Anything that does not belong to the owner is simply
not found -- never a hint that it exists.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.catalog.models import ProductVersion
from app.domains.contracts import payment_plans
from app.domains.wallets.service import _resolve_display_names

PAYMENT_METHOD_LABELS = {"BANK_TRANSFER": "Bonifico"}

ORDER_STATUS = {
    "AWAITING_PAYMENT": ("In attesa di pagamento", "warning"),
    "PAID": ("Pagato", "success"),
    "CANCELLED": ("Annullato", "danger"),
}
CONTRACT_STATUS = {
    "DRAFT": "Bozza", "SUBMITTED": "Inviato", "DOCUMENTS_PENDING": "Documenti mancanti",
    "UNDER_REVIEW": "In revisione", "APPROVED": "Approvato", "PAYMENT_PENDING": "In attesa di pagamento",
    "PAID": "Pagato", "ACTIVATION_PENDING": "In attivazione", "ACTIVE": "Attivo", "SUSPENDED": "Sospeso",
    "CANCELLED": "Cessato", "EXPIRED": "Scaduto", "RENEWED": "Rinnovato", "REJECTED": "Respinto",
}
WALLET_TYPE_LABELS = {
    "ADMIN_CREDIT": "Accredito",
    "TRANSFER": "Trasferimento",
    "PURCHASE_DEBIT": "Pagamento con JavCash",
    "REVERSAL": "Storno",
}
WALLET_SOURCE_LABELS = {
    "MANUAL_ADMIN": "Ricarica manuale",
    "WELCOME_BONUS": "Omaggio di benvenuto",
    "ORDER_CASHBACK_BASE": "Cashback ordine",
    "ORDER_CASHBACK_BONUS": "Bonus 5% cashback ordine",
    "CONTRACT_CASHBACK": "Cashback contratto Jav",
}
INSTALMENT_SOURCE_LABELS = {
    "ADMIN": "Confermata dall'amministrazione",
}
PLAN_LABELS = {"FULL": "Soluzione unica", "INSTALMENTS_3": "3 rate mensili", "MONTHLY_12": "12 rate mensili"}


class DetailNotFoundError(Exception):
    pass


def _code(value: uuid.UUID) -> str:
    return str(value)[:8].upper()


def _euro(cents: int | None) -> str:
    if cents is None:
        return "—"
    return f"{cents / 100:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _fact(label: str, value: object, mono: bool = False) -> dict | None:
    if value is None or value == "":
        return None
    return {"label": label, "value": str(value), "mono": mono}


def _event(label: str, at: datetime | None, by: str | None = None, tone: str = "done") -> dict:
    # Some older columns are timestamp WITHOUT time zone and come back naive;
    # they were always written in UTC. Made aware here, or sorting a
    # timeline that mixes them with aware ones fails.
    if at is not None and at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    return {"label": label, "at": at, "by": by, "tone": tone}


async def _names(db: AsyncSession, organization_id: uuid.UUID, *user_ids: uuid.UUID | None) -> dict[uuid.UUID, str]:
    ids = {u for u in user_ids if u is not None}
    return await _resolve_display_names(db, organization_id=organization_id, user_ids=ids) if ids else {}


def _clean(detail: dict) -> dict:
    detail["facts"] = [f for f in detail.get("facts", []) if f is not None]
    detail["timeline"] = sorted(
        detail.get("timeline", []), key=lambda e: (e["at"] is None, e["at"] or datetime.max.replace(tzinfo=UTC))
    )
    return detail


async def build_detail(
    db: AsyncSession, *, organization_id: uuid.UUID, ref: str, owner_user_id: uuid.UUID | None
) -> dict:
    kind, _, raw_id = ref.partition(":")
    try:
        entity_id = uuid.UUID(raw_id)
    except ValueError as exc:
        raise DetailNotFoundError(ref) from exc
    builders = {
        "wallet": _wallet_detail,
        "order": _order_detail,
        "contract": _contract_detail,
    }
    builder = builders.get(kind)
    if builder is None:
        raise DetailNotFoundError(ref)
    detail = await builder(db, organization_id=organization_id, entity_id=entity_id, owner_user_id=owner_user_id)
    return _clean({"ref": f"{kind}:{entity_id}", **detail})


# --- JavCash -------------------------------------------------------------------


async def _wallet_detail(
    db: AsyncSession, *, organization_id: uuid.UUID, entity_id: uuid.UUID, owner_user_id: uuid.UUID | None
) -> dict:
    from app.domains.wallets.models import Wallet, WalletTransaction

    txn = await db.get(WalletTransaction, entity_id)
    if txn is None or txn.organization_id != organization_id:
        raise DetailNotFoundError()
    from_wallet = await db.get(Wallet, txn.from_wallet_id) if txn.from_wallet_id else None
    to_wallet = await db.get(Wallet, txn.to_wallet_id) if txn.to_wallet_id else None
    if owner_user_id is not None and owner_user_id not in {
        from_wallet.user_id if from_wallet else None, to_wallet.user_id if to_wallet else None
    }:
        raise DetailNotFoundError()
    names = await _names(
        db, organization_id, from_wallet.user_id if from_wallet else None,
        to_wallet.user_id if to_wallet else None, txn.actor_user_id,
    )
    outgoing = (
        from_wallet is not None and (owner_user_id is None and to_wallet is None or from_wallet.user_id == owner_user_id)
    )
    title = WALLET_SOURCE_LABELS.get(txn.source or "") or WALLET_TYPE_LABELS.get(txn.type, "Movimento JavCash")
    related = []
    txn_order_id = txn.reference_order_id
    if txn_order_id:
        related.append(f"order:{txn_order_id}")
    if txn.reference_contract_id:
        related.append(f"contract:{txn.reference_contract_id}")
    return {
        "kind": "WALLET",
        "title": title,
        "subtitle": txn.note,
        "status": "Registrato",
        "status_tone": "success",
        "amount_cents": txn.amount_cents,
        "currency": "JAVCASH",
        "direction": "out" if outgoing else "in",
        "facts": [
            _fact("Tipo", WALLET_TYPE_LABELS.get(txn.type, txn.type)),
            _fact("Origine", WALLET_SOURCE_LABELS.get(txn.source or "")),
            _fact("Da", f"{names.get(from_wallet.user_id, '—')} · {from_wallet.address}" if from_wallet else None),
            _fact("A", f"{names.get(to_wallet.user_id, '—')} · {to_wallet.address}" if to_wallet else None),
            _fact("Ordine", f"#{_code(txn_order_id)}") if txn_order_id else None,
            _fact("Contratto", f"#{_code(txn.reference_contract_id)}") if txn.reference_contract_id else None,
            _fact("Storna il movimento", _code(txn.reverses_transaction_id), mono=True) if txn.reverses_transaction_id else None,
            _fact("Nota", txn.note),
            _fact("ID movimento", txn.id, mono=True),
        ],
        "timeline": [
            _event("Movimento registrato sul wallet", txn.created_at,
                   by=names.get(txn.actor_user_id) if txn.actor_user_id else "Automatico"),
        ],
        "related_refs": related,
        "tab": "wallet",
        "order_id": txn_order_id,
        "contract_id": txn.reference_contract_id,
    }


# --- Ordini -----------------------------------------------------------------------


async def _order_detail(
    db: AsyncSession, *, organization_id: uuid.UUID, entity_id: uuid.UUID, owner_user_id: uuid.UUID | None
) -> dict:
    from app.domains.orders.models import Order

    order = await db.get(Order, entity_id)
    if order is None or order.organization_id != organization_id:
        raise DetailNotFoundError()
    if owner_user_id is not None and order.customer_user_id != owner_user_id:
        raise DetailNotFoundError()

    names = await _names(
        db, organization_id, order.customer_user_id, order.created_by_user_id, order.paid_by_user_id,
        order.cancelled_by_user_id,
    )
    version = await db.get(ProductVersion, order.product_version_id)
    cashback_surcharge = order.cashback_surcharge_cents or 0
    paid_cents = order.amount_cents - order.credit_applied_cents + cashback_surcharge
    status_label, tone = ORDER_STATUS.get(order.status, (order.status, "neutral"))
    timeline = [
        _event("Ordine creato", order.created_at, by=names.get(order.created_by_user_id)),
    ]
    if order.payment_proof_uploaded_at:
        timeline.append(_event(
            "Ricevuta del bonifico caricata", order.payment_proof_uploaded_at,
            by=order.payment_proof_original_filename,
        ))
    if order.paid_at:
        timeline.append(_event(
            "Pagamento confermato", order.paid_at,
            by=names.get(order.paid_by_user_id),
        ))
    elif order.status == "AWAITING_PAYMENT":
        timeline.append(_event("In attesa del pagamento", None, tone="pending"))
    if order.cashback_credited_at:
        timeline.append(_event("Cashback accreditato", order.cashback_credited_at))
    if order.cancelled_at:
        timeline.append(_event(
            "Ordine annullato", order.cancelled_at, by=names.get(order.cancelled_by_user_id), tone="warning"
        ))
    return {
        "kind": "ORDER",
        "title": version.name if version else "Ordine",
        "subtitle": f"Ordine #{_code(order.id)} · Shop",
        "status": status_label,
        "status_tone": tone,
        "amount_cents": order.amount_cents,
        "currency": "EUR",
        "direction": "out",
        "facts": [
            _fact("Cliente", names.get(order.customer_user_id)) if owner_user_id is None else None,
            _fact("Prezzo", _euro(order.amount_cents)),
            _fact("Pagato con JavCash", _euro(order.credit_applied_cents)) if order.credit_applied_cents else None,
            _fact("Supplemento cashback", _euro(cashback_surcharge)) if cashback_surcharge else None,
            _fact("Pagato in euro", _euro(paid_cents)),
            _fact("Metodo", PAYMENT_METHOD_LABELS.get(order.payment_method, order.payment_method)),
            _fact("Cashback richiesto", "Sì" if order.cashback_requested else None),
            _fact("Ricevuta bonifico", order.payment_proof_original_filename),
            _fact("Motivo annullamento", getattr(order, "cancellation_reason", None)),
            _fact("Nota", order.note),
            _fact("ID ordine", order.id, mono=True),
        ],
        "timeline": timeline,
        "related_refs": [],
        "tab": "orders",
        "order_id": order.id,
    }


# --- Contratti --------------------------------------------------------------------------


async def _contract_detail(
    db: AsyncSession, *, organization_id: uuid.UUID, entity_id: uuid.UUID, owner_user_id: uuid.UUID | None
) -> dict:
    from app.domains.contracts.models import Contract, ContractInstalment, ContractStatusHistory
    from app.domains.customers.models import Customer

    contract = await db.get(Contract, entity_id)
    if contract is None or contract.organization_id != organization_id:
        raise DetailNotFoundError()
    customer = await db.get(Customer, contract.customer_id)
    if owner_user_id is not None and (customer is None or customer.user_id != owner_user_id):
        raise DetailNotFoundError()
    version = await db.get(ProductVersion, contract.product_version_id) if contract.product_version_id else None
    instalments = list(
        (
            await db.execute(
                select(ContractInstalment)
                .where(ContractInstalment.contract_id == contract.id)
                .order_by(ContractInstalment.number)
            )
        ).scalars()
    )
    history = list(
        (
            await db.execute(
                select(ContractStatusHistory)
                .where(ContractStatusHistory.contract_id == contract.id)
                .order_by(ContractStatusHistory.created_at)
            )
        ).scalars()
    )
    names = await _names(
        db, organization_id, customer.user_id if customer else None,
        *[h.actor_user_id for h in history], *[i.confirmed_by_user_id for i in instalments],
    )
    paid = [i for i in instalments if i.status == "PAID"]
    status = CONTRACT_STATUS.get(contract.status, contract.status)
    tone = (
        "success" if contract.status in ("ACTIVE", "RENEWED")
        else "danger" if contract.status in ("REJECTED", "CANCELLED", "SUSPENDED")
        else "warning"
    )

    # The steps that matter for money and activation, not every hop of the
    # state machine (the automatic cascades would triple the list).
    milestones = {
        "SUBMITTED": "Contratto inviato",
        "UNDER_REVIEW": "Documenti completi, in revisione",
        "APPROVED": "Approvato dall'amministrazione",
        "ACTIVE": "Contratto attivo",
        "REJECTED": "Respinto",
        "SUSPENDED": "Sospeso",
        "CANCELLED": "Cessato",
        "RENEWED": "Rinnovato",
    }
    timeline = [_event("Contratto creato", contract.created_at)]
    for h in history:
        if h.to_status in milestones:
            timeline.append(_event(
                milestones[h.to_status], h.created_at,
                by=names.get(h.actor_user_id) if h.reason != "Automatico -- nessuna decisione separata richiesta" else "Automatico",
                tone="warning" if h.to_status in ("REJECTED", "SUSPENDED", "CANCELLED") else "done",
            ))
    for i in paid:
        timeline.append(_event(
            f"Pagamento {'' if i.instalments_total == 1 else f'rata {i.number}/{i.instalments_total} '}ricevuto · {_euro(i.amount_cents)}",
            i.paid_at,
            by=(INSTALMENT_SOURCE_LABELS.get(i.payment_source or "") or "")
            + (f" ({names.get(i.confirmed_by_user_id)})" if i.confirmed_by_user_id else ""),
        ))
    if contract.cashback_credited_at:
        timeline.append(_event("Cashback JavCash accreditato", contract.cashback_credited_at))
    next_due = next((i for i in instalments if i.status == "SCHEDULED"), None)
    if next_due is not None:
        timeline.append(_event(
            f"Prossima rata {next_due.number}/{next_due.instalments_total} · {_euro(next_due.amount_cents)} "
            f"prevista il {next_due.due_date.strftime('%d/%m/%Y')}",
            None, tone="pending",
        ))

    # Paid in rate, the contract costs the rate price.
    _, chosen_vat, chosen_gross = payment_plans.chosen_amounts(contract)
    return {
        "kind": "CONTRACT",
        "title": version.name if version else "Contratto Jav",
        "subtitle": f"Contratto #{_code(contract.id)} · pratica #{_code(contract.contract_request_id)}",
        "status": status,
        "status_tone": tone,
        "amount_cents": chosen_gross,
        "currency": "EUR",
        "direction": "out",
        "facts": [
            _fact("Cliente", names.get(customer.user_id) if customer and customer.user_id else None)
            if owner_user_id is None else None,
            _fact("Intestatario", " ".join(x for x in (contract.holder_first_name, contract.holder_last_name) if x)),
            _fact("Totale contratto", _euro(chosen_gross)),
            _fact("IVA", f"{contract.vat_rate}% · {_euro(chosen_vat)}") if chosen_vat else None,
            _fact("Modalità di pagamento", PLAN_LABELS.get(contract.payment_plan or "")),
            _fact("Pagato finora", f"{_euro(sum(i.amount_cents for i in paid))} · {len(paid)}/{len(instalments)} "
                  f"{'rate' if len(instalments) != 1 else 'pagamento'}") if instalments else None,
            _fact("Attivo dal", contract.activated_at.strftime("%d/%m/%Y") if contract.activated_at else None),
            _fact("Scadenza", contract.expires_at.strftime("%d/%m/%Y") if contract.expires_at else None),
            _fact("IBAN", contract.iban, mono=True),
            _fact("ID contratto", contract.id, mono=True),
        ],
        "timeline": timeline,
        "instalments": [
            {
                "number": i.number,
                "instalments_total": i.instalments_total,
                "due_date": i.due_date.isoformat(),
                "amount_cents": i.amount_cents,
                "status": i.status,
                "paid_at": i.paid_at,
                "source": INSTALMENT_SOURCE_LABELS.get(i.payment_source or ""),
                "confirmed_by": names.get(i.confirmed_by_user_id) if i.confirmed_by_user_id else None,
            }
            for i in instalments
        ],
        "related_refs": [],
        "tab": "contracts",
        "contract_id": contract.id,
    }
