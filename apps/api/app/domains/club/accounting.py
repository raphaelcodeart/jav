"""La contabilità: del club, della piattaforma, di ogni famiglia.

Tutto quello che qui si legge si **calcola** da ciò che il gestionale sa già
(quote, prove di pagamento, cartellino, ordini dello Shop) più i pochi fatti
che solo la segreteria conosce (spese, costi fissi, tariffe orarie) e la
percentuale decisa dal superadmin. Niente totali salvati: una quota corretta,
una prova rifiutata, un turno sistemato correggono subito ogni numero
(docs/club-portal.md, "Contabilità").

Le regole, in breve:

- **incasso** = quote PAGATE, nel mese in cui sono state pagate (`paid_at`),
  non in quello in cui scadevano: è il denaro entrato davvero. Ne fa parte
  anche ciò che la famiglia ha pagato con il credito del wallet (lo si
  mostra a parte, perché quella parte non arriva con un bonifico);
- **emesso** = quote con scadenza nel periodo, condonate escluse; il tasso
  di riscossione è la parte di queste già pagata;
- **mancati incassi** = sconti (escalão, famiglia), taxa de falta e condoni
  delle quote con scadenza nel periodo: denaro a cui il club ha rinunciato;
- **costi** = spese registrate (comprese quelle dei costi fissi) + costo
  dello staff dal cartellino (ore dei turni chiusi × tariffa valida quel
  giorno);
- **commissione della piattaforma** = percentuale degli incassi del mese,
  con la percentuale valida quel mese (default 10%);
- **risultato** = incassi − costi − commissione;
- **corsi JAV** (club/kinds.py): niente commissione (i soldi sono già di
  JAV); il treinador responsabile di un corso prende la sua percentuale di
  ogni mensilità del corso pagata nel mese (corso, treinador e percentuale
  congelati sulla quota all'emissione). È un costo come lo staff a ore, e
  ciò che resta è la parte di JAV;
- **debiti** = quote DA PAGARE oggi, per anzianità dalla scadenza.

Ogni funzione riceve il suo perimetro: un `ClubScope` per il club, l'id
dell'organizzazione per la piattaforma, il club e l'utente per la famiglia.
Le query sono raggruppate (una per tipo di dato, mai una per mese o per
atleta).
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.club import kinds
from app.domains.club.models import (
    DEFAULT_PLATFORM_FEE_PCT,
    EXPENSE_CATEGORIES,
    EXPENSE_PAYMENT_METHODS,
    FEE_KINDS,
    Club,
    ClubAthlete,
    ClubExpense,
    ClubFee,
    ClubPaymentProof,
    ClubPlatformFee,
    ClubRecurringExpense,
    ClubStaffRate,
    ClubWorkSession,
)
from app.domains.club.scope import ClubScope
from app.domains.club.service import ClubNotFoundError, ClubValidationError

logger = logging.getLogger(__name__)

#: Le fasce di anzianità dei debiti, in giorni dopo la scadenza (inclusi).
AGING_BUCKETS = (("NOT_DUE", None, 0), ("D0_30", 1, 30), ("D31_60", 31, 60), ("D61_90", 61, 90), ("D90_PLUS", 91, None))
#: Quanti mesi indietro si può far partire un costo fisso: oltre, è un
#: errore di battitura più che un affitto di tre anni fa.
RECURRING_BACKFILL_MONTHS = 24
#: Le righe massime del libro cassa in una risposta; oltre si restringe il periodo.
LEDGER_LIMIT = 3000


# --- Periodi --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Period:
    """Un mese (`2026-10`) o un anno (`2026`): `start` incluso, `end` escluso."""

    key: str
    kind: str
    start: date
    end: date

    @property
    def months(self) -> list[str]:
        return months_between(self.start, self.end)


def _add_months(d: date, n: int) -> date:
    index = d.year * 12 + d.month - 1 + n
    return date(index // 12, index % 12 + 1, 1)


def months_between(start: date, end: date) -> list[str]:
    out, cur = [], date(start.year, start.month, 1)
    while cur < end:
        out.append(f"{cur.year:04d}-{cur.month:02d}")
        cur = _add_months(cur, 1)
    return out


def month_start(month: str) -> date:
    year, mon = (int(x) for x in month.split("-"))
    return date(year, mon, 1)


def parse_period(value: str | None, *, today: date) -> Period:
    """`YYYY-MM` o `YYYY`; vuoto = il mese in corso."""
    value = (value or "").strip() or f"{today.year:04d}-{today.month:02d}"
    try:
        if len(value) == 4:
            year = int(value)
            if not 2000 <= year <= 2100:
                raise ValueError
            return Period(key=value, kind="year", start=date(year, 1, 1), end=date(year + 1, 1, 1))
        start = month_start(value)
        if not 2000 <= start.year <= 2100 or len(value) != 7:
            raise ValueError
    except ValueError as exc:
        raise ClubValidationError("Il periodo è un mese (AAAA-MM) o un anno (AAAA).") from exc
    return Period(key=value, kind="month", start=start, end=_add_months(start, 1))


def _utc(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=UTC)


def _month_of(column):
    """Il mese (`YYYY-MM`) di una data o di un istante, in UTC: lo stesso
    taglio dei confini dei periodi."""
    return func.to_char(func.timezone("UTC", column), "YYYY-MM")


def _date_month(column):
    return func.to_char(column, "YYYY-MM")


# --- La commissione della piattaforma --------------------------------------------------------------


def fee_cents(income_cents: int, pct: Decimal) -> int:
    """La commissione su un incasso, arrotondata al centesimo (metà in su)."""
    return int((Decimal(income_cents) * pct / Decimal(100)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


async def _fee_history(db: AsyncSession, club_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[tuple[date, Decimal]]]:
    rows = (
        await db.execute(
            select(ClubPlatformFee.club_id, ClubPlatformFee.valid_from, ClubPlatformFee.pct)
            .where(ClubPlatformFee.club_id.in_(club_ids))
            .order_by(ClubPlatformFee.valid_from)
        )
    ).all() if club_ids else []
    out: dict[uuid.UUID, list[tuple[date, Decimal]]] = {}
    for club_id, valid_from, pct in rows:
        out.setdefault(club_id, []).append((valid_from, Decimal(pct)))
    return out


async def _club_kinds(db: AsyncSession, club_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not club_ids:
        return {}
    return dict((await db.execute(select(Club.id, Club.kind).where(Club.id.in_(club_ids)))).all())


def pct_on(history: list[tuple[date, Decimal]], month: str, *, kind: str | None = None) -> Decimal:
    """La percentuale valida in quel mese: l'ultima decisa da quel mese o
    prima; senza decisioni, il default del tipo di unità. Dove il tipo la
    fissa (i corsi JAV: 0%) lo storico non conta."""
    rules = kinds.rules_for(kind)
    if not rules.platform_fee_editable:
        return rules.default_platform_fee_pct
    first = month_start(month)
    pct = rules.default_platform_fee_pct if kind else DEFAULT_PLATFORM_FEE_PCT
    for valid_from, value in history:
        if valid_from <= first:
            pct = value
    return pct


async def set_platform_fee(
    db: AsyncSession, *, organization_id: uuid.UUID, club_id: uuid.UUID, pct: Decimal, actor_user_id: uuid.UUID,
    today: date | None = None,
) -> dict:
    """La percentuale vale dal mese in corso in poi: i mesi chiusi restano
    calcolati con quella che valeva allora. Cambiarla due volte nello stesso
    mese aggiorna la stessa riga (UNIQUE club + mese)."""
    today = today or utcnow().date()
    club = await db.get(Club, club_id)
    if club is None or club.organization_id != organization_id:
        raise ClubNotFoundError("Club non trovato.")
    if not kinds.rules_of(club).platform_fee_editable:
        raise ClubValidationError(kinds.NO_PLATFORM_FEE)
    pct = Decimal(pct).quantize(Decimal("0.01"))
    if not Decimal(0) <= pct <= Decimal(100):
        raise ClubValidationError("La percentuale va da 0 a 100.")
    valid_from = date(today.year, today.month, 1)
    previous = pct_on(
        (await _fee_history(db, [club_id])).get(club_id, []), f"{today.year:04d}-{today.month:02d}", kind=club.kind
    )
    await db.execute(
        insert(ClubPlatformFee)
        .values(
            id=uuid.uuid4(), created_at=utcnow(), organization_id=organization_id, club_id=club_id, pct=pct,
            valid_from=valid_from, set_by_user_id=actor_user_id,
        )
        .on_conflict_do_update(
            constraint="uq_club_platform_fees_club_from", set_={"pct": pct, "set_by_user_id": actor_user_id}
        )
    )
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="clubs.platform_fee_set", entity_type="club", entity_id=str(club_id),
        previous_value={"pct": str(previous)}, new_value={"pct": str(pct), "valid_from": valid_from.isoformat()},
    )
    await db.commit()
    return {"club_id": club_id, "pct": pct, "valid_from": valid_from}


# --- I numeri di un mese, club per club ------------------------------------------------------------


@dataclass
class Figures:
    """I numeri di un club in un mese (o la somma di più mesi)."""

    income_by_kind: dict[str, int] = field(default_factory=dict)
    credit_cents: int = 0
    issued_cents: int = 0
    issued_paid_cents: int = 0
    discounts_cents: int = 0
    absence_cents: int = 0
    waived_cents: int = 0
    #: Mensilità esenti («Isenta este mês»): fuori dall'emesso e dai mancati incassi.
    exempt_cents: int = 0
    expenses_by_category: dict[str, int] = field(default_factory=dict)
    staff_cents: int = 0
    staff_minutes: int = 0
    platform_fee_cents: int = 0
    #: Corsi JAV: la parte dei treinador sulle mensilità dei loro corsi
    #: pagate nel mese, e gli incassi delle quote attribuite a un corso.
    coach_share_cents: int = 0
    course_income_cents: int = 0

    @property
    def income_cents(self) -> int:
        return sum(self.income_by_kind.values())

    @property
    def expenses_cents(self) -> int:
        return sum(self.expenses_by_category.values())

    @property
    def costs_cents(self) -> int:
        return self.expenses_cents + self.staff_cents + self.coach_share_cents

    @property
    def result_cents(self) -> int:
        return self.income_cents - self.costs_cents - self.platform_fee_cents

    def add(self, other: "Figures") -> "Figures":
        for kind, cents in other.income_by_kind.items():
            self.income_by_kind[kind] = self.income_by_kind.get(kind, 0) + cents
        for cat, cents in other.expenses_by_category.items():
            self.expenses_by_category[cat] = self.expenses_by_category.get(cat, 0) + cents
        for name in ("credit_cents", "issued_cents", "issued_paid_cents", "discounts_cents", "absence_cents",
                     "waived_cents", "exempt_cents", "staff_cents", "staff_minutes", "platform_fee_cents", "coach_share_cents",
                     "course_income_cents"):
            setattr(self, name, getattr(self, name) + getattr(other, name))
        return self

    def as_dict(self) -> dict:
        return {
            "income_cents": self.income_cents,
            "income_by_kind": {kind: self.income_by_kind.get(kind, 0) for kind in FEE_KINDS},
            "credit_cents": self.credit_cents,
            "issued_cents": self.issued_cents,
            "issued_paid_cents": self.issued_paid_cents,
            "collection_rate": round(self.issued_paid_cents * 100 / self.issued_cents) if self.issued_cents else None,
            "discounts_cents": self.discounts_cents,
            "absence_cents": self.absence_cents,
            "waived_cents": self.waived_cents,
            "missed_cents": self.discounts_cents + self.absence_cents + self.waived_cents,
            "exempt_cents": self.exempt_cents,
            "expenses_cents": self.expenses_cents,
            "expenses_by_category": {cat: self.expenses_by_category.get(cat, 0) for cat in EXPENSE_CATEGORIES},
            "staff_cents": self.staff_cents,
            "staff_minutes": self.staff_minutes,
            "coach_share_cents": self.coach_share_cents,
            # Ciò che dell'incasso resta all'unità dopo la parte dei treinador:
            # nei corsi JAV è la parte di JudoArteVida.
            "kept_cents": self.income_cents - self.coach_share_cents,
            "costs_cents": self.costs_cents,
            "platform_fee_cents": self.platform_fee_cents,
            "result_cents": self.result_cents,
        }


def _session_minutes(session_start: datetime, session_end: datetime) -> int:
    return max(int((session_end - session_start).total_seconds() // 60), 0)


def _rate_on(rates: list[tuple[date, int]], day: date) -> int:
    rate = 0
    for valid_from, cents in rates:
        if valid_from <= day:
            rate = cents
    return rate


async def _staff_rates(db: AsyncSession, club_ids: list[uuid.UUID]) -> dict[tuple[uuid.UUID, uuid.UUID], list[tuple[date, int]]]:
    rows = (
        await db.execute(
            select(ClubStaffRate.club_id, ClubStaffRate.user_id, ClubStaffRate.valid_from, ClubStaffRate.hourly_rate_cents)
            .where(ClubStaffRate.club_id.in_(club_ids))
            .order_by(ClubStaffRate.valid_from)
        )
    ).all() if club_ids else []
    out: dict[tuple[uuid.UUID, uuid.UUID], list[tuple[date, int]]] = {}
    for club_id, user_id, valid_from, cents in rows:
        out.setdefault((club_id, user_id), []).append((valid_from, int(cents)))
    return out


async def staff_sessions(
    db: AsyncSession, *, club_ids: list[uuid.UUID], start: date, end: date
) -> list[tuple[uuid.UUID, uuid.UUID, datetime, datetime]]:
    """I turni **chiusi** iniziati nel periodo: un turno ancora aperto (o
    un'uscita dimenticata) non diventa un costo finché qualcuno non lo chiude
    o la segreteria non lo corregge."""
    if not club_ids:
        return []
    return [
        tuple(r)
        for r in (
            await db.execute(
                select(ClubWorkSession.club_id, ClubWorkSession.user_id, ClubWorkSession.started_at, ClubWorkSession.ended_at)
                .where(
                    ClubWorkSession.club_id.in_(club_ids), ClubWorkSession.ended_at.is_not(None),
                    ClubWorkSession.started_at >= _utc(start), ClubWorkSession.started_at < _utc(end),
                )
            )
        ).all()
    ]


async def monthly_figures(
    db: AsyncSession, *, club_ids: list[uuid.UUID], start: date, end: date,
) -> dict[tuple[uuid.UUID, str], Figures]:
    """I numeri di ogni (club, mese) tra `start` e `end`: cinque query
    raggruppate in tutto, qualunque sia il numero di club e di mesi."""
    out: dict[tuple[uuid.UUID, str], Figures] = {}
    if not club_ids:
        return out

    def at(club_id: uuid.UUID, month: str) -> Figures:
        return out.setdefault((club_id, month), Figures())

    paid_month = _month_of(ClubFee.paid_at)
    for club_id, month, kind, cents in (
        await db.execute(
            select(ClubFee.club_id, paid_month, ClubFee.kind, func.sum(ClubFee.amount_cents))
            .where(
                ClubFee.club_id.in_(club_ids), ClubFee.status == "PAID",
                ClubFee.paid_at >= _utc(start), ClubFee.paid_at < _utc(end),
            )
            .group_by(ClubFee.club_id, paid_month, ClubFee.kind)
        )
    ).all():
        at(club_id, month).income_by_kind[kind] = int(cents or 0)

    proof_month = _month_of(ClubPaymentProof.created_at)
    for club_id, month, cents in (
        await db.execute(
            select(ClubPaymentProof.club_id, proof_month, func.sum(ClubPaymentProof.credit_cents))
            .where(
                ClubPaymentProof.club_id.in_(club_ids), ClubPaymentProof.status == "ACCEPTED",
                ClubPaymentProof.credit_cents > 0,
                ClubPaymentProof.created_at >= _utc(start), ClubPaymentProof.created_at < _utc(end),
            )
            .group_by(ClubPaymentProof.club_id, proof_month)
        )
    ).all():
        at(club_id, month).credit_cents = int(cents or 0)

    due_month = _date_month(ClubFee.due_date)
    zero = 0
    # Un mese esente («Isenta este mês») esce dal mese del tutto: né emesso,
    # né mancato incasso (i suoi sconti compresi); si conta a parte.
    exempt = func.coalesce(ClubFee.waive_kind, "") == "EXEMPT"
    for club_id, month, issued, issued_paid, discounts, absence, waived, exempted in (
        await db.execute(
            select(
                ClubFee.club_id, due_month,
                func.sum(_case(ClubFee.status != "WAIVED", ClubFee.amount_cents, zero)),
                func.sum(_case(ClubFee.status == "PAID", ClubFee.amount_cents, zero)),
                func.sum(_case(exempt, zero, ClubFee.discount_cents)),
                func.sum(_case(exempt, zero, absence_cents_sql())),
                func.sum(_case((ClubFee.status == "WAIVED") & ~exempt, ClubFee.amount_cents, zero)),
                func.sum(_case(exempt, ClubFee.amount_cents, zero)),
            )
            .where(ClubFee.club_id.in_(club_ids), ClubFee.due_date >= start, ClubFee.due_date < end)
            .group_by(ClubFee.club_id, due_month)
        )
    ).all():
        f = at(club_id, month)
        f.issued_cents, f.issued_paid_cents = int(issued or 0), int(issued_paid or 0)
        f.discounts_cents, f.absence_cents, f.waived_cents = int(discounts or 0), int(absence or 0), int(waived or 0)
        f.exempt_cents = int(exempted or 0)

    spent_month = _date_month(ClubExpense.spent_on)
    for club_id, month, category, cents in (
        await db.execute(
            select(ClubExpense.club_id, spent_month, ClubExpense.category, func.sum(ClubExpense.amount_cents))
            .where(ClubExpense.club_id.in_(club_ids), ClubExpense.spent_on >= start, ClubExpense.spent_on < end)
            .group_by(ClubExpense.club_id, spent_month, ClubExpense.category)
        )
    ).all():
        at(club_id, month).expenses_by_category[category] = int(cents or 0)

    rates = await _staff_rates(db, club_ids)
    for club_id, user_id, started_at, ended_at in await staff_sessions(db, club_ids=club_ids, start=start, end=end):
        day = started_at.astimezone(UTC).date()
        minutes = _session_minutes(started_at, ended_at)
        f = at(club_id, f"{day.year:04d}-{day.month:02d}")
        f.staff_minutes += minutes
        f.staff_cents += round(minutes * _rate_on(rates.get((club_id, user_id), []), day) / 60)

    for club_id, month, cents, share in await coach_share_rows(db, club_ids=club_ids, start=start, end=end):
        f = at(club_id, month)
        f.course_income_cents += cents
        f.coach_share_cents += share

    history = await _fee_history(db, club_ids)
    club_kinds = await _club_kinds(db, club_ids)
    for (club_id, month), f in out.items():
        f.platform_fee_cents = fee_cents(
            f.income_cents, pct_on(history.get(club_id, []), month, kind=club_kinds.get(club_id))
        )
    return out


async def coach_share_rows(
    db: AsyncSession, *, club_ids: list[uuid.UUID], start: date, end: date,
) -> list[tuple[uuid.UUID, str, int, int]]:
    """(club, mese, incasso delle quote con un treinador, sua parte): le
    mensilità dei corsi JAV pagate nel periodo, raggruppate per corso,
    treinador e percentuale congelati sulla quota. La parte si arrotonda al
    centesimo (metà in su) gruppo per gruppo, come la commissione."""
    return [
        (club_id, month, cents, share)
        for club_id, month, _course, _coach, cents, share in await _share_groups(
            db, club_ids=club_ids, start=start, end=end,
        )
    ]


async def _share_groups(
    db: AsyncSession, *, club_ids: list[uuid.UUID], start: date | None, end: date | None,
    coach_user_id: uuid.UUID | None = None,
) -> list[tuple[uuid.UUID, str, uuid.UUID | None, uuid.UUID | None, int, int]]:
    if not club_ids:
        return []
    paid_month = _month_of(ClubFee.paid_at)
    stmt = (
        select(ClubFee.club_id, paid_month, ClubFee.course_id, ClubFee.coach_user_id, ClubFee.coach_share_pct,
               func.sum(ClubFee.amount_cents))
        .where(ClubFee.club_id.in_(club_ids), ClubFee.status == "PAID", ClubFee.paid_at.is_not(None),
               ClubFee.coach_share_pct.is_not(None))
        .group_by(ClubFee.club_id, paid_month, ClubFee.course_id, ClubFee.coach_user_id, ClubFee.coach_share_pct)
    )
    if start is not None:
        stmt = stmt.where(ClubFee.paid_at >= _utc(start))
    if end is not None:
        stmt = stmt.where(ClubFee.paid_at < _utc(end))
    if coach_user_id is not None:
        stmt = stmt.where(ClubFee.coach_user_id == coach_user_id)
    return [
        (club_id, month, course_id, coach_id, int(cents or 0), fee_cents(int(cents or 0), Decimal(pct)))
        for club_id, month, course_id, coach_id, pct, cents in (await db.execute(stmt)).all()
    ]


def _case(condition, then, otherwise):
    return case((condition, then), else_=otherwise)


def absence_cents(fee: ClubFee) -> int:
    """Quanto ha tolto la taxa de falta: si calcola dal netto congelato
    (absence.py::apply), non da `amount_cents`, che un pagamento parziale
    riduce alla parte pagata (club/fee_splits.py)."""
    gross = fee.gross_amount_cents if fee.gross_amount_cents is not None else fee.amount_cents
    net = gross - (fee.discount_cents or 0)
    return {"HALF": net - net // 2, "FULL": net}.get(fee.absence_adjustment or "", 0)


def absence_cents_sql():
    """absence_cents() in SQL, per le somme raggruppate."""
    net = func.coalesce(ClubFee.gross_amount_cents, ClubFee.amount_cents) - ClubFee.discount_cents
    return case(
        (ClubFee.absence_adjustment == "HALF", net - net // 2), (ClubFee.absence_adjustment == "FULL", net), else_=0,
    )


async def expected_coach_share(db: AsyncSession, *, club_ids: list[uuid.UUID], start: date, end: date) -> int:
    """La parte dei treinador delle mensilità che scadono nel periodo e non
    sono ancora pagate: per la previsione del mese."""
    if not club_ids:
        return 0
    rows = (
        await db.execute(
            select(ClubFee.coach_share_pct, func.sum(ClubFee.amount_cents))
            .where(ClubFee.club_id.in_(club_ids), ClubFee.status == "DUE", ClubFee.coach_share_pct.is_not(None),
                   ClubFee.due_date >= start, ClubFee.due_date < end)
            .group_by(ClubFee.coach_share_pct)
        )
    ).all()
    return sum(fee_cents(int(cents or 0), Decimal(pct)) for pct, cents in rows)


def _sum(figures: dict[tuple[uuid.UUID, str], Figures], *, months: list[str], club_id: uuid.UUID | None = None) -> Figures:
    total = Figures()
    wanted = set(months)
    for (cid, month), f in figures.items():
        if month in wanted and (club_id is None or cid == club_id):
            total.add(f)
    return total


# --- Debiti ---------------------------------------------------------------------------------------


def aging_bucket(due_date: date, today: date) -> str:
    days = (today - due_date).days
    for key, low, high in AGING_BUCKETS:
        if (low is None or days >= low) and (high is None or days <= high):
            return key
    return "D90_PLUS"


async def _due_rows(db: AsyncSession, club_ids: list[uuid.UUID]):
    """Le quote da pagare con la famiglia a cui appartengono: il genitore
    dell'atleta, o il genitore stesso per la quota socio."""
    if not club_ids:
        return []
    family = func.coalesce(ClubAthlete.guardian_user_id, ClubFee.guardian_user_id)
    return (
        await db.execute(
            select(ClubFee.club_id, family, ClubFee.due_date, ClubFee.amount_cents)
            .outerjoin(ClubAthlete, ClubAthlete.id == ClubFee.athlete_id)
            .where(ClubFee.club_id.in_(club_ids), ClubFee.status == "DUE", ClubFee.amount_cents > 0)
        )
    ).all()


def _empty_aging() -> dict[str, dict]:
    return {key: {"cents": 0, "count": 0} for key, _low, _high in AGING_BUCKETS}


async def debts(db: AsyncSession, *, scope: ClubScope, today: date, limit: int | None = 10) -> dict:
    """Quanto devono le famiglie oggi, per anzianità, e chi deve di più."""
    from app.domains.club.people import _names

    aging = _empty_aging()
    families: dict[uuid.UUID, dict] = {}
    for _club_id, family_id, due_date, cents in await _due_rows(db, [scope.club_id]):
        bucket = aging_bucket(due_date, today)
        aging[bucket]["cents"] += int(cents)
        aging[bucket]["count"] += 1
        if family_id is None:
            continue
        row = families.setdefault(family_id, {
            "user_id": family_id, "due_cents": 0, "overdue_cents": 0, "fees": 0, "oldest_due_date": due_date,
        })
        row["due_cents"] += int(cents)
        row["fees"] += 1
        if due_date < today:
            row["overdue_cents"] += int(cents)
        row["oldest_due_date"] = min(row["oldest_due_date"], due_date)
    ranked = sorted(families.values(), key=lambda r: (-r["overdue_cents"], -r["due_cents"]))
    if limit is not None:
        ranked = ranked[:limit]
    names = await _names(db, {r["user_id"] for r in ranked})
    for r in ranked:
        r["name"] = names.get(r["user_id"], "")
        r["days_overdue"] = max((today - r["oldest_due_date"]).days, 0)
    total = sum(b["cents"] for b in aging.values())
    return {
        "total_cents": total,
        "overdue_cents": total - aging["NOT_DUE"]["cents"],
        "families": len(families),
        "aging": aging,
        "top": ranked,
    }


# --- La contabilità del club ---------------------------------------------------------------------


def _comparison_months(period: Period, today: date) -> tuple[list[str], list[str]]:
    """I mesi del periodo da confrontare e quelli dell'anno prima. Per l'anno
    in corso si confronta da gennaio a oggi con lo stesso tratto dell'anno
    prima: confrontare dieci mesi con dodici sarebbe ingannevole."""
    months = period.months
    if period.kind == "year" and period.start.year == today.year:
        months = [m for m in months if month_start(m) <= today]
    previous = [f"{int(m[:4]) - 1:04d}{m[4:]}" for m in months]
    return months, previous


async def club_summary(db: AsyncSession, *, scope: ClubScope, period: Period, today: date) -> dict:
    """Conto economico del periodo, con l'andamento di dodici mesi, il
    confronto con l'anno prima, la previsione del mese e i debiti di oggi."""
    range_start = date(period.start.year - 1, 1, 1)
    figures = await monthly_figures(db, club_ids=[scope.club_id], start=range_start, end=period.end)
    series_months = period.months if period.kind == "year" else months_between(_add_months(period.start, -11), period.end)
    totals = _sum(figures, months=period.months)
    months, previous_months = _comparison_months(period, today)
    history = (await _fee_history(db, [scope.club_id])).get(scope.club_id, [])
    last_month = period.months[-1]
    club = await db.get(Club, scope.club_id)
    club_kind = club.kind if club is not None else None

    out = {
        "period": period.key,
        "kind": period.kind,
        "club_kind": club_kind,
        "start": period.start,
        "end": period.end - timedelta(days=1),
        "platform_fee_pct": pct_on(history, last_month, kind=club_kind),
        "totals": totals.as_dict(),
        "compared_months": months,
        "current": _sum(figures, months=months).as_dict(),
        "previous": _sum(figures, months=previous_months).as_dict(),
        "series": [
            {"month": m, **{k: v for k, v in _sum(figures, months=[m]).as_dict().items()
                            if k in ("income_cents", "costs_cents", "platform_fee_cents", "result_cents")}}
            for m in series_months
        ],
        "ytd": None,
        "ytd_previous": None,
        "forecast": None,
        "debts": await debts(db, scope=scope, today=today),
    }
    if period.kind == "month":
        ytd = months_between(date(period.start.year, 1, 1), period.end)
        out["ytd"] = _sum(figures, months=ytd).as_dict()
        out["ytd_previous"] = _sum(figures, months=[f"{int(m[:4]) - 1:04d}{m[4:]}" for m in ytd]).as_dict()
        if period.end > today:
            # Il mese non è finito: quanto entrerà se le famiglie pagano le
            # quote che scadono nel mese e non sono ancora pagate.
            expected = totals.issued_cents - totals.issued_paid_cents
            income = totals.income_cents + expected
            fee = fee_cents(income, pct_on(history, last_month, kind=club_kind))
            # Nei corsi JAV anche la parte dei treinador delle quote che
            # devono ancora entrare.
            share = await expected_coach_share(db, club_ids=[scope.club_id], start=period.start, end=period.end)
            out["forecast"] = {
                "expected_cents": expected,
                "income_cents": income,
                "platform_fee_cents": fee,
                "result_cents": income - totals.costs_cents - share - fee,
            }
    return out


# --- Libro cassa ----------------------------------------------------------------------------------


async def ledger(
    db: AsyncSession, *, scope: ClubScope, period: Period, kind: str | None = None, q: str | None = None,
) -> dict:
    """Entrate e uscite del periodo in un elenco solo, dalla più recente: le
    quote pagate, le spese, e una riga al mese per il costo dello staff e
    per la commissione della piattaforma (calcolati, e lo dicono)."""
    from app.domains.club.people import _names

    rows: list[dict] = []
    if kind in (None, "", "INCOME"):
        fees = (
            await db.execute(
                select(ClubFee, ClubAthlete)
                .outerjoin(ClubAthlete, ClubAthlete.id == ClubFee.athlete_id)
                .where(
                    ClubFee.club_id == scope.club_id, ClubFee.status == "PAID",
                    ClubFee.paid_at >= _utc(period.start), ClubFee.paid_at < _utc(period.end),
                )
                .order_by(ClubFee.paid_at.desc())
                .limit(LEDGER_LIMIT + 1)
            )
        ).all()
        families = {a.guardian_user_id if a is not None else f.guardian_user_id for f, a in fees}
        names = await _names(db, {u for u in families if u})
        for fee, athlete in fees:
            family = athlete.guardian_user_id if athlete is not None else fee.guardian_user_id
            rows.append({
                "id": str(fee.id), "date": fee.paid_at.astimezone(UTC).date(), "type": "INCOME", "category": fee.kind,
                "description": fee.description,
                "counterparty": (f"{athlete.first_name} {athlete.last_name}" if athlete is not None else names.get(family, "")),
                "family": names.get(family, ""),
                "amount_cents": fee.amount_cents,
                "method": "PROOF" if fee.paid_via_proof_id else "MANUAL",
                "has_receipt": False, "expense_id": None, "recurring": False, "computed": False,
            })
    if kind in (None, "", "EXPENSE"):
        expenses = (
            await db.execute(
                select(ClubExpense)
                .where(ClubExpense.club_id == scope.club_id, ClubExpense.spent_on >= period.start, ClubExpense.spent_on < period.end)
                .order_by(ClubExpense.spent_on.desc())
                .limit(LEDGER_LIMIT + 1)
            )
        ).scalars().all()
        for e in expenses:
            rows.append({
                "id": str(e.id), "date": e.spent_on, "type": "EXPENSE", "category": e.category,
                "description": e.description, "counterparty": e.supplier or "", "family": "",
                "amount_cents": -e.amount_cents, "method": e.payment_method,
                "has_receipt": e.receipt_storage_key is not None, "expense_id": e.id,
                "recurring": e.recurring_id is not None, "computed": False,
            })
    if kind in (None, "", "EXPENSE", "COMPUTED"):
        figures = await monthly_figures(db, club_ids=[scope.club_id], start=period.start, end=period.end)
        for month in period.months:
            f = figures.get((scope.club_id, month))
            if f is None:
                continue
            last_day = _add_months(month_start(month), 1) - timedelta(days=1)
            if f.staff_cents:
                rows.append({
                    "id": f"staff-{month}", "date": last_day, "type": "STAFF", "category": "STAFF_CLOCK",
                    "description": month, "counterparty": "", "family": "", "amount_cents": -f.staff_cents,
                    "method": "COMPUTED", "has_receipt": False, "expense_id": None, "recurring": False,
                    "computed": True,
                })
            if f.coach_share_cents:
                rows.append({
                    "id": f"coach-{month}", "date": last_day, "type": "STAFF", "category": "COACH_SHARE",
                    "description": month, "counterparty": "", "family": "", "amount_cents": -f.coach_share_cents,
                    "method": "COMPUTED", "has_receipt": False, "expense_id": None, "recurring": False,
                    "computed": True,
                })
            if f.platform_fee_cents:
                rows.append({
                    "id": f"platform-{month}", "date": last_day, "type": "PLATFORM_FEE", "category": "PLATFORM_FEE",
                    "description": month, "counterparty": "", "family": "", "amount_cents": -f.platform_fee_cents,
                    "method": "COMPUTED", "has_receipt": False, "expense_id": None, "recurring": False,
                    "computed": True,
                })
    if q and q.strip():
        needle = q.strip().lower()
        rows = [r for r in rows if needle in f"{r['description']} {r['counterparty']} {r['family']}".lower()]
    rows.sort(key=lambda r: (r["date"], r["type"] == "INCOME"), reverse=True)
    truncated = len(rows) > LEDGER_LIMIT
    rows = rows[:LEDGER_LIMIT]
    return {
        "rows": rows,
        "truncated": truncated,
        "in_cents": sum(r["amount_cents"] for r in rows if r["amount_cents"] > 0),
        "out_cents": -sum(r["amount_cents"] for r in rows if r["amount_cents"] < 0),
    }


# --- Spese ----------------------------------------------------------------------------------------


def expense_dict(e: ClubExpense) -> dict:
    return {
        "id": e.id, "spent_on": e.spent_on, "category": e.category, "amount_cents": e.amount_cents,
        "description": e.description, "supplier": e.supplier, "payment_method": e.payment_method,
        "has_receipt": e.receipt_storage_key is not None, "receipt_filename": e.receipt_filename,
        "recurring_id": e.recurring_id, "period": e.period, "created_at": e.created_at,
    }


def _clean_expense(data: dict, *, today: date, partial: bool = False) -> dict:
    out: dict = {}
    if "category" in data and data["category"] is not None or not partial:
        if data.get("category") not in EXPENSE_CATEGORIES:
            raise ClubValidationError("Scegli la categoria della spesa.")
        out["category"] = data["category"]
    if "payment_method" in data and data["payment_method"] is not None or not partial:
        method = data.get("payment_method") or "BANK_TRANSFER"
        if method not in EXPENSE_PAYMENT_METHODS:
            raise ClubValidationError("Scegli come è stata pagata.")
        out["payment_method"] = method
    if "amount_cents" in data and data["amount_cents"] is not None or not partial:
        amount = data.get("amount_cents")
        if not isinstance(amount, int) or amount <= 0 or amount > 100_000_000:
            raise ClubValidationError("L'importo deve essere maggiore di zero.")
        out["amount_cents"] = amount
    if "description" in data and data["description"] is not None or not partial:
        description = (data.get("description") or "").strip()
        if len(description) < 2:
            raise ClubValidationError("Scrivi in due parole che spesa è (es. «Affitto palestra ottobre»).")
        out["description"] = description[:200]
    if "supplier" in data:
        out["supplier"] = (data.get("supplier") or "").strip()[:200] or None
    return out


async def list_expenses(
    db: AsyncSession, *, scope: ClubScope, period: Period, category: str | None = None,
) -> list[ClubExpense]:
    stmt = select(ClubExpense).where(
        ClubExpense.club_id == scope.club_id, ClubExpense.spent_on >= period.start, ClubExpense.spent_on < period.end
    )
    if category:
        stmt = stmt.where(ClubExpense.category == category)
    return list((await db.execute(stmt.order_by(ClubExpense.spent_on.desc(), ClubExpense.created_at.desc()))).scalars())


async def _get_expense(db: AsyncSession, *, scope: ClubScope, expense_id: uuid.UUID) -> ClubExpense:
    expense = await db.get(ClubExpense, expense_id)
    if expense is None or expense.club_id != scope.club_id:
        raise ClubNotFoundError("Spesa non trovata.")
    return expense


def _check_spent_on(spent_on: date, today: date) -> date:
    if spent_on > today + timedelta(days=366):
        raise ClubValidationError("La data della spesa è troppo lontana nel futuro.")
    if spent_on.year < 2000:
        raise ClubValidationError("Controlla la data della spesa.")
    return spent_on


async def create_expense(
    db: AsyncSession, *, scope: ClubScope, actor_user_id: uuid.UUID, data: dict, today: date | None = None,
) -> ClubExpense:
    today = today or utcnow().date()
    values = _clean_expense(data, today=today)
    expense = ClubExpense(
        **scope.columns(), **values, spent_on=_check_spent_on(data.get("spent_on") or today, today),
        created_by_user_id=actor_user_id,
    )
    db.add(expense)
    await db.flush()
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.expense_created", entity_type="club_expense", entity_id=str(expense.id),
        new_value={**values, "spent_on": expense.spent_on.isoformat()},
    )
    await db.commit()
    await db.refresh(expense)
    return expense


async def update_expense(
    db: AsyncSession, *, scope: ClubScope, expense_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict,
    today: date | None = None,
) -> ClubExpense:
    """Anche una spesa nata da un costo fisso si corregge (la bolletta vera è
    diversa dalla rata prevista): resta legata al suo mese."""
    today = today or utcnow().date()
    expense = await _get_expense(db, scope=scope, expense_id=expense_id)
    values = _clean_expense(data, today=today, partial=True)
    if data.get("spent_on") is not None:
        values["spent_on"] = _check_spent_on(data["spent_on"], today)
    previous = {k: str(getattr(expense, k)) for k in values}
    for key, value in values.items():
        setattr(expense, key, value)
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.expense_updated", entity_type="club_expense", entity_id=str(expense.id),
        previous_value=previous, new_value={k: str(v) for k, v in values.items()},
    )
    await db.commit()
    await db.refresh(expense)
    return expense


async def delete_expense(db: AsyncSession, *, scope: ClubScope, expense_id: uuid.UUID, actor_user_id: uuid.UUID) -> None:
    from app.core.storage import delete_document_object

    expense = await _get_expense(db, scope=scope, expense_id=expense_id)
    if expense.recurring_id is not None:
        # Cancellata, il giro dopo del job la ricreerebbe (il vincolo UNIQUE
        # non avrebbe più niente da proteggere): si corregge l'importo, o si
        # ferma il costo fisso.
        raise ClubValidationError(
            "Questa spesa viene da un costo fisso: correggine l'importo, oppure ferma il costo fisso."
        )
    key = expense.receipt_storage_key
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.expense_deleted", entity_type="club_expense", entity_id=str(expense.id),
        previous_value={"description": expense.description, "amount_cents": expense.amount_cents,
                        "spent_on": expense.spent_on.isoformat(), "category": expense.category},
    )
    await db.delete(expense)
    await db.commit()
    if key:
        try:
            delete_document_object(storage_key=key)
        except Exception:
            # Un file rimasto nel bucket non deve far fallire la cancellazione.
            logger.warning("Expense receipt %s not deleted from storage", key, exc_info=True)


async def attach_receipt(
    db: AsyncSession, *, scope: ClubScope, expense_id: uuid.UUID, actor_user_id: uuid.UUID,
    file_bytes: bytes, content_type: str | None, original_filename: str | None,
) -> ClubExpense:
    """La ricevuta (foto o PDF) nel bucket privato dei documenti, come le
    prove di pagamento delle famiglie. Ricaricarla sostituisce la precedente."""
    from app.core.storage import UploadValidationError, upload_document

    expense = await _get_expense(db, scope=scope, expense_id=expense_id)
    try:
        key = upload_document(
            file_bytes=file_bytes, content_type=content_type or "", key_prefix=f"club-expenses/{scope.club_id}",
        )
    except UploadValidationError as exc:
        raise ClubValidationError("Carica una foto (JPG o PNG) o un PDF, di massimo 15 MB.") from exc
    expense.receipt_storage_key = key
    expense.receipt_filename = (original_filename or "ricevuta")[:255]
    expense.receipt_content_type = content_type
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.expense_receipt", entity_type="club_expense", entity_id=str(expense.id),
    )
    await db.commit()
    await db.refresh(expense)
    return expense


async def receipt_key(db: AsyncSession, *, scope: ClubScope, expense_id: uuid.UUID) -> str:
    expense = await _get_expense(db, scope=scope, expense_id=expense_id)
    if expense.receipt_storage_key is None:
        raise ClubNotFoundError("Questa spesa non ha una ricevuta.")
    return expense.receipt_storage_key


# --- Costi fissi ----------------------------------------------------------------------------------


def recurring_dict(r: ClubRecurringExpense) -> dict:
    return {
        "id": r.id, "category": r.category, "amount_cents": r.amount_cents, "description": r.description,
        "supplier": r.supplier, "payment_method": r.payment_method, "day_of_month": r.day_of_month,
        "starts_on": r.starts_on, "ends_on": r.ends_on, "active": r.active,
    }


async def list_recurring(db: AsyncSession, *, scope: ClubScope) -> list[ClubRecurringExpense]:
    return list(
        (
            await db.execute(
                select(ClubRecurringExpense)
                .where(ClubRecurringExpense.club_id == scope.club_id)
                .order_by(ClubRecurringExpense.active.desc(), ClubRecurringExpense.description)
            )
        ).scalars()
    )


def _months_due(r: ClubRecurringExpense, *, first: date, last: date) -> list[str]:
    """I mesi tra `first` e `last` (inclusi) in cui il costo fisso vale."""
    out = []
    for month in months_between(first, _add_months(last, 1)):
        start = month_start(month)
        end = _add_months(start, 1) - timedelta(days=1)
        if end >= r.starts_on and (r.ends_on is None or start <= r.ends_on):
            out.append(month)
    return out


async def materialise_recurring(
    db: AsyncSession, *, scope: ClubScope, today: date | None = None, recurring_id: uuid.UUID | None = None,
    backfill: bool = False,
) -> int:
    """I costi fissi diventano spese del mese. Il job lo fa ogni giorno per il
    mese in corso; alla creazione di un costo fisso con una data d'inizio
    passata si recuperano anche i mesi indietro (`backfill`). Idempotente:
    UNIQUE (costo fisso, mese), ON CONFLICT DO NOTHING. Restituisce quante
    spese ha creato."""
    today = today or utcnow().date()
    this_month = date(today.year, today.month, 1)
    stmt = select(ClubRecurringExpense).where(
        ClubRecurringExpense.club_id == scope.club_id, ClubRecurringExpense.active.is_(True)
    )
    if recurring_id is not None:
        stmt = stmt.where(ClubRecurringExpense.id == recurring_id)
    created = 0
    for r in (await db.execute(stmt)).scalars().all():
        first = this_month
        if backfill:
            first = max(date(r.starts_on.year, r.starts_on.month, 1), _add_months(this_month, -RECURRING_BACKFILL_MONTHS))
        for month in _months_due(r, first=first, last=this_month):
            start = month_start(month)
            result = await db.execute(
                insert(ClubExpense)
                .values(
                    id=uuid.uuid4(), created_at=utcnow(), organization_id=r.organization_id, club_id=r.club_id,
                    spent_on=date(start.year, start.month, r.day_of_month), category=r.category,
                    amount_cents=r.amount_cents, description=r.description, supplier=r.supplier,
                    payment_method=r.payment_method, created_by_user_id=None, recurring_id=r.id, period=month,
                )
                .on_conflict_do_nothing(constraint="uq_club_expenses_recurring_period")
                .returning(ClubExpense.id)
            )
            created += 1 if result.first() is not None else 0
    await db.commit()
    return created


def _clean_recurring(data: dict, *, partial: bool) -> dict:
    out = _clean_expense(data, today=utcnow().date(), partial=partial)
    if "day_of_month" in data and data["day_of_month"] is not None or not partial:
        day = data.get("day_of_month") or 1
        if not isinstance(day, int) or not 1 <= day <= 28:
            raise ClubValidationError("Il giorno del mese va da 1 a 28.")
        out["day_of_month"] = day
    for key in ("starts_on", "ends_on", "active"):
        if key in data and (data[key] is not None or key == "ends_on"):
            out[key] = data[key]
    return out


async def create_recurring(
    db: AsyncSession, *, scope: ClubScope, actor_user_id: uuid.UUID, data: dict, today: date | None = None,
) -> ClubRecurringExpense:
    today = today or utcnow().date()
    values = _clean_recurring(data, partial=False)
    values.setdefault("starts_on", date(today.year, today.month, 1))
    if values["starts_on"] < _add_months(date(today.year, today.month, 1), -RECURRING_BACKFILL_MONTHS):
        raise ClubValidationError("Un costo fisso può partire al massimo due anni fa.")
    if values.get("ends_on") is not None and values["ends_on"] < values["starts_on"]:
        raise ClubValidationError("La fine deve venire dopo l'inizio.")
    recurring = ClubRecurringExpense(**scope.columns(), **values, created_by_user_id=actor_user_id)
    db.add(recurring)
    await db.flush()
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.recurring_expense_created", entity_type="club_recurring_expense", entity_id=str(recurring.id),
        new_value={k: str(v) for k, v in values.items()},
    )
    await db.commit()
    await db.refresh(recurring)
    await materialise_recurring(db, scope=scope, today=today, recurring_id=recurring.id, backfill=True)
    return recurring


async def _get_recurring(db: AsyncSession, *, scope: ClubScope, recurring_id: uuid.UUID) -> ClubRecurringExpense:
    recurring = await db.get(ClubRecurringExpense, recurring_id)
    if recurring is None or recurring.club_id != scope.club_id:
        raise ClubNotFoundError("Costo fisso non trovato.")
    return recurring


async def update_recurring(
    db: AsyncSession, *, scope: ClubScope, recurring_id: uuid.UUID, actor_user_id: uuid.UUID, data: dict,
    today: date | None = None,
) -> ClubRecurringExpense:
    """Le modifiche valgono per i mesi che non sono ancora stati registrati:
    quelli già passati sono spese, e si correggono una per una."""
    today = today or utcnow().date()
    recurring = await _get_recurring(db, scope=scope, recurring_id=recurring_id)
    values = _clean_recurring(data, partial=True)
    for key, value in values.items():
        setattr(recurring, key, value)
    if recurring.ends_on is not None and recurring.ends_on < recurring.starts_on:
        raise ClubValidationError("La fine deve venire dopo l'inizio.")
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.recurring_expense_updated", entity_type="club_recurring_expense", entity_id=str(recurring.id),
        new_value={k: str(v) for k, v in values.items()},
    )
    await db.commit()
    await db.refresh(recurring)
    return recurring


async def delete_recurring(
    db: AsyncSession, *, scope: ClubScope, recurring_id: uuid.UUID, actor_user_id: uuid.UUID,
) -> bool:
    """Senza mesi registrati si cancella; con, si ferma (`active` falso) e le
    spese già registrate restano nel conto. True se cancellato."""
    recurring = await _get_recurring(db, scope=scope, recurring_id=recurring_id)
    used = (
        await db.execute(select(func.count()).where(ClubExpense.recurring_id == recurring.id))
    ).scalar_one()
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.recurring_expense_deleted" if not used else "club.recurring_expense_stopped",
        entity_type="club_recurring_expense", entity_id=str(recurring.id),
    )
    if used:
        recurring.active = False
    else:
        await db.delete(recurring)
    await db.commit()
    return not used


# --- Costo dello staff ----------------------------------------------------------------------------


async def staff_costs(db: AsyncSession, *, scope: ClubScope, period: Period, today: date) -> list[dict]:
    """Per ogni persona dello staff: ore dei turni chiusi nel periodo,
    tariffa oraria valida oggi, costo calcolato (con la tariffa di ogni
    giorno). Compaiono anche segreteria e istruttori senza ore."""
    from app.domains.club.clubs import CLUB_STAFF_ROLES
    from app.domains.club.people import _names
    from app.domains.rbac.models import Role, UserRole
    from app.domains.users.models import User

    rates = await _staff_rates(db, [scope.club_id])
    minutes: dict[uuid.UUID, int] = {}
    cost: dict[uuid.UUID, int] = {}
    for _club_id, user_id, started_at, ended_at in await staff_sessions(
        db, club_ids=[scope.club_id], start=period.start, end=period.end
    ):
        m = _session_minutes(started_at, ended_at)
        minutes[user_id] = minutes.get(user_id, 0) + m
        cost[user_id] = cost.get(user_id, 0) + round(
            m * _rate_on(rates.get((scope.club_id, user_id), []), started_at.astimezone(UTC).date()) / 60
        )
    staff = set(
        (
            await db.execute(
                select(User.id)
                .join(UserRole, UserRole.user_id == User.id)
                .join(Role, Role.id == UserRole.role_id)
                .where(User.club_id == scope.club_id, Role.code.in_(CLUB_STAFF_ROLES))
            )
        ).scalars()
    )
    people = staff | set(minutes) | {uid for (_cid, uid) in rates}
    names = await _names(db, people)
    rows = []
    for uid in people:
        history = rates.get((scope.club_id, uid), [])
        current = [r for r in history if r[0] <= today]
        rows.append({
            "user_id": uid, "name": names.get(uid, ""), "minutes": minutes.get(uid, 0),
            "hourly_rate_cents": current[-1][1] if current else None,
            "rate_valid_from": current[-1][0] if current else None,
            "cost_cents": cost.get(uid, 0),
        })
    return sorted(rows, key=lambda r: (-r["cost_cents"], r["name"].lower()))


async def set_staff_rate(
    db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, hourly_rate_cents: int, actor_user_id: uuid.UUID,
    valid_from: date | None = None, today: date | None = None,
) -> dict:
    """La tariffa vale da `valid_from` (default: il primo del mese in corso)
    in poi; i mesi prima restano calcolati con quella di allora."""
    from app.domains.club.workclock import staff_user

    today = today or utcnow().date()
    await staff_user(db, scope=scope, user_id=user_id)
    if not 0 <= hourly_rate_cents <= 100_000:
        raise ClubValidationError("La tariffa oraria va da 0 a 1.000 €.")
    valid_from = valid_from or date(today.year, today.month, 1)
    await db.execute(
        insert(ClubStaffRate)
        .values(
            id=uuid.uuid4(), created_at=utcnow(), **scope.columns(), user_id=user_id,
            hourly_rate_cents=hourly_rate_cents, valid_from=valid_from, set_by_user_id=actor_user_id,
        )
        .on_conflict_do_update(
            constraint="uq_club_staff_rates_club_user_from",
            set_={"hourly_rate_cents": hourly_rate_cents, "set_by_user_id": actor_user_id},
        )
    )
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.staff_rate_set", entity_type="user", entity_id=str(user_id),
        new_value={"hourly_rate_cents": hourly_rate_cents, "valid_from": valid_from.isoformat()},
    )
    await db.commit()
    return {"user_id": user_id, "hourly_rate_cents": hourly_rate_cents, "valid_from": valid_from}


# --- La piattaforma -------------------------------------------------------------------------------


async def platform_summary(db: AsyncSession, *, organization_id: uuid.UUID, year: int, today: date) -> dict:
    """Tutti i club insieme e uno per uno: incassi, costi, risultato, debiti,
    e quanto spetta alla piattaforma (questo mese, quest'anno, da sempre),
    più la crescita della rete e le vendite dello Shop.

    L'unità dei corsi JAV (club/kinds.py) non è un club: sta a parte
    (`courses_unit`), fuori dai totali dei club, e ciò che JAV ne tiene (gli
    incassi meno la parte dei treinador) è una riga sua del contatore."""
    from app.domains.jav_market.models import JavMarketOrder

    every = list(
        (await db.execute(select(Club).where(Club.organization_id == organization_id).order_by(Club.name))).scalars()
    )
    clubs = [c for c in every if not kinds.is_courses_unit(c)]
    unit = next((c for c in every if kinds.is_courses_unit(c)), None)
    all_ids = [c.id for c in every]
    ids = [c.id for c in clubs]
    this_month = f"{today.year:04d}-{today.month:02d}"
    year_period = Period(key=str(year), kind="year", start=date(year, 1, 1), end=date(year + 1, 1, 1))
    series_start = _add_months(date(today.year, today.month, 1), -11)
    series_end = _add_months(date(today.year, today.month, 1), 1)
    figures = await monthly_figures(
        db, club_ids=all_ids, start=min(year_period.start, series_start), end=max(year_period.end, series_end),
    )
    series_months = months_between(series_start, series_end)
    history = await _fee_history(db, all_ids)

    # Da sempre: solo gli incassi servono, mese per mese, per applicare a
    # ogni mese la sua percentuale.
    all_time: dict[uuid.UUID, int] = {}
    all_time_income: dict[uuid.UUID, int] = {}
    paid_month = _month_of(ClubFee.paid_at)
    kind_of = {c.id: c.kind for c in every}
    if all_ids:
        for club_id, month, cents in (
            await db.execute(
                select(ClubFee.club_id, paid_month, func.sum(ClubFee.amount_cents))
                .where(ClubFee.club_id.in_(all_ids), ClubFee.status == "PAID", ClubFee.paid_at.is_not(None))
                .group_by(ClubFee.club_id, paid_month)
            )
        ).all():
            all_time_income[club_id] = all_time_income.get(club_id, 0) + int(cents or 0)
            all_time[club_id] = all_time.get(club_id, 0) + fee_cents(
                int(cents or 0), pct_on(history.get(club_id, []), month, kind=kind_of[club_id])
            )

    athletes = dict(
        (
            await db.execute(
                select(ClubAthlete.club_id, func.count())
                .where(ClubAthlete.club_id.in_(all_ids), ClubAthlete.status == "ACTIVE")
                .group_by(ClubAthlete.club_id)
            )
        ).all()
    ) if all_ids else {}
    families = dict(
        (
            await db.execute(
                select(ClubAthlete.club_id, func.count(func.distinct(ClubAthlete.guardian_user_id)))
                .where(ClubAthlete.club_id.in_(all_ids), ClubAthlete.status == "ACTIVE")
                .group_by(ClubAthlete.club_id)
            )
        ).all()
    ) if all_ids else {}
    debt: dict[uuid.UUID, dict] = {}
    for club_id, _family, due_date, cents in await _due_rows(db, all_ids):
        row = debt.setdefault(club_id, {"total": 0, "overdue": 0, "aging": _empty_aging()})
        bucket = aging_bucket(due_date, today)
        row["total"] += int(cents)
        row["overdue"] += int(cents) if due_date < today else 0
        row["aging"][bucket]["cents"] += int(cents)
        row["aging"][bucket]["count"] += 1

    year_months = [m for m in year_period.months if month_start(m) <= today] if year == today.year else year_period.months

    def club_row(c: Club) -> dict:
        month_f = _sum(figures, months=[this_month], club_id=c.id)
        year_f = _sum(figures, months=year_period.months, club_id=c.id)
        d = debt.get(c.id, {"total": 0, "overdue": 0, "aging": _empty_aging()})
        return {
            "id": c.id, "name": c.name, "slug": c.slug, "status": c.status, "kind": c.kind,
            "platform_fee_pct": pct_on(history.get(c.id, []), this_month, kind=c.kind),
            "athletes_active": int(athletes.get(c.id, 0)), "families": int(families.get(c.id, 0)),
            "month": month_f.as_dict(), "year": year_f.as_dict(),
            "platform_fee_all_time_cents": all_time.get(c.id, 0),
            "debt_cents": d["total"], "overdue_cents": d["overdue"], "aging": d["aging"],
        }

    rows = [club_row(c) for c in clubs]
    totals_month = _sum_clubs(figures, months=[this_month], club_ids=ids)
    totals_year = _sum_clubs(figures, months=year_period.months, club_ids=ids)
    aging_total = _empty_aging()
    for club_id, d in debt.items():
        if club_id not in ids:
            continue
        for key, b in d["aging"].items():
            aging_total[key]["cents"] += b["cents"]
            aging_total[key]["count"] += b["count"]

    # La previsione del mese: la commissione sugli incassi già fatti più
    # quella sulle quote del mese ancora da pagare.
    forecast = 0
    for c in clubs:
        f = _sum(figures, months=[this_month], club_id=c.id)
        forecast += fee_cents(f.income_cents + f.issued_cents - f.issued_paid_cents,
                              pct_on(history.get(c.id, []), this_month, kind=c.kind))

    # I corsi JAV: ciò che JAV tiene = incassi meno la parte dei treinador.
    courses = None
    if unit is not None:
        unit_month = _sum(figures, months=[this_month], club_id=unit.id)
        unit_year = _sum(figures, months=year_period.months, club_id=unit.id)
        month_start_day = date(today.year, today.month, 1)
        expected = unit_month.issued_cents - unit_month.issued_paid_cents
        expected_share = await expected_coach_share(
            db, club_ids=[unit.id], start=month_start_day, end=_add_months(month_start_day, 1),
        )
        all_time_share = sum(share for _c, _m, _cents, share in await coach_share_rows(
            db, club_ids=[unit.id], start=date(2000, 1, 1), end=date(2101, 1, 1),
        ))
        courses = {
            **club_row(unit),
            "kept_month_cents": unit_month.income_cents - unit_month.coach_share_cents,
            "kept_month_forecast_cents": (
                unit_month.income_cents + expected - unit_month.coach_share_cents - expected_share
            ),
            "kept_year_cents": unit_year.income_cents - unit_year.coach_share_cents,
            "kept_all_time_cents": all_time_income.get(unit.id, 0) - all_time_share,
        }

    series = []
    for m in series_months:
        by_club = {str(c.id): _sum(figures, months=[m], club_id=c.id).platform_fee_cents for c in clubs}
        f = _sum_clubs(figures, months=[m], club_ids=ids)
        unit_f = _sum(figures, months=[m], club_id=unit.id) if unit is not None else Figures()
        series.append({
            "month": m, "platform_fee_cents": f.platform_fee_cents, "income_cents": f.income_cents,
            "costs_cents": f.costs_cents, "result_cents": f.result_cents, "by_club": by_club,
            "courses_kept_cents": unit_f.income_cents - unit_f.coach_share_cents,
        })

    growth = await _growth(db, organization_id=organization_id, club_ids=ids, months=series_months)

    order_month = _month_of(JavMarketOrder.paid_at)
    shop_rows = (
        await db.execute(
            select(order_month, func.count(), func.sum(JavMarketOrder.amount_cents))
            .where(
                JavMarketOrder.organization_id == organization_id, JavMarketOrder.status == "PAID",
                JavMarketOrder.paid_at.is_not(None),
            )
            .group_by(order_month)
        )
    ).all()
    shop_by_month = {m: (int(n), int(c or 0)) for m, n, c in shop_rows}
    shop = {
        "month_cents": shop_by_month.get(this_month, (0, 0))[1],
        "year_cents": sum(c for m, (_n, c) in shop_by_month.items() if m.startswith(f"{year:04d}-")),
        "all_time_cents": sum(c for _n, c in shop_by_month.values()),
        "orders_year": sum(n for m, (n, _c) in shop_by_month.items() if m.startswith(f"{year:04d}-")),
        "series": [{"month": m, "cents": shop_by_month.get(m, (0, 0))[1]} for m in series_months],
    }

    return {
        "year": year,
        "month": this_month,
        "year_months": year_months,
        "clubs": rows,
        "courses_unit": courses,
        "totals": {
            "clubs_active": sum(1 for c in clubs if c.status == "ACTIVE"),
            "athletes_active": sum(r["athletes_active"] for r in rows),
            "families": sum(r["families"] for r in rows),
            "month": totals_month.as_dict(),
            "year": totals_year.as_dict(),
            "debt_cents": sum(r["debt_cents"] for r in rows),
            "overdue_cents": sum(r["overdue_cents"] for r in rows),
            "aging": aging_total,
        },
        "earnings": {
            "month_cents": totals_month.platform_fee_cents,
            "month_forecast_cents": forecast,
            "year_cents": totals_year.platform_fee_cents,
            "all_time_cents": sum(all_time.get(i, 0) for i in ids),
            # La riga a parte dei corsi JAV (0 se l'unità non c'è ancora).
            "courses_month_cents": courses["kept_month_cents"] if courses else 0,
            "courses_month_forecast_cents": courses["kept_month_forecast_cents"] if courses else 0,
            "courses_year_cents": courses["kept_year_cents"] if courses else 0,
            "courses_all_time_cents": courses["kept_all_time_cents"] if courses else 0,
            "series": series,
        },
        "growth": growth,
        "shop": shop,
        "default_platform_fee_pct": DEFAULT_PLATFORM_FEE_PCT,
    }


def _sum_clubs(figures: dict[tuple[uuid.UUID, str], Figures], *, months: list[str], club_ids: list[uuid.UUID]) -> Figures:
    total = Figures()
    for club_id in club_ids:
        total.add(_sum(figures, months=months, club_id=club_id))
    return total


async def _growth(db: AsyncSession, *, organization_id: uuid.UUID, club_ids: list[uuid.UUID], months: list[str]) -> list[dict]:
    """A fine di ogni mese: club esistenti, atleti iscritti (entrati e non
    ancora usciti), famiglie con almeno un atleta iscritto."""
    clubs = (
        await db.execute(
            select(Club.created_at).where(Club.organization_id == organization_id, Club.kind == kinds.CLUB)
        )
    ).scalars().all()
    athletes = (
        await db.execute(
            select(ClubAthlete.guardian_user_id, ClubAthlete.joined_on, ClubAthlete.left_on)
            .where(ClubAthlete.club_id.in_(club_ids))
        )
    ).all() if club_ids else []
    out = []
    for m in months:
        last = _add_months(month_start(m), 1) - timedelta(days=1)
        enrolled = [g for g, joined, left in athletes if joined <= last and (left is None or left > last)]
        out.append({
            "month": m,
            "clubs": sum(1 for created in clubs if created.astimezone(UTC).date() <= last),
            "athletes": len(enrolled),
            "families": len(set(enrolled)),
        })
    return out


async def club_options(db: AsyncSession, *, organization_id: uuid.UUID, club_id: uuid.UUID) -> dict:
    """La percentuale di un club: quella di adesso e lo storico."""
    club = await db.get(Club, club_id)
    if club is None or club.organization_id != organization_id:
        raise ClubNotFoundError("Club non trovato.")
    history = (await _fee_history(db, [club_id])).get(club_id, [])
    today = utcnow().date()
    return {
        "club_id": club_id,
        "pct": pct_on(history, f"{today.year:04d}-{today.month:02d}", kind=club.kind),
        "editable": kinds.rules_of(club).platform_fee_editable,
        "history": [{"valid_from": v, "pct": p} for v, p in history],
    }


# --- I conti di una famiglia ----------------------------------------------------------------------


async def personal_account(db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, year: int, today: date) -> dict:
    """I conti di chi usa il portale: un genitore, un atleta adulto, o un
    atleta adulto che è anche genitore. Un conto solo; il dettaglio persona
    per persona compare solo se ci sono figli (con una persona sola sarebbe
    la stessa tabella due volte)."""
    from app.domains.club.family import fee_dict
    from app.domains.club.people import INVESTMENT_SOURCE
    from app.domains.club.referrals import WALLET_SOURCE
    from app.domains.jav_market.models import JavMarketOrder
    from app.domains.wallets.models import Wallet, WalletTransaction

    athletes = list(
        (
            await db.execute(
                select(ClubAthlete)
                .where(ClubAthlete.club_id == scope.club_id, ClubAthlete.guardian_user_id == user_id)
                .order_by(ClubAthlete.is_self.desc(), ClubAthlete.birth_date)
            )
        ).scalars()
    )
    by_id = {a.id: a for a in athletes}
    ids = list(by_id)
    owner = (ClubFee.kind == "MEMBERSHIP") & (ClubFee.guardian_user_id == user_id)
    if ids:
        owner = owner | ClubFee.athlete_id.in_(ids)
    fees = list(
        (await db.execute(select(ClubFee).where(ClubFee.club_id == scope.club_id, owner).order_by(ClubFee.due_date))).scalars()
    )
    year_start, year_end = _utc(date(year, 1, 1)), _utc(date(year + 1, 1, 1))

    def in_year(fee: ClubFee) -> bool:
        return fee.paid_at is not None and year_start <= fee.paid_at < year_end

    def missed(fee: ClubFee) -> int:
        waived = fee.amount_cents if fee.status == "WAIVED" else 0
        return (fee.discount_cents or 0) + absence_cents(fee) + waived

    def numbers(rows: list[ClubFee]) -> dict:
        paid = [f for f in rows if f.status == "PAID"]
        due = [f for f in rows if f.status == "DUE"]
        return {
            "paid_year_cents": sum(f.amount_cents for f in paid if in_year(f)),
            "paid_all_time_cents": sum(f.amount_cents for f in paid),
            "paid_by_kind": {k: sum(f.amount_cents for f in paid if in_year(f) and f.kind == k) for k in FEE_KINDS},
            "due_cents": sum(f.amount_cents for f in due),
            "overdue_cents": sum(f.amount_cents for f in due if f.due_date < today),
            "upcoming_cents": sum(f.amount_cents for f in due if f.due_date >= today),
            "savings_year_cents": sum(missed(f) for f in rows if f.due_date.year == year),
        }

    orders = (
        await db.execute(
            select(JavMarketOrder).where(
                JavMarketOrder.organization_id == scope.organization_id, JavMarketOrder.customer_user_id == user_id,
                JavMarketOrder.status == "PAID", JavMarketOrder.paid_at.is_not(None),
            )
        )
    ).scalars().all()
    orders_year = [o for o in orders if year_start <= o.paid_at < year_end]

    has_children = any(not a.is_self for a in athletes)
    people = []
    if has_children:
        for a in athletes:
            mine = [f for f in fees if f.athlete_id == a.id]
            people.append({
                "athlete_id": a.id, "name": f"{a.first_name} {a.last_name}", "is_self": a.is_self, "status": a.status,
                **numbers(mine),
                "shop_year_cents": sum(o.amount_cents for o in orders_year if o.athlete_id == a.id),
            })
        membership = [f for f in fees if f.kind == "MEMBERSHIP"]
        if membership:
            people.append({
                "athlete_id": None, "name": "", "is_self": False, "status": "ACTIVE", **numbers(membership),
                "shop_year_cents": 0,
            })

    wallet = (
        await db.execute(select(Wallet).where(Wallet.organization_id == scope.organization_id, Wallet.user_id == user_id))
    ).scalar_one_or_none()
    referral_cents = investment_cents = 0
    if wallet is not None:
        credits = (
            await db.execute(
                select(WalletTransaction.id, WalletTransaction.source, WalletTransaction.amount_cents).where(
                    WalletTransaction.to_wallet_id == wallet.id, WalletTransaction.type == "ADMIN_CREDIT",
                    WalletTransaction.source.in_((WALLET_SOURCE, INVESTMENT_SOURCE)),
                )
            )
        ).all()
        reversed_ids = set(
            (
                await db.execute(
                    select(WalletTransaction.reverses_transaction_id).where(
                        WalletTransaction.type == "REVERSAL",
                        WalletTransaction.reverses_transaction_id.in_([c.id for c in credits]),
                    )
                )
            ).scalars()
        ) if credits else set()
        for tx_id, source, cents in credits:
            if tx_id in reversed_ids:
                continue
            if source == WALLET_SOURCE:
                referral_cents += int(cents)
            else:
                investment_cents += int(cents)
    credit_on_fees = int(
        (
            await db.execute(
                select(func.coalesce(func.sum(ClubPaymentProof.credit_cents), 0)).where(
                    ClubPaymentProof.club_id == scope.club_id, ClubPaymentProof.uploaded_by_user_id == user_id,
                    ClubPaymentProof.status == "ACCEPTED",
                )
            )
        ).scalar_one()
    )

    months = months_between(date(year, 1, 1), date(year + 1, 1, 1))
    series = []
    for m in months:
        series.append({
            "month": m,
            "fees_cents": sum(f.amount_cents for f in fees if f.status == "PAID" and f.paid_at is not None
                              and f.paid_at.astimezone(UTC).strftime("%Y-%m") == m),
            "shop_cents": sum(o.amount_cents for o in orders if o.paid_at.astimezone(UTC).strftime("%Y-%m") == m),
        })
    due = [f for f in fees if f.status == "DUE"]
    discounted = [f for f in fees if f.due_date.year == year and missed(f) > 0]
    return {
        "year": year,
        "has_children": has_children,
        "is_athlete": any(a.is_self for a in athletes),
        "totals": numbers(fees),
        "people": people,
        "shop": {
            "year_cents": sum(o.amount_cents for o in orders_year),
            "all_time_cents": sum(o.amount_cents for o in orders),
            "orders_year": len(orders_year),
            "credit_used_year_cents": sum(o.credit_applied_cents for o in orders_year),
        },
        "wallet": {
            "balance_cents": wallet.balance_cents if wallet is not None else 0,
            "referral_credits_cents": referral_cents,
            "investments_cents": investment_cents,
            "credit_spent_on_fees_cents": credit_on_fees,
            "credit_spent_on_shop_cents": sum(o.credit_applied_cents for o in orders),
        },
        "series": series,
        "next_payments": [fee_dict(f, today=today, athlete=by_id.get(f.athlete_id)) for f in due[:8]],
        "discounts": [
            {**fee_dict(f, today=today, athlete=by_id.get(f.athlete_id)), "saved_cents": missed(f)}
            for f in sorted(discounted, key=lambda f: f.due_date, reverse=True)[:24]
        ],
    }
