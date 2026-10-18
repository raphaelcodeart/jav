"""Le API dei judogi e della lista dei desideri (club/judogi.py).

- `/club/judogi/...`        famiglie e atleti (`club.athlete`): il listino
  per il calcolatore, il conto, l'ordine (titolare o atleta maggiorenne),
  gli ordini dei miei atleti;
- `/club/wishlist/...`      la lista dei desideri: l'atleta minorenne
  aggiunge, il titolare decide;
- `/club/admin/judogi/...`  la segreteria (`club.manage`): ordini, stati,
  CSV per il fornitore, listino e impostazioni.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.domains.club import judogi
from app.domains.club import lessons as lessons_service
from app.domains.club import service as club_service
from app.domains.club.models import Club, ClubAthlete
from app.domains.club.scope import ClubUser, require_club_permission

MEMBER = "club.athlete"
MANAGE = "club.manage"

member_router = APIRouter(prefix="/club/judogi", tags=["club"])
wishlist_router = APIRouter(prefix="/club/wishlist", tags=["club"])
admin_router = APIRouter(prefix="/club/admin/judogi", tags=["club-admin"])


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


# --- Schemi ---------------------------------------------------------------------------------------


class TradeIn(BaseModel):
    kimono_type: str | None = None
    color: str | None = None
    brand: str = Field(default="", max_length=60)
    size_cm: int | None = Field(default=None, ge=80, le=220)
    #: Un judogi dell'armadio dell'atleta: il server legge tipo, colore,
    #: marca e taglia dall'ordine, e alla consegna del nuovo lo ritira.
    owned_order_id: uuid.UUID | None = None


class Choice(BaseModel):
    """Le scelte del calcolatore: mai un prezzo."""

    kimono_type: str
    color: str
    brand: str = Field(max_length=60)
    size_cm: int | None = Field(default=None, ge=80, le=220)
    height_cm: int | None = Field(default=None, ge=60, le=230)
    trade_in: TradeIn | None = None


class QuoteWrite(Choice):
    athlete_id: uuid.UUID | None = None


class OrderWrite(Choice):
    athlete_id: uuid.UUID
    kimono_name: str = Field(max_length=100)
    notes: str | None = Field(default=None, max_length=2000)
    #: Il desiderio da cui nasce l'ordine, se c'è.
    wish_id: uuid.UUID | None = None


class WishJudogi(Choice):
    kimono_name: str | None = Field(default=None, max_length=100)


class WishWrite(BaseModel):
    athlete_id: uuid.UUID
    kind: Literal["PRODUCT", "JUDOGI"]
    product_id: uuid.UUID | None = None
    variant_id: uuid.UUID | None = None
    judogi: WishJudogi | None = None
    note: str | None = Field(default=None, max_length=300)


class WishDecision(BaseModel):
    status: Literal["ORDERED", "DISMISSED"]


class AdminOrderWrite(Choice):
    athlete_id: uuid.UUID
    kimono_name: str = Field(max_length=100)
    notes: str | None = Field(default=None, max_length=2000)


class AdminOrderUpdate(BaseModel):
    status: str | None = None
    internal_notes: str | None = Field(default=None, max_length=4000)
    price_cents: int | None = Field(default=None, ge=0)


class SettingsWrite(BaseModel):
    customization_cents: int | None = Field(default=None, ge=0, le=100_000)
    trade_in_percent: int | None = Field(default=None, ge=0, le=100)


class PriceWrite(BaseModel):
    kimono_type: str
    color: str
    brand: str = Field(max_length=60)
    size_cm: int = Field(ge=80, le=220)
    price_cents: int = Field(ge=0, le=10_000_000)
    active: bool = True


class PriceUpdate(BaseModel):
    price_cents: int | None = Field(default=None, ge=0, le=10_000_000)
    active: bool | None = None


# --- Famiglie e atleti ----------------------------------------------------------------------------


@member_router.get("/catalog")
async def catalog(
    height_cm: int | None = Query(default=None, ge=60, le=230),
    current_user: ClubUser = Depends(require_club_permission(MEMBER)), db: AsyncSession = Depends(get_db),
) -> dict:
    """Il listino del club come lo percorre il calcolatore, con la taglia
    consigliata per l'altezza."""
    club = await _club(db, current_user)
    rows = await judogi.price_rows(db, club_id=club.id)
    models = await judogi.models_of(db, club_id=club.id)
    return {**judogi.settings_of(club), "types": judogi.price_tree(rows, height_cm=height_cm, models=models)}


@member_router.get("/athletes")
async def my_athletes(
    current_user: ClubUser = Depends(require_club_permission(MEMBER)), db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Per chi posso ordinare (BUY) o desiderare (WISH)."""
    today = await _today(db, current_user)
    mine = await judogi.my_athletes(db, scope=current_user.scope, user_id=current_user.user_id, today=today)
    from app.domains.club import loja

    hc = await loja.high_competition_map(db, [a for a, _m in mine])
    return [judogi.athlete_dict(a, mode, today, high_competition=hc[a.id]) for a, mode in mine]


@member_router.post("/quote")
async def quote(
    payload: QuoteWrite,
    current_user: ClubUser = Depends(require_club_permission(MEMBER)), db: AsyncSession = Depends(get_db),
) -> dict:
    club = await _club(db, current_user)
    height = payload.height_cm
    try:
        # L'atleta si verifica sempre: la permuta può leggere il suo armadio.
        if payload.athlete_id is not None:
            athlete, _mode = await judogi.athlete_for(
                db, scope=current_user.scope, user_id=current_user.user_id, athlete_id=payload.athlete_id,
                today=await _today(db, current_user),
            )
            height = height or athlete.height_cm
        result = await judogi.quote(db, club=club, choice=payload.model_dump(), height_cm=height,
                                    athlete_id=payload.athlete_id)
    except club_service.ClubError as exc:
        _raise(exc)
    return result


@member_router.post("/orders", status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: OrderWrite,
    current_user: ClubUser = Depends(require_club_permission(MEMBER)), db: AsyncSession = Depends(get_db),
) -> dict:
    """Il titolare (o l'atleta maggiorenne per sé) ordina: il conto si rifà
    qui e nasce la quota da pagare."""
    club = await _club(db, current_user)
    today = await _today(db, current_user)
    try:
        athlete, mode = await judogi.athlete_for(
            db, scope=current_user.scope, user_id=current_user.user_id, athlete_id=payload.athlete_id, today=today,
        )
        if mode != "BUY":
            raise club_service.ClubValidationError(
                "Il judogi lo ordina chi paga: mettilo nella lista dei desideri e lo vedrà il titolare."
            )
        wish = None
        if payload.wish_id is not None:
            wish, _owner, _m = await judogi.get_wish(
                db, scope=current_user.scope, user_id=current_user.user_id, wish_id=payload.wish_id, today=today,
            )
            if wish.athlete_id != athlete.id or wish.kind != "JUDOGI" or wish.status != "OPEN":
                raise club_service.ClubValidationError("Questo desiderio non è più aperto.")
        order = await judogi.create_order(
            db, scope=current_user.scope, club=club, athlete=athlete, actor_user_id=current_user.user_id,
            data=payload.model_dump(), today=today, wish=wish,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return judogi.order_dict(order, athlete)


@member_router.get("/orders")
async def my_orders(
    current_user: ClubUser = Depends(require_club_permission(MEMBER)), db: AsyncSession = Depends(get_db),
) -> list[dict]:
    today = await _today(db, current_user)
    mine = await judogi.my_athletes(db, scope=current_user.scope, user_id=current_user.user_id, today=today)
    return await judogi.orders_of(db, athlete_ids=[a.id for a, _m in mine])


# --- La lista dei desideri --------------------------------------------------------------------------


@wishlist_router.get("")
async def list_wishes(
    current_user: ClubUser = Depends(require_club_permission(MEMBER)), db: AsyncSession = Depends(get_db),
) -> list[dict]:
    return await judogi.list_wishes(
        db, scope=current_user.scope, user_id=current_user.user_id, today=await _today(db, current_user),
    )


@wishlist_router.post("", status_code=status.HTTP_201_CREATED)
async def add_wish(
    payload: WishWrite,
    current_user: ClubUser = Depends(require_club_permission(MEMBER)), db: AsyncSession = Depends(get_db),
) -> dict:
    club = await _club(db, current_user)
    today = await _today(db, current_user)
    try:
        athlete, _mode = await judogi.athlete_for(
            db, scope=current_user.scope, user_id=current_user.user_id, athlete_id=payload.athlete_id, today=today,
        )
        wish = await judogi.add_wish(
            db, scope=current_user.scope, club=club, athlete=athlete, actor_user_id=current_user.user_id,
            data={**payload.model_dump(), "judogi": payload.judogi.model_dump() if payload.judogi else None},
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return {"id": wish.id, "status": wish.status}


@wishlist_router.patch("/{wish_id}")
async def decide_wish(
    wish_id: uuid.UUID, payload: WishDecision,
    current_user: ClubUser = Depends(require_club_permission(MEMBER)), db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        wish = await judogi.decide_wish(
            db, scope=current_user.scope, user_id=current_user.user_id, wish_id=wish_id, status=payload.status,
            today=await _today(db, current_user),
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return {"id": wish.id, "status": wish.status}


@wishlist_router.delete("/{wish_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_wish(
    wish_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MEMBER)), db: AsyncSession = Depends(get_db),
) -> Response:
    try:
        await judogi.remove_wish(
            db, scope=current_user.scope, user_id=current_user.user_id, wish_id=wish_id,
            today=await _today(db, current_user),
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- La segreteria ------------------------------------------------------------------------------------


@admin_router.get("/orders")
async def admin_orders(
    order_status: str | None = Query(default=None, alias="status"), q: str | None = Query(default=None, max_length=100),
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> list[dict]:
    return await judogi.admin_orders(db, scope=current_user.scope, status=order_status, search=q)


@admin_router.get("/orders.csv")
async def admin_orders_csv(
    order_status: str | None = Query(default=None, alias="status"),
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> Response:
    """Il file per il fornitore: per default gli ordini in attesa."""
    rows = await judogi.admin_orders(db, scope=current_user.scope, status=order_status or "PENDING")
    body = "﻿" + judogi.orders_csv(rows)  # il BOM: Excel apre gli accenti giusti
    return Response(body, media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": 'attachment; filename="pedidos-judogi.csv"',
    })


@admin_router.post("/orders", status_code=status.HTTP_201_CREATED)
async def admin_create_order(
    payload: AdminOrderWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> dict:
    """La segreteria ordina per un atleta (al banco, al telefono)."""
    club = await _club(db, current_user)
    athlete = await db.get(ClubAthlete, payload.athlete_id)
    if athlete is None or athlete.club_id != current_user.club_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Atleta non trovato.")
    try:
        # Al banco la segreteria sa per chi è: le regole della Loja valgono
        # per le famiglie.
        order = await judogi.create_order(
            db, scope=current_user.scope, club=club, athlete=athlete, actor_user_id=current_user.user_id,
            data=payload.model_dump(), today=await _today(db, current_user), check_rules=False,
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return judogi.order_dict(order, athlete)


@admin_router.patch("/orders/{order_id}")
async def admin_update_order(
    order_id: uuid.UUID, payload: AdminOrderUpdate,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        order = await judogi.update_order(
            db, scope=current_user.scope, order_id=order_id, actor_user_id=current_user.user_id,
            data=payload.model_dump(exclude_unset=True), today=await _today(db, current_user),
        )
    except club_service.ClubError as exc:
        _raise(exc)
    rows = await judogi.orders_of(db, athlete_ids=[order.athlete_id])
    return next(r for r in rows if r["id"] == order.id)


@admin_router.get("/settings")
async def get_settings(
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> dict:
    return judogi.settings_of(await _club(db, current_user))


@admin_router.put("/settings")
async def put_settings(
    payload: SettingsWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        result = await judogi.update_settings(
            db, club=await _club(db, current_user), actor_user_id=current_user.user_id,
            data=payload.model_dump(exclude_none=True),
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return result


@admin_router.get("/prices")
async def list_prices(
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> list[dict]:
    rows = await judogi.price_rows(db, club_id=current_user.club_id, active_only=False)
    return [judogi.price_dict(r) for r in rows]


@admin_router.post("/prices")
async def upsert_price(
    payload: PriceWrite,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        row = await judogi.upsert_price(
            db, scope=current_user.scope, actor_user_id=current_user.user_id, data=payload.model_dump(),
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return judogi.price_dict(row)


@admin_router.post("/prices/seed")
async def seed_prices(
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> dict:
    """Il listino di partenza, in un club che non ne ha."""
    added = await judogi.seed_prices(db, club=await _club(db, current_user))
    await db.commit()
    return {"added": added}


@admin_router.patch("/prices/{price_id}")
async def update_price(
    price_id: uuid.UUID, payload: PriceUpdate,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        row = await judogi.update_price(
            db, scope=current_user.scope, price_id=price_id, actor_user_id=current_user.user_id,
            data=payload.model_dump(exclude_unset=True),
        )
    except club_service.ClubError as exc:
        _raise(exc)
    return judogi.price_dict(row)


@admin_router.delete("/prices/{price_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_price(
    price_id: uuid.UUID,
    current_user: ClubUser = Depends(require_club_permission(MANAGE)), db: AsyncSession = Depends(get_db),
) -> Response:
    try:
        await judogi.delete_price(db, scope=current_user.scope, price_id=price_id, actor_user_id=current_user.user_id)
    except club_service.ClubError as exc:
        _raise(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
