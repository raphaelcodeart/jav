"""Celery application. Runs as `apps/worker` in the docker-compose topology, but is
defined inside the api package on purpose: the worker must reuse the exact same
domain code (models, services, the commission engine) as the API, never a copy of
it. `docker-compose.dev.yml`'s celery-worker/celery-beat services build from this
same image (apps/api/Dockerfile) and simply run a different command."""

import logging

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

# Every domain's models, so SQLAlchemy's declarative metadata is fully
# populated before any task ever flushes a session -- without this, a task
# whose own import chain never happens to touch e.g. organizations.models
# (nothing here did, before this was added) hits NoReferencedTableError the
# first time it tries to flush a row with an FK to a table SQLAlchemy has
# literally never heard of yet. Same reasoning, and the same list, as
# main.py's own noqa import block for the API process -- discovered when
# process_outbox_task (which runs every minute) turned out to have always
# crashed on its first flush for exactly this reason.
from app.domains.audit import models as _audit_models  # noqa: F401
from app.domains.auth import models as _auth_models  # noqa: F401
from app.domains.catalog import models as _catalog_models  # noqa: F401
from app.domains.club import contact_models as _club_contact_models  # noqa: F401
from app.domains.club import models as _club_models  # noqa: F401
from app.domains.club import operations_models as _club_operations_models  # noqa: F401
from app.domains.club import records_models as _club_records_models  # noqa: F401
from app.domains.club import site_models as _club_site_models  # noqa: F401
from app.domains.commissions import models as _commissions_models  # noqa: F401
from app.domains.contracts import models as _contracts_models  # noqa: F401
from app.domains.customers import models as _customers_models  # noqa: F401
from app.domains.documentation import models as _documentation_models  # noqa: F401
from app.domains.documents import models as _documents_models  # noqa: F401
from app.domains.email_texts import models as _email_texts_models  # noqa: F401
from app.domains.friend_referrals import models as _friend_referrals_models  # noqa: F401
from app.domains.network import models as _network_models  # noqa: F401
from app.domains.notifications import models as _notifications_models  # noqa: F401
from app.domains.orders import models as _orders_models  # noqa: F401
from app.domains.organizations import models as _organizations_models  # noqa: F401
from app.domains.outbox import models as _outbox_models  # noqa: F401
from app.domains.rbac import models as _rbac_models  # noqa: F401
from app.domains.referral import models as _referral_models  # noqa: F401
from app.domains.support import models as _support_models  # noqa: F401
from app.domains.users import models as _users_models  # noqa: F401
from app.domains.wallets import models as _wallets_models  # noqa: F401
from app.legacy import models as _legacy_models  # noqa: F401

logger = logging.getLogger(__name__)
settings = get_settings()

celery_app = Celery("jav", broker=settings.redis_url, backend=settings.redis_url)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "process-domain-outbox": {
            "task": "app.celery_app.process_outbox_task",
            "schedule": crontab(minute="*/1"),
        },
        "monthly-rank-evaluation": {
            "task": "app.celery_app.run_monthly_rank_evaluation_task",
            # Day 1 of each month, not the last instant of the last day -- more
            # robust than trying to catch an exact month-end moment, and still
            # evaluates the month that just closed (see previous_calendar_month()).
            "schedule": crontab(day_of_month=1, hour=2, minute=0),
        },
        # Il club si gestisce da solo (docs/club-portal.md, "Automatismi").
        # Ogni job è idempotente: girare due volte non crea doppioni.
        "club-monthly-fees": {
            "task": "app.celery_app.club_monthly_fees_task",
            "schedule": crontab(day_of_month=1, hour=3, minute=0),
        },
        "club-new-season": {
            "task": "app.celery_app.club_new_season_task",
            "schedule": crontab(month_of_year=9, day_of_month=1, hour=3, minute=30),
        },
        # L'iscrizione segue l'anno solare: il 1° gennaio, dopo le mensilità.
        "club-new-year": {
            "task": "app.celery_app.club_new_year_task",
            "schedule": crontab(month_of_year=1, day_of_month=1, hour=3, minute=30),
        },
        "club-reminders": {
            "task": "app.celery_app.club_reminders_task",
            "schedule": crontab(hour=8, minute=0),
        },
        # Avvisi della mensilità e multa (club/payment_reminders.py): ogni ora,
        # il job guarda da sé l'ora del club e manda ogni avviso una volta.
        "club-payment-reminders": {
            "task": "app.celery_app.club_payment_reminders_task",
            "schedule": crontab(minute=5),
        },
        "club-close-competitions": {
            "task": "app.celery_app.club_close_competitions_task",
            "schedule": crontab(hour=1, minute=0),
        },
        # I costi fissi del club diventano spese del mese. Ogni giorno e non
        # solo il 1°: un giorno saltato si recupera il giorno dopo, e il
        # vincolo UNIQUE (costo fisso, mese) impedisce i doppioni.
        "club-recurring-expenses": {
            "task": "app.celery_app.club_recurring_expenses_task",
            "schedule": crontab(hour=3, minute=10),
        },
    },
)


@celery_app.task(name="app.celery_app.process_outbox_task")
def process_outbox_task() -> int:
    """Polls domain_outbox for unprocessed events (ContractActivated, etc.) and
    dispatches them -- primarily this is what triggers commission calculation
    after a contract activation commits (see ADR 0005, the transactional outbox)."""
    import asyncio

    from app.core.db import AsyncSessionLocal
    from app.domains.commissions.tasks.dispatch import process_pending_outbox_events

    async def _run() -> int:
        async with AsyncSessionLocal() as db:
            return await process_pending_outbox_events(db)

    return asyncio.run(_run())


@celery_app.task(name="app.celery_app.run_monthly_rank_evaluation_task")
def run_monthly_rank_evaluation_task() -> int:
    """Evaluates the calendar month that just closed for every organization,
    promoting/demoting each ACTIVE agent's rank to match their production
    (see commissions/services/rank_evaluation.py). Same admin-triggerable logic
    also runs on demand via POST /commissions/rank-evaluation/run."""
    import asyncio

    from sqlalchemy import select

    from app.core.db import AsyncSessionLocal, utcnow
    from app.domains.commissions.services.rank_evaluation import (
        previous_calendar_month,
        run_monthly_rank_evaluation,
    )
    from app.domains.organizations.models import Organization

    async def _run() -> int:
        window_start, window_end = previous_calendar_month(utcnow())
        total_changes = 0
        async with AsyncSessionLocal() as db:
            org_ids = (await db.execute(select(Organization.id))).scalars().all()
            for organization_id in org_ids:
                changes = await run_monthly_rank_evaluation(
                    db, organization_id=organization_id, window_start=window_start, window_end=window_end,
                )
                total_changes += len(changes)
        return total_changes

    return asyncio.run(_run())


def _club_run(job_name: str) -> int:
    """Lancia un job del club (club/tasks.py) per ogni club attivo. Un club
    che fallisce non ferma gli altri: l'errore va nel log e il giro
    successivo riprova, perché ogni job è idempotente. Un club sospeso non
    riceve quote né promemoria: le sue famiglie non possono nemmeno entrare."""
    import asyncio

    from sqlalchemy import select

    from app.core.db import AsyncSessionLocal
    from app.domains.club import tasks as club_tasks
    from app.domains.club.models import Club
    from app.domains.club.scope import ClubScope

    job = getattr(club_tasks, job_name)

    async def _run() -> int:
        total = 0
        async with AsyncSessionLocal() as db:
            scopes = [
                ClubScope(organization_id=org_id, club_id=club_id)
                for club_id, org_id in (
                    await db.execute(select(Club.id, Club.organization_id).where(Club.status == "ACTIVE"))
                ).all()
            ]
        for scope in scopes:
            async with AsyncSessionLocal() as db:
                try:
                    total += await job(db, scope=scope)
                except Exception:
                    logger.exception("Club job %s failed for club %s", job_name, scope.club_id)
        return total

    return asyncio.run(_run())


@celery_app.task(name="app.celery_app.club_monthly_fees_task")
def club_monthly_fees_task() -> int:
    return _club_run("run_monthly_fees")


@celery_app.task(name="app.celery_app.club_new_year_task")
def club_new_year_task() -> int:
    return _club_run("run_new_year")


@celery_app.task(name="app.celery_app.club_new_season_task")
def club_new_season_task() -> int:
    return _club_run("run_new_season")


@celery_app.task(name="app.celery_app.club_reminders_task")
def club_reminders_task() -> int:
    return _club_run("send_reminders")


@celery_app.task(name="app.celery_app.club_payment_reminders_task")
def club_payment_reminders_task() -> int:
    return _club_run("run_payment_reminders")


@celery_app.task(name="app.celery_app.club_close_competitions_task")
def club_close_competitions_task() -> int:
    return _club_run("close_expired_competitions")


@celery_app.task(name="app.celery_app.club_recurring_expenses_task")
def club_recurring_expenses_task() -> int:
    return _club_run("run_recurring_expenses")
