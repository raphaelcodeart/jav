"""I relatórios della segreteria. Specifica: docs/club-portal.md, "Relatórios".

Tutto si calcola dalle quote, dalle prove e dai numeri della contabilità
(accounting.py), con poche query raggruppate per relatório: niente totali
salvati, quindi un pagamento corretto corregge anche il relatório. Ogni
relatório esiste in tre forme: il JSON per lo schermo, il CSV e l'XLSX
(scritti qui, server-side: il browser sceglie solo quale e per che periodo).

- `matrix`       atleti × mesi: la mensilità di ogni atleta in ogni mese
                 della stagione (set → ago) o dell'anno, con i totali;
- `collections`  gli incassi per mese e per metodo (bonifico, MB Way,
                 contanti, carta, credito): la somma è l'incasso della
                 contabilità;
- `debts`        chi deve quanto, famiglia per famiglia, per anzianità;
- `adjustments`  il registro di ciò che non si è incassato per scelta:
                 mesi esenti, condoni, taxa de falta, pagamenti parziali,
                 con il motivo e chi l'ha deciso;
- `cash`         i contanti ricevuti da ogni persona, mese per mese;
- `pnl`          entrate e uscite di ogni mese (il conto economico).

Le intestazioni dei file sono in portoghese, inglese o italiano
(`lang`, come JAVBOT: spagnolo → portoghese, francese/tedesco/ucraino →
inglese); a schermo le traduce l'interfaccia, nelle sue sette lingue.
"""

import csv
import io
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.club import accounting, fee_splits, seasons
from app.domains.club.models import PAYMENT_METHODS, ClubAthlete, ClubFee, ClubPlan
from app.domains.club.scope import ClubScope
from app.domains.club.service import ClubValidationError
from app.domains.users.models import User

REPORTS = ("matrix", "collections", "debts", "adjustments", "cash", "pnl")
FORMATS = ("json", "csv", "xlsx")

# --- Il periodo -----------------------------------------------------------------------------------


def report_period(*, season: int | None, year: int | None, today: date) -> dict:
    """Una stagione (settembre → agosto) o un anno solare; senza niente, la
    stagione in corso."""
    if season is not None and year is not None:
        raise ClubValidationError("Scegli una stagione o un anno, non tutti e due.")
    if year is not None:
        if not 2000 <= year <= 2100:
            raise ClubValidationError("Anno non valido.")
        months = [(year, m) for m in range(1, 13)]
        return {"kind": "year", "key": str(year), "label": str(year), "months": months,
                "start": date(year, 1, 1), "end": date(year + 1, 1, 1)}
    season = seasons.season_of(today) if season is None else season
    if not 2000 <= season <= 2100:
        raise ClubValidationError("Stagione non valida.")
    return {"kind": "season", "key": f"season-{season}", "label": seasons.season_label(season),
            "months": [(y, m) for y, m in _season_months(season)],
            "start": date(season, 9, 1), "end": date(season + 1, 9, 1)}


def _season_months(season: int) -> list[tuple[int, int]]:
    return [(season + (m < 9), m) for m in (9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8)]


def _key(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def _day(value: datetime | None) -> date | None:
    return value.astimezone(UTC).date() if value is not None else None


def _name(a: ClubAthlete) -> str:
    return f"{a.first_name} {a.last_name}"


# --- Atleti × mesi --------------------------------------------------------------------------------


def _enrolled(athlete: ClubAthlete, year: int, month: int) -> bool:
    first = date(year, month, 1)
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return athlete.joined_on < nxt and (athlete.left_on is None or athlete.left_on >= first)


def _cell(parts: list[ClubFee], athlete: ClubAthlete, *, year: int, month: int, today: date) -> dict:
    period = _key(year, month)
    if not parts:
        if athlete.exempt_monthly:
            state = "EXEMPT"
        elif not _enrolled(athlete, year, month):
            state = "NOT_ENROLLED"
        elif period > seasons.period_of(today):
            state = "UPCOMING"
        else:
            state = "NONE"
        return {"period": period, "state": state, "paid_cents": 0, "due_cents": 0, "waived_cents": 0,
                "paid_on": None, "method": None, "receiver": None, "reason": None, "overdue": False, "fee_id": None}
    parts = fee_splits.order_parts(parts)
    state = fee_splits.group_state(parts, today=today)
    paid = [p for p in parts if p.status == "PAID"]
    due = [p for p in parts if p.status == "DUE"]
    last = max(paid, key=lambda p: p.paid_at or datetime.min.replace(tzinfo=UTC)) if paid else None
    methods = {p.payment_method for p in paid if p.payment_method}
    root = parts[0]
    reason = root.waive_reason if root.status == "WAIVED" else next((p.split_reason for p in parts if p.split_reason), None)
    main = fee_splits.group_main(parts)
    return {
        "period": period,
        "state": state,
        "paid_cents": sum(p.amount_cents for p in paid),
        "due_cents": sum(p.amount_cents for p in due),
        "waived_cents": sum(p.amount_cents for p in parts if p.status == "WAIVED"),
        "paid_on": _day(last.paid_at) if last else None,
        "method": (next(iter(methods)) if len(methods) == 1 else "MIXED") if methods else None,
        "receiver": last.cash_received_by_name if last else None,
        "reason": reason,
        "overdue": bool(due) and min(p.due_date for p in due) < today,
        "fee_id": main.id,
    }


async def matrix(db: AsyncSession, *, scope: ClubScope, period: dict, today: date) -> dict:
    """Una riga per atleta (attivo, o con almeno una mensilità nel periodo),
    una colonna per mese. Due query: atleti e mensilità."""
    keys = [_key(y, m) for y, m in period["months"]]
    fees = list(
        (
            await db.execute(
                select(ClubFee).where(
                    ClubFee.club_id == scope.club_id, ClubFee.kind == "MONTHLY",
                    ClubFee.period >= min(keys), ClubFee.period < f"{max(keys)}~",
                )
            )
        ).scalars()
    )
    groups: dict[tuple[uuid.UUID, str], list[ClubFee]] = {}
    for f in fees:
        base = fee_splits.base_period(f.period)
        if base in keys:
            groups.setdefault((f.athlete_id, base), []).append(f)
    with_fee = list({athlete_id for athlete_id, _ in groups})
    who = ClubAthlete.status == "ACTIVE"
    if with_fee:
        who = who | ClubAthlete.id.in_(with_fee)
    athletes = list(
        (
            await db.execute(
                select(ClubAthlete).where(ClubAthlete.club_id == scope.club_id, who)
                .order_by(ClubAthlete.last_name, ClubAthlete.first_name)
            )
        ).scalars()
    )
    plans = {p.id: p.name for p in (await db.execute(select(ClubPlan).where(ClubPlan.club_id == scope.club_id))).scalars()}
    rows = []
    columns = {k: {"period": k, "paid_cents": 0, "due_cents": 0, "overdue_cents": 0, "waived_cents": 0,
                   "paid": 0, "partial": 0, "due": 0, "exempt": 0} for k in keys}
    for a in athletes:
        cells = []
        for year, month in period["months"]:
            cell = _cell(groups.get((a.id, _key(year, month)), []), a, year=year, month=month, today=today)
            cells.append(cell)
            col = columns[cell["period"]]
            col["paid_cents"] += cell["paid_cents"]
            col["due_cents"] += cell["due_cents"]
            col["overdue_cents"] += cell["due_cents"] if cell["overdue"] else 0
            col["waived_cents"] += cell["waived_cents"]
            col["paid"] += cell["state"] == "PAID"
            col["partial"] += cell["state"] == "PARTIAL"
            col["due"] += cell["state"] in ("DUE", "OVERDUE")
            col["exempt"] += cell["state"] in ("MONTH_EXEMPT", "WAIVED", "EXEMPT")
        rows.append({
            "athlete_id": a.id, "name": _name(a), "first_name": a.first_name, "last_name": a.last_name,
            "member_number": a.member_number, "group": plans.get(a.plan_id) if a.plan_id else None,
            "status": a.status, "cells": cells,
            "paid_cents": sum(c["paid_cents"] for c in cells),
            "due_cents": sum(c["due_cents"] for c in cells),
            "overdue_cents": sum(c["due_cents"] for c in cells if c["overdue"]),
            "waived_cents": sum(c["waived_cents"] for c in cells),
            "months_paid": sum(1 for c in cells if c["state"] == "PAID"),
        })
    cols = [columns[k] for k in keys]
    return {
        "period": _period_out(period), "months": keys, "rows": rows, "columns": cols,
        "totals": {
            "athletes": len(rows),
            **{k: sum(c[k] for c in cols) for k in ("paid_cents", "due_cents", "overdue_cents", "waived_cents")},
        },
    }


def _period_out(period: dict) -> dict:
    return {"kind": period["kind"], "key": period["key"], "label": period["label"],
            "start": period["start"], "end": period["end"]}


# --- Le tabelle (tutti gli altri relatórios) ------------------------------------------------------
#
# Una tabella è {"columns": [{"key", "type", "month"?, "method"?}], "rows":
# [{key: valore}], "totals": {key: valore} | None}. `type`: text, money
# (centesimi), date, int, pct, code (un codice da tradurre).


def _col(key: str, type_: str = "text", **extra) -> dict:
    return {"key": key, "type": type_, **extra}


async def collections(db: AsyncSession, *, scope: ClubScope, period: dict, today: date) -> dict:
    """Gli incassi (quote pagate, nel mese in cui sono state pagate) per
    metodo: la stessa regola dell'incasso della contabilità."""
    month = accounting._month_of(ClubFee.paid_at)
    method = func.coalesce(ClubFee.payment_method, "UNKNOWN")
    data: dict[str, dict[str, int]] = {}
    counts: dict[str, int] = {}
    for m, meth, cents, n in (
        await db.execute(
            select(month, method, func.sum(ClubFee.amount_cents), func.count())
            .where(
                ClubFee.club_id == scope.club_id, ClubFee.status == "PAID",
                ClubFee.paid_at >= accounting._utc(period["start"]), ClubFee.paid_at < accounting._utc(period["end"]),
            )
            .group_by(month, method)
        )
    ).all():
        data.setdefault(m, {})[meth] = int(cents or 0)
        counts[m] = counts.get(m, 0) + int(n)
    methods = [m for m in (*PAYMENT_METHODS, "UNKNOWN") if any(m in row for row in data.values())]
    rows = []
    for year, mon in period["months"]:
        key = _key(year, mon)
        row = {"month": key, **{m: data.get(key, {}).get(m, 0) for m in methods},
               "payments": counts.get(key, 0), "total": sum(data.get(key, {}).values())}
        rows.append(row)
    totals = {"month": None, **{m: sum(r[m] for r in rows) for m in methods},
              "payments": sum(r["payments"] for r in rows), "total": sum(r["total"] for r in rows)}
    return {
        "period": _period_out(period),
        "columns": [_col("month", "month"), *(_col(m, "money", method=m) for m in methods),
                    _col("payments", "int"), _col("total", "money")],
        "rows": rows, "totals": totals,
    }


async def debts(db: AsyncSession, *, scope: ClubScope, period: dict, today: date) -> dict:
    """Le quote da pagare di oggi, famiglia per famiglia, per anzianità
    dalla scadenza (accounting.AGING_BUCKETS). Il periodo non conta: un
    debito è di oggi."""
    from app.domains.club.people import _names

    family = func.coalesce(ClubAthlete.guardian_user_id, ClubFee.guardian_user_id)
    rows_db = (
        await db.execute(
            select(family, ClubFee.due_date, ClubFee.amount_cents, ClubAthlete.first_name, ClubAthlete.last_name)
            .outerjoin(ClubAthlete, ClubAthlete.id == ClubFee.athlete_id)
            .where(ClubFee.club_id == scope.club_id, ClubFee.status == "DUE", ClubFee.amount_cents > 0)
        )
    ).all()
    buckets = [b for b, _low, _high in accounting.AGING_BUCKETS]
    families: dict[uuid.UUID, dict] = {}
    for family_id, due_date, cents, first, last in rows_db:
        if family_id is None:
            continue
        row = families.setdefault(family_id, {
            "user_id": family_id, "athletes": set(), "fees": 0, "total": 0, "overdue": 0,
            "oldest_due": due_date, **{b: 0 for b in buckets},
        })
        row["fees"] += 1
        row["total"] += int(cents)
        row["overdue"] += int(cents) if due_date < today else 0
        row[accounting.aging_bucket(due_date, today)] += int(cents)
        row["oldest_due"] = min(row["oldest_due"], due_date)
        if first:
            row["athletes"].add(f"{first} {last}")
    names = await _names(db, set(families))
    emails = dict((await db.execute(select(User.id, User.email).where(User.id.in_(list(families))))).all()) if families else {}
    rows = []
    for r in sorted(families.values(), key=lambda r: (-r["overdue"], -r["total"])):
        rows.append({
            "family": names.get(r["user_id"], ""), "email": emails.get(r["user_id"], ""),
            "athletes": ", ".join(sorted(r["athletes"])), "fees": r["fees"],
            **{b: r[b] for b in buckets}, "overdue": r["overdue"], "total": r["total"],
            "oldest_due": r["oldest_due"], "days_overdue": max((today - r["oldest_due"]).days, 0),
        })
    totals = {"family": None, "fees": sum(r["fees"] for r in rows), **{b: sum(r[b] for r in rows) for b in buckets},
              "overdue": sum(r["overdue"] for r in rows), "total": sum(r["total"] for r in rows)}
    return {
        "period": {**_period_out(period), "as_of": today},
        "columns": [_col("family"), _col("email"), _col("athletes"), _col("fees", "int"),
                    *(_col(b, "money") for b in buckets), _col("overdue", "money"), _col("total", "money"),
                    _col("oldest_due", "date"), _col("days_overdue", "int")],
        "rows": rows, "totals": totals,
    }


async def adjustments(db: AsyncSession, *, scope: ClubScope, period: dict, today: date) -> dict:
    """Ciò che non si è incassato per una decisione, con il motivo e chi:
    mesi esenti, condoni, taxa de falta (intera e mezza) e pagamenti
    parziali. La data è quella della decisione (il condono, il pagamento
    parziale); per la mezza taxa de falta, che non la registra, la scadenza."""
    from app.domains.club.people import _names

    start, end = period["start"], period["end"]
    start_at, end_at = accounting._utc(start), accounting._utc(end)
    waived = (
        await db.execute(
            select(ClubFee, ClubAthlete)
            .outerjoin(ClubAthlete, ClubAthlete.id == ClubFee.athlete_id)
            .where(
                ClubFee.club_id == scope.club_id,
                or_(
                    (ClubFee.status == "WAIVED") & ClubFee.waived_at.is_not(None)
                    & (ClubFee.waived_at >= start_at) & (ClubFee.waived_at < end_at),
                    (ClubFee.status == "WAIVED") & ClubFee.waived_at.is_(None)
                    & (ClubFee.due_date >= start) & (ClubFee.due_date < end),
                    (ClubFee.absence_adjustment == "HALF") & (ClubFee.due_date >= start) & (ClubFee.due_date < end),
                    ClubFee.split_from_fee_id.is_not(None) & (ClubFee.created_at >= start_at) & (ClubFee.created_at < end_at),
                ),
            )
        )
    ).all()
    parents = {f.split_from_fee_id for f, _a in waived if f.split_from_fee_id}
    paid_parts = {
        f.id: f for f in (await db.execute(select(ClubFee).where(ClubFee.id.in_(parents)))).scalars()
    } if parents else {}
    actors = {f.waived_by_user_id for f, _a in waived if f.waived_by_user_id}
    actors |= {p.paid_by_user_id for p in paid_parts.values() if p.paid_by_user_id}
    families = {f.guardian_user_id for f, a in waived if a is None and f.guardian_user_id}
    names = await _names(db, actors | families)
    rows = []
    for fee, athlete in waived:
        who = _name(athlete) if athlete is not None else names.get(fee.guardian_user_id, "")
        base = {"athlete": who, "kind": fee.kind, "fee": fee.description, "period": fee.period}
        if fee.split_from_fee_id is not None:
            paid = paid_parts.get(fee.split_from_fee_id)
            rows.append({**base, "date": _day(fee.created_at), "type": "PARTIAL", "amount": fee.amount_cents,
                         "paid": paid.amount_cents if paid is not None else 0, "reason": fee.split_reason or "",
                         "by": names.get(paid.paid_by_user_id, "") if paid is not None and paid.paid_by_user_id else "",
                         "status": fee.status})
            continue
        if fee.status == "WAIVED":
            kind = "EXEMPT" if fee.waive_kind == "EXEMPT" else ("ABSENCE_FULL" if fee.absence_adjustment == "FULL" else "WAIVED")
            amount = accounting.absence_cents(fee) if kind == "ABSENCE_FULL" else fee.amount_cents
            rows.append({**base, "date": _day(fee.waived_at) or fee.due_date, "type": kind, "amount": amount, "paid": 0,
                         "reason": fee.waive_reason or "", "by": names.get(fee.waived_by_user_id, "") if fee.waived_by_user_id else "",
                         "status": fee.status})
        if fee.absence_adjustment == "HALF":
            rows.append({**base, "date": fee.due_date, "type": "ABSENCE_HALF", "amount": accounting.absence_cents(fee),
                         "paid": 0, "reason": "", "by": "", "status": fee.status})
    rows.sort(key=lambda r: (r["date"], r["athlete"]), reverse=True)
    types = ("EXEMPT", "WAIVED", "ABSENCE_FULL", "ABSENCE_HALF", "PARTIAL")
    return {
        "period": _period_out(period),
        "columns": [_col("date", "date"), _col("type", "code"), _col("athlete"), _col("fee", "fee"),
                    _col("amount", "money"), _col("paid", "money"), _col("reason"), _col("by"), _col("status", "code")],
        "rows": rows,
        "totals": {"date": None, "amount": sum(r["amount"] for r in rows), "paid": sum(r["paid"] for r in rows)},
        "by_type": {t: {"count": sum(1 for r in rows if r["type"] == t),
                        "cents": sum(r["amount"] for r in rows if r["type"] == t)} for t in types},
    }


async def cash(db: AsyncSession, *, scope: ClubScope, period: dict, today: date) -> dict:
    """I contanti: chi li ha ricevuti, mese per mese (il nome congelato
    sulla quota pagata, la persona dello staff o il nome scritto a mano)."""
    month = accounting._month_of(ClubFee.paid_at)
    rows_db = (
        await db.execute(
            select(ClubFee.cash_received_by_user_id, ClubFee.cash_received_by_name, month,
                   func.sum(ClubFee.amount_cents), func.count())
            .where(
                ClubFee.club_id == scope.club_id, ClubFee.status == "PAID", ClubFee.payment_method == "CASH",
                ClubFee.paid_at >= accounting._utc(period["start"]), ClubFee.paid_at < accounting._utc(period["end"]),
            )
            .group_by(ClubFee.cash_received_by_user_id, ClubFee.cash_received_by_name, month)
        )
    ).all()
    keys = [_key(y, m) for y, m in period["months"]]
    people: dict[str, dict] = {}
    for user_id, name, m, cents, n in rows_db:
        ident = str(user_id) if user_id else f"name:{(name or '').strip().lower()}"
        row = people.setdefault(ident, {"receiver": (name or "").strip() or "—", "payments": 0, "total": 0,
                                        **{k: 0 for k in keys}})
        row[m] = row.get(m, 0) + int(cents or 0)
        row["payments"] += int(n)
        row["total"] += int(cents or 0)
    rows = sorted(people.values(), key=lambda r: -r["total"])
    totals = {"receiver": None, **{k: sum(r[k] for r in rows) for k in keys},
              "payments": sum(r["payments"] for r in rows), "total": sum(r["total"] for r in rows)}
    return {
        "period": _period_out(period),
        "columns": [_col("receiver"), *(_col(k, "money", month=k) for k in keys), _col("payments", "int"),
                    _col("total", "money")],
        "rows": rows, "totals": totals,
    }


async def pnl(db: AsyncSession, *, scope: ClubScope, period: dict, today: date) -> dict:
    """Il conto economico mese per mese: gli stessi numeri della
    contabilità (accounting.monthly_figures)."""
    figures = await accounting.monthly_figures(db, club_ids=[scope.club_id], start=period["start"], end=period["end"])
    rows = []
    for year, mon in period["months"]:
        key = _key(year, mon)
        f = figures.get((scope.club_id, key), accounting.Figures()).as_dict()
        rows.append({
            "month": key, "issued": f["issued_cents"], "income": f["income_cents"], "credit": f["credit_cents"],
            "collection_rate": f["collection_rate"], "expenses": f["expenses_cents"], "staff": f["staff_cents"],
            "coach_share": f["coach_share_cents"], "platform_fee": f["platform_fee_cents"],
            "result": f["result_cents"], "missed": f["missed_cents"], "exempt": f["exempt_cents"],
        })
    sums = ("issued", "income", "credit", "expenses", "staff", "coach_share", "platform_fee", "result", "missed", "exempt")
    totals = {"month": None, **{k: sum(r[k] for r in rows) for k in sums}}
    issued_paid = sum(
        figures.get((scope.club_id, _key(y, m)), accounting.Figures()).issued_paid_cents for y, m in period["months"]
    )
    totals["collection_rate"] = round(issued_paid * 100 / totals["issued"]) if totals["issued"] else None
    return {
        "period": _period_out(period),
        "columns": [_col("month", "month"), _col("issued", "money"), _col("income", "money"), _col("credit", "money"),
                    _col("collection_rate", "pct"), _col("expenses", "money"), _col("staff", "money"),
                    _col("coach_share", "money"), _col("platform_fee", "money"), _col("result", "money"),
                    _col("missed", "money"), _col("exempt", "money")],
        "rows": rows, "totals": totals,
    }


BUILDERS = {"matrix": matrix, "collections": collections, "debts": debts, "adjustments": adjustments,
            "cash": cash, "pnl": pnl}


async def build(db: AsyncSession, *, scope: ClubScope, report: str, period: dict, today: date) -> dict:
    if report not in BUILDERS:
        raise ClubValidationError("Relatório sconosciuto.")
    return {"report": report, **await BUILDERS[report](db, scope=scope, period=period, today=today)}


# --- I file ---------------------------------------------------------------------------------------

#: (pt, en, it) — l'ordine di `_lang`.
LABELS: dict[str, tuple[str, str, str]] = {
    "title.matrix": ("Mensalidades por atleta", "Monthly fees by athlete", "Mensilità per atleta"),
    "title.collections": ("Recebimentos por mês e método", "Collections by month and method", "Incassi per mese e metodo"),
    "title.debts": ("Dívidas por família", "Debts by family", "Debiti per famiglia"),
    "title.adjustments": ("Isenções, perdões e pagamentos parciais", "Exemptions, waivers and partial payments",
                          "Esenzioni, condoni e pagamenti parziali"),
    "title.cash": ("Numerário recebido por pessoa", "Cash received per person", "Contanti ricevuti per persona"),
    "title.pnl": ("Receitas e despesas por mês", "Income and expenses by month", "Entrate e uscite per mese"),
    "detail": ("Detalhe", "Detail", "Dettaglio"),
    "legend": ("Legenda", "Legend", "Legenda"),
    "col.name": ("Atleta", "Athlete", "Atleta"),
    "col.member_number": ("N.º sócio", "Member no.", "N. socio"),
    "col.group": ("Grupo", "Group", "Gruppo"),
    "col.status": ("Estado", "Status", "Stato"),
    "col.month": ("Mês", "Month", "Mese"),
    "col.state": ("Situação", "State", "Situazione"),
    "col.paid_on": ("Pago em", "Paid on", "Pagata il"),
    "col.method": ("Método", "Method", "Metodo"),
    "col.receiver": ("Recebido por", "Received by", "Ricevuti da"),
    "col.reason": ("Motivo", "Reason", "Motivo"),
    "col.paid_cents": ("Pago", "Paid", "Pagato"),
    "col.due_cents": ("Em dívida", "Owed", "Da pagare"),
    "col.overdue_cents": ("Em atraso", "Overdue", "Scaduto"),
    "col.waived_cents": ("Isento/perdoado", "Exempt/waived", "Esente/condonato"),
    "col.months_paid": ("Meses pagos", "Months paid", "Mesi pagati"),
    "col.total_row": ("Total", "Total", "Totale"),
    "col.payments": ("Pagamentos", "Payments", "Pagamenti"),
    "col.total": ("Total", "Total", "Totale"),
    "col.family": ("Família", "Family", "Famiglia"),
    "col.email": ("Email", "Email", "Email"),
    "col.athletes": ("Atletas", "Athletes", "Atleti"),
    "col.fees": ("Quotas", "Fees", "Quote"),
    "col.NOT_DUE": ("A vencer", "Not yet due", "Non scadute"),
    "col.D0_30": ("1–30 dias", "1–30 days", "1–30 giorni"),
    "col.D31_60": ("31–60 dias", "31–60 days", "31–60 giorni"),
    "col.D61_90": ("61–90 dias", "61–90 days", "61–90 giorni"),
    "col.D90_PLUS": ("Mais de 90 dias", "Over 90 days", "Oltre 90 giorni"),
    "col.overdue": ("Em atraso", "Overdue", "Scaduto"),
    "col.oldest_due": ("Vencimento mais antigo", "Oldest due date", "Scadenza più vecchia"),
    "col.days_overdue": ("Dias de atraso", "Days overdue", "Giorni di ritardo"),
    "col.date": ("Data", "Date", "Data"),
    "col.type": ("Tipo", "Type", "Tipo"),
    "col.athlete": ("Atleta", "Athlete", "Atleta"),
    "col.fee": ("Quota", "Fee", "Quota"),
    "col.amount": ("Valor", "Amount", "Importo"),
    "col.paid": ("Pago", "Paid", "Pagato"),
    "col.by": ("Decidido por", "Decided by", "Deciso da"),
    "col.issued": ("Emitido", "Issued", "Emesso"),
    "col.income": ("Receitas", "Income", "Incassi"),
    "col.credit": ("Dos quais crédito", "Of which credit", "Di cui credito"),
    "col.collection_rate": ("Taxa de cobrança %", "Collection rate %", "Riscossione %"),
    "col.expenses": ("Despesas", "Expenses", "Spese"),
    "col.staff": ("Pessoal", "Staff", "Personale"),
    "col.coach_share": ("Parte dos treinadores", "Coaches' share", "Parte dei treinador"),
    "col.platform_fee": ("Comissão", "Platform fee", "Commissione"),
    "col.result": ("Resultado", "Result", "Risultato"),
    "col.missed": ("Receita perdida", "Revenue forgone", "Mancati incassi"),
    "col.exempt": ("Meses isentos", "Exempt months", "Mesi esenti"),
    "method.BANK_TRANSFER": ("Transferência", "Bank transfer", "Bonifico"),
    "method.MBWAY": ("MB Way", "MB Way", "MB Way"),
    "method.CASH": ("Numerário", "Cash", "Contanti"),
    "method.CARD": ("Cartão", "Card", "Carta"),
    "method.WALLET": ("Crédito", "Credit", "Credito"),
    "method.UNKNOWN": ("Não indicado", "Not recorded", "Non indicato"),
    "method.MIXED": ("Vários", "Mixed", "Misto"),
    "state.PAID": ("Pago", "Paid", "Pagata"),
    "state.PARTIAL": ("Parcial", "Partial", "Parziale"),
    "state.DUE": ("Por pagar", "Due", "Da pagare"),
    "state.OVERDUE": ("Em atraso", "Overdue", "Scaduta"),
    "state.WAIVED": ("Perdoada", "Waived", "Condonata"),
    "state.MONTH_EXEMPT": ("Isento este mês", "Exempt this month", "Esente questo mese"),
    "state.EXEMPT": ("Isento", "Exempt", "Esente"),
    "state.NOT_ENROLLED": ("Não inscrito", "Not enrolled", "Non iscritto"),
    "state.UPCOMING": ("Futuro", "Upcoming", "Futuro"),
    "state.NONE": ("Sem quota", "Not billed", "Non emessa"),
    "type.EXEMPT": ("Isento este mês", "Exempt this month", "Esente questo mese"),
    "type.WAIVED": ("Perdoada", "Waived", "Condonata"),
    "type.ABSENCE_FULL": ("Taxa de falta (total)", "Absence rate (full)", "Taxa de falta (intera)"),
    "type.ABSENCE_HALF": ("Taxa de falta (metade)", "Absence rate (half)", "Taxa de falta (metà)"),
    "type.PARTIAL": ("Pagamento parcial", "Partial payment", "Pagamento parziale"),
    "status.DUE": ("Por pagar", "Due", "Da pagare"),
    "status.PAID": ("Pago", "Paid", "Pagata"),
    "status.WAIVED": ("Perdoada", "Waived", "Condonata"),
    "status.ACTIVE": ("Ativo", "Active", "Attivo"),
    "status.SUSPENDED": ("Suspenso", "Suspended", "Sospeso"),
    "status.LEFT": ("Saiu", "Left", "Uscito"),
}
MONTHS = {
    "pt": ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"),
    "en": ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
    "it": ("gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"),
}
_LANGS = ("pt", "en", "it")
_NEAREST = {"es": "pt", "fr": "en", "de": "en", "uk": "en"}

#: I colori delle caselle dell'XLSX, come nel quadro del mese.
STATE_FILL = {
    "PAID": "D1FAE5", "PARTIAL": "FEF3C7", "DUE": "FFF7ED", "OVERDUE": "FFE4E6", "WAIVED": "E5E7EB",
    "MONTH_EXEMPT": "E0F2FE", "EXEMPT": "E0F2FE", "NOT_ENROLLED": "F9FAFB", "UPCOMING": "F9FAFB", "NONE": "F9FAFB",
}


def _lang(value: str | None) -> str:
    value = _NEAREST.get(value or "", value)
    return value if value in _LANGS else "pt"


def label(key: str, lang: str) -> str:
    texts = LABELS.get(key)
    return texts[_LANGS.index(lang)] if texts else key.split(".", 1)[-1]


def _month_name(key: str, lang: str) -> str:
    year, mon = key.split("-")
    return f"{MONTHS[lang][int(mon) - 1]} {year}"


def _euro(cents: int | None, lang: str) -> str:
    if cents is None:
        return ""
    text = f"{cents / 100:,.2f}"
    if lang != "en":
        text = text.replace(",", " ").replace(".", ",").replace(" ", ".")
    return text


def _short_date(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d is not None else ""


def _cell_text(cell: dict, lang: str) -> str:
    """Una casella della matrice in parole: «35,00 · 12/10 · MB Way»."""
    state = cell["state"]
    if state == "PAID":
        bits = [_euro(cell["paid_cents"], lang)]
        if cell["paid_on"]:
            bits.append(cell["paid_on"].strftime("%d/%m"))
        if cell["method"]:
            bits.append(label(f"method.{cell['method']}", lang))
        return " · ".join(bits)
    if state == "PARTIAL":
        return f"{label('state.PARTIAL', lang)} {_euro(cell['paid_cents'], lang)} / {label('col.due_cents', lang).lower()} {_euro(cell['due_cents'], lang)}"
    if state in ("DUE", "OVERDUE"):
        return f"{label(f'state.{state}', lang)} {_euro(cell['due_cents'], lang)}"
    if state in ("MONTH_EXEMPT", "WAIVED"):
        return label(f"state.{state}", lang) + (f": {cell['reason']}" if cell.get("reason") else "")
    if state in ("NONE", "NOT_ENROLLED", "UPCOMING"):
        return ""
    return label(f"state.{state}", lang)


def _table_of(data: dict, lang: str) -> tuple[list[str], list[list], list[str]]:
    """(intestazioni, righe, tipi) di una tabella o della matrice, pronte per
    il file. I tipi dicono all'XLSX come formattare la colonna."""
    if data["report"] == "matrix":
        headers = [label("col.name", lang), label("col.member_number", lang), label("col.group", lang),
                   *(_month_name(k, lang) for k in data["months"]),
                   label("col.paid_cents", lang), label("col.due_cents", lang), label("col.overdue_cents", lang),
                   label("col.waived_cents", lang), label("col.months_paid", lang)]
        types = ["text", "text", "text", *(["cell"] * len(data["months"])), "money", "money", "money", "money", "int"]
        rows = [[r["name"], r["member_number"] or "", r["group"] or "", *r["cells"], r["paid_cents"], r["due_cents"],
                 r["overdue_cents"], r["waived_cents"], r["months_paid"]] for r in data["rows"]]
        t = data["totals"]
        rows.append([label("col.total_row", lang), "", "", *({"total": c} for c in data["columns"]),
                     t["paid_cents"], t["due_cents"], t["overdue_cents"], t["waived_cents"], None])
        return headers, rows, types
    cols = data["columns"]
    headers = []
    for c in cols:
        if c.get("month"):
            headers.append(_month_name(c["month"], lang))
        elif c.get("method"):
            headers.append(label(f"method.{c['method']}", lang))
        else:
            headers.append(label(f"col.{c['key']}", lang))
    types = [c["type"] for c in cols]
    rows = [[r.get(c["key"]) for c in cols] for r in data["rows"]]
    if data.get("totals"):
        total = [data["totals"].get(c["key"]) for c in cols]
        total[0] = label("col.total_row", lang)
        rows.append(total)
    return headers, rows, types


def _plain(value, type_: str, lang: str):
    """Il valore per il CSV: importi con la virgola (Excel in portoghese)."""
    if value is None:
        return ""
    if type_ == "cell":
        if "total" in value:
            col = value["total"]
            return _euro(col["paid_cents"], lang) + (f" / {_euro(col['due_cents'], lang)}" if col["due_cents"] else "")
        return _cell_text(value, lang)
    if type_ == "money":
        return _euro(value, lang)
    if type_ == "month":
        return _month_name(value, lang) if isinstance(value, str) and len(value) == 7 and value[4] == "-" else value
    if type_ == "date":
        return _short_date(value) if isinstance(value, date) else value
    if type_ == "code":
        prefix = "type" if value in ("EXEMPT", "WAIVED", "ABSENCE_FULL", "ABSENCE_HALF", "PARTIAL") else "status"
        return label(f"{prefix}.{value}", lang)
    return value


def filename(data: dict, ext: str) -> str:
    return f"relatorio-{data['report']}-{data['period']['key']}.{ext}"


def to_csv(data: dict, *, lang: str | None) -> bytes:
    """CSV con il punto e virgola e il BOM: si apre bene con Excel in
    portoghese o italiano (dove la virgola è il separatore dei decimali)."""
    lang = _lang(lang)
    headers, rows, types = _table_of(data, lang)
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";" if lang != "en" else ",", lineterminator="\r\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow([_plain(v, t, lang) for v, t in zip(row, types, strict=True)])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def to_xlsx(data: dict, *, lang: str | None) -> bytes:
    """Un foglio con la tabella (importi come numeri in euro, intestazioni
    fisse, colonne larghe il giusto); la matrice ha le caselle colorate per
    stato, una legenda, e un secondo foglio «Dettaglio» con una riga per
    atleta e mese, comodo per le tabelle pivot."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    lang = _lang(lang)
    headers, rows, types = _table_of(data, lang)
    wb = Workbook()
    ws = wb.active
    title = label("title." + data["report"], lang)
    ws.title = title[:31]
    bold = Font(bold=True)
    header_fill = PatternFill("solid", fgColor="1F2937")
    money_fmt = '#,##0.00 "€"'
    ws.append([f"{title} — {data['period']['label']}"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append(headers)
    for idx in range(1, len(headers) + 1):
        c = ws.cell(row=2, column=idx)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = header_fill
        c.alignment = Alignment(wrap_text=True, vertical="center")
    last = len(rows)
    for i, row in enumerate(rows, start=1):
        out = []
        for value, type_ in zip(row, types, strict=True):
            if type_ == "money":
                out.append(value / 100 if isinstance(value, int) else value)
            elif type_ in ("cell", "code", "month"):
                out.append(_plain(value, type_, lang))
            else:
                out.append(value)
        ws.append(out)
        r = ws.max_row
        for idx, (value, type_) in enumerate(zip(row, types, strict=True), start=1):
            c = ws.cell(row=r, column=idx)
            if type_ == "money":
                c.number_format = money_fmt
            elif type_ == "date" and isinstance(value, date):
                c.number_format = "dd/mm/yyyy"
            elif type_ == "cell" and isinstance(value, dict) and "state" in value:
                c.fill = PatternFill("solid", fgColor=STATE_FILL.get(value["state"], "FFFFFF"))
                c.alignment = Alignment(wrap_text=True, vertical="top")
            if i == last and data.get("totals") is not None:
                c.font = bold
    ws.freeze_panes = "B3" if data["report"] != "matrix" else "D3"
    for idx, type_ in enumerate(types, start=1):
        width = {"cell": 18, "money": 13, "int": 10, "pct": 10, "date": 12, "month": 12, "code": 20}.get(type_, 24)
        ws.column_dimensions[get_column_letter(idx)].width = width

    if data["report"] == "matrix":
        ws.append([])
        ws.append([label("legend", lang)])
        ws.cell(row=ws.max_row, column=1).font = bold
        for state in ("PAID", "PARTIAL", "DUE", "OVERDUE", "MONTH_EXEMPT", "WAIVED", "EXEMPT", "NONE"):
            ws.append([label(f"state.{state}", lang)])
            ws.cell(row=ws.max_row, column=1).fill = PatternFill("solid", fgColor=STATE_FILL[state])
        detail = wb.create_sheet(label("detail", lang)[:31])
        detail.append([label(f"col.{k}", lang) for k in (
            "name", "member_number", "group", "month", "state", "paid_cents", "due_cents", "waived_cents",
            "paid_on", "method", "receiver", "reason")])
        for c in detail[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = header_fill
        for r in data["rows"]:
            for cell in r["cells"]:
                detail.append([
                    r["name"], r["member_number"] or "", r["group"] or "", _month_name(cell["period"], lang),
                    label(f"state.{cell['state']}", lang), cell["paid_cents"] / 100, cell["due_cents"] / 100,
                    cell["waived_cents"] / 100, cell["paid_on"],
                    label(f"method.{cell['method']}", lang) if cell["method"] else "", cell["receiver"] or "",
                    cell["reason"] or "",
                ])
                row_no = detail.max_row
                for col in (6, 7, 8):
                    detail.cell(row=row_no, column=col).number_format = money_fmt
                detail.cell(row=row_no, column=9).number_format = "dd/mm/yyyy"
        detail.freeze_panes = "B2"
        for idx, width in enumerate((24, 10, 18, 12, 18, 11, 11, 11, 12, 14, 18, 36), start=1):
            detail.column_dimensions[get_column_letter(idx)].width = width
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
