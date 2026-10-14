import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.organizations.models import Organization
from app.domains.organizations.schemas import OrganizationSettingsUpdate

SETTINGS_KEYS = (
    "bank_iban", "bank_account_holder", "bank_transfer_instructions", "admin_notification_email",
    "contract_instalment_cashback_mode",
)

# Placeholder until the administrator sets the real mailbox in Impostazioni
# (Organization.settings["admin_notification_email"]).
DEFAULT_ADMIN_NOTIFICATION_EMAIL = "admin@example.com"

#: How a contract paid in 3 or 12 instalments earns its JavCash cashback
#:, chosen by the administrator in Impostazioni:
#:   PER_INSTALMENT -- a slice with every instalment actually collected
#:                     (the default);
#:   UPFRONT        -- the whole contract's cashback at once, as soon as the
#:                     first instalment is paid.
CASHBACK_PER_INSTALMENT = "PER_INSTALMENT"
CASHBACK_UPFRONT = "UPFRONT"
CONTRACT_INSTALMENT_CASHBACK_MODES = frozenset({CASHBACK_PER_INSTALMENT, CASHBACK_UPFRONT})


async def get_contract_instalment_cashback_mode(db: AsyncSession, *, organization_id: uuid.UUID) -> str:
    org = await db.get(Organization, organization_id)
    mode = (org.settings or {}).get("contract_instalment_cashback_mode") if org is not None else None
    return mode if mode in CONTRACT_INSTALMENT_CASHBACK_MODES else CASHBACK_PER_INSTALMENT


async def get_settings(db: AsyncSession, *, organization_id: uuid.UUID) -> dict:
    org = await db.get(Organization, organization_id)
    if org is None:
        return {key: None for key in SETTINGS_KEYS}
    return {key: org.settings.get(key) for key in SETTINGS_KEYS}


async def update_settings(
    db: AsyncSession, *, organization_id: uuid.UUID, payload: OrganizationSettingsUpdate
) -> dict:
    """Merges into the existing settings dict -- never replaces it wholesale,
    so a future unrelated key living in the same JSONB blob is never
    clobbered by an admin only touching the bank fields. Only fields
    actually present in `payload` overwrite (Pydantic's exclude_unset), so a
    PATCH that omits bank_account_holder leaves it exactly as it was."""
    org = await db.get(Organization, organization_id)
    if org is None:
        raise ValueError("Organization not found")

    updates = payload.model_dump(exclude_unset=True)
    # Mutating the dict in place doesn't get picked up by SQLAlchemy's
    # change-tracking on a JSONB column -- must assign a new dict.
    org.settings = {**org.settings, **updates}
    await db.commit()
    await db.refresh(org)
    return {key: org.settings.get(key) for key in SETTINGS_KEYS}


async def is_bank_transfer_configured(db: AsyncSession, *, organization_id: uuid.UUID) -> bool:
    """Gates whether "Paga con bonifico" is even offered as an option --
    see orders/service.py::get_available_payment_methods(). An IBAN is the
    one field that actually matters; the holder name and instructions text
    are cosmetic."""
    org = await db.get(Organization, organization_id)
    if org is None:
        return False
    return bool(org.settings.get("bank_iban"))


class OrganizationNotResolvedError(LookupError):
    """Un messaggio per l'utente (CLAUDE.md §6)."""


async def resolve_organization_id(db: AsyncSession, raw: str | None) -> uuid.UUID:
    """The organization a public request (login, password reset, invite
    link) is for. An installation serves one club: when the caller doesn't
    say which organization, it is the only one there is, resolved here
    rather than baked into the frontend -- a hardcoded id silently breaks
    login the moment the database is recreated. With more than one
    organization the caller must name it."""
    if raw:
        try:
            return uuid.UUID(raw)
        except ValueError as exc:
            raise OrganizationNotResolvedError("Organizzazione non valida.") from exc
    ids = (await db.execute(select(Organization.id).limit(2))).scalars().all()
    if len(ids) != 1:
        raise OrganizationNotResolvedError("Indica l'organizzazione a cui accedere.")
    return ids[0]


async def get_payment_info(db: AsyncSession, *, organization_id: uuid.UUID) -> dict:
    """The bank details a customer needs to actually make a transfer --
    every "paga con bonifico" screen (cart, catalog and Shop checkout, "I
    miei Ordini", club fees) reads them. Only these three fields, never the
    rest of the settings: what an admin configures for the organization is
    not a customer's business, the IBAN they must pay into is."""
    org = await db.get(Organization, organization_id)
    settings = (org.settings or {}) if org is not None else {}
    return {
        "iban": settings.get("bank_iban") or None,
        "holder": settings.get("bank_account_holder") or None,
        "instructions": settings.get("bank_transfer_instructions") or None,
    }


async def get_admin_notification_email(db: AsyncSession, *, organization_id: uuid.UUID) -> str:
    """Where the "new ticket opened" alert (support/service.py::create_ticket)
    goes -- an admin-editable override of DEFAULT_ADMIN_NOTIFICATION_EMAIL."""
    org = await db.get(Organization, organization_id)
    if org is None:
        return DEFAULT_ADMIN_NOTIFICATION_EMAIL
    return org.settings.get("admin_notification_email") or DEFAULT_ADMIN_NOTIFICATION_EMAIL
