"""Come si paga un contratto Jav: unica soluzione, 3 rate o 12 rate.

Contracts only. The Shop's own checkout (orders) is a separate flow and is
untouched by any of this -- an order is a purchase, a contract is a
subscription to a service, and merging the two would make both worse.

**Every payment is a bank transfer an administrator confirms.** The amount
comes from the breakdown frozen on the contract itself (`catalog/pricing.py`),
which already accounts for that customer's VAT: nothing here is ever priced
from what the browser sends.

**3 rate and 12 rate are the same mechanism**: one transfer per instalment,
each confirmed by an administrator, the first one with the transfer that
starts the plan -- they differ only in N, and split the same total: the rate
price (monthly price x 12), which is not the one-go price (see
plan_gross_cents). Jav is splitting its own invoice, not lending anything.
"""

from dataclasses import dataclass

PLAN_FULL = "FULL"
PLAN_INSTALMENTS_3 = "INSTALMENTS_3"
PLAN_MONTHLY_12 = "MONTHLY_12"


@dataclass(frozen=True)
class PaymentPlan:
    key: str
    #: 1 means a single transfer; anything higher is one transfer per
    #: instalment, a month apart.
    instalments: int
    label: str
    description: str


PAYMENT_PLANS: tuple[PaymentPlan, ...] = (
    PaymentPlan(
        key=PLAN_FULL,
        instalments=1,
        label="Soluzione unica",
        description="Un solo bonifico per l'intero importo.",
    ),
    PaymentPlan(
        key=PLAN_INSTALMENTS_3,
        instalments=3,
        label="3 rate mensili",
        description="Il primo bonifico oggi, gli altri due uno al mese.",
    ),
    PaymentPlan(
        key=PLAN_MONTHLY_12,
        instalments=12,
        label="12 rate mensili",
        description="Il primo bonifico oggi, gli altri undici uno al mese.",
    ),
)


def plan_by_key(key: str | None) -> PaymentPlan | None:
    return next((p for p in PAYMENT_PLANS if p.key == key), None)


@dataclass(frozen=True)
class PlanBreakdown:
    """Exactly what the customer will be asked to transfer, and when.

    Every instalment is the SAME amount, and an amount rarely divides evenly
    by 3 or 12 -- so the instalment is rounded to the cent and `total_cents`
    is `instalment x instalments`, which can differ from the contract by a
    few cents in either direction (`rounding_difference_cents`, at most 6
    cents for 12 instalments).

    That difference is **shown to the customer next to each option** rather
    than hidden: one transfer amount the customer can repeat every month is
    simpler than a different last one, and silently rounding up would
    overcharge without saying so.
    """

    plan: PaymentPlan
    #: What the contract itself says is owed.
    contract_total_cents: int
    #: What this plan will actually collect: instalment x instalments.
    total_cents: int
    instalment_cents: int
    #: total_cents - contract_total_cents. Zero whenever it divides evenly,
    #: which it does for every price in the catalog.
    rounding_difference_cents: int


def breakdown_for(plan: PaymentPlan, total_cents: int) -> PlanBreakdown:
    """`total_cents` split into the plan's instalments. Paying by bank
    transfer never carries a discount (business decision), so a single
    payment is the total itself."""
    if plan.instalments <= 1:
        return PlanBreakdown(
            plan=plan,
            contract_total_cents=total_cents,
            total_cents=total_cents,
            instalment_cents=total_cents,
            rounding_difference_cents=0,
        )
    # Half-up on the cent, the same rounding the VAT calculation uses.
    instalment = (total_cents * 2 + plan.instalments) // (plan.instalments * 2)
    plan_total = instalment * plan.instalments
    return PlanBreakdown(
        plan=plan,
        contract_total_cents=total_cents,
        total_cents=plan_total,
        instalment_cents=instalment,
        rounding_difference_cents=plan_total - total_cents,
    )


def plan_gross_cents(plan: PaymentPlan, contract) -> int:
    """What the whole contract costs, VAT included, paid with `plan`.

    In one go, the one-go price (`gross_amount_cents`); in rate
    (3 or 12, the same total), the rate price frozen next to it
    (`instalments_gross_amount_cents` = monthly price x 12 + VAT) -- 149 €
    against 12 x 18,30 €. A contract with no rate price (a product without
    one) splits the one-go price.

    Every amount of a contract that depends on the plan -- the options
    offered, the transfer amounts, the instalment schedule, the cashback, the
    commission preview -- goes through here, never straight to
    gross_amount_cents."""
    if plan.instalments > 1 and getattr(contract, "instalments_gross_amount_cents", None):
        return int(contract.instalments_gross_amount_cents)
    return int(contract.gross_amount_cents or 0)


def paid_gross_cents(contract) -> int:
    """What a contract costs with the plan it was paid (or is being paid)
    with; the one-go price while no plan is chosen."""
    plan = plan_by_key(getattr(contract, "payment_plan", None))
    if plan is None:
        return int(contract.gross_amount_cents or 0)
    return plan_gross_cents(plan, contract)


def chosen_amounts(contract) -> tuple[int | None, int | None, int | None]:
    """(net, VAT, gross) of the contract with the plan it chose -- the rate
    price once it chose rate and has one, the one-go price otherwise. For
    documents and accounting, which print one "Totale"."""
    plan = plan_by_key(getattr(contract, "payment_plan", None))
    if plan is not None and plan.instalments > 1 and getattr(contract, "instalments_gross_amount_cents", None):
        return (
            contract.instalments_net_amount_cents,
            contract.instalments_vat_amount_cents,
            contract.instalments_gross_amount_cents,
        )
    return contract.net_amount_cents, contract.vat_amount_cents, contract.gross_amount_cents


def contract_breakdown(plan: PaymentPlan, contract) -> PlanBreakdown:
    """What a contract that chose (or is choosing) `plan` is asked to pay."""
    return breakdown_for(plan, plan_gross_cents(plan, contract))
