"""Le API dei testi delle email (service.py), per il superadmin dalla
console: elenco, modifica, ritorno al testo predefinito, anteprima con il
marchio di JudoArteVida o di un club, e un'email di prova a sé."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.email import send_html_email_best_effort
from app.core.email_templates import render_email, text_to_html
from app.domains.club.email_brand import club_brand
from app.domains.club.scope import CLUBS_MANAGE
from app.domains.email_texts import service
from app.domains.users.models import User

router = APIRouter(prefix="/email-templates", tags=["email-templates"])


async def _superadmin(
    current_user: CurrentUser = Depends(require_permission(CLUBS_MANAGE)), db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    user = await db.get(User, current_user.user_id)
    if user is None or user.club_id is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "I testi delle email li cura lo staff di JudoArteVida.")
    return current_user


class TextWrite(BaseModel):
    subject: str = Field(max_length=200)
    heading: str = Field(max_length=200)
    body: str = Field(max_length=8000)
    cta_label: str | None = Field(default=None, max_length=80)


class PreviewWrite(TextWrite):
    #: Il club di cui usare il marchio; None = JudoArteVida.
    club_id: uuid.UUID | None = None


def _raise(exc: service.EmailTextError) -> None:
    raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.get("")
async def list_texts(_: CurrentUser = Depends(_superadmin), db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await service.list_texts(db)


@router.put("/{key}")
async def save_text(key: str, payload: TextWrite, user: CurrentUser = Depends(_superadmin), db: AsyncSession = Depends(get_db)) -> dict:
    try:
        return await service.save(db, key=key, data=payload.model_dump(), actor_user_id=user.user_id)
    except service.EmailTextError as exc:
        _raise(exc)


@router.delete("/{key}")
async def reset_text(key: str, _: CurrentUser = Depends(_superadmin), db: AsyncSession = Depends(get_db)) -> dict:
    try:
        return await service.reset(db, key=key)
    except service.EmailTextError as exc:
        _raise(exc)


async def _render(db: AsyncSession, key: str, payload: PreviewWrite) -> tuple[str, str, str]:
    if key not in service.TEXTS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Email non trovata.")
    brand = await club_brand(db, payload.club_id)
    values = {**service.sample_values(key), "marca": brand.name}
    subject = service.fill(payload.subject, values)
    body = service.fill(payload.body, values)
    has_cta = service.TEXTS[key].cta_label is not None
    html = render_email(
        preheader=subject, heading=service.fill(payload.heading, values), body_html=text_to_html(body),
        cta_label=payload.cta_label if has_cta else None, cta_url="https://jav.ecodo.ai/login" if has_cta else None,
        brand=brand,
    )
    return subject, html, body


@router.post("/{key}/preview")
async def preview_text(key: str, payload: PreviewWrite, _: CurrentUser = Depends(_superadmin), db: AsyncSession = Depends(get_db)) -> dict:
    subject, html, _body = await _render(db, key, payload)
    return {"subject": subject, "html": html}


@router.post("/{key}/test")
async def test_text(key: str, payload: PreviewWrite, user: CurrentUser = Depends(_superadmin), db: AsyncSession = Depends(get_db)) -> dict:
    """Manda l'anteprima a chi la chiede, con i valori d'esempio."""
    subject, html, body = await _render(db, key, payload)
    me = await db.get(User, user.user_id)
    sent = send_html_email_best_effort(context=f"email-template test ({key})", to=me.email, subject=f"[Prova] {subject}",
                                       html_body=html, text_body=body)
    return {"sent": sent, "to": me.email}
