"""I club della piattaforma: crearli, modificarli, dar loro una segreteria.

Lo fa il superadmin (`clubs.manage`). Un club nasce con il suo indirizzo
(`/c/<slug>`, da dare alle famiglie per registrarsi) e, se indicata, con la
sua segreteria: un account legato al club che riceve l'invito a scegliersi
la password. Da lì in avanti il club lo manda avanti la segreteria.
"""

import re
import secrets
import unicodedata
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.domains.audit import service as audit_service
from app.domains.club import kinds
from app.domains.club.models import Club, ClubAthlete, ClubPlan
from app.domains.club.scope import ClubScope
from app.domains.club.service import ClubNotFoundError, ClubValidationError
from app.domains.rbac.models import Role, UserRole
from app.domains.users.models import User

#: Cosa un club tiene nelle sue impostazioni. Solo questi: il resto del JSONB
#: non lo scrive nessuno da fuori.
CLUB_SETTINGS_KEYS = (
    "bank_iban", "bank_account_holder", "bank_transfer_instructions", "contact_email",
    # L'ente a cui si chiede il trasporto per gare e stage (di solito il
    # comune): il default di ogni evento nuovo.
    "transport_entity_name", "transport_entity_email",
    # La lingua delle lettere che il club manda a terzi (trasporto): "pt",
    # "it" o "en".
    "letters_language",
)
LETTER_LANGUAGES = ("pt", "it", "en")
#: I ruoli che un club può dare ai suoi account di staff.
CLUB_STAFF_ROLES = ("SECRETARY", "INSTRUCTOR")


def slugify(name: str) -> str:
    """"Judo Clube de Lagos" -> "judo-clube-de-lagos"."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:80].strip("-")


def club_settings(club: Club) -> dict:
    return {key: (club.settings or {}).get(key) or None for key in CLUB_SETTINGS_KEYS}


async def list_clubs(db: AsyncSession, *, organization_id: uuid.UUID) -> list[dict]:
    """I club, con i numeri che servono a riconoscerli a colpo d'occhio."""
    clubs = list(
        (await db.execute(select(Club).where(Club.organization_id == organization_id).order_by(Club.name))).scalars()
    )
    ids = [c.id for c in clubs]
    athletes = dict(
        (
            await db.execute(
                select(ClubAthlete.club_id, func.count())
                .where(ClubAthlete.club_id.in_(ids), ClubAthlete.status == "ACTIVE")
                .group_by(ClubAthlete.club_id)
            )
        ).all()
    ) if ids else {}
    staff = await _staff_by_club(db, club_ids=ids)
    return [club_dict(c, athletes_active=athletes.get(c.id, 0), staff=staff.get(c.id, [])) for c in clubs]


def club_dict(club: Club, *, athletes_active: int = 0, staff: list[dict] | None = None) -> dict:
    return {
        "id": club.id,
        "name": club.name,
        "slug": club.slug,
        "status": club.status,
        "kind": club.kind,
        "created_at": club.created_at,
        "settings": club_settings(club),
        "athletes_active": athletes_active,
        "staff": staff or [],
    }


async def _staff_by_club(db: AsyncSession, *, club_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[dict]]:
    if not club_ids:
        return {}
    rows = (
        await db.execute(
            select(User.club_id, User.id, User.email, Role.code)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(User.club_id.in_(club_ids), Role.code.in_(CLUB_STAFF_ROLES))
            .order_by(User.email)
        )
    ).all()
    out: dict[uuid.UUID, list[dict]] = {}
    for club_id, user_id, email, role in rows:
        out.setdefault(club_id, []).append({"user_id": user_id, "email": email, "role": role})
    return out


async def get_club(db: AsyncSession, *, organization_id: uuid.UUID, club_id: uuid.UUID) -> Club:
    club = await db.get(Club, club_id)
    if club is None or club.organization_id != organization_id:
        raise ClubNotFoundError("Club non trovato.")
    return club


async def get_club_by_slug(db: AsyncSession, *, slug: str) -> Club | None:
    """Per la pagina pubblica di registrazione: solo un club attivo esiste."""
    return (
        await db.execute(select(Club).where(Club.slug == slug.strip().lower(), Club.status == "ACTIVE"))
    ).scalars().first()


async def _check_slug(db: AsyncSession, *, organization_id: uuid.UUID, slug: str, exclude: uuid.UUID | None = None) -> str:
    slug = slugify(slug)
    if len(slug) < 3:
        raise ClubValidationError("L'indirizzo del club deve avere almeno 3 lettere o cifre.")
    stmt = select(Club.id).where(Club.organization_id == organization_id, Club.slug == slug)
    if exclude is not None:
        stmt = stmt.where(Club.id != exclude)
    if (await db.execute(stmt)).first() is not None:
        raise ClubValidationError(f"L'indirizzo «{slug}» è già di un altro club: scegline un altro.")
    return slug


async def create_club(
    db: AsyncSession, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID, name: str, slug: str | None,
    settings: dict | None = None, secretary_email: str | None = None,
) -> tuple[Club, str | None]:
    """Il club e, se l'invito alla segreteria non è potuto partire (SMTP non
    configurato), il link di primo accesso da consegnarle a mano."""
    name = name.strip()
    if len(name) < 3:
        raise ClubValidationError("Scrivi il nome del club.")
    club = Club(
        organization_id=organization_id, name=name,
        slug=await _check_slug(db, organization_id=organization_id, slug=slug or name),
        status="ACTIVE",
        settings={k: v for k, v in (settings or {}).items() if k in CLUB_SETTINGS_KEYS and v},
    )
    db.add(club)
    await db.flush()
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="clubs.created", entity_type="club", entity_id=str(club.id),
        new_value={"name": club.name, "slug": club.slug},
    )
    await db.commit()
    await db.refresh(club)
    invite_link = None
    if secretary_email:
        _user, invite_link = await add_staff(
            db, scope=ClubScope(organization_id=organization_id, club_id=club.id), actor_user_id=actor_user_id,
            email=secretary_email, role="SECRETARY",
        )
    return club, invite_link


async def get_courses_unit(db: AsyncSession, *, organization_id: uuid.UUID) -> Club | None:
    return (
        await db.execute(select(Club).where(Club.organization_id == organization_id, Club.kind == kinds.JAV_COURSES))
    ).scalars().first()


async def ensure_courses_unit(db: AsyncSession, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID) -> Club:
    """L'unità "Cursos JAV" (club/kinds.py): se c'è la restituisce, se no
    la crea con il suo piano di default (25 € al mese, iscrizione 0, dai 3
    anni in su), che la segreteria poi può cambiare. Una sola per
    organizzazione: lo garantisce anche un indice UNIQUE parziale."""
    existing = await get_courses_unit(db, organization_id=organization_id)
    if existing is not None:
        return existing
    slug = kinds.COURSES_UNIT_SLUG
    taken = (
        await db.execute(select(Club.id).where(Club.organization_id == organization_id, Club.slug == slug))
    ).first()
    if taken is not None:
        slug = await _check_slug(db, organization_id=organization_id, slug=f"{slug}-escolas")
    club = Club(organization_id=organization_id, name=kinds.COURSES_UNIT_NAME, slug=slug, status="ACTIVE",
                settings={}, kind=kinds.JAV_COURSES)
    db.add(club)
    await db.flush()
    db.add(ClubPlan(
        organization_id=organization_id, club_id=club.id, name="Cursos nas escolas",
        description="Mensalidade dos cursos JAV nas escolas: sem inscrição.",
        min_age=3, max_age=None, monthly_fee_cents=kinds.COURSES_MONTHLY_FEE_CENTS, enrollment_fee_cents=0,
        due_day=10, active=True,
    ))
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="clubs.created", entity_type="club", entity_id=str(club.id),
        new_value={"name": club.name, "slug": club.slug, "kind": club.kind},
    )
    await db.commit()
    await db.refresh(club)
    return club


async def update_club(
    db: AsyncSession, *, organization_id: uuid.UUID, club_id: uuid.UUID, actor_user_id: uuid.UUID, changes: dict,
) -> Club:
    club = await get_club(db, organization_id=organization_id, club_id=club_id)
    if "name" in changes and changes["name"] is not None:
        if len(changes["name"].strip()) < 3:
            raise ClubValidationError("Scrivi il nome del club.")
        club.name = changes["name"].strip()
    if changes.get("slug"):
        club.slug = await _check_slug(db, organization_id=organization_id, slug=changes["slug"], exclude=club.id)
    if changes.get("status") is not None:
        if changes["status"] not in ("ACTIVE", "SUSPENDED"):
            raise ClubValidationError("Stato del club non valido.")
        club.status = changes["status"]
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="clubs.updated", entity_type="club", entity_id=str(club.id),
        new_value={k: v for k, v in changes.items() if k != "settings"},
    )
    await db.commit()
    await db.refresh(club)
    return club


async def update_club_settings(
    db: AsyncSession, *, scope: ClubScope, actor_user_id: uuid.UUID, changes: dict
) -> Club:
    """IBAN e contatti del club: li cura la sua segreteria. Si fondono con
    quelli che ci sono (una PATCH che non nomina un campo non lo tocca), e
    un campo vuoto lo cancella."""
    club = await get_club(db, organization_id=scope.organization_id, club_id=scope.club_id)
    updates = {k: (v.strip() or None) if isinstance(v, str) else v for k, v in changes.items() if k in CLUB_SETTINGS_KEYS}
    if updates.get("letters_language") and updates["letters_language"] not in LETTER_LANGUAGES:
        raise ClubValidationError("Lingua delle lettere non valida.")
    if updates.get("bank_iban"):
        updates["bank_iban"] = re.sub(r"\s+", "", updates["bank_iban"]).upper()
    # Una colonna JSONB modificata sul posto non risulta cambiata a
    # SQLAlchemy: va assegnato un dizionario nuovo.
    club.settings = {**(club.settings or {}), **updates}
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="clubs.settings_updated", entity_type="club", entity_id=str(club.id), new_value=updates,
    )
    await db.commit()
    await db.refresh(club)
    return club


async def add_staff(
    db: AsyncSession, *, scope: ClubScope, actor_user_id: uuid.UUID, email: str, role: str,
) -> tuple[User, str | None]:
    """Un account di staff del club (segreteria o istruttore), legato al
    club: vede solo quello. Riceve l'email per scegliersi la password; la
    password iniziale è casuale e nessuno la conosce.

    Se l'email non parte (SMTP non configurato) restituisce il link di primo
    accesso, perché chi crea l'account lo consegni a mano: altrimenti la
    persona non avrebbe modo di entrare."""
    from app.domains.auth import service as auth_service

    if role not in CLUB_STAFF_ROLES:
        raise ClubValidationError("Ruolo non valido: segreteria o istruttore.")
    email = email.strip().lower()
    if "@" not in email:
        raise ClubValidationError("Indirizzo email non valido.")
    club = await get_club(db, organization_id=scope.organization_id, club_id=scope.club_id)
    existing = (
        await db.execute(
            select(User).where(User.organization_id == scope.organization_id, func.lower(User.email) == email)
        )
    ).scalar_one_or_none()
    if existing is not None:
        # Un account c'è già: un'email è una persona, e una persona di un
        # altro club (o della piattaforma) non si sposta da qui.
        raise ClubValidationError(f"Esiste già un account con l'email {email}.")
    role_row = (
        await db.execute(
            select(Role).where(
                (Role.organization_id == scope.organization_id) | (Role.organization_id.is_(None)), Role.code == role
            )
        )
    ).scalars().first()
    if role_row is None:
        raise ClubValidationError("Il ruolo non è configurato: rilancia app.seed.bootstrap.")
    user = User(
        organization_id=scope.organization_id, club_id=club.id, email=email,
        password_hash=hash_password(secrets.token_urlsafe(32)), status="ACTIVE",
    )
    db.add(user)
    await db.flush()
    db.add(UserRole(user_id=user.id, organization_id=scope.organization_id, role_id=role_row.id))
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="clubs.staff_added", entity_type="club", entity_id=str(club.id),
        new_value={"email": email, "role": role},
    )
    await db.commit()
    await db.refresh(user)
    intro = (
        f"Il tuo account per la segreteria di {club.name} su Jav è pronto: da qui gestisci atleti, quote e gare del club."
        if role == "SECRETARY"
        else f"Il tuo account da istruttore di {club.name} su Jav è pronto: da qui segni presenze e cinture dei tuoi corsi."
    )
    link, sent = await auth_service.send_account_invite_email(
        db, user=user, invited_by_display_name=club.name, intro=intro
    )
    return user, None if sent else link


async def staff_access_link(
    db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, actor_user_id: uuid.UUID,
) -> str | None:
    """Un link nuovo per impostare la password, per una persona dello staff
    del club (segreteria o istruttore): serve a chi non ha mai ricevuto
    l'invito (le segreterie importate dal gestionale di prima) o l'ha perso.
    Lo stesso meccanismo dell'invito (auth_service.send_account_invite_email,
    vale 7 giorni): se l'email parte restituisce None, altrimenti il link da
    consegnare a mano. La password non passa mai da chi lo chiede."""
    from app.domains.auth import service as auth_service

    user = (
        await db.execute(
            select(User)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(User.id == user_id, User.club_id == scope.club_id, Role.code.in_(CLUB_STAFF_ROLES))
        )
    ).scalars().first()
    if user is None:
        raise ClubNotFoundError("Persona dello staff non trovata in questo club.")
    club = await get_club(db, organization_id=scope.organization_id, club_id=scope.club_id)
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="clubs.staff_access_link", entity_type="user", entity_id=str(user.id),
    )
    link, sent = await auth_service.send_account_invite_email(
        db, user=user, invited_by_display_name=club.name,
        intro=f"Ecco il tuo accesso a Jav per {club.name}: scegli la tua password con il link qui sotto.",
    )
    return None if sent else link


async def update_club_pricing(db: AsyncSession, *, scope: ClubScope, actor_user_id: uuid.UUID, changes: dict) -> dict:
    """Sconti e quote del club (pricing.py). Valgono per le quote emesse da
    adesso: quelle già emesse hanno il prezzo congelato (CLAUDE.md §5)."""
    from app.domains.club import pricing as pricing_rules

    club = await get_club(db, organization_id=scope.organization_id, club_id=scope.club_id)
    try:
        updates = pricing_rules.validate_pricing(changes)
    except ValueError as exc:
        raise ClubValidationError(str(exc)) from exc
    current = (club.settings or {}).get("pricing") or {}
    if "tier_discount_pct" in updates:
        updates["tier_discount_pct"] = {**(current.get("tier_discount_pct") or {}), **updates["tier_discount_pct"]}
    club.settings = {**(club.settings or {}), "pricing": {**current, **updates}}
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="clubs.pricing_updated", entity_type="club", entity_id=str(club.id), new_value=updates,
    )
    await db.commit()
    await db.refresh(club)
    return pricing_rules.get_pricing(club)


async def notify_club_staff(
    db: AsyncSession, *, scope: ClubScope, type_: str, entity_id: uuid.UUID, title: str, body: str | None = None,
    entity_type: str = "club_competition",
) -> None:
    """Una notifica alla segreteria del club (non allo staff della
    piattaforma, che vede tutti i club e non deve ricevere quelle di tutti).
    `entity_type` dice a che cosa si riferisce: una gara (il caso di sempre)
    o, per esempio, un messaggio scritto a JAVBOT."""
    from app.domains.notifications import service as notifications_service

    secretaries = (
        await db.execute(
            select(User.id)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(User.club_id == scope.club_id, Role.code == "SECRETARY", User.status == "ACTIVE")
        )
    ).scalars().all()
    for user_id in set(secretaries):
        await notifications_service.notify_user(
            db, organization_id=scope.organization_id, user_id=user_id, type_=type_,
            entity_type=entity_type, entity_id=entity_id, title=title, body=body,
        )
    await db.commit()


async def platform_overview(db: AsyncSession, *, organization_id: uuid.UUID, today) -> dict:
    """I numeri della piattaforma, club per club: chi gestisce tutti i club
    vede a colpo d'occhio dove ci sono atleti, quote scadute e incassi, e i
    prossimi eventi di tutti."""
    from app.domains.club import seasons
    from app.domains.club.models import ClubCompetition, ClubFee

    clubs = list(
        (await db.execute(select(Club).where(Club.organization_id == organization_id).order_by(Club.name))).scalars()
    )
    ids = [c.id for c in clubs]
    month = seasons.period_of(today)

    async def per_club(stmt) -> dict:
        return dict((await db.execute(stmt)).all()) if ids else {}

    athletes = await per_club(
        select(ClubAthlete.club_id, func.count())
        .where(ClubAthlete.club_id.in_(ids), ClubAthlete.status == "ACTIVE").group_by(ClubAthlete.club_id)
    )
    overdue = await per_club(
        select(ClubFee.club_id, func.coalesce(func.sum(ClubFee.amount_cents), 0))
        .where(ClubFee.club_id.in_(ids), ClubFee.status == "DUE", ClubFee.due_date < today).group_by(ClubFee.club_id)
    )
    paid_month = await per_club(
        select(ClubFee.club_id, func.coalesce(func.sum(ClubFee.amount_cents), 0))
        .where(ClubFee.club_id.in_(ids), ClubFee.status == "PAID", ClubFee.period == month, ClubFee.kind == "MONTHLY")
        .group_by(ClubFee.club_id)
    )
    issued_month = await per_club(
        select(ClubFee.club_id, func.coalesce(func.sum(ClubFee.amount_cents), 0))
        .where(ClubFee.club_id.in_(ids), ClubFee.period == month, ClubFee.kind == "MONTHLY")
        .group_by(ClubFee.club_id)
    )
    names = {c.id: c.name for c in clubs}
    events = (
        await db.execute(
            select(ClubCompetition)
            .where(ClubCompetition.club_id.in_(ids), ClubCompetition.ends_on >= today)
            .order_by(ClubCompetition.starts_on).limit(12)
        )
    ).scalars().all() if ids else []
    rows = [
        {
            "id": c.id, "name": c.name, "slug": c.slug, "status": c.status, "kind": c.kind,
            "athletes_active": int(athletes.get(c.id, 0)), "overdue_cents": int(overdue.get(c.id, 0)),
            "month_paid_cents": int(paid_month.get(c.id, 0)), "month_issued_cents": int(issued_month.get(c.id, 0)),
        }
        for c in clubs
    ]
    return {
        "month": month,
        "clubs": rows,
        "totals": {
            # Solo i club ufficiali: l'unità dei corsi JAV non è un club (club/kinds.py).
            "clubs_active": sum(1 for c in clubs if c.status == "ACTIVE" and c.kind == "CLUB"),
            "athletes_active": sum(r["athletes_active"] for r in rows),
            "overdue_cents": sum(r["overdue_cents"] for r in rows),
            "month_paid_cents": sum(r["month_paid_cents"] for r in rows),
            "month_issued_cents": sum(r["month_issued_cents"] for r in rows),
        },
        "upcoming_events": [
            {"id": e.id, "club_id": e.club_id, "club_name": names[e.club_id], "name": e.name, "kind": e.kind,
             "starts_on": e.starts_on, "location": e.location, "status": e.status}
            for e in events
        ],
    }
