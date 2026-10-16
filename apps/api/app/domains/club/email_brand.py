"""Il marchio delle email di un club (core/email_templates.EmailBrand): il
logo e i colori della sua pagina pubblica (club/brand.py, contrasto già
controllato), i suoi contatti, e in fondo la rete JudoArteVida. Senza club,
o senza pagina, si firma JudoArteVida."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.email_templates import EmailBrand, jav_brand


async def club_brand(db: AsyncSession, club_id: uuid.UUID | None) -> EmailBrand:
    from app.domains.club import brand as brand_rules
    from app.domains.club.models import Club
    from app.domains.club.site_models import ClubSite

    if club_id is None:
        return jav_brand()
    club = await db.get(Club, club_id)
    if club is None or club.kind == "JAV_COURSES":
        return jav_brand()
    site = (await db.execute(select(ClubSite).where(ClubSite.club_id == club_id))).scalar_one_or_none()
    theme = brand_rules.theme(site.brand_primary if site else None, site.brand_secondary if site else None,
                              site.brand_accent if site else None)
    base = get_settings().public_app_base_url
    contacts = tuple(x for x in (
        (site.contact_email if site else None) or (club.settings or {}).get("contact_email"),
        site.contact_phone if site else None,
    ) if x)
    return EmailBrand(
        name=club.name,
        logo_url=(site.logo_url if site and site.logo_url else f"{base}/judoartevida-logo.jpg"),
        primary=theme["cover_from"], accent=theme["accent"], on_primary="#ffffff",
        tagline=(site.tagline if site and site.tagline else (site.city if site else None)),
        contact_lines=contacts,
        website=f"{base}/clubes/{club.slug}" if site and site.published else base,
        network=True,
    )


async def brand_for_user(db: AsyncSession, user_id: uuid.UUID) -> EmailBrand:
    """Il marchio di chi riceve: il suo club, o JudoArteVida."""
    from app.domains.users.models import User

    user = await db.get(User, user_id)
    return await club_brand(db, user.club_id if user else None)
