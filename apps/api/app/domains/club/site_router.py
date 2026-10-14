"""Le API del sito pubblico JudoArteVida (docs/club-portal.md, "Sito pubblico").

- `/public-site/...`                       chiunque, senza login: il portale;
- `/club/admin/site/...`                   la segreteria (`club.manage`): la
  pagina del suo club, chi dei suoi atleti compare e la scheda di ognuno
  (`/athletes/{id}/page`: profilo IJF, testi, foto e video);
- `/club/athletes/{id}/public-profile`     il genitore (`club.family`): il
  consenso per suo figlio.

Le rotte pubbliche non ricevono mai un club dall'utente se non come slug
dell'indirizzo, e il servizio risponde "non trovato" per tutto ciò che non è
pubblicato: un club in bozza o un atleta senza consenso non esistono.
"""

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.rate_limit import rate_limit
from app.domains.club import service as club_service
from app.domains.club import site as site_service
from app.domains.club import videos as videos_service
from app.domains.club.models import Club
from app.domains.club.scope import ClubUser, require_club_permission
from app.domains.club.site_schemas import (
    AthleteMediaWrite,
    AthletePageAdminRead,
    AthletePageWrite,
    AthletePublicStatusRead,
    AthleteVideoWrite,
    PortalHomeRead,
    PublicClubCard,
    PublicClubPage,
    PublicCoursesRead,
    PublicEvent,
    PublicEventDetail,
    PublicJudokaProfile,
    PublicProfileConsentRead,
    PublicProfileConsentWrite,
    PublicRankingRead,
    PublishWrite,
    SiteAdminRead,
    SiteImageRead,
    SiteWrite,
)

public_site_router = APIRouter(prefix="/public-site", tags=["public-site"])
site_admin_router = APIRouter(prefix="/club/admin/site", tags=["club-admin"])
site_family_router = APIRouter(prefix="/club", tags=["club"])


@public_site_router.get("/videos")
async def public_videos(db: AsyncSession = Depends(get_db)) -> list[dict]:
    """Gli ultimi video del canale YouTube di JudoArteVida (club/videos.py)."""
    return await videos_service.latest_videos(db)

FAMILY = "club.family"
MANAGE = "club.manage"


def _raise(exc: club_service.ClubError) -> None:
    code = status.HTTP_404_NOT_FOUND if isinstance(exc, club_service.ClubNotFoundError) else status.HTTP_400_BAD_REQUEST
    raise HTTPException(code, str(exc)) from exc


# --- Pubbliche ------------------------------------------------------------------------------------


@public_site_router.get("/home", response_model=PortalHomeRead)
async def portal_home(db: AsyncSession = Depends(get_db)) -> PortalHomeRead:
    return PortalHomeRead(**await site_service.portal_home(db))


@public_site_router.get("/courses", response_model=PublicCoursesRead)
async def public_courses(db: AsyncSession = Depends(get_db)) -> PublicCoursesRead:
    """"Cursos JAV nas escolas": i corsi pubblicati, senza persone."""
    return PublicCoursesRead(**await site_service.public_courses(db))


@public_site_router.get("/clubs", response_model=list[PublicClubCard])
async def list_clubs(db: AsyncSession = Depends(get_db)) -> list[PublicClubCard]:
    return [PublicClubCard(**c) for c in await site_service.list_public_clubs(db)]


@public_site_router.get("/clubs/{slug}", response_model=PublicClubPage)
async def club_page(slug: str, db: AsyncSession = Depends(get_db)) -> PublicClubPage:
    try:
        return PublicClubPage(**await site_service.club_page(db, slug=slug))
    except club_service.ClubError as exc:
        _raise(exc)


@public_site_router.get("/judoka/{athlete_id}", response_model=PublicJudokaProfile)
async def judoka_profile(athlete_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> PublicJudokaProfile:
    try:
        return PublicJudokaProfile(**await site_service.judoka_profile(db, athlete_id=athlete_id))
    except club_service.ClubError as exc:
        _raise(exc)


@public_site_router.get("/events", response_model=list[PublicEvent])
async def list_events(
    club: str | None = Query(default=None, max_length=80),
    kind: str | None = Query(default=None),
    when: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[PublicEvent]:
    try:
        return [PublicEvent(**e) for e in await site_service.list_events(db, club_slug=club, kind=kind, when=when)]
    except club_service.ClubError as exc:
        _raise(exc)


@public_site_router.get("/events/{event_id}", response_model=PublicEventDetail)
async def event_detail(event_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> PublicEventDetail:
    try:
        return PublicEventDetail(**await site_service.event_detail(db, event_id=event_id))
    except club_service.ClubError as exc:
        _raise(exc)


@public_site_router.get("/ranking", response_model=PublicRankingRead)
async def ranking(
    season: int | None = Query(default=None, ge=2000, le=2100),
    age_band: str | None = Query(default=None),
    club: str | None = Query(default=None, max_length=80),
    db: AsyncSession = Depends(get_db),
) -> PublicRankingRead:
    try:
        return PublicRankingRead(**await site_service.public_ranking(db, season=season, age_band=age_band, club_slug=club))
    except club_service.ClubError as exc:
        _raise(exc)


# --- Segreteria -----------------------------------------------------------------------------------


async def _admin_read(db: AsyncSession, current_user: ClubUser, site) -> SiteAdminRead:
    club = await db.get(Club, current_user.club_id)
    return SiteAdminRead(**site_service.admin_site_dict(site, club))


@site_admin_router.get("", response_model=SiteAdminRead)
async def get_site(
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> SiteAdminRead:
    return await _admin_read(db, current_user, await site_service.get_site(db, scope=current_user.scope))


@site_admin_router.put("", response_model=SiteAdminRead)
async def update_site(
    payload: SiteWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> SiteAdminRead:
    try:
        site = await site_service.update_site(
            db, scope=current_user.scope, actor_user_id=current_user.user_id,
            changes=payload.model_dump(exclude_unset=True),
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return await _admin_read(db, current_user, site)


@site_admin_router.post("/publish", response_model=SiteAdminRead)
async def publish_site(
    payload: PublishWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> SiteAdminRead:
    site = await site_service.update_site(
        db, scope=current_user.scope, actor_user_id=current_user.user_id, changes={"published": payload.published},
    )
    return await _admin_read(db, current_user, site)


@site_admin_router.post(
    "/images", response_model=SiteImageRead,
    dependencies=[Depends(rate_limit("club-site-image", max_requests=40, window_seconds=300))],
)
async def upload_image(
    slot: str = Form(...),
    caption: str | None = Form(default=None),
    file: UploadFile = File(...),
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> SiteImageRead:
    try:
        site, url = await site_service.upload_site_image(
            db, scope=current_user.scope, actor_user_id=current_user.user_id, slot=slot,
            file_bytes=await file.read(), content_type=file.content_type or "", caption=caption,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return SiteImageRead(url=url, site=await _admin_read(db, current_user, site))


@site_admin_router.get("/athletes", response_model=list[AthletePublicStatusRead])
async def list_athletes(
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> list[AthletePublicStatusRead]:
    rows = await site_service.list_athletes_public_status(db, scope=current_user.scope)
    return [AthletePublicStatusRead(**r) for r in rows]


@site_admin_router.post("/athletes/{athlete_id}/publish", response_model=list[AthletePublicStatusRead])
async def publish_athlete(
    athlete_id: uuid.UUID,
    payload: PublishWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[AthletePublicStatusRead]:
    try:
        await site_service.set_athlete_published(
            db, scope=current_user.scope, athlete_id=athlete_id, published=payload.published,
            actor_user_id=current_user.user_id,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    rows = await site_service.list_athletes_public_status(db, scope=current_user.scope)
    return [AthletePublicStatusRead(**r) for r in rows]


# La scheda pubblica di un atleta: rifiutata nell'unità dei corsi JAV
# (site._page_athlete), dove gli atleti non compaiono mai.


@site_admin_router.get("/athletes/{athlete_id}/page", response_model=AthletePageAdminRead)
async def get_athlete_page(
    athlete_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> AthletePageAdminRead:
    try:
        return AthletePageAdminRead(**await site_service.athlete_page_admin(
            db, scope=current_user.scope, athlete_id=athlete_id,
        ))
    except club_service.ClubError as exc:
        _raise(exc)


@site_admin_router.put("/athletes/{athlete_id}/page", response_model=AthletePageAdminRead)
async def update_athlete_page(
    athlete_id: uuid.UUID,
    payload: AthletePageWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> AthletePageAdminRead:
    try:
        return AthletePageAdminRead(**await site_service.update_athlete_page(
            db, scope=current_user.scope, athlete_id=athlete_id, actor_user_id=current_user.user_id,
            changes=payload.model_dump(exclude_unset=True),
        ))
    except club_service.ClubError as exc:
        _raise(exc)


@site_admin_router.post(
    "/athletes/{athlete_id}/page/photos", response_model=AthletePageAdminRead,
    dependencies=[Depends(rate_limit("club-athlete-page-photo", max_requests=40, window_seconds=300))],
)
async def add_athlete_photo(
    athlete_id: uuid.UUID,
    caption: str | None = Form(default=None),
    file: UploadFile = File(...),
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> AthletePageAdminRead:
    try:
        return AthletePageAdminRead(**await site_service.add_athlete_photo(
            db, scope=current_user.scope, athlete_id=athlete_id, actor_user_id=current_user.user_id,
            file_bytes=await file.read(), content_type=file.content_type or "", caption=caption,
        ))
    except club_service.ClubError as exc:
        _raise(exc)


@site_admin_router.post("/athletes/{athlete_id}/page/videos", response_model=AthletePageAdminRead)
async def add_athlete_video(
    athlete_id: uuid.UUID,
    payload: AthleteVideoWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> AthletePageAdminRead:
    try:
        return AthletePageAdminRead(**await site_service.add_athlete_video(
            db, scope=current_user.scope, athlete_id=athlete_id, actor_user_id=current_user.user_id,
            url=payload.url, caption=payload.caption,
        ))
    except club_service.ClubError as exc:
        _raise(exc)


@site_admin_router.patch("/athletes/{athlete_id}/page/media/{media_id}", response_model=AthletePageAdminRead)
async def update_athlete_media(
    athlete_id: uuid.UUID,
    media_id: uuid.UUID,
    payload: AthleteMediaWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> AthletePageAdminRead:
    try:
        return AthletePageAdminRead(**await site_service.update_athlete_media(
            db, scope=current_user.scope, athlete_id=athlete_id, media_id=media_id,
            actor_user_id=current_user.user_id, changes=payload.model_dump(exclude_unset=True),
        ))
    except club_service.ClubError as exc:
        _raise(exc)


@site_admin_router.delete("/athletes/{athlete_id}/page/media/{media_id}", response_model=AthletePageAdminRead)
async def delete_athlete_media(
    athlete_id: uuid.UUID,
    media_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> AthletePageAdminRead:
    try:
        return AthletePageAdminRead(**await site_service.delete_athlete_media(
            db, scope=current_user.scope, athlete_id=athlete_id, media_id=media_id,
            actor_user_id=current_user.user_id,
        ))
    except club_service.ClubError as exc:
        _raise(exc)


# --- Famiglia -------------------------------------------------------------------------------------


async def _my_athlete(db: AsyncSession, current_user: ClubUser, athlete_id: uuid.UUID):
    try:
        return await club_service.get_owned_athlete(
            db, scope=current_user.scope, guardian_user_id=current_user.user_id, athlete_id=athlete_id,
        )
    except club_service.ClubError as exc:
        _raise(exc)


@site_family_router.get("/athletes/{athlete_id}/public-profile", response_model=PublicProfileConsentRead)
async def get_public_profile(
    athlete_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> PublicProfileConsentRead:
    athlete = await _my_athlete(db, current_user, athlete_id)
    return PublicProfileConsentRead(**await site_service.get_consent(db, athlete=athlete))


@site_family_router.put("/athletes/{athlete_id}/public-profile", response_model=PublicProfileConsentRead)
async def update_public_profile(
    athlete_id: uuid.UUID,
    payload: PublicProfileConsentWrite,
    current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> PublicProfileConsentRead:
    athlete = await _my_athlete(db, current_user, athlete_id)
    return PublicProfileConsentRead(**await site_service.update_consent(
        db, athlete=athlete, actor_user_id=current_user.user_id, changes=payload.model_dump(exclude_unset=True),
    ))
