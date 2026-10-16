"""Il conto dell'atleta (docs/club-portal.md, "Il conto dell'atleta").

Ogni atleta ha un **titolare** (`guardian_user_id`): il genitore di un
minore, o l'adulto stesso (atleta "me stesso"). Il titolare paga, carica le
prove, iscrive alle gare. In più l'atleta può avere **il suo accesso**
(`club_athletes.user_id`, ruolo ATHLETE) per la sua area: le lezioni del
mese, la presenza di oggi, cintura e medaglie, le quote **in lettura**, e
più avanti materiale formativo e giochi.

- **Chi crea l'accesso**: il titolare, dal conto famiglia. Un nome utente
  ("tiago.lagos") e una password, oppure l'email del ragazzo se ce l'ha; e/o
  un **QR** per entrare al volo (i più piccoli non ricordano una password).
  Un atleta senza email ha un indirizzo finto `<username>@atleta.invalid`:
  nessuna posta parte verso di lui (core/email.py), la password gliela
  reimposta il titolare.
- **Chi vede l'area**: l'atleta stesso, e il titolare (che apre l'area di
  ogni suo atleta, anche la propria se si allena). Nessun altro.
- **A 18 anni** l'atleta con un suo accesso può **diventare titolare del
  proprio conto** (proposta, mai automatica): da lì paga e gestisce da sé.
  Le quote già emesse restano a chi era titolare quando sono nate.
"""

import hashlib
import re
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email import PLACEHOLDER_EMAIL_DOMAIN, is_placeholder_address
from app.core.security import hash_password
from app.domains.audit import service as audit_service
from app.domains.club import seasons
from app.domains.club.models import (
    ClubAthlete,
    ClubAthleteLoginCode,
    ClubAttendance,
    ClubCourse,
    ClubCourseAthlete,
    ClubCourseSlot,
)
from app.domains.club.scope import scope_of
from app.domains.club.service import ClubNotFoundError, ClubValidationError
from app.domains.users.models import User

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,39}$")
MIN_PASSWORD = 6
#: Quanto vale un QR: abbastanza per un trimestre sul tablet di casa; poi se
#: ne crea un altro (e quello vecchio si può revocare prima).
QR_VALID_DAYS = 90
ADULT_AGE = 18


def age_on(birth: date, today: date) -> int:
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


async def _role_id(db: AsyncSession, organization_id: uuid.UUID, code: str) -> uuid.UUID:
    from app.domains.rbac.models import Role

    role = (
        await db.execute(
            select(Role).where(
                (Role.organization_id == organization_id) | (Role.organization_id.is_(None)), Role.code == code,
            )
        )
    ).scalars().first()
    if role is None:
        raise ClubValidationError("Il ruolo atleta non è ancora configurato: avvisa la segreteria.")
    return role.id


async def _grant(db: AsyncSession, user: User, code: str) -> None:
    from app.domains.rbac.models import UserRole

    role_id = await _role_id(db, user.organization_id, code)
    exists = (
        await db.execute(select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role_id))
    ).scalar_one_or_none()
    if exists is None:
        db.add(UserRole(user_id=user.id, organization_id=user.organization_id, role_id=role_id))


# --- Il titolare crea e gestisce l'accesso -------------------------------------------------------


def login_dict(athlete: ClubAthlete, user: User | None, codes: list[ClubAthleteLoginCode]) -> dict:
    now = datetime.now(UTC)
    active = [c for c in codes if c.revoked_at is None and c.expires_at > now]
    return {
        "athlete_id": athlete.id,
        "has_login": user is not None,
        "is_self": athlete.is_self,
        "username": user.username if user else None,
        "email": None if user is None or is_placeholder_address(user.email) else user.email,
        "active": user is not None and user.status == "ACTIVE",
        "qr_active_until": max((c.expires_at for c in active), default=None),
    }


async def _codes(db: AsyncSession, athlete_id: uuid.UUID) -> list[ClubAthleteLoginCode]:
    return list((await db.execute(
        select(ClubAthleteLoginCode).where(ClubAthleteLoginCode.athlete_id == athlete_id)
    )).scalars())


async def login_status(db: AsyncSession, *, athlete: ClubAthlete) -> dict:
    user = await db.get(User, athlete.user_id) if athlete.user_id else None
    return login_dict(athlete, user, await _codes(db, athlete.id))


async def set_login(
    db: AsyncSession, *, athlete: ClubAthlete, actor_user_id: uuid.UUID,
    username: str | None, email: str | None, password: str | None,
) -> dict:
    """Crea o aggiorna l'accesso dell'atleta. Alla creazione servono un nome
    utente e una password (l'email è facoltativa); dopo, ogni campo si cambia
    da solo (una password nuova = "l'ha dimenticata")."""
    if athlete.is_self:
        raise ClubValidationError("Sei tu: entri già con il tuo account.")
    user = await db.get(User, athlete.user_id) if athlete.user_id else None
    username = (username or "").strip().lower() or None
    email = (email or "").strip().lower() or None
    if username is not None and not USERNAME_RE.match(username):
        raise ClubValidationError(
            "Il nome utente: da 3 a 40 caratteri, lettere minuscole, numeri, punto, trattino (es. tiago.lagos)."
        )
    if password is not None and len(password.strip()) < MIN_PASSWORD:
        raise ClubValidationError(f"La password deve avere almeno {MIN_PASSWORD} caratteri.")
    if email is not None and ("@" not in email or is_placeholder_address(email)):
        raise ClubValidationError("L'email non è valida.")
    if user is None and (username is None or password is None):
        raise ClubValidationError("Per creare l'accesso servono un nome utente e una password.")

    org = athlete.organization_id
    if username is not None:
        taken = (await db.execute(
            select(User.id).where(User.organization_id == org, User.username == username)
        )).scalar_one_or_none()
        if taken is not None and (user is None or taken != user.id):
            raise ClubValidationError("Questo nome utente è già usato: scegline un altro.")
    if email is not None:
        taken = (await db.execute(
            select(User.id).where(User.organization_id == org, func.lower(User.email) == email)
        )).scalar_one_or_none()
        if taken is not None and (user is None or taken != user.id):
            raise ClubValidationError("Esiste già un account con questa email.")

    created = user is None
    if user is None:
        now = datetime.now(UTC)
        user = User(
            organization_id=org, club_id=athlete.club_id, username=username,
            email=email or f"{username}@{PLACEHOLDER_EMAIL_DOMAIN}", password_hash=hash_password(password.strip()),
            status="ACTIVE",
            # Il titolare ha accettato privacy e verificato la sua email: per
            # l'accesso di suo figlio non si ripetono i cancelli dell'adulto.
            email_verified_at=now, privacy_accepted_at=now,
        )
        db.add(user)
        await db.flush()
        await _grant(db, user, "ATHLETE")
        athlete.user_id = user.id
    else:
        if username is not None and username != user.username:
            if is_placeholder_address(user.email):
                user.email = f"{username}@{PLACEHOLDER_EMAIL_DOMAIN}"
            user.username = username
        if email is not None:
            user.email = email
        if password is not None:
            user.password_hash = hash_password(password.strip())
            user.failed_login_attempts = 0
            user.locked_until = None
        user.status = "ACTIVE"
    await audit_service.record(
        db, organization_id=org, actor_user_id=actor_user_id,
        action="club.athlete_login_created" if created else "club.athlete_login_updated",
        entity_type="club_athlete", entity_id=str(athlete.id),
        new_value={"username": user.username, "password_changed": password is not None},
    )
    await db.commit()
    return await login_status(db, athlete=athlete)


async def disable_login(db: AsyncSession, *, athlete: ClubAthlete, actor_user_id: uuid.UUID) -> dict:
    """Spegne l'accesso (e ogni QR): l'account resta, con la sua storia, e si
    riaccende impostando una password nuova."""
    if athlete.is_self or athlete.user_id is None:
        raise ClubValidationError("Questo atleta non ha un accesso suo da spegnere.")
    user = await db.get(User, athlete.user_id)
    user.status = "FROZEN"
    await _revoke_codes(db, athlete.id)
    from app.domains.auth import service as auth_service

    await auth_service.revoke_all_sessions(db, user_id=user.id)
    await audit_service.record(
        db, organization_id=athlete.organization_id, actor_user_id=actor_user_id,
        action="club.athlete_login_disabled", entity_type="club_athlete", entity_id=str(athlete.id),
    )
    await db.commit()
    return await login_status(db, athlete=athlete)


async def _revoke_codes(db: AsyncSession, athlete_id: uuid.UUID) -> None:
    now = datetime.now(UTC)
    for code in await _codes(db, athlete_id):
        if code.revoked_at is None:
            code.revoked_at = now


async def create_qr(db: AsyncSession, *, athlete: ClubAthlete, actor_user_id: uuid.UUID) -> tuple[str, dict]:
    """Un QR nuovo (quelli vecchi si revocano: uno solo vale alla volta).
    Il codice in chiaro esce solo qui, una volta."""
    if athlete.user_id is None or athlete.is_self:
        raise ClubValidationError("Prima crea l'accesso dell'atleta (nome utente e password).")
    user = await db.get(User, athlete.user_id)
    if user.status != "ACTIVE":
        raise ClubValidationError("L'accesso di questo atleta è spento: riaccendilo con una password nuova.")
    await _revoke_codes(db, athlete.id)
    code = secrets.token_urlsafe(32)
    db.add(ClubAthleteLoginCode(
        organization_id=athlete.organization_id, athlete_id=athlete.id, token_hash=_hash(code),
        created_by_user_id=actor_user_id, expires_at=datetime.now(UTC) + timedelta(days=QR_VALID_DAYS),
    ))
    await audit_service.record(
        db, organization_id=athlete.organization_id, actor_user_id=actor_user_id,
        action="club.athlete_qr_created", entity_type="club_athlete", entity_id=str(athlete.id),
    )
    await db.commit()
    return code, await login_status(db, athlete=athlete)


async def revoke_qr(db: AsyncSession, *, athlete: ClubAthlete, actor_user_id: uuid.UUID) -> dict:
    await _revoke_codes(db, athlete.id)
    await audit_service.record(
        db, organization_id=athlete.organization_id, actor_user_id=actor_user_id,
        action="club.athlete_qr_revoked", entity_type="club_athlete", entity_id=str(athlete.id),
    )
    await db.commit()
    return await login_status(db, athlete=athlete)


class LoginCodeError(Exception):
    pass


async def user_for_code(db: AsyncSession, *, organization_id: uuid.UUID, code: str) -> User:
    """L'account dell'atleta dietro un QR valido. Un codice sconosciuto,
    scaduto, revocato o di un accesso spento dà lo stesso errore."""
    row = (await db.execute(
        select(ClubAthleteLoginCode).where(
            ClubAthleteLoginCode.token_hash == _hash(code), ClubAthleteLoginCode.organization_id == organization_id,
        )
    )).scalar_one_or_none()
    now = datetime.now(UTC)
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        raise LoginCodeError("Questo QR non vale più: chiedi a chi gestisce il tuo conto di crearne uno nuovo.")
    athlete = await db.get(ClubAthlete, row.athlete_id)
    user = await db.get(User, athlete.user_id) if athlete and athlete.user_id else None
    if user is None or user.status != "ACTIVE" or athlete.status != "ACTIVE":
        raise LoginCodeError("Questo QR non vale più: chiedi a chi gestisce il tuo conto di crearne uno nuovo.")
    row.last_used_at = now
    return user


# --- L'area dell'atleta -------------------------------------------------------------------------


async def area_athletes(db: AsyncSession, *, user_id: uuid.UUID, club_id: uuid.UUID) -> list[ClubAthlete]:
    """Le aree che questo account può aprire: la propria (se è un atleta) e
    quelle degli atleti di cui è titolare. Prima la propria."""
    rows = list((await db.execute(
        select(ClubAthlete).where(
            ClubAthlete.club_id == club_id, ClubAthlete.status == "ACTIVE",
            (ClubAthlete.user_id == user_id) | (ClubAthlete.guardian_user_id == user_id),
        ).order_by(ClubAthlete.first_name)
    )).scalars())
    return sorted(rows, key=lambda a: a.user_id != user_id)


async def area_athlete(db: AsyncSession, *, user_id: uuid.UUID, club_id: uuid.UUID, athlete_id: uuid.UUID) -> ClubAthlete:
    athlete = await db.get(ClubAthlete, athlete_id)
    if (
        athlete is None or athlete.club_id != club_id
        or (athlete.user_id != user_id and athlete.guardian_user_id != user_id)
    ):
        raise ClubNotFoundError("Atleta non trovato.")
    return athlete


async def month_lessons(db: AsyncSession, *, athlete: ClubAthlete, today: date) -> list[dict]:
    """Le lezioni del mese dei corsi a cui l'atleta è iscritto, ognuna con il
    suo stato: PRESENT, ABSENT (segnata assente), MISSED (passata senza
    presenza), TODAY, UPCOMING."""
    first = today.replace(day=1)
    nxt = (first + timedelta(days=32)).replace(day=1)
    rows = (await db.execute(
        select(ClubCourse, ClubCourseSlot)
        .join(ClubCourseAthlete, ClubCourseAthlete.course_id == ClubCourse.id)
        .join(ClubCourseSlot, ClubCourseSlot.course_id == ClubCourse.id)
        .where(ClubCourseAthlete.athlete_id == athlete.id, ClubCourse.active.is_(True))
    )).all()
    marks = {
        (course_id, day): present
        for course_id, day, present in (await db.execute(
            select(ClubAttendance.course_id, ClubAttendance.date, ClubAttendance.present).where(
                ClubAttendance.athlete_id == athlete.id, ClubAttendance.date >= first, ClubAttendance.date < nxt,
            )
        )).all()
    }
    out: list[dict] = []
    seen: set[tuple] = set()
    day = first
    while day < nxt:
        for course, slot in sorted(rows, key=lambda r: r[1].starts_at):
            if slot.weekday != day.weekday() or (course.id, day) in seen:
                continue
            seen.add((course.id, day))
            mark = marks.get((course.id, day))
            status = (
                "PRESENT" if mark is True else "ABSENT" if mark is False
                else "TODAY" if day == today else "UPCOMING" if day > today else "MISSED"
            )
            out.append({
                "date": day, "course_id": course.id, "course_name": course.name,
                "starts_at": slot.starts_at, "ends_at": slot.ends_at, "status": status,
            })
        day += timedelta(days=1)
    return out


async def area(db: AsyncSession, *, athlete: ClubAthlete, viewer_user_id: uuid.UUID, today: date) -> dict:
    """Tutto ciò che la pagina dell'atleta mostra. Le quote ci sono in
    lettura; `can_manage` dice se chi guarda è il titolare (lui paga)."""
    from app.domains.club import family as family_service

    detail = await family_service.athlete_detail(db, athlete=athlete, today=today)
    lessons = await month_lessons(db, athlete=athlete, today=today)
    age = age_on(athlete.birth_date, today)
    own = athlete.user_id == viewer_user_id
    return {
        **detail,
        "age": age,
        "is_minor": age < ADULT_AGE,
        "viewer_is_athlete": own,
        "can_manage": athlete.guardian_user_id == viewer_user_id,
        # Pagare (caricare la prova delle sue quote): il titolare, o l'atleta
        # stesso con il suo accesso dai 18 anni di età federale.
        "can_pay": athlete.guardian_user_id == viewer_user_id
        or (own and seasons.federal_age(athlete.birth_date, today.year) >= ADULT_AGE),
        # Diventare titolare: solo l'atleta stesso, maggiorenne, con un suo
        # accesso, che ancora non lo è.
        "can_become_holder": own and age >= ADULT_AGE and not athlete.is_self
        and athlete.guardian_user_id != viewer_user_id,
        "today": today,
        "lessons": lessons,
        "month_present": sum(1 for lesson in lessons if lesson["status"] == "PRESENT"),
        "month_total": sum(1 for lesson in lessons if lesson["status"] != "UPCOMING"),
    }


async def mark_today(
    db: AsyncSession, *, athlete: ClubAthlete, course_id: uuid.UUID, present: bool, actor_user_id: uuid.UUID,
) -> None:
    """La presenza di oggi segnata dall'atleta (o dal titolare dalla sua
    area): le stesse regole di quando la segna il genitore."""
    from app.domains.club import lessons as lessons_service

    await lessons_service.family_mark(
        db, scope=scope_of(athlete), guardian_user_id=athlete.guardian_user_id, athlete_id=athlete.id,
        course_id=course_id, present=present, note=None, actor_user_id=actor_user_id,
    )


async def become_holder(
    db: AsyncSession, *, athlete: ClubAthlete, user_id: uuid.UUID, email: str | None, today: date,
) -> None:
    """L'atleta maggiorenne diventa titolare del suo conto: da qui paga,
    carica le prove e iscrive alle gare da sé. Serve un'email vera (le quote
    e le conferme arrivano lì). Le quote già emesse non cambiano titolare."""
    if athlete.user_id != user_id or athlete.is_self:
        raise ClubValidationError("Solo l'atleta può diventare titolare del suo conto.")
    if age_on(athlete.birth_date, today) < ADULT_AGE:
        raise ClubValidationError("Si diventa titolari del proprio conto a 18 anni.")
    user = await db.get(User, user_id)
    email = (email or "").strip().lower() or None
    if is_placeholder_address(user.email):
        if email is None or "@" not in email or is_placeholder_address(email):
            raise ClubValidationError("Per gestire quote e pagamenti serve la tua email.")
        taken = (await db.execute(
            select(User.id).where(User.organization_id == user.organization_id, func.lower(User.email) == email)
        )).scalar_one_or_none()
        if taken is not None and taken != user.id:
            raise ClubValidationError("Esiste già un account con questa email.")
        user.email = email
        # Un'email scritta da lui e mai verificata: la verifica la chiede il
        # cancello dell'area famiglia, come per ogni adulto.
        user.email_verified_at = None
    other_self = (await db.execute(
        select(ClubAthlete.id).where(ClubAthlete.guardian_user_id == user_id, ClubAthlete.is_self.is_(True))
    )).scalar_one_or_none()
    if other_self is not None:
        raise ClubValidationError("Questo account è già titolare di un atleta \"me stesso\".")
    old_guardian = athlete.guardian_user_id
    athlete.guardian_user_id = user_id
    athlete.is_self = True
    await _grant(db, user, "CUSTOMER")
    await _ensure_customer(db, user=user, athlete=athlete)
    await audit_service.record(
        db, organization_id=athlete.organization_id, actor_user_id=user_id,
        action="club.athlete_became_holder", entity_type="club_athlete", entity_id=str(athlete.id),
        previous_value={"guardian_user_id": str(old_guardian)}, new_value={"guardian_user_id": str(user_id)},
    )
    await db.commit()


async def _ensure_customer(db: AsyncSession, *, user: User, athlete: ClubAthlete) -> None:
    """Il titolare ha un Customer come ogni famiglia (Shop, contabilità)."""
    from app.domains.customers.models import Customer, CustomerProfile

    exists = (await db.execute(select(Customer).where(Customer.user_id == user.id))).scalar_one_or_none()
    if exists is not None:
        return
    customer = Customer(organization_id=user.organization_id, user_id=user.id, kind="PRIVATE", email=user.email)
    db.add(customer)
    await db.flush()
    db.add(CustomerProfile(customer_id=customer.id, first_name=athlete.first_name, last_name=athlete.last_name))
