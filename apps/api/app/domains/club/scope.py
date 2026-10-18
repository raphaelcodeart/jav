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

- un **treinador di più club** (`club_staff_memberships`) sceglie entrando
  in quale lavorare: il frontend lo manda nell'intestazione `X-Jav-Staff-Club`
  (cookie `jav_staff_club`). Vale **solo** per le rotte del treinador
  (`club.instruct`) e per il tema dell'area del treinador: famiglia, atleta e
  segreteria restano sul club dell'account, così un treinador che è anche
  genitore non mescola i dati. In un club che non è il suo (`home` falso) è
  solo treinador: mai segreteria, qualunque ruolo abbia a casa.

Un club sospeso chiude la porta ai suoi account, non al superadmin, che deve
poter entrare per sistemare.
"""

import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, require_permission
from app.domains.club.models import Club
from app.domains.rbac.service import get_permission_codes_for_user
from app.domains.users.models import User

CLUB_HEADER = "X-Jav-Club"
#: Il club scelto dal treinador di più club (club/staff_clubs.py).
STAFF_CLUB_HEADER = "X-Jav-Staff-Club"
#: Le rotte su cui vale la scelta del treinador.
STAFF_PERMISSION = "club.instruct"
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
    #: Il club dell'account (o quello in cui è entrato il superadmin). Falso
    #: per un treinador nel club di un'altra appartenenza: lì non è segreteria.
    home: bool = True

    @property
    def scope(self) -> ClubScope:
        return ClubScope(organization_id=self.organization_id, club_id=self.club_id)


async def staff_club(db: AsyncSession, *, user: User, requested: str | None) -> Club | None:
    """Il club di un'altra appartenenza scelto dal treinador, se è davvero
    suo e attivo; None = il club dell'account."""
    from app.domains.club.models import ClubStaffMembership

    if not requested or user.club_id is None:
        return None
    try:
        club_id = uuid.UUID(requested)
    except ValueError:
        return None
    if club_id == user.club_id:
        return None
    member = (await db.execute(select(ClubStaffMembership.id).where(
        ClubStaffMembership.user_id == user.id, ClubStaffMembership.club_id == club_id,
        ClubStaffMembership.status == "ACTIVE",
    ))).first()
    if member is None:
        return None
    club = await db.get(Club, club_id)
    return club if club is not None and club.status == "ACTIVE" else None


async def resolve_club(
    db: AsyncSession, *, current_user: CurrentUser, requested: str | None, staff_requested: str | None = None,
) -> Club:
    """Il club della richiesta. `staff_requested` (il club scelto dal
    treinador) lo passa solo chi serve l'area del treinador."""
    user = await db.get(User, current_user.user_id)
    if user is not None and user.club_id is not None:
        other = await staff_club(db, user=user, requested=staff_requested)
        if other is not None:
            return other
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
        staff = request.headers.get(STAFF_CLUB_HEADER) if permission_code == STAFF_PERMISSION else None
        club = await resolve_club(db, current_user=current_user, requested=request.headers.get(CLUB_HEADER),
                                  staff_requested=staff)
        user = await db.get(User, current_user.user_id)
        return ClubUser(
            user_id=current_user.user_id, organization_id=current_user.organization_id,
            roles=current_user.roles, club_id=club.id,
            home=user is None or user.club_id is None or user.club_id == club.id,
        )

    return _checker
