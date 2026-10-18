"""Le API dei corsi esterni (extcourses/service.py).

- `/public/ext-courses[...]`  il sito: i corsi pubblicati e l'iscrizione di
  chi non ha un account;
- `/ext/family[...]`          il genitore: i suoi figli, mensilità, prove, avvisi,
  l'iscrizione da dentro (anche chi è già famiglia di un club: si iscrive
  di nuovo, l'anagrafica è del corso);
- `/ext/staff[...]`           la scuola e il treinador dei corsi a cui sono
  legati (ext_staff), e il superadmin;
- `/ext/admin[...]`           il superadmin (`clubs.manage`): corsi, gruppi,
  persone, conti.

Niente qui passa da club/scope.py: i corsi esterni non sono di un club.
"""

import uuid
from datetime import date, time
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db, utcnow
from app.core.deps import CurrentUser, get_current_user, require_permission
from app.core.rate_limit import rate_limit
from app.domains.extcourses import service
from app.domains.extcourses.models import ExtGroup
from app.domains.rbac.service import get_permission_codes_for_user
from app.domains.users.models import User

ADMIN = "clubs.manage"

public_router = APIRouter(prefix="/public/ext-courses", tags=["ext-courses"])
family_router = APIRouter(prefix="/ext/family", tags=["ext-courses"])
staff_router = APIRouter(prefix="/ext/staff", tags=["ext-courses"])
admin_router = APIRouter(prefix="/ext/admin", tags=["ext-courses"])


def _raise(exc: service.ExtError):
    code = (status.HTTP_404_NOT_FOUND if isinstance(exc, service.ExtNotFound)
            else status.HTTP_409_CONFLICT if isinstance(exc, service.ExtAccountExists) else status.HTTP_400_BAD_REQUEST)
    raise HTTPException(code, str(exc)) from exc


async def _org_id(db: AsyncSession) -> uuid.UUID:
    from sqlalchemy import select

    from app.domains.organizations.models import Organization

    org = (await db.execute(select(Organization.id).limit(2))).scalars().all()
    if len(org) != 1:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organizzazione non trovata.")
    return org[0]


async def _is_admin(db: AsyncSession, user: CurrentUser) -> bool:
    return ADMIN in await get_permission_codes_for_user(db, user_id=user.user_id, organization_id=user.organization_id)


# --- Schemi ---------------------------------------------------------------------------------------


class ChildWrite(BaseModel):
    first_name: str = Field(max_length=80)
    last_name: str = Field(max_length=80)
    birth_date: date
    sex: str | None = Field(default=None, max_length=1)
    notes: str | None = Field(default=None, max_length=500)


class PublicSignup(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    guardian_name: str = Field(max_length=160)
    guardian_phone: str | None = Field(default=None, max_length=40)
    children: list[ChildWrite] = Field(min_length=1, max_length=service.MAX_CHILDREN)
    privacy_accepted: bool


class EnrollWrite(BaseModel):
    guardian_name: str | None = Field(default=None, max_length=160)
    guardian_phone: str | None = Field(default=None, max_length=40)
    children: list[ChildWrite] = Field(min_length=1, max_length=service.MAX_CHILDREN)


class AttendanceWrite(BaseModel):
    date: date
    marks: dict[uuid.UUID, bool]


class ClockWrite(BaseModel):
    action: str = Field(pattern="^(in|out)$")


class NoticeWrite(BaseModel):
    title: str = Field(max_length=200)
    body: str | None = Field(default=None, max_length=4000)


class FeePaidWrite(BaseModel):
    method: str


class RejectWrite(BaseModel):
    reason: str = Field(max_length=500)


class CourseWrite(BaseModel):
    name: str | None = Field(default=None, max_length=150)
    school_name: str | None = Field(default=None, max_length=200)
    school_address: str | None = Field(default=None, max_length=300)
    school_city: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    monthly_fee_cents: int | None = Field(default=None, ge=0, le=100_000)
    billing_months: list[int] | None = None
    due_day: int | None = Field(default=None, ge=1, le=28)
    starts_on: date | None = None
    ends_on: date | None = None
    active: bool | None = None
    published: bool | None = None
    public_coach_name: str | None = Field(default=None, max_length=80)


class GroupWrite(BaseModel):
    name: str = Field(max_length=120)
    min_age: int | None = Field(default=None, ge=0, le=99)
    max_age: int | None = Field(default=None, ge=0, le=99)
    weekday: int = Field(ge=0, le=6)
    starts_at: time
    ends_at: time
    active: bool = True


class StaffWrite(BaseModel):
    email: str = Field(max_length=255)
    role: str = Field(pattern="^(COACH|SCHOOL)$")
    share_pct: Decimal | None = Field(default=None, ge=0, le=100)


# --- Pubblico -------------------------------------------------------------------------------------


@public_router.get("")
async def public_list(db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await service.public_courses(db)


@public_router.post("/{course_id}/signup", status_code=status.HTTP_201_CREATED,
                    dependencies=[Depends(rate_limit("ext-signup", max_requests=10, window_seconds=600))])
async def public_signup(course_id: uuid.UUID, payload: PublicSignup, db: AsyncSession = Depends(get_db)) -> dict:
    """L'iscrizione dal sito: nasce l'account del genitore e i figli si
    iscrivono. 409 se l'email ha già un account: entra e iscrivi da dentro."""
    if not payload.privacy_accepted:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Aceita a política de privacidade para continuar.")
    try:
        course = await service.get_course(db, organization_id=await _org_id(db), course_id=course_id)
        if not course.published:
            raise service.ExtNotFound("Corso non trovato.")
        await service.public_signup(
            db, course=course, email=payload.email, password=payload.password, guardian_name=payload.guardian_name,
            guardian_phone=payload.guardian_phone, children=[c.model_dump() for c in payload.children],
            today=utcnow().date(),
        )
    except service.ExtError as exc:
        _raise(exc)
    return {"ok": True}


# --- Il genitore --------------------------------------------------------------------------------


@family_router.get("")
async def my_family(current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    return await service.family(db, user_id=current_user.user_id, today=utcnow().date())


@family_router.post("/courses/{course_id}/enroll", status_code=status.HTTP_201_CREATED)
async def enroll(course_id: uuid.UUID, payload: EnrollWrite, current_user: CurrentUser = Depends(get_current_user),
                 db: AsyncSession = Depends(get_db)) -> dict:
    """Un account che c'è già (anche una famiglia di un club) iscrive i
    figli: l'anagrafica si scrive di nuovo, è del corso."""
    user = await db.get(User, current_user.user_id)
    try:
        course = await service.get_course(db, organization_id=current_user.organization_id, course_id=course_id)
        await service.enroll(db, course=course, parent=user, children=[c.model_dump() for c in payload.children],
                             guardian_name=payload.guardian_name, guardian_phone=payload.guardian_phone,
                             today=utcnow().date())
    except service.ExtError as exc:
        _raise(exc)
    return await service.family(db, user_id=current_user.user_id, today=utcnow().date())


@family_router.post("/proofs", status_code=status.HTTP_201_CREATED,
                    dependencies=[Depends(rate_limit("ext-proof", max_requests=20, window_seconds=600))])
async def upload_proof(
    fee_ids: str = Form(...), method: str = Form("BANK_TRANSFER"), note: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> dict:
    """La prova di pagamento delle mensilità scelte (`fee_ids` separati da virgola)."""
    try:
        ids = [uuid.UUID(x) for x in fee_ids.split(",") if x.strip()]
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mensalidades inválidas.") from exc
    blob = (await file.read(), file.content_type or "", file.filename or "") if file is not None and file.filename else None
    try:
        await service.upload_proof(db, user_id=current_user.user_id, fee_ids=ids, method=method, file=blob, note=note)
    except service.ExtError as exc:
        _raise(exc)
    return await service.family(db, user_id=current_user.user_id, today=utcnow().date())


# --- Scuola e treinador -------------------------------------------------------------------------


@staff_router.get("/courses")
async def staff_courses(current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> list[dict]:
    """I corsi in cui lavoro (scuola o treinador); per il superadmin tutti."""
    if await _is_admin(db, current_user):
        return [{**c, "roles": ["ADMIN"]} for c in await service.admin_courses(db, organization_id=current_user.organization_id)]
    return await service.my_staff_courses(db, user_id=current_user.user_id)


async def _staff(db, user: CurrentUser, course_id: uuid.UUID, role: str | None = None):
    try:
        return await service.staff_course(db, user_id=user.user_id, course_id=course_id,
                                          admin=await _is_admin(db, user), role=role)
    except service.ExtError as exc:
        _raise(exc)
    raise AssertionError


@staff_router.get("/courses/{course_id}")
async def staff_course(course_id: uuid.UUID, current_user: CurrentUser = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)) -> dict:
    course, roles = await _staff(db, current_user, course_id)
    return await service.roster(db, course=course, roles=roles, today=utcnow().date())


@staff_router.get("/courses/{course_id}/attendance")
async def attendance_day(course_id: uuid.UUID, on: date = Query(...), current_user: CurrentUser = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)) -> dict:
    course, _roles = await _staff(db, current_user, course_id)
    return await service.attendance_day(db, course=course, on=on)


@staff_router.post("/courses/{course_id}/attendance")
async def mark_attendance(course_id: uuid.UUID, payload: AttendanceWrite,
                          current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    course, _roles = await _staff(db, current_user, course_id)
    try:
        await service.mark_attendance(db, course=course, on=payload.date, marks=payload.marks,
                                      actor_user_id=current_user.user_id, today=utcnow().date())
    except service.ExtError as exc:
        _raise(exc)
    return await service.attendance_day(db, course=course, on=payload.date)


@staff_router.post("/courses/{course_id}/clock")
async def clock(course_id: uuid.UUID, payload: ClockWrite, current_user: CurrentUser = Depends(get_current_user),
                db: AsyncSession = Depends(get_db)) -> dict:
    course, _roles = await _staff(db, current_user, course_id, role=None)
    try:
        return await service.clock(db, course=course, user_id=current_user.user_id, action=payload.action)
    except service.ExtError as exc:
        _raise(exc)
    raise AssertionError


@staff_router.get("/clock")
async def clock_state(current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    return await service.clock_state(db, user_id=current_user.user_id)


@staff_router.get("/earnings")
async def earnings(year: int | None = Query(default=None), current_user: CurrentUser = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db)) -> dict:
    """I guadagni del treinador nei corsi esterni: la sua parte delle mensilità pagate."""
    return await service.accounts(db, organization_id=current_user.organization_id, year=year or utcnow().year,
                                  coach_user_id=current_user.user_id)


@staff_router.post("/courses/{course_id}/notices", status_code=status.HTTP_201_CREATED)
async def post_notice(course_id: uuid.UUID, payload: NoticeWrite, current_user: CurrentUser = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)) -> dict:
    course, _roles = await _staff(db, current_user, course_id)
    try:
        notice = await service.post_notice(db, course=course, author_user_id=current_user.user_id,
                                           title=payload.title, body=payload.body)
    except service.ExtError as exc:
        _raise(exc)
    return {"id": notice.id, "title": notice.title, "body": notice.body, "created_at": notice.created_at}


@staff_router.post("/courses/{course_id}/fees/{fee_id}/paid")
async def fee_paid(course_id: uuid.UUID, fee_id: uuid.UUID, payload: FeePaidWrite,
                   current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    """La scuola (o il superadmin) segna una mensilità pagata in contanti, MB WAY o POS."""
    course, roles = await _staff(db, current_user, course_id)
    if not roles & {"SCHOOL", "ADMIN"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Os pagamentos são da escola.")
    try:
        fee = await service.set_fee_paid(db, course=course, fee_id=fee_id, actor_user_id=current_user.user_id,
                                         method=payload.method)
    except service.ExtError as exc:
        _raise(exc)
    return service.fee_dict(fee, today=utcnow().date())


@staff_router.post("/courses/{course_id}/proofs/{proof_id}/reject")
async def reject_proof(course_id: uuid.UUID, proof_id: uuid.UUID, payload: RejectWrite,
                       current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    course, roles = await _staff(db, current_user, course_id)
    if not roles & {"SCHOOL", "ADMIN"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Os pagamentos são da escola.")
    try:
        proof = await service.reject_proof(db, course=course, proof_id=proof_id, actor_user_id=current_user.user_id,
                                           reason=payload.reason)
    except service.ExtError as exc:
        _raise(exc)
    return {"id": proof.id, "status": proof.status}


@staff_router.get("/proofs/{proof_id}/url")
async def proof_url(proof_id: uuid.UUID, current_user: CurrentUser = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)) -> dict:
    """Il file della prova: al genitore che l'ha caricata, alla scuola del
    corso, al superadmin. Un URL di pochi minuti."""
    from app.core.storage import generate_presigned_document_url

    try:
        proof = await service.proof_for(db, proof_id=proof_id)
        if proof.parent_user_id != current_user.user_id:
            _course, roles = await service.staff_course(db, user_id=current_user.user_id, course_id=proof.course_id,
                                                        admin=await _is_admin(db, current_user))
            if not roles & {"SCHOOL", "ADMIN"}:
                raise service.ExtNotFound("Prova não encontrada.")
    except service.ExtError as exc:
        _raise(exc)
    if not proof.storage_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esta prova não tem ficheiro.")
    return {"url": generate_presigned_document_url(storage_key=proof.storage_key), "filename": proof.filename}


# --- Il superadmin --------------------------------------------------------------------------------


@admin_router.get("/courses")
async def admin_courses(current_user: CurrentUser = Depends(require_permission(ADMIN)), db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await service.admin_courses(db, organization_id=current_user.organization_id)


@admin_router.post("/courses", status_code=status.HTTP_201_CREATED)
async def create_course(payload: CourseWrite, current_user: CurrentUser = Depends(require_permission(ADMIN)),
                        db: AsyncSession = Depends(get_db)) -> dict:
    try:
        course = await service.save_course(db, organization_id=current_user.organization_id,
                                           actor_user_id=current_user.user_id, data=payload.model_dump(exclude_none=True))
    except service.ExtError as exc:
        _raise(exc)
    return service.course_dict(course, [])


async def _admin_course(db, user: CurrentUser, course_id: uuid.UUID):
    try:
        return await service.get_course(db, organization_id=user.organization_id, course_id=course_id)
    except service.ExtError as exc:
        _raise(exc)
    raise AssertionError


@admin_router.patch("/courses/{course_id}")
async def update_course(course_id: uuid.UUID, payload: CourseWrite,
                        current_user: CurrentUser = Depends(require_permission(ADMIN)), db: AsyncSession = Depends(get_db)) -> dict:
    course = await _admin_course(db, current_user, course_id)
    try:
        course = await service.save_course(db, organization_id=current_user.organization_id,
                                           actor_user_id=current_user.user_id,
                                           data=payload.model_dump(exclude_unset=True), course=course)
    except service.ExtError as exc:
        _raise(exc)
    return service.course_dict(course, (await service.groups_of(db, [course.id], only_active=False))[course.id])


@admin_router.post("/courses/{course_id}/logo")
async def course_logo(course_id: uuid.UUID, file: UploadFile | None = File(default=None),
                      current_user: CurrentUser = Depends(require_permission(ADMIN)), db: AsyncSession = Depends(get_db)) -> dict:
    """Il logo della scuola (senza file: lo toglie)."""
    from app.core.storage import UploadValidationError, upload_media

    course = await _admin_course(db, current_user, course_id)
    if file is not None and file.filename:
        try:
            course.school_logo_url = upload_media(file_bytes=await file.read(), content_type=file.content_type or "",
                                                  key_prefix=f"photos/ext-courses/{course.id}")
        except UploadValidationError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "O logótipo deve ser JPG, PNG ou WebP até 5 MB.") from exc
    else:
        course.school_logo_url = None
    await db.commit()
    await db.refresh(course)
    return service.course_dict(course, (await service.groups_of(db, [course.id], only_active=False))[course.id])


@admin_router.post("/courses/{course_id}/groups", status_code=status.HTTP_201_CREATED)
async def add_group(course_id: uuid.UUID, payload: GroupWrite,
                    current_user: CurrentUser = Depends(require_permission(ADMIN)), db: AsyncSession = Depends(get_db)) -> dict:
    course = await _admin_course(db, current_user, course_id)
    try:
        group = await service.save_group(db, course=course, data=payload.model_dump())
    except service.ExtError as exc:
        _raise(exc)
    return service.group_dict(group)


@admin_router.patch("/courses/{course_id}/groups/{group_id}")
async def update_group(course_id: uuid.UUID, group_id: uuid.UUID, payload: GroupWrite,
                       current_user: CurrentUser = Depends(require_permission(ADMIN)), db: AsyncSession = Depends(get_db)) -> dict:
    course = await _admin_course(db, current_user, course_id)
    group = await db.get(ExtGroup, group_id)
    if group is None or group.course_id != course.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Grupo não encontrado.")
    try:
        group = await service.save_group(db, course=course, data=payload.model_dump(), group=group)
    except service.ExtError as exc:
        _raise(exc)
    return service.group_dict(group)


@admin_router.post("/courses/{course_id}/staff", status_code=status.HTTP_201_CREATED)
async def add_staff(course_id: uuid.UUID, payload: StaffWrite,
                    current_user: CurrentUser = Depends(require_permission(ADMIN)), db: AsyncSession = Depends(get_db)) -> dict:
    course = await _admin_course(db, current_user, course_id)
    try:
        _row, link = await service.add_staff(db, course=course, actor_user_id=current_user.user_id, email=payload.email,
                                             role=payload.role, share_pct=payload.share_pct)
    except service.ExtError as exc:
        _raise(exc)
    return {"staff": await service.staff_list(db, course=course), "invite_link": link}


@admin_router.delete("/courses/{course_id}/staff/{staff_id}")
async def remove_staff(course_id: uuid.UUID, staff_id: uuid.UUID,
                       current_user: CurrentUser = Depends(require_permission(ADMIN)), db: AsyncSession = Depends(get_db)) -> dict:
    course = await _admin_course(db, current_user, course_id)
    try:
        await service.remove_staff(db, course=course, staff_id=staff_id)
    except service.ExtError as exc:
        _raise(exc)
    return {"staff": await service.staff_list(db, course=course)}


@admin_router.get("/accounts")
async def accounts(year: int | None = Query(default=None), course_id: uuid.UUID | None = Query(default=None),
                   current_user: CurrentUser = Depends(require_permission(ADMIN)), db: AsyncSession = Depends(get_db)) -> dict:
    """La contabilità dei corsi esterni, separata dai club: incassato, parte
    del treinador, parte di JudoArteVida, mese per mese e corso per corso."""
    return await service.accounts(db, organization_id=current_user.organization_id, year=year or utcnow().year,
                                  course_ids=[course_id] if course_id else None)
