"""La pratica: più contratti, compilati e pagati insieme.

Business rule, as the business put it: a customer who signs up
for ten services has ten contracts -- ten for the customer, ten for the
promoter, each with its own package, its own approval, its own instalments
and its own commissions -- but the customer fills in who they are once,
uploads their identity once, chooses a package for each contract, and pays
once.

In the code a contract of the pratica is called a "point" (a line of the
pratica): the routes and the dashboard speak of points, the database of
contracts.

The flow a pratica follows, as the business asked:

1. Everything once, at the start: holder (nome, cognome, email, PEC, IBAN),
   address, and how many contracts. The pratica is created DRAFT with that
   many points already there -- each a real DRAFT contract, so a
   half-finished pratica survives a closed browser.
2. Shared documents (identity, fiscal code...), once, on the pratica.
3. For each point, the package to activate; its price is frozen on the
   contract then.
4. Submit: every point leaves DRAFT together and enters the ordinary review
   flow. From here on each contract lives its own life.
5. Payment (customer only): one bank transfer for every payable contract in
   the pratica, with the plan the customer chose -- the whole amount, or the
   first instalment of each. An administrator confirms it arrived
   (confirm_bank_transfer), and every later instalment one by one
   (instalments.py::confirm_manually).

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
)
from app.domains.customers.models import Company, Customer, CustomerProfile
from app.domains.network.models import AgentProfile
from app.domains.notifications import service as notifications_service

#: Beyond this many contracts at once it is a job for the back office, not a
#: web form.
MAX_POINTS_PER_REQUEST = 50


class ContractRequestError(Exception):
    pass


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
    #: PRIVATE or a business kind; None = the customer's kind.
    kind: str | None = None
    #: A business pratica only: ragione sociale and the legal
    #: representative's fiscal code (first/last name above are theirs).
    company_name: str | None = None
    legal_rep_fiscal_code: str | None = None
    #: A private holder's fiscal code; the birth date and place
    #: (Belfiore code) of whoever is named above, holder or legal rep.
    fiscal_code: str | None = None
    birth_date: date | None = None
    birth_place_code: str | None = None


#: What the pratica's data form may say the contracts are for.
PRATICA_KINDS = frozenset({"PRIVATE", "SOLE_PROPRIETOR", "COMPANY", "CONDOMINIUM"})


def pratica_kind(request: ContractRequest, customer: Customer | None) -> str:
    """Who the contracts of this pratica are for: the kind chosen
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
    sociale and their fiscal code are required, their name is
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
    """Everyone who signs -- the private holder or the legal
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
    date and place -- a warning, never a block. Empty for a
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
            "La pratica è già stata inviata: i contratti scelti non si possono più modificare. "
            "Per aggiungere un altro contratto apri una nuova pratica."
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
    product_version_id: uuid.UUID | None = None,
) -> ContractRequest:
    """Opens a DRAFT pratica with its holder, its address and `points_count`
    points already created, each a DRAFT contract waiting for its package.
    `product_version_id` (the customer started from a package in the
    catalog) pre-chooses it for every point.

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
        new_value={"customer_id": str(customer_id), "created_by_role": actor_role, "points": points_count},
    )
    await db.commit()
    await db.refresh(request)
    await set_points_count(db, request=request, count=points_count, actor_user_id=actor_user_id)
    if product_version_id is not None:
        await set_product_for_all(
            db, request=request, product_version_id=product_version_id, actor_user_id=actor_user_id,
        )
    await db.refresh(request)
    return request


async def update_holder(
    db: AsyncSession, *, request: ContractRequest, holder: HolderData, actor_user_id: uuid.UUID
) -> ContractRequest:
    """Holder data and address can change while the pratica is a draft, and
    every point follows. Commits."""
    _assert_draft(request)
    customer = await db.get(Customer, request.customer_id)
    kind = _holder_kind(customer, holder)
    _check_holder(kind, holder)
    previous_kind = pratica_kind(request, customer)
    _apply_holder_kind(request, kind, holder)
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


# --- I contratti della pratica ------------------------------------------------


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


async def add_point(db: AsyncSession, *, request: ContractRequest, actor_user_id: uuid.UUID) -> Contract:
    """One more contract in a draft pratica: a DRAFT contract with no package
    yet. Commits."""
    _assert_draft(request)
    if len(await list_points(db, request=request)) >= MAX_POINTS_PER_REQUEST:
        raise ContractRequestError(
            f"Una pratica può contenere al massimo {MAX_POINTS_PER_REQUEST} contratti: "
            "per gli altri apri una seconda pratica."
        )
    producer_agent_id, substituted_for = await _producer_for_new_point(db, request=request)

    try:
        contract = await contract_service.create_contract(
            db, organization_id=request.organization_id, customer_id=request.customer_id,
            product_version_id=None,
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
    db: AsyncSession, *, request: ContractRequest, count: int, actor_user_id: uuid.UUID
) -> list[Contract]:
    """"Quanti contratti?": adds or removes points until the pratica has
    exactly that many. Removing takes the most recent points first, and
    among them the ones without a package chosen -- never the work already
    done when there is an empty point to drop instead. Commits."""
    _assert_draft(request)
    if count < 1:
        raise ContractRequestError("Una pratica deve avere almeno un contratto.")
    if count > MAX_POINTS_PER_REQUEST:
        raise ContractRequestError(
            f"Una pratica può contenere al massimo {MAX_POINTS_PER_REQUEST} contratti: "
            "per gli altri apri una seconda pratica."
        )
    points = await list_points(db, request=request)
    excess = len(points) - count
    if excess > 0:
        drafts = [c for c in points if c.status == "DRAFT"]
        removable = sorted(drafts, key=lambda c: (c.product_version_id is not None, -c.created_at.timestamp()))
        if len(removable) < excess:
            raise ContractRequestError(f"Non si possono togliere {excess} contratti: alcuni non sono più modificabili.")
        for contract in removable[:excess]:
            await _cancel_point(db, request=request, contract=contract, actor_user_id=actor_user_id)
    for _ in range(max(0, -excess)):
        await add_point(db, request=request, actor_user_id=actor_user_id)
    return await list_points(db, request=request)


async def get_point(db: AsyncSession, *, request: ContractRequest, contract_id: uuid.UUID) -> Contract:
    contract = await db.get(Contract, contract_id)
    if contract is None or contract.contract_request_id != request.id:
        raise ContractRequestError("Contratto non trovato in questa pratica.")
    return contract


async def remove_point(
    db: AsyncSession, *, request: ContractRequest, contract: Contract, actor_user_id: uuid.UUID
) -> None:
    """Takes a contract out of a draft pratica. The contract is CANCELLED,
    not deleted: its creation is already in the audit trail and the history
    should say what became of it. The last one cannot go."""
    _assert_draft(request)
    if contract.status != "DRAFT":
        raise ContractRequestError("Questo contratto non si può più togliere dalla pratica.")
    if len(await list_points(db, request=request)) <= 1:
        raise ContractRequestError("Una pratica deve avere almeno un contratto.")
    await _cancel_point(db, request=request, contract=contract, actor_user_id=actor_user_id)


async def _cancel_point(
    db: AsyncSession, *, request: ContractRequest, contract: Contract, actor_user_id: uuid.UUID
) -> None:
    await contract_service.transition_contract(
        db, organization_id=request.organization_id, contract=contract, to_status="CANCELLED",
        actor_user_id=actor_user_id, reason="Contratto tolto dalla pratica prima dell'invio", notes=None,
        correlation_id=str(uuid.uuid4()),
    )
    request.updated_at = utcnow()
    await db.commit()


async def _assign_package(db: AsyncSession, *, contract: Contract, version: ProductVersion, product: Product) -> None:
    """Freezes the price of the chosen package on the contract. Does not
    commit."""
    await contract_service.freeze_price(db, contract=contract, version=version, customer_kind=await contract_kind(db, contract))


async def set_point_product(
    db: AsyncSession, *, request: ContractRequest, contract: Contract, product_version_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> Contract:
    """Chooses (or changes) the package of one contract. Commits."""
    _assert_draft(request)
    if contract.status != "DRAFT":
        raise ContractRequestError("Il pacchetto di questo contratto non si può più cambiare.")
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
#: yet and nothing has been activated. Without this, a package chosen
#: wrongly by the customer could only be fixed by rejecting the contract
#: and starting a new pratica.
STAFF_REPACKAGE_STATUSES = frozenset(
    {"DRAFT", "SUBMITTED", "DOCUMENTS_PENDING", "UNDER_REVIEW", "APPROVED", "PAYMENT_PENDING"}
)


async def staff_set_point_product(
    db: AsyncSession, *, request: ContractRequest, contract: Contract, product_version_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> Contract:
    """An administrator fixes the package of one contract, also on a pratica
    already sent -- never once it is paid or active, because the price is
    frozen at payment and the commissions follow it. Commits."""
    if contract.paid_at is not None:
        raise ContractRequestError(
            "Questo contratto è già pagato: il pacchetto non si cambia più. Respingilo e apri una nuova pratica."
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
) -> int:
    """"Stesso pacchetto per tutti": applied to every draft contract of the
    pratica. Returns how many received it. Commits."""
    _assert_draft(request)
    version, product = await _load_package(db, request=request, product_version_id=product_version_id)
    applied = 0
    for contract in await list_points(db, request=request):
        if contract.status != "DRAFT":
            continue
        await _assign_package(db, contract=contract, version=version, product=product)
        applied += 1
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
        raise ContractRequestError("Aggiungi almeno un contratto prima di inviare la pratica.")
    missing = [p for p in points if p.product_version_id is None]
    if missing:
        raise ContractRequestError(
            f"Scegli il pacchetto per {'il contratto' if len(missing) == 1 else f'i {len(missing)} contratti'} "
            "ancora senza, poi invia la pratica."
        )
    if not (request.holder_first_name and request.holder_last_name and request.email and _request_address(request)):
        raise ContractRequestError("Completa i dati dell'intestatario e l'indirizzo prima di inviare la pratica.")
    if not (request.holder_birth_date and request.holder_birth_place_code):
        # A draft saved before these were asked: the data form asks them now.
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
    # administration: either way the customer is the one who
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
                    f"{len(points)} {'contratto' if len(points) == 1 else 'contratti'}. "
                    "Controllala in “I miei Contratti” e procedi con il pagamento."
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
    or the administration: the customer is the one
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
        f"<strong>{len(points)} {'contratto' if len(points) == 1 else 'contratti'}</strong>, "
        f"per un totale di <strong>{total / 100:.2f} €</strong> in un'unica soluzione.</p>"
        "<p>Accedi alla tua area, controlla i contratti in "
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
            f"{len(points)} {'contratto' if len(points) == 1 else 'contratti'}. "
            "Accedi a I miei Contratti per controllarla e pagare."
        ),
    )



async def unlock_request(
    db: AsyncSession, *, request: ContractRequest, actor_user_id: uuid.UUID
) -> ContractRequest:
    """«Sblocca pratica»: a pratica sent but not paid goes back
    to draft -- every contract still alive with it -- so the customer, their
    promoter or staff can choose the packages again, then send it and pay
    the new total. Approvals already given are lost: the pratica is reviewed
    again once sent.

    Refused when anything was paid (a contract, an instalment), or once the
    customer uploaded a bank transfer receipt. A transfer only announced is
    undone (the total will change). Commits."""
    if request.status != "SUBMITTED":
        raise ContractRequestError("Si sblocca solo una pratica inviata e non ancora pagata.")
    points = await list_points(db, request=request)
    live = [c for c in points if c.status not in ("CANCELLED", "REJECTED")]
    if not live:
        raise ContractRequestError("Questa pratica non ha contratti da riaprire.")
    if any(c.paid_at is not None for c in points):
        raise ContractRequestError("La pratica è già pagata, anche solo in parte: non si può sbloccare.")
    paid_instalment = (
        await db.execute(
            select(ContractInstalment.id).where(
                ContractInstalment.contract_id.in_([c.id for c in points]), ContractInstalment.status == "PAID"
            )
        )
    ).first()
    if paid_instalment is not None:
        raise ContractRequestError("Una rata della pratica è già pagata: non si può sbloccare.")
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
    request.bank_transfer_requested_at = None
    request.bank_transfer_total_cents = None
    request.status = "DRAFT"
    request.submitted_at = None
    request.updated_at = utcnow()
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
                "Puoi cambiare i pacchetti scelti in “I miei Contratti” (Riprendi), "
                "poi inviarla di nuovo e pagare il nuovo totale."
            ),
        )
    await db.commit()
    await db.refresh(request)
    return request


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


async def point_labels(db: AsyncSession, points: list[Contract]) -> dict[uuid.UUID, str]:
    """"Abbonamento annuale — Contratto 1A2B3C4D": what the customer sees on
    the payment screen, one line per contract."""
    out = {}
    for contract in points:
        version = await db.get(ProductVersion, contract.product_version_id) if contract.product_version_id else None
        point = f"Contratto {str(contract.id)[:8].upper()}"
        out[contract.id] = f"{version.name} — {point}" if version else point
    return out


@dataclass(frozen=True)
class RequestPlanOption:
    plan: payment_plans.PaymentPlan
    instalment_cents: int
    total_cents: int
    rounding_difference_cents: int
    available: bool
    unavailable_reason: str | None


def plan_options(points: list[Contract]) -> list[RequestPlanOption]:
    """Every plan, priced for these contracts: each contract split on its own
    (exactly the instalment its own schedule will record), then added up. The
    customer sees one transfer amount per month; each contract still owns its
    instalment."""
    options = []
    for plan in payment_plans.PAYMENT_PLANS:
        breakdowns = [payment_plans.contract_breakdown(plan, c) for c in points]
        reason = None
        if any(b.instalment_cents <= 0 for b in breakdowns):
            reason = "Importo troppo basso per questa modalità."
        options.append(
            RequestPlanOption(
                plan=plan,
                instalment_cents=sum(b.instalment_cents for b in breakdowns),
                total_cents=sum(b.total_cents for b in breakdowns),
                rounding_difference_cents=sum(b.rounding_difference_cents for b in breakdowns),
                available=bool(points) and reason is None,
                unavailable_reason=reason,
            )
        )
    return options


async def cashback_total_cents(
    db: AsyncSession, *, points: list[Contract], plan: payment_plans.PaymentPlan | None = None,
) -> int:
    """JavCash these contracts earn: in one go on the one-go price, with an
    instalment `plan` on the rate price."""
    total = 0
    for contract in points:
        if contract.product_version_id is None or not contract.gross_amount_cents:
            continue
        version = await db.get(ProductVersion, contract.product_version_id)
        if version is not None:
            gross = payment_plans.plan_gross_cents(plan, contract) if plan is not None else int(contract.gross_amount_cents)
            total += pricing.contract_cashback_cents(version=version, gross_amount_cents=gross)
    return total


# --- Pagamento con bonifico ---------------------------------------------------


class BankTransferError(Exception):
    pass


def bank_transfer_pending(request: ContractRequest, points: list[Contract]) -> bool:
    """Announced by the customer, not yet confirmed, and still something to
    pay by transfer."""
    return (
        request.bank_transfer_requested_at is not None
        and request.bank_transfer_confirmed_at is None
        and any(c.payment_method == "BANK_TRANSFER" and contract_service.is_payable(c) for c in points)
    )


async def request_bank_transfer(
    db: AsyncSession, *, request: ContractRequest, actor_user_id: uuid.UUID,
    plan_key: str = payment_plans.PLAN_FULL,
) -> ContractRequest:
    """The customer pays the pratica by transfer, with the plan they chose:
    the whole amount in one transfer, or the first instalment of each
    contract now and the others a month apart. Never a discount for paying
    by bank transfer (business decision). Nothing is paid until an
    administrator confirms the money arrived. Commits."""
    from app.domains.organizations import service as organizations_service

    if not await organizations_service.is_bank_transfer_configured(db, organization_id=request.organization_id):
        raise BankTransferError("Il pagamento con bonifico non è disponibile al momento.")
    plan = payment_plans.plan_by_key(plan_key)
    if plan is None:
        raise BankTransferError("Modalità di pagamento non valida.")
    points = payable_points(await list_points(db, request=request))
    if not points:
        raise BankTransferError("In questa pratica non c'è nessun contratto da pagare.")
    option = next(o for o in plan_options(points) if o.plan.key == plan.key)
    if not option.available:
        raise BankTransferError(option.unavailable_reason or "Questa modalità di pagamento non è disponibile.")
    total = 0
    for contract in points:
        contract.payment_plan = plan.key
        contract.payment_method = "BANK_TRANSFER"
        contract.updated_at = utcnow()
        # The first transfer: the whole amount, or each contract's first instalment.
        total += payment_plans.contract_breakdown(plan, contract).instalment_cents
    request.bank_transfer_requested_at = utcnow()
    request.bank_transfer_total_cents = total
    request.bank_transfer_confirmed_at = None
    request.bank_transfer_confirmed_by_user_id = None
    request.updated_at = utcnow()
    code = _code(request)
    await audit_service.record(
        db, organization_id=request.organization_id, actor_user_id=actor_user_id,
        action="contract_request.bank_transfer_requested", entity_type="contract_request",
        entity_id=str(request.id), new_value={"total_cents": total, "contracts": len(points), "payment_plan": plan.key},
    )
    first = "" if plan.instalments <= 1 else f" (prima rata di {plan.instalments})"
    await notifications_service.notify_roles(
        db, organization_id=request.organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="CONTRACT_REQUEST_BANK_TRANSFER", entity_type="contract_request", entity_id=request.id,
        title=f"Pratica {code}: il cliente paga con bonifico",
        body=f"{total / 100:.2f} EUR{first} per {len(points)} {'contratto' if len(points) == 1 else 'contratti'}. "
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
    """An administrator saw the (first) transfer arrive: every contract
    announced for transfer is paid, each on its own -- its first instalment
    row, its JavCash, its activation if already approved. Later instalments
    are confirmed one by one (instalments.py::confirm_manually). Returns the
    contracts paid. Commits."""
    from app.domains.contracts import service as contracts_service

    points = await list_points(db, request=request)
    if not bank_transfer_pending(request, points):
        raise BankTransferError("Questa pratica non ha un bonifico in attesa di conferma.")
    paid = []
    for contract in points:
        if contract.payment_method != "BANK_TRANSFER" or not contract_service.is_payable(contract):
            continue
        contract = await contracts_service.record_transfer_payment(
            db, organization_id=request.organization_id, contract=contract,
            confirmed_by_user_id=actor_user_id, notify_staff=False,
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
        entry = out.setdefault(row.contract_id, {"total": row.instalments_total, "paid": 0})
        if row.status == "PAID":
            entry["paid"] += 1
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
            # The pratica's own kind (privato / azienda).
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


async def detail(db: AsyncSession, *, request: ContractRequest) -> dict:
    """Everything one screen needs about a pratica: the summary, the holder,
    and every contract with its package, price, documents completeness and
    instalments."""
    from app.domains.documents import service as documents_service

    [summary] = await summaries(db, [request])
    points = await list_points(db, request=request)
    # Numbered in the order they were added: "Contratto 1, Contratto 2".
    positions = {c.id: n for n, c in enumerate(points, start=1)}
    rows = await contract_service.to_read_dicts(db, points)
    customer = await db.get(Customer, request.customer_id)
    kind = pratica_kind(request, customer)
    instalments = await _instalment_summary(db, [c.id for c in points])

    enriched = []
    for contract, row in zip(points, rows, strict=True):
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
            "product_id": product.id if product else None,
            "documents_missing": sum(1 for s in slots if s["required"] and s["document"] is None),
            "documents_rejected": sum(1 for s in slots if s["document"] is not None and s["document"].status == "REJECTED"),
            "instalments_total": instalments.get(contract.id, {}).get("total"),
            "instalments_paid": instalments.get(contract.id, {}).get("paid", 0),
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
        #: What the documents step still lacks -- the wizard
        #: will not go past it, and submit_request refuses, until empty.
        "notes_updated_at": request.notes_updated_at,
        "notes_author": await _notes_author(db, request),
        "documents_blocking": await documents_service.pratica_blocking_missing(
            db, request=request, customer_kind=kind
        ),
    }
    return out
