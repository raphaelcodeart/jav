"""Le lezioni: gli orari settimanali dei corsi, calati sui giorni veri.

- il **calendario** di chi insegna: le lezioni dei suoi corsi (titolare o
  adjunto) in un intervallo di giorni; la segreteria vede tutto il club;
- le **lezioni di oggi**, con quella in corso (o la prossima) già scelta:
  lo strumento presenze si apre lì, senza cercare;
- le **presenze segnate dal genitore**: solo oggi, solo per i suoi atleti e
  solo nelle lezioni di oggi dei corsi a cui sono iscritti. Correggere i
  giorni passati è della segreteria e degli istruttori;
- il **registro del giorno** per la segreteria: ogni presenza segnata, da
  chi, con la nota.
"""

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.club import courses as courses_service
from app.domains.club.models import (
    ClubAthlete,
    ClubAttendance,
    ClubCourse,
    ClubCourseAthlete,
    ClubCourseSlot,
)
from app.domains.club.scope import ClubScope
from app.domains.club.service import ClubNotFoundError, ClubValidationError, get_owned_athlete

#: Oltre a questo numero di giorni il calendario non si calcola in una volta.
MAX_RANGE_DAYS = 62
#: Il fuso dei club che non ne indicano uno (`clubs.settings["timezone"]`):
#: le lezioni sono in ora locale, il server è in UTC.
DEFAULT_TIMEZONE = "Europe/Lisbon"


async def club_now(db: AsyncSession, *, club_id: uuid.UUID) -> datetime:
    """L'ora locale del club, senza fuso (come gli orari delle lezioni)."""
    from zoneinfo import ZoneInfo

    from app.domains.club.models import Club

    club = await db.get(Club, club_id)
    name = ((club.settings or {}).get("timezone") if club else None) or DEFAULT_TIMEZONE
    return utcnow().astimezone(ZoneInfo(name)).replace(tzinfo=None)


async def lessons(
    db: AsyncSession, *, scope: ClubScope, start: date, end: date, teacher_user_id: uuid.UUID | None,
    now: datetime | None = None,
) -> list[dict]:
    """Le lezioni tra `start` ed `end` (compresi), ordinate. Con
    `teacher_user_id` solo i corsi che quel treinador vede
    (`courses.visible_course_filter`: tutti, tranne quelli da cui è escluso),
    con `mine` sulle lezioni dei corsi che insegna."""
    if end < start or (end - start).days > MAX_RANGE_DAYS:
        raise ClubValidationError("Scegli un intervallo di al massimo due mesi.")
    courses = await courses_service.list_courses(db, scope=scope, visible_to_user_id=teacher_user_id)
    if not courses:
        return []
    taught = (
        await courses_service.taught_course_ids(db, scope=scope, user_id=teacher_user_id)
        if teacher_user_id is not None else set()
    )
    by_id = {c.id: c for c in courses}
    slots = await courses_service.slots_by_course(db, course_ids=list(by_id))
    enrolled = await courses_service.enrolled_athlete_ids(db, course_ids=list(by_id))
    present = {
        (course_id, day): n
        for course_id, day, n in (
            await db.execute(
                select(ClubAttendance.course_id, ClubAttendance.date, func.count())
                .where(
                    ClubAttendance.course_id.in_(list(by_id)), ClubAttendance.present.is_(True),
                    ClubAttendance.date >= start, ClubAttendance.date <= end,
                )
                .group_by(ClubAttendance.course_id, ClubAttendance.date)
            )
        ).all()
    }
    out: list[dict] = []
    day = start
    while day <= end:
        for course_id, course_slots in slots.items():
            for slot in course_slots:
                if slot.weekday != day.weekday():
                    continue
                out.append({
                    "course_id": course_id, "course_name": by_id[course_id].name, "slot_id": slot.id, "date": day,
                    "starts_at": slot.starts_at, "ends_at": slot.ends_at, "room": slot.room,
                    "enrolled": len(enrolled[course_id]), "present": present.get((course_id, day), 0),
                    "current": False, "mine": course_id in taught,
                })
        day += timedelta(days=1)
    out.sort(key=lambda lesson: (lesson["date"], lesson["starts_at"], lesson["course_name"]))
    _mark_current(out, now=now or await club_now(db, club_id=scope.club_id))
    return out


def _mark_current(items: list[dict], *, now: datetime) -> None:
    """La lezione in corso adesso; se non ce n'è, la prossima di oggi; se
    sono finite tutte, l'ultima di oggi. Ora locale del server."""
    today = [i for i in items if i["date"] == now.date()]
    if not today:
        return
    clock = now.time()
    running = [i for i in today if i["starts_at"] <= clock <= i["ends_at"]]
    upcoming = [i for i in today if i["starts_at"] > clock]
    (running or upcoming or today[-1:])[0]["current"] = True


async def family_today(db: AsyncSession, *, scope: ClubScope, guardian_user_id: uuid.UUID, today: date | None = None) -> list[dict]:
    """Le lezioni di oggi degli atleti della famiglia, con la presenza se
    già segnata (da chiunque)."""
    today = today or (await club_now(db, club_id=scope.club_id)).date()
    rows = (
        await db.execute(
            select(ClubAthlete, ClubCourse, ClubCourseSlot)
            .join(ClubCourseAthlete, ClubCourseAthlete.athlete_id == ClubAthlete.id)
            .join(ClubCourse, ClubCourse.id == ClubCourseAthlete.course_id)
            .join(ClubCourseSlot, ClubCourseSlot.course_id == ClubCourse.id)
            .where(
                ClubAthlete.club_id == scope.club_id, ClubAthlete.guardian_user_id == guardian_user_id,
                ClubAthlete.status == "ACTIVE", ClubCourse.active.is_(True), ClubCourseSlot.weekday == today.weekday(),
            )
            .order_by(ClubCourseSlot.starts_at, ClubAthlete.first_name)
        )
    ).all()
    if not rows:
        return []
    marks = {
        (athlete_id, course_id): (present, note)
        for athlete_id, course_id, present, note in (
            await db.execute(
                select(ClubAttendance.athlete_id, ClubAttendance.course_id, ClubAttendance.present, ClubAttendance.note)
                .where(ClubAttendance.athlete_id.in_({a.id for a, _c, _s in rows}), ClubAttendance.date == today)
            )
        ).all()
    }
    seen: set[tuple] = set()
    out = []
    for athlete, course, slot in rows:
        # Due orari dello stesso corso nello stesso giorno sono una presenza sola.
        if (athlete.id, course.id) in seen:
            continue
        seen.add((athlete.id, course.id))
        present, note = marks.get((athlete.id, course.id), (None, None))
        out.append({
            "athlete_id": athlete.id, "athlete_name": f"{athlete.first_name} {athlete.last_name}",
            "course_id": course.id, "course_name": course.name, "starts_at": slot.starts_at, "ends_at": slot.ends_at,
            "present": present, "note": note,
        })
    return out


async def family_mark(
    db: AsyncSession, *, scope: ClubScope, guardian_user_id: uuid.UUID, athlete_id: uuid.UUID,
    course_id: uuid.UUID, present: bool, note: str | None, today: date | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> None:
    """Il genitore segna (o toglie) la presenza di oggi. Solo oggi, solo una
    lezione di oggi a cui l'atleta è iscritto. Una presenza già segnata dallo
    staff, il genitore non la toglie. `actor_user_id`: chi la segna, se non
    è il titolare (l'atleta dalla sua area, club/athlete_access.py)."""
    today = today or (await club_now(db, club_id=scope.club_id)).date()
    athlete = await get_owned_athlete(db, scope=scope, guardian_user_id=guardian_user_id, athlete_id=athlete_id)
    lesson = next(
        (r for r in await family_today(db, scope=scope, guardian_user_id=guardian_user_id, today=today)
         if r["athlete_id"] == athlete.id and r["course_id"] == course_id),
        None,
    )
    if lesson is None:
        raise ClubNotFoundError("Oggi non c'è una lezione di questo corso per questo atleta.")
    existing = (
        await db.execute(
            select(ClubAttendance).where(
                ClubAttendance.athlete_id == athlete.id, ClubAttendance.course_id == course_id,
                ClubAttendance.date == today,
            )
        )
    ).scalar_one_or_none()
    if existing is not None and existing.recorded_by_kind == "STAFF" and not present:
        raise ClubValidationError("La presenza l'ha già segnata l'istruttore: per correggerla parla con la segreteria.")
    course = await db.get(ClubCourse, course_id)
    await courses_service.mark_attendance(
        db, course=course, athlete=athlete, on=today, present=present, actor_user_id=actor_user_id or guardian_user_id,
        note=note, by_family=True,
    )


async def day_log(db: AsyncSession, *, scope: ClubScope, on: date) -> list[dict]:
    """Tutte le presenze segnate in un giorno nel club, con le note: la
    segreteria sa chi è venuto e che cosa le hanno scritto."""
    rows = (
        await db.execute(
            select(ClubAttendance, ClubAthlete, ClubCourse)
            .join(ClubAthlete, ClubAthlete.id == ClubAttendance.athlete_id)
            .join(ClubCourse, ClubCourse.id == ClubAttendance.course_id)
            .where(ClubAttendance.club_id == scope.club_id, ClubAttendance.date == on)
            .order_by(ClubCourse.name, ClubAthlete.last_name, ClubAthlete.first_name)
        )
    ).all()
    return [
        {
            "athlete_id": athlete.id, "athlete_name": f"{athlete.first_name} {athlete.last_name}",
            "course_id": course.id, "course_name": course.name, "present": mark.present, "note": mark.note,
            "recorded_by_kind": mark.recorded_by_kind,
        }
        for mark, athlete, course in rows
    ]
