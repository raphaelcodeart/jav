"""Le persone del club, in un elenco solo: atleti, genitori che non si
allenano, segreteria, treinador e treinador adjunto, monitor e monitor
adjunto. Ognuno con i suoi "simboli" (i tipi a cui appartiene) e la sua
scheda: debiti, pagamenti, risultati, investimenti del club.

Una persona può essere più cose insieme (un genitore che si allena è anche
atleta, un atleta grande può essere monitor): l'elenco ha una riga per
persona e la lista dei suoi tipi, non una riga per tipo.

Gli investimenti sono ricariche del wallet della famiglia fatte dal club per
un atleta (un premio, una borsa di studio): le fa solo il superadmin
(`wallet.credit`), la segreteria le vede.
"""

import hashlib
import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.club import belts as belts_catalog
from app.domains.club import seasons
from app.domains.club.models import (
    CLUB_FUNCTIONS,
    ClubAthlete,
    ClubCompetition,
    ClubCompetitionEntry,
    ClubFee,
    ClubFunction,
    ClubPaymentProof,
    ClubReferee,
)
from app.domains.club.scope import ClubScope
from app.domains.club.service import ClubNotFoundError, ClubValidationError, current_belts
from app.domains.rbac.models import Role, UserRole
from app.domains.users.models import User

INVESTMENT_SOURCE = "CLUB_INVESTMENT"


async def _names(db: AsyncSession, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Nome e cognome dal profilo cliente; l'email per chi non ce l'ha (lo staff)."""
    from app.domains.customers.models import Customer, CustomerProfile

    if not user_ids:
        return {}
    rows = (
        await db.execute(
            select(User.id, User.email, CustomerProfile.first_name, CustomerProfile.last_name)
            .outerjoin(Customer, Customer.user_id == User.id)
            .outerjoin(CustomerProfile, CustomerProfile.customer_id == Customer.id)
            .where(User.id.in_(user_ids))
        )
    ).all()
    out: dict[uuid.UUID, str] = {}
    for user_id, email, first, last in rows:
        name = " ".join(x for x in (first, last) if x)
        out.setdefault(user_id, name or email)
    return out


async def list_people(db: AsyncSession, *, scope: ClubScope) -> list[dict]:
    """Tutti, una riga a testa, con i tipi: ATHLETE, PARENT, SECRETARY,
    COACH, ASSISTANT_COACH, MONITOR, ASSISTANT_MONITOR, REFEREE. Un adulto
    che si allena (`is_self`) è una riga sola: atleta, e anche genitore se
    il conto ha altri atleti, istruttore se ha l'account da istruttore."""
    athletes = list(
        (await db.execute(select(ClubAthlete).where(ClubAthlete.club_id == scope.club_id))).scalars()
    )
    users = list((await db.execute(select(User).where(User.club_id == scope.club_id))).scalars())
    roles = dict(
        (
            await db.execute(
                select(UserRole.user_id, func.array_agg(Role.code))
                .join(Role, Role.id == UserRole.role_id)
                .where(UserRole.user_id.in_([u.id for u in users]))
                .group_by(UserRole.user_id)
            )
        ).all()
    ) if users else {}
    functions = list((await db.execute(select(ClubFunction).where(ClubFunction.club_id == scope.club_id))).scalars())
    fn_by_user = {f.user_id: f.function for f in functions if f.user_id}
    fn_by_athlete = {f.athlete_id: f.function for f in functions if f.athlete_id}
    referees = list((await db.execute(select(ClubReferee).where(ClubReferee.club_id == scope.club_id))).scalars())
    referee_users = {r.user_id for r in referees if r.user_id}
    referee_athletes = {r.athlete_id for r in referees if r.athlete_id}
    due = dict(
        (
            await db.execute(
                select(ClubFee.athlete_id, func.sum(ClubFee.amount_cents))
                .where(ClubFee.club_id == scope.club_id, ClubFee.status == "DUE", ClubFee.athlete_id.is_not(None))
                .group_by(ClubFee.athlete_id)
            )
        ).all()
    )
    member_due = dict(
        (
            await db.execute(
                select(ClubFee.guardian_user_id, func.sum(ClubFee.amount_cents))
                .where(ClubFee.club_id == scope.club_id, ClubFee.status == "DUE", ClubFee.kind == "MEMBERSHIP")
                .group_by(ClubFee.guardian_user_id)
            )
        ).all()
    )
    belts = await current_belts(db, athlete_ids=[a.id for a in athletes])
    names = await _names(db, {u.id for u in users})
    emails = {u.id: u.email for u in users}
    today = utcnow().date()

    rows: list[dict] = []
    self_athlete_of = {a.guardian_user_id: a for a in athletes if a.is_self}
    children = {}
    for a in athletes:
        children.setdefault(a.guardian_user_id, []).append(a)
    for a in athletes:
        kinds = ["ATHLETE"]
        holder_roles = set(roles.get(a.guardian_user_id) or []) if a.is_self else set()
        if a.is_self and len(children.get(a.guardian_user_id, [])) > 1:
            kinds.append("PARENT")
        if "SECRETARY" in holder_roles:
            kinds.append("SECRETARY")
        function = fn_by_athlete.get(a.id) or (fn_by_user.get(a.guardian_user_id) if a.is_self else None)
        if function:
            kinds.append(function)
        elif "INSTRUCTOR" in holder_roles:
            kinds.append("COACH")
        if a.id in referee_athletes or (a.is_self and a.guardian_user_id in referee_users):
            kinds.append("REFEREE")
        rows.append({
            "kind": "ATHLETE", "id": a.id, "user_id": a.guardian_user_id if a.is_self else None,
            "name": f"{a.first_name} {a.last_name}", "kinds": kinds, "status": a.status,
            "photo_url": a.photo_url, "belt": belts.get(a.id),
            "age": seasons.age_on(a.birth_date, today),
            "email": emails.get(a.guardian_user_id), "guardian_name": names.get(a.guardian_user_id),
            "due_cents": int(due.get(a.id) or 0), "children": None,
            "social_tier": a.social_tier, "adapted_judo": a.adapted_judo,
        })
    for u in users:
        user_roles = set(roles.get(u.id) or [])
        if u.id in self_athlete_of:
            continue  # già nell'elenco come atleta, con i suoi tipi
        kinds: list[str] = []
        if "CUSTOMER" in user_roles:
            kinds.append("PARENT")
        if "SECRETARY" in user_roles:
            kinds.append("SECRETARY")
        if fn_by_user.get(u.id):
            kinds.append(fn_by_user[u.id])
        elif "INSTRUCTOR" in user_roles:
            kinds.append("COACH")
        if u.id in referee_users:
            kinds.append("REFEREE")
        if not kinds:
            continue
        family = children.get(u.id, [])
        rows.append({
            "kind": "USER", "id": u.id, "user_id": u.id, "name": names.get(u.id, u.email), "kinds": kinds,
            "status": "ACTIVE" if u.status == "ACTIVE" else "SUSPENDED", "photo_url": None, "belt": None,
            "age": None, "email": u.email, "guardian_name": None,
            "due_cents": int(member_due.get(u.id) or 0) + sum(int(due.get(a.id) or 0) for a in family),
            "children": [{"id": a.id, "name": f"{a.first_name} {a.last_name}"} for a in family],
            "social_tier": None, "adapted_judo": False,
        })
    rows.sort(key=lambda r: r["name"].lower())
    return rows


async def set_referee(
    db: AsyncSession, *, scope: ClubScope, actor_user_id: uuid.UUID, referee: bool,
    user_id: uuid.UUID | None = None, athlete_id: uuid.UUID | None = None,
) -> None:
    """Segna (o toglie) una persona del club come árbitro."""
    if (user_id is None) == (athlete_id is None):
        raise ClubValidationError("Indica una persona.")
    if user_id is not None:
        user = await db.get(User, user_id)
        if user is None or user.club_id != scope.club_id:
            raise ClubNotFoundError("Persona non trovata.")
        where = ClubReferee.user_id == user_id
    else:
        athlete = await db.get(ClubAthlete, athlete_id)
        if athlete is None or athlete.club_id != scope.club_id:
            raise ClubNotFoundError("Atleta non trovato.")
        where = ClubReferee.athlete_id == athlete_id
    existing = (
        await db.execute(select(ClubReferee).where(ClubReferee.club_id == scope.club_id, where))
    ).scalar_one_or_none()
    if referee and existing is None:
        db.add(ClubReferee(**scope.columns(), user_id=user_id, athlete_id=athlete_id))
    elif not referee and existing is not None:
        await db.delete(existing)
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.referee_set", entity_type="club", entity_id=str(scope.club_id),
        new_value={"user_id": str(user_id) if user_id else None,
                   "athlete_id": str(athlete_id) if athlete_id else None, "referee": referee},
    )
    await db.commit()


async def set_function(
    db: AsyncSession, *, scope: ClubScope, actor_user_id: uuid.UUID, function: str | None,
    user_id: uuid.UUID | None = None, athlete_id: uuid.UUID | None = None,
) -> None:
    """Assegna (o toglie, con None) la funzione a una persona del club."""
    if (user_id is None) == (athlete_id is None):
        raise ClubValidationError("Indica una persona.")
    if function is not None and function not in CLUB_FUNCTIONS:
        raise ClubValidationError("Funzione non valida.")
    if user_id is not None:
        user = await db.get(User, user_id)
        if user is None or user.club_id != scope.club_id:
            raise ClubNotFoundError("Persona non trovata.")
        if function in ("COACH", "ASSISTANT_COACH") and not await _has_role(db, user_id, "INSTRUCTOR"):
            raise ClubValidationError(
                "Per essere treinador serve un account da istruttore: aggiungilo da Impostazioni → Staff."
            )
        existing = (
            await db.execute(select(ClubFunction).where(ClubFunction.club_id == scope.club_id, ClubFunction.user_id == user_id))
        ).scalar_one_or_none()
    else:
        athlete = await db.get(ClubAthlete, athlete_id)
        if athlete is None or athlete.club_id != scope.club_id:
            raise ClubNotFoundError("Atleta non trovato.")
        if function in ("COACH", "ASSISTANT_COACH"):
            raise ClubValidationError("Treinador e treinador adjunto sono account dello staff, non atleti.")
        existing = (
            await db.execute(
                select(ClubFunction).where(ClubFunction.club_id == scope.club_id, ClubFunction.athlete_id == athlete_id)
            )
        ).scalar_one_or_none()
    if function is None:
        if existing is not None:
            await db.delete(existing)
    elif existing is not None:
        existing.function = function
    else:
        db.add(ClubFunction(**scope.columns(), function=function, user_id=user_id, athlete_id=athlete_id))
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.function_set", entity_type="club", entity_id=str(scope.club_id),
        new_value={"user_id": str(user_id) if user_id else None,
                   "athlete_id": str(athlete_id) if athlete_id else None, "function": function},
    )
    await db.commit()


async def _has_role(db: AsyncSession, user_id: uuid.UUID, code: str) -> bool:
    return (
        await db.execute(
            select(UserRole.id).join(Role, Role.id == UserRole.role_id).where(UserRole.user_id == user_id, Role.code == code)
        )
    ).first() is not None


async def person_card(db: AsyncSession, *, scope: ClubScope, athlete_id: uuid.UUID | None = None,
                      user_id: uuid.UUID | None = None) -> dict:
    """La scheda di una persona: debiti, pagamenti, risultati, investimenti.
    Per un genitore, quelli di tutta la famiglia."""
    from app.domains.club.family import fee_dict
    from app.domains.wallets.models import Wallet, WalletTransaction

    today = utcnow().date()
    if athlete_id is not None:
        athlete = await db.get(ClubAthlete, athlete_id)
        if athlete is None or athlete.club_id != scope.club_id:
            raise ClubNotFoundError("Atleta non trovato.")
        athletes = [athlete]
        guardian_id = athlete.guardian_user_id
        include_membership = athlete.is_self
    else:
        user = await db.get(User, user_id)
        if user is None or user.club_id != scope.club_id:
            raise ClubNotFoundError("Persona non trovata.")
        athletes = list(
            (
                await db.execute(
                    select(ClubAthlete).where(ClubAthlete.club_id == scope.club_id, ClubAthlete.guardian_user_id == user.id)
                )
            ).scalars()
        )
        guardian_id = user.id
        include_membership = True
    by_id = {a.id: a for a in athletes}
    ids = list(by_id)
    fee_filter = ClubFee.athlete_id.in_(ids) if ids else ClubFee.id.is_(None)
    if include_membership:
        fee_filter = fee_filter | ((ClubFee.kind == "MEMBERSHIP") & (ClubFee.guardian_user_id == guardian_id))
    fees = list(
        (
            await db.execute(
                select(ClubFee).where(ClubFee.club_id == scope.club_id, fee_filter).order_by(ClubFee.due_date.desc())
            )
        ).scalars()
    )
    proofs = list(
        (
            await db.execute(
                select(ClubPaymentProof)
                .where(ClubPaymentProof.club_id == scope.club_id, ClubPaymentProof.uploaded_by_user_id == guardian_id)
                .order_by(ClubPaymentProof.created_at.desc())
                .limit(50)
            )
        ).scalars()
    )
    results = (
        await db.execute(
            select(ClubCompetitionEntry, ClubCompetition)
            .join(ClubCompetition, ClubCompetition.id == ClubCompetitionEntry.competition_id)
            .where(ClubCompetitionEntry.athlete_id.in_(ids) if ids else ClubCompetitionEntry.id.is_(None))
            .order_by(ClubCompetition.starts_on.desc())
        )
    ).all()
    investments = (
        await db.execute(
            select(WalletTransaction)
            .join(Wallet, Wallet.id == WalletTransaction.to_wallet_id)
            .where(
                WalletTransaction.source == INVESTMENT_SOURCE,
                WalletTransaction.reference_club_athlete_id.in_(ids) if ids else WalletTransaction.id.is_(None),
            )
            .order_by(WalletTransaction.created_at.desc())
        )
    ).scalars().all()
    belts = await current_belts(db, athlete_ids=ids)
    from app.domains.club.competitions import points_for

    return {
        "debts": [fee_dict(f, today=today, athlete=by_id.get(f.athlete_id)) for f in fees if f.status == "DUE"],
        "payments": [fee_dict(f, today=today, athlete=by_id.get(f.athlete_id)) for f in fees if f.status == "PAID"],
        "proofs": [
            {"id": p.id, "created_at": p.created_at, "amount_cents": p.amount_cents, "credit_cents": p.credit_cents,
             "status": p.status, "has_file": p.storage_key is not None}
            for p in proofs
        ],
        "results": [
            {"competition_id": c.id, "name": c.name, "starts_on": c.starts_on, "kind": c.kind, "level": c.level,
             "athlete_name": f"{by_id[e.athlete_id].first_name} {by_id[e.athlete_id].last_name}",
             "placement": e.placement, "status": e.status,
             "points": points_for(placement=e.placement, level=c.level)
             if e.status == "REGISTERED" and c.kind == "COMPETITION" else 0}
            for e, c in results
        ],
        "belts": [
            {"athlete_name": f"{a.first_name} {a.last_name}", "belt": belts_catalog.get(belts[a.id]).label}
            for a in athletes if a.id in belts
        ],
        "investments": [
            {"id": t.id, "created_at": t.created_at, "amount_cents": t.amount_cents, "note": t.note,
             "athlete_name": _full_name(by_id.get(t.reference_club_athlete_id))}
            for t in investments
        ],
        "totals": {
            "debt_cents": sum(f.amount_cents for f in fees if f.status == "DUE"),
            "paid_cents": sum(f.amount_cents for f in fees if f.status == "PAID"),
            "invested_cents": sum(t.amount_cents for t in investments),
        },
    }


def _full_name(athlete: ClubAthlete | None) -> str | None:
    return f"{athlete.first_name} {athlete.last_name}" if athlete is not None else None


async def invest(
    db: AsyncSession, *, scope: ClubScope, athlete_id: uuid.UUID, amount_cents: int, note: str,
    actor_user_id: uuid.UUID, on: date | None = None,
) -> dict:
    """Il club investe su un atleta: ricarica il wallet della sua famiglia,
    con il motivo. Lo stesso investimento (stesso atleta, importo e motivo)
    due volte nello stesso giorno è un doppio clic, non un secondo
    investimento: la chiave del movimento lo impedisce."""
    from app.domains.wallets import service as wallets_service

    athlete = await db.get(ClubAthlete, athlete_id)
    if athlete is None or athlete.club_id != scope.club_id:
        raise ClubNotFoundError("Atleta non trovato.")
    if amount_cents <= 0:
        raise ClubValidationError("L'importo deve essere maggiore di zero.")
    note = note.strip()
    if len(note) < 3:
        raise ClubValidationError("Scrivi il motivo dell'investimento: la famiglia lo legge nel wallet.")
    day = (on or utcnow().date()).isoformat()
    wallet = await wallets_service.get_or_create_wallet(
        db, organization_id=scope.organization_id, user_id=athlete.guardian_user_id
    )
    # hashlib e non hash(): quello di Python cambia a ogni avvio del processo.
    digest = hashlib.sha256(note.encode()).hexdigest()[:16]
    key = f"club-investment:{athlete.id}:{amount_cents}:{day}:{digest}"
    txn = await wallets_service.credit_wallet(
        db, organization_id=scope.organization_id, wallet_id=wallet.id, amount_cents=amount_cents,
        type_="ADMIN_CREDIT", actor_user_id=actor_user_id, reference_club_athlete_id=athlete.id,
        source=INVESTMENT_SOURCE, note=f"Investimento del club per {athlete.first_name}: {note}"[:500],
        idempotency_key=key,
    )
    return {"id": txn.id, "amount_cents": txn.amount_cents, "created_at": txn.created_at, "note": txn.note}
