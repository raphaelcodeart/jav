import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Import every domain's models module so SQLAlchemy's metadata (and therefore
# Alembic autogenerate) sees all tables, even though nothing else here references
# these imports directly.
from app.domains.accounting.router import router as accounting_router
from app.domains.audit import models as _audit_models  # noqa: F401
from app.domains.auth import models as _auth_models  # noqa: F401
from app.domains.auth.router import router as auth_router
from app.domains.carts import models as _carts_models  # noqa: F401
from app.domains.carts.router import router as carts_router
from app.domains.catalog import models as _catalog_models  # noqa: F401
from app.domains.catalog.router import router as catalog_router
from app.domains.club import contact_models as _club_contact_models  # noqa: F401
from app.domains.club import models as _club_models  # noqa: F401
from app.domains.club import operations_models as _club_operations_models  # noqa: F401
from app.domains.club import records_models as _club_records_models  # noqa: F401
from app.domains.club import site_models as _club_site_models  # noqa: F401
from app.domains.club.accounting_router import (
    admin_accounting_router,
    family_accounting_router,
    platform_accounting_router,
)
from app.domains.club.contact_router import (
    contact_club_router,
    contact_platform_router,
    contact_public_router,
)
from app.domains.club.athlete_router import router as club_athlete_router
from app.domains.club.router import admin_router as club_admin_router
from app.domains.club.router import clubs_router
from app.domains.club.router import router as club_router
from app.domains.club.router import staff_router as club_staff_router
from app.domains.club.site_router import public_site_router, site_admin_router, site_family_router
from app.domains.commissions import models as _commissions_models  # noqa: F401
from app.domains.commissions.router import router as commissions_router
from app.domains.contracts import models as _contracts_models  # noqa: F401
from app.domains.contracts.requests_router import router as contract_requests_router
from app.domains.contracts.router import router as contracts_router
from app.domains.customers import models as _customers_models  # noqa: F401
from app.domains.customers.router import router as customers_router
from app.domains.documentation import models as _documentation_models  # noqa: F401
from app.domains.documentation.router import router as documentation_router
from app.domains.documents import models as _documents_models  # noqa: F401
from app.domains.documents.router import router as documents_router
from app.domains.friend_referrals import models as _friend_referrals_models  # noqa: F401
from app.domains.friend_referrals.router import router as friend_referrals_router
from app.domains.jav_market import models as _jav_market_models  # noqa: F401
from app.domains.jav_market.router import router as jav_market_router
from app.domains.javbot import models as _javbot_models  # noqa: F401
from app.domains.club.club_documents_router import router as club_documents_router
from app.domains.javbot.knowledge_router import club_knowledge_router as javbot_club_knowledge_router
from app.domains.javbot.knowledge_router import platform_knowledge_router as javbot_platform_knowledge_router
from app.domains.javbot.router import public_router as javbot_public_router
from app.domains.javbot.router import router as javbot_router
from app.domains.marketplaces import models as _marketplaces_models  # noqa: F401
from app.domains.marketplaces.router import router as marketplaces_router
from app.domains.network import models as _network_models  # noqa: F401
from app.domains.network.router import router as network_router
from app.domains.notifications import models as _notifications_models  # noqa: F401
from app.domains.notifications.router import router as notifications_router
from app.domains.orders import models as _orders_models  # noqa: F401
from app.domains.orders.router import router as orders_router
from app.domains.organizations import models as _organizations_models  # noqa: F401
from app.domains.organizations.router import router as organizations_router
from app.domains.outbox import models as _outbox_models  # noqa: F401
from app.domains.product_requests import models as _product_requests_models  # noqa: F401
from app.domains.product_requests.router import router as product_requests_router
from app.domains.rbac import models as _rbac_models  # noqa: F401
from app.domains.referral import models as _referral_models  # noqa: F401
from app.domains.referral.router import authenticated_router as referral_authenticated_router
from app.domains.referral.router import router as referral_router
from app.domains.reports.router import router as reports_router
from app.domains.shop_categories import models as _shop_categories_models  # noqa: F401
from app.domains.shop_categories.router import router as shop_categories_router
from app.domains.support import models as _support_models  # noqa: F401
from app.domains.support.router import router as support_router
from app.domains.users import models as _users_models  # noqa: F401
from app.domains.users.router import router as users_router
from app.domains.wallets import models as _wallets_models  # noqa: F401
from app.legacy import models as _legacy_models  # noqa: F401
from app.domains.wallets.router import router as wallets_router

settings = get_settings()

app = FastAPI(
    title="Jav Platform API",
    version="0.1.0",
    description="See /opt/webapps/jav/docs for architecture and business rules.",
    docs_url="/docs" if settings.enable_api_docs else None,
    redoc_url="/redoc" if settings.enable_api_docs else None,
    openapi_url="/openapi.json" if settings.enable_api_docs else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api")
app.include_router(accounting_router, prefix="/api")
app.include_router(network_router, prefix="/api")
app.include_router(referral_router, prefix="/api")
app.include_router(referral_authenticated_router, prefix="/api")
app.include_router(contracts_router, prefix="/api")
app.include_router(contract_requests_router, prefix="/api")
app.include_router(commissions_router, prefix="/api")
app.include_router(customers_router, prefix="/api")
app.include_router(catalog_router, prefix="/api")
app.include_router(carts_router, prefix="/api")
app.include_router(club_router, prefix="/api")
app.include_router(club_admin_router, prefix="/api")
app.include_router(club_athlete_router, prefix="/api")
app.include_router(club_staff_router, prefix="/api")
app.include_router(clubs_router, prefix="/api")
app.include_router(admin_accounting_router, prefix="/api")
app.include_router(platform_accounting_router, prefix="/api")
app.include_router(family_accounting_router, prefix="/api")
app.include_router(public_site_router, prefix="/api")
app.include_router(site_admin_router, prefix="/api")
app.include_router(site_family_router, prefix="/api")
app.include_router(contact_public_router, prefix="/api")
app.include_router(contact_club_router, prefix="/api")
app.include_router(contact_platform_router, prefix="/api")
app.include_router(reports_router, prefix="/api")
app.include_router(support_router, prefix="/api")
app.include_router(product_requests_router, prefix="/api")
app.include_router(documents_router, prefix="/api")
app.include_router(notifications_router, prefix="/api")
app.include_router(documentation_router, prefix="/api")
app.include_router(wallets_router, prefix="/api")
app.include_router(orders_router, prefix="/api")
app.include_router(jav_market_router, prefix="/api")
app.include_router(marketplaces_router, prefix="/api")
app.include_router(shop_categories_router, prefix="/api")
app.include_router(friend_referrals_router, prefix="/api")
app.include_router(organizations_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(javbot_router, prefix="/api")
app.include_router(javbot_public_router, prefix="/api")
app.include_router(javbot_club_knowledge_router, prefix="/api")
app.include_router(club_documents_router, prefix="/api")
app.include_router(javbot_platform_knowledge_router, prefix="/api")


@app.on_event("startup")
async def _ensure_media_bucket() -> None:
    from app.core.storage import ensure_documents_bucket, ensure_media_bucket

    try:
        ensure_media_bucket()
        ensure_documents_bucket()
    except Exception:
        # Photo/document upload is a nice-to-have, not core to the app -- a
        # MinIO hiccup at startup must never take down the whole API.
        logger.exception("Could not ensure media/documents buckets exist -- photo/document upload will fail until this is resolved")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readiness")
async def readiness() -> dict[str, str]:
    from sqlalchemy import text

    from app.core.db import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        await session.execute(text("SELECT 1"))
    return {"status": "ready"}
