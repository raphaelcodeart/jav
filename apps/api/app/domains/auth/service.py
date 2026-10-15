import logging
import uuid
from datetime import UTC, datetime, timedelta
from html import escape, unescape

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.email import EmailNotConfiguredError, send_html_email, send_html_email_best_effort
from app.core.email_templates import render_email
from app.core.security import (
    create_access_token,
    generate_email_verification_token,
    generate_otp_code,
    generate_password_reset_token,
    generate_refresh_token,
    hash_email_verification_token,
    hash_otp_code,
    hash_password,
    hash_password_reset_token,
    hash_refresh_token,
    verify_password,
)
from app.domains.audit import service as audit_service
from app.domains.auth.models import (
    EmailVerificationToken,
    OtpCode,
    PasswordResetToken,
    Session,
    SpendPin,
)
from app.domains.auth.schemas import RegisterFamilyRequest, RegisterRequest
from app.domains.organizations.models import Organization
from app.domains.rbac.service import get_roles_for_user
from app.domains.users import service as users_service
from app.domains.users.models import User

settings = get_settings()
logger = logging.getLogger(__name__)

MAX_FAILED_ATTEMPTS = 5  # placeholder policy, see docs/open-questions.md #7
LOCKOUT_WINDOW_MINUTES = 15

GENERIC_AUTH_ERROR = "Invalid email or password"


class AuthenticationError(Exception):
    pass


class AccountLockedError(Exception):
    pass


async def authenticate(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    email: str,
    password: str,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[str, str]:
    """Returns (access_token, refresh_token). Raises AuthenticationError /
    AccountLockedError with an identical message shape for unknown-email and
    wrong-password cases, to avoid account enumeration. Case-insensitive
    lookup (func.lower on both sides): new accounts are always stored
    lowercase (see RegisterRequest/LoginRequest's normalize_email
    validators), but this must still find accounts created before that
    normalization existed, whatever case their email happens to be stored
    in."""
    # Con "@" è un'email; senza, il nome utente di un atleta (sempre minuscolo).
    match = func.lower(User.email) == email.lower() if "@" in email else User.username == email.lower()
    stmt = select(User).where(User.organization_id == organization_id, match)
    user = (await db.execute(stmt)).scalar_one_or_none()

    if user is None:
        # Still do a hash-verify against a dummy hash to keep response timing similar
        # regardless of whether the account exists (mitigates timing-based enumeration).
        verify_password(password, "$argon2id$v=19$m=65536,t=3,p=4$" + "0" * 22 + "$" + "0" * 43)
        # audit_log.organization_id is a real FK -- a bogus/stale organization_id
        # (e.g. a client still pointing at a demo org that got re-seeded with a new
        # id) must not crash the audit write with an unhandled IntegrityError; skip
        # it rather than fail the whole login attempt over a logging side effect.
        if await db.get(Organization, organization_id) is not None:
            await audit_service.record(
                db, organization_id=organization_id, actor_user_id=None,
                action="login.failed", entity_type="user", entity_id=email,
                reason="unknown_email", ip_address=ip_address, user_agent=user_agent,
            )
            await db.commit()
        raise AuthenticationError(GENERIC_AUTH_ERROR)

    if user.status != "ACTIVE":
        # An admin-frozen account (users/service.py::freeze_user) -- reuses
        # AccountLockedError/423 rather than a new exception type, since the
        # router-level handling ("locked out, contact support") is identical;
        # the message is what actually tells the two cases apart.
        raise AccountLockedError("This account has been disabled. Contact the administrator.")

    if user.locked_until and user.locked_until > datetime.now(UTC):
        raise AccountLockedError("Account temporarily locked, try again later")

    if not verify_password(password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
            user.locked_until = datetime.now(UTC) + timedelta(minutes=LOCKOUT_WINDOW_MINUTES)
            user.failed_login_attempts = 0
        await audit_service.record(
            db, organization_id=organization_id, actor_user_id=user.id,
            action="login.failed", entity_type="user", entity_id=str(user.id),
            reason="wrong_password", ip_address=ip_address, user_agent=user_agent,
        )
        await db.commit()
        raise AuthenticationError(GENERIC_AUTH_ERROR)

    user.failed_login_attempts = 0
    user.locked_until = None
    return await issue_session(
        db, user=user, organization_id=organization_id, ip_address=ip_address, user_agent=user_agent,
    )


async def issue_session(
    db: AsyncSession, *, user: User, organization_id: uuid.UUID, ip_address: str | None, user_agent: str | None,
    action: str = "login.success",
) -> tuple[str, str]:
    """La sessione di un utente già riconosciuto (password o QR dell'atleta):
    access token con i ruoli, refresh token, audit."""
    roles = await get_roles_for_user(db, user_id=user.id, organization_id=organization_id)
    access_token = create_access_token(
        subject=str(user.id), organization_id=str(organization_id), roles=roles
    )
    refresh_token = generate_refresh_token()
    session = Session(
        user_id=user.id,
        refresh_token_hash=hash_refresh_token(refresh_token),
        user_agent=user_agent,
        ip_address=ip_address,
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(session)

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=user.id,
        action=action, entity_type="user", entity_id=str(user.id),
        ip_address=ip_address, user_agent=user_agent,
    )
    await db.commit()
    return access_token, refresh_token


async def rotate_refresh_token(
    db: AsyncSession, *, organization_id: uuid.UUID, refresh_token: str
) -> tuple[str, str]:
    """Validates and rotates a refresh token: the old session is revoked and a new
    one issued in the same call, so a stolen-and-reused old token is detectable
    (it will already be revoked) and cannot be replayed indefinitely."""
    token_hash = hash_refresh_token(refresh_token)
    stmt = select(Session).where(Session.refresh_token_hash == token_hash)
    session = (await db.execute(stmt)).scalar_one_or_none()

    if session is None:
        raise AuthenticationError("Invalid refresh token")
    if session.revoked_at is not None and not await _within_rotation_grace(db, session):
        raise AuthenticationError("Invalid refresh token")
    if session.expires_at < datetime.now(UTC):
        raise AuthenticationError("Refresh token expired")

    user = await db.get(User, session.user_id)
    if user is None or user.organization_id != organization_id:
        raise AuthenticationError("Invalid refresh token")

    if session.revoked_at is None:
        session.revoked_at = datetime.now(UTC)

    roles = await get_roles_for_user(db, user_id=user.id, organization_id=organization_id)
    new_access_token = create_access_token(
        subject=str(user.id), organization_id=str(organization_id), roles=roles
    )
    new_refresh_token = generate_refresh_token()
    new_session = Session(
        user_id=user.id,
        refresh_token_hash=hash_refresh_token(new_refresh_token),
        user_agent=session.user_agent,
        ip_address=session.ip_address,
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(new_session)
    await db.flush()
    if session.replaced_by_session_id is None:
        session.replaced_by_session_id = new_session.id
    await db.commit()
    return new_access_token, new_refresh_token


#: How long a just-rotated refresh token is still honoured.
ROTATION_GRACE_SECONDS = 60


async def _within_rotation_grace(db: AsyncSession, session: Session) -> bool:
    """A page fires several calls at once; when the access token has just
    expired each of them refreshes with the SAME refresh token. The first
    rotates it; refusing every other one would show "Sessione scaduta" to a
    user who is logged in. So a token rotated in the
    last ROTATION_GRACE_SECONDS is honoured once more (the caller gets a new
    session of its own).

    Never after a logout: a session a logout revoked has no successor, and
    one whose successor was logged out is not honoured either. Outside the
    window, reuse is refused exactly as before -- the stolen-token defence
    the rotation exists for."""
    if session.replaced_by_session_id is None or session.revoked_at is None:
        return False
    revoked_at = session.revoked_at if session.revoked_at.tzinfo else session.revoked_at.replace(tzinfo=UTC)
    if datetime.now(UTC) - revoked_at > timedelta(seconds=ROTATION_GRACE_SECONDS):
        return False
    successor = await db.get(Session, session.replaced_by_session_id)
    return successor is not None and (successor.revoked_at is None or successor.replaced_by_session_id is not None)


async def revoke_session(db: AsyncSession, *, refresh_token: str) -> None:
    token_hash = hash_refresh_token(refresh_token)
    await db.execute(
        update(Session)
        .where(Session.refresh_token_hash == token_hash, Session.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await db.commit()


async def revoke_all_sessions(db: AsyncSession, *, user_id: uuid.UUID) -> None:
    await db.execute(
        update(Session)
        .where(Session.user_id == user_id, Session.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await db.commit()


class RegistrationError(Exception):
    pass


PRIVATE_LIKE_KINDS = {"PRIVATE", "SOLE_PROPRIETOR"}
COMPANY_LIKE_KINDS = {"COMPANY", "CONDOMINIUM"}


async def register_with_referral(db: AsyncSession, *, organization_id: uuid.UUID, payload: RegisterRequest) -> User:
    """Self-service signup, gated on a valid referral code -- registration is
    invite-only by design (docs/business-rules.md): every new customer must be
    attributed to the promoter who referred them, no exceptions. Validates the
    referral code FIRST, before creating anything, so an invalid/expired code
    never leaves a half-created account behind. Everything else -- user, role
    grant, customer, profile/company, attribution -- is one transaction, one
    commit, so a customer can never exist without their required promoter
    attribution."""
    from app.domains.customers.models import Company, Customer, CustomerProfile
    from app.domains.friend_referrals import service as friend_referrals_service
    from app.domains.friend_referrals.models import (
        REFERRAL_SOURCE_FRIEND_LINK,
        REFERRAL_SOURCE_PROMOTER_LINK,
    )
    from app.domains.network.models import AgentProfile
    from app.domains.rbac.models import Role, UserRole
    from app.domains.referral import service as referral_service
    from app.domains.referral.models import CustomerAttribution

    if payload.kind in PRIVATE_LIKE_KINDS and not (payload.first_name and payload.last_name):
        raise RegistrationError("first_name and last_name are required for this customer kind")
    if payload.kind in COMPANY_LIKE_KINDS and not payload.company_name:
        raise RegistrationError("company_name is required for this customer kind")

    # Two kinds of link can bring somebody here, and they are resolved in this
    # order so the existing promoter flow is byte-for-byte unchanged:
    #
    #   1. a PROMOTER link  -> exactly as before: the customer joins that
    #      promoter's tree and that promoter earns on them.
    #   2. an INVITE link (friend_referral_codes) -> the customer is
    #      attributed to the referrer's OWN promoter, because a plain customer
    #      earns nothing and cannot have a downline. See
    #      friend_referrals/service.py::promoter_code_for_referrer.
    #
    # Either way the new customer ALSO lands in the referrer's one-level
    # "invitati" list, which is purely informational -- it never affects
    # where they sit in the commercial tree or who gets paid.
    friend_code = None
    promoter_code = await referral_service.get_active_promoter_code(
        db, organization_id=organization_id, code=payload.referral_code
    )
    if promoter_code is None:
        friend_code = await friend_referrals_service.get_active_code(
            db, organization_id=organization_id, code=payload.referral_code
        )
        if friend_code is None:
            raise RegistrationError("Invalid or expired referral code -- registration is invite-only")
        promoter_code = await friend_referrals_service.promoter_code_for_referrer(
            db, organization_id=organization_id, user_id=friend_code.user_id
        )
        if promoter_code is None:
            # The inviter's own promoter chain has no active agent left,
            # so there is nobody to attribute this registration to. Refuse
            # rather than create a customer nobody owns -- the same invariant
            # invite-only registration exists to protect.
            raise RegistrationError(
                "Questo link di invito non è utilizzabile al momento -- contatta l'assistenza."
            )

    existing = (
        await db.execute(
            select(User).where(
                User.organization_id == organization_id, func.lower(User.email) == payload.email.lower()
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise RegistrationError("An account with this email already exists")

    role = (
        await db.execute(
            select(Role).where(
                (Role.organization_id == organization_id) | (Role.organization_id.is_(None)),
                Role.code == "CUSTOMER",
            )
        )
    ).scalars().first()
    if role is None:
        raise RegistrationError("Customer role is not configured for this organization")

    user = User(
        organization_id=organization_id,
        email=payload.email,
        password_hash=hash_password(payload.password),
        status="ACTIVE",
    )
    db.add(user)
    await db.flush()
    # accept_privacy=True is enforced by RegisterRequest's own validator --
    # this only ever runs once that's already guaranteed true.
    await users_service.mark_privacy_accepted(db, user=user)

    db.add(UserRole(user_id=user.id, organization_id=organization_id, role_id=role.id))

    customer = Customer(
        organization_id=organization_id,
        user_id=user.id,
        kind=payload.kind,
        email=payload.email,
        phone=payload.phone,
    )
    db.add(customer)
    await db.flush()

    if payload.kind in PRIVATE_LIKE_KINDS:
        db.add(CustomerProfile(customer_id=customer.id, first_name=payload.first_name, last_name=payload.last_name))
    else:
        db.add(Company(customer_id=customer.id, company_name=payload.company_name))

    db.add(
        CustomerAttribution(
            organization_id=organization_id,
            customer_id=customer.id,
            promoter_code_id=promoter_code.id,
            referral_session_id=None,
            attributed_at=datetime.now(UTC),
        )
    )

    # The one-level invite list. For a promoter link the referrer is the
    # agent's own login (a promoter with no user account simply records
    # nothing -- there is no list for them to look at). Never raises: this is
    # an informational list, and a problem here must not fail a registration
    # that has otherwise completely succeeded.
    referrer_user_id = friend_code.user_id if friend_code is not None else None
    if referrer_user_id is None:
        agent = await db.get(AgentProfile, promoter_code.agent_id)
        referrer_user_id = agent.user_id if agent is not None else None
    if referrer_user_id is not None:
        await friend_referrals_service.record_referral(
            db,
            organization_id=organization_id,
            referrer_user_id=referrer_user_id,
            referred_customer_id=customer.id,
            code_used=payload.referral_code,
            source=REFERRAL_SOURCE_FRIEND_LINK if friend_code is not None else REFERRAL_SOURCE_PROMOTER_LINK,
        )

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=user.id,
        action="auth.self_registered", entity_type="customer", entity_id=str(customer.id),
        new_value={"email": payload.email, "referral_code": payload.referral_code},
    )
    await db.commit()
    await db.refresh(user)
    await send_verification_email(db, user=user)
    return user


async def register_family(db: AsyncSession, *, payload: RegisterFamilyRequest) -> User:
    """Un genitore si registra dal link del suo club. Diversamente da
    register_with_referral nessun promoter: l'account nasce legato al club
    (users.club_id), ed è da lì che vede quote, corsi e gare. Lo Shop resta
    quello della piattaforma, uguale per tutti i club."""
    from app.domains.club import clubs as clubs_service
    from app.domains.club import referrals as club_referrals
    from app.domains.customers.models import Customer, CustomerProfile
    from app.domains.rbac.models import Role, UserRole

    club = await clubs_service.get_club_by_slug(db, slug=payload.club_slug)
    if club is None:
        raise RegistrationError("Club non trovato: controlla il link che hai ricevuto dal club.")
    organization_id = club.organization_id
    existing = (
        await db.execute(
            select(User).where(
                User.organization_id == organization_id, func.lower(User.email) == payload.email.lower()
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise RegistrationError(
            "Esiste già un account con questa email: accedi, oppure recupera la password se non la ricordi."
        )
    role = (
        await db.execute(
            select(Role).where(
                (Role.organization_id == organization_id) | (Role.organization_id.is_(None)),
                Role.code == "CUSTOMER",
            )
        )
    ).scalars().first()
    if role is None:
        raise RegistrationError("Registrazione non disponibile al momento: contatta la segreteria del club.")

    user = User(
        organization_id=organization_id, club_id=club.id, email=payload.email,
        password_hash=hash_password(payload.password), status="ACTIVE",
    )
    db.add(user)
    await db.flush()
    await users_service.mark_privacy_accepted(db, user=user)
    db.add(UserRole(user_id=user.id, organization_id=organization_id, role_id=role.id))
    customer = Customer(
        organization_id=organization_id, user_id=user.id, kind="PRIVATE", email=payload.email, phone=payload.phone,
    )
    db.add(customer)
    await db.flush()
    db.add(CustomerProfile(customer_id=customer.id, first_name=payload.first_name, last_name=payload.last_name))
    await club_referrals.record_club_invite(db, club=club, invite_code=payload.invite_code, customer_id=customer.id)
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=user.id,
        action="auth.family_registered", entity_type="customer", entity_id=str(customer.id),
        new_value={"email": payload.email, "club_id": str(club.id)},
    )
    await db.commit()
    await db.refresh(user)
    await send_verification_email(db, user=user)
    return user


EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES = 60 * 24


class EmailVerificationError(Exception):
    pass


async def send_verification_email(db: AsyncSession, *, user: User) -> None:
    """Mandatory-verification gate applies to NEW registrations only (an
    explicit product decision -- accounts that existed before this feature
    shipped are grandfathered as already-verified, see the 0026 migration's
    backfill and docs/business-rules.md#account-gates). Best-effort: an SMTP
    hiccup here must not break registration itself, which has already
    committed by the time this runs."""
    token = generate_email_verification_token()
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=hash_email_verification_token(token),
            expires_at=datetime.now(UTC) + timedelta(minutes=EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES),
        )
    )
    await db.commit()

    verify_link = f"{settings.public_app_base_url}/verify-email?token={token}"
    html = render_email(
        preheader="Conferma il tuo indirizzo email per attivare il tuo account Jav",
        heading="Benvenuto in Jav!",
        body_html=(
            "<p>Grazie per esserti registrato. Per attivare il tuo account e iniziare a usare la dashboard, "
            "conferma il tuo indirizzo email cliccando il pulsante qui sotto.</p>"
            f"<p>Il link è valido per {EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES // 60} ore.</p>"
        ),
        cta_label="Conferma la mia email",
        cta_url=verify_link,
    )
    try:
        send_html_email(
            to=user.email,
            subject="Conferma la tua email - Jav",
            html_body=html,
            text_body=f"Conferma il tuo indirizzo email entro {EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES // 60} ore: {verify_link}",
        )
    except EmailNotConfiguredError:
        logger.warning("Verification email for %s (SMTP not configured) -- link: %s", user.email, verify_link)


async def verify_email(db: AsyncSession, *, token: str) -> User:
    token_hash = hash_email_verification_token(token)
    stmt = select(EmailVerificationToken).where(EmailVerificationToken.token_hash == token_hash)
    row = (await db.execute(stmt)).scalar_one_or_none()

    if row is None or row.used_at is not None:
        raise EmailVerificationError("Invalid or already-used verification link")
    if row.expires_at < datetime.now(UTC):
        raise EmailVerificationError("This verification link has expired")

    user = await db.get(User, row.user_id)
    if user is None:
        raise EmailVerificationError("Invalid or already-used verification link")

    user.email_verified_at = datetime.now(UTC)
    row.used_at = datetime.now(UTC)

    await audit_service.record(
        db, organization_id=user.organization_id, actor_user_id=user.id,
        action="auth.email_verified", entity_type="user", entity_id=str(user.id),
    )
    await db.commit()
    await db.refresh(user)
    return user


async def resend_verification_email(db: AsyncSession, *, user: User) -> None:
    if user.email_verified_at is not None:
        return
    await send_verification_email(db, user=user)


PASSWORD_RESET_TOKEN_EXPIRE_MINUTES = 60
# A promoter-created customer (network/service.py::create_recruited_customer)
# may not check their email for days -- much more generous than a genuine
# "forgot password" moment, which is why this is a separate constant rather
# than reusing PASSWORD_RESET_TOKEN_EXPIRE_MINUTES.
ACCOUNT_INVITE_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7


class PasswordResetError(Exception):
    pass


async def send_account_invite_email(
    db: AsyncSession, *, user: User, invited_by_display_name: str, intro: str | None = None
) -> tuple[str, bool]:
    """The very first email a promoter-created customer ever receives (see
    network/service.py::create_recruited_customer) -- their account already
    exists (random, never-revealed password) but they've never set one
    themselves, so this doubles as their "primo accesso": reuses the exact
    same PasswordResetToken mechanism/page as a genuine "dimenticata
    password" request (see request_password_reset above), just different
    copy and a much longer expiry (ACCOUNT_INVITE_TOKEN_EXPIRE_MINUTES, not
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES) since there's no urgency here.
    Completing it also marks the account email-verified -- see
    reset_password()'s own comment for why that's equally valid proof.

    `intro` sostituisce la prima frase quando l'invito non viene da un
    promoter (la segreteria di un club creata dal superadmin, un istruttore):
    testo semplice, l'escape lo fa questa funzione.

    Restituisce il link e se l'email è partita: senza SMTP chi ha creato
    l'account può consegnare il link a mano (club/clubs.py::add_staff)."""
    settings = get_settings()
    intro = escape(intro) if intro else (
        f"{invited_by_display_name} ha creato per te un account su Jav e attivato "
        "quanto concordato -- trovi già tutto configurato non appena accedi."
    )
    token = generate_password_reset_token()
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_password_reset_token(token),
            expires_at=datetime.now(UTC) + timedelta(minutes=ACCOUNT_INVITE_TOKEN_EXPIRE_MINUTES),
        )
    )
    await db.commit()

    set_password_link = f"{settings.public_app_base_url}/reset-password?token={token}"
    html = render_email(
        preheader="Il tuo account Jav è pronto",
        heading="Il tuo account Jav è pronto",
        body_html=(
            f"<p>{intro}</p>"
            "<p>Per accedere per la prima volta, scegli subito la tua password personale.</p>"
        ),
        cta_label="Imposta la tua password",
        cta_url=set_password_link,
    )
    sent = send_html_email_best_effort(
        context=f"Account-invite email (user={user.id})",
        to=user.email,
        subject="Il tuo account Jav è pronto",
        html_body=html,
        text_body=(
            f"{unescape(intro)}\n\n"
            f"Imposta la tua password qui: {set_password_link}"
        ),
    )
    return set_password_link, sent


async def request_password_reset(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    email: str,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    """Always returns normally, whether or not the email belongs to a real
    account -- same enumeration-safety principle as authenticate(): a caller
    must never be able to use this endpoint to discover which emails have
    accounts."""
    # Con "@" è un'email; senza, il nome utente di un atleta (sempre minuscolo).
    match = func.lower(User.email) == email.lower() if "@" in email else User.username == email.lower()
    stmt = select(User).where(User.organization_id == organization_id, match)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if user is None:
        await audit_service.record(
            db, organization_id=organization_id, actor_user_id=None,
            action="password_reset.requested", entity_type="user", entity_id=email,
            reason="unknown_email", ip_address=ip_address, user_agent=user_agent,
        )
        await db.commit()
        return

    token = generate_password_reset_token()
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_password_reset_token(token),
            expires_at=datetime.now(UTC) + timedelta(minutes=PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
        )
    )

    recipient = user.email
    reset_link = f"{settings.public_app_base_url}/reset-password?token={token}"
    intro_html = "<p>Hai richiesto di reimpostare la password del tuo account Jav.</p>"
    intro_text = "Hai richiesto di reimpostare la password del tuo account Jav.\n\n"
    subject = "Reimposta la tua password - Jav"

    html = render_email(
        preheader="Reimposta la tua password Jav",
        heading="Reimposta la tua password",
        body_html=(
            intro_html
            + f"<p>Il link scade tra {PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minuti. Se non hai richiesto tu "
            "questa operazione, ignora questa email: la password resterà invariata.</p>"
        ),
        cta_label="Scegli una nuova password",
        cta_url=reset_link,
    )
    try:
        send_html_email(
            to=recipient,
            subject=subject,
            html_body=html,
            text_body=(
                intro_text
                + f"Apri questo link entro {PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minuti per scegliere una nuova password:\n"
                f"{reset_link}\n\n"
                "Se non hai richiesto tu questa operazione, ignora questa email."
            ),
        )
        delivery = "sent"
    except EmailNotConfiguredError:
        # No SMTP configured yet. The token/link is deliberately NOT written
        # anywhere a web-UI role (even audit.read) could read it -- that would
        # let any admin-tier account take over any user's account by reading
        # their reset link. It goes to the process log only, which requires
        # server shell access (`docker compose logs api`), a much higher trust
        # bar. See docs/business-rules.md §Password reset.
        logger.warning("Password reset for %s (SMTP not configured) -- link: %s", recipient, reset_link)
        delivery = "logged_only"

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=user.id,
        action="password_reset.requested", entity_type="user", entity_id=str(user.id),
        # delivered_to is recorded ONLY when it differs from the account's own
        # address: a redirected admin reset is exactly the kind of event an
        # auditor needs to see explicitly. The token itself is still never
        # written here (see the SMTP comment above).
        new_value={"delivery": delivery},
        ip_address=ip_address, user_agent=user_agent,
    )
    await db.commit()


async def reset_password(db: AsyncSession, *, token: str, new_password: str) -> None:
    token_hash = hash_password_reset_token(token)
    stmt = select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    reset_token = (await db.execute(stmt)).scalar_one_or_none()

    if reset_token is None or reset_token.used_at is not None:
        raise PasswordResetError("Invalid or already-used reset link")
    if reset_token.expires_at < datetime.now(UTC):
        raise PasswordResetError("This reset link has expired")

    user = await db.get(User, reset_token.user_id)
    if user is None:
        raise PasswordResetError("Invalid or already-used reset link")

    user.password_hash = hash_password(new_password)
    user.failed_login_attempts = 0
    user.locked_until = None
    reset_token.used_at = datetime.now(UTC)
    # Successfully completing a token-based emailed link is equally strong
    # proof of inbox control as clicking the dedicated verify-email link --
    # matters most for send_account_invite_email() below, whose recipient
    # has no password yet and would otherwise need to click TWO separate
    # emailed links (invite, then verify) before ever getting past the
    # account gates (docs/business-rules.md#account-gates).
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)

    # A password reset is exactly the moment to kill every existing session --
    # if the reset was needed because the old password leaked, whoever has it
    # (and any session opened with it) must be logged out now.
    await db.execute(
        update(Session)
        .where(Session.user_id == user.id, Session.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )

    await audit_service.record(
        db, organization_id=user.organization_id, actor_user_id=user.id,
        action="password_reset.completed", entity_type="user", entity_id=str(user.id),
    )
    await db.commit()


OTP_EXPIRE_MINUTES = 10

# See network/service.py::apply_as_promoter. A separate constant (not a free
# string at each call site) so a typo can't silently create two disjoint
# "purposes" for what should be the same gate.
PROMOTER_APPLICATION_OTP_PURPOSE = "PROMOTER_APPLICATION"
# Gates self-checkout spending existing wallet JavCash on an order (any
# credit_applied_cents > 0 on POST /orders/mine) -- see
# orders/service.py::create_order. A stolen session token alone must not be
# enough to drain a wallet at self-checkout; this is the same "prove you
# still control the inbox" backstop PROMOTER_APPLICATION_OTP_PURPOSE already
# uses for a different sensitive self-service action.
WALLET_CREDIT_SPEND_OTP_PURPOSE = "WALLET_CREDIT_SPEND"


async def request_otp(db: AsyncSession, *, user: User, purpose: str, context_line: str) -> None:
    """Emails a short numeric code the user must type back in to confirm a
    sensitive self-service action -- see core/security.py::generate_otp_code.
    Best-effort delivery, same EmailNotConfiguredError fallback as every
    other email in this module."""
    code = generate_otp_code()
    db.add(
        OtpCode(
            user_id=user.id,
            purpose=purpose,
            code_hash=hash_otp_code(code),
            expires_at=datetime.now(UTC) + timedelta(minutes=OTP_EXPIRE_MINUTES),
        )
    )
    await db.commit()

    html = render_email(
        preheader="Il tuo codice di conferma Jav",
        heading="Codice di conferma",
        body_html=(
            f"<p>{context_line}</p>"
            f'<p style="font-size:28px; font-weight:700; letter-spacing:6px; color:#f97316; margin:20px 0;">{code}</p>'
            f"<p>Il codice scade tra {OTP_EXPIRE_MINUTES} minuti. Se non hai richiesto tu questo codice, ignora questa email.</p>"
        ),
    )
    try:
        send_html_email(
            to=user.email,
            subject="Il tuo codice di conferma - Jav",
            html_body=html,
            text_body=f"Il tuo codice di conferma: {code} (valido {OTP_EXPIRE_MINUTES} minuti)",
        )
    except EmailNotConfiguredError:
        logger.warning("OTP for %s purpose=%s not sent (SMTP not configured) -- code: %s", user.email, purpose, code)


async def verify_otp(db: AsyncSession, *, user_id: uuid.UUID, purpose: str, code: str) -> bool:
    """Consumes the most recent, still-unused code for this user/purpose --
    commits the used_at marker immediately on success so the same code can
    never be replayed, independent of whether the caller's own action
    (e.g. the promoter application) goes on to succeed or fail."""
    stmt = (
        select(OtpCode)
        .where(OtpCode.user_id == user_id, OtpCode.purpose == purpose, OtpCode.used_at.is_(None))
        .order_by(OtpCode.created_at.desc())
    )
    row = (await db.execute(stmt)).scalars().first()
    if row is None or row.expires_at < datetime.now(UTC) or row.code_hash != hash_otp_code(code):
        return False
    row.used_at = datetime.now(UTC)
    await db.commit()
    return True


# --- PIN dei JavCash -------------------------------------------------------------
#
# Il cliente sceglie come confermare l'uso dei JavCash al checkout: il codice
# via email (sempre disponibile) oppure un PIN di quattro cifre scelto da lui.
# Tutti i checkout passano da request_spend_code / verify_spend_code, così la
# regola vive in un posto solo.

SPEND_PIN_MAX_ATTEMPTS = 5
SPEND_PIN_LOCK_MINUTES = 15
SPEND_METHOD_PIN = "PIN"
SPEND_METHOD_EMAIL = "EMAIL"


class SpendPinError(ValueError):
    """Un messaggio già scritto per il cliente, in italiano."""


def _pin_locked(pin: SpendPin) -> bool:
    return pin.locked_until is not None and pin.locked_until > datetime.now(UTC)


def _check_pin_shape(pin: str) -> None:
    """Quattro cifre, e non le più ovvie: 0000, 1111, 1234, 4321 sono le
    prime che prova chiunque abbia in mano un telefono sbloccato."""
    if len(pin) != 4 or not pin.isdigit():
        raise SpendPinError("Il PIN deve essere di 4 cifre.")
    if len(set(pin)) == 1 or pin in "0123456789" or pin in "9876543210":
        raise SpendPinError("Scegli un PIN meno prevedibile: niente cifre tutte uguali o in fila.")


async def get_spend_pin(db: AsyncSession, *, user_id: uuid.UUID) -> SpendPin | None:
    found = await db.execute(select(SpendPin).where(SpendPin.user_id == user_id))
    return found.scalar_one_or_none()


def spend_pin_status(pin: SpendPin | None) -> dict:
    """Cosa sa il browser: se il PIN è acceso e se è bloccato. Mai l'hash."""
    enabled = bool(pin and pin.enabled and pin.pin_hash)
    locked = bool(enabled and pin is not None and _pin_locked(pin))
    return {
        "enabled": enabled,
        "locked_until": pin.locked_until if locked and pin is not None else None,
        # Il metodo che il checkout userà adesso: con il PIN bloccato si torna
        # all'email finché il blocco non scade.
        "method": SPEND_METHOD_PIN if enabled and not locked else SPEND_METHOD_EMAIL,
    }


def _spend_pin_email(user: User, *, heading: str, body: str) -> None:
    send_html_email_best_effort(
        context=f"Spend-PIN notice (user={user.id})",
        to=user.email,
        subject=f"{heading} - Jav",
        html_body=render_email(
            preheader=heading, heading=heading,
            body_html=(
                f"<p>{body}</p>"
                "<p>Se non sei stato tu, cambia subito la password del tuo account e scrivici dal "
                "Supporto.</p>"
            ),
        ),
        text_body=f"{body}\n\nSe non sei stato tu, cambia subito la password e scrivici dal Supporto.",
    )


async def set_spend_pin(db: AsyncSession, *, user: User, pin: str, password: str) -> SpendPin:
    """Accende il PIN, o lo cambia. Chiede la password dell'account: una
    sessione rubata non deve bastare a sostituire il codice via email con un
    PIN scelto da chi l'ha rubata."""
    if not verify_password(password, user.password_hash):
        raise SpendPinError("La password non è corretta.")
    _check_pin_shape(pin)
    row = await get_spend_pin(db, user_id=user.id)
    if row is None:
        row = SpendPin(user_id=user.id)
        db.add(row)
    was_enabled = bool(row.enabled and row.pin_hash)
    row.pin_hash = hash_password(pin)
    row.enabled = True
    row.failed_attempts = 0
    row.locked_until = None
    row.updated_at = datetime.now(UTC)
    await audit_service.record(
        db, organization_id=user.organization_id, actor_user_id=user.id,
        action="spend_pin.changed" if was_enabled else "spend_pin.enabled",
        entity_type="user", entity_id=str(user.id),
    )
    await db.commit()
    await db.refresh(row)
    _spend_pin_email(
        user, heading="PIN dei JavCash " + ("cambiato" if was_enabled else "attivato"),
        body=(
            "Da adesso, per usare i tuoi JavCash in un acquisto, ti chiederemo il PIN che hai scelto "
            "invece di mandarti un codice via email."
        ),
    )
    return row


async def disable_spend_pin(db: AsyncSession, *, user: User, password: str) -> None:
    """Torna al codice via email. Il PIN si cancella, non si mette da parte:
    riaccenderlo vuol dire sceglierne uno di nuovo."""
    if not verify_password(password, user.password_hash):
        raise SpendPinError("La password non è corretta.")
    row = await get_spend_pin(db, user_id=user.id)
    if row is None or not row.enabled:
        return
    row.enabled = False
    row.pin_hash = None
    row.failed_attempts = 0
    row.locked_until = None
    row.updated_at = datetime.now(UTC)
    await audit_service.record(
        db, organization_id=user.organization_id, actor_user_id=user.id,
        action="spend_pin.disabled", entity_type="user", entity_id=str(user.id),
    )
    await db.commit()
    _spend_pin_email(
        user, heading="PIN dei JavCash disattivato",
        body="Da adesso, per usare i tuoi JavCash in un acquisto, ti manderemo di nuovo un codice via email.",
    )


async def request_spend_code(
    db: AsyncSession, *, user: User, context_line: str, via_email: bool = False
) -> str:
    """Il passo «mandami il codice» di ogni checkout. Con il PIN acceso non
    parte nessuna email e il checkout chiede il PIN; `via_email` è il «non
    ricordo il PIN»: il codice via email resta sempre possibile."""
    pin = await get_spend_pin(db, user_id=user.id)
    if not via_email and spend_pin_status(pin)["method"] == SPEND_METHOD_PIN:
        return SPEND_METHOD_PIN
    await request_otp(db, user=user, purpose=WALLET_CREDIT_SPEND_OTP_PURPOSE, context_line=context_line)
    return SPEND_METHOD_EMAIL


async def verify_spend_code(db: AsyncSession, *, user_id: uuid.UUID, code: str) -> bool:
    """Accetta il PIN (quattro cifre) o il codice via email (sei cifre).

    Il PIN sbagliato conta: al quinto errore si blocca per un quarto d'ora e
    il cliente riceve un'email, perché quattro cifre sbagliate di fila
    possono voler dire qualcuno che sta provando. Il conteggio si salva
    subito, indipendentemente da come finisce l'acquisto."""
    code = (code or "").strip()
    if len(code) != 4:
        return await verify_otp(db, user_id=user_id, purpose=WALLET_CREDIT_SPEND_OTP_PURPOSE, code=code)
    pin = await get_spend_pin(db, user_id=user_id)
    if pin is None or not pin.enabled or not pin.pin_hash or _pin_locked(pin):
        return False
    if verify_password(code, pin.pin_hash):
        if pin.failed_attempts:
            pin.failed_attempts = 0
            await db.commit()
        return True
    pin.failed_attempts += 1
    locked_now = pin.failed_attempts >= SPEND_PIN_MAX_ATTEMPTS
    if locked_now:
        pin.failed_attempts = 0
        pin.locked_until = datetime.now(UTC) + timedelta(minutes=SPEND_PIN_LOCK_MINUTES)
    await db.commit()
    if locked_now:
        user = await db.get(User, user_id)
        if user is not None:
            _spend_pin_email(
                user, heading="PIN dei JavCash bloccato",
                body=(
                    f"Il PIN è stato sbagliato {SPEND_PIN_MAX_ATTEMPTS} volte di fila, quindi l'abbiamo "
                    f"bloccato per {SPEND_PIN_LOCK_MINUTES} minuti. Nel frattempo, per usare i JavCash, "
                    "ti manderemo un codice via email."
                ),
            )
    return False
