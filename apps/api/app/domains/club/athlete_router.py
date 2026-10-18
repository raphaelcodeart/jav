"""Le rotte del conto dell'atleta (club/athlete_access.py).

- `/club/athletes/{id}/login[...]`: il titolare crea, cambia e spegne
  l'accesso del suo atleta, e ne genera il QR (`club.family`);
- `/club/athlete-area[...]`: l'area dell'atleta, per l'atleta stesso o per il
  suo titolare (`club.athlete`, che hanno sia ATHLETE sia CUSTOMER). Anche
  l'atleta con il suo accesso carica il proprio certificato medico: è lui
  che va dal medico, e la segreteria lo vede come quello caricato dal
  titolare (stesso servizio, stesso bucket privato).
"""

import uuid
from datetime import date, datetime, time

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.rate_limit import rate_limit
from app.domains.club import athlete_access, seasons
from app.domains.club import lessons as lessons_service
from app.domains.club import months as months_service
from app.domains.club import service as club_service
from app.domains.club.schemas import AthleteDetailRead, CertificateRead, SeasonMonthsRead, UrlRead
from app.domains.club.scope import ClubUser, require_club_permission, scope_of

router = APIRouter(prefix="/club", tags=["club-athlete"])

FAMILY = "club.family"
ATHLETE = "club.athlete"


def _raise(exc: club_service.ClubError) -> None:
    code = status.HTTP_404_NOT_FOUND if isinstance(exc, club_service.ClubNotFoundError) else status.HTTP_400_BAD_REQUEST
    raise HTTPException(code, str(exc)) from exc


class AthleteLoginRead(BaseModel):
    athlete_id: uuid.UUID
    has_login: bool
    is_self: bool
    username: str | None
    email: str | None
    active: bool
    qr_active_until: datetime | None


class AthleteLoginWrite(BaseModel):
    username: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=128)


class AthleteQrRead(AthleteLoginRead):
    #: Il link con il codice in chiaro, una volta sola (/entrar/<code>), e il
    #: QR già disegnato (SVG in un data URI: il browser lo mostra in un <img>,
    #: dove nessuno script gira).
    url: str
    qr_image: str


def _qr_image(url: str) -> str:
    import base64

    from reportlab.graphics import renderSVG
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing

    widget = QrCodeWidget(url, barLevel="M")
    x0, y0, x1, y1 = widget.getBounds()
    size = 320
    drawing = Drawing(size, size, transform=[size / (x1 - x0), 0, 0, size / (y1 - y0), 0, 0])
    drawing.add(widget)
    svg = renderSVG.drawToString(drawing)
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


class AreaAthleteRef(BaseModel):
    id: uuid.UUID
    name: str
    photo_url: str | None
    is_own: bool


class AreaLessonRead(BaseModel):
    date: date
    course_id: uuid.UUID
    course_name: str
    starts_at: time
    ends_at: time
    status: str


class AthleteAreaRead(AthleteDetailRead):
    age: int
    is_minor: bool
    viewer_is_athlete: bool
    can_manage: bool
    #: Può caricare la prova delle quote: il titolare, o l'atleta dai 18 anni federali.
    can_pay: bool = False
    can_become_holder: bool
    #: Il titolare guarda un figlio maggiorenne: può invitarlo a prendere il suo conto.
    can_invite_holder: bool = False
    #: Oggi all'ora del club (le lezioni di oggi si segnano solo oggi).
    today: date
    lessons: list[AreaLessonRead]
    month_present: int
    month_total: int


class AreaAttendanceWrite(BaseModel):
    course_id: uuid.UUID


class BecomeHolderWrite(BaseModel):
    email: str | None = Field(default=None, max_length=255)


# --- Il titolare: l'accesso del suo atleta ------------------------------------------------------


async def _owned(db: AsyncSession, user: ClubUser, athlete_id: uuid.UUID):
    try:
        return await club_service.get_owned_athlete(
            db, scope=user.scope, guardian_user_id=user.user_id, athlete_id=athlete_id,
        )
    except club_service.ClubError as exc:
        _raise(exc)


@router.get("/athletes/{athlete_id}/login", response_model=AthleteLoginRead)
async def get_login(
    athlete_id: uuid.UUID, current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> AthleteLoginRead:
    athlete = await _owned(db, current_user, athlete_id)
    return AthleteLoginRead(**await athlete_access.login_status(db, athlete=athlete))


@router.put(
    "/athletes/{athlete_id}/login", response_model=AthleteLoginRead,
    dependencies=[Depends(rate_limit("club-athlete-login", max_requests=20, window_seconds=300))],
)
async def put_login(
    athlete_id: uuid.UUID, payload: AthleteLoginWrite,
    current_user: ClubUser = Depends(require_club_permission(FAMILY)), db: AsyncSession = Depends(get_db),
) -> AthleteLoginRead:
    athlete = await _owned(db, current_user, athlete_id)
    try:
        row = await athlete_access.set_login(
            db, athlete=athlete, actor_user_id=current_user.user_id,
            username=payload.username, email=payload.email, password=payload.password,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return AthleteLoginRead(**row)


@router.delete("/athletes/{athlete_id}/login", response_model=AthleteLoginRead)
async def delete_login(
    athlete_id: uuid.UUID, current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> AthleteLoginRead:
    athlete = await _owned(db, current_user, athlete_id)
    try:
        row = await athlete_access.disable_login(db, athlete=athlete, actor_user_id=current_user.user_id)
    except club_service.ClubError as exc:
        _raise(exc)
    return AthleteLoginRead(**row)


@router.post(
    "/athletes/{athlete_id}/login/qr", response_model=AthleteQrRead,
    dependencies=[Depends(rate_limit("club-athlete-qr", max_requests=10, window_seconds=300))],
)
async def create_qr(
    athlete_id: uuid.UUID, current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> AthleteQrRead:
    athlete = await _owned(db, current_user, athlete_id)
    try:
        code, row = await athlete_access.create_qr(db, athlete=athlete, actor_user_id=current_user.user_id)
    except club_service.ClubError as exc:
        _raise(exc)
    from app.core.config import get_settings

    url = f"{get_settings().public_app_base_url.rstrip('/')}/entrar/{code}"
    return AthleteQrRead(**row, url=url, qr_image=_qr_image(url))


@router.delete("/athletes/{athlete_id}/login/qr", response_model=AthleteLoginRead)
async def delete_qr(
    athlete_id: uuid.UUID, current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> AthleteLoginRead:
    athlete = await _owned(db, current_user, athlete_id)
    return AthleteLoginRead(**await athlete_access.revoke_qr(db, athlete=athlete, actor_user_id=current_user.user_id))


# --- L'area dell'atleta -------------------------------------------------------------------------


@router.get("/athlete-area", response_model=list[AreaAthleteRef])
async def list_areas(
    current_user: ClubUser = Depends(require_club_permission(ATHLETE)), db: AsyncSession = Depends(get_db),
) -> list[AreaAthleteRef]:
    athletes = await athlete_access.area_athletes(db, user_id=current_user.user_id, club_id=current_user.club_id)
    return [
        AreaAthleteRef(id=a.id, name=f"{a.first_name} {a.last_name}", photo_url=a.photo_url,
                       is_own=a.user_id == current_user.user_id)
        for a in athletes
    ]


async def _area_athlete(db: AsyncSession, user: ClubUser, athlete_id: uuid.UUID):
    try:
        return await athlete_access.area_athlete(db, user_id=user.user_id, club_id=user.club_id, athlete_id=athlete_id)
    except club_service.ClubError as exc:
        _raise(exc)


@router.get("/athlete-area/{athlete_id}", response_model=AthleteAreaRead)
async def get_area(
    athlete_id: uuid.UUID, current_user: ClubUser = Depends(require_club_permission(ATHLETE)),
    db: AsyncSession = Depends(get_db),
) -> AthleteAreaRead:
    athlete = await _area_athlete(db, current_user, athlete_id)
    today = (await lessons_service.club_now(db, club_id=current_user.club_id)).date()
    return AthleteAreaRead(**await athlete_access.area(
        db, athlete=athlete, viewer_user_id=current_user.user_id, today=today,
    ))


class InviteHolderWrite(BaseModel):
    email: str = Field(min_length=3, max_length=255)


@router.post("/athlete-area/{athlete_id}/invite-holder")
async def invite_holder(
    athlete_id: uuid.UUID, payload: InviteHolderWrite,
    current_user: ClubUser = Depends(require_club_permission(ATHLETE)), db: AsyncSession = Depends(get_db),
) -> dict:
    """Il titolare invita il figlio maggiorenne a prendere il suo conto
    (athlete_access.invite_holder): l'email all'atleta, il genitore resta collegato."""
    athlete = await _area_athlete(db, current_user, athlete_id)
    try:
        link = await athlete_access.invite_holder(
            db, athlete=athlete, guardian_user_id=current_user.user_id, email=payload.email,
            today=(await lessons_service.club_now(db, club_id=current_user.club_id)).date(),
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return {"sent": link is None, "link": link}


@router.get("/athlete-area/{athlete_id}/months", response_model=SeasonMonthsRead)
async def get_area_months(
    athlete_id: uuid.UUID, current_user: ClubUser = Depends(require_club_permission(ATHLETE)),
    db: AsyncSession = Depends(get_db),
) -> SeasonMonthsRead:
    """Le mensilità dell'atleta mese per mese, in lettura: le paga il titolare."""
    athlete = await _area_athlete(db, current_user, athlete_id)
    today = (await lessons_service.club_now(db, club_id=current_user.club_id)).date()
    return SeasonMonthsRead(**await months_service.season_months(
        db, athlete=athlete, season=seasons.season_of(today), today=today,
    ))


@router.post("/athlete-area/{athlete_id}/attendance", status_code=status.HTTP_204_NO_CONTENT)
async def mark_present(
    athlete_id: uuid.UUID, payload: AreaAttendanceWrite,
    current_user: ClubUser = Depends(require_club_permission(ATHLETE)), db: AsyncSession = Depends(get_db),
) -> None:
    athlete = await _area_athlete(db, current_user, athlete_id)
    try:
        await athlete_access.mark_today(
            db, athlete=athlete, course_id=payload.course_id, present=True, actor_user_id=current_user.user_id,
        )
    except club_service.ClubError as exc:
        _raise(exc)


@router.delete("/athlete-area/{athlete_id}/attendance/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unmark_present(
    athlete_id: uuid.UUID, course_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(ATHLETE)), db: AsyncSession = Depends(get_db),
) -> None:
    athlete = await _area_athlete(db, current_user, athlete_id)
    try:
        await athlete_access.mark_today(
            db, athlete=athlete, course_id=course_id, present=False, actor_user_id=current_user.user_id,
        )
    except club_service.ClubError as exc:
        _raise(exc)


def _certificates(certs, today: date) -> list[CertificateRead]:
    return [
        CertificateRead(
            id=c.id, type=c.type, issued_on=c.issued_on, expires_on=c.expires_on,
            status=club_service.certificate_status(c, today=today), original_filename=c.original_filename,
        )
        for c in certs
    ]


@router.get("/athlete-area/{athlete_id}/certificates", response_model=list[CertificateRead])
async def list_area_certificates(
    athlete_id: uuid.UUID, current_user: ClubUser = Depends(require_club_permission(ATHLETE)),
    db: AsyncSession = Depends(get_db),
) -> list[CertificateRead]:
    athlete = await _area_athlete(db, current_user, athlete_id)
    today = (await lessons_service.club_now(db, club_id=current_user.club_id)).date()
    return _certificates(await club_service.list_certificates(db, athlete_id=athlete.id), today)


@router.post(
    "/athlete-area/{athlete_id}/certificates", response_model=CertificateRead, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("club-certificate", max_requests=20, window_seconds=300))],
)
async def upload_area_certificate(
    athlete_id: uuid.UUID,
    file: UploadFile = File(...),
    type: str = Form(...),
    issued_on: date = Form(...),
    expires_on: date = Form(...),
    current_user: ClubUser = Depends(require_club_permission(ATHLETE)),
    db: AsyncSession = Depends(get_db),
) -> CertificateRead:
    athlete = await _area_athlete(db, current_user, athlete_id)
    today = (await lessons_service.club_now(db, club_id=current_user.club_id)).date()
    # Un minorenne il certificato lo vede, ma lo carica il genitore.
    if athlete.guardian_user_id != current_user.user_id and athlete_access.age_on(athlete.birth_date, today) < athlete_access.ADULT_AGE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Il certificato lo carica il tuo genitore: chiediglielo.")
    try:
        cert = await club_service.upload_certificate(
            db, athlete=athlete, actor_user_id=current_user.user_id, type_=type, issued_on=issued_on,
            expires_on=expires_on, file_bytes=await file.read(), content_type=file.content_type or "",
            original_filename=file.filename or "certificato",
        )
    except club_service.ClubError as exc:
        _raise(exc)
    today = (await lessons_service.club_now(db, club_id=current_user.club_id)).date()
    return _certificates([cert], today)[0]


@router.get("/athlete-area/{athlete_id}/certificates/{certificate_id}/url", response_model=UrlRead)
async def area_certificate_url(
    athlete_id: uuid.UUID, certificate_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(ATHLETE)), db: AsyncSession = Depends(get_db),
) -> UrlRead:
    athlete = await _area_athlete(db, current_user, athlete_id)
    try:
        cert = await club_service.get_certificate(db, scope=current_user.scope, certificate_id=certificate_id)
    except club_service.ClubError as exc:
        _raise(exc)
    if cert.athlete_id != athlete.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Certificato non trovato.")
    return UrlRead(url=club_service.presigned_url(cert.storage_key))


@router.post(
    "/athlete-area/{athlete_id}/payment-proofs", status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("club-payment-proof", max_requests=20, window_seconds=300))],
)
async def upload_area_payment_proof(
    athlete_id: uuid.UUID,
    file: UploadFile | None = File(default=None),
    fee_ids: list[uuid.UUID] = Form(...),
    note: str | None = Form(default=None, max_length=500),
    method: str = Form(default="BANK_TRANSFER", pattern="^(BANK_TRANSFER|MBWAY|CASH)$"),
    cash_received_by_user_id: uuid.UUID | None = Form(default=None),
    cash_received_by_name: str | None = Form(default=None, max_length=120),
    current_user: ClubUser = Depends(require_club_permission(ATHLETE)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """La prova di pagamento delle quote dell'atleta, dalla sua area: il
    titolare, o l'atleta stesso con il suo accesso dai 18 anni di età
    federale. Le stesse regole del genitore (club_service.upload_payment_proof),
    ma solo per le quote di questo atleta e senza il credito del wallet (è del
    titolare)."""
    from app.domains.club.models import ClubFee

    athlete = await _area_athlete(db, current_user, athlete_id)
    today = (await lessons_service.club_now(db, club_id=current_user.club_id)).date()
    is_holder = athlete.guardian_user_id == current_user.user_id
    adult_self = athlete.user_id == current_user.user_id and seasons.federal_age(athlete.birth_date, today.year) >= 18
    if not (is_holder or adult_self):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Le quote le paga il titolare del conto.")
    owners = (await db.execute(select(ClubFee.athlete_id).where(ClubFee.id.in_(fee_ids)))).scalars().all()
    if len(owners) != len(set(fee_ids)) or any(o != athlete.id for o in owners):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quota non trovata.")
    try:
        proof = await club_service.upload_payment_proof(
            db, scope=scope_of(athlete), guardian_user_id=athlete.guardian_user_id, fee_ids=fee_ids,
            file_bytes=await file.read() if file is not None else None,
            content_type=file.content_type if file is not None else None,
            original_filename=(file.filename or "pagamento") if file is not None else None, note=note,
            method=method, cash_received_by_user_id=cash_received_by_user_id,
            cash_received_by_name=cash_received_by_name, uploaded_by_user_id=current_user.user_id,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return {"id": str(proof.id), "receipt_number": proof.receipt_number}


@router.post(
    "/athlete-area/{athlete_id}/photo", status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit("club-athlete-photo", max_requests=20, window_seconds=300))],
)
async def upload_area_photo(
    athlete_id: uuid.UUID, file: UploadFile = File(...),
    current_user: ClubUser = Depends(require_club_permission(ATHLETE)), db: AsyncSession = Depends(get_db),
) -> None:
    """La foto della scheda, come su un social: dall'area dell'atleta (lui
    stesso o il titolare). Stesso servizio della pagina della famiglia."""
    athlete = await _area_athlete(db, current_user, athlete_id)
    try:
        await club_service.set_athlete_photo(
            db, athlete=athlete, file_bytes=await file.read(), content_type=file.content_type or "",
            actor_user_id=current_user.user_id,
        )
    except club_service.ClubError as exc:
        _raise(exc)


class WhiteJudogiWrite(BaseModel):
    white_judogi: bool


@router.put("/athlete-area/{athlete_id}/white-judogi", status_code=status.HTTP_204_NO_CONTENT)
async def set_area_white_judogi(
    athlete_id: uuid.UUID, payload: WhiteJudogiWrite,
    current_user: ClubUser = Depends(require_club_permission(ATHLETE)), db: AsyncSession = Depends(get_db),
) -> None:
    """«Ho il judogi bianco»: dall'area dell'atleta (lui o il titolare)."""
    athlete = await _area_athlete(db, current_user, athlete_id)
    athlete.white_judogi = payload.white_judogi
    await db.commit()


@router.get("/athlete-area/{athlete_id}/competitions")
async def area_competitions(
    athlete_id: uuid.UUID, current_user: ClubUser = Depends(require_club_permission(ATHLETE)), db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Le prove in arrivo del club e della rete, per l'area dell'atleta: con
    l'iscrizione dell'atleta (se c'è) e se le iscrizioni sono aperte, così
    il bottone «Voglio partecipare» appare solo quando serve."""
    from app.domains.club import competitions as competitions_service
    from app.domains.club.schemas import CompetitionRead

    athlete = await _area_athlete(db, current_user, athlete_id)
    scope = scope_of(athlete)
    today = (await lessons_service.club_now(db, club_id=current_user.club_id)).date()
    comps = await competitions_service.list_competitions(db, scope=scope, from_date=today)
    entries = {e.competition_id: e for e in await competitions_service.list_entries(
        db, competition_ids=[c.id for c in comps], athlete_ids=[athlete.id])} if comps else {}
    return [
        {**CompetitionRead.model_validate(c).model_dump(mode="json"),
         "registrations_open": c.status == "OPEN" and c.registration_deadline >= today,
         "entry_status": entries[c.id].status if c.id in entries else None,
         "viewer_is_holder": athlete.guardian_user_id == current_user.user_id}
        for c in comps
    ]


@router.post("/athlete-area/{athlete_id}/competitions/{competition_id}/wish")
async def wish_to_compete(
    athlete_id: uuid.UUID, competition_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(ATHLETE)), db: AsyncSession = Depends(get_db),
) -> dict:
    """«Voglio partecipare»: l'atleta (spesso minorenne, che non si iscrive
    da solo) dice al titolare del conto che vuole andare a una prova. Parte
    un'email e una notifica al titolare con la scadenza delle iscrizioni.
    Una volta sola per atleta e prova."""
    from app.domains.club import competitions as competitions_service
    from app.domains.club import participation

    athlete = await _area_athlete(db, current_user, athlete_id)
    try:
        comp = await competitions_service.get_competition(db, scope=scope_of(athlete), competition_id=competition_id)
    except club_service.ClubError as exc:
        _raise(exc)
    today = (await lessons_service.club_now(db, club_id=current_user.club_id)).date()
    if comp.status != "OPEN" or comp.registration_deadline < today:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Le iscrizioni a questa prova sono chiuse.")
    if await participation.blocking_debts(db, athlete=athlete, today=today, exclude_competition_id=comp.id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, participation.DEBTS_REASON)
    if athlete.guardian_user_id == current_user.user_id:
        return {"sent": False, "already": False, "holder": True}
    sent = await participation.send_wish(db, athlete=athlete, competition=comp)
    return {"sent": sent, "already": not sent, "holder": False}


@router.get("/athlete-area/{athlete_id}/money")
async def area_money(
    athlete_id: uuid.UUID, current_user: ClubUser = Depends(require_club_permission(ATHLETE)), db: AsyncSession = Depends(get_db),
) -> dict:
    """Il wallet della famiglia, l'aiuto del club (i costi pagati per
    l'atleta) e i suoi investimenti (club/support.py)."""
    from app.domains.club import support

    athlete = await _area_athlete(db, current_user, athlete_id)
    return await support.money(db, athlete=athlete)


@router.post("/athlete-area/{athlete_id}/become-holder", status_code=status.HTTP_204_NO_CONTENT)
async def become_holder(
    athlete_id: uuid.UUID, payload: BecomeHolderWrite,
    current_user: ClubUser = Depends(require_club_permission(ATHLETE)), db: AsyncSession = Depends(get_db),
) -> None:
    athlete = await _area_athlete(db, current_user, athlete_id)
    today = (await lessons_service.club_now(db, club_id=current_user.club_id)).date()
    try:
        await athlete_access.become_holder(
            db, athlete=athlete, user_id=current_user.user_id, email=payload.email, today=today,
        )
    except club_service.ClubError as exc:
        _raise(exc)
