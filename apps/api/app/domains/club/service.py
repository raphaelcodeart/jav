"""Atleti, piani, quote, prove di pagamento, certificati e cinture.

Le gare stanno in competitions.py, corsi e presenze in courses.py, la pagina
del genitore in family.py, i job automatici in tasks.py.

Ogni funzione che il genitore può chiamare riceve `guardian_user_id` e lo
verifica qui, nel servizio: il router non ha l'atleta in mano, il servizio
sì (stesso principio di core/deps.py::require_permission).
"""

import logging
import uuid
from datetime import date, timedelta
from html import escape

from sqlalchemy import func, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import utcnow
from app.core.email import send_html_email_best_effort
from app.core.email_templates import render_email
from app.domains.audit import service as audit_service
from app.domains.club import belts as belts_catalog
from app.domains.club import kinds, receipts, referrals, seasons
from app.domains.club import pricing as pricing_rules
from app.domains.club.models import (
    ATHLETE_STATUSES,
    CERTIFICATE_TYPES,
    SOCIAL_TIERS,
    Club,
    ClubAthlete,
    ClubBeltGrade,
    ClubCourse,
    ClubCourseAthlete,
    ClubFee,
    ClubMedicalCertificate,
    ClubPaymentProof,
    ClubPaymentProofFee,
    ClubPlan,
)
from app.domains.club.scope import ClubScope, scope_of
from app.domains.notifications import service as notifications_service
from app.domains.users.models import User

logger = logging.getLogger(__name__)

#: Quanto prima della scadenza un certificato si mostra "in scadenza".
CERTIFICATE_EXPIRING_DAYS = 30
PRESIGNED_URL_TTL_SECONDS = 300


class ClubError(Exception):
    """Ogni messaggio è già scritto per chi usa l'app, in italiano."""


class ClubNotFoundError(ClubError):
    pass


class ClubValidationError(ClubError):
    pass


# --- Piani ----------------------------------------------------------------------------------------


async def list_plans(db: AsyncSession, *, scope: ClubScope, only_active: bool = False) -> list[ClubPlan]:
    stmt = select(ClubPlan).where(ClubPlan.club_id == scope.club_id)
    if only_active:
        stmt = stmt.where(ClubPlan.active.is_(True))
    return list((await db.execute(stmt.order_by(ClubPlan.min_age, ClubPlan.name))).scalars())


def _validate_plan(*, min_age: int, max_age: int | None, billing_months: list[int]) -> None:
    if max_age is not None and max_age < min_age:
        raise ClubValidationError("L'età massima non può essere inferiore all'età minima.")
    if not billing_months or any(m < 1 or m > 12 for m in billing_months):
        raise ClubValidationError("Indica almeno un mese di fatturazione, da 1 (gennaio) a 12 (dicembre).")


async def _check_enrollment_allowed(db: AsyncSession, *, club_id: uuid.UUID, enrollment_fee_cents: int | None) -> None:
    """Nei corsi JAV si paga solo la mensilità (kinds.py): un'iscrizione
    annuale messa per sbaglio in un piano verrebbe emessa a ogni atleta."""
    if enrollment_fee_cents and not (await kinds.club_rules(db, club_id=club_id)).has_enrollment_fees:
        raise ClubValidationError("Nei corsi JAV l'iscrizione è gratuita: lascia l'iscrizione a 0.")


async def create_plan(db: AsyncSession, *, scope: ClubScope, actor_user_id: uuid.UUID, data: dict) -> ClubPlan:
    months = sorted(set(data.get("billing_months") or [9, 10, 11, 12, 1, 2, 3, 4, 5, 6]), key=lambda m: (m < 9, m))
    _validate_plan(min_age=data["min_age"], max_age=data.get("max_age"), billing_months=months)
    await _check_enrollment_allowed(db, club_id=scope.club_id, enrollment_fee_cents=data.get("enrollment_fee_cents"))
    plan = ClubPlan(**scope.columns(), **{**data, "billing_months": months})
    db.add(plan)
    await db.flush()
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.plan_created", entity_type="club_plan", entity_id=str(plan.id),
        new_value={"name": plan.name, "min_age": plan.min_age, "max_age": plan.max_age},
    )
    await db.commit()
    await db.refresh(plan)
    return plan


async def update_plan(
    db: AsyncSession, *, scope: ClubScope, plan_id: uuid.UUID, actor_user_id: uuid.UUID, changes: dict
) -> ClubPlan:
    plan = await db.get(ClubPlan, plan_id)
    if plan is None or plan.club_id != scope.club_id:
        raise ClubNotFoundError("Piano non trovato.")
    if "billing_months" in changes and changes["billing_months"] is not None:
        changes["billing_months"] = sorted(set(changes["billing_months"]), key=lambda m: (m < 9, m))
    await _check_enrollment_allowed(db, club_id=scope.club_id, enrollment_fee_cents=changes.get("enrollment_fee_cents"))
    for key, value in changes.items():
        setattr(plan, key, value)
    _validate_plan(min_age=plan.min_age, max_age=plan.max_age, billing_months=plan.billing_months)
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.plan_updated", entity_type="club_plan", entity_id=str(plan.id),
        new_value={k: v for k, v in changes.items() if k != "billing_months"},
    )
    await db.commit()
    await db.refresh(plan)
    return plan


async def delete_plan(db: AsyncSession, *, scope: ClubScope, plan_id: uuid.UUID, actor_user_id: uuid.UUID) -> None:
    """Un piano che qualcuno usa non si cancella: si disattiva. Le quote già
    emesse hanno il loro importo congelato, ma l'atleta deve continuare a
    sapere qual è il suo piano."""
    plan = await db.get(ClubPlan, plan_id)
    if plan is None or plan.club_id != scope.club_id:
        raise ClubNotFoundError("Piano non trovato.")
    in_use = (await db.execute(select(func.count()).where(ClubAthlete.plan_id == plan_id))).scalar_one()
    if in_use:
        raise ClubValidationError(
            f"Il piano è assegnato a {in_use} atleti: disattivalo invece di cancellarlo."
        )
    await db.delete(plan)
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.plan_deleted", entity_type="club_plan", entity_id=str(plan_id),
    )
    await db.commit()


def pick_plan(plans: list[ClubPlan], *, age: int) -> ClubPlan | None:
    """Il piano attivo che copre l'età. Se più piani la coprono vince il più
    stretto: "Agonisti 14-17" batte "Tutti 4+"."""
    fitting = [
        p for p in plans
        if p.active and p.min_age <= age and (p.max_age is None or age <= p.max_age)
    ]
    if not fitting:
        return None
    return min(fitting, key=lambda p: ((p.max_age if p.max_age is not None else 200) - p.min_age, -p.min_age))


async def assign_plan(db: AsyncSession, *, athlete: ClubAthlete, year: int) -> ClubPlan | None:
    """Assegna il piano per l'età federale dell'anno solare `year`
    (seasons.federal_age), salvo che la segreteria l'abbia scelto a mano.
    Non committa."""
    if athlete.plan_locked:
        return await db.get(ClubPlan, athlete.plan_id) if athlete.plan_id else None
    plans = await list_plans(db, scope=scope_of(athlete), only_active=True)
    plan = pick_plan(plans, age=seasons.federal_age(athlete.birth_date, year))
    athlete.plan_id = plan.id if plan else None
    return plan


# --- Atleti ---------------------------------------------------------------------------------------


async def get_owned_athlete(
    db: AsyncSession, *, scope: ClubScope, guardian_user_id: uuid.UUID, athlete_id: uuid.UUID
) -> ClubAthlete:
    """L'atleta, se è di questa famiglia. Un atleta di un'altra famiglia è
    "non trovato", non "vietato": non si conferma che esista."""
    athlete = await db.get(ClubAthlete, athlete_id)
    if athlete is None or athlete.club_id != scope.club_id or athlete.guardian_user_id != guardian_user_id:
        raise ClubNotFoundError("Atleta non trovato.")
    return athlete


async def get_athlete(db: AsyncSession, *, scope: ClubScope, athlete_id: uuid.UUID) -> ClubAthlete:
    athlete = await db.get(ClubAthlete, athlete_id)
    if athlete is None or athlete.club_id != scope.club_id:
        raise ClubNotFoundError("Atleta non trovato.")
    return athlete


async def list_family_athletes(
    db: AsyncSession, *, scope: ClubScope, guardian_user_id: uuid.UUID, include_left: bool = False
) -> list[ClubAthlete]:
    stmt = select(ClubAthlete).where(
        ClubAthlete.club_id == scope.club_id, ClubAthlete.guardian_user_id == guardian_user_id
    )
    if not include_left:
        stmt = stmt.where(ClubAthlete.status != "LEFT")
    return list((await db.execute(stmt.order_by(ClubAthlete.is_self.desc(), ClubAthlete.birth_date))).scalars())


def _validate_birth_date(birth_date: date, *, today: date) -> None:
    if birth_date > today:
        raise ClubValidationError("La data di nascita non può essere nel futuro.")
    if seasons.age_on(birth_date, today) > 110:
        raise ClubValidationError("Controlla la data di nascita: risulta un'età di oltre 110 anni.")


async def create_athlete(
    db: AsyncSession,
    *,
    scope: ClubScope,
    guardian_user_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    first_name: str,
    last_name: str,
    birth_date: date,
    sex: str,
    is_self: bool = False,
    fiscal_code: str | None = None,
    weight_kg=None,
    belt: str | None = None,
    course_id: uuid.UUID | None = None,
    today: date | None = None,
) -> ClubAthlete:
    """Il genitore aggiunge un figlio (o se stesso). Il resto lo fa il
    sistema: il piano dall'età, la cintura bianca (o quella dichiarata),
    l'iscrizione dell'anno a pro rata, la quota del mese in corso e, per un
    minorenne, la quota socio del genitore.

    Nei corsi JAV (kinds.py) niente cintura, e `course_id` è il corso a cui
    l'atleta si iscrive subito: prima delle quote, perché la mensilità del
    mese nasca già attribuita al suo corso."""
    today = today or utcnow().date()
    _validate_birth_date(birth_date, today=today)
    if sex not in ("M", "F"):
        raise ClubValidationError("Indica il sesso dell'atleta (M o F).")
    rules = await kinds.club_rules(db, club_id=scope.club_id)
    if belt is not None and not rules.has_belts:
        raise ClubValidationError(kinds.NO_BELTS)
    if belt is not None and belt not in belts_catalog.BELT_CODES:
        raise ClubValidationError("Cintura non riconosciuta.")
    course = None
    if course_id is not None:
        course = await db.get(ClubCourse, course_id)
        if course is None or course.club_id != scope.club_id or not course.active:
            raise ClubValidationError("Corso non trovato: scegline uno dall'elenco.")
    if is_self:
        existing_self = (
            await db.execute(
                select(ClubAthlete.id).where(
                    ClubAthlete.guardian_user_id == guardian_user_id, ClubAthlete.is_self.is_(True)
                )
            )
        ).first()
        if existing_self is not None:
            raise ClubValidationError("Hai già un profilo atleta per te stesso.")

    athlete = ClubAthlete(
        **scope.columns(),
        guardian_user_id=guardian_user_id,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        birth_date=birth_date,
        sex=sex,
        is_self=is_self,
        fiscal_code=(fiscal_code or "").strip().upper() or None,
        weight_kg=weight_kg,
        joined_on=today,
        status="ACTIVE",
    )
    db.add(athlete)
    await db.flush()

    plan = await assign_plan(db, athlete=athlete, year=today.year)
    if rules.has_belts:
        give_starting_belt(db, athlete=athlete, on=today, belt=belt)
    if course is not None:
        db.add(ClubCourseAthlete(course_id=course.id, athlete_id=athlete.id))
    await db.flush()
    if plan is not None:
        pricing = await club_pricing(db, club_id=scope.club_id)
        sizes = await family_sizes(db, club_id=scope.club_id)
        await ensure_enrollment_fee(db, athlete=athlete, plan=plan, year=today.year, start_month=today.month)
        await ensure_monthly_fee(
            db, athlete=athlete, plan=plan, year=today.year, month=today.month, pricing=pricing,
            family_size=sizes.get(guardian_user_id, 1),
            course=course if rules.coach_paid_by_share else None,
        )
        await ensure_family_membership(
            db, scope=scope, guardian_user_id=guardian_user_id, on=today, pricing=pricing
        )

    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.athlete_created", entity_type="club_athlete", entity_id=str(athlete.id),
        new_value={
            "plan_id": str(athlete.plan_id) if athlete.plan_id else None, "is_self": is_self,
            "course_id": str(course.id) if course is not None else None,
        },
    )
    await db.commit()
    await db.refresh(athlete)
    return athlete


def give_starting_belt(db: AsyncSession, *, athlete: ClubAthlete, on: date, belt: str | None = None) -> None:
    """La cintura con cui un atleta entra in un club: la bianca, o quella
    dichiarata da chi arriva da un altro club. Non committa."""
    starting = belt or belts_catalog.STARTING_BELT
    db.add(ClubBeltGrade(
        **scope_of(athlete).columns(), athlete_id=athlete.id, grade=starting, awarded_on=on,
        awarded_by_user_id=None,
        note=None if starting == belts_catalog.STARTING_BELT else "Cintura dichiarata all'iscrizione",
    ))


#: Cosa il genitore può correggere da solo. Piano, stato e tesseramento li
#: decide la segreteria.
GUARDIAN_EDITABLE = {"first_name", "last_name", "birth_date", "sex", "fiscal_code", "weight_kg"}
ADMIN_EDITABLE = GUARDIAN_EDITABLE | {
    "plan_id", "plan_locked", "status", "federation_number", "federation_expires_on",
    # Gli sconti: li decide la segreteria dopo aver visto il documento.
    "social_tier", "adapted_judo",
}


async def update_athlete(
    db: AsyncSession, *, athlete: ClubAthlete, actor_user_id: uuid.UUID, changes: dict, as_admin: bool,
    today: date | None = None,
) -> ClubAthlete:
    today = today or utcnow().date()
    allowed = ADMIN_EDITABLE if as_admin else GUARDIAN_EDITABLE
    changes = {k: v for k, v in changes.items() if k in allowed}
    if "birth_date" in changes:
        _validate_birth_date(changes["birth_date"], today=today)
    if "sex" in changes and changes["sex"] not in ("M", "F"):
        raise ClubValidationError("Indica il sesso dell'atleta (M o F).")
    if "status" in changes and changes["status"] not in ATHLETE_STATUSES:
        raise ClubValidationError("Stato non valido.")
    if changes.get("social_tier") is not None and changes["social_tier"] not in SOCIAL_TIERS:
        raise ClubValidationError("L'escalão è A, B o C.")
    if "adapted_judo" in changes and changes["adapted_judo"] is None:
        changes["adapted_judo"] = False
    if "plan_id" in changes and changes["plan_id"] is not None:
        plan = await db.get(ClubPlan, changes["plan_id"])
        if plan is None or plan.club_id != athlete.club_id:
            raise ClubValidationError("Piano non trovato.")
        # Scegliere il piano a mano vuol dire che il ricalcolo per età non
        # lo deve più toccare, salvo che la segreteria lo sblocchi.
        changes.setdefault("plan_locked", True)
    if "fiscal_code" in changes:
        changes["fiscal_code"] = (changes["fiscal_code"] or "").strip().upper() or None

    previous = {k: str(getattr(athlete, k)) for k in changes}
    for key, value in changes.items():
        setattr(athlete, key, value)
    if changes.get("status") == "LEFT" and athlete.left_on is None:
        athlete.left_on = today
    elif changes.get("status") == "ACTIVE":
        athlete.left_on = None
    # Una data di nascita corretta, o un piano sbloccato, rimettono in
    # gioco il piano per età.
    if not athlete.plan_locked and ("birth_date" in changes or "plan_locked" in changes):
        await assign_plan(db, athlete=athlete, year=today.year)

    await audit_service.record(
        db, organization_id=athlete.organization_id, actor_user_id=actor_user_id,
        action="club.athlete_updated", entity_type="club_athlete", entity_id=str(athlete.id),
        previous_value=previous, new_value={k: str(v) for k, v in changes.items()},
    )
    await db.commit()
    await db.refresh(athlete)
    return athlete


async def set_athlete_photo(
    db: AsyncSession, *, athlete: ClubAthlete, file_bytes: bytes, content_type: str, actor_user_id: uuid.UUID
) -> ClubAthlete:
    from app.core.storage import UploadValidationError, upload_media

    try:
        athlete.photo_url = upload_media(
            file_bytes=file_bytes, content_type=content_type, key_prefix=f"club-athletes/{athlete.id}"
        )
    except UploadValidationError as exc:
        raise ClubValidationError("La foto deve essere un'immagine JPG, PNG o WebP di massimo 5 MB.") from exc
    await audit_service.record(
        db, organization_id=athlete.organization_id, actor_user_id=actor_user_id,
        action="club.athlete_photo_updated", entity_type="club_athlete", entity_id=str(athlete.id),
    )
    await db.commit()
    await db.refresh(athlete)
    return athlete


async def search_athletes(
    db: AsyncSession, *, scope: ClubScope, status: str | None = None, plan_id: uuid.UUID | None = None,
    q: str | None = None, limit: int = 500, course_id: uuid.UUID | None = None,
) -> list[ClubAthlete]:
    stmt = select(ClubAthlete).where(ClubAthlete.club_id == scope.club_id)
    if course_id:
        stmt = stmt.where(
            ClubAthlete.id.in_(select(ClubCourseAthlete.athlete_id).where(ClubCourseAthlete.course_id == course_id))
        )
    if status:
        stmt = stmt.where(ClubAthlete.status == status)
    if plan_id:
        stmt = stmt.where(ClubAthlete.plan_id == plan_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            (ClubAthlete.first_name.ilike(like)) | (ClubAthlete.last_name.ilike(like))
            | (func.concat(ClubAthlete.first_name, " ", ClubAthlete.last_name).ilike(like))
        )
    return list((await db.execute(stmt.order_by(ClubAthlete.last_name, ClubAthlete.first_name).limit(limit))).scalars())


# --- Quote ----------------------------------------------------------------------------------------


async def _insert_fee(db: AsyncSession, **values) -> None:
    """INSERT ... ON CONFLICT DO NOTHING sul vincolo (atleta, tipo, periodo):
    la stessa quota chiesta due volte esiste una volta sola."""
    await db.execute(
        insert(ClubFee)
        .values(id=uuid.uuid4(), created_at=utcnow(), status="DUE", **values)
        .on_conflict_do_nothing(constraint="uq_club_fees_athlete_kind_period")
    )


def monthly_fee_due(athlete: ClubAthlete, plan: ClubPlan, *, year: int, month: int) -> bool:
    """Se per quel mese all'atleta tocca la quota. Un esente non ha
    mensilità: una quota da 0 € sarebbe solo rumore nel suo conto."""
    if athlete.status != "ACTIVE" or plan.monthly_fee_cents <= 0 or month not in (plan.billing_months or []):
        return False
    if athlete.exempt_monthly:
        return False
    first_of_month = date(year, month, 1)
    next_month = date(year + (month == 12), month % 12 + 1, 1)
    # Iscritto entro il mese, e non uscito prima che cominciasse.
    return athlete.joined_on < next_month and (athlete.left_on is None or athlete.left_on >= first_of_month)


async def club_pricing(db: AsyncSession, *, club_id: uuid.UUID) -> dict:
    return pricing_rules.get_pricing(await db.get(Club, club_id))


async def family_sizes(db: AsyncSession, *, club_id: uuid.UUID) -> dict[uuid.UUID, int]:
    """Quanti atleti attivi ha ogni famiglia del club: decide lo sconto
    famiglia. Una query sola per tutto il club."""
    rows = (
        await db.execute(
            select(ClubAthlete.guardian_user_id, func.count())
            .where(ClubAthlete.club_id == club_id, ClubAthlete.status == "ACTIVE")
            .group_by(ClubAthlete.guardian_user_id)
        )
    ).all()
    return dict(rows)


def course_attribution(course: ClubCourse | None) -> dict:
    """A chi va una mensilità dei corsi JAV: il corso, il suo treinador
    responsabile e la sua percentuale di quel momento. Si congela sulla
    quota come il prezzo (docs/club-portal.md, "Cursos JAV")."""
    if course is None:
        return {}
    pct = course.coach_share_pct if course.coach_share_pct is not None else kinds.DEFAULT_COACH_SHARE_PCT
    return {
        "course_id": course.id,
        "coach_user_id": course.instructor_user_id,
        # Senza un treinador responsabile non c'è nessuno a cui dare la sua parte.
        "coach_share_pct": pct if course.instructor_user_id is not None else None,
    }


async def primary_courses(db: AsyncSession, *, athlete_ids: list[uuid.UUID]) -> dict[uuid.UUID, ClubCourse]:
    """Il corso a cui si attribuisce la mensilità di ogni atleta dei corsi
    JAV: la mensilità è una sola anche per chi va a due corsi, e va al
    primo corso (attivo) a cui si è iscritto; a parità, all'id più basso,
    perché il risultato non dipenda dall'ordine delle righe."""
    if not athlete_ids:
        return {}
    rows = (
        await db.execute(
            select(ClubCourseAthlete.athlete_id, ClubCourse)
            .join(ClubCourse, ClubCourse.id == ClubCourseAthlete.course_id)
            .where(ClubCourseAthlete.athlete_id.in_(athlete_ids), ClubCourse.active.is_(True))
            .order_by(ClubCourseAthlete.created_at, ClubCourse.id)
        )
    ).all()
    out: dict[uuid.UUID, ClubCourse] = {}
    for athlete_id, course in rows:
        out.setdefault(athlete_id, course)
    return out


async def ensure_monthly_fee(
    db: AsyncSession, *, athlete: ClubAthlete, plan: ClubPlan, year: int, month: int, pricing: dict,
    family_size: int, course: ClubCourse | None = None,
) -> None:
    """La mensilità, con gli sconti di quel momento congelati sopra
    (pricing.py::monthly_price). `course` solo nei corsi JAV: il corso (e il
    suo treinador) a cui va la quota."""
    if not monthly_fee_due(athlete, plan, year=year, month=month):
        return
    price = pricing_rules.monthly_price(
        list_cents=plan.monthly_fee_cents, athlete=athlete, family_size=family_size, pricing=pricing
    )
    await _insert_fee(
        db, **scope_of(athlete).columns(), athlete_id=athlete.id, kind="MONTHLY",
        period=f"{year:04d}-{month:02d}",
        description=f"Quota di {seasons.month_label(year, month)}",
        due_date=date(year, month, plan.due_day), **price, **course_attribution(course),
    )


async def ensure_enrollment_fee(
    db: AsyncSession, *, athlete: ClubAthlete, plan: ClubPlan, year: int, start_month: int = 1,
) -> None:
    """L'iscrizione dell'anno solare, dal mese d'ingresso a dicembre. Senza
    sconti (pricing.py)."""
    if athlete.status != "ACTIVE" or plan.enrollment_fee_cents <= 0 or athlete.exempt_annual:
        return
    # Divisa in rate ("2026/1", "2026/2"): l'iscrizione dell'anno c'è già.
    if await _has_annual_fee(db, athlete_id=athlete.id, kind="ENROLLMENT", year=year):
        return
    amount = pricing_rules.prorated(plan.enrollment_fee_cents, start_month=start_month)
    await _insert_fee(
        db, **scope_of(athlete).columns(), athlete_id=athlete.id, kind="ENROLLMENT",
        period=str(year),
        description=f"Iscrizione {pricing_rules.period_label(year, start_month)}",
        **pricing_rules.annual_price(amount_cents=amount, athlete=athlete),
        due_date=max(date(year, start_month, plan.due_day), athlete.joined_on),
    )


async def _has_annual_fee(
    db: AsyncSession, *, kind: str, year: int, athlete_id: uuid.UUID | None = None,
    club_id: uuid.UUID | None = None, guardian_user_id: uuid.UUID | None = None,
) -> bool:
    """Se la quota annuale c'è già, intera o divisa in rate."""
    stmt = select(ClubFee.id).where(
        ClubFee.kind == kind, or_(ClubFee.period == str(year), ClubFee.period.like(f"{year}/%")),
    )
    if athlete_id is not None:
        stmt = stmt.where(ClubFee.athlete_id == athlete_id)
    else:
        stmt = stmt.where(ClubFee.club_id == club_id, ClubFee.guardian_user_id == guardian_user_id)
    return (await db.execute(stmt.limit(1))).first() is not None


async def ensure_membership_fee(
    db: AsyncSession, *, scope: ClubScope, guardian_user_id: uuid.UUID, year: int, start_month: int,
    pricing: dict, due_day: int = 10,
) -> None:
    """La quota socio del genitore, una per famiglia e per anno. Chi chiama
    ha già deciso che serve (pricing.py::needs_parent_membership)."""
    amount = pricing_rules.prorated(pricing["parent_member_fee_cents"], start_month=start_month)
    if amount <= 0:
        return
    if await _has_annual_fee(
        db, kind="MEMBERSHIP", year=year, club_id=scope.club_id, guardian_user_id=guardian_user_id,
    ):
        return
    await db.execute(
        insert(ClubFee)
        .values(
            id=uuid.uuid4(), created_at=utcnow(), status="DUE", **scope.columns(), athlete_id=None,
            guardian_user_id=guardian_user_id, kind="MEMBERSHIP", period=str(year),
            description=f"Quota socio genitore {pricing_rules.period_label(year, start_month)}",
            amount_cents=amount, gross_amount_cents=amount, due_date=date(year, start_month, due_day),
        )
        .on_conflict_do_nothing(
            index_elements=["club_id", "guardian_user_id", "period"], index_where=text("kind = 'MEMBERSHIP'")
        )
    )


async def ensure_family_membership(
    db: AsyncSession, *, scope: ClubScope, guardian_user_id: uuid.UUID, on: date, pricing: dict,
) -> None:
    athletes = (
        await db.execute(
            select(ClubAthlete).where(
                ClubAthlete.club_id == scope.club_id, ClubAthlete.guardian_user_id == guardian_user_id
            )
        )
    ).scalars().all()
    if pricing_rules.needs_parent_membership(list(athletes), on=on):
        await ensure_membership_fee(
            db, scope=scope, guardian_user_id=guardian_user_id, year=on.year, start_month=on.month, pricing=pricing,
        )


async def generate_monthly_fees(
    db: AsyncSession, *, scope: ClubScope, period: str, today: date | None = None,
) -> int:
    """Le quote del mese per ogni atleta attivo. Idempotente: rilanciarla
    non crea doppioni (vincolo UNIQUE). Restituisce quante quote ha creato.

    Il gruppo di ogni mese lo decide l'età federale di quell'anno
    (seasons.federal_age), salvo i piani scelti a mano: a gennaio chi entra
    nella fascia del gruppo dopo paga già la mensilità del gruppo nuovo, e il
    genitore riceve un avviso. Il piano dell'atleta segue solo il mese in
    corso o uno futuro: rigenerare un mese passato non lo riporta indietro."""
    try:
        year, month = seasons.parse_period(period)
    except ValueError as exc:
        raise ClubValidationError("Il mese deve essere nel formato AAAA-MM.") from exc
    today = today or utcnow().date()
    plans = {p.id: p for p in await list_plans(db, scope=scope)}
    active_plans = [p for p in plans.values() if p.active]
    pricing = await club_pricing(db, club_id=scope.club_id)
    sizes = await family_sizes(db, club_id=scope.club_id)
    athletes = (
        await db.execute(
            select(ClubAthlete).where(ClubAthlete.club_id == scope.club_id, ClubAthlete.status == "ACTIVE")
        )
    ).scalars().all()
    before = await _count_fees(db, scope=scope, kind="MONTHLY", period=period)
    courses = (
        await primary_courses(db, athlete_ids=[a.id for a in athletes])
        if (await kinds.club_rules(db, club_id=scope.club_id)).coach_paid_by_share else {}
    )
    follows_plan = period >= seasons.period_of(today)
    moved: list[tuple[ClubAthlete, ClubPlan]] = []
    for athlete in athletes:
        current = plans.get(athlete.plan_id) if athlete.plan_id else None
        plan = current
        if not athlete.plan_locked:
            # Se nessun piano copre la nuova età si resta dove si era: meglio
            # la mensilità di prima che nessuna.
            plan = pick_plan(active_plans, age=seasons.federal_age(athlete.birth_date, year)) or current
        if plan is None:
            continue
        if follows_plan and plan is not current:
            athlete.plan_id = plan.id
            if current is not None:
                moved.append((athlete, plan))
        await ensure_monthly_fee(
            db, athlete=athlete, plan=plan, year=year, month=month, pricing=pricing,
            family_size=sizes.get(athlete.guardian_user_id, 1), course=courses.get(athlete.id),
        )
    for athlete, plan in moved:
        await notifications_service.notify_user(
            db, organization_id=scope.organization_id, user_id=athlete.guardian_user_id,
            type_="CLUB_PLAN_CHANGED", entity_type="club_athlete", entity_id=athlete.id,
            title=f"{athlete.first_name} passa al gruppo «{plan.name}»",
            body=(
                f"Da {seasons.month_label(year, month)} {athlete.first_name} ha "
                f"{seasons.federal_age(athlete.birth_date, year)} anni federali: la mensilità del nuovo gruppo "
                f"è di {plan.monthly_fee_cents / 100:.2f} € (prima degli sconti)."
            ),
        )
    await db.commit()
    return await _count_fees(db, scope=scope, kind="MONTHLY", period=period) - before


async def start_season(db: AsyncSession, *, scope: ClubScope, season: int) -> int:
    """Inizio stagione (1° settembre): ricalcola i piani per età, salvo
    quelli scelti a mano. Le iscrizioni seguono l'anno solare (start_year).
    Restituisce quanti atleti hanno cambiato piano."""
    athletes = (
        await db.execute(
            select(ClubAthlete).where(ClubAthlete.club_id == scope.club_id, ClubAthlete.status == "ACTIVE")
        )
    ).scalars().all()
    changed = 0
    for athlete in athletes:
        before = athlete.plan_id
        await assign_plan(db, athlete=athlete, year=season)
        changed += athlete.plan_id != before
    await db.commit()
    return changed


async def start_year(db: AsyncSession, *, scope: ClubScope, year: int) -> int:
    """1° gennaio: l'iscrizione dell'anno di ogni atleta attivo e la quota
    socio dei genitori che la devono. Idempotente. Restituisce quante quote
    ha creato."""
    plans = {p.id: p for p in await list_plans(db, scope=scope)}
    pricing = await club_pricing(db, club_id=scope.club_id)
    athletes = (
        await db.execute(
            select(ClubAthlete).where(ClubAthlete.club_id == scope.club_id, ClubAthlete.status == "ACTIVE")
        )
    ).scalars().all()
    before = await _count_year_fees(db, scope=scope, year=year)
    by_family: dict[uuid.UUID, list[ClubAthlete]] = {}
    for athlete in athletes:
        by_family.setdefault(athlete.guardian_user_id, []).append(athlete)
        if athlete.plan_id in plans:
            await ensure_enrollment_fee(db, athlete=athlete, plan=plans[athlete.plan_id], year=year)
    for guardian_id, family in by_family.items():
        if pricing_rules.needs_parent_membership(family, on=date(year, 1, 1)):
            await ensure_membership_fee(
                db, scope=scope, guardian_user_id=guardian_id, year=year, start_month=1, pricing=pricing
            )
    await db.commit()
    return await _count_year_fees(db, scope=scope, year=year) - before


async def _count_year_fees(db: AsyncSession, *, scope: ClubScope, year: int) -> int:
    return (
        await db.execute(
            select(func.count()).where(
                ClubFee.club_id == scope.club_id, ClubFee.kind.in_(("ENROLLMENT", "MEMBERSHIP")),
                ClubFee.period == str(year),
            )
        )
    ).scalar_one()


async def _count_fees(db: AsyncSession, *, scope: ClubScope, kind: str, period: str) -> int:
    return (
        await db.execute(
            select(func.count()).where(
                ClubFee.club_id == scope.club_id, ClubFee.kind == kind, ClubFee.period == period
            )
        )
    ).scalar_one()


async def list_fees(
    db: AsyncSession, *, scope: ClubScope, athlete_ids: list[uuid.UUID] | None = None,
    guardian_user_id: uuid.UUID | None = None,
    status: str | None = None, kind: str | None = None, period: str | None = None, limit: int = 1000,
    course: uuid.UUID | str | None = None,
) -> list[ClubFee]:
    """`athlete_ids` le quote di quegli atleti; con `guardian_user_id` anche
    la quota socio di quel genitore, che non è di nessun atleta. `course`
    (corsi JAV): le quote attribuite a quel corso, o "none" le mensilità
    senza corso."""
    stmt = select(ClubFee).where(ClubFee.club_id == scope.club_id)
    if course == "none":
        stmt = stmt.where(ClubFee.course_id.is_(None), ClubFee.kind == "MONTHLY")
    elif course is not None:
        stmt = stmt.where(ClubFee.course_id == course)
    if athlete_ids is not None and guardian_user_id is not None:
        stmt = stmt.where(ClubFee.athlete_id.in_(athlete_ids) | (ClubFee.guardian_user_id == guardian_user_id))
    elif athlete_ids is not None:
        stmt = stmt.where(ClubFee.athlete_id.in_(athlete_ids))
    if status:
        stmt = stmt.where(ClubFee.status == status)
    if kind:
        stmt = stmt.where(ClubFee.kind == kind)
    if period:
        stmt = stmt.where(ClubFee.period == period)
    return list((await db.execute(stmt.order_by(ClubFee.due_date, ClubFee.created_at).limit(limit))).scalars())


async def _get_fee(db: AsyncSession, *, scope: ClubScope, fee_id: uuid.UUID) -> ClubFee:
    fee = await db.get(ClubFee, fee_id)
    if fee is None or fee.club_id != scope.club_id:
        raise ClubNotFoundError("Quota non trovata.")
    return fee


async def waive_fee(
    db: AsyncSession, *, scope: ClubScope, fee_id: uuid.UUID, actor_user_id: uuid.UUID, reason: str
) -> ClubFee:
    fee = await _get_fee(db, scope=scope, fee_id=fee_id)
    if fee.status != "DUE":
        raise ClubValidationError("Si può condonare solo una quota ancora da pagare.")
    fee.status = "WAIVED"
    fee.waived_by_user_id = actor_user_id
    fee.waived_at = utcnow()
    fee.waive_reason = reason
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.fee_waived", entity_type="club_fee", entity_id=str(fee.id), reason=reason,
    )
    await db.commit()
    await db.refresh(fee)
    return fee


async def cash_receivers(db: AsyncSession, *, scope: ClubScope) -> list[dict]:
    """Chi nel club può ricevere contanti: la segreteria e gli istruttori
    attivi, con il nome da mostrare a un genitore."""
    from app.domains.club.clubs import CLUB_STAFF_ROLES
    from app.domains.club.people import _names
    from app.domains.rbac.models import Role, UserRole

    ids = set(
        (
            await db.execute(
                select(User.id)
                .join(UserRole, UserRole.user_id == User.id)
                .join(Role, Role.id == UserRole.role_id)
                .where(User.club_id == scope.club_id, Role.code.in_(CLUB_STAFF_ROLES), User.status == "ACTIVE")
            )
        ).scalars()
    )
    names = await _names(db, ids)
    return sorted(({"user_id": uid, "name": names.get(uid, "")} for uid in ids), key=lambda r: r["name"].lower())


async def _cash_receiver(
    db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID | None, name: str | None,
) -> tuple[uuid.UUID | None, str]:
    """(account, nome congelato) di chi ha preso i contanti: una persona
    dello staff del club, oppure un nome scritto a mano (un allenatore senza
    account, il presidente)."""
    if user_id is not None:
        match = next((r for r in await cash_receivers(db, scope=scope) if r["user_id"] == user_id), None)
        if match is None:
            raise ClubValidationError("Questa persona non fa parte dello staff del club.")
        return user_id, match["name"][:120]
    name = (name or "").strip()
    if len(name) < 2:
        raise ClubValidationError("Scrivi a chi sono stati consegnati i contanti.")
    return None, name[:120]


async def mark_fee_paid(
    db: AsyncSession, *, scope: ClubScope, fee_id: uuid.UUID, actor_user_id: uuid.UUID, note: str | None,
    method: str, cash_received_by_user_id: uuid.UUID | None = None,
    cash_received_by_name: str | None = None,
) -> ClubFee:
    """Pagata fuori dal portale: la segreteria la segna a mano e dice come
    (bonifico arrivato in banca, contanti e a chi, carta al POS)."""
    if method not in ("BANK_TRANSFER", "MBWAY", "CASH", "CARD"):
        raise ClubValidationError("Scegli come è stata pagata: bonifico, MB Way, contanti o carta.")
    receiver_id, receiver_name = (None, None)
    if method == "CASH":
        receiver_id, receiver_name = await _cash_receiver(
            db, scope=scope, user_id=cash_received_by_user_id, name=cash_received_by_name
        )
    fee = await _get_fee(db, scope=scope, fee_id=fee_id)
    if fee.status != "DUE":
        raise ClubValidationError("Questa quota non è da pagare.")
    fee.status = "PAID"
    fee.paid_at = utcnow()
    fee.paid_by_user_id = actor_user_id
    fee.payment_note = note
    fee.payment_method = method
    fee.cash_received_by_user_id = receiver_id
    fee.cash_received_by_name = receiver_name
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.fee_marked_paid", entity_type="club_fee", entity_id=str(fee.id), reason=note,
        new_value={"method": method, "cash_received_by": receiver_name},
    )
    await db.commit()
    await db.refresh(fee)
    await referrals.on_fee_paid(db, fee=fee)
    return fee


def _clear_payment(fee: ClubFee) -> None:
    fee.paid_at = fee.paid_by_user_id = fee.payment_note = None
    fee.paid_via_proof_id = None
    fee.payment_method = fee.cash_received_by_user_id = fee.cash_received_by_name = None


async def reopen_fee(db: AsyncSession, *, scope: ClubScope, fee_id: uuid.UUID, actor_user_id: uuid.UUID) -> ClubFee:
    """Annulla un condono o un "pagata a mano" sbagliato. Una quota pagata
    con una prova si riapre rifiutando la prova, non da qui: la prova copre
    anche altre quote."""
    fee = await _get_fee(db, scope=scope, fee_id=fee_id)
    if fee.status == "DUE":
        raise ClubValidationError("La quota è già da pagare.")
    if fee.paid_via_proof_id is not None:
        raise ClubValidationError("Questa quota è stata pagata con una prova di pagamento: rifiuta la prova.")
    was_paid = fee.status == "PAID"
    fee.status = "DUE"
    _clear_payment(fee)
    fee.waived_at = fee.waived_by_user_id = fee.waive_reason = None
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.fee_reopened", entity_type="club_fee", entity_id=str(fee.id),
    )
    await db.commit()
    await db.refresh(fee)
    if was_paid:
        await referrals.on_fee_unpaid(db, fee=fee, actor_user_id=actor_user_id)
    return fee


# --- Prove di pagamento ---------------------------------------------------------------------------


async def upload_payment_proof(
    db: AsyncSession,
    *,
    scope: ClubScope,
    guardian_user_id: uuid.UUID,
    fee_ids: list[uuid.UUID],
    file_bytes: bytes | None,
    content_type: str | None,
    original_filename: str | None,
    note: str | None = None,
    credit_cents: int = 0,
    spend_code: str | None = None,
    method: str = "BANK_TRANSFER",
    cash_received_by_user_id: uuid.UUID | None = None,
    cash_received_by_name: str | None = None,
) -> ClubPaymentProof:
    """Il genitore carica la foto del pagamento e indica cosa copre. Le
    quote risultano pagate subito: è la regola di autogestione
    (docs/club-portal.md). La segreteria può rifiutarla dopo.

    Con `method="CASH"` non c'è una foto: il genitore dice a chi ha dato i
    contanti, e quella persona riceve un avviso (se non li ha avuti, la
    segreteria rifiuta la prova come ogni altra).

    `credit_cents` è la parte pagata con il credito del wallet (sconti
    invito): si conferma con il PIN o il codice via email, come ogni spesa
    di JavCash. Se il credito copre tutto, la foto non serve."""
    from app.core.storage import UploadValidationError
    from app.core.storage import upload_document as storage_upload_document
    from app.domains.auth import service as auth_service
    from app.domains.wallets import service as wallets_service

    fee_ids = list(dict.fromkeys(fee_ids))
    if not fee_ids:
        raise ClubValidationError("Scegli almeno una quota da pagare.")
    if method not in ("BANK_TRANSFER", "MBWAY", "CASH"):
        raise ClubValidationError("Scegli come hai pagato: bonifico, MB Way o contanti.")
    receiver_id, receiver_name = (None, None)
    if method == "CASH":
        if credit_cents:
            raise ClubValidationError("Il credito del wallet non si usa insieme ai contanti.")
        receiver_id, receiver_name = await _cash_receiver(
            db, scope=scope, user_id=cash_received_by_user_id, name=cash_received_by_name
        )
        file_bytes = None
    rows = (
        await db.execute(
            select(ClubFee, ClubAthlete)
            .outerjoin(ClubAthlete, ClubAthlete.id == ClubFee.athlete_id)
            .where(ClubFee.id.in_(fee_ids), ClubFee.club_id == scope.club_id)
            .with_for_update(of=ClubFee)
        )
    ).all()

    def _mine(fee: ClubFee, athlete: ClubAthlete | None) -> bool:
        return (athlete.guardian_user_id if athlete is not None else fee.guardian_user_id) == guardian_user_id

    if len(rows) != len(fee_ids) or not all(_mine(f, a) for f, a in rows):
        raise ClubNotFoundError("Quota non trovata.")
    not_due = [f for f, _a in rows if f.status != "DUE"]
    if not_due:
        raise ClubValidationError(f"«{not_due[0].description}» non è più da pagare: aggiorna la pagina.")

    total = sum(f.amount_cents for f, _a in rows)
    if credit_cents < 0 or credit_cents > total:
        raise ClubValidationError("Il credito da usare non può superare il totale delle quote.")
    wallet = None
    if credit_cents:
        wallet = await wallets_service.get_wallet_by_user_id(
            db, organization_id=scope.organization_id, user_id=guardian_user_id
        )
        if wallet is None or wallet.balance_cents < credit_cents:
            raise ClubValidationError("Nel tuo wallet non c'è abbastanza credito: aggiorna la pagina.")
        if not spend_code or not await auth_service.verify_spend_code(db, user_id=guardian_user_id, code=spend_code):
            raise ClubValidationError("Il codice di conferma non è corretto o è scaduto.")

    storage_key = None
    if file_bytes:
        try:
            storage_key = storage_upload_document(
                file_bytes=file_bytes, content_type=content_type or "",
                key_prefix=f"club-payment-proofs/{guardian_user_id}",
            )
        except UploadValidationError as exc:
            raise ClubValidationError("Carica una foto (JPG o PNG) o un PDF, di massimo 15 MB.") from exc
    elif credit_cents < total and method != "CASH":
        raise ClubValidationError(
            "Carica la foto o il PDF della conferma MB Way." if method == "MBWAY"
            else "Carica la foto o il PDF della ricevuta del bonifico."
        )

    proof = ClubPaymentProof(
        **scope.columns(),
        uploaded_by_user_id=guardian_user_id,
        storage_key=storage_key,
        original_filename=(original_filename or "pagamento")[:255] if storage_key else None,
        content_type=content_type if storage_key else None,
        amount_cents=total,
        credit_cents=credit_cents,
        note=note,
        status="ACCEPTED",
        method=method,
        cash_received_by_user_id=receiver_id,
        cash_received_by_name=receiver_name,
        receipt_number=await receipts.next_number(
            db, club_id=scope.club_id, prefix=receipts.prefix_for([f.kind for f, _a in rows]),
            year=utcnow().year,
        ),
    )
    db.add(proof)
    await db.flush()
    now = utcnow()
    for fee, _athlete in rows:
        db.add(ClubPaymentProofFee(proof_id=proof.id, fee_id=fee.id))
        fee.status = "PAID"
        fee.paid_at = now
        fee.paid_via_proof_id = proof.id
        fee.paid_by_user_id = guardian_user_id
        fee.payment_method = "WALLET" if credit_cents == total and total > 0 else method
        fee.cash_received_by_user_id = receiver_id
        fee.cash_received_by_name = receiver_name
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=guardian_user_id,
        action="club.payment_proof_uploaded", entity_type="club_payment_proof", entity_id=str(proof.id),
        new_value={
            "fee_ids": [str(f) for f in fee_ids], "amount_cents": total, "credit_cents": credit_cents,
            "method": method, "cash_received_by": receiver_name,
        },
    )
    if receiver_id is not None:
        await notifications_service.notify_user(
            db, organization_id=scope.organization_id, user_id=receiver_id, type_="CLUB_CASH_DECLARED",
            entity_type="club_payment_proof", entity_id=proof.id,
            title=f"Contanti consegnati a te: {total / 100:.2f} €",
            body=(
                ", ".join(f"{a.first_name if a else 'Quota socio'}: {f.description}" for f, a in rows)[:400]
                + ". Se non li hai ricevuti, avvisa la segreteria."
            ),
        )
    if wallet is not None:
        # L'addebito committa tutto insieme: prova, quote pagate, credito
        # scalato. Se il saldo nel frattempo non basta, non resta niente.
        try:
            await wallets_service.debit_wallet_for_club_fees(
                db, organization_id=scope.organization_id, wallet_id=wallet.id, amount_cents=credit_cents,
                reference_club_proof_id=proof.id, actor_user_id=guardian_user_id,
                note=", ".join(f.description for f, _a in rows)[:500],
                idempotency_key=f"club-proof-credit:{proof.id}",
            )
        except wallets_service.InsufficientBalanceError as exc:
            await db.rollback()
            raise ClubValidationError("Nel tuo wallet non c'è abbastanza credito: aggiorna la pagina.") from exc
    else:
        await db.commit()
    await db.refresh(proof)
    for fee, _athlete in rows:
        await referrals.on_fee_paid(db, fee=fee)
    return proof


async def get_proof(db: AsyncSession, *, scope: ClubScope, proof_id: uuid.UUID) -> ClubPaymentProof:
    proof = await db.get(ClubPaymentProof, proof_id)
    if proof is None or proof.club_id != scope.club_id:
        raise ClubNotFoundError("Prova di pagamento non trovata.")
    return proof


async def list_proofs(
    db: AsyncSession, *, scope: ClubScope, uploaded_by_user_id: uuid.UUID | None = None,
    status: str | None = None, limit: int = 500,
) -> list[ClubPaymentProof]:
    stmt = select(ClubPaymentProof).where(ClubPaymentProof.club_id == scope.club_id)
    if uploaded_by_user_id is not None:
        stmt = stmt.where(ClubPaymentProof.uploaded_by_user_id == uploaded_by_user_id)
    if status:
        stmt = stmt.where(ClubPaymentProof.status == status)
    return list((await db.execute(stmt.order_by(ClubPaymentProof.created_at.desc()).limit(limit))).scalars())


async def fees_by_proof(db: AsyncSession, *, proof_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[ClubFee]]:
    if not proof_ids:
        return {}
    rows = (
        await db.execute(
            select(ClubPaymentProofFee.proof_id, ClubFee)
            .join(ClubFee, ClubFee.id == ClubPaymentProofFee.fee_id)
            .where(ClubPaymentProofFee.proof_id.in_(proof_ids))
            .order_by(ClubFee.due_date)
        )
    ).all()
    out: dict[uuid.UUID, list[ClubFee]] = {pid: [] for pid in proof_ids}
    for proof_id, fee in rows:
        out[proof_id].append(fee)
    return out


async def reject_proof(
    db: AsyncSession, *, scope: ClubScope, proof_id: uuid.UUID, actor_user_id: uuid.UUID, reason: str
) -> ClubPaymentProof:
    """La segreteria rifiuta una prova: le quote che aveva pagato tornano da
    pagare, e il genitore lo sa subito, con il motivo."""
    proof = await get_proof(db, scope=scope, proof_id=proof_id)
    if proof.status == "REJECTED":
        raise ClubValidationError("Questa prova è già stata rifiutata.")
    proof.status = "REJECTED"
    proof.reviewed_by_user_id = actor_user_id
    proof.reviewed_at = utcnow()
    proof.rejection_reason = reason
    reopened = (
        await db.execute(select(ClubFee).where(ClubFee.paid_via_proof_id == proof.id).with_for_update())
    ).scalars().all()
    for fee in reopened:
        fee.status = "DUE"
        _clear_payment(fee)
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.payment_proof_rejected", entity_type="club_payment_proof", entity_id=str(proof.id),
        reason=reason, new_value={"reopened_fee_ids": [str(f.id) for f in reopened]},
    )
    if proof.credit_cents:
        await _refund_proof_credit(db, scope=scope, proof=proof, actor_user_id=actor_user_id)
    for fee in reopened:
        await referrals.on_fee_unpaid(db, fee=fee, actor_user_id=actor_user_id)
    descriptions = ", ".join(f.description for f in reopened) or "le quote indicate"
    await notifications_service.notify_user(
        db, organization_id=scope.organization_id, user_id=proof.uploaded_by_user_id, type_="CLUB_PROOF_REJECTED",
        entity_type="club_payment_proof", entity_id=proof.id,
        title="Una prova di pagamento non è stata accettata",
        body=f"{descriptions}: {reason}",
    )
    await db.commit()
    await db.refresh(proof)
    await email_guardian(
        db, user_id=proof.uploaded_by_user_id, context="club proof rejected",
        subject="Prova di pagamento non accettata",
        heading="Prova di pagamento non accettata",
        lines=[
            f"La segreteria non ha potuto accettare la prova di pagamento per: <strong>{escape(descriptions)}</strong>.",
            f"Motivo: {escape(reason)}",
            "Le quote risultano di nuovo da pagare: puoi caricare una nuova prova dal portale.",
        ],
    )
    return proof


async def _refund_proof_credit(
    db: AsyncSession, *, scope: ClubScope, proof: ClubPaymentProof, actor_user_id: uuid.UUID
) -> None:
    """Il credito usato con una prova rifiutata torna nel wallet: le quote
    tornano da pagare, e il genitore non deve perdere lo sconto."""
    from app.domains.wallets import service as wallets_service
    from app.domains.wallets.models import WalletTransaction

    debit = (
        await db.execute(
            select(WalletTransaction).where(
                WalletTransaction.reference_club_proof_id == proof.id, WalletTransaction.type == "PURCHASE_DEBIT"
            )
        )
    ).scalars().first()
    if debit is None:
        return
    await wallets_service.reverse_transaction(
        db, organization_id=scope.organization_id, transaction_id=debit.id, actor_user_id=actor_user_id,
        reason="Prova di pagamento non accettata: il credito torna nel wallet",
        idempotency_key=f"club-proof-refund:{proof.id}",
    )


def presigned_url(storage_key: str) -> str:
    from app.core.storage import generate_presigned_document_url

    return generate_presigned_document_url(storage_key=storage_key, expires_in_seconds=PRESIGNED_URL_TTL_SECONDS)


# --- Certificati medici ---------------------------------------------------------------------------


def certificate_status(cert: ClubMedicalCertificate | None, *, today: date) -> str:
    """MISSING / VALID / EXPIRING / EXPIRED."""
    if cert is None:
        return "MISSING"
    if cert.expires_on < today:
        return "EXPIRED"
    if cert.expires_on <= today + timedelta(days=CERTIFICATE_EXPIRING_DAYS):
        return "EXPIRING"
    return "VALID"


async def latest_certificates(db: AsyncSession, *, athlete_ids: list[uuid.UUID]) -> dict[uuid.UUID, ClubMedicalCertificate]:
    """Il certificato che scade per ultimo, per atleta: quello che conta."""
    if not athlete_ids:
        return {}
    rows = (
        await db.execute(
            select(ClubMedicalCertificate)
            .where(ClubMedicalCertificate.athlete_id.in_(athlete_ids))
            .order_by(ClubMedicalCertificate.expires_on.desc())
        )
    ).scalars().all()
    out: dict[uuid.UUID, ClubMedicalCertificate] = {}
    for cert in rows:
        out.setdefault(cert.athlete_id, cert)
    return out


async def has_valid_agonistic_certificate(db: AsyncSession, *, athlete_id: uuid.UUID, on: date) -> bool:
    found = (
        await db.execute(
            select(ClubMedicalCertificate.id).where(
                ClubMedicalCertificate.athlete_id == athlete_id,
                ClubMedicalCertificate.type == "AGONISTIC",
                ClubMedicalCertificate.issued_on <= on,
                ClubMedicalCertificate.expires_on >= on,
            ).limit(1)
        )
    ).first()
    return found is not None


async def list_certificates(db: AsyncSession, *, athlete_id: uuid.UUID) -> list[ClubMedicalCertificate]:
    return list(
        (
            await db.execute(
                select(ClubMedicalCertificate)
                .where(ClubMedicalCertificate.athlete_id == athlete_id)
                .order_by(ClubMedicalCertificate.expires_on.desc())
            )
        ).scalars()
    )


async def upload_certificate(
    db: AsyncSession,
    *,
    athlete: ClubAthlete,
    actor_user_id: uuid.UUID,
    type_: str,
    issued_on: date,
    expires_on: date,
    file_bytes: bytes,
    content_type: str,
    original_filename: str,
) -> ClubMedicalCertificate:
    from app.core.storage import UploadValidationError
    from app.core.storage import upload_document as storage_upload_document

    if type_ not in CERTIFICATE_TYPES:
        raise ClubValidationError("Indica se il certificato è agonistico o non agonistico.")
    if expires_on < issued_on:
        raise ClubValidationError("La scadenza non può essere prima della data di rilascio.")
    if expires_on > issued_on + timedelta(days=366 * 2):
        raise ClubValidationError("Controlla le date: un certificato medico sportivo dura al massimo due anni.")
    try:
        storage_key = storage_upload_document(
            file_bytes=file_bytes, content_type=content_type, key_prefix=f"club-certificates/{athlete.id}"
        )
    except UploadValidationError as exc:
        raise ClubValidationError("Carica una foto (JPG o PNG) o un PDF, di massimo 15 MB.") from exc
    cert = ClubMedicalCertificate(
        **scope_of(athlete).columns(), athlete_id=athlete.id, type=type_,
        issued_on=issued_on, expires_on=expires_on, storage_key=storage_key,
        original_filename=original_filename[:255], uploaded_by_user_id=actor_user_id,
    )
    db.add(cert)
    await db.flush()
    await audit_service.record(
        db, organization_id=athlete.organization_id, actor_user_id=actor_user_id,
        action="club.certificate_uploaded", entity_type="club_medical_certificate", entity_id=str(cert.id),
        new_value={"athlete_id": str(athlete.id), "type": type_, "expires_on": expires_on.isoformat()},
    )
    await db.commit()
    await db.refresh(cert)
    return cert


async def get_certificate(db: AsyncSession, *, scope: ClubScope, certificate_id: uuid.UUID) -> ClubMedicalCertificate:
    cert = await db.get(ClubMedicalCertificate, certificate_id)
    if cert is None or cert.club_id != scope.club_id:
        raise ClubNotFoundError("Certificato non trovato.")
    return cert


# --- Cinture --------------------------------------------------------------------------------------


async def current_belts(db: AsyncSession, *, athlete_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    """La cintura attuale di ogni atleta: la più alta dello storico."""
    if not athlete_ids:
        return {}
    rows = (
        await db.execute(
            select(ClubBeltGrade.athlete_id, ClubBeltGrade.grade).where(ClubBeltGrade.athlete_id.in_(athlete_ids))
        )
    ).all()
    out: dict[uuid.UUID, str] = {}
    for athlete_id, grade in rows:
        if athlete_id not in out or belts_catalog.rank(grade) > belts_catalog.rank(out[athlete_id]):
            out[athlete_id] = grade
    return out


async def belt_history(db: AsyncSession, *, athlete_id: uuid.UUID) -> list[ClubBeltGrade]:
    rows = list(
        (await db.execute(select(ClubBeltGrade).where(ClubBeltGrade.athlete_id == athlete_id))).scalars()
    )
    return sorted(rows, key=lambda g: belts_catalog.rank(g.grade))


async def award_belt(
    db: AsyncSession, *, athlete: ClubAthlete, grade: str, awarded_on: date, actor_user_id: uuid.UUID,
    note: str | None = None,
) -> ClubBeltGrade:
    """Un passaggio di grado: solo verso l'alto."""
    if not (await kinds.club_rules(db, club_id=athlete.club_id)).has_belts:
        raise ClubValidationError(kinds.NO_BELTS)
    if grade not in belts_catalog.BELT_CODES:
        raise ClubValidationError("Cintura non riconosciuta.")
    current = (await current_belts(db, athlete_ids=[athlete.id])).get(athlete.id)
    if current is not None and belts_catalog.rank(grade) <= belts_catalog.rank(current):
        raise ClubValidationError(
            f"{athlete.first_name} ha già la cintura {belts_catalog.get(current).label.lower()}: "
            "scegli un grado superiore."
        )
    row = ClubBeltGrade(
        **scope_of(athlete).columns(), athlete_id=athlete.id, grade=grade, awarded_on=awarded_on,
        awarded_by_user_id=actor_user_id, note=note,
    )
    db.add(row)
    await db.flush()
    label = belts_catalog.get(grade).label
    await audit_service.record(
        db, organization_id=athlete.organization_id, actor_user_id=actor_user_id,
        action="club.belt_awarded", entity_type="club_athlete", entity_id=str(athlete.id),
        previous_value={"grade": current}, new_value={"grade": grade},
    )
    await notifications_service.notify_user(
        db, organization_id=athlete.organization_id, user_id=athlete.guardian_user_id, type_="CLUB_BELT_AWARDED",
        entity_type="club_athlete", entity_id=athlete.id,
        title=f"{athlete.first_name} ha conquistato la cintura {label.lower()}!",
    )
    await db.commit()
    await db.refresh(row)
    return row


async def delete_belt(db: AsyncSession, *, scope: ClubScope, belt_id: uuid.UUID, actor_user_id: uuid.UUID) -> None:
    """Correzione di un passaggio inserito per errore. La cintura di
    partenza non si toglie: l'atleta resterebbe senza cintura."""
    row = await db.get(ClubBeltGrade, belt_id)
    if row is None or row.club_id != scope.club_id:
        raise ClubNotFoundError("Cintura non trovata.")
    remaining = (
        await db.execute(select(func.count()).where(ClubBeltGrade.athlete_id == row.athlete_id))
    ).scalar_one()
    if remaining <= 1:
        raise ClubValidationError("È l'unica cintura dell'atleta: non si può togliere.")
    await db.delete(row)
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.belt_deleted", entity_type="club_athlete", entity_id=str(row.athlete_id),
        previous_value={"grade": row.grade},
    )
    await db.commit()


# --- Email al genitore ----------------------------------------------------------------------------


async def email_guardian(
    db: AsyncSession, *, user_id: uuid.UUID, context: str, subject: str, heading: str, lines: list[str],
    cta_label: str = "Apri il portale",
) -> None:
    """Un'email al genitore, dopo il commit di ciò che annuncia. Non fa mai
    fallire l'operazione (send_html_email_best_effort). `lines` è markup già
    sicuro: chi chiama fa l'escape dei valori."""
    user = await db.get(User, user_id)
    if user is None:
        return
    base = get_settings().public_app_base_url
    html = render_email(
        preheader=subject, heading=heading,
        body_html="".join(f"<p>{line}</p>" for line in lines),
        cta_label=cta_label, cta_url=f"{base}/customer",
    )
    text = "\n\n".join(_strip_tags(line) for line in lines) + f"\n\n{base}/customer"
    send_html_email_best_effort(context=context, to=user.email, subject=subject, html_body=html, text_body=text)


def _strip_tags(markup: str) -> str:
    import re
    from html import unescape

    return unescape(re.sub(r"<[^>]+>", "", markup))
