"""I video del canale YouTube di JudoArteVida, per il carosello del portale.

Si leggono dal feed pubblico del canale (gli ultimi 15 video): un video
nuovo pubblicato su YouTube compare da solo sul sito, senza che nessuno
tocchi niente. Il feed si chiede al massimo ogni mezz'ora e resta in
memoria; se YouTube non risponde si mostra l'ultimo elenco buono (o niente:
il carosello sparisce, la pagina no).

I video non si scaricano: il sito li incorpora con il lettore di YouTube,
come prevedono i termini di YouTube. Il canale si cambia con l'impostazione
dell'organizzazione `youtube_channel_id`.
"""

import html
import logging
import re
import time

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.organizations.models import Organization

logger = logging.getLogger(__name__)

#: Il canale "Judo Arte e Vida" (@ml8126).
DEFAULT_CHANNEL_ID = "UC07qkOMK4AOyOzqQEZll0ww"
CACHE_SECONDS = 30 * 60
FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")

_cache: dict[str, tuple[float, list[dict]]] = {}


def parse_feed(xml: str) -> list[dict]:
    """Gli <entry> del feed Atom: id, titolo, data, miniatura. Con espressioni
    regolari e non con un parser XML: il formato è fisso e così non c'è
    niente da interpretare oltre ai pochi campi che servono."""
    out = []
    for entry in re.findall(r"<entry>(.*?)</entry>", xml, re.DOTALL):
        video_id = (re.search(r"<yt:videoId>([^<]+)</yt:videoId>", entry) or [None, ""])[1]
        if not _VIDEO_ID.match(video_id):
            continue
        title = (re.search(r"<media:title>([^<]*)</media:title>", entry) or [None, ""])[1]
        published = (re.search(r"<published>([^<]+)</published>", entry) or [None, ""])[1]
        views = re.search(r'<media:statistics views="(\d+)"', entry)
        out.append({
            "id": video_id,
            "title": html.unescape(title).strip(),
            "published": published[:10] or None,
            "views": int(views.group(1)) if views else None,
            "thumbnail": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
            "url": f"https://www.youtube.com/watch?v={video_id}",
        })
    return out


async def channel_id_for(db: AsyncSession) -> str:
    from sqlalchemy import select

    settings = (await db.execute(select(Organization.settings).limit(1))).scalar_one_or_none() or {}
    value = (settings or {}).get("youtube_channel_id") or DEFAULT_CHANNEL_ID
    return value if re.match(r"^UC[A-Za-z0-9_-]{22}$", value) else DEFAULT_CHANNEL_ID


async def latest_videos(db: AsyncSession, *, now: float | None = None) -> list[dict]:
    channel_id = await channel_id_for(db)
    now = now or time.monotonic()
    cached = _cache.get(channel_id)
    if cached and now - cached[0] < CACHE_SECONDS:
        return cached[1]
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            res = await client.get(FEED_URL.format(channel_id=channel_id))
            res.raise_for_status()
        videos = parse_feed(res.text)
        _cache[channel_id] = (now, videos)
        return videos
    except Exception:
        logger.warning("YouTube feed not available for %s", channel_id, exc_info=True)
        return cached[1] if cached else []
