#!/usr/bin/env bash
# Manda una notifica allo staff di ogni organizzazione, dentro l'app (la
# campanella). Per gli script notturni: un backup che fallisce in silenzio
# è peggio di nessun backup. Best effort -- se l'app è giù non fa niente.
# Usage: scripts/notify-staff.sh <dev|production> "<titolo>" "<testo>"
set -uo pipefail

ENV="${1:?env}"
TITLE="${2:?titolo}"
BODY="${3:-}"
docker compose -f "docker-compose.${ENV}.yml" exec -T api python - "$TITLE" "$BODY" <<'PY' >/dev/null 2>&1 || true
import asyncio, sys
import app.main  # noqa: F401
from sqlalchemy import select
from app.core.db import AsyncSessionLocal
from app.domains.notifications import service as notifications
from app.domains.organizations.models import Organization

async def main() -> None:
    async with AsyncSessionLocal() as db:
        for org_id in (await db.execute(select(Organization.id))).scalars().all():
            await notifications.notify_roles(
                db, organization_id=org_id, roles=notifications.STAFF_NOTIFY_ROLES,
                type_="BACKUP_FAILED", entity_type="backup", entity_id="nightly",
                title=sys.argv[1], body=sys.argv[2] or None,
            )
        await db.commit()

asyncio.run(main())
PY
