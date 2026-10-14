"""Gare, iscrizioni, risultati e Jav Ranking.

Il ranking non si salva da nessuna parte: si somma dai risultati ogni volta
che qualcuno lo guarda. Correggere un piazzamento corregge la classifica,
senza un ricalcolo da ricordarsi di lanciare.
"""

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.club import kinds, seasons
from app.domains.club.models import (
    COMPETITION_LEVELS,
    EVENT_KINDS,
    PLACEMENTS,
    Club,
    ClubAthlete,
    ClubCompetition,
    ClubCompetitionEntry,
    ClubFee,
)
from app.domains.club.scope import ClubScope, scope_of
from app.domains.club.service import (
    ClubNotFoundError,
    ClubValidationError,
    _insert_fee,
    current_belts,
    has_valid_agonistic_certificate,
)

#: Punti per piazzamento (0 = partecipazione).
PLACEMENT_POINTS = {1: 100, 2: 70, 3: 50, 5: 30, 7: 20, 0: 10}
LEVEL_COEFFICIENTS = {"CLUB": 1, "REGIONAL": 2, "NATIONAL": 3, "INTERNATIONAL": 4}
LEVEL_LABELS = {"CLUB": "Club", "REGIONAL": "Regionale", "NATIONAL": "Nazionale", "INTERNATIONAL": "Internazionale"}
PLACEMENT_LABELS = {1: "1° posto", 2: "2° posto", 3: "3° posto", 5: "5° posto", 7: "7° posto", 0: "Partecipazione"}


@dataclass(frozen=True)
class AgeBand:
    code: str
    label: str
    min_age: int
    max_age: int | None


#: Le fasce del Jav Ranking, per età al 1° settembre della stagione
#: (le stesse soglie delle classi d'età giovanili del judo italiano).
AGE_BANDS: tuple[AgeBand, ...] = (
    AgeBand("BAMBINI", "Bambini (fino a 7 anni)", 0, 7),
    AgeBand("FANCIULLI", "Fanciulli (8-9)", 8, 9),
    AgeBand("RAGAZZI", "Ragazzi (10-11)", 10, 11),
    AgeBand("ESORDIENTI", "Esordienti (12-13)", 12, 13),
    AgeBand("CADETTI", "Cadetti (14-16)", 14, 16),
    AgeBand("JUNIORES", "Juniores (17-19)", 17, 19),
    AgeBand("SENIORES", "Seniores (20+)", 20, None),
)
_BANDS_BY_CODE = {b.code: b for b in AGE_BANDS}


def age_band_for(age: int) -> AgeBand:
    for band in AGE_BANDS:
        if band.min_age <= age and (band.max_age is None or age <= band.max_age):
            return band
    return AGE_BANDS[-1]


def points_for(*, placement: int | None, level: str) -> int:
    if placement is None:
        return 0
    return PLACEMENT_POINTS[placement] * LEVEL_COEFFICIENTS[level]


# --- Gare (segreteria) ----------------------------------------------------------------------------


def _validate_competition(c: ClubCompetition) -> None:
    if c.level not in COMPETITION_LEVELS:
        raise ClubValidationError("Livello della gara non valido.")
    if c.kind not in EVENT_KINDS:
        raise ClubValidationError("Tipo di evento non valido: gara o stage.")
    if c.transport_entity_email and "@" not in c.transport_entity_email:
        raise ClubValidationError("L'email dell'ente per il trasporto non è valida.")
    if c.ends_on < c.starts_on:
        raise ClubValidationError("La gara non può finire prima di cominciare.")
    if c.registration_deadline > c.starts_on:
        raise ClubValidationError("La scadenza delle iscrizioni deve essere entro il giorno della gara.")
    if c.fee_cents < 0:
        raise ClubValidationError("La quota d'iscrizione non può essere negativa.")
    if c.min_age is not None and c.max_age is not None and c.max_age < c.min_age:
        raise ClubValidationError("L'età massima non può essere inferiore all'età minima.")


async def create_competition(
    db: AsyncSession, *, scope: ClubScope, actor_user_id: uuid.UUID, data: dict
) -> ClubCompetition:
    if not (await kinds.club_rules(db, club_id=scope.club_id)).has_competitions:
        raise ClubValidationError(kinds.NO_COMPETITIONS)
    data = {**data}
    data.setdefault("kind", "COMPETITION")
    data.setdefault("transport_companions", 0)
    data.setdefault("ends_on", data["starts_on"])
    if data["ends_on"] is None:
        data["ends_on"] = data["starts_on"]
    # L'ente del trasporto, se l'evento non ne indica uno: quello di sempre
    # del club (di solito il comune), dalle impostazioni.
    club = await db.get(Club, scope.club_id)
    defaults = (club.settings or {}) if club is not None else {}
    data["transport_entity_name"] = data.get("transport_entity_name") or defaults.get("transport_entity_name")
    data["transport_entity_email"] = data.get("transport_entity_email") or defaults.get("transport_entity_email")
    comp = ClubCompetition(**scope.columns(), created_by_user_id=actor_user_id, status="OPEN", **data)
    _validate_competition(comp)
    db.add(comp)
    await db.flush()
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.competition_created", entity_type="club_competition", entity_id=str(comp.id),
        new_value={"name": comp.name, "starts_on": comp.starts_on.isoformat()},
    )
    await db.commit()
    await db.refresh(comp)
    return comp


async def get_competition(db: AsyncSession, *, scope: ClubScope, competition_id: uuid.UUID) -> ClubCompetition:
    comp = await db.get(ClubCompetition, competition_id)
    if comp is None or comp.club_id != scope.club_id:
        raise ClubNotFoundError("Gara non trovata.")
    return comp


async def update_competition(
    db: AsyncSession, *, scope: ClubScope, competition_id: uuid.UUID, actor_user_id: uuid.UUID,
    changes: dict,
) -> ClubCompetition:
    comp = await get_competition(db, scope=scope, competition_id=competition_id)
    for key, value in changes.items():
        setattr(comp, key, value)
    _validate_competition(comp)
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.competition_updated", entity_type="club_competition", entity_id=str(comp.id),
        new_value={k: str(v) for k, v in changes.items()},
    )
    await db.commit()
    await db.refresh(comp)
    return comp


async def set_competition_status(
    db: AsyncSession, *, scope: ClubScope, competition_id: uuid.UUID, actor_user_id: uuid.UUID, status: str
) -> ClubCompetition:
    comp = await get_competition(db, scope=scope, competition_id=competition_id)
    if status not in ("OPEN", "CLOSED", "DONE"):
        raise ClubValidationError("Stato della gara non valido.")
    was_open = comp.status == "OPEN"
    comp.status = status
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.competition_status", entity_type="club_competition", entity_id=str(comp.id),
        new_value={"status": status},
    )
    await db.commit()
    await db.refresh(comp)
    if was_open and status == "CLOSED":
        from app.domains.club import transport

        await transport.on_registrations_closed(db, comp=comp)
        await db.refresh(comp)
    return comp


async def list_competitions(
    db: AsyncSession, *, scope: ClubScope, status: str | None = None, from_date: date | None = None,
) -> list[ClubCompetition]:
    stmt = select(ClubCompetition).where(ClubCompetition.club_id == scope.club_id)
    if status:
        stmt = stmt.where(ClubCompetition.status == status)
    if from_date:
        stmt = stmt.where(ClubCompetition.ends_on >= from_date)
    return list((await db.execute(stmt.order_by(ClubCompetition.starts_on))).scalars())


async def list_entries(
    db: AsyncSession, *, competition_ids: list[uuid.UUID] | None = None, athlete_ids: list[uuid.UUID] | None = None,
) -> list[ClubCompetitionEntry]:
    stmt = select(ClubCompetitionEntry)
    if competition_ids is not None:
        stmt = stmt.where(ClubCompetitionEntry.competition_id.in_(competition_ids))
    if athlete_ids is not None:
        stmt = stmt.where(ClubCompetitionEntry.athlete_id.in_(athlete_ids))
    return list((await db.execute(stmt.order_by(ClubCompetitionEntry.created_at))).scalars())


async def record_results(
    db: AsyncSession, *, scope: ClubScope, competition_id: uuid.UUID, actor_user_id: uuid.UUID,
    results: list[tuple[uuid.UUID, int | None]],
) -> ClubCompetition:
    """I piazzamenti, inseriti dalla segreteria a gara finita. La gara
    passa a DONE: le iscrizioni sono chiuse per definizione."""
    comp = await get_competition(db, scope=scope, competition_id=competition_id)
    if comp.kind == "STAGE":
        raise ClubValidationError("Uno stage non ha piazzamenti: i risultati si inseriscono solo per le gare.")
    entries = {
        e.id: e
        for e in (
            await db.execute(select(ClubCompetitionEntry).where(ClubCompetitionEntry.competition_id == comp.id))
        ).scalars()
    }
    for entry_id, placement in results:
        entry = entries.get(entry_id)
        if entry is None:
            raise ClubNotFoundError("Iscrizione non trovata in questa gara.")
        if placement is not None and placement not in PLACEMENTS:
            raise ClubValidationError("Piazzamento non valido: 1, 2, 3, 5, 7 oppure partecipazione.")
        if entry.status != "REGISTERED" and placement is not None:
            raise ClubValidationError("Un atleta ritirato non può avere un risultato.")
        entry.placement = placement
    comp.status = "DONE"
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.competition_results", entity_type="club_competition", entity_id=str(comp.id),
        new_value={"results": {str(e): p for e, p in results}},
    )
    await db.commit()
    await db.refresh(comp)
    return comp


# --- Iscrizioni (genitore) ------------------------------------------------------------------------


async def eligibility(
    db: AsyncSession, *, competition: ClubCompetition, athlete: ClubAthlete, today: date | None = None,
) -> tuple[bool, str | None]:
    """(può iscriversi, perché no). Il motivo è già la frase da mostrare."""
    today = today or utcnow().date()
    if competition.status != "OPEN" or today > competition.registration_deadline:
        return False, "Le iscrizioni sono chiuse."
    if athlete.status != "ACTIVE":
        return False, f"{athlete.first_name} non risulta attivo nel club."
    age = seasons.age_on(athlete.birth_date, competition.starts_on)
    if competition.min_age is not None and age < competition.min_age:
        return False, f"La gara è dai {competition.min_age} anni in su."
    if competition.max_age is not None and age > competition.max_age:
        return False, f"La gara è fino a {competition.max_age} anni."
    if competition.requires_agonistic_certificate and not await has_valid_agonistic_certificate(
        db, athlete_id=athlete.id, on=competition.starts_on
    ):
        return False, (
            f"Serve un certificato medico agonistico valido il {competition.starts_on.strftime('%d/%m/%Y')}: "
            "caricalo nella scheda dell'atleta."
        )
    return True, None


async def register_entry(
    db: AsyncSession, *, competition: ClubCompetition, athlete: ClubAthlete, actor_user_id: uuid.UUID,
    category: str | None, weight_kg=None, today: date | None = None,
) -> ClubCompetitionEntry:
    """Iscrive l'atleta e crea la quota della gara. Iscriversi di nuovo dopo
    un ritiro riattiva la stessa iscrizione e la stessa quota."""
    ok, reason = await eligibility(db, competition=competition, athlete=athlete, today=today)
    entry = (
        await db.execute(
            select(ClubCompetitionEntry).where(
                ClubCompetitionEntry.competition_id == competition.id, ClubCompetitionEntry.athlete_id == athlete.id
            ).with_for_update()
        )
    ).scalar_one_or_none()
    if entry is not None and entry.status == "REGISTERED":
        raise ClubValidationError(f"{athlete.first_name} è già iscritto a questa gara.")
    if not ok:
        raise ClubValidationError(reason or "Iscrizione non possibile.")

    if entry is None:
        entry = ClubCompetitionEntry(
            **scope_of(competition).columns(), competition_id=competition.id, athlete_id=athlete.id,
            registered_by_user_id=actor_user_id,
        )
        db.add(entry)
    entry.status = "REGISTERED"
    entry.category = category
    entry.weight_kg = weight_kg if weight_kg is not None else athlete.weight_kg
    entry.registered_by_user_id = actor_user_id
    await db.flush()

    if competition.fee_cents > 0:
        await _insert_fee(
            db, **scope_of(competition).columns(), athlete_id=athlete.id, kind="COMPETITION",
            period=str(competition.id), competition_id=competition.id,
            description=f"Iscrizione {'stage' if competition.kind == 'STAGE' else 'gara'}: {competition.name}"[:200],
            amount_cents=competition.fee_cents, due_date=competition.registration_deadline,
        )
        # Una quota condonata al ritiro torna da pagare con la nuova iscrizione.
        fee = await _competition_fee(db, competition_id=competition.id, athlete_id=athlete.id)
        if fee is not None and fee.status == "WAIVED":
            fee.status = "DUE"
            fee.waived_at = fee.waived_by_user_id = fee.waive_reason = None

    await audit_service.record(
        db, organization_id=competition.organization_id, actor_user_id=actor_user_id,
        action="club.competition_entry_registered", entity_type="club_competition_entry", entity_id=str(entry.id),
        new_value={"competition_id": str(competition.id), "athlete_id": str(athlete.id), "category": category},
    )
    await db.commit()
    await db.refresh(entry)
    return entry


async def _competition_fee(db: AsyncSession, *, competition_id: uuid.UUID, athlete_id: uuid.UUID) -> ClubFee | None:
    return (
        await db.execute(
            select(ClubFee).where(
                ClubFee.athlete_id == athlete_id, ClubFee.kind == "COMPETITION", ClubFee.period == str(competition_id)
            ).with_for_update()
        )
    ).scalar_one_or_none()


async def withdraw_entry(
    db: AsyncSession, *, competition: ClubCompetition, athlete: ClubAthlete, actor_user_id: uuid.UUID,
    today: date | None = None,
) -> ClubCompetitionEntry:
    """Ritiro entro la scadenza. La quota non ancora pagata si condona; una
    già pagata resta pagata (un eventuale rimborso lo decide la segreteria)."""
    today = today or utcnow().date()
    entry = (
        await db.execute(
            select(ClubCompetitionEntry).where(
                ClubCompetitionEntry.competition_id == competition.id, ClubCompetitionEntry.athlete_id == athlete.id
            )
        )
    ).scalar_one_or_none()
    if entry is None or entry.status != "REGISTERED":
        raise ClubNotFoundError(f"{athlete.first_name} non è iscritto a questa gara.")
    if today > competition.registration_deadline or competition.status != "OPEN":
        raise ClubValidationError("Le iscrizioni sono chiuse: per ritirarti contatta la segreteria.")
    entry.status = "WITHDRAWN"
    fee = await _competition_fee(db, competition_id=competition.id, athlete_id=athlete.id)
    if fee is not None and fee.status == "DUE":
        fee.status = "WAIVED"
        fee.waived_at = utcnow()
        fee.waived_by_user_id = actor_user_id
        fee.waive_reason = "Iscrizione ritirata"
    await audit_service.record(
        db, organization_id=competition.organization_id, actor_user_id=actor_user_id,
        action="club.competition_entry_withdrawn", entity_type="club_competition_entry", entity_id=str(entry.id),
    )
    await db.commit()
    await db.refresh(entry)
    return entry


# --- Jav Ranking ----------------------------------------------------------------------------------


async def athlete_points(
    db: AsyncSession, *, athlete_ids: list[uuid.UUID], season: int | None = None,
) -> dict[uuid.UUID, dict]:
    """Punti, gare e medaglie per atleta, nella stagione (o da sempre)."""
    if not athlete_ids:
        return {}
    stmt = (
        select(ClubCompetitionEntry, ClubCompetition)
        .join(ClubCompetition, ClubCompetition.id == ClubCompetitionEntry.competition_id)
        .where(
            ClubCompetitionEntry.athlete_id.in_(athlete_ids),
            ClubCompetitionEntry.status == "REGISTERED",
            ClubCompetitionEntry.placement.is_not(None),
            # Gli stage non danno punti né medaglie.
            ClubCompetition.kind == "COMPETITION",
        )
    )
    if season is not None:
        stmt = stmt.where(
            ClubCompetition.starts_on >= seasons.season_start(season),
            ClubCompetition.starts_on <= seasons.season_end(season),
        )
    out = {
        a: {"points": 0, "competitions": 0, "gold": 0, "silver": 0, "bronze": 0}
        for a in athlete_ids
    }
    for entry, comp in (await db.execute(stmt)).all():
        row = out[entry.athlete_id]
        row["points"] += points_for(placement=entry.placement, level=comp.level)
        row["competitions"] += 1
        if entry.placement == 1:
            row["gold"] += 1
        elif entry.placement == 2:
            row["silver"] += 1
        elif entry.placement == 3:
            row["bronze"] += 1
    return out


async def ranking(
    db: AsyncSession, *, scope: ClubScope, season: int, sex: str | None = None,
    age_band: str | None = None, viewer_user_id: uuid.UUID | None = None,
) -> list[dict]:
    """La classifica della stagione. Ex aequo: stessa posizione, e chi viene
    dopo salta i posti (1, 2, 2, 4), come in ogni classifica sportiva."""
    if age_band is not None and age_band not in _BANDS_BY_CODE:
        raise ClubValidationError("Fascia d'età non valida.")
    if not (await kinds.club_rules(db, club_id=scope.club_id)).in_rankings:
        # I corsi JAV non hanno classifica (club/kinds.py).
        return []
    stmt = select(ClubAthlete).where(ClubAthlete.club_id == scope.club_id, ClubAthlete.status != "LEFT")
    if sex:
        stmt = stmt.where(ClubAthlete.sex == sex)
    athletes = list((await db.execute(stmt)).scalars())
    if age_band is not None:
        band = _BANDS_BY_CODE[age_band]
        athletes = [a for a in athletes if age_band_for(seasons.season_age(a.birth_date, season)).code == band.code]
    points = await athlete_points(db, athlete_ids=[a.id for a in athletes], season=season)
    ranked = [a for a in athletes if points[a.id]["competitions"] > 0]
    ranked.sort(key=lambda a: (-points[a.id]["points"], -points[a.id]["gold"], a.last_name, a.first_name))
    belts = await current_belts(db, athlete_ids=[a.id for a in ranked])

    rows: list[dict] = []
    position = 0
    previous: int | None = None
    for index, athlete in enumerate(ranked, start=1):
        p = points[athlete.id]
        if p["points"] != previous:
            position = index
            previous = p["points"]
        rows.append({
            "position": position,
            "athlete_id": athlete.id,
            # Nome e iniziale: la classifica la vedono tutte le famiglie.
            "display_name": f"{athlete.first_name} {athlete.last_name[:1]}.",
            "photo_url": athlete.photo_url,
            "sex": athlete.sex,
            "age_band": age_band_for(seasons.season_age(athlete.birth_date, season)).code,
            "belt": belts.get(athlete.id),
            "is_mine": viewer_user_id is not None and athlete.guardian_user_id == viewer_user_id,
            **p,
        })
    return rows
