"""Il personale del club (club/staff_work.py).

Le promesse: un compito lo scrive chi l'ha fatto, un lavoretto la segreteria
anche per chi non ha un account; pagare crea una spesa COLLABORATORS una volta
sola, e una riga pagata non si cancella; il mese somma ore × tariffa e
lavoretti; i messaggi vanno al canale giusto e la risposta torna alla persona.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.domains.club import accounting, staff_work
from app.domains.club import service as club_service
from app.domains.club.models import ClubExpense, ClubWorkSession
from app.domains.notifications.models import Notification
from tests.test_club_fees import _user


async def test_tasks_jobs_payment_and_the_month(db, scope):
    admin = await _user(db, scope, "admin")
    coach = await _user(db, scope, "treinador")
    today = date.today()
    month = today.strftime("%Y-%m")
    first = today.replace(day=1)
    await accounting.set_staff_rate(db, scope=scope, user_id=coach.id, hourly_rate_cents=1200,
                                    valid_from=first - timedelta(days=40), actor_user_id=admin.id)
    start = datetime(first.year, first.month, first.day, 18, tzinfo=UTC)
    db.add(ClubWorkSession(**scope.columns(), user_id=coach.id, started_at=start, ended_at=start + timedelta(hours=2)))
    await db.commit()

    with pytest.raises(club_service.ClubValidationError):
        await staff_work.add_task(db, scope=scope, actor_user_id=coach.id, kind="TASK", title=" ", done_on=today, user_id=coach.id)
    task = await staff_work.add_task(db, scope=scope, actor_user_id=coach.id, kind="TASK", title="Montato il tatami",
                                     done_on=today, minutes=45, user_id=coach.id)
    assert task.person_name and task.cost_cents == 0
    job = await staff_work.add_task(db, scope=scope, actor_user_id=admin.id, kind="ODD_JOB", title="Riparata la porta",
                                    done_on=today, cost_cents=4000, person_name="Sr. Manuel")
    with pytest.raises(club_service.ClubValidationError):  # senza costo non si paga
        await staff_work.pay_task(db, scope=scope, task_id=task.id, actor_user_id=admin.id)

    summary = await staff_work.month_summary(db, scope=scope, month=month, today=today)
    assert summary["totals"]["hours_cost_cents"] == 2400
    assert summary["totals"]["jobs_cost_cents"] == 4000 and summary["totals"]["unpaid_cents"] == 4000
    assert summary["totals"]["total_cents"] == 6400
    assert {p["name"] for p in summary["people"]} >= {"Sr. Manuel"}

    paid = await staff_work.pay_task(db, scope=scope, task_id=job.id, actor_user_id=admin.id, payment_method="CASH")
    assert paid.paid_on and paid.expense_id
    expense = await db.get(ClubExpense, paid.expense_id)
    assert expense.category == "COLLABORATORS" and expense.amount_cents == 4000
    with pytest.raises(club_service.ClubValidationError):
        await staff_work.pay_task(db, scope=scope, task_id=job.id, actor_user_id=admin.id)
    with pytest.raises(club_service.ClubValidationError):
        await staff_work.delete_task(db, scope=scope, task_id=job.id, actor_user_id=admin.id)
    assert (await staff_work.month_summary(db, scope=scope, month=month, today=today))["totals"]["unpaid_cents"] == 0

    # L'area della persona: solo le sue righe; e cancella solo le sue.
    mine = await staff_work.my_month(db, scope=scope, user_id=coach.id, month=month, today=today)
    assert [t["title"] for t in mine["tasks"]] == ["Montato il tatami"] and mine["hours_cost_cents"] == 2400
    other = await _user(db, scope, "adjunto")
    with pytest.raises(club_service.ClubNotFoundError):
        await staff_work.delete_task(db, scope=scope, task_id=task.id, actor_user_id=other.id, own_user_id=other.id)
    await staff_work.delete_task(db, scope=scope, task_id=task.id, actor_user_id=coach.id, own_user_id=coach.id)


async def test_messages_go_to_the_right_channel_and_back(db, scope):
    admin = await _user(db, scope, "admin")
    coach = await _user(db, scope, "treinador")
    with pytest.raises(club_service.ClubValidationError):
        await staff_work.staff_write(db, scope=scope, staff_user_id=coach.id, channel="FAX", body="ciao")
    await staff_work.staff_write(db, scope=scope, staff_user_id=coach.id, channel="CLUB", body="Domani arrivo tardi")
    await staff_work.staff_write(db, scope=scope, staff_user_id=coach.id, channel="JAV", body="Quando è la formazione?")

    club_box = await staff_work.inbox(db, channel="CLUB", club_id=scope.club_id)
    assert len(club_box) == 1 and club_box[0]["unread"] == 1 and club_box[0]["last_body"] == "Domani arrivo tardi"
    jav_box = await staff_work.inbox(db, channel="JAV", organization_id=scope.organization_id)
    assert len(jav_box) == 1 and jav_box[0]["last_body"].startswith("Quando")

    await staff_work.thread(db, club_id=scope.club_id, staff_user_id=coach.id, channel="CLUB", mark_read_from_staff=True)
    assert (await staff_work.inbox(db, channel="CLUB", club_id=scope.club_id))[0]["unread"] == 0
    await staff_work.reply(db, scope=scope, staff_user_id=coach.id, channel="CLUB", body="Va bene, grazie", author_user_id=admin.id)
    rows = await staff_work.thread(db, club_id=scope.club_id, staff_user_id=coach.id, channel="CLUB", mark_read_from_staff=False)
    assert [m.from_staff for m in rows] == [True, False] and rows[1].read_at is not None
    note = (await db.execute(select(Notification).where(Notification.recipient_user_id == coach.id,
                                                        Notification.type == "CLUB_STAFF_MESSAGE"))).scalars().all()
    assert len(note) == 1
