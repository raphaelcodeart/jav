"""Gare, iscrizioni, risultati e Jav Ranking.

Il ranking non si salva da nessuna parte: si somma dai risultati ogni volta
che qualcuno lo guarda. Correggere un piazzamento corregge la classifica,
senza un ricalcolo da ricordarsi di lanciare.

**Eventi della rete** (`club_id` NULL): il calendário comune dei club
(federazione, ADJA, opens, estágios). Li vede ogni club
dell'organizzazione e ognuno ci iscrive i suoi atleti; l'iscrizione e la
quota hanno il club dell'atleta, mai quello (inesistente) dell'evento.
L'evento lo modifica solo la piattaforma (network.py); un club registra i
risultati dei suoi atleti.
"""

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import and_, or_, select
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

#: Punti per livello di gara: (oro, argento, bronzo, partecipazione). È la
#: tabella che i club usavano già (docs/legacy-judo-aev.md): le famiglie
#: ritrovano gli stessi punti. Un 5°, un 7° o un piazzamento più basso
#: valgono la partecipazione; CLUB e INTERNATIONAL (generico) sono i nostri,
#: tra i livelli vicini.
LEVEL_POINTS: dict[str, tuple[int, int, int, int]] = {
    "CLUB": (3, 2, 1, 1),
    "REGIONAL": (5, 3, 2, 1),
    "ZONAL": (7, 5, 3, 2),
    "OPENS": (10, 8, 5, 3),
    "NATIONAL": (15, 10, 8, 4),
    "INTERNATIONAL": (20, 15, 10, 5),
    "EUROPEAN_CUP": (20, 15, 10, 5),
    "EUROPEAN_CHAMPIONSHIP": (25, 20, 15, 6),
    "WORLD_CHAMPIONSHIP": (30, 25, 20, 7),
    "OLYMPIC_GAMES": (35, 30, 25, 8),
}
LEVEL_LABELS = {
    "CLUB": "Club", "REGIONAL": "Regionale", "ZONAL": "Zonale", "OPENS": "Open", "NATIONAL": "Nazionale",
    "INTERNATIONAL": "Internazionale", "EUROPEAN_CUP": "Coppa Europa", "EUROPEAN_CHAMPIONSHIP": "Campionato europeo",
    "WORLD_CHAMPIONSHIP": "Campionato del mondo", "OLYMPIC_GAMES": "Giochi Olimpici",
}
PLACEMENT_LABELS = {1: "1° posto", 2: "2° posto", 3: "3° posto", 5: "5° posto", 7: "7° posto", 0: "Partecipazione"}


@dataclass(frozen=True)
class AgeBand:
    code: str
    label: str
    min_age: int
    max_age: int | None


#: I gruppi del Jav Ranking: gli stessi Grupo 1/2/3 dei club (e dei loro
#: piani), per età federale nell'anno della classifica (anno − anno di
#: nascita), come nel gestionale che i club usavano; i Veteranos (30 anni
#: federali e oltre, come l'escalão federale) hanno la loro classifica, e il
#: Grupo 3 si ferma a 29.
AGE_BANDS: tuple[AgeBand, ...] = (
    AgeBand("GRUPO_1", "Grupo 1 · 3–7 anos", 0, 7),
    AgeBand("GRUPO_2", "Grupo 2 · 8–12 anos", 8, 12),
    AgeBand("GRUPO_3", "Grupo 3 · 13–29 anos", 13, 29),
    AgeBand("VETERANOS", "Veteranos · 30+ anos", 30, None),
)


def ranking_year(today: date) -> int:
    """Il ranking è dell'anno solare, come l'età federale e come lo
    conoscevano i club ("Ranking 2026")."""
    return today.year


def ranking_label(year: int) -> str:
    return str(year)


def ranking_age(birth_date: date, year: int) -> int:
    return seasons.federal_age(birth_date, year)
_BANDS_BY_CODE = {b.code: b for b in AGE_BANDS}


def age_band_for(age: int) -> AgeBand:
    for band in AGE_BANDS:
        if band.min_age <= age and (band.max_age is None or age <= band.max_age):
            return band
    return AGE_BANDS[-1]


def points_for(*, placement: int | None, level: str) -> int:
    if placement is None:
        return 0
    gold, silver, bronze, participation = LEVEL_POINTS[level]
    return {1: gold, 2: silver, 3: bronze}.get(placement, participation)


def visible_to(scope: ClubScope):
    """Gli eventi di un club: i suoi e quelli della rete."""
    return or_(
        ClubCompetition.club_id == scope.club_id,
        and_(ClubCompetition.club_id.is_(None), ClubCompetition.organization_id == scope.organization_id),
    )


def entry_scope(competition: ClubCompetition, athlete: ClubAthlete) -> ClubScope:
    """Il club di un'iscrizione e della sua quota: quello dell'atleta (per
    un evento della rete l'evento non ne ha uno)."""
    return scope_of(athlete)


NETWORK_EVENT = "È un evento della rete: lo modifica JudoArteVida."


# --- Gare (segreteria) ----------------------------------------------------------------------------


def _validate_competition(c: ClubCompetition) -> None:
    if c.level not in COMPETITION_LEVELS:
        raise ClubValidationError("Livello della gara non valido.")
    if c.kind not in EVENT_KINDS:
        raise ClubValidationError("Tipo di evento non valido.")
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


async def get_competition(
    db: AsyncSession, *, scope: ClubScope, competition_id: uuid.UUID, editing: bool = False,
) -> ClubCompetition:
    """La gara, se il club la vede: sua o della rete. `editing`: solo le
    sue (un evento della rete lo modifica la piattaforma)."""
    comp = await db.get(ClubCompetition, competition_id)
    if comp is None or comp.organization_id != scope.organization_id:
        raise ClubNotFoundError("Gara non trovata.")
    if comp.club_id is None:
        if editing:
            raise ClubValidationError(NETWORK_EVENT)
        return comp
    if comp.club_id != scope.club_id:
        raise ClubNotFoundError("Gara non trovata.")
    return comp


async def update_competition(
    db: AsyncSession, *, scope: ClubScope, competition_id: uuid.UUID, actor_user_id: uuid.UUID,
    changes: dict,
) -> ClubCompetition:
    comp = await get_competition(db, scope=scope, competition_id=competition_id, editing=True)
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


async def set_competition_image(
    db: AsyncSession, *, scope: ClubScope, competition_id: uuid.UUID, actor_user_id: uuid.UUID,
    file_bytes: bytes | None, content_type: str = "",
) -> ClubCompetition:
    """La foto o la locandina della gara, nel bucket media (è pubblica come
    la circolare); `file_bytes` None la toglie. Solo le gare del club: un
    evento della rete lo cura la piattaforma."""
    from app.core.storage import UploadValidationError, upload_media

    comp = await get_competition(db, scope=scope, competition_id=competition_id, editing=True)
    if file_bytes is None:
        comp.image_url = None
    else:
        try:
            comp.image_url = upload_media(file_bytes=file_bytes, content_type=content_type,
                                          key_prefix=f"club-events/{scope.club_id}")
        except UploadValidationError as exc:
            raise ClubValidationError("L'immagine deve essere un JPG, PNG o WebP di massimo 5 MB.") from exc
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.competition_image", entity_type="club_competition", entity_id=str(comp.id),
        new_value={"image": comp.image_url is not None},
    )
    await db.commit()
    await db.refresh(comp)
    return comp


async def set_competition_status(
    db: AsyncSession, *, scope: ClubScope, competition_id: uuid.UUID, actor_user_id: uuid.UUID, status: str
) -> ClubCompetition:
    comp = await get_competition(db, scope=scope, competition_id=competition_id, editing=True)
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
    stmt = select(ClubCompetition).where(visible_to(scope))
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
    if comp.kind != "COMPETITION":
        raise ClubValidationError("Solo le gare hanno piazzamenti: per gli altri eventi non si inseriscono risultati.")
    # Di un evento della rete, ogni club registra i suoi atleti.
    entries = {
        e.id: e
        for e in (
            await db.execute(select(ClubCompetitionEntry).where(
                ClubCompetitionEntry.competition_id == comp.id, ClubCompetitionEntry.club_id == scope.club_id,
            ))
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
    if comp.club_id is not None:
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
    # Con dei debiti scaduti non ci si iscrive (participation.py), salvo le
    # quote che la segreteria ha segnato «non bloccanti».
    from app.domains.club.participation import DEBTS_REASON, blocking_debts

    if await blocking_debts(db, athlete=athlete, today=today, exclude_competition_id=competition.id):
        return False, DEBTS_REASON
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
            **entry_scope(competition, athlete).columns(), competition_id=competition.id, athlete_id=athlete.id,
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
            db, **entry_scope(competition, athlete).columns(), athlete_id=athlete.id, kind="COMPETITION",
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


def period_range(*, period: str, year: int, month: int | None = None) -> tuple[date, date] | None:
    """Le date di un periodo del ranking: un mese, un anno solare, o (None)
    da sempre."""
    if period == "all":
        return None
    if period == "month":
        if month is None or not 1 <= month <= 12:
            raise ClubValidationError("Mese non valido.")
        last = (date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1))
        return date(year, month, 1), last
    if period == "year":
        return date(year, 1, 1), date(year, 12, 31)
    raise ClubValidationError("Periodo non valido: mese, anno o da sempre.")


async def athlete_points(
    db: AsyncSession, *, athlete_ids: list[uuid.UUID], season: int | None = None,
    between: tuple[date, date] | None = None,
) -> dict[uuid.UUID, dict]:
    """Punti, gare e medaglie per atleta, nell'anno solare `season` (il nome
    è rimasto: il ranking era per stagione), tra le date `between`, o da
    sempre."""
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
        between = (date(season, 1, 1), date(season, 12, 31))
    if between is not None:
        stmt = stmt.where(ClubCompetition.starts_on >= between[0], ClubCompetition.starts_on <= between[1])
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
    age_band: str | None = None, viewer_user_id: uuid.UUID | None = None, club_only: bool = False,
) -> list[dict]:
    """La classifica dell'anno, **di tutta la rete** (tutti i club
    dell'organizzazione che hanno il ranking), come nel gestionale di prima;
    `club_only` la restringe al club. Ex aequo: stessa posizione, e chi
    viene dopo salta i posti (1, 2, 2, 4), come in ogni classifica sportiva."""
    if age_band is not None and age_band not in _BANDS_BY_CODE:
        raise ClubValidationError("Fascia d'età non valida.")
    if not (await kinds.club_rules(db, club_id=scope.club_id)).in_rankings:
        # I corsi JAV non hanno classifica (club/kinds.py).
        return []
    clubs = {
        c.id: c for c in (await db.execute(select(Club).where(Club.organization_id == scope.organization_id))).scalars()
        if (c.id == scope.club_id or not club_only) and kinds.rules_of(c).in_rankings
    }
    stmt = select(ClubAthlete).where(ClubAthlete.club_id.in_(list(clubs)), ClubAthlete.status != "LEFT")
    if sex:
        stmt = stmt.where(ClubAthlete.sex == sex)
    athletes = list((await db.execute(stmt)).scalars())
    if age_band is not None:
        band = _BANDS_BY_CODE[age_band]
        athletes = [a for a in athletes if age_band_for(ranking_age(a.birth_date, season)).code == band.code]
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
            "age_band": age_band_for(ranking_age(athlete.birth_date, season)).code,
            "belt": belts.get(athlete.id),
            "is_mine": viewer_user_id is not None and athlete.guardian_user_id == viewer_user_id,
            "club_name": clubs[athlete.club_id].name,
            **p,
        })
    return rows
