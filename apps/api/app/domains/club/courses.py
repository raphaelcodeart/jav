"""Corsi, orari settimanali, iscritti ai corsi e presenze.

La presenza la segna l'istruttore dal telefono, un tocco per atleta: per
questo `mark_attendance` è un upsert sulla chiave (atleta, corso, giorno) e
toccare di nuovo lo stesso nome corregge, non duplica.
"""

import uuid
from datetime import date, time

from sqlalchemy import case, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.club import kinds
from app.domains.club.models import (
    ClubAthlete,
    ClubAttendance,
    ClubCourse,
    ClubCourseAthlete,
    ClubCourseCoachExclusion,
    ClubCourseSlot,
    ClubCourseStaff,
    ClubFee,
)
from app.domains.club.scope import ClubScope, scope_of
from app.domains.club.service import ClubNotFoundError, ClubValidationError
from app.domains.users.models import User

WEEKDAY_LABELS = ("Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica")


async def get_course(db: AsyncSession, *, scope: ClubScope, course_id: uuid.UUID) -> ClubCourse:
    course = await db.get(ClubCourse, course_id)
    if course is None or course.club_id != scope.club_id:
        raise ClubNotFoundError("Corso non trovato.")
    return course


#: I campi che hanno senso solo nei corsi JAV (luogo, pagina pubblica,
#: percentuale del treinador): in un club ufficiale restano vuoti.
COURSES_UNIT_FIELDS = (
    "venue_name", "venue_address", "venue_city", "public_description", "public_coach_name", "coach_share_pct",
    "published", "venue_logo_url",
)


def _validate_course(course: ClubCourse) -> None:
    if course.min_age is not None and course.max_age is not None and course.max_age < course.min_age:
        raise ClubValidationError("L'età massima non può essere inferiore all'età minima.")


async def _apply_kind(db: AsyncSession, *, scope: ClubScope, course: ClubCourse) -> None:
    """Nei corsi JAV il treinador prende la sua percentuale (default 50%);
    in un club ufficiale lo staff è pagato a ore e un corso non ha né
    percentuale né pagina pubblica sua."""
    rules = await kinds.club_rules(db, club_id=scope.club_id)
    if rules.coach_paid_by_share:
        if course.coach_share_pct is None:
            course.coach_share_pct = kinds.DEFAULT_COACH_SHARE_PCT
        return
    for field in COURSES_UNIT_FIELDS:
        if field == "published":
            course.published = False
        else:
            setattr(course, field, None)


async def _validate_instructor(db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID | None) -> None:
    if user_id is None:
        return
    user = await db.get(User, user_id)
    # L'istruttore è del club (o dello staff della piattaforma, che insegna
    # dove serve), o un treinador di un altro club che allena anche qui
    # (club/staff_clubs.py): mai uno che qui non c'entra.
    if user is None or user.organization_id != scope.organization_id:
        raise ClubValidationError("Istruttore non trovato.")
    if user.club_id not in (None, scope.club_id):
        from app.domains.club.staff_clubs import active_coach_ids

        if user.id not in await active_coach_ids(db, club_id=scope.club_id):
            raise ClubValidationError("Istruttore non trovato.")


async def create_course(db: AsyncSession, *, scope: ClubScope, actor_user_id: uuid.UUID, data: dict) -> ClubCourse:
    await _validate_instructor(db, scope=scope, user_id=data.get("instructor_user_id"))
    course = ClubCourse(**scope.columns(), **data)
    _validate_course(course)
    await _apply_kind(db, scope=scope, course=course)
    db.add(course)
    await db.flush()
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.course_created", entity_type="club_course", entity_id=str(course.id),
        new_value={"name": course.name},
    )
    await db.commit()
    await db.refresh(course)
    return course


async def update_course(
    db: AsyncSession, *, scope: ClubScope, course_id: uuid.UUID, actor_user_id: uuid.UUID, changes: dict
) -> ClubCourse:
    course = await get_course(db, scope=scope, course_id=course_id)
    if "instructor_user_id" in changes:
        await _validate_instructor(db, scope=scope, user_id=changes["instructor_user_id"])
    for key, value in changes.items():
        setattr(course, key, value)
    _validate_course(course)
    await _apply_kind(db, scope=scope, course=course)
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.course_updated", entity_type="club_course", entity_id=str(course.id),
        new_value={k: str(v) for k, v in changes.items()},
    )
    await db.commit()
    await db.refresh(course)
    return course


async def list_courses(
    db: AsyncSession, *, scope: ClubScope, only_active: bool = True, instructor_user_id: uuid.UUID | None = None,
    visible_to_user_id: uuid.UUID | None = None,
) -> list[ClubCourse]:
    """I corsi del club. Con `instructor_user_id` solo quelli che quella
    persona insegna (titolare o adjunto); con `visible_to_user_id` quelli che
    un treinador vede (`visible_course_filter`), i suoi per primi."""
    stmt = select(ClubCourse).where(ClubCourse.club_id == scope.club_id)
    if only_active:
        stmt = stmt.where(ClubCourse.active.is_(True))
    if instructor_user_id is not None:
        stmt = stmt.where(_taught_by(instructor_user_id))
    if visible_to_user_id is not None:
        stmt = stmt.where(visible_course_filter(visible_to_user_id))
        # CASE e non `mine DESC`: senza titolare il confronto è NULL, e NULL
        # in un DESC va in testa.
        mine = case((_taught_by(visible_to_user_id), 0), else_=1)
        return list((await db.execute(stmt.order_by(mine, ClubCourse.name))).scalars())
    return list((await db.execute(stmt.order_by(ClubCourse.name))).scalars())


def _taught_by(user_id: uuid.UUID):
    # I suoi corsi: quelli di cui è titolare e quelli in cui è adjunto.
    return (ClubCourse.instructor_user_id == user_id) | ClubCourse.id.in_(
        select(ClubCourseStaff.course_id).where(ClubCourseStaff.user_id == user_id)
    )


def visible_course_filter(user_id: uuid.UUID):
    """Che cosa vede un treinador: **tutti** i corsi del club, tranne quelli da
    cui la segreteria l'ha escluso (`ClubCourseCoachExclusion`). Nei club
    piccoli i treinador insegnano in tutti i gruppi: un treinador senza corsi
    assegnati che non vede nessuno è un errore, non una scelta. Chi insegna il
    corso lo vede comunque, anche se escluso per sbaglio. Unico punto in cui
    si decide: l'area del treinador (presenze, lezioni, Início, quaderno, i
    miei atleti) passa tutta di qui. I soldi no: la quota del treinador sui
    corsi JAV resta del titolare (`instructor_user_id`)."""
    excluded = select(ClubCourseCoachExclusion.course_id).where(ClubCourseCoachExclusion.user_id == user_id)
    return _taught_by(user_id) | ClubCourse.id.not_in(excluded)


async def taught_course_ids(db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID) -> set[uuid.UUID]:
    """I corsi che `user_id` insegna (titolare o adjunto): «i miei»."""
    return set((await db.execute(
        select(ClubCourse.id).where(ClubCourse.club_id == scope.club_id, _taught_by(user_id))
    )).scalars())


async def can_see(db: AsyncSession, *, course: ClubCourse, user_id: uuid.UUID) -> bool:
    """Il controllo di `visible_course_filter` per un corso solo."""
    return (await db.execute(
        select(ClubCourse.id).where(ClubCourse.id == course.id, visible_course_filter(user_id))
    )).first() is not None


async def coach_exclusions_by_course(db: AsyncSession, *, course_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[uuid.UUID]]:
    out: dict[uuid.UUID, list[uuid.UUID]] = {c: [] for c in course_ids}
    if course_ids:
        for course_id, user_id in (await db.execute(
            select(ClubCourseCoachExclusion.course_id, ClubCourseCoachExclusion.user_id)
            .where(ClubCourseCoachExclusion.course_id.in_(course_ids))
        )).all():
            out[course_id].append(user_id)
    return out


async def set_coach_exclusions(
    db: AsyncSession, *, scope: ClubScope, course_id: uuid.UUID, user_ids: list[uuid.UUID], actor_user_id: uuid.UUID,
) -> list[uuid.UUID]:
    """I treinador che NON vedono il corso: l'elenco intero, che sostituisce
    il precedente (vuoto = lo vedono tutti)."""
    course = await get_course(db, scope=scope, course_id=course_id)
    for user_id in user_ids:
        await _validate_instructor(db, scope=scope, user_id=user_id)
    rows = {
        r.user_id: r for r in (await db.execute(
            select(ClubCourseCoachExclusion).where(ClubCourseCoachExclusion.course_id == course.id)
        )).scalars()
    }
    wanted = set(user_ids)
    for user_id in set(rows) - wanted:
        await db.delete(rows[user_id])
    for user_id in wanted - set(rows):
        db.add(ClubCourseCoachExclusion(
            club_id=scope.club_id, course_id=course.id, user_id=user_id, created_by_user_id=actor_user_id,
        ))
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.course_coach_exclusions_set", entity_type="club_course", entity_id=str(course.id),
        previous_value={"user_ids": sorted(str(u) for u in rows)},
        new_value={"user_ids": sorted(str(u) for u in wanted)},
    )
    await db.commit()
    return sorted(wanted, key=str)


async def slots_by_course(db: AsyncSession, *, course_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[ClubCourseSlot]]:
    out: dict[uuid.UUID, list[ClubCourseSlot]] = {c: [] for c in course_ids}
    if not course_ids:
        return out
    rows = (
        await db.execute(
            select(ClubCourseSlot)
            .where(ClubCourseSlot.course_id.in_(course_ids))
            .order_by(ClubCourseSlot.weekday, ClubCourseSlot.starts_at)
        )
    ).scalars()
    for slot in rows:
        out[slot.course_id].append(slot)
    return out


async def add_slot(
    db: AsyncSession, *, scope: ClubScope, course_id: uuid.UUID, actor_user_id: uuid.UUID,
    weekday: int, starts_at: time, ends_at: time, room: str | None,
) -> ClubCourseSlot:
    await get_course(db, scope=scope, course_id=course_id)
    if not 0 <= weekday <= 6:
        raise ClubValidationError("Giorno della settimana non valido.")
    if ends_at <= starts_at:
        raise ClubValidationError("L'orario di fine deve essere dopo quello di inizio.")
    slot = ClubCourseSlot(course_id=course_id, weekday=weekday, starts_at=starts_at, ends_at=ends_at, room=room)
    db.add(slot)
    await db.flush()
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.course_slot_added", entity_type="club_course", entity_id=str(course_id),
        new_value={"weekday": weekday, "starts_at": starts_at.isoformat(), "ends_at": ends_at.isoformat()},
    )
    await db.commit()
    await db.refresh(slot)
    return slot


async def update_slot(
    db: AsyncSession, *, scope: ClubScope, slot_id: uuid.UUID, actor_user_id: uuid.UUID,
    weekday: int, starts_at: time, ends_at: time, room: str | None,
) -> ClubCourseSlot:
    """Corregge un orario (giorno, ore, sala) senza toglierlo e rifarlo: le
    presenze già segnate restano sul corso, non sull'orario."""
    slot = await db.get(ClubCourseSlot, slot_id)
    if slot is None:
        raise ClubNotFoundError("Orario non trovato.")
    await get_course(db, scope=scope, course_id=slot.course_id)
    if not 0 <= weekday <= 6:
        raise ClubValidationError("Giorno della settimana non valido.")
    if ends_at <= starts_at:
        raise ClubValidationError("L'orario di fine deve essere dopo quello di inizio.")
    previous = {"weekday": slot.weekday, "starts_at": slot.starts_at.isoformat(), "ends_at": slot.ends_at.isoformat()}
    slot.weekday, slot.starts_at, slot.ends_at, slot.room = weekday, starts_at, ends_at, room
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.course_slot_updated", entity_type="club_course", entity_id=str(slot.course_id),
        previous_value=previous,
        new_value={"weekday": weekday, "starts_at": starts_at.isoformat(), "ends_at": ends_at.isoformat()},
    )
    await db.commit()
    await db.refresh(slot)
    return slot


async def delete_slot(db: AsyncSession, *, scope: ClubScope, slot_id: uuid.UUID, actor_user_id: uuid.UUID) -> None:
    slot = await db.get(ClubCourseSlot, slot_id)
    if slot is None:
        raise ClubNotFoundError("Orario non trovato.")
    await get_course(db, scope=scope, course_id=slot.course_id)
    await db.delete(slot)
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.course_slot_deleted", entity_type="club_course", entity_id=str(slot.course_id),
    )
    await db.commit()


async def enrolled_athlete_ids(db: AsyncSession, *, course_ids: list[uuid.UUID]) -> dict[uuid.UUID, set[uuid.UUID]]:
    out: dict[uuid.UUID, set[uuid.UUID]] = {c: set() for c in course_ids}
    if not course_ids:
        return out
    rows = (
        await db.execute(
            select(ClubCourseAthlete.course_id, ClubCourseAthlete.athlete_id).where(
                ClubCourseAthlete.course_id.in_(course_ids)
            )
        )
    ).all()
    for course_id, athlete_id in rows:
        out[course_id].add(athlete_id)
    return out


async def enrol(
    db: AsyncSession, *, course: ClubCourse, athlete: ClubAthlete, actor_user_id: uuid.UUID,
) -> None:
    """Idempotente: iscrivere due volte lo stesso atleta non fa niente."""
    if not course.active:
        raise ClubValidationError("Il corso non è attivo.")
    if athlete.status != "ACTIVE":
        raise ClubValidationError(f"{athlete.first_name} non risulta attivo nel club.")
    await db.execute(
        insert(ClubCourseAthlete)
        .values(id=uuid.uuid4(), created_at=utcnow(), course_id=course.id, athlete_id=athlete.id)
        .on_conflict_do_nothing(constraint="uq_club_course_athletes_course_athlete")
    )
    await _attribute_orphan_fees(db, course=course, athlete=athlete)
    await audit_service.record(
        db, organization_id=course.organization_id, actor_user_id=actor_user_id,
        action="club.course_enrolled", entity_type="club_course", entity_id=str(course.id),
        new_value={"athlete_id": str(athlete.id)},
    )
    await db.commit()


async def _attribute_orphan_fees(db: AsyncSession, *, course: ClubCourse, athlete: ClubAthlete) -> None:
    """Nei corsi JAV una mensilità emessa quando l'atleta non aveva ancora un
    corso (aggiunto senza sceglierlo) va al primo corso a cui si iscrive.
    Solo le quote ancora da pagare e senza corso: un'attribuzione già fatta
    non si cambia mai, e un incasso già entrato resta dov'era."""
    from app.domains.club.service import course_attribution

    if not (await kinds.club_rules(db, club_id=course.club_id)).coach_paid_by_share:
        return
    await db.execute(
        update(ClubFee)
        .where(
            ClubFee.athlete_id == athlete.id, ClubFee.club_id == course.club_id, ClubFee.kind == "MONTHLY",
            ClubFee.status == "DUE", ClubFee.course_id.is_(None),
        )
        .values(**course_attribution(course))
    )


async def unenrol(db: AsyncSession, *, course: ClubCourse, athlete: ClubAthlete, actor_user_id: uuid.UUID) -> None:
    row = (
        await db.execute(
            select(ClubCourseAthlete).where(
                ClubCourseAthlete.course_id == course.id, ClubCourseAthlete.athlete_id == athlete.id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise ClubNotFoundError(f"{athlete.first_name} non è iscritto a questo corso.")
    await db.delete(row)
    await audit_service.record(
        db, organization_id=course.organization_id, actor_user_id=actor_user_id,
        action="club.course_unenrolled", entity_type="club_course", entity_id=str(course.id),
        new_value={"athlete_id": str(athlete.id)},
    )
    await db.commit()


async def roster(db: AsyncSession, *, course: ClubCourse, on: date) -> list[tuple[ClubAthlete, bool | None, str | None]]:
    """Gli iscritti al corso e, per ognuno, la presenza del giorno (None se
    non ancora segnata) e la nota per la segreteria."""
    athletes = list(
        (
            await db.execute(
                select(ClubAthlete)
                .join(ClubCourseAthlete, ClubCourseAthlete.athlete_id == ClubAthlete.id)
                .where(ClubCourseAthlete.course_id == course.id, ClubAthlete.status == "ACTIVE")
                .order_by(ClubAthlete.last_name, ClubAthlete.first_name)
            )
        ).scalars()
    )
    marks = {
        athlete_id: (present, note)
        for athlete_id, present, note in (
            await db.execute(
                select(ClubAttendance.athlete_id, ClubAttendance.present, ClubAttendance.note).where(
                    ClubAttendance.course_id == course.id, ClubAttendance.date == on
                )
            )
        ).all()
    }
    return [(a, *marks.get(a.id, (None, None))) for a in athletes]


async def mark_attendance(
    db: AsyncSession, *, course: ClubCourse, athlete: ClubAthlete, on: date, present: bool, actor_user_id: uuid.UUID,
    note: str | None = None, by_family: bool = False,
) -> None:
    """Segna (o corregge) la presenza. Lo staff può tornare sui giorni
    passati; il genitore solo oggi (lo controlla lessons.py prima di
    chiamare)."""
    from app.domains.club.lessons import club_now

    if on > (await club_now(db, club_id=course.club_id)).date():
        raise ClubValidationError("Non si può segnare una presenza in un giorno futuro.")
    note = (note or "").strip()[:300] or None
    values = {"present": present, "recorded_by_user_id": actor_user_id, "recorded_by_kind": "FAMILY" if by_family else "STAFF"}
    if note is not None:
        values["note"] = note
    await db.execute(
        insert(ClubAttendance)
        .values(
            id=uuid.uuid4(), created_at=utcnow(), **scope_of(course).columns(), course_id=course.id,
            athlete_id=athlete.id, date=on, **values, **({} if note is not None else {"note": None}),
        )
        .on_conflict_do_update(constraint="uq_club_attendances_athlete_course_date", set_=values)
    )
    await db.commit()


async def staff_ids_by_course(db: AsyncSession, *, course_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[uuid.UUID]]:
    out: dict[uuid.UUID, list[uuid.UUID]] = {c: [] for c in course_ids}
    if course_ids:
        for course_id, user_id in (
            await db.execute(
                select(ClubCourseStaff.course_id, ClubCourseStaff.user_id).where(ClubCourseStaff.course_id.in_(course_ids))
            )
        ).all():
            out[course_id].append(user_id)
    return out


async def set_course_staff(
    db: AsyncSession, *, scope: ClubScope, course_id: uuid.UUID, user_ids: list[uuid.UUID], actor_user_id: uuid.UUID,
) -> None:
    """Gli adjunto del corso: l'elenco intero, che sostituisce il precedente."""
    course = await get_course(db, scope=scope, course_id=course_id)
    for user_id in user_ids:
        await _validate_instructor(db, scope=scope, user_id=user_id)
    current = set((await staff_ids_by_course(db, course_ids=[course.id]))[course.id])
    wanted = set(user_ids) - {course.instructor_user_id}
    for user_id in current - wanted:
        row = (
            await db.execute(
                select(ClubCourseStaff).where(ClubCourseStaff.course_id == course.id, ClubCourseStaff.user_id == user_id)
            )
        ).scalar_one()
        await db.delete(row)
    for user_id in wanted - current:
        db.add(ClubCourseStaff(course_id=course.id, user_id=user_id))
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.course_staff_set", entity_type="club_course", entity_id=str(course.id),
        new_value={"user_ids": [str(u) for u in sorted(wanted, key=str)]},
    )
    await db.commit()


async def teaches(db: AsyncSession, *, course: ClubCourse, user_id: uuid.UUID) -> bool:
    if course.instructor_user_id == user_id:
        return True
    return (
        await db.execute(
            select(ClubCourseStaff.id).where(ClubCourseStaff.course_id == course.id, ClubCourseStaff.user_id == user_id)
        )
    ).first() is not None


async def attendance_counts(db: AsyncSession, *, athlete_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """Presenze (solo quelle "presente") da sempre, per atleta."""
    if not athlete_ids:
        return {}
    rows = (
        await db.execute(
            select(ClubAttendance.athlete_id, func.count())
            .where(ClubAttendance.athlete_id.in_(athlete_ids), ClubAttendance.present.is_(True))
            .group_by(ClubAttendance.athlete_id)
        )
    ).all()
    out = {a: 0 for a in athlete_ids}
    out.update(dict(rows))
    return out
