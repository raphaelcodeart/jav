import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.audit import service as audit_service
from app.domains.users.models import User
from app.domains.users.schemas import ProfileUpdate

REQUIRED_PROFILE_FIELDS = (
    "fiscal_code",
    "residence_street",
    "residence_city",
    "residence_province",
    "residence_postal_code",
)


def is_profile_complete(user: User) -> bool:
    """Gates the mandatory profile-completion popup (see
    docs/business-rules.md#profile-completion) -- applies to every account,
    existing or new, per an explicit product decision to block until
    complete rather than grandfather this one."""
    return all(getattr(user, field) for field in REQUIRED_PROFILE_FIELDS)


class ProfileUpdateError(Exception):
    pass


async def update_profile(db: AsyncSession, *, user_id: uuid.UUID, payload: ProfileUpdate) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise ProfileUpdateError("User not found")

    user.fiscal_code = payload.fiscal_code
    user.residence_street = payload.residence_street
    user.residence_city = payload.residence_city
    user.residence_province = payload.residence_province.upper()
    user.residence_postal_code = payload.residence_postal_code
    user.residence_country = payload.residence_country.upper()

    await audit_service.record(
        db, organization_id=user.organization_id, actor_user_id=user.id,
        action="user.profile_completed", entity_type="user", entity_id=str(user.id),
        new_value={"fiscal_code": payload.fiscal_code, "residence_city": payload.residence_city},
    )
    await db.commit()
    await db.refresh(user)
    return user


async def mark_privacy_accepted(db: AsyncSession, *, user: User) -> None:
    """Does not commit -- caller (registration) commits as part of the same
    transaction, same convention as audit_service.record()."""
    user.privacy_accepted_at = datetime.now(UTC)


class UserLifecycleError(Exception):
    pass


async def freeze_user(
    db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID, actor_user_id: uuid.UUID
) -> User | None:
    """Blocks login immediately (see auth/service.py::authenticate's status
    check) AND revokes every existing session right away -- freezing an
    account that's currently logged in must not leave it usable until the
    access token naturally expires. Deliberately does not touch any other
    row: contracts, orders, wallet history, network position all stay
    exactly as they were, unlike delete_user() below."""
    from app.domains.auth import service as auth_service

    user = await db.get(User, user_id)
    if user is None or user.organization_id != organization_id:
        return None
    if user.id == actor_user_id:
        raise UserLifecycleError("You cannot freeze your own account")

    user.status = "FROZEN"
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="user.frozen", entity_type="user", entity_id=str(user.id),
    )
    await db.commit()
    await auth_service.revoke_all_sessions(db, user_id=user.id)
    await db.refresh(user)
    return user


async def unfreeze_user(
    db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID, actor_user_id: uuid.UUID
) -> User | None:
    user = await db.get(User, user_id)
    if user is None or user.organization_id != organization_id:
        return None

    user.status = "ACTIVE"
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="user.unfrozen", entity_type="user", entity_id=str(user.id),
    )
    await db.commit()
    await db.refresh(user)
    return user


# --- Sblocco dell'account da parte del superadmin (Session 88) -----------------------------------
#
# Un cliente che non riceve l'email di conferma, o che non riesce a finire il
# profilo, resta fermo davanti ai tre controlli d'ingresso (email confermata,
# privacy accettata, profilo completo). Il superadmin può segnarli come fatti
# per lui. Email e privacy si segnano e basta; codice fiscale e indirizzo no:
# non si inventano, li scrive il superadmin (proposti dai dati del cliente,
# se ci sono). Tutto finisce nell'audit con chi l'ha fatto: la privacy
# «accettata» così è un'accettazione raccolta dal superadmin, non un clic del
# cliente, e deve restare distinguibile.

PROFILE_FIELD_LABELS = {
    "fiscal_code": "codice fiscale",
    "residence_street": "indirizzo",
    "residence_city": "città",
    "residence_province": "provincia",
    "residence_postal_code": "CAP",
}


async def _suggested_profile(db: AsyncSession, *, user: User) -> dict:
    """Il profilo com'è, completato con quello che sappiamo già del cliente:
    il codice fiscale della sua scheda e l'indirizzo dell'ultima pratica."""
    from sqlalchemy import select

    from app.domains.contracts.models import ContractRequest
    from app.domains.customers.models import Customer

    out = {field: getattr(user, field) for field in PROFILE_FIELD_LABELS}
    customer = (
        await db.execute(select(Customer).where(Customer.user_id == user.id))
    ).scalars().first()
    if customer is not None:
        if not out["fiscal_code"] and customer.fiscal_code:
            out["fiscal_code"] = customer.fiscal_code.upper()
        request = (
            await db.execute(
                select(ContractRequest)
                .where(ContractRequest.customer_id == customer.id, ContractRequest.street.is_not(None))
                .order_by(ContractRequest.created_at.desc())
            )
        ).scalars().first()
        if request is not None and not out["residence_street"]:
            out["residence_street"] = request.street
            out["residence_city"] = out["residence_city"] or request.city
            out["residence_province"] = out["residence_province"] or (request.province or "")[:2].upper() or None
            out["residence_postal_code"] = out["residence_postal_code"] or request.postal_code
    return out


async def account_status(db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID) -> dict | None:
    """Cosa blocca l'account, e il profilo proposto per completarlo."""
    user = await db.get(User, user_id)
    if user is None or user.organization_id != organization_id:
        return None
    return {
        "email_verified": user.email_verified_at is not None,
        "privacy_accepted": user.privacy_accepted_at is not None,
        "profile_complete": is_profile_complete(user),
        "missing_profile_fields": [
            label for field, label in PROFILE_FIELD_LABELS.items() if not getattr(user, field)
        ],
        "suggested_profile": await _suggested_profile(db, user=user),
    }


async def unlock_account(
    db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID, actor_user_id: uuid.UUID,
    profile: ProfileUpdate | None,
) -> User | None:
    """Segna come fatti i controlli d'ingresso che mancano. Il profilo si
    completa solo con i dati passati: senza, e con il profilo incompleto,
    niente sblocco -- un cliente «attivo» senza codice fiscale non potrebbe
    comunque fare una pratica."""
    user = await db.get(User, user_id)
    if user is None or user.organization_id != organization_id:
        return None
    now = datetime.now(UTC)
    done: dict[str, bool] = {}
    if not is_profile_complete(user):
        if profile is None:
            missing = [label for field, label in PROFILE_FIELD_LABELS.items() if not getattr(user, field)]
            raise UserLifecycleError("Per sbloccarlo servono anche: " + ", ".join(missing) + ".")
        user.fiscal_code = profile.fiscal_code
        user.residence_street = profile.residence_street
        user.residence_city = profile.residence_city
        user.residence_province = profile.residence_province.upper()
        user.residence_postal_code = profile.residence_postal_code
        user.residence_country = profile.residence_country
        done["profile"] = True
    if user.email_verified_at is None:
        user.email_verified_at = now
        done["email_verified"] = True
    if user.privacy_accepted_at is None:
        user.privacy_accepted_at = now
        done["privacy_accepted"] = True
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="user.account_unlocked", entity_type="user", entity_id=str(user.id),
        new_value=done,
        reason="Controlli d'ingresso segnati come fatti dal superadmin per conto del cliente",
    )
    await db.commit()
    await db.refresh(user)
    return user

