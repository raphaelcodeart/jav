"""Su quale club lavora chi chiama.

La piattaforma ospita più club, e ogni API del dominio club lavora su uno
solo. Quale, lo decide questo modulo, mai il chiamante:

- un account **di un club** (genitore, segreteria, istruttore: `users.club_id`)
  lavora sempre e solo sul suo club. Un'intestazione che ne indichi un altro
  viene ignorata, non rifiutata: non c'è niente da tentare;
- lo **staff della piattaforma** (`users.club_id` NULL, con `clubs.enter`)
  sceglie il club da gestire ("entra nel club" dal pannello Club): il
  frontend lo manda nell'intestazione `X-Jav-Club`, il proxy BFF la copia dal
  cookie `jav_club`.

Un club sospeso chiude la porta ai suoi account, non al superadmin, che deve
poter entrare per sistemare.
"""

import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, require_permission
from app.domains.club.models import Club
from app.domains.rbac.service import get_permission_codes_for_user
from app.domains.users.models import User

CLUB_HEADER = "X-Jav-Club"
#: Creare e modificare i club.
CLUBS_MANAGE = "clubs.manage"
#: Lavorare dentro un club qualsiasi, scegliendolo.
CLUBS_ENTER = "clubs.enter"


@dataclass(frozen=True)
class ClubScope:
    """Il perimetro di ogni funzione del dominio club: le query filtrano per
    `club_id`, l'audit e le notifiche vanno all'organizzazione."""

    organization_id: uuid.UUID
    club_id: uuid.UUID

    def columns(self) -> dict:
        """Le due colonne di ogni riga nuova del dominio."""
        return {"organization_id": self.organization_id, "club_id": self.club_id}


def scope_of(entity) -> ClubScope:
    """Il perimetro di una riga già caricata (atleta, corso, gara)."""
    return ClubScope(organization_id=entity.organization_id, club_id=entity.club_id)


@dataclass
class ClubUser(CurrentUser):
    club_id: uuid.UUID

    @property
    def scope(self) -> ClubScope:
        return ClubScope(organization_id=self.organization_id, club_id=self.club_id)


async def resolve_club(db: AsyncSession, *, current_user: CurrentUser, requested: str | None) -> Club:
    user = await db.get(User, current_user.user_id)
    if user is not None and user.club_id is not None:
        club = await db.get(Club, user.club_id)
        if club is None or club.status != "ACTIVE":
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Il tuo club al momento non è attivo: contatta la segreteria."
            )
        return club

    granted = await get_permission_codes_for_user(
        db, user_id=current_user.user_id, organization_id=current_user.organization_id
    )
    if CLUBS_ENTER not in granted:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Il tuo account non è collegato a nessun club: contatta la segreteria."
        )
    if not requested:
        raise HTTPException(status.HTTP_409_CONFLICT, "Scegli prima il club su cui lavorare, dal pannello Club.")
    try:
        club_id = uuid.UUID(requested)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Club non trovato.") from exc
    club = await db.get(Club, club_id)
    if club is None or club.organization_id != current_user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Club non trovato.")
    return club


def require_club_permission(permission_code: str):
    """Come core/deps.py::require_permission, più il club: la dipendenza di
    ogni rotta del dominio club."""

    async def _checker(
        request: Request,
        current_user: CurrentUser = Depends(require_permission(permission_code)),
        db: AsyncSession = Depends(get_db),
    ) -> ClubUser:
        club = await resolve_club(db, current_user=current_user, requested=request.headers.get(CLUB_HEADER))
        return ClubUser(
            user_id=current_user.user_id, organization_id=current_user.organization_id,
            roles=current_user.roles, club_id=club.id,
        )

    return _checker
