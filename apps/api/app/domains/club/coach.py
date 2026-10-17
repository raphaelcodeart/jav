"""Gli strumenti del treinador oltre a presenze e cartellino. Specifica:
docs/club-portal.md, "L'area del treinador".

- **Início**: quello che serve ogni giorno in una schermata (le lezioni di
  oggi, i registri delle presenze rimasti vuoti, le prove in arrivo, i
  messaggi non letti, gli atleti a cui fare attenzione);
- **il quaderno del treinador**: le note delle lezioni (corso + giorno: che
  cosa si è fatto, le tecniche, le osservazioni), una storia per corso che
  si sfoglia e si cerca; e le note personali sugli atleti;
- **i miei atleti**: gli iscritti ai corsi che vede (e chi non è in nessun
  corso), con presenze recenti, certificato medico e note.

Chi vede che cosa (il controllo è qui, non nel router): un treinador vede
tutti i corsi del club tranne quelli da cui la segreteria l'ha escluso
(`courses.visible_course_filter`), gli atleti iscritti a quei corsi e quelli
attivi che non sono in nessun corso; la segreteria (`manager=True`, chi ha `club.manage`) vede tutto il club. Le note
le corregge solo chi le ha scritte; toglierle può anche la segreteria. Le note
sugli atleti non escono mai dall'area dello staff: niente famiglia, niente
atleta.
"""

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.club import courses as courses_service
from app.domains.club.coach_models import ATHLETE_NOTE_CATEGORIES, ClubAthleteNote, ClubLessonNote
from app.domains.club.models import ClubAthlete, ClubAttendance, ClubCourse, ClubCourseAthlete
from app.domains.club.scope import ClubScope
from app.domains.club.service import ClubNotFoundError, ClubValidationError

MAX_BODY = 8000
MAX_TECHNIQUES = 30
#: Da quanti giorni senza venire un atleta "manca" (Início, «Atenção»).
ABSENT_DAYS = 21
#: Fin dove l'Início cerca i registri delle presenze rimasti vuoti.
MISSING_REGISTER_DAYS = 14
#: Le prove in arrivo che l'Início mostra.
EVENTS_AHEAD_DAYS = 60


# --- Che cosa vede chi chiede ---------------------------------------------------------------------


async def my_courses(
    db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, manager: bool, only_active: bool = False,
) -> list[ClubCourse]:
    """I corsi che chi chiede vede (tutti, tranne quelli da cui è escluso; i
    suoi per primi), anche quelli chiusi: le loro note restano sue. La
    segreteria: tutti quelli del club."""
    return await courses_service.list_courses(
        db, scope=scope, only_active=only_active, visible_to_user_id=None if manager else user_id,
    )


async def _course(
    db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, manager: bool, course_id: uuid.UUID,
) -> ClubCourse:
    course = await courses_service.get_course(db, scope=scope, course_id=course_id)
    if not manager and not await courses_service.can_see(db, course=course, user_id=user_id):
        raise ClubNotFoundError("Corso non trovato.")
    return course


async def my_athlete_ids(
    db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, manager: bool,
) -> dict[uuid.UUID, list[uuid.UUID]]:
    """Gli atleti di chi chiede, con i corsi (suoi) a cui sono iscritti."""
    courses = await my_courses(db, scope=scope, user_id=user_id, manager=manager, only_active=True)
    out: dict[uuid.UUID, list[uuid.UUID]] = {}
    for course_id, athletes in (await courses_service.enrolled_athlete_ids(db, course_ids=[c.id for c in courses])).items():
        for athlete_id in athletes:
            out.setdefault(athlete_id, []).append(course_id)
    return out


async def _athlete(
    db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, manager: bool, athlete_id: uuid.UUID,
) -> ClubAthlete:
    """L'atleta, se chi chiede lo vede (o è la segreteria): iscritto a un
    corso che vede, o attivo e senza corsi. Un atleta che sta solo in corsi da
    cui il treinador è escluso, per lui, non esiste."""
    athlete = await db.get(ClubAthlete, athlete_id)
    if athlete is None or athlete.club_id != scope.club_id:
        raise ClubNotFoundError("Atleta non trovato.")
    if not manager:
        courses = await my_courses(db, scope=scope, user_id=user_id, manager=False)
        enrolled = (
            await db.execute(
                select(ClubCourseAthlete.id).where(
                    ClubCourseAthlete.athlete_id == athlete.id,
                    ClubCourseAthlete.course_id.in_([c.id for c in courses] or [uuid.uuid4()]),
                )
            )
        ).first()
        if enrolled is None and (athlete.status != "ACTIVE" or await _in_any_active_course(db, athlete.id)):
            raise ClubNotFoundError("Atleta non trovato.")
    return athlete


async def _in_any_active_course(db: AsyncSession, athlete_id: uuid.UUID) -> bool:
    return (await db.execute(
        select(ClubCourseAthlete.id).join(ClubCourse, ClubCourse.id == ClubCourseAthlete.course_id)
        .where(ClubCourseAthlete.athlete_id == athlete_id, ClubCourse.active.is_(True))
    )).first() is not None


async def _names(db: AsyncSession, ids: set) -> dict[uuid.UUID, str]:
    from app.domains.club.people import _names as people_names

    return await people_names(db, {i for i in ids if i})


def _text(value: str | None, limit: int) -> str | None:
    return (value or "").strip()[:limit] or None


def _techniques(value: str | list[str] | None) -> str | None:
    """Le tecniche come etichette: separate da virgole, senza doppioni
    (senza badare alle maiuscole), al massimo MAX_TECHNIQUES."""
    items = value if isinstance(value, list) else (value or "").split(",")
    seen: dict[str, str] = {}
    for raw in items:
        tag = " ".join(str(raw).split())[:60]
        if tag and tag.lower() not in seen:
            seen[tag.lower()] = tag
    joined = ", ".join(list(seen.values())[:MAX_TECHNIQUES])
    return joined[:500] or None


def _tags(value: str | None) -> list[str]:
    return [t.strip() for t in (value or "").split(",") if t.strip()]


# --- Le note delle lezioni ------------------------------------------------------------------------


def _lesson_dict(n: ClubLessonNote, *, names: dict, courses: dict, viewer: uuid.UUID) -> dict:
    return {
        "id": n.id, "course_id": n.course_id, "course_name": courses.get(n.course_id, ""),
        "lesson_date": n.lesson_date, "title": n.title, "techniques": _tags(n.techniques), "body": n.body,
        "author_user_id": n.author_user_id, "author_name": names.get(n.author_user_id, ""),
        "mine": n.author_user_id == viewer, "created_at": n.created_at, "updated_at": n.updated_at,
    }


async def list_lesson_notes(
    db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, manager: bool, course_id: uuid.UUID | None = None,
    q: str | None = None, date_from: date | None = None, date_to: date | None = None, technique: str | None = None,
    limit: int = 30, offset: int = 0,
) -> dict:
    """La storia delle lezioni, dalla più recente: dei corsi di chi chiede
    (o di uno solo), con la ricerca nel tema, nelle tecniche e nel testo.
    Con le tecniche più lavorate del periodo, per vedere che cosa manca."""
    courses = await my_courses(db, scope=scope, user_id=user_id, manager=manager)
    by_id = {c.id: c.name for c in courses}
    if course_id is not None:
        if course_id not in by_id:
            raise ClubNotFoundError("Corso non trovato.")
        ids = [course_id]
    else:
        ids = list(by_id)
    if not ids:
        return {"items": [], "total": 0, "techniques": []}
    where = [ClubLessonNote.club_id == scope.club_id, ClubLessonNote.course_id.in_(ids)]
    if date_from:
        where.append(ClubLessonNote.lesson_date >= date_from)
    if date_to:
        where.append(ClubLessonNote.lesson_date <= date_to)
    period = list(where)
    if q and q.strip():
        like = f"%{q.strip()[:100]}%"
        where.append(or_(ClubLessonNote.title.ilike(like), ClubLessonNote.techniques.ilike(like),
                         ClubLessonNote.body.ilike(like)))
    if technique and technique.strip():
        where.append(ClubLessonNote.techniques.ilike(f"%{technique.strip()[:60]}%"))
    total = (await db.execute(select(func.count()).select_from(ClubLessonNote).where(*where))).scalar_one()
    rows = list((await db.execute(
        select(ClubLessonNote).where(*where)
        .order_by(ClubLessonNote.lesson_date.desc(), ClubLessonNote.created_at.desc())
        .limit(max(1, min(limit, 100))).offset(max(offset, 0))
    )).scalars())
    # Le tecniche del periodo (senza la ricerca): quante volte e l'ultima.
    counts: dict[str, dict] = {}
    for tags, day in (await db.execute(
        select(ClubLessonNote.techniques, ClubLessonNote.lesson_date).where(*period, ClubLessonNote.techniques.is_not(None))
        .order_by(ClubLessonNote.lesson_date.desc()).limit(2000)
    )).all():
        for tag in _tags(tags):
            entry = counts.setdefault(tag.lower(), {"name": tag, "count": 0, "last_date": day})
            entry["count"] += 1
    names = await _names(db, {n.author_user_id for n in rows})
    return {
        "items": [_lesson_dict(n, names=names, courses=by_id, viewer=user_id) for n in rows],
        "total": total,
        "techniques": sorted(counts.values(), key=lambda e: (-e["count"], e["name"].lower()))[:40],
    }


def _lesson_values(data: dict) -> dict:
    values = {
        "title": " ".join((data.get("title") or "").split())[:200] or None,
        "techniques": _techniques(data.get("techniques")),
        "body": _text(data.get("body"), MAX_BODY),
    }
    if not any(values.values()):
        raise ClubValidationError("Scrivi che cosa si è fatto: un tema, le tecniche o qualche riga.")
    return values


def _lesson_date(value: date, *, today: date) -> date:
    if value > today + timedelta(days=60) or value < today - timedelta(days=730):
        raise ClubValidationError("La data della lezione non è valida.")
    return value


async def add_lesson_note(
    db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, manager: bool, course_id: uuid.UUID,
    lesson_date: date, data: dict, today: date,
) -> dict:
    course = await _course(db, scope=scope, user_id=user_id, manager=manager, course_id=course_id)
    note = ClubLessonNote(**scope.columns(), course_id=course.id, lesson_date=_lesson_date(lesson_date, today=today),
                          author_user_id=user_id, **_lesson_values(data))
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return _lesson_dict(note, names=await _names(db, {user_id}), courses={course.id: course.name}, viewer=user_id)


async def _lesson_note(db: AsyncSession, *, scope: ClubScope, note_id: uuid.UUID) -> ClubLessonNote:
    note = await db.get(ClubLessonNote, note_id)
    if note is None or note.club_id != scope.club_id:
        raise ClubNotFoundError("Nota non trovata.")
    return note


async def update_lesson_note(
    db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, manager: bool, note_id: uuid.UUID, data: dict,
    today: date,
) -> dict:
    """Solo chi l'ha scritta la corregge (e solo se insegna ancora nel corso)."""
    note = await _lesson_note(db, scope=scope, note_id=note_id)
    if note.author_user_id != user_id:
        raise ClubNotFoundError("Nota non trovata.")
    course = await _course(db, scope=scope, user_id=user_id, manager=manager, course_id=note.course_id)
    merged = {"title": note.title, "techniques": note.techniques, "body": note.body, **data}
    for key, value in _lesson_values(merged).items():
        setattr(note, key, value)
    if data.get("lesson_date"):
        note.lesson_date = _lesson_date(data["lesson_date"], today=today)
    note.updated_at = utcnow()
    await db.commit()
    await db.refresh(note)
    return _lesson_dict(note, names=await _names(db, {user_id}), courses={course.id: course.name}, viewer=user_id)


async def delete_lesson_note(
    db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, manager: bool, note_id: uuid.UUID,
) -> None:
    note = await _lesson_note(db, scope=scope, note_id=note_id)
    if note.author_user_id != user_id and not manager:
        raise ClubNotFoundError("Nota non trovata.")
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=user_id, action="club.lesson_note_deleted",
        entity_type="club_lesson_note", entity_id=str(note.id),
        previous_value={"course_id": str(note.course_id), "lesson_date": note.lesson_date.isoformat(),
                        "title": note.title, "author_user_id": str(note.author_user_id)},
    )
    await db.delete(note)
    await db.commit()


# --- Le note sugli atleti -------------------------------------------------------------------------


def _athlete_note_dict(n: ClubAthleteNote, *, names: dict, viewer: uuid.UUID) -> dict:
    return {
        "id": n.id, "athlete_id": n.athlete_id, "category": n.category, "body": n.body,
        "author_user_id": n.author_user_id, "author_name": names.get(n.author_user_id, ""),
        "mine": n.author_user_id == viewer, "created_at": n.created_at, "updated_at": n.updated_at,
    }


def _category(value: str | None) -> str:
    value = (value or "OTHER").upper()
    if value not in ATHLETE_NOTE_CATEGORIES:
        raise ClubValidationError("Scegli di che cosa parla la nota.")
    return value


def _note_body(value: str | None) -> str:
    body = _text(value, MAX_BODY)
    if not body or len(body) < 2:
        raise ClubValidationError("La nota è vuota.")
    return body


async def list_athlete_notes(
    db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, manager: bool, athlete_id: uuid.UUID,
) -> list[dict]:
    athlete = await _athlete(db, scope=scope, user_id=user_id, manager=manager, athlete_id=athlete_id)
    rows = list((await db.execute(
        select(ClubAthleteNote).where(ClubAthleteNote.club_id == scope.club_id, ClubAthleteNote.athlete_id == athlete.id)
        .order_by(ClubAthleteNote.created_at.desc())
    )).scalars())
    names = await _names(db, {n.author_user_id for n in rows})
    return [_athlete_note_dict(n, names=names, viewer=user_id) for n in rows]


async def add_athlete_note(
    db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, manager: bool, athlete_id: uuid.UUID, data: dict,
) -> dict:
    athlete = await _athlete(db, scope=scope, user_id=user_id, manager=manager, athlete_id=athlete_id)
    note = ClubAthleteNote(**scope.columns(), athlete_id=athlete.id, author_user_id=user_id,
                           category=_category(data.get("category")), body=_note_body(data.get("body")))
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return _athlete_note_dict(note, names=await _names(db, {user_id}), viewer=user_id)


async def _athlete_note(db: AsyncSession, *, scope: ClubScope, note_id: uuid.UUID) -> ClubAthleteNote:
    note = await db.get(ClubAthleteNote, note_id)
    if note is None or note.club_id != scope.club_id:
        raise ClubNotFoundError("Nota non trovata.")
    return note


async def update_athlete_note(
    db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, manager: bool, note_id: uuid.UUID, data: dict,
) -> dict:
    """Solo chi l'ha scritta la corregge; il testo di prima resta nell'audit."""
    note = await _athlete_note(db, scope=scope, note_id=note_id)
    await _athlete(db, scope=scope, user_id=user_id, manager=manager, athlete_id=note.athlete_id)
    if note.author_user_id != user_id:
        raise ClubNotFoundError("Nota non trovata.")
    previous = {"category": note.category, "body": note.body}
    if data.get("category") is not None:
        note.category = _category(data["category"])
    if data.get("body") is not None:
        note.body = _note_body(data["body"])
    note.updated_at = utcnow()
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=user_id, action="club.athlete_note_updated",
        entity_type="club_athlete_note", entity_id=str(note.id), previous_value=previous,
        new_value={"category": note.category, "body": note.body},
    )
    await db.commit()
    await db.refresh(note)
    return _athlete_note_dict(note, names=await _names(db, {user_id}), viewer=user_id)


async def delete_athlete_note(
    db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, manager: bool, note_id: uuid.UUID,
) -> None:
    note = await _athlete_note(db, scope=scope, note_id=note_id)
    await _athlete(db, scope=scope, user_id=user_id, manager=manager, athlete_id=note.athlete_id)
    if note.author_user_id != user_id and not manager:
        raise ClubNotFoundError("Nota non trovata.")
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=user_id, action="club.athlete_note_deleted",
        entity_type="club_athlete_note", entity_id=str(note.id),
        previous_value={"athlete_id": str(note.athlete_id), "category": note.category, "body": note.body,
                        "author_user_id": str(note.author_user_id)},
    )
    await db.delete(note)
    await db.commit()


# --- I miei atleti --------------------------------------------------------------------------------


async def _attendance_stats(
    db: AsyncSession, *, athlete_ids: list[uuid.UUID], since: date,
) -> tuple[dict[uuid.UUID, int], dict[uuid.UUID, date]]:
    """Presenze dal giorno `since` e l'ultima presenza di sempre, per atleta."""
    if not athlete_ids:
        return {}, {}
    recent = dict((await db.execute(
        select(ClubAttendance.athlete_id, func.count()).where(
            ClubAttendance.athlete_id.in_(athlete_ids), ClubAttendance.present.is_(True), ClubAttendance.date >= since,
        ).group_by(ClubAttendance.athlete_id)
    )).all())
    last = dict((await db.execute(
        select(ClubAttendance.athlete_id, func.max(ClubAttendance.date)).where(
            ClubAttendance.athlete_id.in_(athlete_ids), ClubAttendance.present.is_(True),
        ).group_by(ClubAttendance.athlete_id)
    )).all())
    return recent, last


async def my_athletes(
    db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, manager: bool, today: date,
) -> list[dict]:
    """Gli atleti dei corsi di chi chiede, con quello che un treinador vuole
    sapere prima della lezione: cintura, presenze degli ultimi 30 giorni,
    l'ultima volta che è venuto, il certificato medico (solo lo stato, il
    file resta della segreteria) e quante note ci sono."""
    from app.domains.club import family as family_service
    from app.domains.club import service as club_service

    courses = {c.id: c.name for c in await my_courses(db, scope=scope, user_id=user_id, manager=manager, only_active=True)}
    by_athlete = await my_athlete_ids(db, scope=scope, user_id=user_id, manager=manager)
    # Anche chi non è (ancora) iscritto a un corso: la segreteria tutti gli
    # attivi, un treinador quelli che non stanno in nessun corso attivo (gli
    # iscritti solo a corsi da cui è escluso restano fuori).
    in_courses = select(ClubCourseAthlete.athlete_id).join(ClubCourse, ClubCourse.id == ClubCourseAthlete.course_id) \
        .where(ClubCourse.active.is_(True))
    loose = select(ClubAthlete.id).where(ClubAthlete.club_id == scope.club_id, ClubAthlete.status == "ACTIVE")
    if not manager:
        loose = loose.where(ClubAthlete.id.not_in(in_courses))
    for (athlete_id,) in (await db.execute(loose)).all():
        by_athlete.setdefault(athlete_id, [])
    if not by_athlete:
        return []
    athletes = list((await db.execute(
        select(ClubAthlete).where(ClubAthlete.id.in_(list(by_athlete)), ClubAthlete.status == "ACTIVE")
        .order_by(ClubAthlete.first_name, ClubAthlete.last_name)
    )).scalars())
    ids = [a.id for a in athletes]
    belts = await club_service.current_belts(db, athlete_ids=ids)
    certs = await club_service.latest_certificates(db, athlete_ids=ids)
    recent, last = await _attendance_stats(db, athlete_ids=ids, since=today - timedelta(days=30))
    notes = {
        athlete_id: (n, at) for athlete_id, n, at in (await db.execute(
            select(ClubAthleteNote.athlete_id, func.count(), func.max(ClubAthleteNote.created_at))
            .where(ClubAthleteNote.athlete_id.in_(ids)).group_by(ClubAthleteNote.athlete_id)
        )).all()
    }
    out = []
    for a in athletes:
        cert = certs.get(a.id)
        n, at = notes.get(a.id, (0, None))
        out.append({
            "id": a.id, "first_name": a.first_name, "last_name": a.last_name, "photo_url": a.photo_url,
            "sex": a.sex, "birth_date": a.birth_date, "belt": family_service.belt_dict(belts.get(a.id)),
            "courses": sorted(courses[c] for c in by_athlete[a.id] if c in courses),
            "course_ids": [c for c in by_athlete[a.id] if c in courses],
            "attended_30d": recent.get(a.id, 0), "last_present": last.get(a.id),
            "certificate_status": club_service.certificate_status(cert, today=today),
            "certificate_expires_on": cert.expires_on if cert else None,
            "notes": n, "last_note_at": at,
        })
    return out


async def athlete_sheet(
    db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, manager: bool, athlete_id: uuid.UUID, today: date,
) -> dict:
    """La scheda di un atleta per il treinador: com'è, le presenze degli
    ultimi 90 giorni giorno per giorno, il certificato e le note."""
    from app.domains.club import family as family_service
    from app.domains.club import service as club_service

    athlete = await _athlete(db, scope=scope, user_id=user_id, manager=manager, athlete_id=athlete_id)
    courses = {c.id: c.name for c in await my_courses(db, scope=scope, user_id=user_id, manager=manager)}
    enrolled = [c for (c,) in (await db.execute(
        select(ClubCourseAthlete.course_id).where(ClubCourseAthlete.athlete_id == athlete.id)
    )).all() if c in courses]
    since = today - timedelta(days=90)
    marks = (await db.execute(
        select(ClubAttendance.date, ClubAttendance.course_id, ClubAttendance.present, ClubAttendance.note)
        .where(ClubAttendance.athlete_id == athlete.id, ClubAttendance.date >= since)
        .order_by(ClubAttendance.date.desc())
    )).all()
    cert = (await club_service.latest_certificates(db, athlete_ids=[athlete.id])).get(athlete.id)
    belt = (await club_service.current_belts(db, athlete_ids=[athlete.id])).get(athlete.id)
    return {
        "id": athlete.id, "first_name": athlete.first_name, "last_name": athlete.last_name,
        "photo_url": athlete.photo_url, "sex": athlete.sex, "birth_date": athlete.birth_date,
        "weight_kg": float(athlete.weight_kg) if athlete.weight_kg is not None else None,
        "adapted_judo": bool(athlete.adapted_judo), "belt": family_service.belt_dict(belt),
        "courses": [{"id": c, "name": courses[c]} for c in enrolled],
        "certificate_status": club_service.certificate_status(cert, today=today),
        "certificate_expires_on": cert.expires_on if cert else None,
        "attendance": [
            {"date": d, "course_id": c, "course_name": courses.get(c, ""), "present": p, "note": n}
            for d, c, p, n in marks
        ],
        "present_90d": sum(1 for m in marks if m.present),
        "notes": await list_athlete_notes(db, scope=scope, user_id=user_id, manager=manager, athlete_id=athlete.id),
    }


# --- Início ---------------------------------------------------------------------------------------


async def home(db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, manager: bool, now: datetime) -> dict:
    """L'Início del treinador. `now` è l'ora locale del club (lessons.club_now)."""
    from app.domains.club import calendar
    from app.domains.club import lessons as lessons_service
    from app.domains.club.operations_models import ClubStaffMessage

    today = now.date()
    teacher = None if manager else user_id
    window = await lessons_service.lessons(
        db, scope=scope, start=today - timedelta(days=MISSING_REGISTER_DAYS), end=today,
        teacher_user_id=teacher, now=now,
    )
    today_lessons = [lesson for lesson in window if lesson["date"] == today]
    # Un registro vuoto di una lezione già finita: quasi sempre dimenticato.
    missing = [
        lesson for lesson in window
        if lesson["present"] == 0 and lesson["enrolled"] > 0
        and (lesson["date"] < today or lesson["ends_at"] < now.time())
    ]
    missing.sort(key=lambda lesson: (lesson["date"], lesson["starts_at"]), reverse=True)
    events = await calendar.calendar_events(db, scope=scope, date_from=today,
                                            date_to=today + timedelta(days=EVENTS_AHEAD_DAYS))
    unread = dict((await db.execute(
        select(ClubStaffMessage.channel, func.count()).where(
            ClubStaffMessage.club_id == scope.club_id, ClubStaffMessage.staff_user_id == user_id,
            ClubStaffMessage.from_staff.is_(False), ClubStaffMessage.read_at.is_(None),
        ).group_by(ClubStaffMessage.channel)
    )).all())
    athletes = await my_athletes(db, scope=scope, user_id=user_id, manager=manager, today=today)
    coached = [a for a in athletes if a["course_ids"]]
    absent = [
        a for a in coached
        if a["last_present"] is not None and (today - a["last_present"]).days >= ABSENT_DAYS
    ]
    absent.sort(key=lambda a: a["last_present"])
    certificate = [a for a in coached if a["certificate_status"] in ("EXPIRED", "MISSING", "EXPIRING")]
    certificate.sort(key=lambda a: ({"EXPIRED": 0, "MISSING": 1, "EXPIRING": 2}[a["certificate_status"]], a["first_name"]))
    notes = await list_lesson_notes(db, scope=scope, user_id=user_id, manager=manager, limit=3)

    def brief(a: dict) -> dict:
        return {k: a[k] for k in ("id", "first_name", "last_name", "photo_url", "belt", "last_present",
                                  "certificate_status", "certificate_expires_on")}

    return {
        "today": today,
        "lessons_today": today_lessons,
        "missing_registers": missing[:8],
        "missing_count": len(missing),
        "events": [{**e, "id": str(e["id"])} for e in events[:6]],
        "unread_club": unread.get("CLUB", 0),
        "unread_jav": unread.get("JAV", 0),
        "athletes": len(coached),
        "courses": len(await my_courses(db, scope=scope, user_id=user_id, manager=manager, only_active=True)),
        "absent": [brief(a) for a in absent[:6]],
        "absent_count": len(absent),
        "certificates": [brief(a) for a in certificate[:6]],
        "certificates_count": len(certificate),
        "recent_notes": notes["items"],
    }
