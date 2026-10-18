"""I corsi esterni: iscrizioni, mensilità, prove di pagamento, presenze, turni,
avvisi e conti. Specifica: docs/club-portal.md, "Corsi esterni"; tabelle
in extcourses/models.py.

Chi vede che cosa lo decidono le righe, non i ruoli:

- il **genitore** vede i partecipanti che ha iscritto lui
  (`parent_user_id`) e i loro corsi;
- la **scuola** e il **treinador** vedono i corsi a cui sono legati da una
  riga ACTIVE di `ext_staff` (la scuola: iscritti, contatti, pagamenti,
  prove, presenze; il treinador: gruppi, presenze, turni, i suoi guadagni);
- il **superadmin** (`clubs.manage`) vede tutto.

Il denaro come nei club: ogni importo si calcola qui; la prova caricata
segna subito pagate le mensilità scelte (la scuola o il superadmin la può
rifiutare: tornano da pagare); le mensilità sono UNIQUE per partecipante e
mese, quindi il lavoro mensile può girare due volte senza doppioni.
"""

import secrets
import uuid
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.core.security import hash_password
from app.domains.audit import service as audit_service
from app.domains.extcourses.models import (
    PAYMENT_METHODS,
    ExtAttendance,
    ExtCourse,
    ExtFee,
    ExtGroup,
    ExtNotice,
    ExtParticipant,
    ExtProof,
    ExtStaff,
    ExtWorkSession,
)
from app.domains.users.models import User

MAX_CHILDREN = 6
DEFAULT_SHARE = Decimal("50")


class ExtError(Exception):
    pass


class ExtNotFound(ExtError):
    pass


class ExtValidation(ExtError):
    pass


class ExtAccountExists(ExtError):
    """L'email ha già un account: si entra e si iscrive da dentro."""


def _age(birth: date, on: date) -> int:
    return on.year - birth.year - ((on.month, on.day) < (birth.month, birth.day))


def _period(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _euro(cents: int) -> str:
    return f"{cents / 100:.2f} €".replace(".", ",")


# --- Lettura dei corsi ----------------------------------------------------------------------------


async def get_course(db: AsyncSession, *, organization_id: uuid.UUID, course_id: uuid.UUID) -> ExtCourse:
    course = await db.get(ExtCourse, course_id)
    if course is None or course.organization_id != organization_id:
        raise ExtNotFound("Corso non trovato.")
    return course


async def groups_of(db: AsyncSession, course_ids: list[uuid.UUID], *, only_active: bool = True) -> dict:
    out: dict[uuid.UUID, list[ExtGroup]] = {c: [] for c in course_ids}
    if not course_ids:
        return out
    stmt = select(ExtGroup).where(ExtGroup.course_id.in_(course_ids))
    if only_active:
        stmt = stmt.where(ExtGroup.active.is_(True))
    for g in (await db.execute(stmt.order_by(ExtGroup.weekday, ExtGroup.starts_at))).scalars():
        out[g.course_id].append(g)
    return out


def group_dict(g: ExtGroup) -> dict:
    return {"id": g.id, "name": g.name, "min_age": g.min_age, "max_age": g.max_age, "weekday": g.weekday,
            "starts_at": g.starts_at.strftime("%H:%M"), "ends_at": g.ends_at.strftime("%H:%M"), "active": g.active}


def course_dict(c: ExtCourse, groups: list[ExtGroup]) -> dict:
    return {
        "id": c.id, "name": c.name, "school_name": c.school_name, "school_address": c.school_address,
        "school_city": c.school_city, "school_logo_url": c.school_logo_url, "description": c.description,
        "monthly_fee_cents": c.monthly_fee_cents, "billing_months": sorted(c.billing_months or [], key=lambda m: (m < 8, m)),
        "due_day": c.due_day, "starts_on": c.starts_on, "ends_on": c.ends_on, "active": c.active,
        "published": c.published, "public_coach_name": c.public_coach_name,
        "groups": [group_dict(g) for g in groups],
    }


async def public_courses(db: AsyncSession) -> list[dict]:
    courses = list((await db.execute(select(ExtCourse).where(
        ExtCourse.active.is_(True), ExtCourse.published.is_(True)).order_by(ExtCourse.school_city, ExtCourse.name))).scalars())
    groups = await groups_of(db, [c.id for c in courses])
    return [course_dict(c, groups[c.id]) for c in courses]


def pick_group(groups: list[ExtGroup], birth: date, on: date) -> ExtGroup | None:
    """Il gruppo per l'età del bambino: il primo che lo comprende."""
    age = _age(birth, on)
    for g in groups:
        if (g.min_age is None or age >= g.min_age) and (g.max_age is None or age <= g.max_age):
            return g
    return None


# --- Iscrizione ----------------------------------------------------------------------------------


async def _grant(db: AsyncSession, user: User, code: str) -> None:
    """Il ruolo che apre l'area (EXT_FAMILY, EXT_SCHOOL). Se la riga del
    ruolo non c'è ancora la crea: i permessi li allinea app.seed.bootstrap,
    e le rotte dei corsi esterni guardano comunque le righe, non il ruolo."""
    from app.domains.rbac.models import Role, UserRole

    role = (await db.execute(select(Role).where(
        (Role.organization_id == user.organization_id) | (Role.organization_id.is_(None)), Role.code == code,
    ))).scalars().first()
    if role is None:
        role = Role(organization_id=user.organization_id, code=code, name=code.replace("_", " ").title())
        db.add(role)
        await db.flush()
    exists = (await db.execute(select(UserRole.id).where(UserRole.user_id == user.id, UserRole.role_id == role.id))).first()
    if exists is None:
        db.add(UserRole(user_id=user.id, organization_id=user.organization_id, role_id=role.id))


async def _coach_of(db: AsyncSession, course_id: uuid.UUID) -> ExtStaff | None:
    return (await db.execute(select(ExtStaff).where(
        ExtStaff.course_id == course_id, ExtStaff.role == "COACH", ExtStaff.active.is_(True),
    ).order_by(ExtStaff.created_at).limit(1))).scalar_one_or_none()


async def issue_fee(db: AsyncSession, *, course: ExtCourse, participant: ExtParticipant, month: date) -> bool:
    """La mensilità di un mese, se il mese è del corso e non c'è già (UNIQUE).
    Congela il treinador e la sua percentuale. Non fa commit."""
    first = month.replace(day=1)
    if first.month not in (course.billing_months or []):
        return False
    if first > course.ends_on or (first.replace(day=28) < course.starts_on.replace(day=1)):
        return False
    coach = await _coach_of(db, course.id)
    due = first.replace(day=min(course.due_day, 28))
    result = await db.execute(insert(ExtFee).values(
        id=uuid.uuid4(), created_at=utcnow(), organization_id=course.organization_id, course_id=course.id,
        participant_id=participant.id, period=_period(first), amount_cents=course.monthly_fee_cents, due_date=due,
        status="DUE", coach_user_id=coach.user_id if coach else None,
        coach_share_pct=(coach.share_pct if coach and coach.share_pct is not None else DEFAULT_SHARE) if coach else None,
    ).on_conflict_do_nothing(constraint="uq_ext_fees_participant_period").returning(ExtFee.id))
    return result.first() is not None


def _clean_child(child: dict, today: date) -> dict:
    first = " ".join((child.get("first_name") or "").split())[:80]
    last = " ".join((child.get("last_name") or "").split())[:80]
    birth = child.get("birth_date")
    if len(first) < 2 or len(last) < 2:
        raise ExtValidation("Escreve o nome e o apelido de cada criança.")
    if not isinstance(birth, date) or birth > today or _age(birth, today) > 18:
        raise ExtValidation("Indica a data de nascimento de cada criança (até 18 anos).")
    return {"first_name": first, "last_name": last, "birth_date": birth, "sex": child.get("sex") if child.get("sex") in ("M", "F") else None,
            "notes": (child.get("notes") or "").strip()[:500] or None}


async def enroll(db: AsyncSession, *, course: ExtCourse, parent: User, children: list[dict], guardian_name: str | None,
                 guardian_phone: str | None, today: date) -> list[ExtParticipant]:
    """I figli iscritti al corso dal genitore: una riga nuova per ogni
    bambino (l'anagrafica è del corso), il gruppo per età, la mensilità del
    mese se il corso è già cominciato."""
    if not course.active:
        raise ExtValidation("Este curso não aceita inscrições.")
    if not children or len(children) > MAX_CHILDREN:
        raise ExtValidation("Indica de 1 a 6 crianças.")
    groups = (await groups_of(db, [course.id]))[course.id]
    existing = {(p.first_name.lower(), p.last_name.lower(), p.birth_date) for p in (await db.execute(select(ExtParticipant).where(
        ExtParticipant.course_id == course.id, ExtParticipant.parent_user_id == parent.id,
        ExtParticipant.status == "ACTIVE"))).scalars()}
    out = []
    for raw in children:
        child = _clean_child(raw, today)
        if (child["first_name"].lower(), child["last_name"].lower(), child["birth_date"]) in existing:
            raise ExtValidation(f"{child['first_name']} já está inscrito(a) neste curso.")
        group = pick_group(groups, child["birth_date"], max(today, course.starts_on))
        p = ExtParticipant(organization_id=course.organization_id, course_id=course.id, group_id=group.id if group else None,
                           parent_user_id=parent.id, guardian_name=(guardian_name or "").strip()[:160] or None,
                           guardian_phone=(guardian_phone or "").strip()[:40] or None, joined_on=today, **child)
        db.add(p)
        await db.flush()
        if course.starts_on <= today <= course.ends_on:
            await issue_fee(db, course=course, participant=p, month=today)
        out.append(p)
    await _grant(db, parent, "EXT_FAMILY")
    await audit_service.record(
        db, organization_id=course.organization_id, actor_user_id=parent.id, action="ext.enrolled",
        entity_type="ext_course", entity_id=str(course.id), new_value={"children": len(out)},
    )
    await db.commit()
    return out


async def public_signup(db: AsyncSession, *, course: ExtCourse, email: str, password: str, guardian_name: str,
                        guardian_phone: str | None, children: list[dict], today: date) -> User:
    """L'iscrizione dal sito di chi non ha un account: nasce l'account del
    genitore (con la sua password) e i figli si iscrivono. Un'email che ha già
    un account entra prima e si iscrive da dentro (ExtAccountExists)."""
    from app.domains.customers.models import Customer, CustomerProfile

    email = (email or "").strip().lower()
    if "@" not in email or len(email) > 255:
        raise ExtValidation("Escreve um email válido.")
    if len(password or "") < 8:
        raise ExtValidation("A palavra-passe precisa de pelo menos 8 caracteres.")
    name = " ".join((guardian_name or "").split())
    if len(name.split()) < 2:
        raise ExtValidation("Escreve o teu nome e apelido.")
    taken = (await db.execute(select(User.id).where(
        User.organization_id == course.organization_id, func.lower(User.email) == email))).first()
    if taken is not None:
        raise ExtAccountExists("Já tens uma conta com este email: entra e completa a inscrição.")
    for child in children:
        _clean_child(child, today)
    user = User(organization_id=course.organization_id, email=email, password_hash=hash_password(password),
                status="ACTIVE", privacy_accepted_at=utcnow())
    db.add(user)
    await db.flush()
    customer = Customer(organization_id=course.organization_id, user_id=user.id, kind="PRIVATE", email=email)
    db.add(customer)
    await db.flush()
    first, _, last = name.partition(" ")
    db.add(CustomerProfile(customer_id=customer.id, first_name=first[:128], last_name=last[:128] or "-"))
    await db.flush()
    await enroll(db, course=course, parent=user, children=children, guardian_name=name, guardian_phone=guardian_phone,
                 today=today)
    return user


# --- Il genitore --------------------------------------------------------------------------------


def fee_dict(f: ExtFee, *, today: date, name: str | None = None) -> dict:
    return {"id": f.id, "participant_id": f.participant_id, "participant_name": name, "period": f.period,
            "amount_cents": f.amount_cents, "due_date": f.due_date, "status": f.status,
            "overdue": f.status == "DUE" and f.due_date < today, "paid_at": f.paid_at, "method": f.method}


async def family(db: AsyncSession, *, user_id: uuid.UUID, today: date) -> dict:
    """Tutto ciò che il genitore vede: i figli con corso, gruppo e orario,
    le presenze del mese, le mensilità, le prove, gli avvisi."""
    parts = list((await db.execute(select(ExtParticipant).where(
        ExtParticipant.parent_user_id == user_id, ExtParticipant.status == "ACTIVE").order_by(ExtParticipant.first_name))).scalars())
    course_ids = sorted({p.course_id for p in parts}, key=str)
    courses = {c.id: c for c in (await db.execute(select(ExtCourse).where(ExtCourse.id.in_(course_ids)))).scalars()} if course_ids else {}
    groups = await groups_of(db, course_ids, only_active=False)
    by_group = {g.id: g for gs in groups.values() for g in gs}
    first = today.replace(day=1)
    att: dict[uuid.UUID, list] = {}
    if parts:
        for a in (await db.execute(select(ExtAttendance).where(
            ExtAttendance.participant_id.in_([p.id for p in parts]), ExtAttendance.date >= first))).scalars():
            att.setdefault(a.participant_id, []).append(a)
    fees = list((await db.execute(select(ExtFee).where(ExtFee.participant_id.in_([p.id for p in parts]))
                                  .order_by(ExtFee.period.desc()))).scalars()) if parts else []
    names = {p.id: p.first_name for p in parts}
    notices = list((await db.execute(select(ExtNotice).where(ExtNotice.course_id.in_(course_ids))
                                     .order_by(ExtNotice.created_at.desc()).limit(10))).scalars()) if course_ids else []
    proofs = list((await db.execute(select(ExtProof).where(ExtProof.parent_user_id == user_id)
                                    .order_by(ExtProof.created_at.desc()).limit(10))).scalars())

    def lessons_this_month(p: ExtParticipant) -> int:
        g = by_group.get(p.group_id)
        if g is None:
            return 0
        d, n = first, 0
        while d <= today:
            if d.weekday() == g.weekday and courses[p.course_id].starts_on <= d <= courses[p.course_id].ends_on:
                n += 1
            d += timedelta(days=1)
        return n

    due = [f for f in fees if f.status == "DUE"]
    return {
        "children": [{
            "id": p.id, "first_name": p.first_name, "last_name": p.last_name, "birth_date": p.birth_date,
            "age": _age(p.birth_date, today), "course_id": p.course_id,
            "group": group_dict(by_group[p.group_id]) if p.group_id in by_group else None,
            "present_this_month": sum(1 for a in att.get(p.id, []) if a.present),
            "lessons_this_month": lessons_this_month(p),
        } for p in parts],
        "courses": [course_dict(c, groups[c.id]) for c in courses.values()],
        "due_fees": [fee_dict(f, today=today, name=names.get(f.participant_id)) for f in due],
        "due_cents": sum(f.amount_cents for f in due),
        "overdue_cents": sum(f.amount_cents for f in due if f.due_date < today),
        "paid_fees": [fee_dict(f, today=today, name=names.get(f.participant_id)) for f in fees if f.status == "PAID"][:24],
        "proofs": [{"id": x.id, "amount_cents": x.amount_cents, "method": x.method, "status": x.status,
                    "created_at": x.created_at, "rejection_reason": x.rejection_reason} for x in proofs],
        "notices": [{"id": n.id, "title": n.title, "body": n.body, "created_at": n.created_at,
                     "course_id": n.course_id} for n in notices],
        "payment_info": await _payment_info(db, organization_id=courses[course_ids[0]].organization_id) if course_ids else None,
    }


async def _payment_info(db: AsyncSession, *, organization_id: uuid.UUID) -> dict:
    """Dove si paga: l'IBAN di JudoArteVida (le impostazioni di pagamento
    della piattaforma), non quello di un club."""
    from app.domains.organizations import service as org_service

    return await org_service.get_payment_info(db, organization_id=organization_id)


async def upload_proof(db: AsyncSession, *, user_id: uuid.UUID, fee_ids: list[uuid.UUID], method: str,
                       file: tuple[bytes, str, str] | None, note: str | None) -> ExtProof:
    """La prova di pagamento del genitore: segna pagate subito le mensilità
    scelte (solo sue, solo da pagare). Il file va nel bucket privato."""
    from app.core.storage import UploadValidationError, upload_document

    if method not in PAYMENT_METHODS or method == "POS":
        raise ExtValidation("Escolhe como pagaste.")
    fees = list((await db.execute(select(ExtFee).join(ExtParticipant, ExtParticipant.id == ExtFee.participant_id).where(
        ExtFee.id.in_(fee_ids), ExtParticipant.parent_user_id == user_id, ExtFee.status == "DUE"))).scalars()) if fee_ids else []
    if not fees or len(fees) != len(set(fee_ids)):
        raise ExtValidation("Escolhe as mensalidades que pagaste.")
    if len({f.course_id for f in fees}) != 1:
        raise ExtValidation("Uma prova por curso: escolhe as mensalidades de um curso de cada vez.")
    if method == "BANK_TRANSFER" and file is None:
        raise ExtValidation("Junta o comprovativo da transferência.")
    key = name = None
    if file is not None:
        content, content_type, name = file
        try:
            key = upload_document(file_bytes=content, content_type=content_type, key_prefix=f"ext-proofs/{user_id}")
        except UploadValidationError as exc:
            raise ExtValidation("O comprovativo deve ser um PDF, JPG ou PNG até 15 MB.") from exc
    proof = ExtProof(organization_id=fees[0].organization_id, course_id=fees[0].course_id, parent_user_id=user_id,
                     storage_key=key, filename=(name or "")[:255] or None, amount_cents=sum(f.amount_cents for f in fees),
                     method=method, note=(note or "").strip()[:500] or None, status="ACCEPTED")
    db.add(proof)
    await db.flush()
    now = utcnow()
    for f in fees:
        f.status, f.paid_at, f.method, f.proof_id, f.recorded_by_user_id = "PAID", now, method, proof.id, user_id
    await audit_service.record(
        db, organization_id=proof.organization_id, actor_user_id=user_id, action="ext.proof_uploaded",
        entity_type="ext_proof", entity_id=str(proof.id), new_value={"fees": len(fees), "amount_cents": proof.amount_cents},
    )
    await db.commit()
    await db.refresh(proof)
    return proof


# --- Lo staff (scuola e treinador) ---------------------------------------------------------------


async def staff_roles(db: AsyncSession, *, user_id: uuid.UUID) -> dict[uuid.UUID, set[str]]:
    out: dict[uuid.UUID, set[str]] = {}
    for course_id, role in (await db.execute(select(ExtStaff.course_id, ExtStaff.role).where(
        ExtStaff.user_id == user_id, ExtStaff.active.is_(True)))).all():
        out.setdefault(course_id, set()).add(role)
    return out


async def staff_course(db: AsyncSession, *, user_id: uuid.UUID, course_id: uuid.UUID, admin: bool,
                       role: str | None = None) -> tuple[ExtCourse, set[str]]:
    """Il corso, se chi chiede ci lavora (o è il superadmin); con `role`,
    solo con quel ruolo."""
    course = await db.get(ExtCourse, course_id)
    if course is None:
        raise ExtNotFound("Corso non trovato.")
    if admin:
        return course, {"COACH", "SCHOOL", "ADMIN"}
    roles = (await staff_roles(db, user_id=user_id)).get(course_id, set())
    if not roles or (role and role not in roles):
        raise ExtNotFound("Corso non trovato.")
    return course, roles


async def my_staff_courses(db: AsyncSession, *, user_id: uuid.UUID) -> list[dict]:
    roles = await staff_roles(db, user_id=user_id)
    if not roles:
        return []
    courses = list((await db.execute(select(ExtCourse).where(ExtCourse.id.in_(list(roles)))
                                     .order_by(ExtCourse.name))).scalars())
    groups = await groups_of(db, [c.id for c in courses])
    counts = dict((await db.execute(select(ExtParticipant.course_id, func.count()).where(
        ExtParticipant.course_id.in_(list(roles)), ExtParticipant.status == "ACTIVE").group_by(ExtParticipant.course_id))).all())
    return [{**course_dict(c, groups[c.id]), "roles": sorted(roles[c.id]), "participants": int(counts.get(c.id) or 0)}
            for c in courses]


async def roster(db: AsyncSession, *, course: ExtCourse, roles: set[str], today: date) -> dict:
    """La scheda del corso per lo staff. La scuola vede anche contatti e
    pagamenti; il treinador i bambini e le presenze."""
    parts = list((await db.execute(select(ExtParticipant).where(ExtParticipant.course_id == course.id)
                                   .order_by(ExtParticipant.status, ExtParticipant.first_name))).scalars())
    groups = (await groups_of(db, [course.id], only_active=False))[course.id]
    sees_money = bool(roles & {"SCHOOL", "ADMIN"})
    fees_by: dict[uuid.UUID, list[ExtFee]] = {}
    if sees_money and parts:
        for f in (await db.execute(select(ExtFee).where(ExtFee.course_id == course.id))).scalars():
            fees_by.setdefault(f.participant_id, []).append(f)
    first = today.replace(day=1)
    present = dict((await db.execute(select(ExtAttendance.participant_id, func.count()).where(
        ExtAttendance.course_id == course.id, ExtAttendance.present.is_(True), ExtAttendance.date >= first,
    ).group_by(ExtAttendance.participant_id))).all())
    from app.domains.club.people import _names

    parent_names = await _names(db, {p.parent_user_id for p in parts})
    emails = dict((await db.execute(select(User.id, User.email).where(User.id.in_({p.parent_user_id for p in parts}))))
                  .all()) if parts and sees_money else {}
    rows = []
    for p in parts:
        row = {"id": p.id, "first_name": p.first_name, "last_name": p.last_name, "age": _age(p.birth_date, today),
               "group_id": p.group_id, "status": p.status, "notes": p.notes, "joined_on": p.joined_on,
               "present_this_month": int(present.get(p.id) or 0)}
        if sees_money:
            mine = fees_by.get(p.id, [])
            row.update({
                "guardian_name": p.guardian_name or parent_names.get(p.parent_user_id),
                "guardian_phone": p.guardian_phone, "guardian_email": emails.get(p.parent_user_id),
                "due_cents": sum(f.amount_cents for f in mine if f.status == "DUE"),
                "overdue": any(f.status == "DUE" and f.due_date < today for f in mine),
                "fees": [fee_dict(f, today=today) for f in sorted(mine, key=lambda f: f.period, reverse=True)],
            })
        rows.append(row)
    out = {"course": course_dict(course, groups), "roles": sorted(roles), "participants": rows}
    if sees_money:
        proofs = list((await db.execute(select(ExtProof).where(ExtProof.course_id == course.id)
                                        .order_by(ExtProof.created_at.desc()).limit(50))).scalars())
        out["proofs"] = [{"id": x.id, "amount_cents": x.amount_cents, "method": x.method, "status": x.status,
                          "has_file": x.storage_key is not None, "created_at": x.created_at, "note": x.note,
                          "parent_name": parent_names.get(x.parent_user_id)} for x in proofs]
    out["notices"] = [{"id": n.id, "title": n.title, "body": n.body, "created_at": n.created_at}
                      for n in (await db.execute(select(ExtNotice).where(ExtNotice.course_id == course.id)
                                                 .order_by(ExtNotice.created_at.desc()).limit(20))).scalars()]
    return out


async def attendance_day(db: AsyncSession, *, course: ExtCourse, on: date) -> dict:
    groups = [g for g in (await groups_of(db, [course.id]))[course.id] if g.weekday == on.weekday()]
    parts = list((await db.execute(select(ExtParticipant).where(
        ExtParticipant.course_id == course.id, ExtParticipant.status == "ACTIVE").order_by(ExtParticipant.first_name))).scalars())
    marks = {a.participant_id: a.present for a in (await db.execute(select(ExtAttendance).where(
        ExtAttendance.course_id == course.id, ExtAttendance.date == on))).scalars()}
    return {"date": on, "groups": [{**group_dict(g), "participants": [
        {"id": p.id, "first_name": p.first_name, "last_name": p.last_name, "present": marks.get(p.id)}
        for p in parts if p.group_id == g.id]} for g in groups],
        "no_group": [{"id": p.id, "first_name": p.first_name, "last_name": p.last_name, "present": marks.get(p.id)}
                     for p in parts if p.group_id is None]}


async def mark_attendance(db: AsyncSession, *, course: ExtCourse, on: date, marks: dict[uuid.UUID, bool],
                          actor_user_id: uuid.UUID, today: date) -> int:
    if on > today:
        raise ExtValidation("Não se marcam presenças no futuro.")
    ids = set((await db.execute(select(ExtParticipant.id).where(
        ExtParticipant.course_id == course.id, ExtParticipant.id.in_(list(marks))))).scalars())
    for pid, present in marks.items():
        if pid not in ids:
            continue
        await db.execute(insert(ExtAttendance).values(
            id=uuid.uuid4(), created_at=utcnow(), course_id=course.id, participant_id=pid, date=on, present=present,
            recorded_by_user_id=actor_user_id,
        ).on_conflict_do_update(constraint="uq_ext_attendances_participant_date",
                                set_={"present": present, "recorded_by_user_id": actor_user_id}))
    await db.commit()
    return len(ids)


async def clock(db: AsyncSession, *, course: ExtCourse, user_id: uuid.UUID, action: str) -> dict:
    """Entrata («in») e uscita («out») del treinador nel corso."""
    open_session = (await db.execute(select(ExtWorkSession).where(
        ExtWorkSession.user_id == user_id, ExtWorkSession.ended_at.is_(None)))).scalars().first()
    now = utcnow()
    if action == "in":
        if open_session is not None:
            raise ExtValidation("Já tens uma entrada aberta: marca primeiro a saída.")
        db.add(ExtWorkSession(course_id=course.id, user_id=user_id, started_at=now))
    elif action == "out":
        if open_session is None:
            raise ExtValidation("Não há nenhuma entrada aberta.")
        open_session.ended_at = now
    else:
        raise ExtValidation("in ou out.")
    await db.commit()
    return await clock_state(db, user_id=user_id)


async def clock_state(db: AsyncSession, *, user_id: uuid.UUID) -> dict:
    rows = list((await db.execute(select(ExtWorkSession).where(ExtWorkSession.user_id == user_id)
                                  .order_by(ExtWorkSession.started_at.desc()).limit(20))).scalars())
    open_row = next((r for r in rows if r.ended_at is None), None)
    return {"open": {"course_id": open_row.course_id, "started_at": open_row.started_at} if open_row else None,
            "sessions": [{"course_id": r.course_id, "started_at": r.started_at, "ended_at": r.ended_at,
                          "minutes": int((r.ended_at - r.started_at).total_seconds() // 60) if r.ended_at else None}
                         for r in rows]}


async def post_notice(db: AsyncSession, *, course: ExtCourse, author_user_id: uuid.UUID, title: str,
                      body: str | None) -> ExtNotice:
    from app.domains.notifications import service as notifications_service

    title = " ".join((title or "").split())[:200]
    if len(title) < 3:
        raise ExtValidation("Escreve o título do aviso.")
    notice = ExtNotice(course_id=course.id, author_user_id=author_user_id, title=title,
                       body=(body or "").strip()[:4000] or None)
    db.add(notice)
    await db.flush()
    parents = set((await db.execute(select(ExtParticipant.parent_user_id).where(
        ExtParticipant.course_id == course.id, ExtParticipant.status == "ACTIVE"))).scalars())
    for uid in parents:
        await notifications_service.notify_user(
            db, organization_id=course.organization_id, user_id=uid, type_="EXT_NOTICE", entity_type="ext_course",
            entity_id=course.id, title=f"{course.school_name}: {title}"[:200], body=(body or "")[:300] or None,
        )
    await db.commit()
    await db.refresh(notice)
    return notice


async def set_fee_paid(db: AsyncSession, *, course: ExtCourse, fee_id: uuid.UUID, actor_user_id: uuid.UUID,
                       method: str) -> ExtFee:
    """La scuola (o il superadmin) segna pagata una mensilità: contanti, MB WAY, POS."""
    if method not in PAYMENT_METHODS:
        raise ExtValidation("Escolhe o método.")
    fee = await db.get(ExtFee, fee_id)
    if fee is None or fee.course_id != course.id:
        raise ExtNotFound("Mensalidade não encontrada.")
    if fee.status != "DUE":
        raise ExtValidation("Esta mensalidade já não está por pagar.")
    fee.status, fee.paid_at, fee.method, fee.recorded_by_user_id = "PAID", utcnow(), method, actor_user_id
    await audit_service.record(db, organization_id=course.organization_id, actor_user_id=actor_user_id,
                               action="ext.fee_paid", entity_type="ext_fee", entity_id=str(fee.id),
                               new_value={"method": method})
    await db.commit()
    await db.refresh(fee)
    return fee


async def reject_proof(db: AsyncSession, *, course: ExtCourse, proof_id: uuid.UUID, actor_user_id: uuid.UUID,
                       reason: str) -> ExtProof:
    """Una prova che non va: le sue mensilità tornano da pagare e il
    genitore lo sa."""
    from app.domains.notifications import service as notifications_service

    proof = await db.get(ExtProof, proof_id)
    if proof is None or proof.course_id != course.id:
        raise ExtNotFound("Prova não encontrada.")
    if proof.status == "REJECTED":
        return proof
    reason = (reason or "").strip()[:500]
    if len(reason) < 3:
        raise ExtValidation("Diz porquê.")
    proof.status, proof.reviewed_by_user_id, proof.reviewed_at, proof.rejection_reason = "REJECTED", actor_user_id, utcnow(), reason
    for f in (await db.execute(select(ExtFee).where(ExtFee.proof_id == proof.id))).scalars():
        f.status, f.paid_at, f.method, f.proof_id = "DUE", None, None, None
    await notifications_service.notify_user(
        db, organization_id=course.organization_id, user_id=proof.parent_user_id, type_="EXT_PROOF_REJECTED",
        entity_type="ext_proof", entity_id=proof.id, title=f"{course.school_name}: comprovativo recusado",
        body=reason[:300],
    )
    await db.commit()
    await db.refresh(proof)
    return proof


async def proof_for(db: AsyncSession, *, proof_id: uuid.UUID) -> ExtProof:
    proof = await db.get(ExtProof, proof_id)
    if proof is None:
        raise ExtNotFound("Prova não encontrada.")
    return proof


# --- I conti ---------------------------------------------------------------------------------------


def _share(amount: int, pct: Decimal | None) -> int:
    if not pct:
        return 0
    return int((Decimal(amount) * Decimal(pct) / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


async def accounts(db: AsyncSession, *, organization_id: uuid.UUID, year: int,
                   course_ids: list[uuid.UUID] | None = None, coach_user_id: uuid.UUID | None = None) -> dict:
    """Mese per mese e corso per corso: incassato (le mensilità pagate in
    quel mese, principio di cassa), parte del treinador (la sua percentuale
    congelata), parte di JudoArteVida; e quanto resta da incassare."""
    start, end = datetime(year, 1, 1), datetime(year + 1, 1, 1)
    stmt = select(ExtFee).where(ExtFee.organization_id == organization_id)
    if course_ids is not None:
        stmt = stmt.where(ExtFee.course_id.in_(course_ids))
    if coach_user_id is not None:
        stmt = stmt.where(ExtFee.coach_user_id == coach_user_id)
    fees = list((await db.execute(stmt)).scalars())
    courses = {c.id: c for c in (await db.execute(select(ExtCourse).where(ExtCourse.organization_id == organization_id))).scalars()}
    months: dict[str, dict] = {}
    by_course: dict[uuid.UUID, dict] = {}
    for f in fees:
        c = by_course.setdefault(f.course_id, {"course_id": f.course_id, "name": courses[f.course_id].name if f.course_id in courses else "",
                                               "school_name": courses[f.course_id].school_name if f.course_id in courses else "",
                                               "income_cents": 0, "coach_cents": 0, "jav_cents": 0, "due_cents": 0})
        if f.status == "DUE":
            c["due_cents"] += f.amount_cents
        if f.status != "PAID" or f.paid_at is None:
            continue
        paid = f.paid_at.replace(tzinfo=None)
        if not start <= paid < end:
            continue
        coach = _share(f.amount_cents, f.coach_share_pct)
        key = f"{paid.year:04d}-{paid.month:02d}"
        m = months.setdefault(key, {"period": key, "income_cents": 0, "coach_cents": 0, "jav_cents": 0})
        for target in (m, c):
            target["income_cents"] += f.amount_cents
            target["coach_cents"] += coach
            target["jav_cents"] += f.amount_cents - coach
    total = {k: sum(m[k] for m in months.values()) for k in ("income_cents", "coach_cents", "jav_cents")}
    return {"year": year, "months": [months[k] for k in sorted(months)], "courses": list(by_course.values()),
            "total": total, "due_cents": sum(c["due_cents"] for c in by_course.values())}


# --- Il lavoro mensile ------------------------------------------------------------------------------


async def issue_month(db: AsyncSession, *, today: date | None = None) -> int:
    """Le mensilità del mese per tutti i partecipanti attivi dei corsi attivi
    (idempotente: UNIQUE per partecipante e mese)."""
    today = today or utcnow().date()
    made = 0
    for course in (await db.execute(select(ExtCourse).where(ExtCourse.active.is_(True)))).scalars().all():
        if not course.starts_on <= today <= course.ends_on:
            continue
        for p in (await db.execute(select(ExtParticipant).where(
            ExtParticipant.course_id == course.id, ExtParticipant.status == "ACTIVE"))).scalars().all():
            made += int(await issue_fee(db, course=course, participant=p, month=today))
    await db.commit()
    return made


# --- Il superadmin -------------------------------------------------------------------------------


COURSE_FIELDS = ("name", "school_name", "school_address", "school_city", "description", "monthly_fee_cents",
                 "billing_months", "due_day", "starts_on", "ends_on", "active", "published", "public_coach_name")


async def save_course(db: AsyncSession, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict,
                      course: ExtCourse | None = None) -> ExtCourse:
    values = {k: v for k, v in data.items() if k in COURSE_FIELDS}
    if course is None:
        if not values.get("name") or not values.get("school_name") or not values.get("starts_on") or not values.get("ends_on"):
            raise ExtValidation("Nome, escola, início e fim do curso são obrigatórios.")
        course = ExtCourse(organization_id=organization_id, created_by_user_id=actor_user_id, **values)
        db.add(course)
    else:
        for k, v in values.items():
            setattr(course, k, v)
    if course.ends_on <= course.starts_on:
        raise ExtValidation("O fim do curso deve ser depois do início.")
    if any(m not in range(1, 13) for m in course.billing_months or []):
        raise ExtValidation("Meses inválidos.")
    await db.flush()
    await audit_service.record(db, organization_id=organization_id, actor_user_id=actor_user_id, action="ext.course_saved",
                               entity_type="ext_course", entity_id=str(course.id), new_value={"fields": sorted(values)})
    await db.commit()
    await db.refresh(course)
    return course


async def save_group(db: AsyncSession, *, course: ExtCourse, data: dict, group: ExtGroup | None = None) -> ExtGroup:
    values = {k: data[k] for k in ("name", "min_age", "max_age", "weekday", "starts_at", "ends_at", "active") if k in data}
    if group is None:
        group = ExtGroup(course_id=course.id, **values)
        db.add(group)
    else:
        for k, v in values.items():
            setattr(group, k, v)
    if group.ends_at <= group.starts_at:
        raise ExtValidation("O fim da aula deve ser depois do início.")
    await db.commit()
    await db.refresh(group)
    return group


async def add_staff(db: AsyncSession, *, course: ExtCourse, actor_user_id: uuid.UUID, email: str, role: str,
                    share_pct: Decimal | None) -> tuple[ExtStaff, str | None]:
    """Un treinador o la segreteria della scuola sul corso. Un'email senza
    account riceve l'invito a scegliersi la password (la scuola); il
    treinador deve già avere il suo account. Restituisce il link d'invito se
    l'email non è partita."""
    from app.domains.auth import service as auth_service

    if role not in ("COACH", "SCHOOL"):
        raise ExtValidation("Papel inválido.")
    email = (email or "").strip().lower()
    user = (await db.execute(select(User).where(User.organization_id == course.organization_id,
                                                func.lower(User.email) == email))).scalar_one_or_none()
    link = None
    if user is None:
        if role == "COACH":
            raise ExtValidation("Este treinador ainda não tem conta: cria-a primeiro como treinador de um clube.")
        user = User(organization_id=course.organization_id, email=email,
                    password_hash=hash_password(secrets.token_urlsafe(32)), status="ACTIVE")
        db.add(user)
        await db.flush()
        await _grant(db, user, "EXT_SCHOOL")
        await db.commit()
        link, sent = await auth_service.send_account_invite_email(
            db, user=user, invited_by_display_name="JudoArteVida",
            intro=f"A tua área da escola para o curso de judo «{course.name}» está pronta: vês inscritos, pagamentos e presenças.",
        )
        link = None if sent else link
    elif role == "SCHOOL":
        await _grant(db, user, "EXT_SCHOOL")
    row = (await db.execute(select(ExtStaff).where(ExtStaff.course_id == course.id, ExtStaff.user_id == user.id,
                                                   ExtStaff.role == role))).scalar_one_or_none()
    if row is None:
        row = ExtStaff(course_id=course.id, user_id=user.id, role=role)
        db.add(row)
    row.active = True
    row.share_pct = (share_pct if share_pct is not None else DEFAULT_SHARE) if role == "COACH" else None
    await audit_service.record(db, organization_id=course.organization_id, actor_user_id=actor_user_id,
                               action="ext.staff_added", entity_type="ext_course", entity_id=str(course.id),
                               new_value={"user_id": str(user.id), "role": role})
    await db.commit()
    await db.refresh(row)
    return row, link


async def remove_staff(db: AsyncSession, *, course: ExtCourse, staff_id: uuid.UUID) -> None:
    row = await db.get(ExtStaff, staff_id)
    if row is None or row.course_id != course.id:
        raise ExtNotFound("Pessoa não encontrada.")
    row.active = False
    await db.commit()


async def staff_list(db: AsyncSession, *, course: ExtCourse) -> list[dict]:
    from app.domains.club.people import _names

    rows = list((await db.execute(select(ExtStaff).where(ExtStaff.course_id == course.id, ExtStaff.active.is_(True)))).scalars())
    names = await _names(db, {r.user_id for r in rows})
    emails = dict((await db.execute(select(User.id, User.email).where(User.id.in_({r.user_id for r in rows}))))
                  .all()) if rows else {}
    return [{"id": r.id, "user_id": r.user_id, "role": r.role, "share_pct": r.share_pct, "name": names.get(r.user_id),
             "email": emails.get(r.user_id)} for r in rows]


async def admin_courses(db: AsyncSession, *, organization_id: uuid.UUID) -> list[dict]:
    courses = list((await db.execute(select(ExtCourse).where(ExtCourse.organization_id == organization_id)
                                     .order_by(ExtCourse.active.desc(), ExtCourse.name))).scalars())
    groups = await groups_of(db, [c.id for c in courses], only_active=False)
    counts = dict((await db.execute(select(ExtParticipant.course_id, func.count()).where(
        ExtParticipant.status == "ACTIVE").group_by(ExtParticipant.course_id))).all())
    due = dict((await db.execute(select(ExtFee.course_id, func.sum(ExtFee.amount_cents)).where(
        ExtFee.status == "DUE").group_by(ExtFee.course_id))).all())
    out = []
    for c in courses:
        out.append({**course_dict(c, groups[c.id]), "participants": int(counts.get(c.id) or 0),
                    "due_cents": int(due.get(c.id) or 0), "staff": await staff_list(db, course=c)})
    return out
