"""La richiesta di trasporto per una gara o uno stage.

Il club chiede il pullman al comune (o all'ente che lo sostiene) quando sa
quanti sono: cioè quando le iscrizioni sono chiuse. Allora il sistema scrive
da solo la lettera (la bozza: evento, date, luogo, partenza e ritorno, numero
di atleti e accompagnatori, elenco degli iscritti) nella lingua del club, e
avvisa la segreteria. La segreteria la rilegge, la corregge se serve, e la
manda con un clic. Se l'evento è impostato così (`transport_auto_send`), la
lettera parte da sola alla chiusura.

La lettera parte dall'indirizzo della piattaforma con la risposta indirizzata
al club (Reply-To) e una copia nella sua casella: chi risponde, risponde al
club. Il testo salvato è esattamente quello partito.
"""

import logging
import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.club.models import (
    Club,
    ClubAthlete,
    ClubCompetition,
    ClubCompetitionEntry,
    ClubTransportRequest,
)
from app.domains.club.scope import ClubScope, scope_of
from app.domains.club.service import ClubNotFoundError, ClubValidationError

logger = logging.getLogger(__name__)

_MONTHS = {
    "pt": ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
           "outubro", "novembro", "dezembro"),
    "it": ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre",
           "ottobre", "novembre", "dicembre"),
    "en": ("January", "February", "March", "April", "May", "June", "July", "August", "September",
           "October", "November", "December"),
}


def _day(d: date, lang: str) -> str:
    month = _MONTHS[lang][d.month - 1]
    if lang == "en":
        return f"{d.day} {month} {d.year}"
    return f"{d.day} {'de ' if lang == 'pt' else ''}{month}{' de' if lang == 'pt' else ''} {d.year}"


def _dates(comp: ClubCompetition, lang: str) -> str:
    one = _day(comp.starts_on, lang)
    if comp.ends_on == comp.starts_on:
        return {"pt": f"no dia {one}", "it": f"il {one}", "en": f"on {one}"}[lang]
    two = _day(comp.ends_on, lang)
    return {"pt": f"de {one} a {two}", "it": f"dal {one} al {two}", "en": f"from {one} to {two}"}[lang]


async def registered_athletes(db: AsyncSession, *, competition_id: uuid.UUID) -> list[ClubAthlete]:
    return list(
        (
            await db.execute(
                select(ClubAthlete)
                .join(ClubCompetitionEntry, ClubCompetitionEntry.athlete_id == ClubAthlete.id)
                .where(
                    ClubCompetitionEntry.competition_id == competition_id,
                    ClubCompetitionEntry.status == "REGISTERED",
                )
                .order_by(ClubAthlete.last_name, ClubAthlete.first_name)
            )
        ).scalars()
    )


def compose(*, club: Club, comp: ClubCompetition, athletes: list[ClubAthlete]) -> tuple[str, str]:
    """(oggetto, testo) della lettera, nella lingua del club. Testo semplice:
    è quello che la segreteria vede e corregge (core/email_templates.py::
    render_letter lo impagina)."""
    settings = club.settings or {}
    lang = settings.get("letters_language") or "pt"
    if lang not in _MONTHS:
        lang = "pt"
    n, m = len(athletes), comp.transport_companions or 0
    entity = comp.transport_entity_name or ""
    where = comp.location or "—"
    roster = "\n".join(f"- {a.first_name} {a.last_name} ({a.birth_date.year})" for a in athletes) or "—"
    contact = settings.get("contact_email") or ""
    if lang == "pt":
        what = "o estágio" if comp.kind == "STAGE" else "a prova"
        subject = f"Pedido de transporte – {comp.name} ({_day(comp.starts_on, lang)})"
        lines = [
            f"Exmos. Senhores{' da ' + entity if entity else ''},",
            (f"O {club.name} vem por este meio solicitar o apoio de V. Exas. no transporte dos seus atletas "
            f"para {what} «{comp.name}», que se realiza em {where} {_dates(comp, lang)}."),
            f"Viajarão {n} atletas e {m} acompanhantes, num total de {n + m} pessoas."
            + (f"\nPartida: {comp.transport_departure}" if comp.transport_departure else "")
            + (f"\nRegresso: {comp.transport_return}" if comp.transport_return else ""),
            comp.transport_notes or "",
            f"Atletas inscritos:\n{roster}",
            "Agradecemos desde já a atenção e ficamos ao dispor para qualquer esclarecimento.",
            f"Com os melhores cumprimentos,\n{club.name}" + (f"\n{contact}" if contact else ""),
        ]
    elif lang == "it":
        what = "lo stage" if comp.kind == "STAGE" else "la gara"
        subject = f"Richiesta di trasporto – {comp.name} ({_day(comp.starts_on, lang)})"
        lines = [
            f"Gentili{' ' + entity if entity else ''},",
            (f"il {club.name} chiede il vostro sostegno per il trasporto dei suoi atleti per {what} "
            f"«{comp.name}», che si svolge a {where} {_dates(comp, lang)}."),
            f"Viaggeranno {n} atleti e {m} accompagnatori, in tutto {n + m} persone."
            + (f"\nPartenza: {comp.transport_departure}" if comp.transport_departure else "")
            + (f"\nRitorno: {comp.transport_return}" if comp.transport_return else ""),
            comp.transport_notes or "",
            f"Atleti iscritti:\n{roster}",
            "Vi ringraziamo per l'attenzione e restiamo a disposizione per qualsiasi chiarimento.",
            f"Cordiali saluti,\n{club.name}" + (f"\n{contact}" if contact else ""),
        ]
    else:
        what = "the training camp" if comp.kind == "STAGE" else "the competition"
        subject = f"Transport request – {comp.name} ({_day(comp.starts_on, lang)})"
        lines = [
            f"Dear {entity or 'Sir or Madam'},",
            (f"{club.name} kindly requests your support with transport for its athletes to {what} "
            f"“{comp.name}”, taking place in {where} {_dates(comp, lang)}."),
            f"{n} athletes and {m} companions will travel, {n + m} people in total."
            + (f"\nDeparture: {comp.transport_departure}" if comp.transport_departure else "")
            + (f"\nReturn: {comp.transport_return}" if comp.transport_return else ""),
            comp.transport_notes or "",
            f"Registered athletes:\n{roster}",
            "Thank you for your attention; we remain available for any further information.",
            f"Kind regards,\n{club.name}" + (f"\n{contact}" if contact else ""),
        ]
    return subject[:300], "\n\n".join(line for line in lines if line.strip())


async def _competition(db: AsyncSession, *, scope: ClubScope, competition_id: uuid.UUID) -> ClubCompetition:
    comp = await db.get(ClubCompetition, competition_id)
    if comp is None or comp.club_id != scope.club_id:
        # Anche un evento della rete: la richiesta di trasporto è del club
        # che organizza; per quelli della rete vale l'indicazione
        # `transport_mode` dell'evento.
        raise ClubNotFoundError("Evento non trovato.")
    return comp


async def _request(db: AsyncSession, *, competition_id: uuid.UUID) -> ClubTransportRequest | None:
    return (
        await db.execute(select(ClubTransportRequest).where(ClubTransportRequest.competition_id == competition_id))
    ).scalar_one_or_none()


async def current_count(db: AsyncSession, *, competition_id: uuid.UUID) -> int:
    return (
        await db.execute(
            select(func.count()).where(
                ClubCompetitionEntry.competition_id == competition_id, ClubCompetitionEntry.status == "REGISTERED"
            )
        )
    ).scalar_one()


async def ensure_draft(db: AsyncSession, *, comp: ClubCompetition) -> ClubTransportRequest:
    """La bozza dell'evento, scritta adesso se non c'è (una per evento:
    vincolo UNIQUE). Non committa."""
    club = await db.get(Club, comp.club_id)
    athletes = await registered_athletes(db, competition_id=comp.id)
    subject, body = compose(club=club, comp=comp, athletes=athletes)
    await db.execute(
        insert(ClubTransportRequest)
        .values(
            id=uuid.uuid4(), created_at=utcnow(), **scope_of(comp).columns(), competition_id=comp.id,
            to_email=comp.transport_entity_email, subject=subject, body_text=body, status="DRAFT",
            athletes_count=len(athletes),
        )
        .on_conflict_do_nothing(constraint="uq_club_transport_requests_competition_club")
    )
    return await _request(db, competition_id=comp.id)


async def get_or_prepare(db: AsyncSession, *, scope: ClubScope, competition_id: uuid.UUID) -> ClubTransportRequest:
    comp = await _competition(db, scope=scope, competition_id=competition_id)
    request = await _request(db, competition_id=comp.id) or await ensure_draft(db, comp=comp)
    await db.commit()
    return request


async def regenerate(db: AsyncSession, *, scope: ClubScope, competition_id: uuid.UUID) -> ClubTransportRequest:
    """Riscrive la bozza con gli iscritti e i dati di adesso (le correzioni a
    mano si perdono: lo dice l'interfaccia prima di farlo)."""
    comp = await _competition(db, scope=scope, competition_id=competition_id)
    request = await _request(db, competition_id=comp.id) or await ensure_draft(db, comp=comp)
    club = await db.get(Club, comp.club_id)
    athletes = await registered_athletes(db, competition_id=comp.id)
    request.subject, request.body_text = compose(club=club, comp=comp, athletes=athletes)
    request.athletes_count = len(athletes)
    request.to_email = comp.transport_entity_email or request.to_email
    await db.commit()
    await db.refresh(request)
    return request


async def save(
    db: AsyncSession, *, scope: ClubScope, competition_id: uuid.UUID, to_email: str, subject: str, body_text: str,
) -> ClubTransportRequest:
    request = await get_or_prepare(db, scope=scope, competition_id=competition_id)
    request.to_email, request.subject, request.body_text = to_email.strip(), subject.strip(), body_text
    await db.commit()
    await db.refresh(request)
    return request


async def send(
    db: AsyncSession, *, scope: ClubScope, competition_id: uuid.UUID, to_email: str, subject: str, body_text: str,
    actor_user_id: uuid.UUID | None,
) -> ClubTransportRequest:
    """Manda la lettera così com'è (dopo averla salvata). Se l'invio non
    riesce non risulta inviata, e la segreteria legge perché."""
    from app.core.email import EmailNotConfiguredError, send_html_email
    from app.core.email_templates import render_letter

    if "@" not in to_email:
        raise ClubValidationError("Indica l'indirizzo email dell'ente a cui chiedere il trasporto.")
    request = await save(
        db, scope=scope, competition_id=competition_id, to_email=to_email, subject=subject, body_text=body_text
    )
    from app.domains.club.email_brand import club_brand

    club = await db.get(Club, scope.club_id)
    contact = (club.settings or {}).get("contact_email") or None
    brand = await club_brand(db, scope.club_id)
    try:
        send_html_email(
            to=request.to_email, subject=request.subject,
            html_body=render_letter(subject=request.subject, body_text=request.body_text, brand=brand),
            text_body=request.body_text, reply_to=contact, bcc=contact,
        )
    except EmailNotConfiguredError as exc:
        request.last_error = "L'invio delle email non è ancora configurato sul server."
        await db.commit()
        raise ClubValidationError(f"{request.last_error} La lettera è salvata: mandala quando sarà attivo.") from exc
    except Exception as exc:
        logger.exception("Transport request %s not sent", request.id)
        request.last_error = "Il server di posta non ha accettato l'email."
        await db.commit()
        raise ClubValidationError(f"{request.last_error} Riprova tra poco.") from exc
    request.status = "SENT"
    request.sent_at = utcnow()
    request.sent_by_user_id = actor_user_id
    request.last_error = None
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.transport_request_sent", entity_type="club_competition", entity_id=str(competition_id),
        new_value={"to": request.to_email, "subject": request.subject},
    )
    await db.commit()
    await db.refresh(request)
    return request


async def on_registrations_closed(db: AsyncSession, *, comp: ClubCompetition) -> None:
    """Le iscrizioni di un evento si sono chiuse (dal job notturno o dalla
    segreteria): se serve il trasporto, la bozza si scrive adesso, con gli
    iscritti veri, e la segreteria lo sa. Con l'invio automatico parte
    anche la lettera. Mai fa fallire la chiusura."""
    from app.domains.club.clubs import notify_club_staff

    if not comp.transport_needed:
        return
    try:
        existing = await _request(db, competition_id=comp.id)
        request = existing or await ensure_draft(db, comp=comp)
        await db.commit()
        scope = scope_of(comp)
        if comp.transport_auto_send and request.status == "DRAFT" and request.to_email:
            try:
                await send(
                    db, scope=scope, competition_id=comp.id, to_email=request.to_email, subject=request.subject,
                    body_text=request.body_text, actor_user_id=None,
                )
                await notify_club_staff(
                    db, scope=scope, type_="CLUB_TRANSPORT_SENT", entity_id=comp.id,
                    title=f"Richiesta di trasporto inviata: {comp.name}",
                    body=f"Inviata a {request.to_email} alla chiusura delle iscrizioni.",
                )
                return
            except ClubValidationError:
                pass  # resta la bozza, con l'errore: la segreteria la manda a mano
        if existing is None or request.status == "DRAFT":
            await notify_club_staff(
                db, scope=scope, type_="CLUB_TRANSPORT_DRAFT", entity_id=comp.id,
                title=f"Richiesta di trasporto pronta: {comp.name}",
                body="Le iscrizioni sono chiuse: rileggi la lettera e mandala con un clic.",
            )
    except Exception:
        logger.exception("Transport draft failed for competition %s", comp.id)
        await db.rollback()
