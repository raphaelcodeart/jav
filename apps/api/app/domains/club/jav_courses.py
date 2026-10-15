"""I corsi JAV nelle scuole: i conti corso per corso, i guadagni dei
treinador, e il passaggio di una famiglia a un club ufficiale. Specifica:
docs/club-portal.md, "Cursos JAV"; le regole del tipo di unità stanno in
club/kinds.py.

Come la contabilità del club, niente qui si salva: incassi, parte del
treinador e parte di JAV si calcolano dalle quote, che portano congelati il
corso, il treinador e la percentuale del momento in cui sono state emesse.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.club import kinds
from app.domains.club import service as club_service
from app.domains.club.accounting import Period, _month_of, _share_groups, _utc, fee_cents
from app.domains.club.models import (
    Club,
    ClubAthlete,
    ClubAttendance,
    ClubCourse,
    ClubCourseAthlete,
    ClubFee,
    ClubFunction,
    ClubMedicalCertificate,
)
from app.domains.club.scope import ClubScope
from app.domains.club.service import ClubNotFoundError, ClubValidationError
from app.domains.club.site_models import ClubAthletePublicProfile
from app.domains.users.models import User


async def require_courses_unit(db: AsyncSession, *, scope: ClubScope) -> Club:
    club = await db.get(Club, scope.club_id)
    if not kinds.is_courses_unit(club):
        raise ClubValidationError("Questa funzione è solo dei corsi JAV.")
    return club


# --- I conti corso per corso ----------------------------------------------------------------------


def _empty(course: ClubCourse | None, *, name: str) -> dict:
    return {
        "course_id": course.id if course else None, "name": name,
        "venue_name": course.venue_name if course else None, "venue_city": course.venue_city if course else None,
        "active": course.active if course else True, "published": course.published if course else False,
        "coach_user_id": course.instructor_user_id if course else None, "coach_name": None,
        "coach_share_pct": course.coach_share_pct if course else None,
        "athletes": 0, "attendances": 0, "income_cents": 0, "coach_share_cents": 0, "jav_share_cents": 0,
        "issued_cents": 0, "pending_cents": 0, "debt_cents": 0, "overdue_cents": 0,
    }


async def courses_report(db: AsyncSession, *, scope: ClubScope, period: Period, today: date) -> dict:
    """Ogni corso nel periodo: iscritti, presenze, incassato, parte del
    treinador, parte di JAV, emesso e ancora da incassare, debiti di oggi.
    Le quote senza corso (atleta non ancora iscritto a un corso) hanno una
    riga loro, perché la segreteria le veda e le sistemi."""
    from app.domains.club.people import _names

    await require_courses_unit(db, scope=scope)
    courses = list(
        (await db.execute(select(ClubCourse).where(ClubCourse.club_id == scope.club_id).order_by(ClubCourse.name))).scalars()
    )
    rows: dict[uuid.UUID | None, dict] = {c.id: _empty(c, name=c.name) for c in courses}

    def at(course_id: uuid.UUID | None) -> dict:
        return rows.setdefault(course_id, _empty(None, name=""))

    for course_id, cents in (
        await db.execute(
            select(ClubFee.course_id, func.sum(ClubFee.amount_cents))
            .where(ClubFee.club_id == scope.club_id, ClubFee.status == "PAID",
                   ClubFee.paid_at >= _utc(period.start), ClubFee.paid_at < _utc(period.end))
            .group_by(ClubFee.course_id)
        )
    ).all():
        at(course_id)["income_cents"] += int(cents or 0)
    for _club, _month, course_id, _coach, _cents, share in await _share_groups(
        db, club_ids=[scope.club_id], start=period.start, end=period.end,
    ):
        at(course_id)["coach_share_cents"] += share
    for course_id, issued, pending in (
        await db.execute(
            select(
                ClubFee.course_id,
                func.sum(ClubFee.amount_cents).filter(ClubFee.status != "WAIVED"),
                func.sum(ClubFee.amount_cents).filter(ClubFee.status == "DUE"),
            )
            .where(ClubFee.club_id == scope.club_id, ClubFee.due_date >= period.start, ClubFee.due_date < period.end)
            .group_by(ClubFee.course_id)
        )
    ).all():
        at(course_id)["issued_cents"] += int(issued or 0)
        at(course_id)["pending_cents"] += int(pending or 0)
    for course_id, debt, overdue in (
        await db.execute(
            select(
                ClubFee.course_id, func.sum(ClubFee.amount_cents),
                func.sum(ClubFee.amount_cents).filter(ClubFee.due_date < today),
            )
            .where(ClubFee.club_id == scope.club_id, ClubFee.status == "DUE", ClubFee.amount_cents > 0)
            .group_by(ClubFee.course_id)
        )
    ).all():
        at(course_id)["debt_cents"] += int(debt or 0)
        at(course_id)["overdue_cents"] += int(overdue or 0)
    ids = [c.id for c in courses]
    if ids:
        for course_id, n in (
            await db.execute(
                select(ClubCourseAthlete.course_id, func.count())
                .join(ClubAthlete, ClubAthlete.id == ClubCourseAthlete.athlete_id)
                .where(ClubCourseAthlete.course_id.in_(ids), ClubAthlete.status == "ACTIVE")
                .group_by(ClubCourseAthlete.course_id)
            )
        ).all():
            rows[course_id]["athletes"] = int(n)
        for course_id, n in (
            await db.execute(
                select(ClubAttendance.course_id, func.count())
                .where(ClubAttendance.course_id.in_(ids), ClubAttendance.present.is_(True),
                       ClubAttendance.date >= period.start, ClubAttendance.date < period.end)
                .group_by(ClubAttendance.course_id)
            )
        ).all():
            rows[course_id]["attendances"] = int(n)
    names = await _names(db, {c.instructor_user_id for c in courses if c.instructor_user_id})
    for c in courses:
        rows[c.id]["coach_name"] = names.get(c.instructor_user_id) if c.instructor_user_id else None
    out = []
    for key, row in rows.items():
        row["jav_share_cents"] = row["income_cents"] - row["coach_share_cents"]
        if key is None and not any(row[k] for k in ("income_cents", "issued_cents", "debt_cents")):
            continue
        out.append(row)
    totals = _empty(None, name="")
    for row in out:
        for k in ("athletes", "attendances", "income_cents", "coach_share_cents", "jav_share_cents",
                  "issued_cents", "pending_cents", "debt_cents", "overdue_cents"):
            totals[k] += row[k]
    return {"period": period.key, "start": period.start, "end": period.end, "courses": out, "totals": totals}


# --- I guadagni del treinador ---------------------------------------------------------------------


async def coach_earnings(db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, year: int) -> dict:
    """Mese per mese e corso per corso: quanto è entrato delle mensilità
    attribuite a lui e quanto gliene spetta; e ciò che è emesso e non ancora
    pagato, con la parte che arriverà quando lo sarà. Fuori dai corsi JAV
    (staff pagato a ore) non c'è niente da mostrare."""
    club = await db.get(Club, scope.club_id)
    if not kinds.is_courses_unit(club):
        return {"year": year, "rows": [], "earned_year_cents": 0, "pending_cents": 0}
    start, end = date(year, 1, 1), date(year + 1, 1, 1)
    out: dict[tuple[str, uuid.UUID | None, Decimal], dict] = {}

    def at(month: str, course_id: uuid.UUID | None, pct: Decimal) -> dict:
        return out.setdefault((month, course_id, pct), {
            "month": month, "course_id": course_id, "coach_share_pct": pct, "collected_cents": 0, "earned_cents": 0,
            "pending_cents": 0, "pending_earning_cents": 0,
        })

    paid_month = _month_of(ClubFee.paid_at)
    for month, course_id, pct, cents in (
        await db.execute(
            select(paid_month, ClubFee.course_id, ClubFee.coach_share_pct, func.sum(ClubFee.amount_cents))
            .where(ClubFee.club_id == scope.club_id, ClubFee.coach_user_id == user_id, ClubFee.status == "PAID",
                   ClubFee.coach_share_pct.is_not(None), ClubFee.paid_at >= _utc(start), ClubFee.paid_at < _utc(end))
            .group_by(paid_month, ClubFee.course_id, ClubFee.coach_share_pct)
        )
    ).all():
        row = at(month, course_id, Decimal(pct))
        row["collected_cents"] += int(cents or 0)
        row["earned_cents"] += fee_cents(int(cents or 0), Decimal(pct))
    due_month = func.to_char(ClubFee.due_date, "YYYY-MM")
    for month, course_id, pct, cents in (
        await db.execute(
            select(due_month, ClubFee.course_id, ClubFee.coach_share_pct, func.sum(ClubFee.amount_cents))
            .where(ClubFee.club_id == scope.club_id, ClubFee.coach_user_id == user_id, ClubFee.status == "DUE",
                   ClubFee.coach_share_pct.is_not(None), ClubFee.due_date >= start, ClubFee.due_date < end)
            .group_by(due_month, ClubFee.course_id, ClubFee.coach_share_pct)
        )
    ).all():
        row = at(month, course_id, Decimal(pct))
        row["pending_cents"] += int(cents or 0)
        row["pending_earning_cents"] += fee_cents(int(cents or 0), Decimal(pct))
    course_ids = {k[1] for k in out if k[1] is not None}
    courses = {
        c.id: c for c in (await db.execute(select(ClubCourse).where(ClubCourse.id.in_(course_ids)))).scalars()
    } if course_ids else {}
    rows = []
    for (month, course_id, _pct), row in out.items():
        course = courses.get(course_id) if course_id else None
        rows.append({**row, "course_name": course.name if course else "", "venue_name": course.venue_name if course else None})
    rows.sort(key=lambda r: (r["month"], r["course_name"]), reverse=True)
    return {
        "year": year,
        "rows": rows,
        "earned_year_cents": sum(r["earned_cents"] for r in rows),
        "pending_cents": sum(r["pending_earning_cents"] for r in rows),
    }


# --- Il passaggio a un club ufficiale -------------------------------------------------------------


async def move_targets(db: AsyncSession, *, scope: ClubScope) -> list[dict]:
    """I club ufficiali attivi in cui si può portare una famiglia."""
    await require_courses_unit(db, scope=scope)
    clubs = (
        await db.execute(
            select(Club).where(
                Club.organization_id == scope.organization_id, Club.kind == kinds.CLUB, Club.status == "ACTIVE",
            ).order_by(Club.name)
        )
    ).scalars().all()
    return [{"id": c.id, "name": c.name, "slug": c.slug} for c in clubs]


async def move_family_to_club(
    db: AsyncSession, *, scope: ClubScope, guardian_user_id: uuid.UUID, target_club_id: uuid.UUID,
    actor_user_id: uuid.UUID, today: date | None = None,
) -> dict:
    """Una famiglia dei corsi JAV passa a un club ufficiale: l'account, i suoi
    atleti, i certificati e il consenso al sito vanno al club; i corsi
    finiscono; nel club ogni atleta ha il piano per età, la cintura bianca
    (nei corsi non ne aveva), l'iscrizione dell'anno a pro rata e la
    mensilità dal mese prossimo (quella di questo mese l'ha pagata ai corsi).

    La storia resta dov'era: quote, prove di pagamento e presenze restano
    dell'unità dei corsi JAV, e i conti di quei mesi non cambiano. Rifiutato
    finché la famiglia ha quote da pagare nei corsi: altrimenti resterebbero
    debiti in un posto che la famiglia non vede più."""
    today = today or utcnow().date()
    await require_courses_unit(db, scope=scope)
    target = await db.get(Club, target_club_id)
    if (
        target is None or target.organization_id != scope.organization_id or not kinds.rules_of(target).public_as_club
        or target.status != "ACTIVE"
    ):
        raise ClubNotFoundError("Club non trovato: scegli un club ufficiale attivo.")
    user = await db.get(User, guardian_user_id)
    if user is None or user.club_id != scope.club_id:
        raise ClubNotFoundError("Famiglia non trovata nei corsi JAV.")
    athletes = list(
        (await db.execute(
            select(ClubAthlete).where(
                ClubAthlete.club_id == scope.club_id, ClubAthlete.guardian_user_id == guardian_user_id,
            ).with_for_update()
        )).scalars()
    )
    athlete_ids = [a.id for a in athletes]
    owner = (ClubFee.kind == "MEMBERSHIP") & (ClubFee.guardian_user_id == guardian_user_id)
    if athlete_ids:
        owner = owner | ClubFee.athlete_id.in_(athlete_ids)
    due = (
        await db.execute(
            select(func.count(), func.coalesce(func.sum(ClubFee.amount_cents), 0)).where(
                ClubFee.club_id == scope.club_id, ClubFee.status == "DUE", ClubFee.amount_cents > 0, owner,
            )
        )
    ).one()
    if due[0]:
        raise ClubValidationError(
            f"La famiglia ha ancora {due[0]} quote da pagare nei corsi JAV ({int(due[1]) / 100:.2f} €): "
            "prima vanno pagate o condonate, poi la famiglia può passare al club."
        )

    moving = [a for a in athletes if a.status != "LEFT"]
    moving_ids = [a.id for a in moving]
    if moving_ids:
        # I corsi della scuola finiscono; la funzione (monitor) era dell'unità.
        await db.execute(delete(ClubCourseAthlete).where(ClubCourseAthlete.athlete_id.in_(moving_ids)))
        await db.execute(
            delete(ClubFunction).where(ClubFunction.club_id == scope.club_id, ClubFunction.athlete_id.in_(moving_ids))
        )
    user.club_id = target.id
    await db.execute(
        delete(ClubFunction).where(ClubFunction.club_id == scope.club_id, ClubFunction.user_id == guardian_user_id)
    )
    for athlete in moving:
        athlete.club_id = target.id
        athlete.joined_on = today
        athlete.left_on = None
        athlete.plan_locked = False
        athlete.plan_id = None
    await db.flush()
    if moving_ids:
        # I documenti della persona la seguono (il certificato medico vale
        # anche nel club); il consenso al sito resta della famiglia, ma la
        # pubblicazione la decide il nuovo club.
        for cert in (await db.execute(
            select(ClubMedicalCertificate).where(ClubMedicalCertificate.athlete_id.in_(moving_ids))
        )).scalars():
            cert.club_id = target.id
        for profile in (await db.execute(
            select(ClubAthletePublicProfile).where(ClubAthletePublicProfile.athlete_id.in_(moving_ids))
        )).scalars():
            profile.club_id = target.id
            profile.published = False

    target_scope = ClubScope(organization_id=target.organization_id, club_id=target.id)
    pricing = await club_service.club_pricing(db, club_id=target.id)
    next_year, next_month = (today.year + (today.month == 12), today.month % 12 + 1)
    active = [a for a in moving if a.status == "ACTIVE"]
    sizes = {guardian_user_id: len(active)}
    for athlete in moving:
        plan = await club_service.assign_plan(db, athlete=athlete, year=today.year)
        club_service.give_starting_belt(db, athlete=athlete, on=today)
        await db.flush()
        if plan is not None:
            await club_service.ensure_enrollment_fee(
                db, athlete=athlete, plan=plan, year=today.year, start_month=today.month,
            )
            await club_service.ensure_monthly_fee(
                db, athlete=athlete, plan=plan, year=next_year, month=next_month, pricing=pricing,
                family_size=sizes[guardian_user_id],
            )
    await club_service.ensure_family_membership(
        db, scope=target_scope, guardian_user_id=guardian_user_id, on=today, pricing=pricing,
    )
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.family_moved_to_club", entity_type="user", entity_id=str(guardian_user_id),
        previous_value={"club_id": str(scope.club_id)},
        new_value={"club_id": str(target.id), "athlete_ids": [str(a) for a in moving_ids]},
    )
    await db.commit()
    return {"user_id": guardian_user_id, "club_id": target.id, "club_name": target.name, "athletes": len(moving)}
