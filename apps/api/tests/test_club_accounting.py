"""La contabilità del club, della piattaforma e delle famiglie
(club/accounting.py, docs/club-portal.md "Contabilità").

Le promesse: l'incasso è ciò che è stato pagato, nel mese in cui è stato
pagato; il costo dello staff è ore × tariffa di quel giorno, solo per i
turni chiusi; la commissione della piattaforma usa la percentuale di quel
mese e cambiarla non riscrive il passato; i costi fissi diventano spese una
volta sola per mese; i debiti si contano per anzianità; un club non vede i
numeri di un altro; una famiglia vede un conto solo, persona per persona
solo se ha figli; e la percentuale la cambia solo il superadmin.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import func, select

from app.domains.club import accounting
from app.domains.club import service as club_service
from app.domains.club.models import Club, ClubExpense, ClubFee, ClubWorkSession
from app.domains.club.scope import ClubScope
from tests.test_club_fees import _athlete, _fees, _plans, _user

OCTOBER = accounting.Period(key="2026-10", kind="month", start=date(2026, 10, 1), end=date(2026, 11, 1))
TODAY = date(2026, 10, 20)


async def _other_club(db, organization_id) -> ClubScope:
    club = Club(organization_id=organization_id, name="Judo Clube de Lagos", slug="lagos-acc", settings={})
    db.add(club)
    await db.commit()
    return ClubScope(organization_id=organization_id, club_id=club.id)


async def _pay(db, fee: ClubFee, on: datetime) -> None:
    fee.status = "PAID"
    fee.paid_at = on
    await db.commit()


async def _family_with_paid_october(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    child = await _athlete(db, scope, parent, birth_date=date(2014, 4, 4))
    monthly = (await _fees(db, child.id, kind="MONTHLY", period="2026-10"))[0]
    await _pay(db, monthly, datetime(2026, 10, 12, 9, 0, tzinfo=UTC))
    return admin, parent, child, monthly


def test_aging_buckets():
    today = date(2026, 10, 20)
    assert accounting.aging_bucket(date(2026, 10, 20), today) == "NOT_DUE"
    assert accounting.aging_bucket(date(2026, 11, 1), today) == "NOT_DUE"
    assert accounting.aging_bucket(date(2026, 10, 19), today) == "D0_30"
    assert accounting.aging_bucket(date(2026, 9, 20), today) == "D0_30"
    assert accounting.aging_bucket(date(2026, 9, 19), today) == "D31_60"
    assert accounting.aging_bucket(date(2026, 8, 20), today) == "D61_90"
    assert accounting.aging_bucket(date(2026, 7, 21), today) == "D90_PLUS"


def test_platform_fee_rounding_and_history():
    assert accounting.fee_cents(4000, Decimal(10)) == 400
    assert accounting.fee_cents(3333, Decimal("7.5")) == 250  # 249,975 -> 250
    history = [(date(2026, 11, 1), Decimal("7.5"))]
    assert accounting.pct_on(history, "2026-10") == Decimal(10)  # il default, prima della modifica
    assert accounting.pct_on(history, "2026-11") == Decimal("7.5")
    assert accounting.pct_on(history, "2027-03") == Decimal("7.5")


async def test_the_month_adds_up(db, scope):
    admin, _parent, _child, monthly = await _family_with_paid_october(db, scope)
    await accounting.create_expense(db, scope=scope, actor_user_id=admin.id, today=TODAY, data={
        "spent_on": date(2026, 10, 5), "category": "RENT", "amount_cents": 10000, "description": "Affitto ottobre",
    })
    await accounting.set_staff_rate(
        db, scope=scope, user_id=admin.id, hourly_rate_cents=1500, valid_from=date(2026, 9, 1), actor_user_id=admin.id,
    )
    db.add(ClubWorkSession(**scope.columns(), user_id=admin.id,
                           started_at=datetime(2026, 10, 6, 17, 0, tzinfo=UTC), ended_at=datetime(2026, 10, 6, 19, 0, tzinfo=UTC)))
    await db.commit()

    summary = await accounting.club_summary(db, scope=scope, period=OCTOBER, today=TODAY)
    t = summary["totals"]
    assert t["income_cents"] == monthly.amount_cents == 4000
    assert t["income_by_kind"]["MONTHLY"] == 4000
    assert t["expenses_by_category"]["RENT"] == 10000
    assert t["staff_cents"] == 3000 and t["staff_minutes"] == 120
    assert t["costs_cents"] == 13000
    assert t["platform_fee_cents"] == 400
    assert t["result_cents"] == 4000 - 13000 - 400
    issued = (
        await db.execute(
            select(func.sum(ClubFee.amount_cents)).where(
                ClubFee.club_id == scope.club_id, ClubFee.due_date >= OCTOBER.start, ClubFee.due_date < OCTOBER.end,
            )
        )
    ).scalar_one()
    assert t["issued_cents"] == issued and t["issued_paid_cents"] == 4000
    assert t["collection_rate"] == round(4000 * 100 / issued)
    assert summary["series"][-1]["month"] == "2026-10" and len(summary["series"]) == 12
    # Il mese non è finito: la previsione aggiunge ciò che scade e non è pagato.
    assert summary["forecast"]["expected_cents"] == issued - 4000

    # Pagata a novembre: è incasso di novembre, non di ottobre.
    november = accounting.parse_period("2026-11", today=TODAY)
    await _pay(db, monthly, datetime(2026, 11, 2, tzinfo=UTC))
    assert (await accounting.club_summary(db, scope=scope, period=OCTOBER, today=TODAY))["totals"]["income_cents"] == 0
    assert (await accounting.club_summary(db, scope=scope, period=november, today=TODAY))["totals"]["income_cents"] == 4000


async def test_a_new_percentage_does_not_rewrite_the_past(db, scope):
    admin, _parent, _child, _monthly = await _family_with_paid_october(db, scope)
    await accounting.set_platform_fee(
        db, organization_id=scope.organization_id, club_id=scope.club_id, pct=Decimal(5),
        actor_user_id=admin.id, today=date(2026, 11, 3),
    )
    # Ottobre resta al 10%, la percentuale nuova vale da novembre.
    summary = await accounting.club_summary(db, scope=scope, period=OCTOBER, today=TODAY)
    assert summary["totals"]["platform_fee_cents"] == 400
    # Cambiarla due volte nello stesso mese aggiorna la stessa riga.
    await accounting.set_platform_fee(
        db, organization_id=scope.organization_id, club_id=scope.club_id, pct=Decimal(6),
        actor_user_id=admin.id, today=date(2026, 11, 20),
    )
    options = await accounting.club_options(db, organization_id=scope.organization_id, club_id=scope.club_id)
    assert [h["pct"] for h in options["history"]] == [Decimal("6.00")]
    with pytest.raises(club_service.ClubValidationError):
        await accounting.set_platform_fee(
            db, organization_id=scope.organization_id, club_id=scope.club_id, pct=Decimal(101),
            actor_user_id=admin.id,
        )


async def test_recurring_costs_are_booked_once_per_month(db, scope):
    admin = await _user(db, scope, "admin")
    rent = await accounting.create_recurring(db, scope=scope, actor_user_id=admin.id, today=TODAY, data={
        "category": "RENT", "amount_cents": 50000, "description": "Affitto palestra", "day_of_month": 5,
        "starts_on": date(2026, 8, 1),
    })

    async def booked():
        return list((await db.execute(
            select(ClubExpense.period).where(ClubExpense.recurring_id == rent.id).order_by(ClubExpense.period)
        )).scalars())

    # Creato oggi con inizio ad agosto: agosto, settembre e ottobre subito.
    assert await booked() == ["2026-08", "2026-09", "2026-10"]
    # Il job rilanciato (anche due volte) non crea doppioni.
    assert await accounting.materialise_recurring(db, scope=scope, today=TODAY) == 0
    assert await accounting.materialise_recurring(db, scope=scope, today=TODAY, backfill=True) == 0
    # Il mese dopo, una spesa nuova; ancora una volta sola.
    assert await accounting.materialise_recurring(db, scope=scope, today=date(2026, 11, 1)) == 1
    assert await accounting.materialise_recurring(db, scope=scope, today=date(2026, 11, 2)) == 0
    assert await booked() == ["2026-08", "2026-09", "2026-10", "2026-11"]

    # Una spesa di un costo fisso non si cancella (il job la ricreerebbe):
    # si corregge; il costo fisso con mesi registrati si ferma, non sparisce.
    expense = (await db.execute(select(ClubExpense).where(ClubExpense.period == "2026-10", ClubExpense.recurring_id == rent.id))).scalar_one()
    with pytest.raises(club_service.ClubValidationError):
        await accounting.delete_expense(db, scope=scope, expense_id=expense.id, actor_user_id=admin.id)
    await accounting.update_expense(db, scope=scope, expense_id=expense.id, actor_user_id=admin.id, data={"amount_cents": 52000})
    assert await accounting.delete_recurring(db, scope=scope, recurring_id=rent.id, actor_user_id=admin.id) is False
    assert await accounting.materialise_recurring(db, scope=scope, today=date(2026, 12, 1)) == 0
    summary = await accounting.club_summary(db, scope=scope, period=OCTOBER, today=TODAY)
    assert summary["totals"]["expenses_by_category"]["RENT"] == 52000


async def test_staff_cost_uses_the_rate_of_the_day_and_only_closed_shifts(db, scope):
    admin = await _user(db, scope, "admin")
    coach = await _user(db, scope, "treinador")
    await accounting.set_staff_rate(db, scope=scope, user_id=coach.id, hourly_rate_cents=1000,
                                    valid_from=date(2026, 9, 1), actor_user_id=admin.id)
    await accounting.set_staff_rate(db, scope=scope, user_id=coach.id, hourly_rate_cents=1500,
                                    valid_from=date(2026, 10, 10), actor_user_id=admin.id)
    db.add_all([
        ClubWorkSession(**scope.columns(), user_id=coach.id, started_at=datetime(2026, 10, 5, 18, tzinfo=UTC),
                        ended_at=datetime(2026, 10, 5, 19, tzinfo=UTC)),
        ClubWorkSession(**scope.columns(), user_id=coach.id, started_at=datetime(2026, 10, 12, 18, tzinfo=UTC),
                        ended_at=datetime(2026, 10, 12, 20, tzinfo=UTC)),
        # Ancora aperto: non è un costo finché non si chiude.
        ClubWorkSession(**scope.columns(), user_id=coach.id, started_at=datetime(2026, 10, 19, 18, tzinfo=UTC)),
    ])
    await db.commit()

    rows = {r["user_id"]: r for r in await accounting.staff_costs(db, scope=scope, period=OCTOBER, today=TODAY)}
    assert rows[coach.id]["minutes"] == 180
    assert rows[coach.id]["cost_cents"] == 1000 + 3000
    assert rows[coach.id]["hourly_rate_cents"] == 1500
    summary = await accounting.club_summary(db, scope=scope, period=OCTOBER, today=TODAY)
    assert summary["totals"]["staff_cents"] == 4000
    ledger = await accounting.ledger(db, scope=scope, period=OCTOBER)
    assert [r["amount_cents"] for r in ledger["rows"] if r["type"] == "STAFF"] == [-4000]

    # Solo persone del club.
    lagos = await _other_club(db, scope.organization_id)
    stranger = await _user(db, lagos, "altro")
    with pytest.raises(club_service.ClubNotFoundError):
        await accounting.set_staff_rate(db, scope=scope, user_id=stranger.id, hourly_rate_cents=1000, actor_user_id=admin.id)


async def test_debts_by_age_and_by_family(db, scope):
    _admin, parent, _child, _monthly = await _family_with_paid_october(db, scope)
    report = await accounting.debts(db, scope=scope, today=date(2026, 12, 20))
    due = (
        await db.execute(
            select(func.sum(ClubFee.amount_cents)).where(ClubFee.club_id == scope.club_id, ClubFee.status == "DUE")
        )
    ).scalar_one()
    assert report["total_cents"] == due > 0
    # Iscrizione e quota socio scadevano a metà ottobre: due mesi e più.
    assert report["aging"]["D61_90"]["cents"] == due
    assert report["top"][0]["user_id"] == parent.id
    assert report["top"][0]["overdue_cents"] == due


async def test_a_club_never_sees_another_clubs_numbers(db, scope):
    await _family_with_paid_october(db, scope)
    lagos = await _other_club(db, scope.organization_id)
    admin_lagos = await _user(db, lagos, "admin-lagos")
    await _plans(db, lagos, admin_lagos)
    lagos_parent = await _user(db, lagos)
    lagos_child = await _athlete(db, lagos, lagos_parent, birth_date=date(2014, 4, 4), first_name="Rui")
    lagos_fee = (await _fees(db, lagos_child.id, kind="MONTHLY", period="2026-10"))[0]
    await _pay(db, lagos_fee, datetime(2026, 10, 3, tzinfo=UTC))
    lagos_expense = await accounting.create_expense(db, scope=lagos, actor_user_id=admin_lagos.id, today=TODAY, data={
        "spent_on": date(2026, 10, 1), "category": "EQUIPMENT", "amount_cents": 7000, "description": "Tatami",
    })

    mine = await accounting.club_summary(db, scope=scope, period=OCTOBER, today=TODAY)
    assert mine["totals"]["income_cents"] == 4000
    assert mine["totals"]["expenses_cents"] == 0
    assert all(r["category"] != "EQUIPMENT" for r in (await accounting.ledger(db, scope=scope, period=OCTOBER))["rows"])
    with pytest.raises(club_service.ClubNotFoundError):
        await accounting.update_expense(db, scope=scope, expense_id=lagos_expense.id, actor_user_id=admin_lagos.id,
                                        data={"amount_cents": 1})

    platform = await accounting.platform_summary(db, organization_id=scope.organization_id, year=2026, today=TODAY)
    by_club = {c["id"]: c for c in platform["clubs"]}
    assert by_club[scope.club_id]["month"]["income_cents"] == 4000
    assert by_club[lagos.club_id]["month"]["income_cents"] == 4000
    assert by_club[lagos.club_id]["month"]["costs_cents"] == 7000
    assert platform["earnings"]["month_cents"] == 800
    assert platform["earnings"]["all_time_cents"] == 800
    assert platform["totals"]["athletes_active"] == 2


async def test_one_account_split_by_person_only_with_children(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    adult = await _user(db, scope, "atleta")
    me = await _athlete(db, scope, adult, birth_date=date(1985, 3, 3), first_name="Ana", is_self=True)

    account = await accounting.personal_account(db, scope=scope, user_id=adult.id, year=2026, today=TODAY)
    assert account["is_athlete"] and not account["has_children"]
    assert account["people"] == []
    own_fees = await _fees(db, me.id)
    assert account["totals"]["due_cents"] == sum(f.amount_cents for f in own_fees if f.status == "DUE")

    # Diventa anche genitore: lo stesso conto, ora diviso persona per persona.
    kid = await _athlete(db, scope, adult, birth_date=date(2016, 6, 6), first_name="Bia", sex="F")
    kid_monthly = (await _fees(db, kid.id, kind="MONTHLY", period="2026-10"))[0]
    await _pay(db, kid_monthly, datetime(2026, 10, 11, tzinfo=UTC))
    account = await accounting.personal_account(db, scope=scope, user_id=adult.id, year=2026, today=TODAY)
    assert account["has_children"]
    people = {p["athlete_id"]: p for p in account["people"]}
    assert set(people) >= {me.id, kid.id}
    assert people[kid.id]["paid_year_cents"] == kid_monthly.amount_cents
    assert account["totals"]["paid_year_cents"] == kid_monthly.amount_cents
    assert account["totals"]["paid_by_kind"]["MONTHLY"] == kid_monthly.amount_cents
    assert sum(p["due_cents"] for p in account["people"]) == account["totals"]["due_cents"]
    assert account["series"][9]["fees_cents"] == kid_monthly.amount_cents  # ottobre

    # Un'altra famiglia non compare.
    other = await _user(db, scope, "altra")
    assert (await accounting.personal_account(db, scope=scope, user_id=other.id, year=2026, today=TODAY))["totals"]["paid_all_time_cents"] == 0


async def _client(db, monkeypatch, *, user, scope, granted: set[str]):
    from app.core import deps
    from app.core.db import get_db
    from app.core.deps import CurrentUser, get_current_user
    from app.main import app

    async def _codes(*args, **kwargs):
        return granted

    monkeypatch.setattr(deps, "get_permission_codes_for_user", _codes)

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=user.id, organization_id=scope.organization_id, roles=["SECRETARY"]
    )
    return app, httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/api")


async def test_only_the_superadmin_changes_the_percentage(db, scope, monkeypatch):
    secretary = await _user(db, scope, "segreteria")
    app, client = await _client(db, monkeypatch, user=secretary, scope=scope, granted={"club.manage", "clubs.enter"})
    try:
        async with client:
            denied = await client.put(f"/clubs/{scope.club_id}/platform-fee", json={"pct": "2"})
            assert denied.status_code == 403
            summary = await client.get("/club/admin/accounting/summary", params={"period": "2026"})
            assert summary.status_code == 200, summary.text
            assert Decimal(summary.json()["platform_fee_pct"]) == Decimal(10)
            assert (await client.get("/club/admin/accounting/summary", params={"period": "ottobre"})).status_code == 400
    finally:
        app.dependency_overrides.clear()

    app, client = await _client(db, monkeypatch, user=secretary, scope=scope, granted={"clubs.manage", "clubs.enter"})
    try:
        async with client:
            done = await client.put(f"/clubs/{scope.club_id}/platform-fee", json={"pct": "8.5"})
            assert done.status_code == 200, done.text
            assert Decimal(done.json()["pct"]) == Decimal("8.5")
            platform = await client.get("/clubs/accounting")
            assert platform.status_code == 200, platform.text
    finally:
        app.dependency_overrides.clear()
