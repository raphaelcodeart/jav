"""Gli eventi visti dallo staff: la scheda di un evento (dal calendário e
dagli elenchi) e i risultati che il treinador scrive dal telefono, alla
pesata e a gara finita. Specifica: docs/club-portal.md, "Risultati dal
treinador, scheda dell'evento e relatórios".

**I piazzamenti passano da `competitions.record_results`**, la stessa
funzione della segreteria: il Jav Ranking li somma nello stesso modo, la
gara passa a DONE nello stesso modo, e non esiste un secondo modo di
scrivere un risultato da tenere allineato al primo.

**I contatti** (telefono ed email) li vede solo lo staff, e sono quelli
dell'encarregado finché l'atleta è minorenne; un adulto con il suo account
ha i suoi. Le famiglie vedono la scheda senza contatti, e degli altri
iscritti solo nome e iniziale, come nel ranking.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email import is_placeholder_address
from app.domains.audit import service as audit_service
from app.domains.club import competitions, seasons
from app.domains.club.models import (
    PLACEMENTS,
    Club,
    ClubAthlete,
    ClubCompetition,
    ClubCompetitionEntry,
)
from app.domains.club.scope import ClubScope
from app.domains.club.service import ClubNotFoundError, ClubValidationError
from app.domains.users.models import User

#: I campi che il treinador scrive su un'iscrizione.
ENTRY_FIELDS = ("weight_kg", "category", "placement", "rank", "result_notes")
ADULT_AGE = 18


async def staff_competitions(
    db: AsyncSession, *, scope: ClubScope, past: bool, today: date,
) -> list[dict]:
    """Gli eventi del club e della rete con quanti atleti del club ci sono
    iscritti e quanti hanno già un risultato: i prossimi (dal più vicino) o
    quelli passati (dal più recente)."""
    stmt = select(ClubCompetition).where(competitions.visible_to(scope))
    if past:
        stmt = stmt.where(ClubCompetition.starts_on <= today).order_by(ClubCompetition.starts_on.desc())
    else:
        stmt = stmt.where(ClubCompetition.ends_on >= today).order_by(ClubCompetition.starts_on)
    comps = list((await db.execute(stmt.limit(60))).scalars())
    counts: dict[uuid.UUID, tuple[int, int]] = {}
    if comps:
        rows = (await db.execute(
            select(
                ClubCompetitionEntry.competition_id, func.count(),
                func.count(ClubCompetitionEntry.placement),
            ).where(
                ClubCompetitionEntry.competition_id.in_([c.id for c in comps]),
                ClubCompetitionEntry.club_id == scope.club_id, ClubCompetitionEntry.status == "REGISTERED",
            ).group_by(ClubCompetitionEntry.competition_id)
        )).all()
        counts = {cid: (n, done) for cid, n, done in rows}
    return [
        {**competition_dict(c), "entries_count": counts.get(c.id, (0, 0))[0],
         "results_count": counts.get(c.id, (0, 0))[1]}
        for c in comps
    ]


def competition_dict(c: ClubCompetition, *, club_name: str | None = None) -> dict:
    return {
        "id": c.id, "name": c.name, "description": c.description, "kind": c.kind, "level": c.level,
        "status": c.status, "starts_on": c.starts_on, "ends_on": c.ends_on,
        "starts_at_time": c.starts_at_time, "ends_at_time": c.ends_at_time,
        "location": c.location, "organizer": c.organizer,
        "registration_deadline": c.registration_deadline, "registration_deadline_time": c.registration_deadline_time,
        "fee_cents": c.fee_cents, "min_age": c.min_age, "max_age": c.max_age,
        "age_groups": list(c.age_groups or []), "categories": c.categories,
        "requires_agonistic_certificate": c.requires_agonistic_certificate,
        "circular_url": c.circular_url, "circular_filename": c.circular_filename, "image_url": c.image_url,
        "transport_mode": c.transport_mode, "transport_info": c.transport_info,
        "network": c.club_id is None, "club_name": club_name,
    }


async def contacts_for(db: AsyncSession, athletes: list[ClubAthlete], *, on: date) -> dict[uuid.UUID, dict]:
    """Chi chiamare per ogni atleta: l'encarregado per un minorenne, l'atleta
    stesso se è adulto e ha un account con un recapito vero (un account
    senza email ha un indirizzo finto `@atleta.invalid`, che non conta)."""
    from app.domains.club.people import _names
    from app.domains.customers.models import Customer

    if not athletes:
        return {}
    user_ids = {a.guardian_user_id for a in athletes} | {a.user_id for a in athletes if a.user_id}
    emails = dict((await db.execute(select(User.id, User.email).where(User.id.in_(user_ids)))).all())
    phones = dict((await db.execute(
        select(Customer.user_id, Customer.phone).where(Customer.user_id.in_(user_ids), Customer.phone.is_not(None))
    )).all())
    names = await _names(db, user_ids)

    def reachable(user_id) -> tuple[str | None, str | None]:
        email = emails.get(user_id)
        return (None if is_placeholder_address(email) else email), phones.get(user_id)

    out: dict[uuid.UUID, dict] = {}
    for a in athletes:
        adult = seasons.age_on(a.birth_date, on) >= ADULT_AGE
        user_id = a.guardian_user_id
        if adult and a.user_id is not None and any(reachable(a.user_id)):
            user_id = a.user_id
        email, phone = reachable(user_id)
        out[a.id] = {
            "name": f"{a.first_name} {a.last_name}" if user_id == a.user_id or a.is_self else names.get(user_id),
            "email": email, "phone": phone,
            "is_guardian": not (user_id == a.user_id or a.is_self),
        }
    return out


async def competition_detail(
    db: AsyncSession, *, scope: ClubScope, competition_id: uuid.UUID, staff: bool, today: date,
) -> dict:
    """La scheda di un evento con gli atleti del club iscritti. Lo staff
    vede nome intero, peso, categoria, risultato e contatti; una famiglia
    nome e iniziale, categoria e risultato."""
    comp = await competitions.get_competition(db, scope=scope, competition_id=competition_id)
    club_name = (await db.get(Club, comp.club_id)).name if comp.club_id else None
    pairs = (await db.execute(
        select(ClubCompetitionEntry, ClubAthlete)
        .join(ClubAthlete, ClubAthlete.id == ClubCompetitionEntry.athlete_id)
        .where(
            ClubCompetitionEntry.competition_id == comp.id, ClubCompetitionEntry.club_id == scope.club_id,
            ClubCompetitionEntry.status == "REGISTERED",
        )
        .order_by(ClubAthlete.last_name, ClubAthlete.first_name)
    )).all()
    contacts = await contacts_for(db, [a for _e, a in pairs], on=today) if staff else {}
    entries = []
    for entry, athlete in pairs:
        row = {
            "entry_id": entry.id, "athlete_id": athlete.id,
            "athlete_name": f"{athlete.first_name} {athlete.last_name}" if staff
            else f"{athlete.first_name} {athlete.last_name[:1]}.",
            "photo_url": athlete.photo_url, "category": entry.category, "placement": entry.placement,
            "rank": entry.rank,
            "points": competitions.points_for(placement=entry.placement, level=comp.level)
            if comp.kind == "COMPETITION" else 0,
        }
        if staff:
            row.update({
                "sex": athlete.sex, "age": seasons.age_on(athlete.birth_date, comp.starts_on),
                "weight_kg": entry.weight_kg, "result_notes": entry.result_notes,
                "contact": contacts.get(athlete.id),
            })
        entries.append(row)
    return {**competition_dict(comp, club_name=club_name), "entries": entries}


async def update_entry(
    db: AsyncSession, *, scope: ClubScope, competition_id: uuid.UUID, entry_id: uuid.UUID,
    actor_user_id: uuid.UUID, changes: dict,
) -> ClubCompetitionEntry:
    """Il treinador scrive un pezzo alla volta: alla pesata il peso e la
    categoria, a gara finita il piazzamento (o la posizione vera, il 9° di un
    open, che per il ranking vale la partecipazione) e una nota. Solo le
    iscrizioni del suo club, e solo degli atleti ancora iscritti."""
    comp = await competitions.get_competition(db, scope=scope, competition_id=competition_id)
    entry = await db.get(ClubCompetitionEntry, entry_id, with_for_update=True)
    if entry is None or entry.competition_id != comp.id or entry.club_id != scope.club_id:
        raise ClubNotFoundError("Iscrizione non trovata in questa gara.")
    if entry.status != "REGISTERED":
        raise ClubValidationError("L'atleta si è ritirato da questa gara.")
    unknown = set(changes) - set(ENTRY_FIELDS)
    if unknown:
        raise ClubValidationError("Campo non modificabile.")

    if "weight_kg" in changes:
        weight = changes["weight_kg"]
        if weight is not None and not Decimal(10) <= Decimal(str(weight)) <= Decimal(300):
            raise ClubValidationError("Il peso deve essere tra 10 e 300 kg.")
        entry.weight_kg = weight
    if "category" in changes:
        entry.category = (changes["category"] or "").strip()[:120] or None
    if "result_notes" in changes:
        entry.result_notes = (changes["result_notes"] or "").strip()[:500] or None
    placement = changes.get("placement", entry.placement)
    if placement is not None and placement not in PLACEMENTS:
        raise ClubValidationError("Piazzamento non valido: 1, 2, 3, 5, 7 oppure partecipazione.")
    if "rank" in changes:
        rank = changes["rank"]
        if rank is not None and not 1 <= rank <= 999:
            raise ClubValidationError("La posizione deve essere tra 1 e 999.")
        entry.rank = rank
    # La posizione vera serve solo quando non è già un piazzamento (9°, 17°…).
    if placement != 0:
        entry.rank = None
    elif entry.rank in PLACEMENTS:
        raise ClubValidationError("Per un 1°, 2°, 3°, 5° o 7° posto scegli il piazzamento.")

    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.competition_entry_updated", entity_type="club_competition_entry", entity_id=str(entry.id),
        new_value={k: str(v) for k, v in changes.items()},
    )
    if "placement" in changes and changes["placement"] != entry.placement:
        # Lo stesso percorso della segreteria (record_results fa il commit).
        await competitions.record_results(
            db, scope=scope, competition_id=comp.id, actor_user_id=actor_user_id,
            results=[(entry.id, changes["placement"])],
        )
    else:
        await db.commit()
    await db.refresh(entry)
    return entry
