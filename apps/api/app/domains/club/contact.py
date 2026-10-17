"""I messaggi dal sito pubblico. Specifica: docs/club-portal.md, "Sito
pubblico" → "Messaggi dal sito".

Chi visita la pagina di un club può scrivergli ("Envie uma mensagem ao
clube", in fondo alla pagina); chi visita /contactos scrive a JudoArteVida.
Il messaggio:

1. si **salva** (`contact_messages`): la casella "Messaggi" della segreteria,
   o della console per quelli a JAV, è il punto d'arrivo vero;
2. fa partire una **notifica** a chi lo deve leggere: la segreteria del club
   (clubs.notify_club_staff, come i messaggi di JAVBOT), o gli
   amministratori della piattaforma per quelli a JAV;
3. manda un'**email** all'indirizzo di contatto del club (o a
   info@judoartevida.com), con "Rispondi" che va a chi ha scritto. È una
   cortesia: senza SMTP, o con il server di posta giù, non parte e la
   richiesta riesce lo stesso (CLAUDE.md §5); `emailed_at` resta vuoto.

Contro lo spam, senza servizi di captcha esterni: un campo trappola che le
persone non vedono e i robot riempiono (chi lo riempie riceve "inviato" e
non si salva niente: un robot non deve capire di essere stato scoperto),
il limite per IP del router (core/rate_limit.py, su Redis) e, siccome quel
limite lascia passare se Redis non risponde, un tetto nel database per
mittente (l'impronta dell'IP, mai l'indirizzo).

Senza il consenso a essere ricontattati (GDPR) il messaggio non si accetta:
serve per rispondere, ed è la sola cosa per cui si usano quei dati.
"""

import asyncio
import hashlib
import logging
import re
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.club import clubs as clubs_service
from app.domains.club import site as site_service
from app.domains.club.contact_models import CONTACT_STATUSES, CONTACT_TOPICS, ContactMessage
from app.domains.club.models import Club
from app.domains.club.scope import ClubScope
from app.domains.club.service import ClubError, ClubNotFoundError, ClubValidationError
from app.domains.notifications import service as notifications_service

logger = logging.getLogger(__name__)

NOTIFICATION_TYPE = "CONTACT_MESSAGE"
#: Chi legge i messaggi scritti a JudoArteVida: gli amministratori della
#: piattaforma, gli stessi ruoli che possono entrare nei club (clubs.enter).
JAV_ROLES = {"SUPER_ADMIN", "ORGANIZATION_ADMIN", "ADMIN"}
#: Quanti messaggi può mandare lo stesso mittente in un'ora, contati nel
#: database: la rete sotto il limite di Redis, che se Redis è giù lascia passare.
MAX_PER_HOUR = 5
MIN_MESSAGE = 10
MAX_MESSAGE = 4000
LOCALES = ("pt", "it", "en", "es", "fr", "de", "uk")
#: Quanti messaggi mostra la casella: i più recenti. Chi ne ha di più li
#: archivia; un elenco infinito non si legge comunque.
LIST_LIMIT = 200
_EMAIL = re.compile(r"^[^@\s<>\"'(),;:]+@[^@\s<>\"'(),;:]+\.[A-Za-z]{2,}$")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class ContactTooManyError(ClubError):
    """Lo stesso mittente ha scritto troppe volte in poco tempo."""


def _line(value: str | None, limit: int) -> str:
    """Una riga di testo: niente a capo né caratteri di controllo. Il nome
    finisce nell'oggetto dell'email, e un a capo lì è un'intestazione nuova."""
    return " ".join(_CONTROL.sub("", value or "").split())[:limit]


def clean_message(data: dict) -> dict:
    """Le regole del modulo, con un messaggio per chi scrive (CLAUDE.md §6).
    Il browser controlla le stesse cose, ma si decide qui."""
    name = _line(data.get("name"), 120)
    email = _line(data.get("email"), 255).lower()
    phone = _line(data.get("phone"), 40) or None
    message = _CONTROL.sub("", (data.get("message") or "")).strip()
    if len(name) < 2:
        raise ClubValidationError("Scrivi il tuo nome, così sanno a chi rispondere.")
    if not _EMAIL.match(email):
        raise ClubValidationError("L'email non sembra giusta: controllala, è lì che riceverai la risposta.")
    if phone is not None and not re.fullmatch(r"[0-9+()./\- ]{6,40}", phone):
        raise ClubValidationError("Il telefono può contenere solo numeri, spazi e il +.")
    if len(message) < MIN_MESSAGE:
        raise ClubValidationError("Il messaggio è troppo corto: scrivi qualche parola in più.")
    if len(message) > MAX_MESSAGE:
        raise ClubValidationError(f"Il messaggio è troppo lungo: al massimo {MAX_MESSAGE} caratteri.")
    if data.get("consent") is not True:
        raise ClubValidationError(
            "Per poterti rispondere serve il tuo consenso: spunta la casella sotto il messaggio."
        )
    locale = (data.get("locale") or "pt").lower()[:2]
    topic = (data.get("topic") or "GENERAL").upper()
    return {"name": name, "email": email, "phone": phone, "message": message,
            "locale": locale if locale in LOCALES else "pt", "topic": topic if topic in CONTACT_TOPICS else "GENERAL"}


def ip_hash(ip: str | None) -> str | None:
    """L'impronta dell'IP con il segreto del server: due messaggi dallo
    stesso indirizzo si riconoscono, l'indirizzo non si ricava."""
    if not ip:
        return None
    return hashlib.sha256(f"{get_settings().jwt_secret_key}:contact:{ip}".encode()).hexdigest()


async def _recent_from(db: AsyncSession, fingerprint: str, *, since: datetime) -> int:
    return (await db.execute(
        select(func.count()).select_from(ContactMessage)
        .where(ContactMessage.ip_hash == fingerprint, ContactMessage.created_at >= since)
    )).scalar_one()


async def submit(
    db: AsyncSession, *, data: dict, club_slug: str | None = None, organization_id: uuid.UUID | None = None,
    ip: str | None = None, user_agent: str | None = None, now: datetime | None = None,
) -> ContactMessage | None:
    """Un messaggio dal sito: a un club pubblicato (`club_slug`) o, senza, a
    JudoArteVida (`organization_id`). None = il campo trappola era pieno:
    niente salvato, e chi chiama risponde comunque "inviato"."""
    if _line(data.get("website"), 200):
        logger.info("contact: honeypot filled, message dropped")
        return None
    clean = clean_message(data)
    now = now or utcnow()
    club = site = None
    if club_slug is not None:
        # Solo un club che il sito mostra: a una pagina in bozza non si scrive.
        club, site = await site_service.public_club_by_slug(db, club_slug)
        organization_id = club.organization_id
    if organization_id is None:
        raise ClubNotFoundError("Destinatario non trovato.")
    fingerprint = ip_hash(ip)
    if fingerprint and await _recent_from(db, fingerprint, since=now - timedelta(hours=1)) >= MAX_PER_HOUR:
        raise ContactTooManyError(
            "Hai già mandato diversi messaggi: aspetta un po' prima di scriverne un altro, ti risponderanno presto."
        )
    message = ContactMessage(
        organization_id=organization_id, club_id=club.id if club else None, **clean, status="NEW",
        consent_at=now, ip_hash=fingerprint, user_agent=_line(user_agent, 200) or None, created_at=now,
    )
    db.add(message)
    await db.flush()
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=None, action="contact.message_received",
        entity_type="contact_message", entity_id=str(message.id),
        new_value={"club_id": str(club.id) if club else None},
    )
    title = (f"Nuovo sponsor dal sito: {clean['name']}" if clean["topic"] == "SPONSOR"
             else f"Richiesta di un nuovo club: {clean['name']}" if clean["topic"] == "NEW_CLUB"
             else f"Nuovo messaggio dal sito: {clean['name']}")
    preview = clean["message"][:300]
    if club is not None:
        # La segreteria del club, non lo staff della piattaforma: un messaggio
        # a un club è del club (come quelli di JAVBOT).
        await clubs_service.notify_club_staff(
            db, scope=ClubScope(organization_id=organization_id, club_id=club.id), type_=NOTIFICATION_TYPE,
            entity_type="contact_message", entity_id=message.id, title=title, body=preview,
        )
    else:
        await notifications_service.notify_roles(
            db, organization_id=organization_id, roles=JAV_ROLES, type_=NOTIFICATION_TYPE,
            entity_type="contact_message", entity_id=message.id, title=title, body=preview,
        )
    await db.commit()

    # Dopo il commit: il messaggio c'è già, l'email è una cortesia.
    to = _recipient_email(club, site)
    if to and await asyncio.to_thread(_send_email, await _compose_email(db, message, club=club), to=to, reply_to=message.email):
        message.emailed_at = utcnow()
        await db.commit()
    return message


def _recipient_email(club: Club | None, site) -> str | None:
    if club is None:
        return get_settings().jav_contact_email or None
    # Il contatto della pagina, poi quello delle impostazioni del club (lo
    # stesso che riceve la copia delle lettere del trasporto). Senza nessuno
    # dei due il messaggio resta nella casella del club, e basta: non va a
    # JudoArteVida, perché è scritto al club.
    return (site.contact_email if site is not None else None) or (club.settings or {}).get("contact_email") or None


TOPIC_PT = {"GENERAL": "Pergunta", "SPONSOR": "Patrocínio", "ENROLMENT": "Inscrições e treinos",
            "EVENTS": "Provas e eventos", "NEW_CLUB": "Criar um clube", "OTHER": "Outro"}


async def _compose_email(db: AsyncSession, message: ContactMessage, *, club: Club | None):
    """L'avviso via email (testo personalizzabile, domains/email_texts) nella
    veste del club che lo riceve, o di JudoArteVida. Il testo di chi scrive
    passa da text_to_html, che fa l'escape: niente HTML dal sito."""
    from app.domains.club.email_brand import club_brand
    from app.domains.email_texts.service import compose

    mail = await compose(db, "contact_message", values={
        "onde": f"a página de {club.name}" if club else "o site JudoArteVida",
        "nome": message.name, "email": message.email, "telefone": message.phone or "—",
        "assunto": TOPIC_PT.get(message.topic, message.topic), "mensagem": message.message,
    }, brand=await club_brand(db, club.id if club else None), cta_url=f"{get_settings().public_app_base_url}/area")
    if message.topic == "SPONSOR":
        return type(mail)(subject=f"Patrocínio — {mail.subject}", html=mail.html, text=mail.text)
    if message.topic == "NEW_CLUB":
        return type(mail)(subject=f"Novo clube — {mail.subject}", html=mail.html, text=mail.text)
    return mail


def _send_email(mail, *, to: str, reply_to: str) -> bool:
    from app.core.email import send_html_email_best_effort

    return send_html_email_best_effort(
        context="contact_message", to=to, subject=mail.subject, html_body=mail.html, text_body=mail.text,
        reply_to=reply_to,
    )


# --- Le caselle: segreteria del club e console della piattaforma ----------------------------------


def message_dict(message: ContactMessage, club: Club | None = None) -> dict:
    return {
        "id": message.id,
        "club": {"id": club.id, "name": club.name, "slug": club.slug} if club is not None else None,
        "name": message.name,
        "email": message.email,
        "phone": message.phone,
        "message": message.message,
        "topic": message.topic,
        "locale": message.locale,
        "status": message.status,
        "created_at": message.created_at,
        "emailed_at": message.emailed_at,
    }


async def _inbox(db: AsyncSession, stmt, *, status: str | None) -> dict:
    if status is not None and status not in CONTACT_STATUSES:
        raise ClubValidationError("Stato non valido.")
    counts = dict((await db.execute(
        stmt.with_only_columns(ContactMessage.status, func.count()).group_by(ContactMessage.status)
    )).all())
    if status is not None:
        stmt = stmt.where(ContactMessage.status == status)
    else:
        # Senza filtro: i nuovi e i letti; gli archiviati si chiedono a parte.
        stmt = stmt.where(ContactMessage.status != "ARCHIVED")
    rows = list((await db.execute(stmt.order_by(ContactMessage.created_at.desc()).limit(LIST_LIMIT))).scalars())
    club_ids = {m.club_id for m in rows if m.club_id}
    clubs = {
        c.id: c for c in (await db.execute(select(Club).where(Club.id.in_(club_ids)))).scalars()
    } if club_ids else {}
    return {
        "items": [message_dict(m, clubs.get(m.club_id)) for m in rows],
        "counts": {s: counts.get(s, 0) for s in CONTACT_STATUSES},
    }


async def club_inbox(db: AsyncSession, *, scope: ClubScope, status: str | None = None) -> dict:
    """I messaggi scritti al club: solo i suoi, qualunque cosa chieda chi
    legge (il club lo decide scope.py)."""
    stmt = select(ContactMessage).where(
        ContactMessage.organization_id == scope.organization_id, ContactMessage.club_id == scope.club_id,
    )
    return await _inbox(db, stmt, status=status)


async def platform_inbox(
    db: AsyncSession, *, organization_id: uuid.UUID, club_id: uuid.UUID | None = None, all_clubs: bool = False,
    status: str | None = None,
) -> dict:
    """La casella della console. Di default i messaggi a JudoArteVida; con
    `club_id` quelli di un club, con `all_clubs` tutti: queste due le
    concede il router solo al superadmin (clubs.manage)."""
    stmt = select(ContactMessage).where(ContactMessage.organization_id == organization_id)
    if all_clubs:
        pass
    elif club_id is not None:
        stmt = stmt.where(ContactMessage.club_id == club_id)
    else:
        stmt = stmt.where(ContactMessage.club_id.is_(None))
    return await _inbox(db, stmt, status=status)


async def _set_status(
    db: AsyncSession, message: ContactMessage, *, status: str, organization_id: uuid.UUID, actor_user_id: uuid.UUID,
) -> dict:
    if status not in CONTACT_STATUSES:
        raise ClubValidationError("Stato non valido.")
    previous = message.status
    message.status = status
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id, action="contact.message_status",
        entity_type="contact_message", entity_id=str(message.id),
        previous_value={"status": previous}, new_value={"status": status},
    )
    await db.commit()
    club = await db.get(Club, message.club_id) if message.club_id else None
    return message_dict(message, club)


async def set_club_status(
    db: AsyncSession, *, scope: ClubScope, message_id: uuid.UUID, status: str, actor_user_id: uuid.UUID,
) -> dict:
    message = await db.get(ContactMessage, message_id)
    # Un messaggio di un altro club, o a JAV, per questa casella non esiste.
    if message is None or message.club_id != scope.club_id or message.organization_id != scope.organization_id:
        raise ClubNotFoundError("Messaggio non trovato.")
    return await _set_status(db, message, status=status, organization_id=scope.organization_id,
                             actor_user_id=actor_user_id)


async def set_platform_status(
    db: AsyncSession, *, organization_id: uuid.UUID, message_id: uuid.UUID, status: str, actor_user_id: uuid.UUID,
    can_see_clubs: bool,
) -> dict:
    message = await db.get(ContactMessage, message_id)
    if (
        message is None or message.organization_id != organization_id
        or (message.club_id is not None and not can_see_clubs)
    ):
        raise ClubNotFoundError("Messaggio non trovato.")
    return await _set_status(db, message, status=status, organization_id=organization_id,
                             actor_user_id=actor_user_id)
