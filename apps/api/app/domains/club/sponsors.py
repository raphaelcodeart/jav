"""Gli sponsor della rete JudoArteVida. Specifica: docs/club-portal.md,
"Sponsor".

La home li mostra in una barra di loghi che scorre; ogni logo porta a una
pagina semplice dello sponsor (/patrocinadores/<slug>) che lo descrive, con
un bottone grande verso il suo sito. Li gestisce lo staff della piattaforma
dalla console. Uno sponsor spento (`active`) sparisce dal sito, non dalla
console. Il logo va nel bucket dei media, come le foto delle pagine dei club,
e deve essere uno dei nostri (caricato da qui).
"""

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domains.audit import service as audit_service
from app.domains.club.clubs import slugify
from app.domains.club.service import ClubNotFoundError, ClubValidationError
from app.domains.club.site_models import Sponsor

_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def sponsor_dict(s: Sponsor) -> dict:
    return {
        "id": s.id, "name": s.name, "slug": s.slug, "tagline": s.tagline, "description": s.description,
        "logo_url": s.logo_url, "website_url": s.website_url, "color": s.color, "sort_order": s.sort_order,
        "active": s.active,
    }


def public_dict(s: Sponsor) -> dict:
    out = sponsor_dict(s)
    out.pop("active")
    out.pop("sort_order")
    return out


def _url(value: str | None) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    if not value.lower().startswith(("https://", "http://")):
        value = f"https://{value}"
    if len(value) > 500 or " " in value:
        raise ClubValidationError("Il sito dello sponsor non sembra un indirizzo: es. https://www.cm-lagos.pt")
    return value


def _clean(data: dict) -> dict:
    out: dict = {}
    if "name" in data:
        name = " ".join((data["name"] or "").split())[:120]
        if len(name) < 2:
            raise ClubValidationError("Scrivi il nome dello sponsor.")
        out["name"] = name
    for key, limit in (("tagline", 200), ("description", 5000)):
        if key in data:
            out[key] = (data[key] or "").strip()[:limit] or None
    if "website_url" in data:
        out["website_url"] = _url(data["website_url"])
    if "logo_url" in data:
        logo = (data["logo_url"] or "").strip() or None
        if logo and not logo.startswith(f"{get_settings().public_app_base_url}/media/"):
            raise ClubValidationError("Carica il logo da qui: le immagini esterne non si usano.")
        out["logo_url"] = logo
    if "color" in data:
        color = (data["color"] or "").strip() or None
        if color and not _COLOR.match(color):
            raise ClubValidationError("Il colore va scritto come #RRGGBB.")
        out["color"] = color.upper() if color else None
    if data.get("sort_order") is not None:
        out["sort_order"] = max(0, min(int(data["sort_order"]), 999))
    if data.get("active") is not None:
        out["active"] = bool(data["active"])
    return out


async def list_sponsors(db: AsyncSession, *, organization_id: uuid.UUID, only_active: bool) -> list[Sponsor]:
    stmt = select(Sponsor).where(Sponsor.organization_id == organization_id)
    if only_active:
        stmt = stmt.where(Sponsor.active.is_(True))
    return list((await db.execute(stmt.order_by(Sponsor.sort_order, Sponsor.name))).scalars())


async def public_sponsors(db: AsyncSession) -> list[Sponsor]:
    """Gli sponsor attivi di ogni organizzazione: l'installazione ne ha una."""
    stmt = select(Sponsor).where(Sponsor.active.is_(True)).order_by(Sponsor.sort_order, Sponsor.name)
    return list((await db.execute(stmt)).scalars())


async def public_sponsor(db: AsyncSession, *, slug: str) -> Sponsor:
    found = (await db.execute(
        select(Sponsor).where(Sponsor.slug == slug.strip().lower(), Sponsor.active.is_(True))
    )).scalars().first()
    if found is None:
        raise ClubNotFoundError("Sponsor non trovato.")
    return found


async def _unique_slug(db: AsyncSession, *, organization_id: uuid.UUID, name: str, exclude: uuid.UUID | None = None) -> str:
    base = slugify(name)[:70] or "sponsor"
    slug, n = base, 2
    while True:
        stmt = select(Sponsor.id).where(Sponsor.organization_id == organization_id, Sponsor.slug == slug)
        if exclude is not None:
            stmt = stmt.where(Sponsor.id != exclude)
        if (await db.execute(stmt)).first() is None:
            return slug
        slug, n = f"{base}-{n}", n + 1


async def _get(db: AsyncSession, *, organization_id: uuid.UUID, sponsor_id: uuid.UUID) -> Sponsor:
    sponsor = await db.get(Sponsor, sponsor_id)
    if sponsor is None or sponsor.organization_id != organization_id:
        raise ClubNotFoundError("Sponsor non trovato.")
    return sponsor


async def create_sponsor(db: AsyncSession, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID | None, data: dict) -> Sponsor:
    values = _clean({"name": data.get("name"), **{k: v for k, v in data.items() if k != "name"}})
    sponsor = Sponsor(organization_id=organization_id, **values,
                      slug=await _unique_slug(db, organization_id=organization_id, name=values["name"]))
    db.add(sponsor)
    await db.flush()
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id, action="sponsor.created",
        entity_type="sponsor", entity_id=str(sponsor.id), new_value={"name": sponsor.name},
    )
    await db.commit()
    await db.refresh(sponsor)
    return sponsor


async def update_sponsor(
    db: AsyncSession, *, organization_id: uuid.UUID, sponsor_id: uuid.UUID, actor_user_id: uuid.UUID, changes: dict,
) -> Sponsor:
    sponsor = await _get(db, organization_id=organization_id, sponsor_id=sponsor_id)
    for key, value in _clean(changes).items():
        setattr(sponsor, key, value)
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id, action="sponsor.updated",
        entity_type="sponsor", entity_id=str(sponsor.id), new_value={"name": sponsor.name},
    )
    await db.commit()
    await db.refresh(sponsor)
    return sponsor


async def delete_sponsor(db: AsyncSession, *, organization_id: uuid.UUID, sponsor_id: uuid.UUID, actor_user_id: uuid.UUID) -> None:
    sponsor = await _get(db, organization_id=organization_id, sponsor_id=sponsor_id)
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id, action="sponsor.deleted",
        entity_type="sponsor", entity_id=str(sponsor.id), previous_value={"name": sponsor.name},
    )
    await db.delete(sponsor)
    await db.commit()


def upload_logo(*, organization_id: uuid.UUID, file_bytes: bytes, content_type: str) -> str:
    from app.core.storage import UploadValidationError, upload_media

    try:
        return upload_media(file_bytes=file_bytes, content_type=content_type, key_prefix=f"sponsors/{organization_id}")
    except UploadValidationError as exc:
        raise ClubValidationError("Il logo deve essere un'immagine JPG, PNG o WebP di massimo 5 MB.") from exc
