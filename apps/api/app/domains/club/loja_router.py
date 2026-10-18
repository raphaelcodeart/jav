"""Le API della Loja del club (club/loja.py).

- `/club/loja/...`          famiglie e atleti (`club.athlete`): la vetrina
  per un atleta, il carrello, l'ordine (tutto il carrello o «Comprar já»);
- `/club/staff/loja/...`    segreteria e treinador (`club.instruct`):
  l'armadio dei judogi (anche per una prova), un judogi che l'atleta aveva
  già, un judogi che esce dall'armadio, il segno di alta competizione;
- `/club/admin/loja/...`    la segreteria (`club.manage`): i modelli di
  judogi con le foto.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.domains.audit import service as audit_service
from app.domains.club import judogi, loja
from app.domains.club import lessons as lessons_service
from app.domains.club import service as club_service
from app.domains.club.judogi_router import TradeIn
from app.domains.club.models import Club
from app.domains.club.operations_models import ClubJudogiModel
from app.domains.club.scope import ClubUser, require_club_permission
from app.domains.rbac.service import get_permission_codes_for_user

MEMBER = "club.athlete"
INSTRUCT = "club.instruct"
MANAGE = "club.manage"

member_router = APIRouter(prefix="/club/loja", tags=["club"])
staff_router = APIRouter(prefix="/club/staff/loja", tags=["club-staff"])
admin_router = APIRouter(prefix="/club/admin/loja", tags=["club-admin"])


def _raise(exc: club_service.ClubError) -> None:
    code = status.HTTP_404_NOT_FOUND if isinstance(exc, club_service.ClubNotFoundError) else status.HTTP_400_BAD_REQUEST
    raise HTTPException(code, str(exc)) from exc


async def _club(db: AsyncSession, user: ClubUser) -> Club:
    club = await db.get(Club, user.club_id)
    if club is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Club non trovato.")
    return club


async def _today(db: AsyncSession, user: ClubUser):
    return (await lessons_service.club_now(db, club_id=user.club_id)).date()


async def _manager(db: AsyncSession, user: ClubUser) -> bool:
    if not user.home:
        return False
    granted = await get_permission_codes_for_user(db, user_id=user.user_id, organization_id=user.organization_id)
    return MANAGE in granted


# --- Schemi ---------------------------------------------------------------------------------------


class JudogiLine(BaseModel):
    """Il judogi configurato: solo scelte, mai un prezzo."""

    kimono_type: str
    color: str
    brand: str = Field(max_length=60)
    size_cm: int | None = Field(default=None, ge=80, le=220)
    height_cm: int | None = Field(default=None, ge=60, le=230)
    kimono_name: str = Field(max_length=100)
    notes: str | None = Field(default=None, max_length=2000)
    trade_in: TradeIn | None = None
    #: Il desiderio (lista dei desideri) da cui nasce: si chiude all'ordine.
    wish_id: uuid.UUID | None = None


class LineWrite(BaseModel):
    athlete_id: uuid.UUID
    kind: Literal["JUDOGI", "PRODUCT"]
    judogi: JudogiLine | None = None
    variant_id: uuid.UUID | None = None
    quantity: int = Field(default=1, ge=1, le=20)
    #: Il nome da stampare, se il prodotto lo chiede.
    name: str | None = Field(default=None, max_length=100)


class QuantityWrite(BaseModel):
    quantity: int = Field(ge=1, le=20)


class CheckoutWrite(BaseModel):
    #: Le righe da ordinare; vuoto = tutto il carrello.
    item_ids: list[uuid.UUID] | None = None


class OwnedJudogiWrite(BaseModel):
    athlete_id: uuid.UUID
    kimono_type: str
    color: str
    brand: str = Field(max_length=60)
    size_cm: int = Field(ge=80, le=220)
    kimono_name: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)


class RetireWrite(BaseModel):
    reason: Literal["TRADED_IN", "OUTGROWN", "WORN_OUT", "LOST"]


class HighCompetitionWrite(BaseModel):
    value: bool


class ModelUpdate(BaseModel):
    description: str | None = Field(default=None, max_length=2000)
    image_url: str | None = Field(default=None, max_length=1000)
    images: list[str] | None = Field(default=None, max_length=12)


def _model_dict(m: ClubJudogiModel) -> dict:
    return {"id": m.id, "kimono_type": m.kimono_type, "type_label": judogi.TYPE_PT[m.kimono_type], "brand": m.brand,
            "color": m.color, "color_label": judogi.COLOR_PT[m.color], "description": m.description,
            "image_url": m.image_url, "images": m.images or []}


# --- Famiglie e atleti ----------------------------------------------------------------------------


@member_router.get("/athletes/{athlete_id}")
async def shop(
    athlete_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MEMBER)), db: AsyncSession = Depends(get_db),
) -> dict:
    """La Loja per un atleta: judogi, equipaggiamento che è per lui, kit."""
    try:
        return await loja.shop(db, scope=current_user.scope, club=await _club(db, current_user),
                               user_id=current_user.user_id, athlete_id=athlete_id,
                               today=await _today(db, current_user))
    except club_service.ClubError as exc:
        _raise(exc)
    raise AssertionError


@member_router.get("/cart")
async def get_cart(
    current_user: ClubUser = Depends(require_club_permission(MEMBER)), db: AsyncSession = Depends(get_db),
) -> dict:
    return await loja.cart(db, scope=current_user.scope, club=await _club(db, current_user),
                           user_id=current_user.user_id, today=await _today(db, current_user))


@member_router.post("/cart", status_code=status.HTTP_201_CREATED)
async def add_to_cart(
    payload: LineWrite,
    current_user: ClubUser = Depends(require_club_permission(MEMBER)), db: AsyncSession = Depends(get_db),
) -> dict:
    club = await _club(db, current_user)
    today = await _today(db, current_user)
    try:
        await loja.add_to_cart(db, scope=current_user.scope, club=club, user_id=current_user.user_id,
                               data=payload.model_dump(), today=today)
    except club_service.ClubError as exc:
        _raise(exc)
    return await loja.cart(db, scope=current_user.scope, club=club, user_id=current_user.user_id, today=today)


@member_router.patch("/cart/{item_id}")
async def update_cart_item(
    item_id: uuid.UUID, payload: QuantityWrite,
    current_user: ClubUser = Depends(require_club_permission(MEMBER)), db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        await loja.update_cart_item(db, scope=current_user.scope, user_id=current_user.user_id, item_id=item_id,
                                    quantity=payload.quantity)
    except club_service.ClubError as exc:
        _raise(exc)
    return await loja.cart(db, scope=current_user.scope, club=await _club(db, current_user),
                           user_id=current_user.user_id, today=await _today(db, current_user))


@member_router.delete("/cart/{item_id}")
async def remove_cart_item(
    item_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MEMBER)), db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        await loja.remove_cart_item(db, scope=current_user.scope, user_id=current_user.user_id, item_id=item_id)
    except club_service.ClubError as exc:
        _raise(exc)
    return await loja.cart(db, scope=current_user.scope, club=await _club(db, current_user),
                           user_id=current_user.user_id, today=await _today(db, current_user))


@member_router.post("/checkout", status_code=status.HTTP_201_CREATED)
async def checkout(
    payload: CheckoutWrite,
    current_user: ClubUser = Depends(require_club_permission(MEMBER)), db: AsyncSession = Depends(get_db),
) -> dict:
    """Ogni riga del carrello diventa un ordine con la sua quota; la risposta
    porta le quote, da pagare subito tutte insieme se la famiglia vuole."""
    try:
        return await loja.checkout(db, scope=current_user.scope, club=await _club(db, current_user),
                                   user_id=current_user.user_id, item_ids=payload.item_ids,
                                   today=await _today(db, current_user))
    except club_service.ClubError as exc:
        _raise(exc)
    raise AssertionError


@member_router.post("/buy-now", status_code=status.HTTP_201_CREATED)
async def buy_now(
    payload: LineWrite,
    current_user: ClubUser = Depends(require_club_permission(MEMBER)), db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        return await loja.buy_now(db, scope=current_user.scope, club=await _club(db, current_user),
                                  user_id=current_user.user_id, data=payload.model_dump(),
                                  today=await _today(db, current_user))
    except club_service.ClubError as exc:
        _raise(exc)
    raise AssertionError


# --- Segreteria e treinador -----------------------------------------------------------------------


@staff_router.get("/judogis")
async def staff_judogis(
    competition_id: uuid.UUID | None = Query(default=None),
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> dict:
    """L'armadio dei judogi degli atleti che vedo; con una prova, dei suoi iscritti."""
    try:
        return await loja.staff_judogis(db, scope=current_user.scope, user_id=current_user.user_id,
                                        manager=await _manager(db, current_user), competition_id=competition_id,
                                        today=await _today(db, current_user))
    except club_service.ClubError as exc:
        _raise(exc)
    raise AssertionError


@staff_router.post("/judogis", status_code=status.HTTP_201_CREATED)
async def add_owned_judogi(
    payload: OwnedJudogiWrite,
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        athlete = await loja.staff_athlete(db, scope=current_user.scope, user_id=current_user.user_id,
                                           manager=await _manager(db, current_user), athlete_id=payload.athlete_id)
        order = await loja.add_owned_judogi(db, scope=current_user.scope, athlete=athlete,
                                            actor_user_id=current_user.user_id, data=payload.model_dump(),
                                            today=await _today(db, current_user))
    except club_service.ClubError as exc:
        _raise(exc)
    return judogi.order_dict(order, athlete)


@staff_router.post("/judogis/{order_id}/retire")
async def retire_judogi(
    order_id: uuid.UUID, payload: RetireWrite,
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        order = await loja.retire_judogi(db, scope=current_user.scope, user_id=current_user.user_id,
                                         manager=await _manager(db, current_user), order_id=order_id,
                                         reason=payload.reason, today=await _today(db, current_user))
    except club_service.ClubError as exc:
        _raise(exc)
    return judogi.order_dict(order)


@staff_router.put("/athletes/{athlete_id}/high-competition")
async def set_high_competition(
    athlete_id: uuid.UUID, payload: HighCompetitionWrite,
    current_user: ClubUser = Depends(require_club_permission(INSTRUCT)), db: AsyncSession = Depends(get_db),
) -> dict:
    """La segreteria o il treinador che segue l'atleta segnano l'alta
    competizione (solo nei piani che la permettono)."""
    try:
        athlete = await loja.staff_athlete(db, scope=current_user.scope, user_id=current_user.user_id,
                                           manager=await _manager(db, current_user), athlete_id=athlete_id)
        athlete = await loja.set_high_competition(db, scope=current_user.scope, athlete=athlete,
                                                  actor_user_id=current_user.user_id, value=payload.value)
    except club_service.ClubError as exc:
        _raise(exc)
    return {"athlete_id": athlete.id, "high_competition_flag": athlete.high_competition,
            "high_competition": await loja.is_high_competition(db, athlete)}


# --- La segreteria: i modelli di judogi ------------------------------------------------------------


@admin_router.get("/judogi-models")
async def list_models(
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Le schede dei modelli (una per tipo + marca + colore del listino)."""
    if await judogi.ensure_models(db, club_id=current_user.club_id, organization_id=current_user.organization_id):
        await db.commit()
    rows = (await db.execute(select(ClubJudogiModel).where(ClubJudogiModel.club_id == current_user.club_id)
                             .order_by(ClubJudogiModel.kimono_type, ClubJudogiModel.brand, ClubJudogiModel.color))).scalars()
    return [_model_dict(m) for m in rows]


@admin_router.patch("/judogi-models/{model_id}")
async def update_model(
    model_id: uuid.UUID, payload: ModelUpdate,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> dict:
    """Foto e descrizione di un modello. Le foto si caricano con
    `/club/admin/shop/images`, come quelle dei prodotti del club."""
    model = await db.get(ClubJudogiModel, model_id)
    if model is None or model.club_id != current_user.club_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Modello non trovato.")
    data = payload.model_dump(exclude_unset=True)
    if "description" in data:
        model.description = (data["description"] or "").strip() or None
    if "images" in data and data["images"] is not None:
        model.images = data["images"]
        model.image_url = data["images"][0] if data["images"] else None
    if "image_url" in data:
        model.image_url = data["image_url"]
    await audit_service.record(
        db, organization_id=current_user.organization_id, actor_user_id=current_user.user_id,
        action="club.judogi_model_updated", entity_type="club_judogi_model", entity_id=str(model.id),
        new_value={"fields": sorted(data)},
    )
    await db.commit()
    await db.refresh(model)
    return _model_dict(model)
