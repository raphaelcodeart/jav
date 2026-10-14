"""Le API dei messaggi dal sito (club/contact.py, docs/club-portal.md,
"Messaggi dal sito").

- `POST /public-site/clubs/{slug}/message`  chiunque: scrive a un club pubblicato;
- `POST /public-site/contact`               chiunque: scrive a JudoArteVida;
- `/club/admin/messages`                    la segreteria (`club.manage`): i
  messaggi del suo club, e solo quelli (il club lo decide club/scope.py);
- `/contact-messages`                       lo staff della piattaforma
  (`clubs.enter`, account senza club): i messaggi a JudoArteVida; quelli dei
  club, filtrati per club, solo il superadmin (`clubs.manage`).

Le rotte pubbliche rispondono sempre allo stesso modo quando il messaggio è
accettato, anche se il campo trappola era pieno: un robot non deve capire
che cosa lo ha fermato.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rate_limit import _client_ip, rate_limit
from app.domains.club import contact as contact_service
from app.domains.club import service as club_service
from app.domains.club.contact_schemas import (
    ContactInboxRead,
    ContactMessageRead,
    ContactMessageWrite,
    ContactSentRead,
    ContactStatusWrite,
)
from app.domains.club.models import Club
from app.domains.club.scope import CLUBS_ENTER, CLUBS_MANAGE, ClubUser, require_club_permission
from app.domains.organizations import service as organizations_service
from app.domains.rbac.service import get_permission_codes_for_user
from app.domains.users.models import User

contact_public_router = APIRouter(prefix="/public-site", tags=["public-site"])
contact_club_router = APIRouter(prefix="/club/admin/messages", tags=["club-admin"])
contact_platform_router = APIRouter(prefix="/contact-messages", tags=["contact-messages"])

MANAGE = "club.manage"
#: Per IP: chi scrive davvero manda un messaggio, due se ha dimenticato
#: qualcosa. Sotto c'è anche il tetto nel database (contact.MAX_PER_HOUR).
_LIMIT = rate_limit("public-contact", max_requests=5, window_seconds=600)


def _raise(exc: club_service.ClubError) -> None:
    if isinstance(exc, contact_service.ContactTooManyError):
        code = status.HTTP_429_TOO_MANY_REQUESTS
    elif isinstance(exc, club_service.ClubNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    else:
        code = status.HTTP_400_BAD_REQUEST
    raise HTTPException(code, str(exc)) from exc


async def _submit(db: AsyncSession, request: Request, payload: ContactMessageWrite, **target) -> ContactSentRead:
    try:
        await contact_service.submit(
            db, data=payload.model_dump(), ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"), **target,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return ContactSentRead()


@contact_public_router.post(
    "/clubs/{slug}/message", response_model=ContactSentRead, status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(_LIMIT)],
)
async def message_club(
    slug: str, payload: ContactMessageWrite, request: Request, db: AsyncSession = Depends(get_db),
) -> ContactSentRead:
    return await _submit(db, request, payload, club_slug=slug)


async def _jav_organization(db: AsyncSession) -> uuid.UUID:
    """A quale organizzazione scrive chi scrive a JudoArteVida: quella
    dell'installazione (una sola), come per login e inviti; con più
    organizzazioni, quella dei club attivi se è una sola."""
    try:
        return await organizations_service.resolve_organization_id(db, None)
    except organizations_service.OrganizationNotResolvedError:
        ids = (await db.execute(select(Club.organization_id).where(Club.status == "ACTIVE").distinct())).scalars().all()
        if len(ids) == 1:
            return ids[0]
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Destinatario non trovato.") from None


@contact_public_router.post(
    "/contact", response_model=ContactSentRead, status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(_LIMIT)],
)
async def message_jav(
    payload: ContactMessageWrite, request: Request, db: AsyncSession = Depends(get_db),
) -> ContactSentRead:
    return await _submit(db, request, payload, organization_id=await _jav_organization(db))


# --- Segreteria del club --------------------------------------------------------------------------


@contact_club_router.get("", response_model=ContactInboxRead)
async def club_inbox(
    status_filter: str | None = Query(default=None, alias="status", max_length=10),
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ContactInboxRead:
    try:
        return ContactInboxRead(**await contact_service.club_inbox(db, scope=current_user.scope, status=status_filter))
    except club_service.ClubError as exc:
        _raise(exc)


@contact_club_router.patch("/{message_id}", response_model=ContactMessageRead)
async def club_set_status(
    message_id: uuid.UUID,
    payload: ContactStatusWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ContactMessageRead:
    try:
        return ContactMessageRead(**await contact_service.set_club_status(
            db, scope=current_user.scope, message_id=message_id, status=payload.status,
            actor_user_id=current_user.user_id,
        ))
    except club_service.ClubError as exc:
        _raise(exc)


# --- Console della piattaforma --------------------------------------------------------------------


async def _platform_user(
    current_user: CurrentUser = Depends(require_permission(CLUBS_ENTER)), db: AsyncSession = Depends(get_db),
) -> tuple[CurrentUser, bool]:
    """Lo staff della piattaforma: un account di un club non legge i
    messaggi a JudoArteVida nemmeno se avesse il permesso. Il secondo valore
    dice se può vedere anche quelli dei club (superadmin)."""
    user = await db.get(User, current_user.user_id)
    if user is None or user.club_id is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Questa casella è dello staff di JudoArteVida.")
    granted = await get_permission_codes_for_user(
        db, user_id=current_user.user_id, organization_id=current_user.organization_id,
    )
    return current_user, CLUBS_MANAGE in granted


@contact_platform_router.get("", response_model=ContactInboxRead)
async def platform_inbox(
    club: str = Query(default="jav", max_length=40),
    status_filter: str | None = Query(default=None, alias="status", max_length=10),
    who: tuple[CurrentUser, bool] = Depends(_platform_user),
    db: AsyncSession = Depends(get_db),
) -> ContactInboxRead:
    """`club`: "jav" (i messaggi a JudoArteVida), "all", o l'id di un club."""
    current_user, can_see_clubs = who
    club_id, all_clubs = None, False
    if club != "jav":
        if not can_see_clubs:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "I messaggi dei club li legge la loro segreteria.")
        if club == "all":
            all_clubs = True
        else:
            try:
                club_id = uuid.UUID(club)
            except ValueError as exc:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Club non trovato.") from exc
    try:
        return ContactInboxRead(**await contact_service.platform_inbox(
            db, organization_id=current_user.organization_id, club_id=club_id, all_clubs=all_clubs,
            status=status_filter,
        ))
    except club_service.ClubError as exc:
        _raise(exc)


@contact_platform_router.patch("/{message_id}", response_model=ContactMessageRead)
async def platform_set_status(
    message_id: uuid.UUID,
    payload: ContactStatusWrite,
    who: tuple[CurrentUser, bool] = Depends(_platform_user),
    db: AsyncSession = Depends(get_db),
) -> ContactMessageRead:
    current_user, can_see_clubs = who
    try:
        return ContactMessageRead(**await contact_service.set_platform_status(
            db, organization_id=current_user.organization_id, message_id=message_id, status=payload.status,
            actor_user_id=current_user.user_id, can_see_clubs=can_see_clubs,
        ))
    except club_service.ClubError as exc:
        _raise(exc)
