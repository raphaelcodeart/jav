"""La pratica di attivazione: più punti di fornitura, un contratto per punto,
un pagamento solo.

Business rule (Session 52), as the business put it: a customer with ten POD
is ten contracts -- ten for the customer, ten for the promoter, each with its
own package, its own approval, its own instalments and its own commissions --
but the customer fills in who they are once, uploads their identity once,
chooses a package for each point, and pays once.

The flow a pratica follows (reshaped in Session 53, as the business asked):

1. Everything once, at the start: holder (nome, cognome, email, PEC, IBAN),
   supply address, and "quanti POD hai?". The pratica is created DRAFT with
   that many points already there -- each a real DRAFT contract with its own
   supply point, so a half-finished pratica survives a closed browser. No
   POD/PDR code is asked.
2. Shared documents (identity, fiscal code...), once, on the pratica.
3. For each POD, the contract to activate. The package decides whether the
   point is luce or gas, and its price is frozen on the contract then.
4. Submit: every point leaves DRAFT together and enters the ordinary review
   flow. From here on each contract lives its own life.
5. Payment (customer only): one Checkout Session for every payable contract
   in the pratica -- one line each, or one subscription with one item each.
   See payments/service.py::create_checkout_session_for_request.

Nothing here computes a commission or activates anything: that stays where
it has always been, in contracts/service.py::transition_contract, one
contract at a time.
"""

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import fiscal_code
from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.catalog import pricing
from app.domains.catalog.models import Product, ProductVersion
from app.domains.contracts import payment_plans
from app.domains.contracts import service as contract_service
from app.domains.contracts.models import (
    Contract,
    ContractInstalment,
    ContractRequest,
    ContractRequestCheckout,
)
from app.domains.customers.models import Address, Company, Customer, CustomerProfile, SupplyPoint
from app.domains.network.models import AgentProfile
from app.domains.notifications import service as notifications_service

#: A condominium can have dozens of meters; beyond this it is a job for the
#: back office, not a web form.
MAX_POINTS_PER_REQUEST = 50

#: Stripe's own ceiling on the items of one subscription. An instalment plan
#: puts one item per contract, so a pratica with more payable contracts than
#: this can only be paid in one go (or split into two pratiche).
MAX_SUBSCRIPTION_LINES = 20


class ContractRequestError(Exception):
    pass


#: The two kinds of point a pratica asks for up front. A POD is an
#: electricity meter and takes only luce packages; a PDR is a gas meter and
#: takes only gas packages. The kind is fixed when the point is created
#: ("quanti POD? quanti PDR?"), so the package list can be filtered before
#: anything is chosen -- a gas offer on a POD is not a choice to correct
#: later, it is a contract that cannot exist.
POD = "ELECTRICITY"
PDR = "GAS"
POINT_KIND_LABELS = {POD: "POD", PDR: "PDR"}


def point_kind_label(energy_type: str | None) -> str:
    return POINT_KIND_LABELS.get(energy_type or "", "POD")


def _check_package_fits_point(supply_point: SupplyPoint | None, product: Product, version: ProductVersion) -> None:
    """A typed point accepts only packages of its own energy. An untyped
    point (drafts from before PDR existed) still accepts anything, and the
    package types it, as it always did."""
    if supply_point is None or supply_point.energy_type is None:
        return
    if product.energy_type != supply_point.energy_type:
        kind = point_kind_label(supply_point.energy_type)
        wanted = "luce" if supply_point.energy_type == POD else "gas"
        raise ContractRequestError(
            f"“{version.name}” non si può attivare su un {kind}: su un {kind} vanno solo offerte {wanted}."
        )


@dataclass(frozen=True)
class AddressData:
    street: str
    city: str
    province: str
    postal_code: str


@dataclass(frozen=True)
class HolderData:
    first_name: str
    last_name: str
    email: str
    pec: str | None
    iban: str | None
    address: AddressData
    #: Session 85: PRIVATE or a business kind; None = the customer's kind.
    kind: str | None = None
    #: A business pratica only: ragione sociale and the legal
    #: representative's fiscal code (first/last name above are theirs).
    company_name: str | None = None
    legal_rep_fiscal_code: str | None = None
    #: Session 89: a private holder's fiscal code; the birth date and place
    #: (Belfiore code) of whoever is named above, holder or legal rep.
    fiscal_code: str | None = None
    birth_date: date | None = None
    birth_place_code: str | None = None


#: What the pratica's data form may say the contracts are for.
PRATICA_KINDS = frozenset({"PRIVATE", "SOLE_PROPRIETOR", "COMPANY", "CONDOMINIUM"})


def pratica_kind(request: ContractRequest, customer: Customer | None) -> str:
    """Who the contracts of this pratica are for (Session 85): the kind chosen
    in its data form, or -- a pratica opened before that existed -- the
    customer's. Decides VAT, which packages fit, the PEC and the documents,
    in place of customer.kind everywhere a pratica is at hand."""
    if request.holder_kind:
        return request.holder_kind
    return customer.kind if customer is not None and customer.kind else "PRIVATE"


async def pratica_kind_of(db: AsyncSession, request: ContractRequest) -> str:
    return pratica_kind(request, await db.get(Customer, request.customer_id))


async def contract_kind(db: AsyncSession, contract: Contract) -> str:
    """The same, for one contract: the kind of the pratica it belongs to."""
    request = await db.get(ContractRequest, contract.contract_request_id) if contract.contract_request_id else None
    if request is not None:
        return await pratica_kind_of(db, request)
    customer = await db.get(Customer, contract.customer_id)
    return customer.kind if customer is not None and customer.kind else "PRIVATE"


def _code(request: ContractRequest | Contract) -> str:
    return str(request.id)[:8].upper()


def _request_address(request: ContractRequest) -> AddressData | None:
    if not (request.street and request.city and request.province and request.postal_code):
        return None
    return AddressData(
        street=request.street, city=request.city, province=request.province, postal_code=request.postal_code
    )


def _point_label(energy_type: str | None, address: Address) -> str:
    from app.domains.customers.service import ENERGY_TYPE_LABELS

    kind = ENERGY_TYPE_LABELS.get(energy_type or "", "Punto di fornitura")
    return f"{kind} - {address.street}, {address.city}"


async def _customer_name(db: AsyncSession, customer: Customer | None) -> str:
    if customer is None:
        return "Cliente"
    from app.domains.customers.service import display_name_for

    profile = await db.get(CustomerProfile, customer.id)
    company = await db.get(Company, customer.id)
    return display_name_for(customer.kind, profile, company)


#: Longest note a pratica keeps -- a message, not a document.
MAX_NOTES_LENGTH = 2000


def _holder_kind(customer: Customer | None, holder: "HolderData") -> str:
    if holder.kind:
        if holder.kind not in PRATICA_KINDS:
            raise ContractRequestError("Tipo di contratto non valido: scegli privato o azienda.")
        return holder.kind
    return customer.kind if customer is not None and customer.kind else "PRIVATE"


def _check_holder(kind: str, holder: "HolderData") -> None:
    """A partita IVA (company, ditta, condominium) must give a PEC as well
    as an email: it is where a business receives what has legal weight. And
    a business contract is signed by its legal representative: ragione
    sociale and their fiscal code are required (Session 85), their name is
    the holder's. A private customer is asked for none of it."""
    _check_person(kind, holder)
    if not pricing.is_business_customer(kind):
        return
    if not (holder.company_name or "").strip():
        raise ContractRequestError("Per un contratto aziendale serve la ragione sociale.")
    if not (holder.legal_rep_fiscal_code or "").strip():
        raise ContractRequestError("Per un contratto aziendale serve il codice fiscale del legale rappresentante.")
    if not (holder.pec or "").strip():
        raise ContractRequestError("Per un contratto aziendale la PEC è obbligatoria, oltre all'email.")


def _check_person(kind: str, holder: "HolderData") -> None:
    """Session 89: everyone who signs -- the private holder or the legal
    representative -- gives fiscal code, birth date and place. Whether the
    code matches them is NOT blocking, by the user's choice: it is reported
    by fiscal_code_problems() as a warning, in the wizard and to staff."""
    business = pricing.is_business_customer(kind)
    who = "del legale rappresentante" if business else "dell'intestatario"
    code = holder.legal_rep_fiscal_code if business else holder.fiscal_code
    if not (code or "").strip():
        raise ContractRequestError(f"Serve il codice fiscale {who}.")
    if holder.birth_date is None or not holder.birth_place_code:
        raise ContractRequestError(f"Servono data e luogo di nascita {who}.")
    today = utcnow().date()
    if holder.birth_date.year < 1900 or holder.birth_date > today:
        raise ContractRequestError("La data di nascita non è valida.")
    if (today.year, today.month, today.day) < (holder.birth_date.year + 18, holder.birth_date.month, holder.birth_date.day):
        raise ContractRequestError(f"Chi firma il contratto deve essere maggiorenne: controlla la data di nascita {who}.")
    if fiscal_code.birthplace(holder.birth_place_code) is None:
        raise ContractRequestError("Luogo di nascita non riconosciuto: sceglilo dall'elenco che compare mentre scrivi.")


def fiscal_code_problems(request: ContractRequest) -> list[str]:
    """What in the signer's fiscal code does not match name, surname, birth
    date and place -- a warning, never a block (Session 89). Empty for a
    pratica opened before birth data was asked."""
    code = request.holder_fiscal_code or request.legal_rep_fiscal_code
    if not (code and request.holder_birth_date and request.holder_first_name and request.holder_last_name):
        return []
    return fiscal_code.check(
        code, first_name=request.holder_first_name, last_name=request.holder_last_name,
        birth_date=request.holder_birth_date, birthplace_code=request.holder_birth_place_code,
    )


def _apply_holder_kind(request: ContractRequest, kind: str, holder: "HolderData") -> None:
    business = pricing.is_business_customer(kind)
    place = fiscal_code.birthplace(holder.birth_place_code)
    request.holder_fiscal_code = None if business else fiscal_code.normalize(holder.fiscal_code) or None
    request.holder_birth_date = holder.birth_date
    request.holder_birth_place_code = place["code"] if place else None
    request.holder_birth_place = fiscal_code.birthplace_label(place) if place else None
    request.holder_kind = kind
    request.company_name = holder.company_name.strip() if business and holder.company_name else None
    request.legal_rep_fiscal_code = (
        holder.legal_rep_fiscal_code.strip().upper() if business and holder.legal_rep_fiscal_code else None
    )


def _assert_draft(request: ContractRequest) -> None:
    if request.status != "DRAFT":
        raise ContractRequestError(
            "La pratica è già stata inviata: i POD e i contratti scelti non si possono più modificare. "
            "Per aggiungere un altro POD apri una nuova pratica."
        )


async def list_points(db: AsyncSession, *, request: ContractRequest, include_cancelled: bool = False) -> list[Contract]:
    stmt = select(Contract).where(Contract.contract_request_id == request.id).order_by(Contract.created_at)
    if not include_cancelled:
        # A point removed from a draft is CANCELLED without ever having been
        # sent -- it is not part of the pratica any more. A contract
        # cancelled after activation still is, so only drafts are hidden.
        stmt = stmt.where(~((Contract.status == "CANCELLED") & (Contract.activated_at.is_(None))))
    return list((await db.execute(stmt)).scalars())


# --- Creazione e dati intestatario --------------------------------------------


async def create_request(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID,
    holder: HolderData,
    actor_user_id: uuid.UUID,
    actor_role: str,
    promoter_agent_id: uuid.UUID | None,
    points_count: int = 1,
    pdr_count: int = 0,
    product_version_id: uuid.UUID | None = None,
) -> ContractRequest:
    """Opens a DRAFT pratica with its holder, its address and -- answering
    "quanti POD hai? quanti PDR hai?" -- that many points already created,
    each a DRAFT contract waiting for its package (`points_count` is the POD
    count). `product_version_id` (the customer started from a package in the
    catalog) pre-chooses it for every point of its own energy.

    For a customer acting alone, their referrer is resolved first: a customer
    whose promoter has left with nobody active above must be told before
    filling anything in, not after. Commits."""
    if promoter_agent_id is None:
        try:
            await contract_service.resolve_self_service_producer(
                db, organization_id=organization_id, customer_id=customer_id
            )
        except contract_service.SelfServiceContractError as exc:
            raise ContractRequestError(str(exc)) from exc

    kind = _holder_kind(await db.get(Customer, customer_id), holder)
    _check_holder(kind, holder)
    request = ContractRequest(
        organization_id=organization_id,
        customer_id=customer_id,
        status="DRAFT",
        holder_first_name=holder.first_name,
        holder_last_name=holder.last_name,
        email=holder.email,
        pec=holder.pec,
        iban=holder.iban,
        street=holder.address.street,
        city=holder.address.city,
        province=holder.address.province,
        postal_code=holder.address.postal_code,
        created_by_user_id=actor_user_id,
        created_by_role=actor_role,
        activated_by_promoter_id=promoter_agent_id,
        updated_at=utcnow(),
    )
    _apply_holder_kind(request, kind, holder)
    db.add(request)
    await db.flush()
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="contract_request.created", entity_type="contract_request", entity_id=str(request.id),
        new_value={"customer_id": str(customer_id), "created_by_role": actor_role, "pod": points_count, "pdr": pdr_count},
    )
    await db.commit()
    await db.refresh(request)
    await set_points_count(
        db, request=request, pod_count=points_count, pdr_count=pdr_count, actor_user_id=actor_user_id
    )
    if product_version_id is not None:
        await set_product_for_all(
            db, request=request, product_version_id=product_version_id, actor_user_id=actor_user_id,
            skip_if_no_point_fits=True,
        )
    await db.refresh(request)
    return request


async def update_holder(
    db: AsyncSession, *, request: ContractRequest, holder: HolderData, actor_user_id: uuid.UUID
) -> ContractRequest:
    """Holder data and address can change while the pratica is a draft, and
    every point follows -- except a point that was deliberately moved to an
    address of its own, which keeps it. Commits."""
    _assert_draft(request)
    customer = await db.get(Customer, request.customer_id)
    kind = _holder_kind(customer, holder)
    _check_holder(kind, holder)
    previous_kind = pratica_kind(request, customer)
    _apply_holder_kind(request, kind, holder)
    previous_address = _request_address(request)
    request.holder_first_name = holder.first_name
    request.holder_last_name = holder.last_name
    request.email = holder.email
    request.pec = holder.pec
    request.iban = holder.iban
    request.street = holder.address.street
    request.city = holder.address.city
    request.province = holder.address.province
    request.postal_code = holder.address.postal_code
    request.updated_at = utcnow()
    for contract in await list_points(db, request=request):
        contract.holder_first_name = holder.first_name
        contract.holder_last_name = holder.last_name
        contract.email = holder.email
        contract.pec = holder.pec
        contract.iban = holder.iban
        contract.updated_at = utcnow()
        supply_point = await db.get(SupplyPoint, contract.supply_point_id)
        address = await db.get(Address, supply_point.supply_address_id) if supply_point else None
        if address is not None and (
            previous_address is None
            or (address.street, address.city, address.province, address.postal_code)
            == (previous_address.street, previous_address.city, previous_address.province, previous_address.postal_code)
        ):
            _apply_address(address, holder.address)
            supply_point.label = _point_label(supply_point.energy_type, address)
    if kind != previous_kind:
        await _reprice_for_kind(db, request=request, kind=kind)
    await audit_service.record(
        db, organization_id=request.organization_id, actor_user_id=actor_user_id,
        action="contract_request.holder_updated", entity_type="contract_request", entity_id=str(request.id),
        new_value={"holder_kind": kind} if kind != previous_kind else None,
    )
    await db.commit()
    await db.refresh(request)
    return request


async def _reprice_for_kind(db: AsyncSession, *, request: ContractRequest, kind: str) -> None:
    """Privato <-> azienda changed on a draft: VAT and which packages fit
    change with it. A chosen package that still fits is priced again for
    the new kind (a draft has not committed to a price yet); one that no
    longer fits is taken off, to be chosen again. Does not commit."""
    for contract in await list_points(db, request=request):
        if contract.status != "DRAFT" or contract.product_version_id is None:
            continue
        version = await db.get(ProductVersion, contract.product_version_id)
        product = await db.get(Product, version.product_id) if version is not None else None
        if version is not None and product is not None and pricing.product_allows_customer_kind(product.customer_type, kind):
            await contract_service.freeze_price(db, contract=contract, version=version, customer_kind=kind)
            continue
        contract.product_version_id = None
        contract.customer_kind = kind
        for column in (
            "net_amount_cents", "vat_rate", "vat_amount_cents", "gross_amount_cents",
            "instalments_net_amount_cents", "instalments_vat_amount_cents", "instalments_gross_amount_cents",
        ):
            setattr(contract, column, None)
        contract.updated_at = utcnow()


def _apply_address(address: Address, data: AddressData) -> None:
    address.street = data.street.strip()
    address.city = data.city.strip()
    address.province = data.province.strip().upper()
    address.postal_code = data.postal_code.strip()


# --- I POD della pratica ------------------------------------------------------


async def _producer_for_new_point(
    db: AsyncSession, *, request: ContractRequest
) -> tuple[uuid.UUID, uuid.UUID | None]:
    """Resolved per point, at the moment it is added, with the same rules as
    a single contract: the promoter filling it in, or the customer's own
    referrer -- in both cases walking up to the nearest active sponsor if that
    person is no longer active, and saying so in the audit log."""
    from app.domains.network import service as network_service

    if request.activated_by_promoter_id is not None:
        promoter = await db.get(AgentProfile, request.activated_by_promoter_id)
        if promoter is not None and promoter.status == "ACTIVE":
            return promoter.id, None
        nearest = await network_service.resolve_nearest_active_agent(
            db, organization_id=request.organization_id, agent_id=request.activated_by_promoter_id
        )
        if nearest is None:
            raise ContractRequestError(
                "Il promoter che ha aperto questa pratica non è più attivo e non c'è un referente attivo sopra di lui. "
                "Contatta l'assistenza."
            )
        return nearest.id, request.activated_by_promoter_id
    try:
        return await contract_service.resolve_self_service_producer(
            db, organization_id=request.organization_id, customer_id=request.customer_id
        )
    except contract_service.SelfServiceContractError as exc:
        raise ContractRequestError(str(exc)) from exc


async def _load_package(db: AsyncSession, *, request: ContractRequest, product_version_id: uuid.UUID) -> tuple[ProductVersion, Product]:
    version = await db.get(ProductVersion, product_version_id)
    product = await db.get(Product, version.product_id) if version is not None else None
    if version is None or product is None or product.organization_id != request.organization_id:
        raise ContractRequestError("Contratto non trovato nel catalogo.")
    if product.category != "INTERNAL":
        raise ContractRequestError(
            "Solo i contratti Jav si attivano da qui -- gli altri prodotti si acquistano nello Shop."
        )
    if product.status != "ACTIVE" or version.status != "ACTIVE":
        raise ContractRequestError(f"Il contratto “{version.name}” non è più disponibile.")
    if not pricing.product_allows_customer_kind(product.customer_type, await pratica_kind_of(db, request)):
        raise ContractRequestError(
            f"Il contratto “{version.name}” non è disponibile per la tipologia di questo cliente."
        )
    return version, product


async def add_point(
    db: AsyncSession, *, request: ContractRequest, actor_user_id: uuid.UUID, energy_type: str = POD
) -> Contract:
    """One more POD (luce) or PDR (gas) in a draft pratica: a supply point
    of that kind at the pratica's address, and a DRAFT contract for it with
    no package yet. Commits."""
    from app.domains.customers.models import SupplyPoint as SupplyPointModel

    _assert_draft(request)
    address_data = _request_address(request)
    if address_data is None:
        raise ContractRequestError("Inserisci l'indirizzo di fornitura prima di aggiungere i POD.")
    if len(await list_points(db, request=request)) >= MAX_POINTS_PER_REQUEST:
        raise ContractRequestError(
            f"Una pratica può contenere al massimo {MAX_POINTS_PER_REQUEST} punti di fornitura: "
            "per gli altri apri una seconda pratica."
        )
    producer_agent_id, substituted_for = await _producer_for_new_point(db, request=request)

    address = Address(organization_id=request.organization_id, customer_id=request.customer_id, kind="SUPPLY",
                      street="", city="", province="", postal_code="")
    _apply_address(address, address_data)
    db.add(address)
    await db.flush()
    supply_point = SupplyPointModel(
        organization_id=request.organization_id,
        customer_id=request.customer_id,
        energy_type=energy_type,
        supply_address_id=address.id,
        label=_point_label(energy_type, address),
    )
    db.add(supply_point)
    await db.flush()

    try:
        contract = await contract_service.create_contract(
            db, organization_id=request.organization_id, customer_id=request.customer_id,
            supply_point_id=supply_point.id, product_version_id=None,
            producer_agent_id=producer_agent_id, actor_user_id=actor_user_id,
            correlation_id=str(uuid.uuid4()), contract_request_id=request.id, notify_staff=False,
            email=request.email, holder_first_name=request.holder_first_name,
            holder_last_name=request.holder_last_name, pec=request.pec, iban=request.iban,
            created_by_role=request.created_by_role, activated_by_promoter_id=request.activated_by_promoter_id,
        )
    except contract_service.InvalidProducerAgentError as exc:
        raise ContractRequestError(str(exc)) from exc
    if substituted_for is not None:
        await contract_service.record_producer_substitution(
            db, organization_id=request.organization_id, contract=contract, actor_user_id=actor_user_id,
            substituted_for_agent_id=substituted_for,
        )
    request.updated_at = utcnow()
    await db.commit()
    await db.refresh(contract)
    return contract


async def set_points_count(
    db: AsyncSession, *, request: ContractRequest, pod_count: int | None, pdr_count: int | None,
    actor_user_id: uuid.UUID,
) -> list[Contract]:
    """"Quanti POD hai? Quanti PDR hai?": adds or removes points of each kind
    until the pratica has exactly that many (None leaves a kind as it is).
    Removing takes the most recent points first, and among them the ones
    without a contract chosen -- never the work already done when there is
    an empty point to drop instead. Commits.

    Untyped draft points (created before PDR existed, when every point was
    "a POD") are counted as POD and typed as such on the way."""
    _assert_draft(request)
    points = await list_points(db, request=request)
    for contract in points:
        supply_point = await db.get(SupplyPoint, contract.supply_point_id)
        if supply_point is not None and supply_point.energy_type is None and contract.status == "DRAFT":
            supply_point.energy_type = POD
    await db.commit()

    kinds = {c.id: (await db.get(SupplyPoint, c.supply_point_id)).energy_type for c in points}
    wanted = {
        POD: pod_count if pod_count is not None else sum(1 for k in kinds.values() if k == POD),
        PDR: pdr_count if pdr_count is not None else sum(1 for k in kinds.values() if k == PDR),
    }
    if wanted[POD] < 0 or wanted[PDR] < 0:
        raise ContractRequestError("Il numero di POD e di PDR non può essere negativo.")
    others = sum(1 for k in kinds.values() if k not in (POD, PDR))
    total = wanted[POD] + wanted[PDR] + others
    if total < 1:
        raise ContractRequestError("Una pratica deve avere almeno un POD o un PDR.")
    if total > MAX_POINTS_PER_REQUEST:
        raise ContractRequestError(
            f"Una pratica può contenere al massimo {MAX_POINTS_PER_REQUEST} punti di fornitura (POD + PDR): "
            "per gli altri apri una seconda pratica."
        )

    # Remove first, so the total never crosses the ceiling on the way.
    for energy_type in (POD, PDR):
        of_kind = [c for c in points if kinds[c.id] == energy_type]
        excess = len(of_kind) - wanted[energy_type]
        if excess <= 0:
            continue
        drafts = [c for c in of_kind if c.status == "DRAFT"]
        removable = sorted(drafts, key=lambda c: (c.product_version_id is not None, -c.created_at.timestamp()))
        if len(removable) < excess:
            raise ContractRequestError(
                f"Non si possono togliere {excess} {point_kind_label(energy_type)}: alcuni non sono più modificabili."
            )
        for contract in removable[:excess]:
            await _cancel_point(db, request=request, contract=contract, actor_user_id=actor_user_id)
    for energy_type in (POD, PDR):
        have = sum(1 for c in points if kinds[c.id] == energy_type)
        for _ in range(max(0, wanted[energy_type] - have)):
            await add_point(db, request=request, actor_user_id=actor_user_id, energy_type=energy_type)
    return await list_points(db, request=request)


async def get_point(db: AsyncSession, *, request: ContractRequest, contract_id: uuid.UUID) -> Contract:
    contract = await db.get(Contract, contract_id)
    if contract is None or contract.contract_request_id != request.id:
        raise ContractRequestError("POD non trovato in questa pratica.")
    return contract


async def update_point_address(
    db: AsyncSession, *, request: ContractRequest, contract: Contract, address_data: AddressData,
    actor_user_id: uuid.UUID,
) -> Contract:
    """Moves one POD to an address other than the pratica's -- the second
    home, the shop downstairs. Commits."""
    _assert_draft(request)
    if contract.status != "DRAFT":
        raise ContractRequestError("Questo POD non si può più modificare.")
    supply_point = await db.get(SupplyPoint, contract.supply_point_id)
    address = await db.get(Address, supply_point.supply_address_id) if supply_point else None
    if supply_point is None or address is None:
        raise ContractRequestError("Punto di fornitura non trovato.")
    previous = {"street": address.street, "city": address.city}
    _apply_address(address, address_data)
    supply_point.label = _point_label(supply_point.energy_type, address)
    contract.updated_at = request.updated_at = utcnow()
    await audit_service.record(
        db, organization_id=request.organization_id, actor_user_id=actor_user_id,
        action="contract_request.point_address_updated", entity_type="contract", entity_id=str(contract.id),
        previous_value=previous, new_value={"street": address.street, "city": address.city},
    )
    await db.commit()
    await db.refresh(contract)
    return contract


async def remove_point(
    db: AsyncSession, *, request: ContractRequest, contract: Contract, actor_user_id: uuid.UUID
) -> None:
    """Takes a POD out of a draft pratica. The contract is CANCELLED, not
    deleted: its creation is already in the audit trail and the history
    should say what became of it. The last POD cannot go."""
    _assert_draft(request)
    if contract.status != "DRAFT":
        raise ContractRequestError("Questo POD non si può più togliere dalla pratica.")
    if len(await list_points(db, request=request)) <= 1:
        raise ContractRequestError("Una pratica deve avere almeno un POD o un PDR.")
    await _cancel_point(db, request=request, contract=contract, actor_user_id=actor_user_id)


async def _cancel_point(
    db: AsyncSession, *, request: ContractRequest, contract: Contract, actor_user_id: uuid.UUID
) -> None:
    await contract_service.transition_contract(
        db, organization_id=request.organization_id, contract=contract, to_status="CANCELLED",
        actor_user_id=actor_user_id, reason="POD tolto dalla pratica prima dell'invio", notes=None,
        correlation_id=str(uuid.uuid4()),
    )
    request.updated_at = utcnow()
    await db.commit()


async def _assign_package(db: AsyncSession, *, contract: Contract, version: ProductVersion, product: Product) -> None:
    """A POD takes only luce packages, a PDR only gas ones; an untyped
    point (older drafts) is typed by its package. Freezes the price. Does
    not commit."""
    supply_point = await db.get(SupplyPoint, contract.supply_point_id)
    _check_package_fits_point(supply_point, product, version)
    if supply_point is not None:
        supply_point.energy_type = product.energy_type
        address = await db.get(Address, supply_point.supply_address_id)
        if address is not None:
            supply_point.label = _point_label(product.energy_type, address)
    await contract_service.freeze_price(db, contract=contract, version=version, customer_kind=await contract_kind(db, contract))


async def set_point_product(
    db: AsyncSession, *, request: ContractRequest, contract: Contract, product_version_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> Contract:
    """Chooses (or changes) the contract to activate on one POD. Commits."""
    _assert_draft(request)
    if contract.status != "DRAFT":
        raise ContractRequestError("Il contratto di questo POD non si può più cambiare.")
    version, product = await _load_package(db, request=request, product_version_id=product_version_id)
    previous = str(contract.product_version_id) if contract.product_version_id else None
    await _assign_package(db, contract=contract, version=version, product=product)
    request.updated_at = utcnow()
    await audit_service.record(
        db, organization_id=request.organization_id, actor_user_id=actor_user_id,
        action="contract.package_selected", entity_type="contract", entity_id=str(contract.id),
        previous_value={"product_version_id": previous},
        new_value={"product_version_id": str(version.id), "gross_amount_cents": contract.gross_amount_cents},
    )
    await db.commit()
    await db.refresh(contract)
    return contract


#: A contract whose package staff may still change: the money has not moved
#: yet and nothing has been activated. Session 71 -- before this, a package
#: chosen wrongly by the customer could only be fixed by rejecting the
#: contract and starting a new pratica.
STAFF_REPACKAGE_STATUSES = frozenset(
    {"DRAFT", "SUBMITTED", "DOCUMENTS_PENDING", "UNDER_REVIEW", "APPROVED", "PAYMENT_PENDING"}
)


async def staff_set_point_product(
    db: AsyncSession, *, request: ContractRequest, contract: Contract, product_version_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> Contract:
    """An administrator fixes the package of one POD, also on a pratica
    already sent -- never once it is paid, being charged or active, because
    the price is frozen at payment and the commissions follow it. Commits."""
    if contract.paid_at is not None:
        raise ContractRequestError(
            "Questo contratto è già pagato: il pacchetto non si cambia più. Respingilo e apri una nuova pratica."
        )
    if contract.stripe_subscription_id is not None and contract.billing_stopped_at is None:
        raise ContractRequestError(
            "Gli addebiti a rate di questo contratto sono attivi: interrompili prima di cambiare il pacchetto."
        )
    if contract.status not in STAFF_REPACKAGE_STATUSES:
        raise ContractRequestError(
            f"Un contratto {contract.status} non può cambiare pacchetto."
        )
    version, product = await _load_package(db, request=request, product_version_id=product_version_id)
    previous = str(contract.product_version_id) if contract.product_version_id else None
    previous_gross = contract.gross_amount_cents
    await _assign_package(db, contract=contract, version=version, product=product)
    request.updated_at = utcnow()
    await audit_service.record(
        db, organization_id=request.organization_id, actor_user_id=actor_user_id,
        action="contract.package_changed_by_staff", entity_type="contract", entity_id=str(contract.id),
        previous_value={"product_version_id": previous, "gross_amount_cents": previous_gross},
        new_value={"product_version_id": str(version.id), "gross_amount_cents": contract.gross_amount_cents},
    )
    await db.commit()
    await db.refresh(contract)
    return contract


async def set_product_for_all(
    db: AsyncSession, *, request: ContractRequest, product_version_id: uuid.UUID, actor_user_id: uuid.UUID,
    skip_if_no_point_fits: bool = False,
) -> int:
    """"Stessa offerta per tutti i POD" (or all the PDR): applied to every
    draft point the package fits -- a luce offer lands on the POD only, a
    gas one on the PDR only. Returns how many received it. Commits."""
    _assert_draft(request)
    version, product = await _load_package(db, request=request, product_version_id=product_version_id)
    applied = 0
    for contract in await list_points(db, request=request):
        if contract.status != "DRAFT":
            continue
        supply_point = await db.get(SupplyPoint, contract.supply_point_id)
        if supply_point is not None and supply_point.energy_type not in (None, product.energy_type):
            continue
        await _assign_package(db, contract=contract, version=version, product=product)
        applied += 1
    if applied == 0:
        if skip_if_no_point_fits:
            return 0
        wanted = "PDR" if product.energy_type == PDR else "POD"
        raise ContractRequestError(f"“{version.name}” non si può attivare su nessun punto: in questa pratica non ci sono {wanted}.")
    request.updated_at = utcnow()
    await audit_service.record(
        db, organization_id=request.organization_id, actor_user_id=actor_user_id,
        action="contract_request.package_applied_to_all", entity_type="contract_request",
        entity_id=str(request.id), new_value={"product_version_id": str(version.id), "points": applied},
    )
    await db.commit()
    return applied


async def set_notes(
    db: AsyncSession, *, request: ContractRequest, notes: str | None, actor_user_id: uuid.UUID
) -> ContractRequest:
    """The message left for the administration. Written while the pratica
    is a draft, by whoever fills it in; read by staff. Commits."""
    _assert_draft(request)
    cleaned = (notes or "").strip()
    if len(cleaned) > MAX_NOTES_LENGTH:
        raise ContractRequestError(f"Le note possono essere lunghe al massimo {MAX_NOTES_LENGTH} caratteri.")
    request.notes = cleaned or None
    request.notes_updated_by_user_id = actor_user_id
    request.notes_updated_at = request.updated_at = utcnow()
    await audit_service.record(
        db, organization_id=request.organization_id, actor_user_id=actor_user_id,
        action="contract_request.notes_updated", entity_type="contract_request", entity_id=str(request.id),
        new_value={"notes": request.notes},
    )
    await db.commit()
    await db.refresh(request)
    return request


# --- Invio e annullamento ----------------------------------------------------


async def submit_request(db: AsyncSession, *, request: ContractRequest, actor_user_id: uuid.UUID) -> ContractRequest:
    """Sends the pratica: every point leaves DRAFT together, and each one
    goes on through the same flow a single contract always has --
    DOCUMENTS_PENDING, then UNDER_REVIEW by itself as soon as its required
    documents (its own, or the pratica's) are all in.

    Staff hear about it once, as a pratica, not once per point."""
    from app.domains.customers.models import Customer
    from app.domains.documents import service as documents_service

    _assert_draft(request)
    points = await list_points(db, request=request)
    if not points:
        raise ContractRequestError("Aggiungi almeno un punto di fornitura prima di inviare la pratica.")
    missing = [p for p in points if p.product_version_id is None]
    if missing:
        raise ContractRequestError(
            f"Scegli il contratto da attivare per {'il punto' if len(missing) == 1 else f'i {len(missing)} punti'} "
            "ancora senza, poi invia la pratica."
        )
    if not (request.holder_first_name and request.holder_last_name and request.email and _request_address(request)):
        raise ContractRequestError("Completa i dati dell'intestatario e l'indirizzo prima di inviare la pratica.")
    if not (request.holder_birth_date and request.holder_birth_place_code):
        # A draft opened before Session 89: the data form asks them now.
        raise ContractRequestError(
            "Mancano data e luogo di nascita di chi firma: torna al passo «Dati», completali, poi invia."
        )
    customer = await db.get(Customer, request.customer_id)
    kind = pratica_kind(request, customer)
    if pricing.is_business_customer(kind):
        if not (request.pec or "").strip():
            raise ContractRequestError("Per un contratto aziendale la PEC è obbligatoria: aggiungila nei dati, poi invia.")
        if not (request.company_name and request.legal_rep_fiscal_code):
            raise ContractRequestError(
                "Per un contratto aziendale servono ragione sociale e codice fiscale del legale rappresentante: "
                "aggiungili nei dati, poi invia."
            )
    documents_missing = await documents_service.pratica_blocking_missing(
        db, request=request, customer_kind=kind
    )
    if documents_missing:
        raise ContractRequestError(
            "Prima di inviare la pratica carica almeno una pagina di: " + ", ".join(documents_missing) + "."
        )

    for contract in points:
        if contract.status != "DRAFT":
            continue
        contract = await contract_service.transition_contract(
            db, organization_id=request.organization_id, contract=contract, to_status="SUBMITTED",
            actor_user_id=actor_user_id, reason=f"Pratica {_code(request)} inviata", notes=None,
            correlation_id=str(uuid.uuid4()),
        )
        contract = await contract_service.transition_contract(
            db, organization_id=request.organization_id, contract=contract, to_status="DOCUMENTS_PENDING",
            actor_user_id=actor_user_id, reason=None, notes=None, correlation_id=str(uuid.uuid4()),
        )
        await documents_service.maybe_advance_to_under_review(
            db, organization_id=request.organization_id, contract_id=contract.id, actor_user_id=actor_user_id
        )

    await db.refresh(request)
    if request.status == "DRAFT":
        # transition_contract promotes the pratica when its last draft
        # leaves; reaching here means it had no draft left to move.
        request.status = "SUBMITTED"
        request.submitted_at = utcnow()
    customer = await db.get(Customer, request.customer_id)
    name = await _customer_name(db, customer)
    await notifications_service.notify_roles(
        db, organization_id=request.organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="CONTRACT_CREATED", entity_type="contract_request", entity_id=request.id,
        title=f"Nuova pratica {_code(request)}: {len(points)} {'punto' if len(points) == 1 else 'punti'}",
        body=(
            f"{name} ha inviato una pratica di attivazione con {len(points)} contratt{'o' if len(points) == 1 else 'i'}."
            + (f" Note: {request.notes[:300]}" if request.notes else "")
        ),
        exclude_user_id=actor_user_id,
    )
    await audit_service.record(
        db, organization_id=request.organization_id, actor_user_id=actor_user_id,
        action="contract_request.submitted", entity_type="contract_request", entity_id=str(request.id),
        new_value={"points": len(points)},
    )
    # Filled in FOR the customer -- by their promoter, or by the
    # administration (Session 66): either way the customer is the one who
    # pays, so they are told it is waiting for them.
    filled_in_for_customer = request.created_by_role in ("PROMOTER", "ADMIN") and customer is not None
    promoter_name = None
    if filled_in_for_customer:
        if request.activated_by_promoter_id is not None:
            promoter = await db.get(AgentProfile, request.activated_by_promoter_id)
            promoter_name = promoter.display_name if promoter else None
        who = promoter_name or ("Il tuo promoter" if request.created_by_role == "PROMOTER" else "Jav")
        if customer.user_id is not None:
            await notifications_service.notify_user(
                db, organization_id=request.organization_id, user_id=customer.user_id,
                type_="CONTRACT_CREATED", entity_type="contract_request", entity_id=request.id,
                title="I tuoi contratti sono pronti da pagare",
                body=(
                    f"{who} ha compilato per te la pratica {_code(request)} con "
                    f"{len(points)} POD. Controllala in “I miei Contratti” e procedi con il pagamento."
                ),
            )
    await db.commit()
    await db.refresh(request)
    if filled_in_for_customer:
        _email_customer_about_promoter_pratica(
            request=request, customer=customer,
            promoter_name=promoter_name or (None if request.created_by_role == "PROMOTER" else "Jav"),
            points=points,
        )
    return request


def _email_customer_about_promoter_pratica(
    *, request: ContractRequest, customer: Customer, promoter_name: str | None, points: list[Contract]
) -> None:
    """Somebody filled the pratica in for the customer -- their promoter
    (Session 55) or the administration (Session 66): the customer is the one
    who pays, so they have to find out it is waiting. Best-effort and after
    the commit -- the pratica is sent either way."""
    import html

    from app.core.config import get_settings
    from app.core.email import send_html_email_best_effort
    from app.core.email_templates import render_email

    to = request.email or customer.email
    if not to:
        return
    who = html.escape(promoter_name or "Il tuo promoter")
    heading_who = "Il tuo promoter ha preparato i tuoi contratti" if promoter_name != "Jav" else "Abbiamo preparato i tuoi contratti"
    total = sum(int(p.gross_amount_cents or 0) for p in points)
    body_html = (
        f"<p>{who} ha preparato per te la pratica <strong>{_code(request)}</strong> con "
        f"<strong>{len(points)} POD</strong>, per un totale di <strong>{total / 100:.2f} €</strong> "
        "in un'unica soluzione.</p>"
        "<p>Ogni POD è un contratto a sé. Accedi alla tua area, controlla i contratti in "
        "<em>I miei Contratti</em> e completa il pagamento: puoi pagare in un'unica soluzione o a rate. "
        "Se non hai ancora impostato la password, usa il link di invito che ti è arrivato.</p>"
    )
    send_html_email_best_effort(
        context=f"Promoter pratica email (request={request.id})",
        to=to,
        subject="I tuoi contratti Jav sono pronti - Jav",
        html_body=render_email(
            preheader=heading_who,
            heading="I tuoi contratti sono pronti",
            body_html=body_html,
            cta_label="Vai ai miei contratti",
            cta_url=f"{get_settings().public_app_base_url}/customer?tab=contracts",
        ),
        text_body=(
            f"{promoter_name or 'Il tuo promoter'} ha preparato per te la pratica {_code(request)} con "
            f"{len(points)} POD. Accedi a I miei Contratti per controllarla e pagare."
        ),
    )


#: What «Sblocca pratica» marks on a card checkout opened before the unlock:
#: paid anyway (an old tab), it pays nothing and staff are told to refund.
UNLOCKED_CHECKOUT_OUTCOME = "ANNULLATO: pratica sbloccata"


async def unlock_request(
    db: AsyncSession, *, request: ContractRequest, actor_user_id: uuid.UUID
) -> tuple[ContractRequest, list[str]]:
    """«Sblocca pratica» (Session 89): a pratica sent but not paid goes back
    to draft -- every contract still alive with it -- so the customer, their
    promoter or staff can choose the packages again, then send it and pay
    the new total. Approvals already given are lost: the pratica is reviewed
    again once sent.

    Refused when anything was paid (a contract, an instalment, a card
    checkout), while instalments are being charged, or once the customer
    uploaded a bank transfer receipt. A transfer only announced is undone
    (the total will change). Card checkouts still open are marked so that,
    paid from an old tab, they pay nothing; returns their Stripe session
    ids, for the caller to expire. Commits."""
    if request.status != "SUBMITTED":
        raise ContractRequestError("Si sblocca solo una pratica inviata e non ancora pagata.")
    points = await list_points(db, request=request)
    live = [c for c in points if c.status not in ("CANCELLED", "REJECTED")]
    if not live:
        raise ContractRequestError("Questa pratica non ha contratti da riaprire.")
    if any(c.paid_at is not None for c in points):
        raise ContractRequestError("La pratica è già pagata, anche solo in parte: non si può sbloccare.")
    if any(c.stripe_subscription_id is not None and c.billing_stopped_at is None for c in points):
        raise ContractRequestError("La pratica ha addebiti a rate attivi: non si può sbloccare.")
    paid_instalment = (
        await db.execute(
            select(ContractInstalment.id).where(
                ContractInstalment.contract_id.in_([c.id for c in points]), ContractInstalment.status == "PAID"
            )
        )
    ).first()
    if paid_instalment is not None:
        raise ContractRequestError("Una rata della pratica è già pagata: non si può sbloccare.")
    checkouts = list(
        (
            await db.execute(
                select(ContractRequestCheckout).where(ContractRequestCheckout.contract_request_id == request.id)
            )
        ).scalars()
    )
    if any(c.completed_at is not None for c in checkouts):
        raise ContractRequestError("C'è un pagamento con carta registrato su questa pratica: non si può sbloccare.")
    if request.payment_proof_uploaded_at is not None and request.bank_transfer_requested_at is not None:
        raise ContractRequestError(
            "Il cliente ha caricato la ricevuta del bonifico: controlla prima il bonifico, la pratica non si sblocca."
        )
    stuck = sorted({c.status for c in live if c.status not in contract_service.PREPAYABLE_STATUSES})
    if stuck:
        raise ContractRequestError(f"Ci sono contratti già avanti ({', '.join(stuck)}): la pratica non si sblocca.")

    for contract in live:
        await contract_service.transition_contract(
            db, organization_id=request.organization_id, contract=contract, to_status="DRAFT",
            actor_user_id=actor_user_id, reason=f"Pratica {_code(request)} sbloccata: contratti da rivedere",
            notes=None, correlation_id=str(uuid.uuid4()),
        )
        if contract.payment_method == "BANK_TRANSFER":
            contract.payment_method = None
            contract.payment_plan = None
            contract.payment_discount_cents = 0
    request.bank_transfer_requested_at = None
    request.bank_transfer_total_cents = None
    request.status = "DRAFT"
    request.submitted_at = None
    request.updated_at = utcnow()
    open_sessions = []
    for checkout in checkouts:
        checkout.outcome = UNLOCKED_CHECKOUT_OUTCOME
        open_sessions.append(checkout.stripe_checkout_session_id)
    await audit_service.record(
        db, organization_id=request.organization_id, actor_user_id=actor_user_id,
        action="contract_request.unlocked", entity_type="contract_request", entity_id=str(request.id),
        new_value={"contracts": len(live)},
    )
    customer = await db.get(Customer, request.customer_id)
    if customer is not None and customer.user_id is not None:
        await notifications_service.notify_user(
            db, organization_id=request.organization_id, user_id=customer.user_id,
            type_="CONTRACT_CREATED", entity_type="contract_request", entity_id=request.id,
            title=f"La pratica {_code(request)} è di nuovo modificabile",
            body=(
                "Puoi cambiare i contratti scelti per i tuoi POD e PDR in “I miei Contratti” (Riprendi), "
                "poi inviarla di nuovo e pagare il nuovo totale."
            ),
        )
    await db.commit()
    await db.refresh(request)
    return request, open_sessions


async def cancel_request(db: AsyncSession, *, request: ContractRequest, actor_user_id: uuid.UUID) -> ContractRequest:
    """Abandons a draft pratica and its draft points. A sent pratica is not
    cancelled as a whole: each of its contracts is handled on its own."""
    _assert_draft(request)
    for contract in await list_points(db, request=request):
        if contract.status == "DRAFT":
            await contract_service.transition_contract(
                db, organization_id=request.organization_id, contract=contract, to_status="CANCELLED",
                actor_user_id=actor_user_id, reason="Pratica annullata prima dell'invio", notes=None,
                correlation_id=str(uuid.uuid4()),
            )
    request.status = "CANCELLED"
    request.cancelled_at = request.updated_at = utcnow()
    await audit_service.record(
        db, organization_id=request.organization_id, actor_user_id=actor_user_id,
        action="contract_request.cancelled", entity_type="contract_request", entity_id=str(request.id),
    )
    await db.commit()
    await db.refresh(request)
    return request


# --- Pagamento ---------------------------------------------------------------


def payable_points(points: list[Contract]) -> list[Contract]:
    return [c for c in points if contract_service.is_payable(c)]


@dataclass(frozen=True)
class RequestPlanOption:
    plan: payment_plans.PaymentPlan
    instalment_cents: int
    total_cents: int
    rounding_difference_cents: int
    available: bool
    unavailable_reason: str | None
    #: Session 64: the price before the one-go discount, and the discount.
    list_total_cents: int = 0
    discount_percentage: int = 0
    discount_cents: int = 0


def plan_options(points: list[Contract], *, discount_percentage: int = 0) -> list[RequestPlanOption]:
    """Every plan, priced for these contracts: each contract split on its own
    (exactly the instalment its own schedule will record), then added up. The
    customer sees one monthly figure; each contract still owns its line."""
    options = []
    for plan in payment_plans.PAYMENT_PLANS:
        breakdowns = [
            payment_plans.breakdown_for(
                plan, payment_plans.plan_gross_cents(plan, c),
                discount_percentage=payment_plans.one_go_discount_percentage(c, discount_percentage),
            )
            for c in points
        ]
        reason = None
        if any(b.instalment_cents <= 0 for b in breakdowns):
            reason = "Importo troppo basso per questa modalità."
        elif plan.instalments > 1 and len(points) > MAX_SUBSCRIPTION_LINES:
            reason = (
                f"A rate si possono pagare al massimo {MAX_SUBSCRIPTION_LINES} contratti insieme: "
                "scegli la soluzione unica oppure dividi i punti in due pratiche."
            )
        options.append(
            RequestPlanOption(
                plan=plan,
                instalment_cents=sum(b.instalment_cents for b in breakdowns),
                total_cents=sum(b.total_cents for b in breakdowns),
                rounding_difference_cents=sum(b.rounding_difference_cents for b in breakdowns),
                available=bool(points) and reason is None,
                unavailable_reason=reason,
                list_total_cents=sum(payment_plans.plan_gross_cents(plan, c) for c in points),
                discount_percentage=discount_percentage if any(b.discount_cents for b in breakdowns) else 0,
                discount_cents=sum(b.discount_cents for b in breakdowns),
            )
        )
    return options


async def cashback_total_cents(
    db: AsyncSession, *, points: list[Contract], discount_percentage: int = 0,
    plan: payment_plans.PaymentPlan | None = None,
) -> int:
    """JavCash these contracts earn; with `discount_percentage`, when paid in
    one go at that discount (the cashback follows what is paid); with an
    instalment `plan`, on the rate price (Session 84)."""
    total = 0
    for contract in points:
        if contract.product_version_id is None or not contract.gross_amount_cents:
            continue
        version = await db.get(ProductVersion, contract.product_version_id)
        if version is not None:
            gross = payment_plans.plan_gross_cents(plan, contract) if plan is not None else int(contract.gross_amount_cents)
            paid = gross - payment_plans.discount_cents_for(
                gross, payment_plans.one_go_discount_percentage(contract, discount_percentage)
            )
            total += pricing.contract_cashback_cents(version=version, gross_amount_cents=paid)
    return total


async def apply_checkout(
    db: AsyncSession,
    *,
    checkout: ContractRequestCheckout,
    stripe_invoice_id: str | None,
    stripe_subscription_id: str | None,
    stripe_customer_id: str | None,
    subscription_items: dict[str, str],
) -> str:
    """A Checkout Session of a pratica completed: every contract it covered
    is paid, each exactly as if it had been paid on its own -- its own first
    instalment, its own JavCash, its own activation if already approved.

    `subscription_items` maps contract id -> Stripe subscription item id, for
    an instalment plan: it is what lets each later monthly invoice line find
    its contract (contracts/service.py::record_subscription_invoice).

    A contract already paid by another session (the customer paid twice, in
    two tabs) is not paid again: staff are told to refund that line. Returns
    what happened, in words. Commits."""
    from app.domains.contracts import service as contracts_service

    if checkout.completed_at is not None:
        return f"pratica {str(checkout.contract_request_id)[:8].upper()}: pagamento già registrato"
    if checkout.outcome == UNLOCKED_CHECKOUT_OUTCOME:
        # Opened before «Sblocca pratica», paid anyway from an old tab: its
        # lines are the old packages and prices. Nothing is paid with it.
        code = str(checkout.contract_request_id)[:8].upper()
        checkout.completed_at = utcnow()
        checkout.outcome = "PAGATO DOPO LO SBLOCCO: nessun contratto pagato, da rimborsare"
        await notifications_service.notify_roles(
            db, organization_id=checkout.organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
            type_="CONTRACT_PAID_REJECTED", entity_type="contract_request", entity_id=checkout.contract_request_id,
            title=f"Pratica {code}: pagamento da rimborsare",
            body=(
                "Il cliente ha pagato con carta una pagina di pagamento aperta prima che la pratica fosse "
                "sbloccata. Nessun contratto è stato segnato come pagato: rimborsa il pagamento da Stripe."
            ),
        )
        await db.commit()
        return f"pratica {code}: pagata dopo lo sblocco, da rimborsare"

    plan = payment_plans.plan_by_key(checkout.payment_plan)
    request = await db.get(ContractRequest, checkout.contract_request_id)
    paid: list[Contract] = []
    duplicates: list[Contract] = []
    for line in checkout.lines:
        contract = await db.get(Contract, uuid.UUID(line["contract_id"]))
        if contract is None or contract.contract_request_id != checkout.contract_request_id:
            continue
        if contract.paid_at is not None:
            duplicates.append(contract)
            continue
        contract.payment_plan = checkout.payment_plan
        contract.payment_method = "CARD"
        contract.payment_discount_cents = (
            int(line.get("discount_cents") or 0) if plan is not None and plan.instalments <= 1 else 0
        )
        if stripe_subscription_id:
            contract.stripe_subscription_id = stripe_subscription_id
            contract.stripe_subscription_item_id = subscription_items.get(str(contract.id))
            contract.stripe_customer_id = stripe_customer_id
        contract.updated_at = utcnow()
        await db.commit()
        contract = await contracts_service.record_card_payment(
            db, organization_id=checkout.organization_id, contract=contract,
            stripe_invoice_id=stripe_invoice_id, notify_staff=False,
        )
        if plan is not None and plan.instalments > 1:
            await contracts_service.credit_contract_instalment_cashback(
                db, organization_id=checkout.organization_id, contract=contract, instalment_number=1
            )
        paid.append(contract)

    code = str(checkout.contract_request_id)[:8].upper()
    checkout.completed_at = utcnow()
    checkout.stripe_subscription_id = stripe_subscription_id
    checkout.stripe_customer_id = stripe_customer_id
    outcome = f"pratica {code}: {len(paid)} contratti pagati"
    if duplicates:
        outcome += f", {len(duplicates)} già pagati in precedenza"
    checkout.outcome = outcome[:255]

    if paid:
        await notifications_service.notify_roles(
            db, organization_id=checkout.organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
            type_="CONTRACT_PAID_BEFORE_APPROVAL", entity_type="contract_request", entity_id=checkout.contract_request_id,
            title=f"Pratica {code} pagata: {len(paid)} {'contratto' if len(paid) == 1 else 'contratti'}",
            body=(
                f"Pagamento con carta ({plan.label.lower() if plan else checkout.payment_plan}). "
                "Ogni contratto si attiva appena approvi i suoi documenti e accetti la sua anteprima provvigioni."
            ),
        )
        customer = await db.get(Customer, request.customer_id) if request else None
        if customer is not None and customer.user_id is not None:
            await notifications_service.notify_user(
                db, organization_id=checkout.organization_id, user_id=customer.user_id,
                type_="CONTRACT_PAID_BEFORE_APPROVAL", entity_type="contract_request",
                entity_id=checkout.contract_request_id,
                title="Pagamento ricevuto",
                body=(
                    f"Abbiamo ricevuto il pagamento della pratica {code}. "
                    "Ogni contratto si attiva appena i suoi documenti sono approvati."
                ),
            )
    if duplicates:
        await notifications_service.notify_roles(
            db, organization_id=checkout.organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
            type_="CONTRACT_PAID_REJECTED", entity_type="contract_request", entity_id=checkout.contract_request_id,
            title=f"Pagamento doppio sulla pratica {code}",
            body=(
                f"{len(duplicates)} contratti erano già stati pagati: "
                + ", ".join(_code(c) for c in duplicates)
                + ". Rimborsa quelle righe su Stripe" + (" e interrompi i loro addebiti." if stripe_subscription_id else ".")
            ),
        )
    await db.commit()
    return outcome


# --- Pagamento con bonifico (Session 65) ---------------------------------------


class BankTransferError(Exception):
    pass


def bank_transfer_pending(request: ContractRequest, points: list[Contract]) -> bool:
    """Announced by the customer, not yet confirmed, and still something to
    pay by transfer (a card payment afterwards settles it too)."""
    return (
        request.bank_transfer_requested_at is not None
        and request.bank_transfer_confirmed_at is None
        and any(c.payment_method == "BANK_TRANSFER" and contract_service.is_payable(c) for c in points)
    )


async def request_bank_transfer(
    db: AsyncSession, *, request: ContractRequest, actor_user_id: uuid.UUID
) -> ContractRequest:
    """The customer pays the whole pratica by transfer: a single payment, at
    the full one-go price -- no discount for paying by bank transfer
    (Session 86, business decision; until then the one-go card discount
    applied to a transfer too). Nothing is paid until an administrator
    confirms the money arrived. Commits."""
    from app.domains.organizations import service as organizations_service

    if not await organizations_service.is_bank_transfer_configured(db, organization_id=request.organization_id):
        raise BankTransferError("Il pagamento con bonifico non è disponibile al momento.")
    points = payable_points(await list_points(db, request=request))
    if not points:
        raise BankTransferError("In questa pratica non c'è nessun contratto da pagare.")
    percentage = 0
    total = 0
    for contract in points:
        gross = int(contract.gross_amount_cents or 0)
        contract.payment_plan = payment_plans.PLAN_FULL
        contract.payment_method = "BANK_TRANSFER"
        contract.payment_discount_cents = 0
        contract.updated_at = utcnow()
        total += gross
    request.bank_transfer_requested_at = utcnow()
    request.bank_transfer_total_cents = total
    request.bank_transfer_confirmed_at = None
    request.bank_transfer_confirmed_by_user_id = None
    request.updated_at = utcnow()
    code = _code(request)
    await audit_service.record(
        db, organization_id=request.organization_id, actor_user_id=actor_user_id,
        action="contract_request.bank_transfer_requested", entity_type="contract_request",
        entity_id=str(request.id), new_value={"total_cents": total, "contracts": len(points), "discount": percentage},
    )
    await notifications_service.notify_roles(
        db, organization_id=request.organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="CONTRACT_REQUEST_BANK_TRANSFER", entity_type="contract_request", entity_id=request.id,
        title=f"Pratica {code}: il cliente paga con bonifico",
        body=f"{total / 100:.2f} EUR per {len(points)} {'contratto' if len(points) == 1 else 'contratti'}. "
             "Conferma quando lo ricevi, dalla pratica.",
        exclude_user_id=actor_user_id,
    )
    await db.commit()
    await db.refresh(request)
    return request


async def upload_bank_transfer_proof(
    db: AsyncSession, *, request: ContractRequest, file_bytes: bytes, content_type: str, original_filename: str,
    actor_user_id: uuid.UUID,
) -> ContractRequest:
    from app.core.storage import UploadValidationError
    from app.core.storage import upload_document as storage_upload_document

    if not bank_transfer_pending(request, await list_points(db, request=request)):
        raise BankTransferError("La ricevuta si carica per una pratica in attesa di bonifico.")
    try:
        key = storage_upload_document(
            file_bytes=file_bytes, content_type=content_type,
            key_prefix=f"contract-request-payment-proofs/{request.id}",
        )
    except UploadValidationError as exc:
        raise BankTransferError(str(exc)) from exc
    request.payment_proof_storage_key = key
    request.payment_proof_original_filename = original_filename[:255]
    request.payment_proof_uploaded_at = utcnow()
    await notifications_service.notify_roles(
        db, organization_id=request.organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="CONTRACT_REQUEST_BANK_TRANSFER", entity_type="contract_request", entity_id=request.id,
        title=f"Pratica {_code(request)}: ricevuta del bonifico caricata", body=None, exclude_user_id=actor_user_id,
    )
    await db.commit()
    await db.refresh(request)
    return request


def payment_proof_url(request: ContractRequest) -> str | None:
    from app.core.storage import generate_presigned_document_url

    if not request.payment_proof_storage_key:
        return None
    return generate_presigned_document_url(storage_key=request.payment_proof_storage_key, expires_in_seconds=300)


async def confirm_bank_transfer(
    db: AsyncSession, *, request: ContractRequest, actor_user_id: uuid.UUID
) -> list[Contract]:
    """An administrator saw the transfer arrive: every contract announced for
    transfer is paid, each exactly as a card payment would record it (its
    instalment row at the discounted price, its JavCash, its activation if
    already approved). Returns the contracts paid. Commits."""
    from app.domains.contracts import service as contracts_service

    points = await list_points(db, request=request)
    if not bank_transfer_pending(request, points):
        raise BankTransferError("Questa pratica non ha un bonifico in attesa di conferma.")
    paid = []
    for contract in points:
        if contract.payment_method != "BANK_TRANSFER" or not contract_service.is_payable(contract):
            continue
        contract = await contracts_service.record_card_payment(
            db, organization_id=request.organization_id, contract=contract, notify_staff=False,
            bank_transfer_confirmed_by=actor_user_id,
        )
        paid.append(contract)
    request.bank_transfer_confirmed_at = utcnow()
    request.bank_transfer_confirmed_by_user_id = actor_user_id
    request.updated_at = utcnow()
    code = _code(request)
    await audit_service.record(
        db, organization_id=request.organization_id, actor_user_id=actor_user_id,
        action="contract_request.bank_transfer_confirmed", entity_type="contract_request",
        entity_id=str(request.id), new_value={"contracts": [str(c.id) for c in paid]},
    )
    customer = await db.get(Customer, request.customer_id)
    if customer is not None and customer.user_id is not None:
        await notifications_service.notify_user(
            db, organization_id=request.organization_id, user_id=customer.user_id,
            type_="CONTRACT_PAID_BEFORE_APPROVAL", entity_type="contract_request", entity_id=request.id,
            title="Bonifico ricevuto",
            body=f"Abbiamo ricevuto il bonifico della pratica {code}. "
                 "Ogni contratto si attiva appena i suoi documenti sono approvati.",
        )
    await db.commit()
    await db.refresh(request)
    return paid


# --- Letture ------------------------------------------------------------------


async def _instalment_summary(db: AsyncSession, contract_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
    if not contract_ids:
        return {}
    rows = list(
        (await db.execute(select(ContractInstalment).where(ContractInstalment.contract_id.in_(contract_ids)))).scalars()
    )
    out: dict[uuid.UUID, dict] = {}
    for row in rows:
        entry = out.setdefault(row.contract_id, {"total": row.instalments_total, "paid": 0, "failed": 0})
        if row.status == "PAID":
            entry["paid"] += 1
        elif row.status == "FAILED":
            entry["failed"] += 1
    return out


async def summaries(db: AsyncSession, requests: list[ContractRequest]) -> list[dict]:
    """The row every list shows -- customer, promoter area and staff alike --
    computed from the contracts, never stored twice: how many points, how
    many active, how many waiting for review, what it costs, what is paid."""
    if not requests:
        return []
    request_ids = [r.id for r in requests]
    contracts = list(
        (
            await db.execute(
                select(Contract).where(Contract.contract_request_id.in_(request_ids)).order_by(Contract.created_at)
            )
        ).scalars()
    )
    by_request: dict[uuid.UUID, list[Contract]] = {}
    for c in contracts:
        if c.status == "CANCELLED" and c.activated_at is None:
            continue
        by_request.setdefault(c.contract_request_id, []).append(c)

    customer_ids = {r.customer_id for r in requests}
    customers = {
        c.id: c for c in (await db.execute(select(Customer).where(Customer.id.in_(customer_ids)))).scalars()
    }
    customer_names = {cid: await _customer_name(db, customers.get(cid)) for cid in customer_ids}
    agent_ids = {r.activated_by_promoter_id for r in requests if r.activated_by_promoter_id}
    agent_names = (
        {
            a.id: a.display_name
            for a in (await db.execute(select(AgentProfile).where(AgentProfile.id.in_(agent_ids)))).scalars()
        }
        if agent_ids
        else {}
    )
    instalments = await _instalment_summary(db, [c.id for c in contracts])

    out = []
    for r in requests:
        points = by_request.get(r.id, [])
        live = [c for c in points if c.status not in ("REJECTED", "CANCELLED")]
        statuses: dict[str, int] = {}
        for c in points:
            statuses[c.status] = statuses.get(c.status, 0) + 1
        out.append({
            "id": r.id,
            "code": _code(r),
            "customer_id": r.customer_id,
            "customer_name": customer_names.get(r.customer_id),
            # Session 85: the pratica's own kind (privato / azienda).
            "customer_kind": pratica_kind(r, customers.get(r.customer_id)),
            "holder_kind": r.holder_kind,
            "status": r.status,
            "created_at": r.created_at,
            "submitted_at": r.submitted_at,
            "updated_at": r.updated_at,
            "created_by_role": r.created_by_role,
            "notes": r.notes,
            "activated_by_promoter_id": r.activated_by_promoter_id,
            "activated_by_promoter_name": agent_names.get(r.activated_by_promoter_id) if r.activated_by_promoter_id else None,
            "holder_name": " ".join(x for x in (r.holder_first_name, r.holder_last_name) if x) or None,
            "points_total": len(points),
            "points_by_status": statuses,
            "points_active": sum(1 for c in points if c.status in ("ACTIVE", "RENEWED")),
            "points_to_review": statuses.get("UNDER_REVIEW", 0),
            "points_documents_pending": statuses.get("DOCUMENTS_PENDING", 0),
            "points_without_package": sum(1 for c in points if c.product_version_id is None),
            "points_paid": sum(1 for c in live if c.paid_at is not None),
            "points_payable": sum(1 for c in live if contract_service.is_payable(c)),
            "total_gross_cents": sum(
                payment_plans.plan_gross_cents(payment_plans.plan_by_key(c.payment_plan), c)
                if c.paid_at is not None and payment_plans.plan_by_key(c.payment_plan) is not None
                else int(c.gross_amount_cents or 0)
                for c in live
            ),
            "payment_plans": sorted({c.payment_plan for c in live if c.paid_at is not None and c.payment_plan}),
            "instalments_failed": sum(instalments.get(c.id, {}).get("failed", 0) for c in live),
            "bank_transfer_pending": bank_transfer_pending(r, points),
            "bank_transfer_total_cents": r.bank_transfer_total_cents,
            "bank_transfer_requested_at": r.bank_transfer_requested_at,
            "payment_proof_uploaded_at": r.payment_proof_uploaded_at,
            "total_paid_cents": sum(payment_plans.paid_gross_cents(c) for c in live if c.paid_at is not None),
        })
    return out


async def _notes_author(db: AsyncSession, request: ContractRequest) -> str | None:
    """Who wrote the notes, as staff should read it: the promoter by name,
    the customer as such, or the staff member's email."""
    from app.domains.users.models import User

    if request.notes_updated_by_user_id is None:
        return None
    agent = (
        await db.execute(
            select(AgentProfile).where(
                AgentProfile.organization_id == request.organization_id,
                AgentProfile.user_id == request.notes_updated_by_user_id,
            )
        )
    ).scalar_one_or_none()
    customer = await db.get(Customer, request.customer_id)
    if customer is not None and customer.user_id == request.notes_updated_by_user_id:
        return f"Cliente ({await _customer_name(db, customer)})"
    if agent is not None:
        return f"Promoter {agent.display_name}"
    user = await db.get(User, request.notes_updated_by_user_id)
    return user.email if user else None


async def detail(db: AsyncSession, *, request: ContractRequest, include_checkouts: bool) -> dict:
    """Everything one screen needs about a pratica: the summary, the holder,
    and every point with its supply address, package, price, documents
    completeness and instalments."""
    from app.domains.documents import service as documents_service

    [summary] = await summaries(db, [request])
    points = await list_points(db, request=request)
    # POD first, then PDR, each numbered on its own: "POD 1, POD 2, PDR 1".
    point_types = {c.id: (await db.get(SupplyPoint, c.supply_point_id)) for c in points}
    point_types = {cid: (sp.energy_type if sp else None) for cid, sp in point_types.items()}
    points.sort(key=lambda c: (point_types[c.id] == PDR, c.created_at))
    positions: dict[uuid.UUID, int] = {}
    seen: dict[str, int] = {}
    for c in points:
        kind = point_kind_label(point_types[c.id])
        seen[kind] = seen.get(kind, 0) + 1
        positions[c.id] = seen[kind]
    rows = await contract_service.to_read_dicts(db, points)
    customer = await db.get(Customer, request.customer_id)
    kind = pratica_kind(request, customer)
    instalments = await _instalment_summary(db, [c.id for c in points])

    enriched = []
    for contract, row in zip(points, rows, strict=True):
        supply_point = await db.get(SupplyPoint, contract.supply_point_id)
        address = await db.get(Address, supply_point.supply_address_id) if supply_point else None
        slots = await documents_service.get_contract_documents_status(
            db, organization_id=request.organization_id, contract=contract, customer_kind=kind
        )
        product = None
        if contract.product_version_id is not None:
            version = await db.get(ProductVersion, contract.product_version_id)
            product = await db.get(Product, version.product_id) if version else None
        enriched.append({
            **row,
            "position": positions[contract.id],
            "point_kind": point_kind_label(point_types[contract.id]),
            "meter_number": supply_point.meter_number if supply_point else None,
            "street": address.street if address else None,
            "city": address.city if address else None,
            "province": address.province if address else None,
            "postal_code": address.postal_code if address else None,
            "product_id": product.id if product else None,
            "documents_missing": sum(1 for s in slots if s["required"] and s["document"] is None),
            "documents_rejected": sum(1 for s in slots if s["document"] is not None and s["document"].status == "REJECTED"),
            "instalments_total": instalments.get(contract.id, {}).get("total"),
            "instalments_paid": instalments.get(contract.id, {}).get("paid", 0),
            "instalments_failed": instalments.get(contract.id, {}).get("failed", 0),
            #: Stripe is still charging this contract every month -- what the
            #: "Interrompi addebiti" action applies to.
            "billing_active": contract.stripe_subscription_id is not None and contract.billing_stopped_at is None,
        })

    out = {
        **summary,
        "street": request.street,
        "city": request.city,
        "province": request.province,
        "postal_code": request.postal_code,
        "holder_first_name": request.holder_first_name,
        "holder_last_name": request.holder_last_name,
        "email": request.email,
        "pec": request.pec,
        "iban": request.iban,
        "company_name": request.company_name,
        "legal_rep_fiscal_code": request.legal_rep_fiscal_code,
        "holder_fiscal_code": request.holder_fiscal_code,
        "holder_birth_date": request.holder_birth_date,
        "holder_birth_place": request.holder_birth_place,
        "holder_birth_place_code": request.holder_birth_place_code,
        "fiscal_code_problems": fiscal_code_problems(request),
        "points": enriched,
        "checkouts": [],
        #: What the documents step still lacks (Session 82) -- the wizard
        #: will not go past it, and submit_request refuses, until empty.
        "notes_updated_at": request.notes_updated_at,
        "notes_author": await _notes_author(db, request),
        "documents_blocking": await documents_service.pratica_blocking_missing(
            db, request=request, customer_kind=kind
        ),
    }
    if include_checkouts:
        checkouts = list(
            (
                await db.execute(
                    select(ContractRequestCheckout)
                    .where(ContractRequestCheckout.contract_request_id == request.id)
                    .order_by(ContractRequestCheckout.created_at.desc())
                )
            ).scalars()
        )
        out["checkouts"] = [
            {
                "id": c.id,
                "created_at": c.created_at,
                "payment_plan": c.payment_plan,
                "total_cents": c.total_cents,
                "instalment_cents": c.instalment_cents,
                "contracts": len(c.lines),
                "completed_at": c.completed_at,
                "stripe_checkout_session_id": c.stripe_checkout_session_id,
                "stripe_subscription_id": c.stripe_subscription_id,
                "outcome": c.outcome,
            }
            for c in checkouts
        ]
    return out
