"""Organization.settings (JSONB) exposed through a typed subset -- starting
with the bank IBAN customers wire bonifico payments to. Covers that an update merges rather
than replaces the dict, so an unrelated key already living there (or a field
simply omitted from this PATCH) survives untouched."""

import pytest

from app.domains.organizations import service as organizations_service
from app.domains.organizations.models import Organization
from app.domains.organizations.schemas import OrganizationSettingsUpdate


@pytest.mark.asyncio
async def test_get_settings_defaults_to_none_when_nothing_set(db, organization_id):
    settings = await organizations_service.get_settings(db, organization_id=organization_id)
    assert settings == {
        "bank_iban": None,
        "bank_account_holder": None,
        "bank_transfer_instructions": None,
        "admin_notification_email": None,
        "contract_instalment_cashback_mode": None,
    }


@pytest.mark.asyncio
async def test_update_settings_merges_and_partial_update_preserves_the_rest(db, organization_id):
    org = await db.get(Organization, organization_id)
    # An unrelated key already living in the JSONB blob -- must survive
    # untouched by anything this endpoint does.
    org.settings = {**org.settings, "unrelated_future_setting": "keep-me"}
    await db.commit()

    updated = await organizations_service.update_settings(
        db, organization_id=organization_id,
        payload=OrganizationSettingsUpdate(bank_iban="IT60X0542811101000000123456", bank_account_holder="Jav Srl"),
    )
    assert updated == {
        "bank_iban": "IT60X0542811101000000123456",
        "bank_account_holder": "Jav Srl",
        "bank_transfer_instructions": None,
        "admin_notification_email": None,
        "contract_instalment_cashback_mode": None,
    }

    # Omitting a field (exclude_unset) leaves it exactly as it was.
    partial = await organizations_service.update_settings(
        db, organization_id=organization_id, payload=OrganizationSettingsUpdate(bank_account_holder="New Holder"),
    )
    assert partial["bank_iban"] == "IT60X0542811101000000123456"
    assert partial["bank_account_holder"] == "New Holder"

    org_after = await db.get(Organization, organization_id)
    assert org_after.settings["unrelated_future_setting"] == "keep-me"


@pytest.mark.asyncio
async def test_bank_transfer_instructions_field_merges_like_the_others(db, organization_id):
    await organizations_service.update_settings(
        db, organization_id=organization_id,
        payload=OrganizationSettingsUpdate(bank_iban="IT60X0542811101000000123456"),
    )
    updated = await organizations_service.update_settings(
        db, organization_id=organization_id,
        payload=OrganizationSettingsUpdate(bank_transfer_instructions="Includi il codice ordine nella causale."),
    )
    assert updated["bank_iban"] == "IT60X0542811101000000123456"  # untouched, omitted from this PATCH
    assert updated["bank_transfer_instructions"] == "Includi il codice ordine nella causale."


@pytest.mark.asyncio
async def test_admin_notification_email_defaults_and_can_be_overridden(db, organization_id):
    default = await organizations_service.get_admin_notification_email(db, organization_id=organization_id)
    assert default == organizations_service.DEFAULT_ADMIN_NOTIFICATION_EMAIL

    await organizations_service.update_settings(
        db, organization_id=organization_id,
        payload=OrganizationSettingsUpdate(admin_notification_email="ops@example.com"),
    )
    overridden = await organizations_service.get_admin_notification_email(db, organization_id=organization_id)
    assert overridden == "ops@example.com"


@pytest.mark.asyncio
async def test_payment_info_exposes_only_the_bank_details(db, organization_id):
    assert await organizations_service.get_payment_info(db, organization_id=organization_id) == {
        "iban": None, "holder": None, "instructions": None,
    }

    await organizations_service.update_settings(
        db, organization_id=organization_id,
        payload=OrganizationSettingsUpdate(
            bank_iban="IT60X0542811101000000123456", bank_account_holder="Jav Srl",
            admin_notification_email="segreteria@example.com",
        ),
    )
    info = await organizations_service.get_payment_info(db, organization_id=organization_id)
    assert info == {"iban": "IT60X0542811101000000123456", "holder": "Jav Srl", "instructions": None}


@pytest.mark.asyncio
async def test_a_missing_organization_resolves_to_the_only_one(db, organization_id):
    """Login, password reset and invite links don't carry the organization:
    with one club per installation the API finds it, so the frontend never
    hardcodes an id that breaks when the database is recreated."""
    assert await organizations_service.resolve_organization_id(db, None) == organization_id
    assert await organizations_service.resolve_organization_id(db, str(organization_id)) == organization_id

    db.add(Organization(name="Secondo club", legal_name="Secondo club"))
    await db.commit()
    with pytest.raises(organizations_service.OrganizationNotResolvedError):
        await organizations_service.resolve_organization_id(db, None)
    with pytest.raises(organizations_service.OrganizationNotResolvedError):
        await organizations_service.resolve_organization_id(db, "non-un-uuid")
