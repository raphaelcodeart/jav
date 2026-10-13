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
from app.domains.aliexpress_dropshipping import models as _aliexpress_models  # noqa: F401
from app.domains.audit import models as _audit_models  # noqa: F401
from app.domains.auth import models as _auth_models  # noqa: F401
from app.domains.catalog import models as _catalog_models  # noqa: F401
from app.domains.cj_dropshipping import models as _cj_models  # noqa: F401
from app.domains.commissions import models as _commissions_models  # noqa: F401
from app.domains.contracts import models as _contracts_models  # noqa: F401
from app.domains.customers import models as _customers_models  # noqa: F401
from app.domains.documentation import models as _documentation_models  # noqa: F401
from app.domains.documents import models as _documents_models  # noqa: F401
from app.domains.friend_referrals import models as _friend_referrals_models  # noqa: F401
from app.domains.imported_products import models as _imported_products_models  # noqa: F401
from app.domains.invoice_redemptions import models as _invoice_redemptions_models  # noqa: F401
from app.domains.network import models as _network_models  # noqa: F401
from app.domains.notifications import models as _notifications_models  # noqa: F401
from app.domains.orders import models as _orders_models  # noqa: F401
from app.domains.organizations import models as _organizations_models  # noqa: F401
from app.domains.outbox import models as _outbox_models  # noqa: F401
from app.domains.partners import models as _partners_models  # noqa: F401
from app.domains.payments import models as _payments_models  # noqa: F401
from app.domains.rbac import models as _rbac_models  # noqa: F401
from app.domains.referral import models as _referral_models  # noqa: F401
from app.domains.shopify_dropshipping import models as _shopify_models  # noqa: F401
from app.domains.support import models as _support_models  # noqa: F401
from app.domains.users import models as _users_models  # noqa: F401
from app.domains.vaitto_market import models as _vaitto_market_models  # noqa: F401
from app.domains.symphonya_market import models as _symphonya_market_models  # noqa: F401
from app.domains.soleil_market import models as _soleil_market_models  # noqa: F401
from app.domains.wallets import models as _wallets_models  # noqa: F401

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
        "cj-sync-orders": {
            # Shop Jav Partner: status and tracking of the orders on CJ.
            "task": "app.celery_app.cj_sync_orders_task",
            "schedule": crontab(minute="*/30"),
        },
        "cj-retry-orders": {
            # Shop Jav Partner: orders not sent, temporary failures, orders
            # waiting for CJ balance (paid as soon as the balance covers them).
            "task": "app.celery_app.cj_retry_orders_task",
            "schedule": crontab(minute="*/10"),
        },
        "cj-sync-products": {
            # Cost, stock and availability of the imported CJ products. Every
            # three hours since Session 88 (was nightly), like AliExpress; the
            # live checks on the product card and at checkout cover the rest.
            "task": "app.celery_app.cj_sync_products_task",
            "schedule": crontab(hour="*/3", minute=22),
        },
        "shopify-sync-orders": {
            # Marketplace 3: fulfilment and tracking of the orders in the Shopify store.
            "task": "app.celery_app.shopify_sync_orders_task",
            "schedule": crontab(minute="*/30"),
        },
        "shopify-retry-orders": {
            # Marketplace 3: paid orders not sent yet, temporary failures.
            "task": "app.celery_app.shopify_retry_orders_task",
            "schedule": crontab(minute="*/10"),
        },
        "shopify-sync-products": {
            # Cost, price and stock of the imported Shopify products.
            "task": "app.celery_app.shopify_sync_products_task",
            "schedule": crontab(hour=3, minute=45),
        },
        "aliexpress-sync-orders": {
            # Marketplace 3: shipping and tracking of the orders on AliExpress.
            "task": "app.celery_app.aliexpress_sync_orders_task",
            "schedule": crontab(minute="*/30"),
        },
        "aliexpress-retry-orders": {
            # Marketplace 3: paid orders not sent yet, temporary failures.
            # Never the ones whose answer was lost -- see the domain's
            # service.py: a human decides those.
            "task": "app.celery_app.aliexpress_retry_orders_task",
            "schedule": crontab(minute="*/10"),
        },
        "vaitto-import-feed": {
            # Session 88: il catalogo del Marketplace VAITTO dal feed
            # «universal.csv» di Vaitto -- costi, scorte, disponibilità.
            "task": "app.celery_app.vaitto_import_feed_all_task",
            "schedule": crontab(hour="*/3", minute=37),
        },
        "soleil-import-api": {
            # 13/10/2026: il catalogo di «Market 7» dall'API affiliati di
            # SoleilDrop (solo dove c'è la chiave e l'import automatico).
            "task": "app.celery_app.soleil_import_api_all_task",
            "schedule": crontab(hour="*/3", minute=17),
        },
        "soleil-sync-orders": {
            # Stato e tracking degli ordini su SoleilDrop: la riserva dei webhook.
            "task": "app.celery_app.soleil_sync_orders_task",
            "schedule": crontab(minute="*/30"),
        },
        "soleil-retry-orders": {
            # Ordini pagati non ancora partiti (errori temporanei; quelli mai
            # inviati solo con l'invio automatico acceso).
            "task": "app.celery_app.soleil_retry_orders_task",
            "schedule": crontab(minute="*/10"),
        },
        "symphonya-import-feed": {
            # Session 89: il catalogo del Marketplace SYMPHONYA dall'API di
            # Symphonya -- costi, listino, scorte.
            "task": "app.celery_app.symphonya_import_feed_all_task",
            "schedule": crontab(hour="*/3", minute=52),
        },
        "aliexpress-sync-products": {
            # Cost, price and stock of the imported AliExpress products.
            # Every three hours since Session 87 (was nightly): the full run
            # takes ~5 minutes for 300 products, and the live checks on the
            # product card and at checkout cover what happens in between.
            "task": "app.celery_app.aliexpress_sync_products_task",
            "schedule": crontab(hour="*/3", minute=7),
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


def _cj_run(job, name: str | None = None):
    """Runs a CJ job for every organization that has a CJ key. A job that
    raises is reported to staff once a day (Session 88, as for AliExpress)."""
    import asyncio

    from sqlalchemy import select

    from app.core.db import AsyncSessionLocal
    from app.domains.cj_dropshipping import client as cj_client
    from app.domains.cj_dropshipping.models import CjSettings

    async def _run() -> int:
        cj_client.reset_redis()
        total = 0
        async with AsyncSessionLocal() as db:
            org_ids = list(
                (await db.execute(select(CjSettings.organization_id).where(CjSettings.api_key.is_not(None)))).scalars()
            )
            for org_id in org_ids:
                try:
                    total += await job(db, org_id)
                except Exception as exc:
                    logging.getLogger(__name__).exception("CJ job failed for organization %s", org_id)
                    await db.rollback()
                    if name:
                        from app.domains.cj_dropshipping import service as cj_service

                        try:
                            await cj_service.alert_sync_failure(
                                db, organization_id=org_id, job=name, error=f"Errore tecnico: {exc}"[:500]
                            )
                        except Exception:
                            logging.getLogger(__name__).exception("Could not alert staff about CJ job")
                            await db.rollback()
        return total

    return asyncio.run(_run())


@celery_app.task(name="app.celery_app.cj_sync_orders_task")
def cj_sync_orders_task() -> int:
    from app.domains.cj_dropshipping import service as cj_service

    return _cj_run(lambda db, org_id: cj_service.sync_orders(db, organization_id=org_id), "orders")


@celery_app.task(name="app.celery_app.cj_retry_orders_task")
def cj_retry_orders_task() -> int:
    from app.domains.cj_dropshipping import service as cj_service

    return _cj_run(lambda db, org_id: cj_service.retry_due_orders(db, organization_id=org_id), "retry")


@celery_app.task(name="app.celery_app.cj_sync_products_task")
def cj_sync_products_task() -> int:
    from app.domains.cj_dropshipping import service as cj_service

    return _cj_run(lambda db, org_id: cj_service.sync_all_products(db, organization_id=org_id), "products")


@celery_app.task(name="app.celery_app.cj_forward_order_task")
def cj_forward_order_task(order_id: str) -> str:
    """Automatic "Invia a CJ" right after payment, when enabled."""
    import asyncio
    import uuid

    from app.core.db import AsyncSessionLocal
    from app.domains.cj_dropshipping import client as cj_client
    from app.domains.cj_dropshipping import service as cj_service
    from app.domains.cj_dropshipping.models import CjOrder

    async def _run() -> str:
        cj_client.reset_redis()
        async with AsyncSessionLocal() as db:
            order = await db.get(CjOrder, uuid.UUID(order_id))
            if order is None:
                return "missing"
            try:
                order = await cj_service.forward_order(
                    db, organization_id=order.organization_id, order_id=order.id, actor_user_id=None
                )
            except cj_service.CjError as exc:
                return f"skipped: {exc}"
            return order.fulfillment_status

    return asyncio.run(_run())


def _shopify_run(job):
    """Runs a Shopify job for every organization that has a store configured."""
    import asyncio

    from sqlalchemy import select

    from app.core.db import AsyncSessionLocal
    from app.domains.shopify_dropshipping.models import ShopifySettings

    async def _run() -> int:
        total = 0
        async with AsyncSessionLocal() as db:
            org_ids = list(
                (
                    await db.execute(
                        select(ShopifySettings.organization_id).where(
                            ShopifySettings.access_token.is_not(None), ShopifySettings.shop_domain.is_not(None)
                        )
                    )
                ).scalars()
            )
            for org_id in org_ids:
                try:
                    total += await job(db, org_id)
                except Exception:
                    logging.getLogger(__name__).exception("Shopify job failed for organization %s", org_id)
                    await db.rollback()
        return total

    return asyncio.run(_run())


@celery_app.task(name="app.celery_app.shopify_sync_orders_task")
def shopify_sync_orders_task() -> int:
    from app.domains.shopify_dropshipping import service as shopify_service

    return _shopify_run(lambda db, org_id: shopify_service.sync_orders(db, organization_id=org_id))


@celery_app.task(name="app.celery_app.shopify_retry_orders_task")
def shopify_retry_orders_task() -> int:
    from app.domains.shopify_dropshipping import service as shopify_service

    return _shopify_run(lambda db, org_id: shopify_service.retry_due_orders(db, organization_id=org_id))


@celery_app.task(name="app.celery_app.shopify_sync_products_task")
def shopify_sync_products_task() -> int:
    from app.domains.shopify_dropshipping import service as shopify_service

    return _shopify_run(lambda db, org_id: shopify_service.sync_all_products(db, organization_id=org_id))


@celery_app.task(name="app.celery_app.shopify_forward_order_task")
def shopify_forward_order_task(order_id: str) -> str:
    """Automatic "Invia a Shopify" right after payment, when enabled."""
    import asyncio
    import uuid

    from app.core.db import AsyncSessionLocal
    from app.domains.shopify_dropshipping import service as shopify_service
    from app.domains.shopify_dropshipping.models import ShopifyOrder

    async def _run() -> str:
        async with AsyncSessionLocal() as db:
            order = await db.get(ShopifyOrder, uuid.UUID(order_id))
            if order is None:
                return "missing"
            try:
                order = await shopify_service.forward_order(
                    db, organization_id=order.organization_id, order_id=order.id, actor_user_id=None
                )
            except shopify_service.ShopifyError as exc:
                return f"skipped: {exc}"
            return order.fulfillment_status

    return asyncio.run(_run())


def _aliexpress_run(job, name: str | None = None):
    """Runs an AliExpress job for every organization whose account is linked.

    A job that raises is reported to staff (once a day, see
    aliexpress_dropshipping.service.alert_sync_failure): in Session 87 the
    product sync failed silently for a week on stale worker code, and a
    customer found out before anyone else did."""
    import asyncio

    from sqlalchemy import select

    from app.core.db import AsyncSessionLocal
    from app.domains.aliexpress_dropshipping.models import AliexpressSettings

    async def _run() -> int:
        total = 0
        async with AsyncSessionLocal() as db:
            org_ids = list(
                (
                    await db.execute(
                        select(AliexpressSettings.organization_id).where(
                            AliexpressSettings.access_token.is_not(None),
                            AliexpressSettings.app_key.is_not(None),
                        )
                    )
                ).scalars()
            )
            for org_id in org_ids:
                try:
                    total += await job(db, org_id)
                except Exception as exc:
                    logging.getLogger(__name__).exception("AliExpress job failed for organization %s", org_id)
                    await db.rollback()
                    if name:
                        from app.domains.aliexpress_dropshipping import (
                            service as aliexpress_service,
                        )

                        try:
                            await aliexpress_service.alert_sync_failure(
                                db, organization_id=org_id, job=name, error=f"Errore tecnico: {exc}"[:500]
                            )
                        except Exception:
                            logging.getLogger(__name__).exception("Could not alert staff about AliExpress job")
                            await db.rollback()
        return total

    return asyncio.run(_run())


@celery_app.task(name="app.celery_app.aliexpress_sync_orders_task")
def aliexpress_sync_orders_task() -> int:
    from app.domains.aliexpress_dropshipping import service as aliexpress_service

    return _aliexpress_run(
        lambda db, org_id: aliexpress_service.sync_orders(db, organization_id=org_id), "orders"
    )


@celery_app.task(name="app.celery_app.aliexpress_retry_orders_task")
def aliexpress_retry_orders_task() -> int:
    from app.domains.aliexpress_dropshipping import service as aliexpress_service

    return _aliexpress_run(
        lambda db, org_id: aliexpress_service.retry_due_orders(db, organization_id=org_id), "retry"
    )


@celery_app.task(name="app.celery_app.aliexpress_sync_products_task")
def aliexpress_sync_products_task() -> int:
    from app.domains.aliexpress_dropshipping import service as aliexpress_service

    return _aliexpress_run(
        lambda db, org_id: aliexpress_service.sync_all_products(db, organization_id=org_id), "products"
    )


@celery_app.task(name="app.celery_app.aliexpress_forward_order_task")
def aliexpress_forward_order_task(order_id: str) -> str:
    """Automatic "Invia ad AliExpress" right after payment, when enabled."""
    import asyncio
    import uuid

    from app.core.db import AsyncSessionLocal
    from app.domains.aliexpress_dropshipping import service as aliexpress_service
    from app.domains.aliexpress_dropshipping.models import AliexpressOrder

    async def _run() -> str:
        async with AsyncSessionLocal() as db:
            order = await db.get(AliexpressOrder, uuid.UUID(order_id))
            if order is None:
                return "missing"
            try:
                order = await aliexpress_service.forward_order(
                    db, organization_id=order.organization_id, order_id=order.id, actor_user_id=None
                )
            except aliexpress_service.AliexpressError as exc:
                return f"skipped: {exc}"
            return order.fulfillment_status

    return asyncio.run(_run())


@celery_app.task(name="app.celery_app.vaitto_import_feed_task")
def vaitto_import_feed_task(organization_id: str, actor_user_id: str | None, stash_key: str | None) -> str:
    """Un import del Marketplace VAITTO: dal feed (stash_key None) o dal CSV
    caricato a mano e parcheggiato nel bucket privato, che si cancella dopo."""
    import asyncio
    import uuid

    from app.core.db import AsyncSessionLocal
    from app.core.storage import delete_document_object, download_document
    from app.domains.vaitto_market import feed

    async def _run() -> str:
        content = download_document(storage_key=stash_key) if stash_key else None
        try:
            async with AsyncSessionLocal() as db:
                summary = await feed.import_feed(
                    db, organization_id=uuid.UUID(organization_id),
                    actor_user_id=uuid.UUID(actor_user_id) if actor_user_id else None, content=content,
                )
                return summary["text"]
        except feed.VaittoFeedError as exc:
            return f"errore: {exc}"
        finally:
            if stash_key:
                delete_document_object(storage_key=stash_key)

    return asyncio.run(_run())


@celery_app.task(name="app.celery_app.vaitto_import_feed_all_task")
def vaitto_import_feed_all_task() -> int:
    """L'import periodico, per ogni organizzazione con un feed e l'import
    automatico acceso. Un feed che fallisce lascia l'errore sulle impostazioni
    (last_import_error), che il pannello mostra."""
    import asyncio

    from sqlalchemy import select

    from app.core.db import AsyncSessionLocal
    from app.domains.vaitto_market import feed
    from app.domains.vaitto_market.models import VaittoMarketSettings

    async def _run() -> int:
        done = 0
        async with AsyncSessionLocal() as db:
            org_ids = list((await db.execute(
                select(VaittoMarketSettings.organization_id).where(
                    VaittoMarketSettings.feed_url.is_not(None), VaittoMarketSettings.auto_import.is_(True),
                )
            )).scalars())
            for org_id in org_ids:
                try:
                    await feed.import_feed(db, organization_id=org_id)
                    done += 1
                except feed.VaittoFeedError:
                    logging.getLogger(__name__).warning("Vaitto feed import failed for %s", org_id)
                except Exception:
                    logging.getLogger(__name__).exception("Vaitto feed import crashed for %s", org_id)
                    await db.rollback()
        return done

    return asyncio.run(_run())


@celery_app.task(name="app.celery_app.symphonya_import_feed_task")
def symphonya_import_feed_task(organization_id: str, actor_user_id: str | None, stash_key: str | None) -> str:
    """Un import del Marketplace SYMPHONYA: dal feed (stash_key None) o dal CSV
    caricato a mano e parcheggiato nel bucket privato, che si cancella dopo."""
    import asyncio
    import uuid

    from app.core.db import AsyncSessionLocal
    from app.core.storage import delete_document_object, download_document
    from app.domains.symphonya_market import feed

    async def _run() -> str:
        content = download_document(storage_key=stash_key) if stash_key else None
        try:
            async with AsyncSessionLocal() as db:
                summary = await feed.import_feed(
                    db, organization_id=uuid.UUID(organization_id),
                    actor_user_id=uuid.UUID(actor_user_id) if actor_user_id else None, content=content,
                )
                return summary["text"]
        except feed.SymphonyaFeedError as exc:
            return f"errore: {exc}"
        finally:
            if stash_key:
                delete_document_object(storage_key=stash_key)

    return asyncio.run(_run())


@celery_app.task(name="app.celery_app.soleil_import_feed_task")
def soleil_import_feed_task(organization_id: str, actor_user_id: str | None, stash_key: str | None) -> str:
    """Un import del Marketplace SOLEIL: dall'Excel di SoleilDrop caricato a
    mano e parcheggiato nel bucket privato, che si cancella dopo (Session 90),
    oppure -- stash_key None -- dall'API affiliati (13/10/2026)."""
    import asyncio
    import uuid

    from app.core.db import AsyncSessionLocal
    from app.core.storage import delete_document_object, download_document
    from app.domains.soleil_market import api_sync, feed

    async def _run() -> str:
        actor = uuid.UUID(actor_user_id) if actor_user_id else None
        try:
            async with AsyncSessionLocal() as db:
                if stash_key is None:
                    summary = await api_sync.import_catalog(
                        db, organization_id=uuid.UUID(organization_id), actor_user_id=actor,
                    )
                else:
                    summary = await feed.import_feed(
                        db, organization_id=uuid.UUID(organization_id), actor_user_id=actor,
                        content=download_document(storage_key=stash_key),
                    )
                return summary["text"]
        except feed.SoleilFeedError as exc:
            return f"errore: {exc}"
        finally:
            if stash_key:
                delete_document_object(storage_key=stash_key)

    return asyncio.run(_run())


def _soleil_run(job, *, needs_auto_import: bool = False) -> int:
    """Un lavoro SoleilDrop per ogni organizzazione con la chiave API. Un
    errore di un'organizzazione non ferma le altre e resta nei log; l'esito
    dell'import resta anche sulle impostazioni (last_import_error)."""
    import asyncio

    from sqlalchemy import select

    from app.core.db import AsyncSessionLocal
    from app.domains.soleil_market.models import SoleilMarketSettings

    async def _run() -> int:
        done = 0
        async with AsyncSessionLocal() as db:
            query = select(SoleilMarketSettings.organization_id).where(SoleilMarketSettings.api_key.is_not(None))
            if needs_auto_import:
                query = query.where(SoleilMarketSettings.auto_import.is_(True))
            for org_id in list((await db.execute(query)).scalars()):
                try:
                    await job(db, org_id)
                    done += 1
                except Exception:
                    logging.getLogger(__name__).exception("SoleilDrop job %s failed for %s", job.__name__, org_id)
                    await db.rollback()
        return done

    return asyncio.run(_run())


@celery_app.task(name="app.celery_app.soleil_import_api_all_task")
def soleil_import_api_all_task() -> int:
    from app.domains.soleil_market import api_sync

    async def job(db, org_id):
        await api_sync.import_catalog(db, organization_id=org_id)

    return _soleil_run(job, needs_auto_import=True)


@celery_app.task(name="app.celery_app.soleil_sync_orders_task")
def soleil_sync_orders_task() -> int:
    from app.domains.soleil_market import api_sync

    async def job(db, org_id):
        await api_sync.sync_orders(db, organization_id=org_id)

    return _soleil_run(job)


@celery_app.task(name="app.celery_app.soleil_retry_orders_task")
def soleil_retry_orders_task() -> int:
    from app.domains.soleil_market import api_sync

    async def job(db, org_id):
        await api_sync.retry_orders(db, organization_id=org_id)

    return _soleil_run(job)


@celery_app.task(name="app.celery_app.symphonya_import_feed_all_task")
def symphonya_import_feed_all_task() -> int:
    """L'import periodico, per ogni organizzazione con un feed e l'import
    automatico acceso. Un feed che fallisce lascia l'errore sulle impostazioni
    (last_import_error), che il pannello mostra."""
    import asyncio

    from sqlalchemy import select

    from app.core.db import AsyncSessionLocal
    from app.domains.symphonya_market import feed
    from app.domains.symphonya_market.models import SymphonyaMarketSettings

    async def _run() -> int:
        done = 0
        async with AsyncSessionLocal() as db:
            org_ids = list((await db.execute(
                select(SymphonyaMarketSettings.organization_id).where(
                    SymphonyaMarketSettings.api_key.is_not(None), SymphonyaMarketSettings.auto_import.is_(True),
                )
            )).scalars())
            for org_id in org_ids:
                try:
                    await feed.import_feed(db, organization_id=org_id)
                    done += 1
                except feed.SymphonyaFeedError:
                    logging.getLogger(__name__).warning("Symphonya feed import failed for %s", org_id)
                except Exception:
                    logging.getLogger(__name__).exception("Symphonya feed import crashed for %s", org_id)
                    await db.rollback()
        return done

    return asyncio.run(_run())
