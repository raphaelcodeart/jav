"""La pagina del genitore: tutto quello che serve in una risposta sola.

Il portale lo apre un genitore dal telefono: una chiamata, poche query in
blocco (mai una per figlio), e la risposta contiene già le frasi e i numeri
da mostrare. Le stesse funzioni servono la scheda atleta della segreteria.
"""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.club import achievements as achievements_catalog
from app.domains.club import belts as belts_catalog
from app.domains.club import competitions as competitions_service
from app.domains.club import courses as courses_service
from app.domains.club import month_board
from app.domains.club import months as months_service
from app.domains.club import seasons
from app.domains.club import service as club_service
from app.domains.club.models import (
    ClubAthlete,
    ClubBeltGrade,
    ClubCompetition,
    ClubCompetitionEntry,
    ClubFee,
    ClubPlan,
)
from app.domains.club.scope import ClubScope, scope_of


def belt_dict(code: str | None) -> dict | None:
    if code is None:
        return None
    belt = belts_catalog.get(code)
    return {"code": belt.code, "label": belt.label, "color": belt.color, "stripe": belt.stripe,
            "rank": belts_catalog.rank(belt.code)}


def fee_dict(fee: ClubFee, *, today: date, athlete: ClubAthlete | None = None) -> dict:
    return {
        "id": fee.id,
        "athlete_id": fee.athlete_id,
        "athlete_name": f"{athlete.first_name} {athlete.last_name}" if athlete else None,
        "kind": fee.kind,
        "period": fee.period,
        "description": fee.description,
        "amount_cents": fee.amount_cents,
        "gross_amount_cents": fee.gross_amount_cents,
        "discount_cents": fee.discount_cents or 0,
        "discount_note": fee.discount_note,
        "absence_adjustment": fee.absence_adjustment,
        "due_date": fee.due_date,
        "status": fee.status,
        "overdue": fee.status == "DUE" and fee.due_date < today,
        "paid_at": fee.paid_at,
        "paid_via_proof_id": fee.paid_via_proof_id,
        "payment_note": fee.payment_note,
        "payment_method": fee.payment_method,
        "cash_received_by_name": fee.cash_received_by_name,
        "waive_reason": fee.waive_reason,
        "competition_id": fee.competition_id,
        "course_id": fee.course_id,
        "waive_kind": fee.waive_kind,
        "split_from_fee_id": fee.split_from_fee_id,
        "split_reason": fee.split_reason,
        "non_blocking": bool(fee.non_blocking),
    }


def certificate_dict(cert, *, today: date) -> dict:
    return {
        "status": club_service.certificate_status(cert, today=today),
        "id": cert.id if cert else None,
        "type": cert.type if cert else None,
        "issued_on": cert.issued_on if cert else None,
        "expires_on": cert.expires_on if cert else None,
    }


async def athlete_cards(
    db: AsyncSession, *, athletes: list[ClubAthlete], today: date | None = None
) -> list[dict]:
    """La "figurina" di ogni atleta: piano, cintura, prossima quota,
    certificato, prossima gara, punti e livello. In blocco."""
    today = today or utcnow().date()
    ids = [a.id for a in athletes]
    season = seasons.season_of(today)
    plans = {
        p.id: p
        for p in (
            await db.execute(select(ClubPlan).where(ClubPlan.id.in_({a.plan_id for a in athletes if a.plan_id})))
        ).scalars()
    } if athletes else {}
    belts = await club_service.current_belts(db, athlete_ids=ids)
    belt_counts: dict[uuid.UUID, int] = {a: 0 for a in ids}
    if ids:
        for (athlete_id,) in (
            await db.execute(select(ClubBeltGrade.athlete_id).where(ClubBeltGrade.athlete_id.in_(ids)))
        ).all():
            belt_counts[athlete_id] += 1
    certs = await club_service.latest_certificates(db, athlete_ids=ids)
    due_fees = await club_service.list_fees(db, scope=scope_of(athletes[0]), athlete_ids=ids, status="DUE") if athletes else []
    # I punti "di adesso" sono quelli dell'anno del ranking (anno solare).
    season_points = await competitions_service.athlete_points(
        db, athlete_ids=ids, season=competitions_service.ranking_year(today))
    lifetime = await competitions_service.athlete_points(db, athlete_ids=ids)
    attendances = await courses_service.attendance_counts(db, athlete_ids=ids)
    from app.domains.club import obligations as obligations_service
    from app.domains.club.models import Club

    duties = await obligations_service.obligations(db, athletes=athletes, today=today)
    club_names = dict((await db.execute(select(Club.id, Club.name).where(Club.id.in_({a.club_id for a in athletes})))).all()) if athletes else {}

    upcoming: dict[uuid.UUID, dict] = {}
    if ids:
        rows = (
            await db.execute(
                select(ClubCompetitionEntry, ClubCompetition)
                .join(ClubCompetition, ClubCompetition.id == ClubCompetitionEntry.competition_id)
                .where(
                    ClubCompetitionEntry.athlete_id.in_(ids),
                    ClubCompetitionEntry.status == "REGISTERED",
                    ClubCompetition.ends_on >= today,
                )
                .order_by(ClubCompetition.starts_on)
            )
        ).all()
        for entry, comp in rows:
            upcoming.setdefault(entry.athlete_id, {
                "competition_id": comp.id, "name": comp.name, "starts_on": comp.starts_on,
                "location": comp.location, "category": entry.category,
            })

    cards = []
    for athlete in athletes:
        mine_due = [f for f in due_fees if f.athlete_id == athlete.id]
        plan = plans.get(athlete.plan_id) if athlete.plan_id else None
        belts_earned = max(belt_counts[athlete.id] - 1, 0)
        cards.append({
            "id": athlete.id,
            "first_name": athlete.first_name,
            "last_name": athlete.last_name,
            "birth_date": athlete.birth_date,
            "age": seasons.age_on(athlete.birth_date, today),
            "season_age": seasons.season_age(athlete.birth_date, season),
            # L'età che decide il gruppo: gli anni compiuti entro il 31 dicembre.
            "federal_age": seasons.federal_age(athlete.birth_date, today.year),
            "sex": athlete.sex,
            "photo_url": athlete.photo_url,
            "is_self": athlete.is_self,
            "status": athlete.status,
            "weight_kg": athlete.weight_kg,
            "fiscal_code": athlete.fiscal_code,
            "federation_number": athlete.federation_number,
            "federation_expires_on": athlete.federation_expires_on,
            "social_tier": athlete.social_tier,
            "adapted_judo": athlete.adapted_judo,
            "plan": {"id": plan.id, "name": plan.name, "monthly_fee_cents": plan.monthly_fee_cents} if plan else None,
            "plan_locked": athlete.plan_locked,
            "belt": belt_dict(belts.get(athlete.id)),
            "next_fee": fee_dict(mine_due[0], today=today) if mine_due else None,
            "due_cents": sum(f.amount_cents for f in mine_due),
            "overdue_count": sum(1 for f in mine_due if f.due_date < today),
            "certificate": certificate_dict(certs.get(athlete.id), today=today),
            "next_competition": upcoming.get(athlete.id),
            "ranking_points": season_points[athlete.id]["points"],
            "medals": {k: lifetime[athlete.id][k] for k in ("gold", "silver", "bronze")},
            "attendances": attendances[athlete.id],
            **achievements_catalog.experience(
                attendances=attendances[athlete.id], belts_earned=belts_earned,
                ranking_points=lifetime[athlete.id]["points"],
            ),
            "competitions_count": lifetime[athlete.id]["competitions"],
            "weight_category": athlete.weight_category,
            "age_band": competitions_service.age_band_for(
                competitions_service.ranking_age(athlete.birth_date, today.year)).code,
            "club_name": club_names.get(athlete.club_id),
            "white_judogi": athlete.white_judogi,
            "obligations": duties.get(athlete.id),
            "achievements_earned": sum(
                1 for a in achievements_catalog.achievements(
                    attendances=attendances[athlete.id], belts_earned=belts_earned,
                    current_belt=belts.get(athlete.id), totals=lifetime[athlete.id],
                ) if a["earned"]
            ),
        })
    return cards


async def family_summary(
    db: AsyncSession, *, scope: ClubScope, guardian_user_id: uuid.UUID, today: date | None = None
) -> dict:
    today = today or utcnow().date()
    season = seasons.season_of(today)
    athletes = await club_service.list_family_athletes(
        db, scope=scope, guardian_user_id=guardian_user_id
    )
    by_id = {a.id: a for a in athletes}
    cards = await athlete_cards(db, athletes=athletes, today=today)
    ids = list(by_id)
    # Anche la quota socio del genitore, che non è di nessun figlio.
    fees = await club_service.list_fees(db, scope=scope, athlete_ids=ids, guardian_user_id=guardian_user_id)
    due = [f for f in fees if f.status == "DUE"]
    in_season = [
        f for f in fees
        if f.status == "PAID" and f.paid_at is not None
        and seasons.season_start(season) <= f.paid_at.date() <= seasons.season_end(season)
    ]
    proofs = await club_service.list_proofs(
        db, scope=scope, uploaded_by_user_id=guardian_user_id, limit=5
    )
    proof_fees = await club_service.fees_by_proof(db, proof_ids=[p.id for p in proofs])
    open_competitions = await competitions_service.list_competitions(
        db, scope=scope, status="OPEN", from_date=today
    )
    # Le mensilità della stagione di ogni atleta, per il grafico della
    # famiglia: dalle quote già lette, nessuna query in più.
    season_periods = {f"{y:04d}-{m:02d}" for y, m in months_service.season_periods(season)}
    by_athlete = {
        a.id: {"athlete_id": a.id, "first_name": a.first_name, "paid_cents": 0, "due_cents": 0,
               "overdue_cents": 0, "months_paid": 0, "months_due": 0, "months_overdue": 0}
        for a in athletes
    }
    for f in fees:
        row = by_athlete.get(f.athlete_id)
        if row is None or f.kind != "MONTHLY" or f.period not in season_periods:
            continue
        if f.status == "PAID":
            row["paid_cents"] += f.amount_cents
            row["months_paid"] += 1
        elif f.status == "DUE" and f.due_date < today:
            row["overdue_cents"] += f.amount_cents
            row["months_overdue"] += 1
        elif f.status == "DUE":
            row["due_cents"] += f.amount_cents
            row["months_due"] += 1
    return {
        "season": season,
        "season_label": seasons.season_label(season),
        "athletes": cards,
        "due_fees": [fee_dict(f, today=today, athlete=by_id.get(f.athlete_id)) for f in due],
        "due_cents": sum(f.amount_cents for f in due),
        "overdue_cents": sum(f.amount_cents for f in due if f.due_date < today),
        "paid_season_cents": sum(f.amount_cents for f in in_season),
        "recent_proofs": [proof_dict(p, fees=proof_fees.get(p.id, []), today=today) for p in proofs],
        "open_competitions": len([c for c in open_competitions if c.registration_deadline >= today]),
        "season_months": list(by_athlete.values()),
        "this_month": await month_board.family_month(db, scope=scope, athletes=athletes, today=today),
    }


def proof_dict(proof, *, fees: list[ClubFee], today: date) -> dict:
    return {
        "id": proof.id,
        "created_at": proof.created_at,
        "amount_cents": proof.amount_cents,
        "credit_cents": proof.credit_cents or 0,
        "status": proof.status,
        "note": proof.note,
        "original_filename": proof.original_filename,
        "rejection_reason": proof.rejection_reason,
        "reviewed_at": proof.reviewed_at,
        "uploaded_by_user_id": proof.uploaded_by_user_id,
        "method": proof.method,
        "cash_received_by_name": proof.cash_received_by_name,
        "receipt_number": proof.receipt_number,
        "paid_on": proof.paid_on,
        "fees": [fee_dict(f, today=today) for f in fees],
    }


async def athlete_detail(db: AsyncSession, *, athlete: ClubAthlete, today: date | None = None) -> dict:
    """La scheda completa: la card, più storico cinture, certificati, quote,
    gare e medaglie."""
    today = today or utcnow().date()
    card = (await athlete_cards(db, athletes=[athlete], today=today))[0]
    history = await club_service.belt_history(db, athlete_id=athlete.id)
    certs = await club_service.list_certificates(db, athlete_id=athlete.id)
    fees = await club_service.list_fees(db, scope=scope_of(athlete), athlete_ids=[athlete.id])
    lifetime = (await competitions_service.athlete_points(db, athlete_ids=[athlete.id]))[athlete.id]
    entries = (
        await db.execute(
            select(ClubCompetitionEntry, ClubCompetition)
            .join(ClubCompetition, ClubCompetition.id == ClubCompetitionEntry.competition_id)
            .where(ClubCompetitionEntry.athlete_id == athlete.id)
            .order_by(ClubCompetition.starts_on.desc())
        )
    ).all()
    current = history[-1].grade if history else None
    return {
        **card,
        "belt_history": [
            {"id": g.id, **belt_dict(g.grade), "awarded_on": g.awarded_on, "note": g.note} for g in history
        ],
        "certificates": [
            {"id": c.id, "type": c.type, "issued_on": c.issued_on, "expires_on": c.expires_on,
             "status": club_service.certificate_status(c, today=today), "original_filename": c.original_filename}
            for c in certs
        ],
        "fees": [fee_dict(f, today=today) for f in reversed(fees)],
        "competitions": [
            {
                "competition_id": comp.id, "entry_id": entry.id, "name": comp.name, "starts_on": comp.starts_on,
                "location": comp.location, "level": comp.level, "category": entry.category, "status": entry.status,
                "placement": entry.placement,
                "points": competitions_service.points_for(placement=entry.placement, level=comp.level)
                if entry.status == "REGISTERED" else 0,
            }
            for entry, comp in entries
        ],
        "achievements": achievements_catalog.achievements(
            attendances=card["attendances"], belts_earned=max(len(history) - 1, 0), current_belt=current,
            totals=lifetime,
        ),
    }
