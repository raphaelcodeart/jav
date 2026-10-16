"""La conservazione (domains/legal/retention.py): i messaggi dal sito oltre
24 mesi e le sessioni scadute da oltre 30 giorni spariscono; il resto resta."""

from datetime import timedelta

from sqlalchemy import select

from app.core.db import utcnow
from app.domains.club.contact_models import ContactMessage
from app.domains.legal import retention


async def test_old_contact_messages_go(db, scope):
    now = utcnow()
    for days in (10, 800):
        db.add(ContactMessage(organization_id=scope.organization_id, club_id=None, name="Ana", email="ana@example.demo",
                              message="Olá, queria informações", topic="GENERAL", locale="pt", status="NEW",
                              consent_at=now - timedelta(days=days), created_at=now - timedelta(days=days)))
    await db.commit()
    done = await retention.run(db)
    assert done["contact_messages"] == 1
    left = (await db.execute(select(ContactMessage))).scalars().all()
    assert len(left) == 1
