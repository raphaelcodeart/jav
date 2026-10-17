"""Il bottone «Quero participar» del sito e delle aree: chi del mio conto
può andare a una gara, e l'iscrizione (o la richiesta al titolare) in un
clic. Lo usa chiunque appartenga al club (famiglia, atleta con il suo
accesso, staff con figli), come /club/branding."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, get_current_user
from app.domains.club import competitions as competitions_service
from app.domains.club import lessons as lessons_service
from app.domains.club import participation
from app.domains.club import service as club_service
from app.domains.club.models import Club, ClubCompetition

router = APIRouter(prefix="/club/participation", tags=["club"])


class ParticipateWrite(BaseModel):
    athlete_id: uuid.UUID
    category: str | None = None


async def _club(db: AsyncSession, request: Request, current_user: CurrentUser) -> Club:
    from app.domains.club.scope import CLUB_HEADER, resolve_club

    return await resolve_club(db, current_user=current_user, requested=request.headers.get(CLUB_HEADER))


async def _competition(db: AsyncSession, club: Club, competition_id: uuid.UUID) -> ClubCompetition:
    """La gara se il club la vede: sua o della rete."""
    comp = await db.get(ClubCompetition, competition_id)
    if comp is None or comp.organization_id != club.organization_id or comp.club_id not in (None, club.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gara non trovata.")
    return comp


@router.get("/mine")
async def my_registrations(
    request: Request, current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> dict:
    """Le gare a cui qualcuno del mio conto è già iscritto: il bottone diventa
    «Inscrito». `club_slug`: gli eventi degli altri club non hanno il bottone."""
    club = await _club(db, request, current_user)
    mine = await participation.my_athletes(db, club_id=club.id, user_id=current_user.user_id)
    ids = await participation.registered_competition_ids(db, athlete_ids=[a.id for a, _ in mine])
    return {"has_athletes": bool(mine), "club_slug": club.slug, "registered": [str(i) for i in ids]}


@router.get("/{competition_id}")
async def participation_status(
    competition_id: uuid.UUID, request: Request,
    current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> dict:
    """Per ogni atleta del mio conto: già iscritto, può, ha debiti che
    bloccano (con l'elenco), o non può per un altro motivo."""
    club = await _club(db, request, current_user)
    comp = await _competition(db, club, competition_id)
    today = (await lessons_service.club_now(db, club_id=club.id)).date()
    mine = await participation.my_athletes(db, club_id=club.id, user_id=current_user.user_id)
    return {
        "competition": {"id": comp.id, "name": comp.name, "starts_on": comp.starts_on,
                        "registration_deadline": comp.registration_deadline, "fee_cents": comp.fee_cents,
                        "status": comp.status},
        "athletes": [
            await participation.status_for(db, competition=comp, athlete=a, mode=mode, today=today) for a, mode in mine
        ],
    }


@router.post("/{competition_id}")
async def participate(
    competition_id: uuid.UUID, payload: ParticipateWrite, request: Request,
    current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> dict:
    """Il titolare iscrive (con la quota della gara); l'atleta che non è
    titolare manda il «Voglio partecipare» a chi lo iscrive. I debiti scaduti
    bloccano in tutti e due i casi (competitions.eligibility)."""
    club = await _club(db, request, current_user)
    comp = await _competition(db, club, competition_id)
    today = (await lessons_service.club_now(db, club_id=club.id)).date()
    mine = dict((a.id, (a, mode)) for a, mode in await participation.my_athletes(db, club_id=club.id, user_id=current_user.user_id))
    if payload.athlete_id not in mine:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Atleta non trovato.")
    athlete, mode = mine[payload.athlete_id]
    if mode == "ENROLL":
        try:
            await competitions_service.register_entry(
                db, competition=comp, athlete=athlete, actor_user_id=current_user.user_id,
                category=payload.category, today=today,
            )
        except club_service.ClubError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
        return {"result": "REGISTERED"}
    ok, reason = await competitions_service.eligibility(db, competition=comp, athlete=athlete, today=today)
    if not ok:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, reason or "Iscrizione non possibile.")
    sent = await participation.send_wish(db, athlete=athlete, competition=comp)
    return {"result": "WISH_SENT" if sent else "WISH_ALREADY"}
