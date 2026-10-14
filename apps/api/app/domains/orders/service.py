import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import utcnow
from app.core.email import send_html_email_best_effort
from app.core.email_templates import render_email
from app.domains.catalog.models import Product, ProductVersion
from app.domains.customers.models import Company, Customer, CustomerProfile
from app.domains.customers.service import display_name_for
from app.domains.network.models import AgentProfile
from app.domains.notifications import service as notifications_service
from app.domains.orders.models import ORDER_PAYMENT_METHODS, Order
from app.domains.organizations import service as organizations_service
from app.domains.users.models import User
from app.domains.wallets import service as wallets_service


class OrderError(Exception):
    pass


class ProductNotEligibleError(OrderError):
    pass


class InvalidCreditAmountError(OrderError):
    pass


class InvalidOrderStateError(OrderError):
    pass


class InvalidPaymentMethodError(OrderError):
    pass


class PaymentMethodNotAvailableError(OrderError):
    pass


class PaymentProofError(OrderError):
    """Covers both a bad file (unsupported type / too large) and uploading a
    proof to an order it doesn't apply to (not BANK_TRANSFER, or no longer
    AWAITING_PAYMENT)."""


class CashbackNotAvailableError(OrderError):
    """Raised when cashback_requested=True but either the product doesn't
    offer it (ProductVersion.cashback_enabled is False) or there's no real
    new payment for it to apply to (the wallet credit already covers the
    whole price)."""


class InvalidOtpError(OrderError):
    """Raised when self-checkout spends existing wallet JavCash
    (credit_applied_cents > 0) without a valid, still-fresh OTP code -- see
    create_order's otp_code parameter and
    auth/service.py::WALLET_CREDIT_SPEND_OTP_PURPOSE."""


# Fixed, "flat, admin can't override it per product". What the customer
# pays extra, on top of whatever they actually owe in new money, to opt into
# "riscuoti subito cashback" on an eligible order -- see
# _credit_order_cashback() below for where it's paid back.
ORDER_CASHBACK_PERCENTAGE = 5


async def _get_sellable_product_version(
    db: AsyncSession, *, organization_id: uuid.UUID, product_version_id: uuid.UUID
) -> tuple[ProductVersion, Product]:
    version = await db.get(ProductVersion, product_version_id)
    if version is None:
        raise ProductNotEligibleError("Product version not found")
    product = await db.get(Product, version.product_id)
    if product is None or product.organization_id != organization_id:
        raise ProductNotEligibleError("Product version not found")
    if product.category == "INTERNAL":
        raise ProductNotEligibleError(
            "I prodotti Interno Jav si acquistano come contratto, non come ordine -- vedi POST /contracts."
        )
    return version, product


def max_creditable_cents(*, amount_cents: int, credit_discount_percentage: int) -> int:
    return round(amount_cents * credit_discount_percentage / 100)


async def get_available_payment_methods(db: AsyncSession, *, organization_id: uuid.UUID) -> dict:
    """Gates what a checkout screen may even offer for the residual --
    both create_order() (server-side enforcement) and every quote endpoint
    (so the UI never shows a button that would just fail) read this."""
    return {
        "bank_transfer": await organizations_service.is_bank_transfer_configured(db, organization_id=organization_id),
    }


async def get_quote(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID, product_version_id: uuid.UUID
) -> dict:
    version, _product = await _get_sellable_product_version(
        db, organization_id=organization_id, product_version_id=product_version_id
    )
    wallet = await wallets_service.get_wallet_by_user_id(
        db, organization_id=organization_id, user_id=customer_user_id
    )
    methods = await get_available_payment_methods(db, organization_id=organization_id)
    return {
        "product_version_id": version.id,
        "product_name": version.name,
        "amount_cents": version.base_price_cents,
        "credit_discount_percentage": version.credit_discount_percentage,
        "max_creditable_cents": max_creditable_cents(
            amount_cents=version.base_price_cents, credit_discount_percentage=version.credit_discount_percentage
        ),
        "customer_wallet_balance_cents": wallet.balance_cents if wallet else 0,
        "bank_transfer_available": methods["bank_transfer"],
        "cashback_available": version.cashback_enabled,
        "cashback_percentage": ORDER_CASHBACK_PERCENTAGE,
    }


async def _resolve_display_name(db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID) -> str:
    """Promoter display name, then customer name, then email -- a private
    copy rather than an import of the wallets domain's batch helper, which
    isn't meant to be used across domains."""
    agent = (
        await db.execute(
            select(AgentProfile.display_name).where(
                AgentProfile.organization_id == organization_id, AgentProfile.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if agent:
        return agent

    customer = (
        await db.execute(
            select(Customer).where(Customer.organization_id == organization_id, Customer.user_id == user_id)
        )
    ).scalar_one_or_none()
    if customer is not None:
        profile = await db.get(CustomerProfile, customer.id)
        company = await db.get(Company, customer.id)
        name = display_name_for(customer.kind, profile, company)
        if name != "—":
            return name

    user = await db.get(User, user_id)
    return user.email if user else "—"


async def to_read_dict(db: AsyncSession, order: Order) -> dict:
    version = await db.get(ProductVersion, order.product_version_id)
    customer_name = await _resolve_display_name(
        db, organization_id=order.organization_id, user_id=order.customer_user_id
    )
    return {
        "id": order.id,
        "customer_user_id": order.customer_user_id,
        "customer_display_name": customer_name,
        "product_version_id": order.product_version_id,
        "product_name": version.name if version else "—",
        "product_image_url": version.image_url if version else None,
        "created_by_user_id": order.created_by_user_id,
        "amount_cents": order.amount_cents,
        "credit_applied_cents": order.credit_applied_cents,
        # Includes the cashback surcharge (0 when cashback wasn't requested)
        # -- this is the actual amount owed in new money for this order, via
        # bank transfer.
        "residual_amount_cents": order.amount_cents - order.credit_applied_cents + order.cashback_surcharge_cents,
        "cashback_requested": order.cashback_requested,
        "cashback_surcharge_cents": order.cashback_surcharge_cents,
        "cashback_credited_at": order.cashback_credited_at,
        "status": order.status,
        "payment_method": order.payment_method,
        "payment_proof_uploaded_at": order.payment_proof_uploaded_at,
        "note": order.note,
        "paid_at": order.paid_at,
        "cancelled_at": order.cancelled_at,
        "cancellation_reason": order.cancellation_reason,
        "created_at": order.created_at,
    }


async def hydrate(db: AsyncSession, orders: list[Order]) -> list[dict]:
    return [await to_read_dict(db, o) for o in orders]


async def create_order(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_user_id: uuid.UUID,
    product_version_id: uuid.UUID,
    credit_applied_cents: int,
    actor_user_id: uuid.UUID,
    payment_method: str = "BANK_TRANSFER",
    note: str | None = None,
    cashback_requested: bool = False,
    otp_code: str | None = None,
    require_otp_for_credit_spend: bool = True,
) -> Order:
    """require_otp_for_credit_spend defaults to True (self-checkout, POST
    /orders/mine) -- spending existing wallet JavCash needs a fresh emailed
    OTP so a stolen session token alone can't drain a wallet. The staff
    endpoint (POST /orders, wallet.manage-gated) passes False: an admin
    applying a customer's credit on their behalf is already an audited,
    permissioned action, and the OTP would go to the CUSTOMER's inbox, not
    the admin's -- requiring it there would make the admin flow unusable,
    not safer."""
    version, _product = await _get_sellable_product_version(
        db, organization_id=organization_id, product_version_id=product_version_id
    )
    amount_cents = version.base_price_cents
    cap = max_creditable_cents(amount_cents=amount_cents, credit_discount_percentage=version.credit_discount_percentage)
    if credit_applied_cents < 0 or credit_applied_cents > cap:
        raise InvalidCreditAmountError(
            f"credit_applied_cents must be between 0 and {cap} for this product ({version.credit_discount_percentage}% of {amount_cents})"
        )

    if credit_applied_cents > 0 and require_otp_for_credit_spend:
        from app.domains.auth import service as auth_service

        if not otp_code or not await auth_service.verify_spend_code(
            db, user_id=customer_user_id, code=otp_code
        ):
            raise InvalidOtpError("Codice o PIN di conferma mancante, non valido o scaduto.")

    # residual_before_cashback is the actual "100%" base this order owes in
    # new money before any cashback surcharge -- also what a returned
    # cashback credit is computed FROM (see _credit_order_cashback), never
    # the pre-credit-discount amount_cents. Crediting cashback off a higher
    # base than what was genuinely paid new would let a customer manufacture
    # credit from credit already spent -- exactly the invariant this
    # wallet's whole design exists to prevent.
    residual_before_cashback = amount_cents - credit_applied_cents
    cashback_surcharge_cents = 0
    if cashback_requested:
        if not version.cashback_enabled:
            raise CashbackNotAvailableError("Questo prodotto non consente il cashback.")
        if residual_before_cashback <= 0:
            raise CashbackNotAvailableError(
                "Il cashback richiede un pagamento residuo maggiore di zero -- il credito wallet copre già l'intero importo."
            )
        cashback_surcharge_cents = round(residual_before_cashback * ORDER_CASHBACK_PERCENTAGE / 100)

    total_to_charge = residual_before_cashback + cashback_surcharge_cents

    # Only matters when something is actually going to be charged -- if
    # credit alone covers the price (and no cashback was requested, which
    # would be impossible in that case anyway), payment_method is stored
    # as-given but never acted upon (the order skips straight to PAID
    # below), so an unavailable/garbage value there shouldn't block a
    # 100%-credit order.
    if total_to_charge > 0:
        if payment_method not in ORDER_PAYMENT_METHODS:
            raise InvalidPaymentMethodError(f"payment_method must be one of {ORDER_PAYMENT_METHODS}")
        available = await get_available_payment_methods(db, organization_id=organization_id)
        if payment_method == "BANK_TRANSFER" and not available["bank_transfer"]:
            raise PaymentMethodNotAvailableError("Il pagamento con bonifico non è configurato.")

    wallet = None
    if credit_applied_cents > 0:
        # Checked BEFORE the order row is ever created, not just left to the
        # atomic debit's own CAS guard below -- creating the order first and
        # rolling back on a failed debit would work too, but an explicit
        # rollback() here would conflict with the SAVEPOINT-based session
        # wrapping the test suite's `db` fixture uses (same reasoning as the
        # identical-in-spirit comment on debit_and_transfer's insufficient-
        # balance path). This pre-check can't catch a same-instant race with
        # another debit against the same wallet -- that rarer case is still
        # caught correctly by the CAS in debit_wallet_for_purchase, just
        # without this function's own guarantee that no Order row survives
        # it; an accepted, documented trade-off, not a bug.
        wallet = await wallets_service.get_or_create_wallet(
            db, organization_id=organization_id, user_id=customer_user_id
        )
        if wallet.balance_cents < credit_applied_cents:
            raise wallets_service.InsufficientBalanceError("Insufficient balance")

    order = Order(
        organization_id=organization_id,
        customer_user_id=customer_user_id,
        product_version_id=product_version_id,
        created_by_user_id=actor_user_id,
        amount_cents=amount_cents,
        credit_applied_cents=credit_applied_cents,
        cashback_requested=cashback_requested,
        cashback_surcharge_cents=cashback_surcharge_cents,
        status="AWAITING_PAYMENT",
        payment_method=payment_method,
        note=note,
    )
    db.add(order)
    await db.flush()  # assigns order.id, no commit yet

    # Same "staff sees every new operational event" convention as
    # contracts/service.py::create_contract's CONTRACT_CREATED notification --
    # added before whichever commit below actually happens, so it lands in
    # the same transaction as the order row itself.
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="ORDER_CREATED", entity_type="order", entity_id=order.id,
        title=f"Nuovo ordine: {version.name}", body=f"{amount_cents / 100:.2f} EUR -- {payment_method}",
        exclude_user_id=actor_user_id,
    )

    if credit_applied_cents > 0:
        assert wallet is not None
        if total_to_charge == 0:
            order.status = "PAID"
            order.paid_by_user_id = actor_user_id
            order.paid_at = utcnow()
        # debit_wallet_for_purchase() commits -- this single commit captures
        # the order row (including the PAID transition above, if any) AND
        # the debit transaction together, atomically.
        debit_txn = await wallets_service.debit_wallet_for_purchase(
            db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=credit_applied_cents,
            reference_order_id=order.id, actor_user_id=actor_user_id,
            note=f"Ordine {version.name}", idempotency_key=f"order:{order.id}:credit",
        )
        order.credit_debit_transaction_id = debit_txn.id
        await db.commit()
        await db.refresh(order)
    else:
        await db.commit()
        await db.refresh(order)

    await _send_order_confirmation_email(db, organization_id=organization_id, order=order, version=version)
    return order


async def _send_order_confirmation_email(
    db: AsyncSession, *, organization_id: uuid.UUID, order: Order, version: ProductVersion
) -> None:
    """Best-effort, fires after the order is already committed -- an SMTP
    hiccup here must never undo an order that has already been created.
    Explains exactly how to pay: the IBAN and the causale for the bank
    transfer."""
    user = await db.get(User, order.customer_user_id)
    if user is None:
        return

    residual_cents = order.amount_cents - order.credit_applied_cents + order.cashback_surcharge_cents
    order_code = str(order.id)[:8].upper()
    order_code_line = f"<p>Numero ordine: <strong>#{order_code}</strong></p>"
    cashback_line = (
        f"<p>Include il {ORDER_CASHBACK_PERCENTAGE}% per il cashback che riceverai come JavCash "
        "non appena il pagamento sarà confermato.</p>"
        if order.cashback_requested else ""
    )

    if order.status == "PAID":
        heading = "Ordine confermato"
        body_html = (
            order_code_line
            + f"<p>Il tuo ordine per <strong>{version.name}</strong> è confermato.</p>"
            f"<p>Totale: {order.amount_cents / 100:.2f} &euro;"
            + (f" (di cui {order.credit_applied_cents / 100:.2f} JavCash)" if order.credit_applied_cents else "")
            + "</p><p>Non è richiesto alcun pagamento aggiuntivo.</p>"
        )
    else:
        bank_settings = await organizations_service.get_settings(db, organization_id=organization_id)
        iban = bank_settings.get("bank_iban")
        heading = "Completa il pagamento del tuo ordine"
        body_html = (
            order_code_line
            + f"<p>Il tuo ordine per <strong>{version.name}</strong> è stato registrato.</p>"
            f"<p>Da pagare tramite bonifico: <strong>{residual_cents / 100:.2f} &euro;</strong>"
            + (f" (dopo {order.credit_applied_cents / 100:.2f} JavCash già applicati)" if order.credit_applied_cents else "")
            + "</p>"
            + cashback_line
        )
        if iban:
            body_html += (
                f"<p><strong>IBAN:</strong> {iban}<br>"
                f"<strong>Intestatario:</strong> {bank_settings.get('bank_account_holder') or 'Jav'}<br>"
                f"<strong>Causale:</strong> Ordine {order_code}</p>"
            )
            if bank_settings.get("bank_transfer_instructions"):
                body_html += f"<p>{bank_settings['bank_transfer_instructions']}</p>"
        else:
            body_html += "<p>Contatta l'amministrazione per le coordinate bancarie.</p>"

    html = render_email(
        preheader=f"Riepilogo del tuo ordine -- {version.name}",
        heading=heading,
        body_html=body_html,
    )
    send_html_email_best_effort(
        context=f"Order confirmation email (order={order.id})",
        to=user.email,
        subject=f"Conferma ordine - {version.name} - Jav",
        html_body=html,
        text_body=f"{heading}: {version.name}, totale {order.amount_cents / 100:.2f} EUR.",
    )


async def _send_order_paid_email(
    db: AsyncSession, *, order: Order, version: ProductVersion | None
) -> None:
    """Best-effort, fires after the order is already committed PAID -- the
    second of the two customer emails a product order gets (the first is
    _send_order_confirmation_email's "ordine ricevuto" at creation, which
    deliberately never claims the payment itself is done), sent once an
    admin confirms the bank transfer (confirm_payment)."""
    user = await db.get(User, order.customer_user_id)
    if user is None:
        return

    method_label = "Bonifico bancario"
    product_name = version.name if version else "un prodotto"
    paid_at_label = order.paid_at.strftime("%d/%m/%Y %H:%M") if order.paid_at else "-"
    # What actually landed as new money on THIS payment -- not the raw
    # product price, which credit/cashback can both make different from what
    # was really charged (see to_read_dict's residual_amount_cents).
    amount_paid_cents = order.amount_cents - order.credit_applied_cents + order.cashback_surcharge_cents
    cashback_credited_line = ""
    if order.cashback_requested and order.cashback_credited_at:
        total_cashback_cents = (order.amount_cents - order.credit_applied_cents) + order.cashback_surcharge_cents
        cashback_credited_line = (
            f"<p>Hai ricevuto <strong>{total_cashback_cents / 100:.2f} JavCash</strong> sul tuo wallet.</p>"
        )
    body_html = (
        "<p>Il pagamento del tuo ordine &egrave; stato confermato.</p>"
        f"<p><strong>Numero ordine:</strong> #{str(order.id)[:8].upper()}<br>"
        f"<strong>Prodotto:</strong> {product_name}<br>"
        f"<strong>Importo pagato:</strong> {amount_paid_cents / 100:.2f} &euro;<br>"
        f"<strong>Metodo di pagamento:</strong> {method_label}<br>"
        "<strong>Stato:</strong> Pagato<br>"
        f"<strong>Data:</strong> {paid_at_label}</p>"
        + cashback_credited_line
    )
    html = render_email(
        preheader="Pagamento completato con successo",
        heading="Pagamento completato con successo",
        body_html=body_html,
        cta_label="Vai ai miei ordini",
        cta_url=f"{get_settings().public_app_base_url}/customer?tab=orders",
    )
    send_html_email_best_effort(
        context=f"Order-paid email (order={order.id})",
        to=user.email,
        subject=f"Pagamento confermato - Ordine {str(order.id)[:8]} - Jav",
        html_body=html,
        text_body=(
            f"Pagamento completato con successo. Ordine {order.id}, {product_name}, "
            f"{order.amount_cents / 100:.2f} EUR, {method_label}."
        ),
    )


async def get_org_scoped(db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID) -> Order | None:
    order = await db.get(Order, order_id)
    if order is None or order.organization_id != organization_id:
        return None
    return order


async def get_owned(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID, order_id: uuid.UUID
) -> Order | None:
    """Ownership-scoped lookup -- backs every customer-facing "my order"
    action (payment-proof upload and download) so a customer can never touch
    someone else's order by guessing its id."""
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None or order.customer_user_id != customer_user_id:
        return None
    return order


async def list_orders(
    db: AsyncSession, *, organization_id: uuid.UUID, status_filter: str | None = None
) -> list[Order]:
    stmt = select(Order).where(Order.organization_id == organization_id)
    if status_filter:
        stmt = stmt.where(Order.status == status_filter)
    stmt = stmt.order_by(Order.created_at.desc())
    return list((await db.execute(stmt)).scalars().all())


async def list_orders_for_customer(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID
) -> list[Order]:
    stmt = (
        select(Order)
        .where(Order.organization_id == organization_id, Order.customer_user_id == customer_user_id)
        .order_by(Order.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def _credit_order_cashback(
    db: AsyncSession, *, organization_id: uuid.UUID, order: Order, version: ProductVersion | None,
    actor_user_id: uuid.UUID | None,
) -> None:
    """The other half of "riscuoti subito cashback": once an order that
    opted in reaches PAID (bank transfer admin-confirmed), credits the
    customer's wallet with exactly what they just paid new for this order
    -- the pre-surcharge residual (100%) plus the surcharge itself (the 5%
    bonus) -- as two separate JavCash rows, so the ledger always shows the
    split explicitly.
    Never more than that: the credited total is always <= what genuinely
    landed as real revenue on this exact order, so this can never manufacture
    credit out of credit already spent (see create_order's
    residual_before_cashback comment for the same invariant enforced at the
    other end).

    Idempotent two ways at once: the guard below (cashback_credited_at is
    only ever set once) and, independently, credit_wallet()'s own
    idempotency-key dedup (derived from the order id, never client-supplied)
    -- either alone would be enough to make a retried confirmation a
    no-op, but there is no reason not to have both."""
    if not order.cashback_requested or order.cashback_credited_at is not None:
        return
    base_cents = order.amount_cents - order.credit_applied_cents
    bonus_cents = order.cashback_surcharge_cents
    if base_cents <= 0 or bonus_cents <= 0:
        # Should be unreachable (create_order already refuses cashback with
        # no real residual to reward) -- defensive, not a real code path.
        return

    product_name = version.name if version else "un prodotto"
    wallet = await wallets_service.get_or_create_wallet(
        db, organization_id=organization_id, user_id=order.customer_user_id
    )
    await wallets_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=base_cents,
        type_="ADMIN_CREDIT", actor_user_id=actor_user_id, source="ORDER_CASHBACK_BASE",
        reference_order_id=order.id, note=f"Cashback ordine {product_name}",
        idempotency_key=f"order:{order.id}:cashback-base",
    )
    await wallets_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=bonus_cents,
        type_="ADMIN_CREDIT", actor_user_id=actor_user_id, source="ORDER_CASHBACK_BONUS",
        reference_order_id=order.id, note=f"Bonus {ORDER_CASHBACK_PERCENTAGE}% cashback ordine {product_name}",
        idempotency_key=f"order:{order.id}:cashback-bonus",
    )
    order.cashback_credited_at = utcnow()


async def confirm_payment(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID, actor_user_id: uuid.UUID
) -> Order:
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None:
        raise OrderError("Order not found")
    if order.status != "AWAITING_PAYMENT":
        raise InvalidOrderStateError(f"Cannot confirm payment for an order in status {order.status}")

    order.status = "PAID"
    order.paid_by_user_id = actor_user_id
    order.paid_at = utcnow()

    version = await db.get(ProductVersion, order.product_version_id)
    await notifications_service.notify_user(
        db, organization_id=organization_id, user_id=order.customer_user_id, type_="ORDER_PAID",
        entity_type="order", entity_id=order.id,
        title=f"Il tuo ordine per {version.name if version else 'un prodotto'} è confermato",
        body=None,
    )
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="ORDER_PAID", entity_type="order", entity_id=order.id,
        title=f"Bonifico confermato: {version.name if version else 'ordine'}",
        body=f"{order.amount_cents / 100:.2f} EUR", exclude_user_id=actor_user_id,
    )
    # credit_wallet() (called from here) commits internally -- this captures
    # the PAID transition and notifications above together with the
    # cashback credit rows, atomically, same pattern as create_order's own
    # debit_wallet_for_purchase call.
    await _credit_order_cashback(db, organization_id=organization_id, order=order, version=version, actor_user_id=actor_user_id)
    await db.commit()
    await db.refresh(order)
    await _send_order_paid_email(db, order=order, version=version)
    return order


async def cancel_order(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID, reason: str, actor_user_id: uuid.UUID
) -> Order:
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None:
        raise OrderError("Order not found")
    if order.status != "AWAITING_PAYMENT":
        raise InvalidOrderStateError(f"Cannot cancel an order in status {order.status}")

    if order.credit_debit_transaction_id is not None:
        # Reverses the exact PURCHASE_DEBIT row -- see
        # wallets/service.py::reverse_transaction's PURCHASE_DEBIT handling.
        await wallets_service.reverse_transaction(
            db, organization_id=organization_id, transaction_id=order.credit_debit_transaction_id,
            actor_user_id=actor_user_id, reason=f"Ordine annullato: {reason}",
            idempotency_key=f"order:{order.id}:cancel-refund",
        )

    order.status = "CANCELLED"
    order.cancelled_by_user_id = actor_user_id
    order.cancelled_at = utcnow()
    order.cancellation_reason = reason
    await db.commit()
    await db.refresh(order)
    return order


async def upload_payment_proof(
    db: AsyncSession, *, organization_id: uuid.UUID, order: Order,
    file_bytes: bytes, content_type: str, original_filename: str, actor_user_id: uuid.UUID,
) -> Order:
    """Attaches a customer-uploaded photo/PDF of a bank transfer receipt to
    an AWAITING_PAYMENT/BANK_TRANSFER order -- purely advisory extra
    evidence for whoever clicks "Conferma bonifico ricevuto" in
    admin-orders-panel.tsx; never changes order.status by itself. Reuses
    core/storage.py's private documents bucket directly -- no reason to
    route this through the `documents` domain, whose contract_id is NOT
    NULL by design."""
    from app.core.storage import UploadValidationError
    from app.core.storage import upload_document as storage_upload_document

    if order.status != "AWAITING_PAYMENT":
        raise PaymentProofError(f"Cannot attach a payment proof to an order in status {order.status}")
    if order.payment_method != "BANK_TRANSFER":
        raise PaymentProofError("La prova di pagamento è prevista solo per gli ordini pagati con bonifico.")

    try:
        storage_key = storage_upload_document(
            file_bytes=file_bytes, content_type=content_type,
            key_prefix=f"order-payment-proofs/{order.customer_user_id}",
        )
    except UploadValidationError as exc:
        raise PaymentProofError(str(exc)) from exc

    order.payment_proof_storage_key = storage_key
    order.payment_proof_original_filename = original_filename
    order.payment_proof_uploaded_at = utcnow()

    version = await db.get(ProductVersion, order.product_version_id)
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="ORDER_PAYMENT_PROOF_UPLOADED", entity_type="order", entity_id=order.id,
        title=f"Prova di pagamento caricata: {version.name if version else 'ordine'}",
        body=None, exclude_user_id=actor_user_id,
    )
    await db.commit()
    await db.refresh(order)
    return order


PAYMENT_PROOF_PRESIGNED_URL_TTL_SECONDS = 300


def presigned_payment_proof_url(order: Order) -> str:
    from app.core.storage import generate_presigned_document_url as storage_presign_document

    assert order.payment_proof_storage_key is not None  # guaranteed by the router's own check
    return storage_presign_document(
        storage_key=order.payment_proof_storage_key, expires_in_seconds=PAYMENT_PROOF_PRESIGNED_URL_TTL_SECONDS
    )
