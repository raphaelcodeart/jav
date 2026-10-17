"""Le API del club, in tre gruppi per chi le usa:

- `/club/...`        il genitore (`club.family`), solo sulla propria famiglia;
- `/club/admin/...`  la segreteria (`club.manage`), su tutto il club;
- `/club/staff/...`  istruttori e segreteria (`club.instruct`): corsi,
  presenze, cinture. Un istruttore senza `club.manage` vede solo i suoi corsi;
- `/clubs/...`       il superadmin: crea i club e ci entra.

Ognuna lavora su un club solo, quello che le dà club/scope.py.

Il controllo "è di questa famiglia" lo fa il servizio (get_owned_athlete),
non il router: è il servizio ad avere l'atleta in mano.
"""

import uuid
from datetime import date
from html import escape

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db, utcnow
from app.core.deps import CurrentUser, get_current_user, require_permission
from app.core.rate_limit import rate_limit
from app.domains.club import absence as absence_service
from app.domains.club import achievements as achievements_catalog
from app.domains.club import belts as belts_catalog
from app.domains.club import clubs as clubs_service
from app.domains.club import competitions as competitions_service
from app.domains.club import participation as participation_service
from app.domains.club import courses as courses_service
from app.domains.club import family as family_service
from app.domains.club import jav_courses as jav_courses_service
from app.domains.club import lessons as lessons_service
from app.domains.club import months as months_service
from app.domains.club import people as people_service
from app.domains.club import referrals as referrals_service
from app.domains.club import school_letters as school_letters_service
from app.domains.club import seasons
from app.domains.club import service as club_service
from app.domains.club import transport as transport_service
from app.domains.club import workclock as workclock_service
from app.domains.club.accounting_schemas import CoachEarningsRead, CoursesReportRead
from app.domains.club.models import ClubAthlete, ClubCompetitionEntry, ClubCourseAthlete, ClubFee
from app.domains.club.schemas import (
    AbsenceRowRead,
    AbsenceWrite,
    AdminAthleteRead,
    AdminCertificateRead,
    AdminProofRead,
    AgeBandRead,
    AthleteAdminUpdate,
    AthleteCardRead,
    AthleteCreate,
    AthleteDetailRead,
    AthleteEligibilityRead,
    AthleteUpdate,
    AttendanceWrite,
    BeltAward,
    BeltHistoryRead,
    BeltRead,
    CashReceiverRead,
    CertificateRead,
    ClockRead,
    ClockWrite,
    ClubConfigRead,
    ClubCreate,
    ClubRead,
    ClubSettingsRead,
    ClubSettingsWrite,
    ClubShopOrderRead,
    ClubStaffRead,
    StaffAccessLinkRead,
    ClubStaffWrite,
    ClubUpdate,
    CompetitionRead,
    CompetitionUpdate,
    CompetitionWrite,
    CourseCoachExclusionsWrite,
    CourseRead,
    CourseStaffWrite,
    CourseUpdate,
    CourseWrite,
    CreditCodeRequest,
    CurrentClubRead,
    DayAttendanceRead,
    EnrolWrite,
    EntryCreate,
    EntryRead,
    FamilyAttendanceWrite,
    FamilyCompetitionRead,
    FamilyLessonRead,
    FamilyRead,
    FeeBlockingWrite,
    FeeRead,
    FunctionWrite,
    InvestmentWrite,
    InviteRead,
    JobResultRead,
    LessonRead,
    MarkPaidWrite,
    MonthBoardRead,
    MoveResultRead,
    MoveTargetRead,
    MoveToClubWrite,
    PersonCardRead,
    PersonKindsRead,
    PersonRead,
    PlanRead,
    PlanUpdate,
    PlanWrite,
    PricingRead,
    PricingWrite,
    ProofRead,
    PublicClubRead,
    RankingRead,
    ReasonWrite,
    RefereeWrite,
    SupportWrite,
    ResultsWrite,
    RosterRead,
    SchoolLetterRead,
    SchoolLetterWrite,
    SeasonMonthsRead,
    SlotRead,
    SlotWrite,
    StaffHoursRead,
    TransportRequestRead,
    TransportRequestWrite,
    UrlRead,
    WorkSessionRead,
    WorkSessionUpdate,
)
from app.domains.club.scope import (
    CLUB_HEADER,
    CLUBS_ENTER,
    CLUBS_MANAGE,
    ClubScope,
    ClubUser,
    require_club_permission,
    resolve_club,
)
from app.domains.rbac.service import get_permission_codes_for_user
from app.domains.users.models import User

router = APIRouter(prefix="/club", tags=["club"])
admin_router = APIRouter(prefix="/club/admin", tags=["club-admin"])
staff_router = APIRouter(prefix="/club/staff", tags=["club-staff"])
#: I club della piattaforma: il superadmin li crea e ci entra.
clubs_router = APIRouter(prefix="/clubs", tags=["clubs"])

FAMILY = "club.family"
MANAGE = "club.manage"
INSTRUCT = "club.instruct"


def _raise(exc: club_service.ClubError) -> None:
    code = status.HTTP_404_NOT_FOUND if isinstance(exc, club_service.ClubNotFoundError) else status.HTTP_400_BAD_REQUEST
    raise HTTPException(code, str(exc)) from exc


def _today() -> date:
    return utcnow().date()


#: Perché una prova non ha un file da aprire.
_NO_RECEIPT = {
    False: "Pagamento fatto con il credito del wallet: non c'è una ricevuta.",
    True: "Pagamento in contanti: non c'è una ricevuta da aprire.",
}


# --- Configurazione (tutti) -----------------------------------------------------------------------


@router.get("/config", response_model=ClubConfigRead)
async def get_config(current_user: CurrentUser = Depends(require_permission(FAMILY))) -> ClubConfigRead:
    return _config()


def _config() -> ClubConfigRead:
    season = seasons.season_of(_today())
    return ClubConfigRead(
        season=season,
        season_label=seasons.season_label(season),
        belts=[BeltRead(**family_service.belt_dict(b.code)) for b in belts_catalog.BELTS],
        age_bands=[AgeBandRead(code=b.code, label=b.label, min_age=b.min_age, max_age=b.max_age)
                   for b in competitions_service.AGE_BANDS],
        placement_labels={str(k): v for k, v in competitions_service.PLACEMENT_LABELS.items()},
        level_points={k: list(v) for k, v in competitions_service.LEVEL_POINTS.items()},
        level_labels=competitions_service.LEVEL_LABELS,
        achievements=[
            {"code": a.code, "label": a.label, "description": a.description, "target": a.target}
            for a in achievements_catalog.ACHIEVEMENTS
        ],
        weekdays=list(courses_service.WEEKDAY_LABELS),
    )


@staff_router.get("/config", response_model=ClubConfigRead)
async def get_staff_config(current_user: CurrentUser = Depends(require_permission(INSTRUCT))) -> ClubConfigRead:
    return _config()


# --- Famiglia -------------------------------------------------------------------------------------


@router.get("/family", response_model=FamilyRead)
async def get_family(
    current_user: ClubUser = Depends(require_club_permission(FAMILY)), db: AsyncSession = Depends(get_db)
) -> FamilyRead:
    return FamilyRead(**await family_service.family_summary(
        db, scope=current_user.scope, guardian_user_id=current_user.user_id
    ))


@router.get("/athletes", response_model=list[AthleteCardRead])
async def list_my_athletes(
    current_user: ClubUser = Depends(require_club_permission(FAMILY)), db: AsyncSession = Depends(get_db)
) -> list[AthleteCardRead]:
    athletes = await club_service.list_family_athletes(
        db, scope=current_user.scope, guardian_user_id=current_user.user_id
    )
    return [AthleteCardRead(**c) for c in await family_service.athlete_cards(db, athletes=athletes)]


@router.post("/athletes", response_model=AthleteDetailRead, status_code=status.HTTP_201_CREATED)
async def create_my_athlete(
    payload: AthleteCreate,
    current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> AthleteDetailRead:
    try:
        athlete = await club_service.create_athlete(
            db, scope=current_user.scope, guardian_user_id=current_user.user_id,
            actor_user_id=current_user.user_id, **payload.model_dump(),
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return AthleteDetailRead(**await family_service.athlete_detail(db, athlete=athlete))


async def _my_athlete(db: AsyncSession, current_user: ClubUser, athlete_id: uuid.UUID) -> ClubAthlete:
    try:
        return await club_service.get_owned_athlete(
            db, scope=current_user.scope, guardian_user_id=current_user.user_id,
            athlete_id=athlete_id,
        )
    except club_service.ClubError as exc:
        _raise(exc)


@router.get("/athletes/{athlete_id}", response_model=AthleteDetailRead)
async def get_my_athlete(
    athlete_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> AthleteDetailRead:
    athlete = await _my_athlete(db, current_user, athlete_id)
    return AthleteDetailRead(**await family_service.athlete_detail(db, athlete=athlete))


@router.get("/athletes/{athlete_id}/months", response_model=SeasonMonthsRead)
async def get_my_athlete_months(
    athlete_id: uuid.UUID,
    season: int | None = Query(default=None, ge=2000, le=2100),
    current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> SeasonMonthsRead:
    """Le mensilità dell'atleta mese per mese (club/months.py)."""
    athlete = await _my_athlete(db, current_user, athlete_id)
    today = _today()
    return SeasonMonthsRead(**await months_service.season_months(
        db, athlete=athlete, season=season or seasons.season_of(today), today=today,
    ))


@router.get("/cash-receivers", response_model=list[CashReceiverRead])
async def list_cash_receivers(
    current_user: ClubUser = Depends(require_club_permission("club.athlete")), db: AsyncSession = Depends(get_db)
) -> list[CashReceiverRead]:
    """A chi del club si possono dare i contanti: lo sceglie il genitore (o
    l'atleta maggiorenne) quando dice di aver pagato così. `club.athlete`
    ce l'hanno sia le famiglie sia gli atleti."""
    return [CashReceiverRead(**r) for r in await club_service.cash_receivers(db, scope=current_user.scope)]


@router.patch("/athletes/{athlete_id}", response_model=AthleteDetailRead)
async def update_my_athlete(
    athlete_id: uuid.UUID,
    payload: AthleteUpdate,
    current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> AthleteDetailRead:
    athlete = await _my_athlete(db, current_user, athlete_id)
    try:
        athlete = await club_service.update_athlete(
            db, athlete=athlete, actor_user_id=current_user.user_id,
            changes=payload.model_dump(exclude_unset=True), as_admin=False,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return AthleteDetailRead(**await family_service.athlete_detail(db, athlete=athlete))


@router.post(
    "/athletes/{athlete_id}/photo", response_model=AthleteDetailRead,
    dependencies=[Depends(rate_limit("club-athlete-photo", max_requests=20, window_seconds=300))],
)
async def upload_my_athlete_photo(
    athlete_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> AthleteDetailRead:
    athlete = await _my_athlete(db, current_user, athlete_id)
    try:
        athlete = await club_service.set_athlete_photo(
            db, athlete=athlete, file_bytes=await file.read(), content_type=file.content_type or "",
            actor_user_id=current_user.user_id,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return AthleteDetailRead(**await family_service.athlete_detail(db, athlete=athlete))


@router.get("/fees/mine", response_model=list[FeeRead])
async def list_my_fees(
    status_filter: str | None = Query(default=None, alias="status"),
    current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> list[FeeRead]:
    athletes = await club_service.list_family_athletes(
        db, scope=current_user.scope, guardian_user_id=current_user.user_id, include_left=True
    )
    by_id = {a.id: a for a in athletes}
    fees = await club_service.list_fees(
        db, scope=current_user.scope, athlete_ids=list(by_id), guardian_user_id=current_user.user_id,
        status=status_filter,
    )
    today = _today()
    return [
        FeeRead(**family_service.fee_dict(f, today=today, athlete=by_id.get(f.athlete_id)))
        for f in reversed(fees)
    ]


@router.post(
    "/payment-proofs", response_model=ProofRead, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("club-payment-proof", max_requests=20, window_seconds=300))],
)
async def upload_my_payment_proof(
    file: UploadFile | None = File(default=None),
    fee_ids: list[uuid.UUID] = Form(...),
    note: str | None = Form(default=None, max_length=500),
    credit_cents: int = Form(default=0, ge=0),
    spend_code: str | None = Form(default=None, max_length=12),
    method: str = Form(default="BANK_TRANSFER", pattern="^(BANK_TRANSFER|MBWAY|CASH)$"),
    cash_received_by_user_id: uuid.UUID | None = Form(default=None),
    cash_received_by_name: str | None = Form(default=None, max_length=120),
    current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> ProofRead:
    """La foto del pagamento: le quote indicate risultano pagate subito
    (docs/club-portal.md, regola di autogestione). `credit_cents` è la parte
    pagata con il credito del wallet, confermata con `spend_code`; se copre
    tutto, la foto non serve. Con `method=CASH` niente foto: si dice a chi
    sono stati dati i contanti."""
    try:
        proof = await club_service.upload_payment_proof(
            db, scope=current_user.scope, guardian_user_id=current_user.user_id,
            fee_ids=fee_ids, file_bytes=await file.read() if file is not None else None,
            content_type=file.content_type if file is not None else None,
            original_filename=(file.filename or "pagamento") if file is not None else None, note=note,
            credit_cents=credit_cents, spend_code=spend_code, method=method,
            cash_received_by_user_id=cash_received_by_user_id, cash_received_by_name=cash_received_by_name,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    fees = (await club_service.fees_by_proof(db, proof_ids=[proof.id]))[proof.id]
    return ProofRead(**family_service.proof_dict(proof, fees=fees, today=_today()))


@router.post(
    "/payment-proofs/request-credit-code", status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit("club-credit-code", max_requests=5, window_seconds=300))],
)
async def request_credit_code(
    payload: CreditCodeRequest,
    via: str | None = None,
    current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Il codice (o il PIN) che conferma l'uso del credito del wallet per le
    quote: lo stesso passo di ogni spesa di JavCash."""
    from app.domains.auth import service as auth_service

    user = await db.get(User, current_user.user_id)
    club = await clubs_service.get_club(db, organization_id=current_user.organization_id, club_id=current_user.club_id)
    method = await auth_service.request_spend_code(
        db, user=user, via_email=via == "email",
        context_line=(
            f"Stai per usare <strong>{payload.credit_cents / 100:.2f} €</strong> del tuo credito per pagare "
            f"quote di {escape(club.name)}. Usa questo codice per confermare."
        ),
    )
    return {"ok": True, "method": method}


@router.get("/invite", response_model=InviteRead)
async def get_my_invite(
    current_user: ClubUser = Depends(require_club_permission("club.athlete")), db: AsyncSession = Depends(get_db)
) -> InviteRead:
    """Il link personale per invitare un amico nel club (club/referrals.py):
    della famiglia, o dell'atleta con il suo accesso (il credito va al suo wallet)."""
    club = await clubs_service.get_club(db, organization_id=current_user.organization_id, club_id=current_user.club_id)
    info = await referrals_service.invite_link(
        db, organization_id=current_user.organization_id, club=club, user_id=current_user.user_id
    )
    await db.commit()
    return InviteRead(**info)


@router.get("/pricing", response_model=PricingRead)
async def get_family_pricing(
    current_user: ClubUser = Depends(require_club_permission(FAMILY)), db: AsyncSession = Depends(get_db)
) -> PricingRead:
    """Cosa comprende l'iscrizione e quanto vale un invito: le famiglie lo
    leggono prima di pagare."""
    return PricingRead(**await club_service.club_pricing(db, club_id=current_user.club_id))


@router.get("/payment-proofs/mine", response_model=list[ProofRead])
async def list_my_payment_proofs(
    current_user: ClubUser = Depends(require_club_permission(FAMILY)), db: AsyncSession = Depends(get_db)
) -> list[ProofRead]:
    proofs = await club_service.list_proofs(
        db, scope=current_user.scope, uploaded_by_user_id=current_user.user_id
    )
    fees = await club_service.fees_by_proof(db, proof_ids=[p.id for p in proofs])
    today = _today()
    return [ProofRead(**family_service.proof_dict(p, fees=fees[p.id], today=today)) for p in proofs]


@router.get("/payment-proofs/{proof_id}/url", response_model=UrlRead)
async def get_my_payment_proof_url(
    proof_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> UrlRead:
    try:
        proof = await club_service.get_proof(db, scope=current_user.scope, proof_id=proof_id)
    except club_service.ClubError as exc:
        _raise(exc)
    if proof.uploaded_by_user_id != current_user.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Prova di pagamento non trovata.")
    if proof.storage_key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NO_RECEIPT[proof.method == "CASH"])
    return UrlRead(url=club_service.presigned_url(proof.storage_key))


@router.get("/athletes/{athlete_id}/certificates", response_model=list[CertificateRead])
async def list_my_athlete_certificates(
    athlete_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> list[CertificateRead]:
    athlete = await _my_athlete(db, current_user, athlete_id)
    return _certificates_read(await club_service.list_certificates(db, athlete_id=athlete.id))


def _certificates_read(certs) -> list[CertificateRead]:
    today = _today()
    return [
        CertificateRead(
            id=c.id, type=c.type, issued_on=c.issued_on, expires_on=c.expires_on,
            status=club_service.certificate_status(c, today=today), original_filename=c.original_filename,
        )
        for c in certs
    ]


@router.post(
    "/athletes/{athlete_id}/certificates", response_model=CertificateRead, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("club-certificate", max_requests=20, window_seconds=300))],
)
async def upload_my_athlete_certificate(
    athlete_id: uuid.UUID,
    file: UploadFile = File(...),
    type: str = Form(...),
    issued_on: date = Form(...),
    expires_on: date = Form(...),
    current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> CertificateRead:
    athlete = await _my_athlete(db, current_user, athlete_id)
    return await _upload_certificate(db, current_user, athlete, file, type, issued_on, expires_on)


async def _upload_certificate(db, current_user, athlete, file, type_, issued_on, expires_on) -> CertificateRead:
    try:
        cert = await club_service.upload_certificate(
            db, athlete=athlete, actor_user_id=current_user.user_id, type_=type_, issued_on=issued_on,
            expires_on=expires_on, file_bytes=await file.read(), content_type=file.content_type or "",
            original_filename=file.filename or "certificato",
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return _certificates_read([cert])[0]


@router.get("/certificates/{certificate_id}/url", response_model=UrlRead)
async def get_my_certificate_url(
    certificate_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> UrlRead:
    try:
        cert = await club_service.get_certificate(
            db, scope=current_user.scope, certificate_id=certificate_id
        )
    except club_service.ClubError as exc:
        _raise(exc)
    await _my_athlete(db, current_user, cert.athlete_id)
    return UrlRead(url=club_service.presigned_url(cert.storage_key))


@router.get("/competitions", response_model=list[FamilyCompetitionRead])
async def list_family_competitions(
    include_past: bool = False,
    current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> list[FamilyCompetitionRead]:
    """Le gare, con per ogni atleta della famiglia se può iscriversi e
    perché no: il form non deve mai offrire un'iscrizione che fallirà."""
    today = _today()
    comps = await competitions_service.list_competitions(
        db, scope=current_user.scope, from_date=None if include_past else today
    )
    athletes = await club_service.list_family_athletes(
        db, scope=current_user.scope, guardian_user_id=current_user.user_id
    )
    entries = await competitions_service.list_entries(
        db, competition_ids=[c.id for c in comps], athlete_ids=[a.id for a in athletes]
    ) if comps and athletes else []
    by_key = {(e.competition_id, e.athlete_id): e for e in entries}
    letters = await school_letters_service.letters_by_entry(db, entry_ids=[e.id for e in entries])
    out = []
    for comp in comps:
        rows = []
        for athlete in athletes:
            entry = by_key.get((comp.id, athlete.id))
            ok, reason = await competitions_service.eligibility(db, competition=comp, athlete=athlete, today=today)
            if entry is not None and entry.status == "REGISTERED":
                ok, reason = False, None
            rows.append(AthleteEligibilityRead(
                athlete_id=athlete.id, first_name=athlete.first_name, eligible=ok, reason=reason,
                entry_status=entry.status if entry else None, category=entry.category if entry else None,
                placement=entry.placement if entry else None,
                school_letter_ready=entry is not None and entry.status == "REGISTERED" and entry.id in letters,
                blocked_by_debts=reason == participation_service.DEBTS_REASON,
            ))
        out.append(FamilyCompetitionRead(
            **CompetitionRead.model_validate(comp).model_dump(),
            registrations_open=comp.status == "OPEN" and today <= comp.registration_deadline,
            athletes=rows,
        ))
    return out


async def _entry_read(
    db: AsyncSession, entry: ClubCompetitionEntry, athlete: ClubAthlete, comp, letters: dict | None = None,
) -> EntryRead:
    fee = (
        await db.execute(
            select(ClubFee.status).where(
                ClubFee.athlete_id == athlete.id, ClubFee.kind == "COMPETITION", ClubFee.period == str(comp.id)
            )
        )
    ).scalar_one_or_none()
    return EntryRead(
        id=entry.id, competition_id=entry.competition_id, athlete_id=athlete.id,
        athlete_name=f"{athlete.first_name} {athlete.last_name}", category=entry.category,
        weight_kg=entry.weight_kg, status=entry.status, placement=entry.placement,
        points=competitions_service.points_for(placement=entry.placement, level=comp.level)
        if entry.status == "REGISTERED" else 0,
        fee_status=fee,
        school_letter_at=letters[entry.id].generated_at if letters and entry.id in letters else None,
    )


@router.post("/competitions/{competition_id}/entries", response_model=EntryRead, status_code=status.HTTP_201_CREATED)
async def register_my_athlete(
    competition_id: uuid.UUID,
    payload: EntryCreate,
    current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> EntryRead:
    athlete = await _my_athlete(db, current_user, payload.athlete_id)
    try:
        comp = await competitions_service.get_competition(
            db, scope=current_user.scope, competition_id=competition_id
        )
        entry = await competitions_service.register_entry(
            db, competition=comp, athlete=athlete, actor_user_id=current_user.user_id,
            category=payload.category, weight_kg=payload.weight_kg,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return await _entry_read(db, entry, athlete, comp)


@router.delete("/competitions/{competition_id}/entries/{athlete_id}", response_model=EntryRead)
async def withdraw_my_athlete(
    competition_id: uuid.UUID,
    athlete_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> EntryRead:
    athlete = await _my_athlete(db, current_user, athlete_id)
    try:
        comp = await competitions_service.get_competition(
            db, scope=current_user.scope, competition_id=competition_id
        )
        entry = await competitions_service.withdraw_entry(
            db, competition=comp, athlete=athlete, actor_user_id=current_user.user_id
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return await _entry_read(db, entry, athlete, comp)


@router.get("/competitions/{competition_id}/entries/{athlete_id}/school-letter/url", response_model=UrlRead)
async def my_school_letter_url(
    competition_id: uuid.UUID,
    athlete_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> UrlRead:
    """La giustificazione per la scuola che la segreteria ha generato: il
    titolare la scarica e la porta a scuola."""
    athlete = await _my_athlete(db, current_user, athlete_id)
    entry = (
        await db.execute(
            select(ClubCompetitionEntry).where(
                ClubCompetitionEntry.competition_id == competition_id, ClubCompetitionEntry.athlete_id == athlete.id,
                ClubCompetitionEntry.status == "REGISTERED",
            )
        )
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Iscrizione non trovata.")
    try:
        letter = await school_letters_service.letter_for(
            db, scope=current_user.scope, competition_id=competition_id, entry_id=entry.id
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return UrlRead(url=club_service.presigned_url(letter.storage_key))


@router.get("/ranking", response_model=RankingRead)
async def get_ranking(
    season: int | None = None,
    sex: str | None = Query(default=None, pattern="^[MF]$"),
    age_band: str | None = None,
    club_only: bool = False,
    current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> RankingRead:
    season = season if season is not None else competitions_service.ranking_year(_today())
    try:
        rows = await competitions_service.ranking(
            db, scope=current_user.scope, season=season, sex=sex, age_band=age_band,
            viewer_user_id=current_user.user_id, club_only=club_only,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return RankingRead(season=season, season_label=competitions_service.ranking_label(season), sex=sex,
                       age_band=age_band, rows=rows)


@router.get("/athletes/{athlete_id}/belts", response_model=list[BeltHistoryRead])
async def list_my_athlete_belts(
    athlete_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> list[BeltHistoryRead]:
    athlete = await _my_athlete(db, current_user, athlete_id)
    return _belts_read(await club_service.belt_history(db, athlete_id=athlete.id))


def _belts_read(history) -> list[BeltHistoryRead]:
    return [
        BeltHistoryRead(id=g.id, **family_service.belt_dict(g.grade), awarded_on=g.awarded_on, note=g.note)
        for g in history
    ]


async def _courses_read(
    db: AsyncSession, courses, *, my_athlete_ids: set[uuid.UUID] | None = None,
    mine_ids: set[uuid.UUID] | None = None, with_staff: bool = False,
) -> list[CourseRead]:
    ids = [c.id for c in courses]
    staff = await courses_service.staff_ids_by_course(db, course_ids=ids) if with_staff else {}
    excluded = await courses_service.coach_exclusions_by_course(db, course_ids=ids) if with_staff else {}
    slots = await courses_service.slots_by_course(db, course_ids=ids)
    enrolled = await courses_service.enrolled_athlete_ids(db, course_ids=ids)
    instructor_ids = {c.instructor_user_id for c in courses if c.instructor_user_id}
    # Gli account dello staff non hanno un nome anagrafico: si mostra l'email.
    names = dict(
        (await db.execute(select(User.id, User.email).where(User.id.in_(instructor_ids)))).all()
    ) if instructor_ids else {}
    return [
        CourseRead(
            id=c.id, name=c.name, description=c.description, level=c.level, min_age=c.min_age, max_age=c.max_age,
            instructor_user_id=c.instructor_user_id, instructor_name=names.get(c.instructor_user_id),
            active=c.active, slots=[SlotRead.model_validate(s) for s in slots[c.id]],
            athletes_count=len(enrolled[c.id]),
            my_athlete_ids=sorted(enrolled[c.id] & my_athlete_ids, key=str) if my_athlete_ids is not None else [],
            mine=c.id in mine_ids if mine_ids is not None else False,
            staff_user_ids=staff.get(c.id, []), excluded_coach_ids=excluded.get(c.id, []),
            venue_name=c.venue_name, venue_address=c.venue_address, venue_city=c.venue_city,
            public_description=c.public_description, public_coach_name=c.public_coach_name,
            coach_share_pct=c.coach_share_pct, published=c.published,
        )
        for c in courses
    ]


@router.get("/courses", response_model=list[CourseRead])
async def list_family_courses(
    current_user: ClubUser = Depends(require_club_permission(FAMILY)), db: AsyncSession = Depends(get_db)
) -> list[CourseRead]:
    """L'orario dei corsi attivi, con quali atleti della famiglia ci vanno."""
    athletes = await club_service.list_family_athletes(
        db, scope=current_user.scope, guardian_user_id=current_user.user_id
    )
    courses = await courses_service.list_courses(db, scope=current_user.scope)
    return await _courses_read(db, courses, my_athlete_ids={a.id for a in athletes})


@router.post("/courses/{course_id}/athletes", status_code=status.HTTP_204_NO_CONTENT)
async def enrol_my_athlete(
    course_id: uuid.UUID,
    payload: EnrolWrite,
    current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> None:
    athlete = await _my_athlete(db, current_user, payload.athlete_id)
    try:
        course = await courses_service.get_course(db, scope=current_user.scope, course_id=course_id)
        await courses_service.enrol(db, course=course, athlete=athlete, actor_user_id=current_user.user_id)
    except club_service.ClubError as exc:
        _raise(exc)


@router.delete("/courses/{course_id}/athletes/{athlete_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unenrol_my_athlete(
    course_id: uuid.UUID,
    athlete_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> None:
    athlete = await _my_athlete(db, current_user, athlete_id)
    try:
        course = await courses_service.get_course(db, scope=current_user.scope, course_id=course_id)
        await courses_service.unenrol(db, course=course, athlete=athlete, actor_user_id=current_user.user_id)
    except club_service.ClubError as exc:
        _raise(exc)


# --- Segreteria -----------------------------------------------------------------------------------


@admin_router.get("/plans", response_model=list[PlanRead])
async def admin_list_plans(
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db)
) -> list[PlanRead]:
    plans = await club_service.list_plans(db, scope=current_user.scope)
    counts = dict(
        (
            await db.execute(
                select(ClubAthlete.plan_id, func.count())
                .where(ClubAthlete.club_id == current_user.scope.club_id, ClubAthlete.status == "ACTIVE")
                .group_by(ClubAthlete.plan_id)
            )
        ).all()
    )
    return [PlanRead.model_validate(p).model_copy(update={"athletes_count": counts.get(p.id, 0)}) for p in plans]


@admin_router.post("/plans", response_model=PlanRead, status_code=status.HTTP_201_CREATED)
async def admin_create_plan(
    payload: PlanWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> PlanRead:
    try:
        plan = await club_service.create_plan(
            db, scope=current_user.scope, actor_user_id=current_user.user_id,
            data=payload.model_dump(),
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return PlanRead.model_validate(plan)


@admin_router.patch("/plans/{plan_id}", response_model=PlanRead)
async def admin_update_plan(
    plan_id: uuid.UUID,
    payload: PlanUpdate,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> PlanRead:
    try:
        plan = await club_service.update_plan(
            db, scope=current_user.scope, plan_id=plan_id, actor_user_id=current_user.user_id,
            changes=payload.model_dump(exclude_unset=True),
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return PlanRead.model_validate(plan)


@admin_router.delete("/plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_plan(
    plan_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await club_service.delete_plan(
            db, scope=current_user.scope, plan_id=plan_id, actor_user_id=current_user.user_id
        )
    except club_service.ClubError as exc:
        _raise(exc)


async def _admin_athletes_read(db: AsyncSession, athletes: list[ClubAthlete]) -> list[AdminAthleteRead]:
    cards = await family_service.athlete_cards(db, athletes=athletes)
    extra = await _athlete_registry(db, athletes)
    by_id = {a.id: a for a in athletes}
    return [AdminAthleteRead(**c, member_number=by_id[c["id"]].member_number, **extra[c["id"]]) for c in cards]


async def _athlete_registry(db: AsyncSession, athletes: list[ClubAthlete]) -> dict[uuid.UUID, dict]:
    """Le colonne d'anagrafe della tabella atleti, in poche query per tutti:
    l'encarregado (nome, email, telefono) e chi ha portato l'atleta nel
    club (referrals.py: il link «Invita un amico» del titolare; altrimenti il
    nome scritto nel modulo d'iscrizione)."""
    from app.domains.club.people import _names
    from app.domains.club.records_models import ClubApplication
    from app.domains.club.referrals import SOURCE_CLUB_LINK
    from app.domains.customers.models import Customer
    from app.domains.friend_referrals.models import FriendReferral

    if not athletes:
        return {}
    guardian_ids = {a.guardian_user_id for a in athletes}
    emails = dict((await db.execute(select(User.id, User.email).where(User.id.in_(guardian_ids)))).all())
    phones = dict(
        (await db.execute(select(Customer.user_id, Customer.phone).where(Customer.user_id.in_(guardian_ids)))).all()
    )
    referrers = dict(
        (
            await db.execute(
                select(Customer.user_id, FriendReferral.referrer_user_id)
                .join(FriendReferral, FriendReferral.referred_customer_id == Customer.id)
                .where(Customer.user_id.in_(guardian_ids), FriendReferral.source == SOURCE_CLUB_LINK)
                .order_by(FriendReferral.created_at)
            )
        ).all()
    )
    written = dict(
        (
            await db.execute(
                select(ClubApplication.athlete_id, ClubApplication.referred_by).where(
                    ClubApplication.athlete_id.in_({a.id for a in athletes}),
                    ClubApplication.referred_by.is_not(None),
                )
            )
        ).all()
    )
    names = await _names(db, guardian_ids | set(referrers.values()))
    out: dict[uuid.UUID, dict] = {}
    for a in athletes:
        referrer = referrers.get(a.guardian_user_id)
        if referrer is not None:
            invited = {"kind": "PERSON", "name": names.get(referrer) or "—", "user_id": referrer}
        elif (written.get(a.id) or "").strip():
            invited = {"kind": "WRITTEN", "name": written[a.id].strip()}
        else:
            invited = None
        out[a.id] = {
            "guardian_user_id": a.guardian_user_id,
            "guardian_email": emails.get(a.guardian_user_id),
            "guardian_name": names.get(a.guardian_user_id),
            "guardian_phone": phones.get(a.guardian_user_id),
            "invited_by": invited,
        }
    return out


@admin_router.get("/athletes", response_model=list[AdminAthleteRead])
async def admin_list_athletes(
    status_filter: str | None = Query(default=None, alias="status"),
    plan_id: uuid.UUID | None = None,
    q: str | None = None,
    course_id: uuid.UUID | None = None,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[AdminAthleteRead]:
    athletes = await club_service.search_athletes(
        db, scope=current_user.scope, status=status_filter, plan_id=plan_id, q=q, course_id=course_id,
    )
    return await _admin_athletes_read(db, athletes)


@admin_router.get("/athletes/{athlete_id}", response_model=AthleteDetailRead)
async def admin_get_athlete(
    athlete_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> AthleteDetailRead:
    try:
        athlete = await club_service.get_athlete(db, scope=current_user.scope, athlete_id=athlete_id)
    except club_service.ClubError as exc:
        _raise(exc)
    return AthleteDetailRead(**await family_service.athlete_detail(db, athlete=athlete))


@admin_router.patch("/athletes/{athlete_id}", response_model=AthleteDetailRead)
async def admin_update_athlete(
    athlete_id: uuid.UUID,
    payload: AthleteAdminUpdate,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> AthleteDetailRead:
    try:
        athlete = await club_service.get_athlete(db, scope=current_user.scope, athlete_id=athlete_id)
        athlete = await club_service.update_athlete(
            db, athlete=athlete, actor_user_id=current_user.user_id,
            changes=payload.model_dump(exclude_unset=True), as_admin=True,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return AthleteDetailRead(**await family_service.athlete_detail(db, athlete=athlete))


@admin_router.post(
    "/athletes/{athlete_id}/certificates", response_model=CertificateRead, status_code=status.HTTP_201_CREATED
)
async def admin_upload_certificate(
    athlete_id: uuid.UUID,
    file: UploadFile = File(...),
    type: str = Form(...),
    issued_on: date = Form(...),
    expires_on: date = Form(...),
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> CertificateRead:
    try:
        athlete = await club_service.get_athlete(db, scope=current_user.scope, athlete_id=athlete_id)
    except club_service.ClubError as exc:
        _raise(exc)
    return await _upload_certificate(db, current_user, athlete, file, type, issued_on, expires_on)


@admin_router.get("/certificates/{certificate_id}/url", response_model=UrlRead)
async def admin_get_certificate_url(
    certificate_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> UrlRead:
    try:
        cert = await club_service.get_certificate(
            db, scope=current_user.scope, certificate_id=certificate_id
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return UrlRead(url=club_service.presigned_url(cert.storage_key))


@admin_router.get("/certificates", response_model=list[AdminCertificateRead])
async def admin_list_certificates(
    status_filter: str | None = Query(default=None, alias="status"),
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[AdminCertificateRead]:
    """Lo stato del certificato di ogni atleta attivo, filtrabile
    (MISSING / VALID / EXPIRING / EXPIRED)."""
    today = _today()
    athletes = await club_service.search_athletes(db, scope=current_user.scope, status="ACTIVE")
    certs = await club_service.latest_certificates(db, athlete_ids=[a.id for a in athletes])
    emails = dict(
        (await db.execute(select(User.id, User.email).where(User.id.in_({a.guardian_user_id for a in athletes})))).all()
    ) if athletes else {}
    rows = []
    for athlete in athletes:
        cert = family_service.certificate_dict(certs.get(athlete.id), today=today)
        if status_filter and cert["status"] != status_filter:
            continue
        rows.append(AdminCertificateRead(
            athlete_id=athlete.id, athlete_name=f"{athlete.first_name} {athlete.last_name}",
            guardian_email=emails.get(athlete.guardian_user_id), certificate=cert,
        ))
    return rows


@admin_router.get("/fees", response_model=list[FeeRead])
async def admin_list_fees(
    status_filter: str | None = Query(default=None, alias="status"),
    kind: str | None = None,
    period: str | None = None,
    athlete_id: uuid.UUID | None = None,
    course: str | None = Query(default=None, max_length=40),
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[FeeRead]:
    """`course`: l'id di un corso JAV, o `none` per le quote senza corso."""
    try:
        course_filter = None if not course else ("none" if course == "none" else uuid.UUID(course))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Corso non valido.") from exc
    fees = await club_service.list_fees(
        db, scope=current_user.scope, athlete_ids=[athlete_id] if athlete_id else None,
        status=status_filter, kind=kind, period=period, course=course_filter,
    )
    athletes = {
        a.id: a
        for a in (await db.execute(select(ClubAthlete).where(ClubAthlete.id.in_({f.athlete_id for f in fees})))).scalars()
    } if fees else {}
    today = _today()
    rows = [family_service.fee_dict(f, today=today, athlete=athletes.get(f.athlete_id)) for f in fees]
    club_service.attach_proofs(rows, await club_service.latest_proofs_of_fees(db, fee_ids=[f.id for f in fees]))
    return [FeeRead(**r) for r in rows]


@admin_router.post("/fees/{fee_id}/waive", response_model=FeeRead)
async def admin_waive_fee(
    fee_id: uuid.UUID,
    payload: ReasonWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> FeeRead:
    try:
        fee = await club_service.waive_fee(
            db, scope=current_user.scope, fee_id=fee_id, actor_user_id=current_user.user_id,
            reason=payload.reason,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return FeeRead(**family_service.fee_dict(fee, today=_today()))


@admin_router.post("/fees/{fee_id}/blocking", response_model=FeeRead)
async def admin_set_fee_blocking(
    fee_id: uuid.UUID,
    payload: FeeBlockingWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> FeeRead:
    """Una quota scaduta blocca l'iscrizione alle gare; la segreteria può
    decidere che questa no (es. il judogi pagato a rate)."""
    try:
        fee = await club_service.set_fee_blocking(
            db, scope=current_user.scope, fee_id=fee_id, actor_user_id=current_user.user_id,
            non_blocking=payload.non_blocking,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return FeeRead(**family_service.fee_dict(fee, today=_today()))


@admin_router.post("/fees/{fee_id}/mark-paid", response_model=FeeRead)
async def admin_mark_fee_paid(
    fee_id: uuid.UUID,
    payload: MarkPaidWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> FeeRead:
    try:
        fee = await club_service.mark_fee_paid(
            db, scope=current_user.scope, fee_id=fee_id, actor_user_id=current_user.user_id,
            note=payload.note, method=payload.method, cash_received_by_user_id=payload.cash_received_by_user_id,
            cash_received_by_name=payload.cash_received_by_name,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return FeeRead(**family_service.fee_dict(fee, today=_today()))


@admin_router.post(
    "/fees/pay", status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("club-staff-payment", max_requests=120, window_seconds=600))],
)
async def admin_record_payment(
    fee_ids: list[uuid.UUID] = Form(...),
    method: str = Form(..., pattern="^(BANK_TRANSFER|MBWAY|CASH|CARD)$"),
    note: str | None = Form(default=None, max_length=500),
    cash_received_by_user_id: uuid.UUID | None = Form(default=None),
    cash_received_by_name: str | None = Form(default=None, max_length=120),
    file: UploadFile | None = File(default=None),
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """«Segna pagato» della segreteria: una o più quote della stessa
    famiglia, come è stata pagata, e (facoltativa) la foto o il PDF della
    prova, anche scattata con il telefono (club_service.staff_record_payment)."""
    try:
        proof = await club_service.staff_record_payment(
            db, scope=current_user.scope, actor_user_id=current_user.user_id, fee_ids=fee_ids, method=method,
            file_bytes=await file.read() if file is not None else None,
            content_type=file.content_type if file is not None else None,
            original_filename=file.filename if file is not None else None, note=note,
            cash_received_by_user_id=cash_received_by_user_id, cash_received_by_name=cash_received_by_name,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return {"id": str(proof.id), "receipt_number": proof.receipt_number, "has_file": proof.storage_key is not None}


@admin_router.get("/cash-receivers", response_model=list[CashReceiverRead])
async def admin_list_cash_receivers(
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db)
) -> list[CashReceiverRead]:
    return [CashReceiverRead(**r) for r in await club_service.cash_receivers(db, scope=current_user.scope)]


@admin_router.get("/athletes/{athlete_id}/months", response_model=SeasonMonthsRead)
async def admin_athlete_months(
    athlete_id: uuid.UUID,
    season: int | None = Query(default=None, ge=2000, le=2100),
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> SeasonMonthsRead:
    try:
        athlete = await club_service.get_athlete(db, scope=current_user.scope, athlete_id=athlete_id)
    except club_service.ClubError as exc:
        _raise(exc)
    today = _today()
    return SeasonMonthsRead(**await months_service.season_months(
        db, athlete=athlete, season=season or seasons.season_of(today), today=today,
    ))


@admin_router.post("/fees/{fee_id}/reopen", response_model=FeeRead)
async def admin_reopen_fee(
    fee_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> FeeRead:
    try:
        fee = await club_service.reopen_fee(
            db, scope=current_user.scope, fee_id=fee_id, actor_user_id=current_user.user_id
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return FeeRead(**family_service.fee_dict(fee, today=_today()))


@admin_router.post("/jobs/generate-monthly-fees", response_model=JobResultRead)
async def admin_generate_monthly_fees(
    period: str | None = None,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> JobResultRead:
    """La stessa funzione del job del 1° del mese. Rilanciarla è innocuo."""
    try:
        created = await club_service.generate_monthly_fees(
            db, scope=current_user.scope, period=period or seasons.period_of(_today()), today=_today(),
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return JobResultRead(created=created)


@admin_router.post("/jobs/new-season", response_model=JobResultRead)
async def admin_start_season(
    season: int | None = None,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> JobResultRead:
    created = await club_service.start_season(
        db, scope=current_user.scope, season=season or seasons.season_of(_today())
    )
    return JobResultRead(created=created)


@admin_router.get("/payment-proofs", response_model=list[AdminProofRead])
async def admin_list_proofs(
    status_filter: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None, max_length=100),
    method: str | None = Query(default=None, pattern="^(BANK_TRANSFER|MBWAY|CASH)$"),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[AdminProofRead]:
    proofs = await club_service.list_proofs(
        db, scope=current_user.scope, status=status_filter, q=q, method=method, date_from=date_from, date_to=date_to,
    )
    fees = await club_service.fees_by_proof(db, proof_ids=[p.id for p in proofs])
    # Anche le quote riaperte da un rifiuto restano legate alla prova:
    # la segreteria vede che cosa copriva.
    athletes = {
        a.id: a
        for a in (
            await db.execute(
                select(ClubAthlete).where(ClubAthlete.id.in_({f.athlete_id for fs in fees.values() for f in fs}))
            )
        ).scalars()
    } if proofs else {}
    emails = dict(
        (await db.execute(select(User.id, User.email).where(User.id.in_({p.uploaded_by_user_id for p in proofs})))).all()
    ) if proofs else {}
    today = _today()
    out = []
    for p in proofs:
        row = family_service.proof_dict(p, fees=fees[p.id], today=today)
        row["fees"] = [family_service.fee_dict(f, today=today, athlete=athletes.get(f.athlete_id)) for f in fees[p.id]]
        out.append(AdminProofRead(**row, uploaded_by_email=emails.get(p.uploaded_by_user_id)))
    return out


@admin_router.get("/payment-proofs/{proof_id}/url", response_model=UrlRead)
async def admin_get_proof_url(
    proof_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> UrlRead:
    try:
        proof = await club_service.get_proof(db, scope=current_user.scope, proof_id=proof_id)
    except club_service.ClubError as exc:
        _raise(exc)
    if proof.storage_key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NO_RECEIPT[proof.method == "CASH"])
    return UrlRead(url=club_service.presigned_url(proof.storage_key))


@admin_router.post("/payment-proofs/{proof_id}/reject", response_model=ProofRead)
async def admin_reject_proof(
    proof_id: uuid.UUID,
    payload: ReasonWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ProofRead:
    try:
        proof = await club_service.reject_proof(
            db, scope=current_user.scope, proof_id=proof_id, actor_user_id=current_user.user_id,
            reason=payload.reason,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    fees = (await club_service.fees_by_proof(db, proof_ids=[proof.id]))[proof.id]
    return ProofRead(**family_service.proof_dict(proof, fees=fees, today=_today()))


@admin_router.get("/competitions", response_model=list[CompetitionRead])
async def admin_list_competitions(
    status_filter: str | None = Query(default=None, alias="status"),
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[CompetitionRead]:
    comps = await competitions_service.list_competitions(
        db, scope=current_user.scope, status=status_filter
    )
    return [CompetitionRead.model_validate(c) for c in comps]


@admin_router.post("/competitions", response_model=CompetitionRead, status_code=status.HTTP_201_CREATED)
async def admin_create_competition(
    payload: CompetitionWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> CompetitionRead:
    try:
        comp = await competitions_service.create_competition(
            db, scope=current_user.scope, actor_user_id=current_user.user_id,
            data=payload.model_dump(),
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return CompetitionRead.model_validate(comp)


@admin_router.patch("/competitions/{competition_id}", response_model=CompetitionRead)
async def admin_update_competition(
    competition_id: uuid.UUID,
    payload: CompetitionUpdate,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> CompetitionRead:
    try:
        comp = await competitions_service.update_competition(
            db, scope=current_user.scope, competition_id=competition_id,
            actor_user_id=current_user.user_id, changes=payload.model_dump(exclude_unset=True),
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return CompetitionRead.model_validate(comp)


@admin_router.post(
    "/competitions/{competition_id}/image", response_model=CompetitionRead,
    dependencies=[Depends(rate_limit("club-event-image", max_requests=30, window_seconds=300))],
)
async def admin_competition_image(
    competition_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> CompetitionRead:
    try:
        comp = await competitions_service.set_competition_image(
            db, scope=current_user.scope, competition_id=competition_id, actor_user_id=current_user.user_id,
            file_bytes=await file.read(), content_type=file.content_type or "",
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return CompetitionRead.model_validate(comp)


@admin_router.delete("/competitions/{competition_id}/image", response_model=CompetitionRead)
async def admin_competition_image_delete(
    competition_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> CompetitionRead:
    try:
        comp = await competitions_service.set_competition_image(
            db, scope=current_user.scope, competition_id=competition_id, actor_user_id=current_user.user_id,
            file_bytes=None,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return CompetitionRead.model_validate(comp)


@admin_router.post("/competitions/{competition_id}/close", response_model=CompetitionRead)
async def admin_close_competition(
    competition_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> CompetitionRead:
    try:
        comp = await competitions_service.set_competition_status(
            db, scope=current_user.scope, competition_id=competition_id,
            actor_user_id=current_user.user_id, status="CLOSED",
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return CompetitionRead.model_validate(comp)


@admin_router.post("/competitions/{competition_id}/reopen", response_model=CompetitionRead)
async def admin_reopen_competition(
    competition_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> CompetitionRead:
    try:
        comp = await competitions_service.set_competition_status(
            db, scope=current_user.scope, competition_id=competition_id,
            actor_user_id=current_user.user_id, status="OPEN",
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return CompetitionRead.model_validate(comp)


@admin_router.get("/competitions/{competition_id}/entries", response_model=list[EntryRead])
async def admin_list_entries(
    competition_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[EntryRead]:
    try:
        comp = await competitions_service.get_competition(
            db, scope=current_user.scope, competition_id=competition_id
        )
    except club_service.ClubError as exc:
        _raise(exc)
    entries = await competitions_service.list_entries(db, competition_ids=[comp.id])
    athletes = {
        a.id: a
        for a in (await db.execute(select(ClubAthlete).where(ClubAthlete.id.in_({e.athlete_id for e in entries})))).scalars()
    } if entries else {}
    letters = await school_letters_service.letters_by_entry(db, entry_ids=[e.id for e in entries])
    return [await _entry_read(db, e, athletes[e.athlete_id], comp, letters) for e in entries]


# --- Giustificazione per la scuola (club/school_letters.py) ----------------------------------------


@admin_router.get("/competitions/{competition_id}/entries/{entry_id}/school-letter", response_model=SchoolLetterRead)
async def admin_school_letter_draft(
    competition_id: uuid.UUID,
    entry_id: uuid.UUID,
    fresh: bool = False,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> SchoolLetterRead:
    """Il testo da correggere prima di generare il PDF: quello già stampato,
    o la proposta (`fresh=true`: la proposta in ogni caso)."""
    fn = school_letters_service.proposal if fresh else school_letters_service.draft
    try:
        data = await fn(db, scope=current_user.scope, competition_id=competition_id, entry_id=entry_id, today=_today())
    except club_service.ClubError as exc:
        _raise(exc)
    return SchoolLetterRead(**data)


@admin_router.post(
    "/competitions/{competition_id}/entries/{entry_id}/school-letter", response_model=UrlRead,
    dependencies=[Depends(rate_limit("club-school-letter", max_requests=30, window_seconds=300))],
)
async def admin_generate_school_letter(
    competition_id: uuid.UUID,
    entry_id: uuid.UUID,
    payload: SchoolLetterWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> UrlRead:
    """Genera (o rigenera) il PDF con il testo corretto e restituisce il
    link per scaricarlo, valido pochi minuti."""
    try:
        letter = await school_letters_service.generate(
            db, scope=current_user.scope, competition_id=competition_id, entry_id=entry_id,
            body_text=payload.body_text, actor_user_id=current_user.user_id,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return UrlRead(url=club_service.presigned_url(letter.storage_key))


@admin_router.get("/competitions/{competition_id}/entries/{entry_id}/school-letter/url", response_model=UrlRead)
async def admin_school_letter_url(
    competition_id: uuid.UUID,
    entry_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> UrlRead:
    try:
        letter = await school_letters_service.letter_for(
            db, scope=current_user.scope, competition_id=competition_id, entry_id=entry_id
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return UrlRead(url=club_service.presigned_url(letter.storage_key))


@admin_router.put("/competitions/{competition_id}/results", response_model=CompetitionRead)
async def admin_record_results(
    competition_id: uuid.UUID,
    payload: ResultsWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> CompetitionRead:
    try:
        comp = await competitions_service.record_results(
            db, scope=current_user.scope, competition_id=competition_id,
            actor_user_id=current_user.user_id, results=[(r.entry_id, r.placement) for r in payload.results],
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return CompetitionRead.model_validate(comp)


@admin_router.get("/ranking", response_model=RankingRead)
async def admin_get_ranking(
    season: int | None = None,
    sex: str | None = Query(default=None, pattern="^[MF]$"),
    age_band: str | None = None,
    club_only: bool = False,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> RankingRead:
    season = season if season is not None else competitions_service.ranking_year(_today())
    try:
        rows = await competitions_service.ranking(
            db, scope=current_user.scope, season=season, sex=sex, age_band=age_band, club_only=club_only,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return RankingRead(season=season, season_label=competitions_service.ranking_label(season), sex=sex,
                       age_band=age_band, rows=rows)


@admin_router.delete("/belts/{belt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_belt(
    belt_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await club_service.delete_belt(
            db, scope=current_user.scope, belt_id=belt_id, actor_user_id=current_user.user_id
        )
    except club_service.ClubError as exc:
        _raise(exc)


@admin_router.get("/courses", response_model=list[CourseRead])
async def admin_list_courses(
    include_inactive: bool = False,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[CourseRead]:
    courses = await courses_service.list_courses(
        db, scope=current_user.scope, only_active=not include_inactive
    )
    return await _courses_read(db, courses, with_staff=True)


@admin_router.post("/courses", response_model=CourseRead, status_code=status.HTTP_201_CREATED)
async def admin_create_course(
    payload: CourseWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> CourseRead:
    try:
        course = await courses_service.create_course(
            db, scope=current_user.scope, actor_user_id=current_user.user_id,
            data=payload.model_dump(),
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return (await _courses_read(db, [course], with_staff=True))[0]


@admin_router.patch("/courses/{course_id}", response_model=CourseRead)
async def admin_update_course(
    course_id: uuid.UUID,
    payload: CourseUpdate,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> CourseRead:
    try:
        course = await courses_service.update_course(
            db, scope=current_user.scope, course_id=course_id, actor_user_id=current_user.user_id,
            changes=payload.model_dump(exclude_unset=True),
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return (await _courses_read(db, [course], with_staff=True))[0]


@admin_router.post("/courses/{course_id}/slots", response_model=SlotRead, status_code=status.HTTP_201_CREATED)
async def admin_add_slot(
    course_id: uuid.UUID,
    payload: SlotWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> SlotRead:
    try:
        slot = await courses_service.add_slot(
            db, scope=current_user.scope, course_id=course_id, actor_user_id=current_user.user_id,
            **payload.model_dump(),
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return SlotRead.model_validate(slot)


@admin_router.patch("/slots/{slot_id}", response_model=SlotRead)
async def admin_update_slot(
    slot_id: uuid.UUID,
    payload: SlotWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> SlotRead:
    try:
        slot = await courses_service.update_slot(
            db, scope=current_user.scope, slot_id=slot_id, actor_user_id=current_user.user_id,
            **payload.model_dump(),
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return SlotRead.model_validate(slot)


@admin_router.delete("/slots/{slot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_slot(
    slot_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await courses_service.delete_slot(
            db, scope=current_user.scope, slot_id=slot_id, actor_user_id=current_user.user_id
        )
    except club_service.ClubError as exc:
        _raise(exc)


@admin_router.post("/courses/{course_id}/athletes", status_code=status.HTTP_204_NO_CONTENT)
async def admin_enrol(
    course_id: uuid.UUID,
    payload: EnrolWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        course = await courses_service.get_course(db, scope=current_user.scope, course_id=course_id)
        athlete = await club_service.get_athlete(
            db, scope=current_user.scope, athlete_id=payload.athlete_id
        )
        await courses_service.enrol(db, course=course, athlete=athlete, actor_user_id=current_user.user_id)
    except club_service.ClubError as exc:
        _raise(exc)


@admin_router.delete("/courses/{course_id}/athletes/{athlete_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_unenrol(
    course_id: uuid.UUID,
    athlete_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        course = await courses_service.get_course(db, scope=current_user.scope, course_id=course_id)
        athlete = await club_service.get_athlete(db, scope=current_user.scope, athlete_id=athlete_id)
        await courses_service.unenrol(db, course=course, athlete=athlete, actor_user_id=current_user.user_id)
    except club_service.ClubError as exc:
        _raise(exc)


@admin_router.get("/stats")
async def admin_stats(
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """I numeri della home della segreteria."""
    club_id = current_user.club_id
    today = _today()
    athletes_active = (
        await db.execute(select(func.count()).where(ClubAthlete.club_id == club_id, ClubAthlete.status == "ACTIVE"))
    ).scalar_one()
    due = (
        await db.execute(
            select(func.count(), func.coalesce(func.sum(ClubFee.amount_cents), 0)).where(
                ClubFee.club_id == club_id, ClubFee.status == "DUE", ClubFee.due_date < today
            )
        )
    ).one()
    month = seasons.period_of(today)
    paid_month = (
        await db.execute(
            select(func.coalesce(func.sum(ClubFee.amount_cents), 0)).where(
                ClubFee.club_id == club_id, ClubFee.kind == "MONTHLY", ClubFee.period == month,
                ClubFee.status == "PAID",
            )
        )
    ).scalar_one()
    issued_month = (
        await db.execute(
            select(func.coalesce(func.sum(ClubFee.amount_cents), 0)).where(
                ClubFee.club_id == club_id, ClubFee.kind == "MONTHLY", ClubFee.period == month,
            )
        )
    ).scalar_one()
    return {
        "athletes_active": athletes_active,
        "overdue_fees": due[0],
        "overdue_cents": int(due[1]),
        "month": month,
        "month_issued_cents": int(issued_month),
        "month_paid_cents": int(paid_month),
    }


# --- Istruttori e segreteria ----------------------------------------------------------------------


async def _staff_course(db: AsyncSession, current_user: ClubUser, course_id: uuid.UUID):
    """Il corso, se chi chiede lo può gestire: la segreteria tutti, un
    istruttore quelli che vede (tutti, tranne quelli da cui è escluso)."""
    try:
        course = await courses_service.get_course(db, scope=current_user.scope, course_id=course_id)
    except club_service.ClubError as exc:
        _raise(exc)
    if not await courses_service.can_see(db, course=course, user_id=current_user.user_id):
        granted = await get_permission_codes_for_user(
            db, user_id=current_user.user_id, organization_id=current_user.organization_id
        )
        if MANAGE not in granted:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Corso non trovato.")
    return course


@staff_router.get("/people-kinds", response_model=list[PersonKindsRead])
async def staff_people_kinds(
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)),
    db: AsyncSession = Depends(get_db),
) -> list[PersonKindsRead]:
    """Solo i simboli delle persone (atleta, genitore, istruttore, árbitro),
    per metterli accanto ai nomi negli elenchi: niente quote né contatti,
    così li vede anche l'istruttore."""
    rows = await people_service.list_people(db, scope=current_user.scope)
    return [PersonKindsRead(kind=r["kind"], id=r["id"], user_id=r["user_id"], kinds=r["kinds"]) for r in rows]


@staff_router.get("/courses", response_model=list[CourseRead])
async def staff_list_courses(
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)), db: AsyncSession = Depends(get_db)
) -> list[CourseRead]:
    granted = await get_permission_codes_for_user(
        db, user_id=current_user.user_id, organization_id=current_user.organization_id
    )
    courses = await courses_service.list_courses(
        db, scope=current_user.scope,
        visible_to_user_id=None if MANAGE in granted else current_user.user_id,
    )
    mine = await courses_service.taught_course_ids(db, scope=current_user.scope, user_id=current_user.user_id)
    return await _courses_read(db, courses, mine_ids=mine)


@staff_router.get("/courses/{course_id}/roster", response_model=RosterRead)
async def staff_roster(
    course_id: uuid.UUID,
    on: date | None = Query(default=None, alias="date"),
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)),
    db: AsyncSession = Depends(get_db),
) -> RosterRead:
    course = await _staff_course(db, current_user, course_id)
    on = on or _today()
    rows = await courses_service.roster(db, course=course, on=on)
    belts = await club_service.current_belts(db, athlete_ids=[a.id for a, _p, _n in rows])
    return RosterRead(course_id=course.id, date=on, rows=[
        {"athlete_id": a.id, "first_name": a.first_name, "last_name": a.last_name, "photo_url": a.photo_url,
         "belt": family_service.belt_dict(belts.get(a.id)), "present": present, "note": note}
        for a, present, note in rows
    ])


@staff_router.post("/courses/{course_id}/attendance", status_code=status.HTTP_204_NO_CONTENT)
async def staff_mark_attendance(
    course_id: uuid.UUID,
    payload: AttendanceWrite,
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)),
    db: AsyncSession = Depends(get_db),
) -> None:
    course = await _staff_course(db, current_user, course_id)
    try:
        athlete = await club_service.get_athlete(
            db, scope=current_user.scope, athlete_id=payload.athlete_id
        )
        enrolled = (
            await db.execute(
                select(ClubCourseAthlete.id).where(
                    ClubCourseAthlete.course_id == course.id, ClubCourseAthlete.athlete_id == athlete.id
                )
            )
        ).first()
        if enrolled is None:
            raise club_service.ClubValidationError(f"{athlete.first_name} non è iscritto a questo corso.")
        await courses_service.mark_attendance(
            db, course=course, athlete=athlete, on=payload.date, present=payload.present,
            actor_user_id=current_user.user_id, note=payload.note,
        )
    except club_service.ClubError as exc:
        _raise(exc)


@staff_router.get("/athletes", response_model=list[AthleteCardRead])
async def staff_search_athletes(
    q: str | None = None,
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)),
    db: AsyncSession = Depends(get_db),
) -> list[AthleteCardRead]:
    athletes = await club_service.search_athletes(
        db, scope=current_user.scope, status="ACTIVE", q=q, limit=100
    )
    return [AthleteCardRead(**c) for c in await family_service.athlete_cards(db, athletes=athletes)]


@staff_router.get("/athletes/{athlete_id}/belts", response_model=list[BeltHistoryRead])
async def staff_list_belts(
    athlete_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)),
    db: AsyncSession = Depends(get_db),
) -> list[BeltHistoryRead]:
    try:
        athlete = await club_service.get_athlete(db, scope=current_user.scope, athlete_id=athlete_id)
    except club_service.ClubError as exc:
        _raise(exc)
    return _belts_read(await club_service.belt_history(db, athlete_id=athlete.id))


@staff_router.post("/athletes/{athlete_id}/belts", response_model=BeltHistoryRead, status_code=status.HTTP_201_CREATED)
async def staff_award_belt(
    athlete_id: uuid.UUID,
    payload: BeltAward,
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)),
    db: AsyncSession = Depends(get_db),
) -> BeltHistoryRead:
    try:
        athlete = await club_service.get_athlete(db, scope=current_user.scope, athlete_id=athlete_id)
        row = await club_service.award_belt(
            db, athlete=athlete, grade=payload.grade, awarded_on=payload.awarded_on,
            actor_user_id=current_user.user_id, note=payload.note,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return _belts_read([row])[0]


# --- Il club su cui si lavora (tutti) -------------------------------------------------------------


@router.get("/current", response_model=CurrentClubRead)
async def get_current_club(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CurrentClubRead:
    """Il nome del club in testata e l'IBAN su cui si pagano le quote. Per
    lo staff della piattaforma, il club in cui è entrato."""
    club = await resolve_club(db, current_user=current_user, requested=request.headers.get(CLUB_HEADER))
    user = await db.get(User, current_user.user_id)
    return CurrentClubRead(
        id=club.id, name=club.name, slug=club.slug, entered=user is not None and user.club_id is None,
        settings=ClubSettingsRead(**clubs_service.club_settings(club)), kind=club.kind,
    )


# --- La segreteria: impostazioni, staff, ordini dello Shop ----------------------------------------


@admin_router.patch("/settings", response_model=CurrentClubRead)
async def admin_update_club_settings(
    payload: ClubSettingsWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> CurrentClubRead:
    club = await clubs_service.update_club_settings(
        db, scope=current_user.scope, actor_user_id=current_user.user_id,
        changes=payload.model_dump(exclude_unset=True),
    )
    user = await db.get(User, current_user.user_id)
    return CurrentClubRead(
        id=club.id, name=club.name, slug=club.slug, entered=user is not None and user.club_id is None,
        settings=ClubSettingsRead(**clubs_service.club_settings(club)), kind=club.kind,
    )


@admin_router.get("/staff", response_model=list[ClubStaffRead])
async def admin_list_staff(
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db)
) -> list[ClubStaffRead]:
    from app.domains.club.people import _names

    rows = await clubs_service.list_clubs(db, organization_id=current_user.organization_id)
    mine = next((c for c in rows if c["id"] == current_user.club_id), None)
    staff = mine["staff"] if mine else []
    names = await _names(db, {m["user_id"] for m in staff})
    return [ClubStaffRead(**{**m, "name": names.get(m["user_id"])}) for m in staff]


@admin_router.post("/staff", response_model=ClubStaffRead, status_code=status.HTTP_201_CREATED)
async def admin_add_staff(
    payload: ClubStaffWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ClubStaffRead:
    """La segreteria aggiunge i suoi istruttori (o un'altra persona in
    segreteria): account del club, solo del club."""
    try:
        user, invite_link = await clubs_service.add_staff(
            db, scope=current_user.scope, actor_user_id=current_user.user_id, email=payload.email, role=payload.role
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return ClubStaffRead(user_id=user.id, email=user.email, role=payload.role, invite_link=invite_link)


@admin_router.get("/month", response_model=MonthBoardRead)
async def admin_month_board(
    period: str | None = Query(default=None, max_length=7),
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> MonthBoardRead:
    """Il quadro del mese (month_board.py): chi ha pagato la mensilità e chi no."""
    from app.domains.club import month_board
    from app.domains.club.lessons import club_now

    today = (await club_now(db, club_id=current_user.club_id)).date()
    try:
        return MonthBoardRead(**await month_board.club_month(db, scope=current_user.scope, period=period, today=today))
    except club_service.ClubError as exc:
        _raise(exc)


@admin_router.get("/shop-orders", response_model=list[ClubShopOrderRead])
async def admin_list_club_shop_orders(
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db)
) -> list[ClubShopOrderRead]:
    """Gli ordini dello Shop delle famiglie del club, in sola lettura: lo
    Shop è della piattaforma, che conferma i pagamenti e spedisce."""
    from app.domains.jav_market import service as shop_service
    from app.domains.jav_market.models import JavMarketOrder

    rows = (
        await db.execute(
            select(JavMarketOrder, User.email)
            .join(User, User.id == JavMarketOrder.customer_user_id)
            .where(User.club_id == current_user.club_id)
            .order_by(JavMarketOrder.created_at.desc())
            .limit(500)
        )
    ).all()
    athlete_ids = {o.athlete_id for o, _e in rows if o.athlete_id}
    athletes = {
        a.id: a for a in (await db.execute(select(ClubAthlete).where(ClubAthlete.id.in_(athlete_ids)))).scalars()
    } if athlete_ids else {}
    out = []
    for order, email in rows:
        athlete = athletes.get(order.athlete_id) if order.athlete_id else None
        out.append(ClubShopOrderRead(
            id=order.id, number=shop_service.order_number(order), created_at=order.created_at,
            customer_email=email,
            athlete_name=f"{athlete.first_name} {athlete.last_name}" if athlete else None,
            items_summary=shop_service.items_summary(await shop_service.order_items(db, order)),
            amount_cents=order.amount_cents, status=order.status, fulfillment_status=order.fulfillment_status,
            payment_proof_uploaded_at=order.payment_proof_uploaded_at,
        ))
    return out


# --- Il superadmin: i club della piattaforma ------------------------------------------------------


@clubs_router.get("", response_model=list[ClubRead])
async def list_clubs(
    current_user: CurrentUser = Depends(require_permission(CLUBS_ENTER)), db: AsyncSession = Depends(get_db)
) -> list[ClubRead]:
    return [ClubRead(**c) for c in await clubs_service.list_clubs(db, organization_id=current_user.organization_id)]


async def _club_read(db: AsyncSession, organization_id: uuid.UUID, club_id: uuid.UUID) -> ClubRead:
    rows = await clubs_service.list_clubs(db, organization_id=organization_id)
    return ClubRead(**next(c for c in rows if c["id"] == club_id))


@clubs_router.get("/overview")
async def platform_overview(
    current_user: CurrentUser = Depends(require_permission(CLUBS_ENTER)), db: AsyncSession = Depends(get_db)
) -> dict:
    """La panoramica della piattaforma: tutti i club e i prossimi eventi."""
    return await clubs_service.platform_overview(db, organization_id=current_user.organization_id, today=_today())


@clubs_router.post("", response_model=ClubRead, status_code=status.HTTP_201_CREATED)
async def create_club(
    payload: ClubCreate,
    current_user: CurrentUser = Depends(require_permission(CLUBS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ClubRead:
    try:
        club, invite_link = await clubs_service.create_club(
            db, organization_id=current_user.organization_id, actor_user_id=current_user.user_id,
            name=payload.name, slug=payload.slug, secretary_email=payload.secretary_email,
            settings=payload.settings.model_dump() if payload.settings else None,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    read = await _club_read(db, current_user.organization_id, club.id)
    return read.model_copy(update={"invite_link": invite_link})


@clubs_router.patch("/{club_id}", response_model=ClubRead)
async def update_club(
    club_id: uuid.UUID,
    payload: ClubUpdate,
    current_user: CurrentUser = Depends(require_permission(CLUBS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ClubRead:
    try:
        await clubs_service.update_club(
            db, organization_id=current_user.organization_id, club_id=club_id, actor_user_id=current_user.user_id,
            changes=payload.model_dump(exclude_unset=True),
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return await _club_read(db, current_user.organization_id, club_id)


@clubs_router.post("/{club_id}/staff", response_model=ClubStaffRead, status_code=status.HTTP_201_CREATED)
async def add_club_staff(
    club_id: uuid.UUID,
    payload: ClubStaffWrite,
    current_user: CurrentUser = Depends(require_permission(CLUBS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ClubStaffRead:
    try:
        club = await clubs_service.get_club(db, organization_id=current_user.organization_id, club_id=club_id)
        user, invite_link = await clubs_service.add_staff(
            db, scope=ClubScope(organization_id=club.organization_id, club_id=club.id), actor_user_id=current_user.user_id,
            email=payload.email, role=payload.role,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return ClubStaffRead(user_id=user.id, email=user.email, role=payload.role, invite_link=invite_link)


@clubs_router.post("/{club_id}/staff/{user_id}/access-link", response_model=StaffAccessLinkRead)
async def club_staff_access_link(
    club_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission(CLUBS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> StaffAccessLinkRead:
    """Il superadmin rimanda a una persona dello staff il link per scegliere
    la password (clubs.staff_access_link)."""
    try:
        club = await clubs_service.get_club(db, organization_id=current_user.organization_id, club_id=club_id)
        link = await clubs_service.staff_access_link(
            db, scope=ClubScope(organization_id=club.organization_id, club_id=club.id), user_id=user_id,
            actor_user_id=current_user.user_id,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return StaffAccessLinkRead(link=link, emailed=link is None)


@clubs_router.get("/public/{slug}", response_model=PublicClubRead)
async def get_public_club(slug: str, db: AsyncSession = Depends(get_db)) -> PublicClubRead:
    """Pubblica: la pagina di registrazione del club (/c/<slug>) mostra il
    nome del club a cui ci si sta iscrivendo. Solo nome e indirizzo."""
    club = await clubs_service.get_club_by_slug(db, slug=slug)
    if club is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Club non trovato: controlla il link che hai ricevuto.")
    return PublicClubRead(name=club.name, slug=club.slug)


# --- Prezzi e sconti, iscrizioni dell'anno ---------------------------------------------------------


@admin_router.get("/pricing", response_model=PricingRead)
async def admin_get_pricing(
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db)
) -> PricingRead:
    return PricingRead(**await club_service.club_pricing(db, club_id=current_user.club_id))


@admin_router.patch("/pricing", response_model=PricingRead)
async def admin_update_pricing(
    payload: PricingWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> PricingRead:
    try:
        pricing = await clubs_service.update_club_pricing(
            db, scope=current_user.scope, actor_user_id=current_user.user_id,
            changes=payload.model_dump(exclude_unset=True),
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return PricingRead(**pricing)


@admin_router.post("/jobs/new-year", response_model=JobResultRead)
async def admin_start_year(
    year: int | None = None,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> JobResultRead:
    """Lo stesso lavoro del 1° gennaio: iscrizioni dell'anno e quote socio.
    Rilanciarlo è innocuo."""
    created = await club_service.start_year(db, scope=current_user.scope, year=year or _today().year)
    return JobResultRead(created=created)


# --- Trasporto per gare e stage --------------------------------------------------------------------


async def _transport_read(db: AsyncSession, request) -> TransportRequestRead:
    read = TransportRequestRead.model_validate(request)
    read.current_athletes_count = await transport_service.current_count(db, competition_id=request.competition_id)
    return read


@admin_router.get("/competitions/{competition_id}/transport", response_model=TransportRequestRead)
async def admin_get_transport(
    competition_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> TransportRequestRead:
    """La richiesta di trasporto dell'evento: se non c'è ancora, la bozza si
    scrive adesso con gli iscritti di adesso."""
    try:
        request = await transport_service.get_or_prepare(db, scope=current_user.scope, competition_id=competition_id)
    except club_service.ClubError as exc:
        _raise(exc)
    return await _transport_read(db, request)


@admin_router.post("/competitions/{competition_id}/transport/regenerate", response_model=TransportRequestRead)
async def admin_regenerate_transport(
    competition_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> TransportRequestRead:
    try:
        request = await transport_service.regenerate(db, scope=current_user.scope, competition_id=competition_id)
    except club_service.ClubError as exc:
        _raise(exc)
    return await _transport_read(db, request)


@admin_router.put("/competitions/{competition_id}/transport", response_model=TransportRequestRead)
async def admin_save_transport(
    competition_id: uuid.UUID,
    payload: TransportRequestWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> TransportRequestRead:
    try:
        request = await transport_service.save(
            db, scope=current_user.scope, competition_id=competition_id, **payload.model_dump()
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return await _transport_read(db, request)


@admin_router.post(
    "/competitions/{competition_id}/transport/send", response_model=TransportRequestRead,
    dependencies=[Depends(rate_limit("club-transport-send", max_requests=10, window_seconds=300))],
)
async def admin_send_transport(
    competition_id: uuid.UUID,
    payload: TransportRequestWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> TransportRequestRead:
    """Manda la lettera così come la segreteria l'ha lasciata nell'anteprima."""
    try:
        request = await transport_service.send(
            db, scope=current_user.scope, competition_id=competition_id, actor_user_id=current_user.user_id,
            **payload.model_dump(),
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return await _transport_read(db, request)


# --- Le persone del club --------------------------------------------------------------------------


@admin_router.get("/people", response_model=list[PersonRead])
async def admin_list_people(
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db)
) -> list[PersonRead]:
    """Atleti, genitori, segreteria, treinador e monitor: una riga a persona."""
    return [PersonRead(**r) for r in await people_service.list_people(db, scope=current_user.scope)]


@admin_router.put("/functions", status_code=status.HTTP_204_NO_CONTENT)
async def admin_set_function(
    payload: FunctionWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await people_service.set_function(
            db, scope=current_user.scope, actor_user_id=current_user.user_id, function=payload.function,
            user_id=payload.user_id, athlete_id=payload.athlete_id,
        )
    except club_service.ClubError as exc:
        _raise(exc)


@admin_router.put("/referees", status_code=status.HTTP_204_NO_CONTENT)
async def admin_set_referee(
    payload: RefereeWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await people_service.set_referee(
            db, scope=current_user.scope, actor_user_id=current_user.user_id, referee=payload.referee,
            user_id=payload.user_id, athlete_id=payload.athlete_id,
        )
    except club_service.ClubError as exc:
        _raise(exc)


@admin_router.get("/athletes/{athlete_id}/supports")
async def admin_list_supports(
    athlete_id: uuid.UUID, current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> dict:
    from app.domains.club import support

    athlete = await db.get(ClubAthlete, athlete_id)
    if athlete is None or athlete.club_id != current_user.club_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Atleta non trovato.")
    return await support.money(db, athlete=athlete)


@admin_router.post("/athletes/{athlete_id}/supports", status_code=status.HTTP_201_CREATED)
async def admin_add_support(
    athlete_id: uuid.UUID, payload: SupportWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> dict:
    """Un costo che il club ha pagato per l'atleta (club/support.py)."""
    from app.domains.club import support

    try:
        row = await support.record(db, scope=current_user.scope, athlete_id=athlete_id, actor_user_id=current_user.user_id,
                                   **payload.model_dump())
    except club_service.ClubError as exc:
        _raise(exc)
    return support.support_dict(row)


@admin_router.get("/people/athletes/{athlete_id}/card", response_model=PersonCardRead)
async def admin_athlete_card(
    athlete_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> PersonCardRead:
    try:
        return PersonCardRead(**await people_service.person_card(db, scope=current_user.scope, athlete_id=athlete_id))
    except club_service.ClubError as exc:
        _raise(exc)


@admin_router.get("/people/users/{user_id}/card", response_model=PersonCardRead)
async def admin_user_card(
    user_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> PersonCardRead:
    try:
        return PersonCardRead(**await people_service.person_card(db, scope=current_user.scope, user_id=user_id))
    except club_service.ClubError as exc:
        _raise(exc)


@admin_router.post("/athletes/{athlete_id}/investments", status_code=status.HTTP_201_CREATED)
async def admin_invest(
    athlete_id: uuid.UUID,
    payload: InvestmentWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Il club investe su un atleta (ricarica il wallet della famiglia).
    Muove denaro: solo chi ha `wallet.credit`, cioè il superadmin."""
    granted = await get_permission_codes_for_user(
        db, user_id=current_user.user_id, organization_id=current_user.organization_id
    )
    if "wallet.credit" not in granted:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Gli investimenti li registra solo il superadmin.")
    try:
        return await people_service.invest(
            db, scope=current_user.scope, athlete_id=athlete_id, amount_cents=payload.amount_cents,
            note=payload.note, actor_user_id=current_user.user_id,
        )
    except club_service.ClubError as exc:
        _raise(exc)


@admin_router.put("/courses/{course_id}/staff", status_code=status.HTTP_204_NO_CONTENT)
async def admin_set_course_staff(
    course_id: uuid.UUID,
    payload: CourseStaffWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await courses_service.set_course_staff(
            db, scope=current_user.scope, course_id=course_id, user_ids=payload.user_ids,
            actor_user_id=current_user.user_id,
        )
    except club_service.ClubError as exc:
        _raise(exc)


@admin_router.get("/courses/{course_id}/coach-exclusions", response_model=list[uuid.UUID])
async def admin_course_coach_exclusions(
    course_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[uuid.UUID]:
    """I treinador che NON vedono il corso: di regola nessuno, ogni
    treinador vede tutti i corsi (courses.visible_course_filter)."""
    try:
        course = await courses_service.get_course(db, scope=current_user.scope, course_id=course_id)
    except club_service.ClubError as exc:
        _raise(exc)
    return (await courses_service.coach_exclusions_by_course(db, course_ids=[course.id]))[course.id]


@admin_router.put("/courses/{course_id}/coach-exclusions", response_model=list[uuid.UUID])
async def admin_set_course_coach_exclusions(
    course_id: uuid.UUID,
    payload: CourseCoachExclusionsWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[uuid.UUID]:
    try:
        return await courses_service.set_coach_exclusions(
            db, scope=current_user.scope, course_id=course_id, user_ids=payload.user_ids,
            actor_user_id=current_user.user_id,
        )
    except club_service.ClubError as exc:
        _raise(exc)


# --- Lezioni, presenze, cartellino ---------------------------------------------------------------


async def _is_manager(db: AsyncSession, current_user: ClubUser) -> bool:
    granted = await get_permission_codes_for_user(
        db, user_id=current_user.user_id, organization_id=current_user.organization_id
    )
    return MANAGE in granted


@staff_router.get("/lessons", response_model=list[LessonRead])
async def staff_lessons(
    start: date | None = Query(default=None, alias="from"),
    end: date | None = Query(default=None, alias="to"),
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)),
    db: AsyncSession = Depends(get_db),
) -> list[LessonRead]:
    """Il calendario: le lezioni dei corsi che vedo (tutti, tranne quelli da
    cui la segreteria mi ha escluso; `mine` su quelli che insegno); la
    segreteria vede tutte quelle del club. Senza date: oggi."""
    today = (await lessons_service.club_now(db, club_id=current_user.club_id)).date()
    start = start or today
    try:
        rows = await lessons_service.lessons(
            db, scope=current_user.scope, start=start, end=end or start,
            teacher_user_id=None if await _is_manager(db, current_user) else current_user.user_id,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return [LessonRead(**r) for r in rows]


@staff_router.get("/clock", response_model=ClockRead)
async def staff_clock(
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)), db: AsyncSession = Depends(get_db)
) -> ClockRead:
    return ClockRead(**await workclock_service.status(db, scope=current_user.scope, user_id=current_user.user_id))


@staff_router.post("/clock/in", response_model=ClockRead)
async def staff_clock_in(
    payload: ClockWrite,
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)),
    db: AsyncSession = Depends(get_db),
) -> ClockRead:
    try:
        return ClockRead(**await workclock_service.clock_in(
            db, scope=current_user.scope, user_id=current_user.user_id, note=payload.note
        ))
    except club_service.ClubError as exc:
        _raise(exc)


@staff_router.post("/clock/out", response_model=ClockRead)
async def staff_clock_out(
    payload: ClockWrite,
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)),
    db: AsyncSession = Depends(get_db),
) -> ClockRead:
    try:
        return ClockRead(**await workclock_service.clock_out(
            db, scope=current_user.scope, user_id=current_user.user_id, note=payload.note
        ))
    except club_service.ClubError as exc:
        _raise(exc)


@admin_router.get("/work-hours", response_model=list[StaffHoursRead])
async def admin_work_hours(
    month: str | None = None,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[StaffHoursRead]:
    try:
        rows = await workclock_service.hours_by_staff(
            db, scope=current_user.scope, month=month or seasons.period_of(_today())
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return [StaffHoursRead(**r) for r in rows]


@admin_router.patch("/work-sessions/{session_id}", response_model=WorkSessionRead)
async def admin_correct_work_session(
    session_id: uuid.UUID,
    payload: WorkSessionUpdate,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> WorkSessionRead:
    try:
        return WorkSessionRead(**await workclock_service.correct(
            db, scope=current_user.scope, session_id=session_id, actor_user_id=current_user.user_id,
            changes=payload.model_dump(exclude_unset=True),
        ))
    except club_service.ClubError as exc:
        _raise(exc)


@admin_router.get("/attendance", response_model=list[DayAttendanceRead])
async def admin_day_attendance(
    on: date | None = Query(default=None, alias="date"),
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[DayAttendanceRead]:
    """Il registro del giorno: ogni presenza segnata, da chi, con la nota."""
    on = on or (await lessons_service.club_now(db, club_id=current_user.club_id)).date()
    return [DayAttendanceRead(**r) for r in await lessons_service.day_log(db, scope=current_user.scope, on=on)]


@router.get("/attendance/today", response_model=list[FamilyLessonRead])
async def family_lessons_today(
    current_user: ClubUser = Depends(require_club_permission(FAMILY)), db: AsyncSession = Depends(get_db)
) -> list[FamilyLessonRead]:
    rows = await lessons_service.family_today(db, scope=current_user.scope, guardian_user_id=current_user.user_id)
    return [FamilyLessonRead(**r) for r in rows]


@router.post("/attendance/today", status_code=status.HTTP_204_NO_CONTENT)
async def family_mark_today(
    payload: FamilyAttendanceWrite,
    current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Il genitore segna la presenza di oggi: solo oggi, solo i suoi atleti."""
    try:
        await lessons_service.family_mark(
            db, scope=current_user.scope, guardian_user_id=current_user.user_id, athlete_id=payload.athlete_id,
            course_id=payload.course_id, present=True, note=payload.note,
        )
    except club_service.ClubError as exc:
        _raise(exc)


@router.delete("/attendance/today/{athlete_id}/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
async def family_unmark_today(
    athlete_id: uuid.UUID,
    course_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(FAMILY)),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await lessons_service.family_mark(
            db, scope=current_user.scope, guardian_user_id=current_user.user_id, athlete_id=athlete_id,
            course_id=course_id, present=False, note=None,
        )
    except club_service.ClubError as exc:
        _raise(exc)


# --- Taxa de falta -------------------------------------------------------------------------------


@admin_router.get("/absence", response_model=list[AbsenceRowRead])
async def admin_absence(
    period: str | None = None,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[AbsenceRowRead]:
    try:
        rows = await absence_service.month_overview(
            db, scope=current_user.scope, period=period or seasons.period_of(_today())
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return [AbsenceRowRead(**r) for r in rows]


@admin_router.put("/fees/{fee_id}/absence", response_model=FeeRead)
async def admin_apply_absence(
    fee_id: uuid.UUID,
    payload: AbsenceWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> FeeRead:
    try:
        fee = await absence_service.apply(
            db, scope=current_user.scope, fee_id=fee_id, adjustment=payload.adjustment,
            actor_user_id=current_user.user_id,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return FeeRead(**family_service.fee_dict(fee, today=_today()))


# --- Corsi JAV (club/kinds.py, club/jav_courses.py) -----------------------------------------------


@admin_router.get("/courses-report", response_model=CoursesReportRead)
async def admin_courses_report(
    period: str | None = None,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> CoursesReportRead:
    """Corso per corso: iscritti, presenze, incassato, parte del treinador e
    di JAV, ancora da incassare, debiti. Solo nell'unità dei corsi JAV."""
    from app.domains.club import accounting

    today = _today()
    try:
        return CoursesReportRead(**await jav_courses_service.courses_report(
            db, scope=current_user.scope, period=accounting.parse_period(period, today=today), today=today,
        ))
    except club_service.ClubError as exc:
        _raise(exc)


@admin_router.get("/move-targets", response_model=list[MoveTargetRead])
async def admin_move_targets(
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db)
) -> list[MoveTargetRead]:
    try:
        return [MoveTargetRead(**c) for c in await jav_courses_service.move_targets(db, scope=current_user.scope)]
    except club_service.ClubError as exc:
        _raise(exc)


@admin_router.post("/people/{user_id}/move-to-club", response_model=MoveResultRead)
async def admin_move_family_to_club(
    user_id: uuid.UUID,
    payload: MoveToClubWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> MoveResultRead:
    """Una famiglia dei corsi JAV passa a un club ufficiale (con i suoi atleti)."""
    try:
        return MoveResultRead(**await jav_courses_service.move_family_to_club(
            db, scope=current_user.scope, guardian_user_id=user_id, target_club_id=payload.target_club_id,
            actor_user_id=current_user.user_id,
        ))
    except club_service.ClubError as exc:
        _raise(exc)


@staff_router.get("/earnings", response_model=CoachEarningsRead)
async def staff_earnings(
    year: int | None = Query(default=None, ge=2000, le=2100),
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)),
    db: AsyncSession = Depends(get_db),
) -> CoachEarningsRead:
    """"I miei guadagni": la parte del treinador delle mensilità dei suoi
    corsi JAV, mese per mese. Solo le sue: l'utente è quello della sessione."""
    return CoachEarningsRead(**await jav_courses_service.coach_earnings(
        db, scope=current_user.scope, user_id=current_user.user_id, year=year or _today().year,
    ))


@clubs_router.post("/jav-courses", response_model=ClubRead)
async def ensure_jav_courses_unit(
    current_user: CurrentUser = Depends(require_permission(CLUBS_MANAGE)), db: AsyncSession = Depends(get_db),
) -> ClubRead:
    """L'unità "Cursos JAV": la crea se non c'è ancora (con il piano da
    25 € al mese), altrimenti restituisce quella che c'è."""
    club = await clubs_service.ensure_courses_unit(
        db, organization_id=current_user.organization_id, actor_user_id=current_user.user_id,
    )
    return await _club_read(db, current_user.organization_id, club.id)
