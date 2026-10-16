import asyncio
import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.db import Base

# Every domain's models, so Base.metadata is fully populated before create_all.
from app.domains.audit import models as _audit_models  # noqa: F401
from app.domains.auth import models as _auth_models  # noqa: F401
from app.domains.carts import models as _carts_models  # noqa: F401
from app.domains.catalog import models as _catalog_models  # noqa: F401
from app.domains.club import models as _club_models  # noqa: F401
from app.domains.club import contact_models as _club_contact_models  # noqa: F401
from app.domains.club import site_models as _club_site_models  # noqa: F401
from app.domains.club import operations_models as _club_operations_models  # noqa: F401
from app.domains.club import records_models as _club_records_models  # noqa: F401
from app.legacy import models as _legacy_models  # noqa: F401
from app.domains.commissions import models as _commissions_models  # noqa: F401
from app.domains.contracts import models as _contracts_models  # noqa: F401
from app.domains.customers import models as _customers_models  # noqa: F401
from app.domains.documentation import models as _documentation_models  # noqa: F401
from app.domains.documents import models as _documents_models  # noqa: F401
from app.domains.email_texts import models as _email_texts_models  # noqa: F401
from app.domains.friend_referrals import models as _friend_referrals_models  # noqa: F401
from app.domains.jav_market import models as _jav_market_models  # noqa: F401
from app.domains.javbot import models as _javbot_models  # noqa: F401
from app.domains.marketplaces import models as _marketplaces_models  # noqa: F401
from app.domains.network import models as _network_models  # noqa: F401
from app.domains.notifications import models as _notifications_models  # noqa: F401
from app.domains.orders import models as _orders_models  # noqa: F401
from app.domains.organizations import models as _organizations_models  # noqa: F401
from app.domains.organizations.models import Organization
from app.domains.outbox import models as _outbox_models  # noqa: F401
from app.domains.product_requests import models as _product_requests_models  # noqa: F401
from app.domains.rbac import models as _rbac_models  # noqa: F401
from app.domains.referral import models as _referral_models  # noqa: F401

# Read by every product list (category_ids), so the tables have to exist even
# when a single unrelated test file is run on its own.
from app.domains.shop_categories import models as _shop_categories_models  # noqa: F401
from app.domains.support import models as _support_models  # noqa: F401
from app.domains.users import models as _users_models  # noqa: F401
from app.domains.wallets import models as _wallets_models  # noqa: F401

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://jav:jav_dev_pw@localhost:5432/jav_test"
)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _create_schema():
    engine = create_async_engine(TEST_DATABASE_URL)
    from sqlalchemy import text

    from app.game.models import GameBase

    async with engine.begin() as conn:
        # Il gioco ha il suo schema e la sua MetaData (app/game): si rifà a parte.
        await conn.execute(text("DROP SCHEMA IF EXISTS game CASCADE"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("CREATE SCHEMA game"))
        await conn.run_sync(GameBase.metadata.create_all)
    await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _ensure_storage_buckets():
    """Normally done by main.py's FastAPI startup event, which never fires in
    a pytest run (no ASGI lifespan here) -- tests that upload real files
    (test_documents.py, and any future photo-upload test) need the buckets to
    already exist against the real MinIO this stack runs, same as the live app."""
    from app.core.storage import ensure_documents_bucket, ensure_media_bucket

    ensure_media_bucket()
    ensure_documents_bucket()


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    """One test = one connection-level transaction, with the ORM session bound to
    it via a savepoint (join_transaction_mode='create_savepoint'). Application code
    is free to call session.commit() (it does, throughout the service layer) --
    that only releases the savepoint. The OUTER transaction is rolled back at
    teardown, so no test's data leaks into the next one despite every service
    function committing internally."""
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.connect() as connection:
        await connection.begin()
        session = AsyncSession(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await connection.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def organization_id(db: AsyncSession) -> uuid.UUID:
    org = Organization(name=f"Test Org {uuid.uuid4()}", status="ACTIVE")
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return org.id


@pytest_asyncio.fixture
async def scope(db: AsyncSession, organization_id: uuid.UUID):
    """Un club nell'organizzazione di test: il perimetro di ogni funzione
    del dominio club (club/scope.py)."""
    from app.domains.club.models import Club
    from app.domains.club.scope import ClubScope

    club = Club(organization_id=organization_id, name="Club di prova", slug=f"club-{uuid.uuid4().hex[:8]}", settings={})
    db.add(club)
    await db.commit()
    return ClubScope(organization_id=organization_id, club_id=club.id)
