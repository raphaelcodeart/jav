"""La conservazione dei dati (docs/legal.md, «Lacune»): ciò che la Política de
Privacidade promette di cancellare, lo cancella questo job ogni notte.

- messaggi dal sito (`contact_messages`) più vecchi di **24 mesi**;
- sessioni (`sessions`) scadute da più di **30 giorni**.

Il resto dei termini (audit 2 anni, certificati, documenti) resta da
applicare: tocca dati che servono come prova e va fatto con più cura.
"""

from datetime import timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow

CONTACT_MONTHS = 24
SESSION_GRACE_DAYS = 30


async def run(db: AsyncSession) -> dict:
    from app.domains.auth.models import Session
    from app.domains.club.contact_models import ContactMessage

    now = utcnow()
    contacts = (await db.execute(
        delete(ContactMessage).where(ContactMessage.created_at < now - timedelta(days=CONTACT_MONTHS * 30 + 10))
    )).rowcount
    sessions = (await db.execute(
        delete(Session).where(Session.expires_at < now - timedelta(days=SESSION_GRACE_DAYS))
    )).rowcount
    await db.commit()
    return {"contact_messages": contacts or 0, "sessions": sessions or 0}
