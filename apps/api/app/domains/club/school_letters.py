"""La giustificazione per la scuola di un atleta iscritto a una gara.

Quando un ragazzo va a una gara in un giorno di scuola, il club scrive alla
scuola: l'atleta è stato selezionato dal club per partecipare, si chiede di
giustificare le assenze. La segreteria apre l'iscrizione, il sistema propone
il testo (nella lingua delle lettere del club, con i dati dell'atleta e
della gara), lei lo corregge se serve, e genera il PDF su carta intestata.

Il PDF contiene i dati di un minore: sta nel bucket **privato** dei
documenti, si apre solo con un URL presigned di pochi minuti, dato a chi può
vederlo (la segreteria del club, il titolare dell'atleta). Una lettera per
iscrizione: rigenerarla sostituisce testo e file, e il file vecchio si
cancella.
"""

import io
import logging
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.club.models import (
    Club,
    ClubAthlete,
    ClubCompetition,
    ClubCompetitionEntry,
    ClubSchoolLetter,
)
from app.domains.club.scope import ClubScope, scope_of
from app.domains.club.service import ClubNotFoundError, ClubValidationError
from app.domains.club.transport import _dates, _day

logger = logging.getLogger(__name__)

MAX_BODY_CHARS = 6000


async def _site(db: AsyncSession, *, club_id: uuid.UUID):
    from app.domains.club.site_models import ClubSite

    return (await db.execute(select(ClubSite).where(ClubSite.club_id == club_id))).scalar_one_or_none()


def _lang(club: Club) -> str:
    lang = (club.settings or {}).get("letters_language") or "pt"
    return lang if lang in ("pt", "it", "en") else "pt"


def compose(
    *, club: Club, comp: ClubCompetition, athlete: ClubAthlete, city: str | None, today: date,
) -> str:
    """Il testo proposto, nella lingua delle lettere del club. Testo
    semplice: è quello che la segreteria vede e corregge; un paragrafo per
    riga vuota."""
    lang = _lang(club)
    name = f"{athlete.first_name} {athlete.last_name}"
    born = _day(athlete.birth_date, lang)
    where = comp.location or "—"
    when = _dates(comp, lang)
    place_date = f"{city}, {_day(today, lang)}" if city else _day(today, lang)
    if lang == "pt":
        f = athlete.sex == "F"
        o, a_ = ("a", "a") if f else ("o", "o")
        what = "no estágio" if comp.kind == "STAGE" else "na prova"
        fed = f", com o n.º de federado {athlete.federation_number}" if athlete.federation_number else ""
        lines = [
            "Exmo(a). Senhor(a) Diretor(a) de Turma,",
            (f"Para os devidos efeitos, o {club.name} declara que {o} atleta {name}, nascid{a_} a {born}{fed}, "
             f"praticante de judo neste clube, foi selecionad{a_} pelo clube, pelas suas excelentes capacidades "
             f"e pelo empenho que demonstra nos treinos, para representar o {club.name} {what} «{comp.name}», "
             f"que se realiza em {where} {when}."),
            (f"Vimos, por isso, solicitar que as faltas d{o} alun{a_} às atividades letivas nesse período sejam "
             "consideradas justificadas, ao abrigo da sua participação em atividades desportivas."),
            "Agradecemos desde já a compreensão e ficamos ao dispor para qualquer esclarecimento.",
            place_date,
            f"Com os melhores cumprimentos,\nA Direção do {club.name}",
        ]
    elif lang == "it":
        f = athlete.sex == "F"
        what = "allo stage" if comp.kind == "STAGE" else "alla gara"
        fed = f", tesserat{'a' if f else 'o'} n. {athlete.federation_number}" if athlete.federation_number else ""
        lines = [
            "Gentile Dirigente Scolastico, gentili docenti,",
            (f"il {club.name} dichiara che l'atleta {name}, nat{'a' if f else 'o'} il {born}{fed}, che pratica "
             f"judo nel nostro club, è stat{'a' if f else 'o'} selezionat{'a' if f else 'o'} dal club, per le sue "
             f"ottime capacità e per l'impegno che dimostra negli allenamenti, per rappresentare il {club.name} "
             f"{what} «{comp.name}», che si svolge a {where} {when}."),
            (f"Chiediamo pertanto che le assenze dell{'a' if f else 'o'} student{'essa' if f else 'e'} dalle lezioni "
             "in quei giorni siano considerate giustificate, per la sua partecipazione ad attività sportive."),
            "Vi ringraziamo per la comprensione e restiamo a disposizione per qualsiasi chiarimento.",
            place_date,
            f"Cordiali saluti,\nLa Direzione del {club.name}",
        ]
    else:
        what = "the training camp" if comp.kind == "STAGE" else "the competition"
        fed = f", federation number {athlete.federation_number}" if athlete.federation_number else ""
        lines = [
            "Dear Head Teacher,",
            (f"{club.name} hereby declares that the athlete {name}, born on {born}{fed}, who practises judo at "
             f"our club, has been selected by the club, for their excellent skills and commitment in training, "
             f"to represent {club.name} at {what} “{comp.name}”, taking place in {where} {when}."),
            ("We therefore kindly ask that the pupil's absence from lessons during that period be considered "
             "justified, as it is due to their participation in a sports event."),
            "Thank you for your understanding; we remain available for any further information.",
            place_date,
            f"Kind regards,\nThe Board of {club.name}",
        ]
    return "\n\n".join(lines)


async def _entry(
    db: AsyncSession, *, scope: ClubScope, competition_id: uuid.UUID, entry_id: uuid.UUID,
) -> tuple[ClubCompetition, ClubCompetitionEntry, ClubAthlete]:
    row = (
        await db.execute(
            select(ClubCompetition, ClubCompetitionEntry, ClubAthlete)
            .join(ClubCompetitionEntry, ClubCompetitionEntry.competition_id == ClubCompetition.id)
            .join(ClubAthlete, ClubAthlete.id == ClubCompetitionEntry.athlete_id)
            .where(
                ClubCompetition.id == competition_id, ClubCompetition.club_id == scope.club_id,
                ClubCompetitionEntry.id == entry_id,
            )
        )
    ).one_or_none()
    if row is None:
        raise ClubNotFoundError("Iscrizione non trovata.")
    return row[0], row[1], row[2]


async def letters_by_entry(db: AsyncSession, *, entry_ids: list[uuid.UUID]) -> dict[uuid.UUID, ClubSchoolLetter]:
    if not entry_ids:
        return {}
    rows = (await db.execute(select(ClubSchoolLetter).where(ClubSchoolLetter.entry_id.in_(entry_ids)))).scalars()
    return {letter.entry_id: letter for letter in rows}


async def draft(
    db: AsyncSession, *, scope: ClubScope, competition_id: uuid.UUID, entry_id: uuid.UUID, today: date,
) -> dict:
    """Il testo da correggere: quello già stampato, se c'è, altrimenti la
    proposta."""
    comp, entry, athlete = await _entry(db, scope=scope, competition_id=competition_id, entry_id=entry_id)
    letter = (await letters_by_entry(db, entry_ids=[entry.id])).get(entry.id)
    if letter is not None:
        body = letter.body_text
    else:
        club = await db.get(Club, scope.club_id)
        site = await _site(db, club_id=scope.club_id)
        body = compose(club=club, comp=comp, athlete=athlete, city=site.city if site else None, today=today)
    return _read(entry=entry, athlete=athlete, letter=letter, body_text=body)


def _read(*, entry: ClubCompetitionEntry, athlete: ClubAthlete, letter: ClubSchoolLetter | None, body_text: str) -> dict:
    return {
        "entry_id": entry.id,
        "athlete_name": f"{athlete.first_name} {athlete.last_name}",
        "body_text": body_text,
        "generated_at": letter.generated_at if letter else None,
    }


async def proposal(
    db: AsyncSession, *, scope: ClubScope, competition_id: uuid.UUID, entry_id: uuid.UUID, today: date,
) -> dict:
    """La proposta di testo da capo, ignorando quello già stampato."""
    comp, entry, athlete = await _entry(db, scope=scope, competition_id=competition_id, entry_id=entry_id)
    letter = (await letters_by_entry(db, entry_ids=[entry.id])).get(entry.id)
    club = await db.get(Club, scope.club_id)
    site = await _site(db, club_id=scope.club_id)
    body = compose(club=club, comp=comp, athlete=athlete, city=site.city if site else None, today=today)
    return _read(entry=entry, athlete=athlete, letter=letter, body_text=body)


def _escape(value: str) -> str:
    """Il testo finisce dentro i mini-tag di reportlab: un "<" scritto dalla
    segreteria non deve poter rompere il PDF."""
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_pdf(*, club: Club, site, body_text: str, logo: bytes | None) -> bytes:
    """Carta intestata del club (logo, nome, recapiti) e il testo, un
    paragrafo per riga vuota."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import (
        HRFlowable,
        Image,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    brand = colors.HexColor(site.brand_primary) if site is not None and site.brand_primary else colors.HexColor("#b91c1c")
    title = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=colors.HexColor("#111827"))
    small = ParagraphStyle("small", fontName="Helvetica", fontSize=8.5, leading=11, textColor=colors.HexColor("#4b5563"))
    body = ParagraphStyle("body", fontName="Helvetica", fontSize=11, leading=16, spaceAfter=10, alignment=4)

    contact = [
        x for x in (
            site.address if site is not None else None,
            site.contact_phone if site is not None else None,
            (site.contact_email if site is not None else None) or (club.settings or {}).get("contact_email"),
            site.website_url if site is not None else None,
        ) if x
    ]
    head_text = [Paragraph(_escape(club.name), title)]
    if contact:
        head_text.append(Paragraph(_escape(" · ".join(contact)), small))
    cells = [head_text]
    widths = [170 * mm]
    if logo:
        try:
            reader = ImageReader(io.BytesIO(logo))
            w, h = reader.getSize()
            side = 22 * mm
            image = Image(io.BytesIO(logo), width=side * min(1, w / h), height=side * min(1, h / w))
            cells = [image, head_text]
            widths = [28 * mm, 142 * mm]
        except Exception:  # noqa: BLE001 -- un logo illeggibile non deve impedire la lettera
            logger.warning("school letter: club logo of %s not readable, printing without it", club.id)
    header = Table([cells], colWidths=widths)
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))

    story: list = [header, Spacer(1, 4 * mm), HRFlowable(width="100%", thickness=1.2, color=brand), Spacer(1, 10 * mm)]
    for paragraph in body_text.replace("\r\n", "\n").split("\n\n"):
        if paragraph.strip():
            story.append(Paragraph(_escape(paragraph.strip()).replace("\n", "<br/>"), body))

    buffer = io.BytesIO()
    SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
        title="Justificação escolar", author=club.name,
    ).build(story)
    return buffer.getvalue()


async def generate(
    db: AsyncSession, *, scope: ClubScope, competition_id: uuid.UUID, entry_id: uuid.UUID, body_text: str,
    actor_user_id: uuid.UUID,
) -> ClubSchoolLetter:
    """Stampa il testo corretto dalla segreteria, salva il PDF nel bucket
    privato e lo lega all'iscrizione. Solo per chi è iscritto davvero."""
    from app.core.storage import delete_document_object, read_media_url, upload_document

    comp, entry, athlete = await _entry(db, scope=scope, competition_id=competition_id, entry_id=entry_id)
    if entry.status != "REGISTERED":
        raise ClubValidationError(f"{athlete.first_name} si è ritirato da questa gara: niente giustificazione.")
    body_text = body_text.strip()
    if len(body_text) < 20:
        raise ClubValidationError("Il testo della giustificazione è troppo corto.")
    if len(body_text) > MAX_BODY_CHARS:
        raise ClubValidationError(f"Il testo è troppo lungo (massimo {MAX_BODY_CHARS} caratteri).")
    club = await db.get(Club, scope.club_id)
    site = await _site(db, club_id=scope.club_id)
    pdf = render_pdf(
        club=club, site=site, body_text=body_text,
        logo=read_media_url(site.logo_url) if site is not None and site.logo_url else None,
    )
    key = upload_document(
        file_bytes=pdf, content_type="application/pdf",
        key_prefix=f"club-school-letters/{scope.club_id}/{comp.id}",
    )
    letter = (await letters_by_entry(db, entry_ids=[entry.id])).get(entry.id)
    old_key = letter.storage_key if letter is not None else None
    if letter is None:
        letter = ClubSchoolLetter(
            **scope_of(comp).columns(), entry_id=entry.id, competition_id=comp.id, athlete_id=athlete.id,
            body_text=body_text, storage_key=key, generated_at=utcnow(), generated_by_user_id=actor_user_id,
        )
        db.add(letter)
    else:
        letter.body_text = body_text
        letter.storage_key = key
        letter.generated_at = utcnow()
        letter.generated_by_user_id = actor_user_id
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.school_letter_generated", entity_type="club_competition_entry", entity_id=str(entry.id),
    )
    await db.commit()
    await db.refresh(letter)
    if old_key and old_key != key:
        delete_document_object(storage_key=old_key)
    return letter


async def letter_for(
    db: AsyncSession, *, scope: ClubScope, competition_id: uuid.UUID, entry_id: uuid.UUID,
) -> ClubSchoolLetter:
    _comp, entry, _athlete = await _entry(db, scope=scope, competition_id=competition_id, entry_id=entry_id)
    letter = (await letters_by_entry(db, entry_ids=[entry.id])).get(entry.id)
    if letter is None:
        raise ClubNotFoundError("La giustificazione non è ancora stata generata.")
    return letter

