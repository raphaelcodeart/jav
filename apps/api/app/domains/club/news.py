"""La bacheca dell'area riservata, come un social: le notizie dei club e di
JudoArteVida (come un post: titolo, testo, una foto, un video o un link), le
prove in arrivo come post, i «mi piace», e i documenti del club condivisi con
i soci (club_documents.py, `shared_with_members`). Specifica:
docs/club-portal.md, "La bacheca".

Chi vede che cosa:

- un post di un club con `audience = CLUB` lo vedono solo i soci di quel club;
- con `audience = NETWORK` lo vedono tutti i club del circuito;
- un post di JudoArteVida (`club_id` NULL, lo scrive l'amministratore dalla
  console) è sempre per tutto il circuito.

Le notizie non vanno sul sito pubblico. Una notizia non pubblicata è una
bozza che vede solo chi l'ha scritta. La foto va nel bucket dei media come
quelle della pagina del club; l'indirizzo della foto deve essere uno dei
nostri (caricato da qui), non un'immagine esterna.
"""

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.club.operations_models import ClubNewsLike, ClubNewsPost
from app.domains.club.scope import ClubScope
from app.domains.club.service import ClubNotFoundError, ClubValidationError

MAX_TITLE = 200
MAX_BODY = 10_000
MAX_URL = 500
#: Quante notizie mostra la bacheca: le fissate in cima e poi le più recenti.
BOARD_LIMIT = 50
#: Fin dove guardare le prove in arrivo da mettere nel flusso.
EVENTS_AHEAD_DAYS = 90
AUDIENCES = ("CLUB", "NETWORK")


@dataclass(frozen=True)
class Owner:
    """Chi scrive: un club (`club_id`) o JudoArteVida (`club_id` None)."""

    organization_id: uuid.UUID
    club_id: uuid.UUID | None

    @classmethod
    def of(cls, scope: ClubScope) -> "Owner":
        return cls(organization_id=scope.organization_id, club_id=scope.club_id)


def _url(value: str | None, *, label: str) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    if len(value) > MAX_URL or not value.lower().startswith(("https://", "http://")):
        raise ClubValidationError(f"{label}: scrivi un indirizzo che inizia con https://")
    return value


def _image(value: str | None) -> str | None:
    value = (value or "").strip() or None
    if value and not value.startswith(f"{get_settings().public_app_base_url}/media/"):
        raise ClubValidationError("Carica la foto da qui: le immagini esterne non si usano.")
    return value


def _clean(data: dict, *, platform: bool) -> dict:
    out: dict = {}
    if "title" in data:
        title = " ".join((data["title"] or "").split())[:MAX_TITLE]
        if not title:
            raise ClubValidationError("Dai un titolo alla notizia.")
        out["title"] = title
    if "body" in data:
        out["body"] = (data["body"] or "").strip()[:MAX_BODY] or None
    if "image_url" in data:
        out["image_url"] = _image(data["image_url"])
    if "video_url" in data:
        out["video_url"] = _url(data["video_url"], label="Video")
    if "link_url" in data:
        out["link_url"] = _url(data["link_url"], label="Link")
    for key in ("pinned", "published"):
        if data.get(key) is not None:
            out[key] = bool(data[key])
    if platform:
        out["audience"] = "NETWORK"
    elif data.get("audience") is not None:
        if data["audience"] not in AUDIENCES:
            raise ClubValidationError("Scegli chi vede la notizia: i soci del club o tutto il circuito.")
        out["audience"] = data["audience"]
    return out


async def _authors(db: AsyncSession, posts: list[ClubNewsPost]) -> dict[uuid.UUID, str]:
    from app.domains.club.people import _names

    return await _names(db, {p.author_user_id for p in posts if p.author_user_id})


async def _clubs(db: AsyncSession, club_ids: set) -> dict[uuid.UUID, dict]:
    """Nome e logo dei club che firmano i post."""
    from app.domains.club.models import Club
    from app.domains.club.site_models import ClubSite

    ids = {c for c in club_ids if c}
    if not ids:
        return {}
    rows = (await db.execute(
        select(Club.id, Club.name, Club.slug, ClubSite.logo_url).outerjoin(ClubSite, ClubSite.club_id == Club.id)
        .where(Club.id.in_(ids))
    )).all()
    return {cid: {"name": name, "slug": slug, "logo_url": logo} for cid, name, slug, logo in rows}


def _jav_ref() -> dict:
    return {"name": "JudoArteVida", "slug": None, "logo_url": f"{get_settings().public_app_base_url}/judoartevida-logo.jpg"}


def post_dict(post: ClubNewsPost, *, authors: dict, clubs: dict | None = None, likes: dict | None = None,
              liked: set | None = None) -> dict:
    return {
        "id": post.id, "title": post.title, "body": post.body, "image_url": post.image_url,
        "video_url": post.video_url, "link_url": post.link_url, "pinned": post.pinned,
        "published": post.published, "published_at": post.published_at, "audience": post.audience,
        "author_name": authors.get(post.author_user_id) if post.author_user_id else None,
        "author_user_id": post.author_user_id,
        "club": (clubs or {}).get(post.club_id) if post.club_id else _jav_ref(),
        "likes": (likes or {}).get(post.id, 0), "liked": post.id in (liked or set()),
    }


async def _likes(db: AsyncSession, post_ids: list[uuid.UUID], user_id: uuid.UUID | None) -> tuple[dict, set]:
    if not post_ids:
        return {}, set()
    counts = dict((await db.execute(
        select(ClubNewsLike.post_id, func.count()).where(ClubNewsLike.post_id.in_(post_ids)).group_by(ClubNewsLike.post_id)
    )).all())
    mine = set((await db.execute(
        select(ClubNewsLike.post_id).where(ClubNewsLike.post_id.in_(post_ids), ClubNewsLike.user_id == user_id)
    )).scalars()) if user_id else set()
    return counts, mine


async def _dicts(db: AsyncSession, posts: list[ClubNewsPost], *, user_id: uuid.UUID | None = None) -> list[dict]:
    authors = await _authors(db, posts)
    clubs = await _clubs(db, {p.club_id for p in posts})
    counts, mine = await _likes(db, [p.id for p in posts], user_id)
    return [post_dict(p, authors=authors, clubs=clubs, likes=counts, liked=mine) for p in posts]


async def list_owner_posts(db: AsyncSession, *, owner: Owner) -> list[dict]:
    """I post di chi scrive (club o piattaforma), bozze comprese: la sua console."""
    where = ClubNewsPost.club_id == owner.club_id if owner.club_id else ClubNewsPost.club_id.is_(None)
    posts = list((await db.execute(
        select(ClubNewsPost).where(ClubNewsPost.organization_id == owner.organization_id, where)
        .order_by(ClubNewsPost.pinned.desc(), ClubNewsPost.published_at.desc())
    )).scalars())
    return await _dicts(db, posts)


async def list_posts(db: AsyncSession, *, scope: ClubScope, include_drafts: bool) -> list[dict]:
    """Compatibilità: i post del club (con le bozze) o la bacheca dei suoi soci."""
    if include_drafts:
        return await list_owner_posts(db, owner=Owner.of(scope))
    return await _visible_posts(db, scope=scope, user_id=None)


async def _visible_posts(db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID | None) -> list[dict]:
    posts = list((await db.execute(
        select(ClubNewsPost).where(
            ClubNewsPost.organization_id == scope.organization_id, ClubNewsPost.published.is_(True),
            or_(ClubNewsPost.club_id == scope.club_id, ClubNewsPost.audience == "NETWORK"),
        ).order_by(ClubNewsPost.pinned.desc(), ClubNewsPost.published_at.desc()).limit(BOARD_LIMIT)
    )).scalars())
    return await _dicts(db, posts, user_id=user_id)


async def feed(db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, today: date) -> list[dict]:
    """Il flusso della bacheca: i post del club, del circuito e di
    JudoArteVida, e le prove dei prossimi mesi come post (alla data in cui
    sono state annunciate). I fissati in cima, poi dal più recente."""
    from app.domains.club import calendar

    items = [{"type": "POST", "date": p["published_at"], "post": p, "event": None}
             for p in await _visible_posts(db, scope=scope, user_id=user_id)]
    events = await calendar.calendar_events(db, scope=scope, date_from=today, date_to=today + timedelta(days=EVENTS_AHEAD_DAYS))
    from app.domains.club.models import ClubCompetition

    created = dict((await db.execute(
        select(ClubCompetition.id, ClubCompetition.created_at).where(ClubCompetition.id.in_([e["id"] for e in events]))
    )).all()) if events else {}
    for e in events:
        items.append({"type": "EVENT", "date": created.get(e["id"]) or utcnow(), "post": None,
                      "event": {**e, "id": str(e["id"])}})
    pinned = [i for i in items if i["post"] and i["post"]["pinned"]]
    rest = sorted((i for i in items if not (i["post"] and i["post"]["pinned"])), key=lambda i: i["date"], reverse=True)
    return pinned + rest[:BOARD_LIMIT + 20]


async def toggle_like(db: AsyncSession, *, scope: ClubScope, post_id: uuid.UUID, user_id: uuid.UUID) -> dict:
    post = await db.get(ClubNewsPost, post_id)
    if (post is None or not post.published or post.organization_id != scope.organization_id
            or (post.club_id != scope.club_id and post.audience != "NETWORK")):
        raise ClubNotFoundError("Notizia non trovata.")
    like = await db.get(ClubNewsLike, (post_id, user_id))
    if like is None:
        db.add(ClubNewsLike(post_id=post_id, user_id=user_id))
    else:
        await db.delete(like)
    await db.commit()
    counts, mine = await _likes(db, [post_id], user_id)
    return {"likes": counts.get(post_id, 0), "liked": post_id in mine}


async def _get(db: AsyncSession, *, owner: Owner, post_id: uuid.UUID) -> ClubNewsPost:
    post = await db.get(ClubNewsPost, post_id)
    if post is None or post.organization_id != owner.organization_id or post.club_id != owner.club_id:
        raise ClubNotFoundError("Notizia non trovata.")
    return post


async def _read(db: AsyncSession, post: ClubNewsPost) -> dict:
    return (await _dicts(db, [post]))[0]


def _owner(scope_or_owner: ClubScope | Owner) -> Owner:
    return scope_or_owner if isinstance(scope_or_owner, Owner) else Owner.of(scope_or_owner)


async def create_post(db: AsyncSession, *, scope: ClubScope | Owner, actor_user_id: uuid.UUID, data: dict) -> dict:
    owner = _owner(scope)
    values = _clean({"title": data.get("title"), **{k: v for k, v in data.items() if k != "title"}},
                    platform=owner.club_id is None)
    post = ClubNewsPost(organization_id=owner.organization_id, club_id=owner.club_id, **values,
                        author_user_id=actor_user_id, published_at=utcnow())
    db.add(post)
    await db.flush()
    await audit_service.record(
        db, organization_id=owner.organization_id, actor_user_id=actor_user_id, action="club.news_created",
        entity_type="club_news_post", entity_id=str(post.id), new_value={"title": post.title, "audience": post.audience},
    )
    await db.commit()
    await db.refresh(post)
    return await _read(db, post)


async def update_post(
    db: AsyncSession, *, scope: ClubScope | Owner, post_id: uuid.UUID, actor_user_id: uuid.UUID, changes: dict,
) -> dict:
    owner = _owner(scope)
    post = await _get(db, owner=owner, post_id=post_id)
    was_published = post.published
    for key, value in _clean(changes, platform=owner.club_id is None).items():
        setattr(post, key, value)
    # Una bozza che si pubblica va in cima, con la data di oggi.
    if post.published and not was_published:
        post.published_at = utcnow()
    await audit_service.record(
        db, organization_id=owner.organization_id, actor_user_id=actor_user_id, action="club.news_updated",
        entity_type="club_news_post", entity_id=str(post.id), new_value={"title": post.title},
    )
    await db.commit()
    await db.refresh(post)
    return await _read(db, post)


async def delete_post(db: AsyncSession, *, scope: ClubScope | Owner, post_id: uuid.UUID, actor_user_id: uuid.UUID) -> None:
    owner = _owner(scope)
    post = await _get(db, owner=owner, post_id=post_id)
    await audit_service.record(
        db, organization_id=owner.organization_id, actor_user_id=actor_user_id, action="club.news_deleted",
        entity_type="club_news_post", entity_id=str(post.id), previous_value={"title": post.title},
    )
    await db.delete(post)
    await db.commit()


def upload_image(*, scope: ClubScope | Owner, file_bytes: bytes, content_type: str) -> str:
    from app.core.storage import UploadValidationError, upload_media

    owner = _owner(scope)
    try:
        return upload_media(file_bytes=file_bytes, content_type=content_type,
                            key_prefix=f"club-news/{owner.club_id or 'jav'}")
    except UploadValidationError as exc:
        raise ClubValidationError("La foto deve essere un'immagine JPG, PNG o WebP di massimo 5 MB.") from exc


# --- I post dei treinadores ------------------------------------------------------------------------
#
# Un treinador scrive sulla bacheca del suo club come la segreteria, con tre
# limiti: solo per i soci del club (mai per tutto il circuito), niente post
# fissati in cima (quello è della segreteria), e corregge o toglie solo i
# suoi. La segreteria li vede tutti nella sua console e li può correggere,
# nascondere o togliere come i propri (moderazione).

_STAFF_FIELDS = ("title", "body", "image_url", "video_url", "link_url", "published")


async def list_author_posts(db: AsyncSession, *, scope: ClubScope, author_user_id: uuid.UUID) -> list[dict]:
    """I post di un treinador, bozze comprese."""
    posts = list((await db.execute(
        select(ClubNewsPost).where(
            ClubNewsPost.organization_id == scope.organization_id, ClubNewsPost.club_id == scope.club_id,
            ClubNewsPost.author_user_id == author_user_id,
        ).order_by(ClubNewsPost.published_at.desc())
    )).scalars())
    return await _dicts(db, posts)


async def staff_feed(db: AsyncSession, *, scope: ClubScope, user_id: uuid.UUID, today: date) -> list[dict]:
    """La bacheca come la vedono i soci, per lo staff."""
    return await feed(db, scope=scope, user_id=user_id, today=today)


async def _own(db: AsyncSession, *, scope: ClubScope, post_id: uuid.UUID, author_user_id: uuid.UUID) -> ClubNewsPost:
    post = await _get(db, owner=Owner.of(scope), post_id=post_id)
    if post.author_user_id != author_user_id:
        raise ClubNotFoundError("Notizia non trovata.")
    return post


async def create_staff_post(db: AsyncSession, *, scope: ClubScope, actor_user_id: uuid.UUID, data: dict) -> dict:
    values = {k: v for k, v in data.items() if k in _STAFF_FIELDS}
    return await create_post(db, scope=scope, actor_user_id=actor_user_id,
                             data={**values, "audience": "CLUB", "pinned": False})


async def update_staff_post(
    db: AsyncSession, *, scope: ClubScope, post_id: uuid.UUID, actor_user_id: uuid.UUID, changes: dict,
) -> dict:
    await _own(db, scope=scope, post_id=post_id, author_user_id=actor_user_id)
    return await update_post(db, scope=scope, post_id=post_id, actor_user_id=actor_user_id,
                             changes={k: v for k, v in changes.items() if k in _STAFF_FIELDS})


async def delete_staff_post(db: AsyncSession, *, scope: ClubScope, post_id: uuid.UUID, actor_user_id: uuid.UUID) -> None:
    await _own(db, scope=scope, post_id=post_id, author_user_id=actor_user_id)
    await delete_post(db, scope=scope, post_id=post_id, actor_user_id=actor_user_id)
