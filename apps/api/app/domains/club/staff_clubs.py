"""I treinador di più club. Specifica: docs/club-portal.md, "Un treinador,
più club".

Un account solo può allenare in più club: ogni club in cui è treinador è una
riga di `club_staff_memberships` (ACTIVE). Entrando nell'area del treinador
sceglie il club (i «pulsantoni» con logo, atleti e corsi): il frontend
ricorda la scelta nel cookie `jav_staff_club`, e club/scope.py la applica
solo alle rotte del treinador. Nel club dell'account (`users.club_id`) resta
quello che era, segreteria compresa; negli altri è solo treinador.

- il **superadmin** assegna e toglie i treinador di ogni club (e approva le
  richieste);
- la **segreteria** di un club chiede un treinador che ha già l'account in
  un altro club (REQUESTED: lo vede il superadmin), e può togliere dal suo
  club un treinador che viene da un altro;
- un treinador nuovo creato dalla segreteria (clubs.add_staff) entra
  ACTIVE nel suo club.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.club.models import Club, ClubAthlete, ClubStaffMembership
from app.domains.club.service import ClubNotFoundError, ClubValidationError
from app.domains.rbac.models import Role, UserRole
from app.domains.users.models import User

COACH_ROLE = "INSTRUCTOR"


async def coach_ids_by_club(db: AsyncSession, *, club_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[uuid.UUID, str]]:
    """Per ogni club, i treinador con il loro stato (ACTIVE / REQUESTED)."""
    if not club_ids:
        return {}
    out: dict[uuid.UUID, dict[uuid.UUID, str]] = {}
    for club_id, user_id, status in (await db.execute(select(
        ClubStaffMembership.club_id, ClubStaffMembership.user_id, ClubStaffMembership.status,
    ).where(ClubStaffMembership.club_id.in_(club_ids)))).all():
        out.setdefault(club_id, {})[user_id] = status
    return out


async def active_coach_ids(db: AsyncSession, *, club_id: uuid.UUID) -> set[uuid.UUID]:
    """I treinador del club: gli istruttori del club stesso (lo restano finché
    hanno il ruolo, anche senza la riga, come quelli importati) e quelli che
    vengono da un altro club con l'appartenenza ACTIVE."""
    home = set((await db.execute(
        select(User.id).join(UserRole, UserRole.user_id == User.id).join(Role, Role.id == UserRole.role_id)
        .where(User.club_id == club_id, Role.code == COACH_ROLE)
    )).scalars())
    return home | {uid for uid, st in (await coach_ids_by_club(db, club_ids=[club_id])).get(club_id, {}).items()
                   if st == "ACTIVE"}


async def _is_coach_account(db: AsyncSession, user_id: uuid.UUID) -> bool:
    return (await db.execute(
        select(UserRole.id).join(Role, Role.id == UserRole.role_id)
        .where(UserRole.user_id == user_id, Role.code == COACH_ROLE)
    )).first() is not None


async def ensure_home_membership(db: AsyncSession, *, user: User, actor_user_id: uuid.UUID | None) -> None:
    """Il treinador nel suo club: la riga ACTIVE. Non fa commit."""
    if user.club_id is None:
        return
    row = (await db.execute(select(ClubStaffMembership).where(
        ClubStaffMembership.club_id == user.club_id, ClubStaffMembership.user_id == user.id,
    ))).scalar_one_or_none()
    if row is None:
        db.add(ClubStaffMembership(organization_id=user.organization_id, club_id=user.club_id, user_id=user.id,
                                   status="ACTIVE", requested_by_user_id=actor_user_id,
                                   decided_by_user_id=actor_user_id, decided_at=utcnow()))
    elif row.status != "ACTIVE":
        row.status, row.decided_by_user_id, row.decided_at = "ACTIVE", actor_user_id, utcnow()


async def _coach_by_email_or_id(db: AsyncSession, *, organization_id: uuid.UUID, email: str | None,
                                user_id: uuid.UUID | None) -> User:
    if user_id is not None:
        user = await db.get(User, user_id)
    else:
        clean = (email or "").strip().lower()
        user = (await db.execute(select(User).where(
            User.organization_id == organization_id, func.lower(User.email) == clean,
        ))).scalar_one_or_none()
    if user is None or user.organization_id != organization_id:
        raise ClubNotFoundError("Non c'è un account con questa email.")
    if not await _is_coach_account(db, user.id):
        raise ClubValidationError("Questo account non è un treinador: crealo come istruttore dallo staff del suo club.")
    return user


async def assign(db: AsyncSession, *, organization_id: uuid.UUID, club_id: uuid.UUID, actor_user_id: uuid.UUID,
                 email: str | None = None, user_id: uuid.UUID | None = None) -> ClubStaffMembership:
    """Il superadmin mette un treinador in un club (o approva la richiesta)."""
    club = await db.get(Club, club_id)
    if club is None or club.organization_id != organization_id:
        raise ClubNotFoundError("Club non trovato.")
    user = await _coach_by_email_or_id(db, organization_id=organization_id, email=email, user_id=user_id)
    row = (await db.execute(select(ClubStaffMembership).where(
        ClubStaffMembership.club_id == club.id, ClubStaffMembership.user_id == user.id,
    ))).scalar_one_or_none()
    if row is None:
        row = ClubStaffMembership(organization_id=organization_id, club_id=club.id, user_id=user.id,
                                  requested_by_user_id=actor_user_id)
        db.add(row)
    row.status, row.decided_by_user_id, row.decided_at = "ACTIVE", actor_user_id, utcnow()
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id, action="clubs.coach_assigned",
        entity_type="club", entity_id=str(club.id), new_value={"user_id": str(user.id)},
    )
    await db.commit()
    await db.refresh(row)
    if user.club_id is None:
        # Un treinador senza club di casa prende il primo che gli si assegna:
        # è lì che vive il suo account (famiglia, avvisi).
        user.club_id = club.id
        await db.commit()
    return row


async def request(db: AsyncSession, *, organization_id: uuid.UUID, club_id: uuid.UUID, actor_user_id: uuid.UUID,
                  email: str) -> ClubStaffMembership:
    """La segreteria chiede un treinador che ha l'account in un altro club:
    resta REQUESTED finché il superadmin non lo approva."""
    from app.domains.notifications import service as notifications_service

    user = await _coach_by_email_or_id(db, organization_id=organization_id, email=email, user_id=None)
    if user.club_id == club_id:
        raise ClubValidationError("È già un treinador di questo club.")
    row = (await db.execute(select(ClubStaffMembership).where(
        ClubStaffMembership.club_id == club_id, ClubStaffMembership.user_id == user.id,
    ))).scalar_one_or_none()
    if row is not None:
        raise ClubValidationError("È già un treinador di questo club." if row.status == "ACTIVE"
                                  else "La richiesta per questo treinador è già partita.")
    row = ClubStaffMembership(organization_id=organization_id, club_id=club_id, user_id=user.id, status="REQUESTED",
                              requested_by_user_id=actor_user_id)
    db.add(row)
    await db.flush()
    club = await db.get(Club, club_id)
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id, action="clubs.coach_requested",
        entity_type="club", entity_id=str(club_id), new_value={"user_id": str(user.id)},
    )
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="CLUB_COACH_REQUESTED", entity_type="club", entity_id=club_id,
        title=f"{club.name if club else 'Un club'} chiede un treinador: {user.email}",
        body="Approva o rifiuta dal pannello Club → staff del club.",
        exclude_user_id=actor_user_id,
    )
    await db.commit()
    await db.refresh(row)
    return row


async def remove(db: AsyncSession, *, organization_id: uuid.UUID, club_id: uuid.UUID, user_id: uuid.UUID,
                 actor_user_id: uuid.UUID, by_secretary: bool) -> None:
    """Toglie un treinador da un club (o rifiuta la richiesta). La segreteria
    toglie solo chi viene da un altro club (anche il superadmin): nel club
    dell'account il treinador lo è finché ha il ruolo."""
    row = (await db.execute(select(ClubStaffMembership).where(
        ClubStaffMembership.club_id == club_id, ClubStaffMembership.user_id == user_id,
        ClubStaffMembership.organization_id == organization_id,
    ))).scalar_one_or_none()
    if row is None:
        raise ClubNotFoundError("Treinador non trovato in questo club.")
    user = await db.get(User, user_id)
    if user is not None and user.club_id == club_id:
        # Nel club del suo account resta treinador finché ha il ruolo: lì si
        # toglie il ruolo, non l'appartenenza.
        raise ClubValidationError("Questo treinador è del club: qui si toglie il ruolo di istruttore, non il club.")
    await db.delete(row)
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id, action="clubs.coach_removed",
        entity_type="club", entity_id=str(club_id), new_value={"user_id": str(user_id)},
    )
    await db.commit()


async def coach_profile(db: AsyncSession, *, user: User) -> dict:
    """Il nome e la foto per il saluto: la foto del profilo, o quella della
    sua scheda di atleta se si allena anche lui."""
    from app.domains.club.people import _names

    names = await _names(db, {user.id})
    photo = user.photo_url
    if not photo:
        photo = (await db.execute(select(ClubAthlete.photo_url).where(
            ClubAthlete.guardian_user_id == user.id, ClubAthlete.is_self.is_(True),
            ClubAthlete.photo_url.is_not(None),
        ).limit(1))).scalar_one_or_none()
    name = names.get(user.id) or user.email
    return {"user_id": user.id, "name": name, "first_name": name.split()[0] if "@" not in name else None,
            "photo_url": photo}


async def my_clubs(db: AsyncSession, *, user: User, can_instruct_home: bool) -> dict:
    """I club in cui chi entra è treinador: il suo (se lì è staff) e quelli
    delle appartenenze ACTIVE, con logo, colori, atleti attivi e i suoi corsi."""
    from app.domains.club import courses as courses_service
    from app.domains.club.scope import ClubScope
    from app.domains.club.site_models import ClubSite

    ids = set((await db.execute(select(ClubStaffMembership.club_id).where(
        ClubStaffMembership.user_id == user.id, ClubStaffMembership.status == "ACTIVE",
    ))).scalars())
    if user.club_id is not None and can_instruct_home:
        ids.add(user.club_id)
    clubs = [c for c in (await db.execute(select(Club).where(Club.id.in_(ids)))).scalars() if c.status == "ACTIVE"] \
        if ids else []
    sites = {s.club_id: s for s in (await db.execute(select(ClubSite).where(
        ClubSite.club_id.in_([c.id for c in clubs]),
    ))).scalars()} if clubs else {}
    athletes = dict((await db.execute(
        select(ClubAthlete.club_id, func.count()).where(
            ClubAthlete.club_id.in_([c.id for c in clubs]), ClubAthlete.status == "ACTIVE",
        ).group_by(ClubAthlete.club_id)
    )).all()) if clubs else {}
    out = []
    for c in clubs:
        site = sites.get(c.id)
        taught = await courses_service.taught_course_ids(
            db, scope=ClubScope(organization_id=c.organization_id, club_id=c.id), user_id=user.id)
        out.append({
            "id": c.id, "name": c.name, "kind": c.kind, "home": c.id == user.club_id,
            "logo_url": site.logo_url if site else None,
            "brand_primary": site.brand_primary if site else None,
            "brand_secondary": site.brand_secondary if site else None,
            "athletes": int(athletes.get(c.id) or 0), "my_courses": len(taught),
        })
    out.sort(key=lambda c: (not c["home"], c["name"].lower()))
    return {"me": await coach_profile(db, user=user), "clubs": out}


async def coaches_overview(db: AsyncSession, *, organization_id: uuid.UUID) -> list[dict]:
    """Per il superadmin: ogni account da treinador con i suoi club."""
    from app.domains.club.people import _names

    users = list((await db.execute(
        select(User).join(UserRole, UserRole.user_id == User.id).join(Role, Role.id == UserRole.role_id)
        .where(User.organization_id == organization_id, Role.code == COACH_ROLE).distinct()
    )).scalars())
    rows = (await db.execute(select(ClubStaffMembership, Club.name).join(Club, Club.id == ClubStaffMembership.club_id)
                             .where(ClubStaffMembership.user_id.in_([u.id for u in users])))).all() if users else []
    clubs: dict[uuid.UUID, list[dict]] = {}
    for m, club_name in rows:
        clubs.setdefault(m.user_id, []).append({"club_id": m.club_id, "name": club_name, "status": m.status})
    names = await _names(db, {u.id for u in users})
    return sorted(({"user_id": u.id, "email": u.email, "name": names.get(u.id, u.email), "home_club_id": u.club_id,
                    "photo_url": u.photo_url, "clubs": sorted(clubs.get(u.id, []), key=lambda c: c["name"])}
                   for u in users), key=lambda r: r["name"].lower())


async def set_photo(db: AsyncSession, *, user: User, url: str | None, actor_user_id: uuid.UUID) -> User:
    user.photo_url = url
    await audit_service.record(
        db, organization_id=user.organization_id, actor_user_id=actor_user_id, action="users.photo_updated",
        entity_type="user", entity_id=str(user.id),
    )
    await db.commit()
    await db.refresh(user)
    return user
