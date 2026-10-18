"""Il curriculum del treinador: l'archivio dei documenti, il Curriculum Vitae
professionale e il Curriculum Sportivo, con i PDF. Specifica:
docs/club-portal.md, "Il curriculum del treinador"; tabelle in
club/cv_models.py.

- **L'archivio**: diplomi di treinador, qualifiche federali, attestati,
  primo soccorso, titoli di studio… Titolo, categoria, ente, date, nota e il
  file nel bucket privato (si apre con un URL presigned, solo dal
  proprietario).
- **Il CV**: quello che scrive il treinador (presentazione, esperienze,
  formazione, competenze, lingue, specializzazioni, sezioni libere) più ciò
  che il gestionale sa già e che non si riscrive: nome, foto, email, i club in
  cui allena, la cintura, le certificazioni dell'archivio.
- **Il Curriculum Sportivo** si ricostruisce dallo storico: le gare e i
  risultati delle sue schede di atleta (in qualunque club), le cinture e i
  Dan, le prove a cui è andato da treinador (i relatórios che ha scritto),
  i club e i corsi in cui ha allenato. Più gli eventi che aggiunge a mano,
  che restano suoi (`coach_sport_events`) e si vedono come «declarado».
- **I PDF** (A4, reportlab come gli altri PDF del gestionale): anteprima al
  volo, o una versione salvata nel bucket privato.
"""

import io
import uuid
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.club import belts as belts_catalog
from app.domains.club.cv_models import (
    COACH_DOCUMENT_CATEGORIES,
    SPORT_EVENT_ROLES,
    SPORT_EVENT_TYPES,
    CoachCvExport,
    CoachDocument,
    CoachProfile,
    CoachSportEvent,
)
from app.domains.club.models import (
    COMPETITION_LEVELS,
    PLACEMENTS,
    Club,
    ClubAthlete,
    ClubBeltGrade,
    ClubCompetition,
    ClubCompetitionEntry,
    ClubCourse,
    ClubCourseStaff,
    ClubEventReport,
    ClubStaffMembership,
    ClubWorkSession,
)
from app.domains.club.service import ClubNotFoundError, ClubValidationError
from app.domains.users.models import User

# --- Le parole del PDF (pt-PT, la lingua dei club e delle federazioni) ---------------------------

CATEGORY_PT = {
    "COACH_DIPLOMA": "Diploma de treinador", "FEDERATION": "Qualificação federativa", "COURSE": "Curso / estágio",
    "FIRST_AID": "Primeiros socorros", "ACADEMIC": "Formação académica", "PROFESSIONAL": "Qualificação profissional",
    "PERSONAL": "Documento pessoal", "OTHER": "Outro",
}
TYPE_PT = {
    "COMPETITION": "Competição", "STAGE": "Estágio", "SEMINAR": "Seminário", "COURSE": "Curso / formação",
    "GRADING": "Exame de graduação", "REFEREEING": "Arbitragem", "EDUCATION": "Formação", "MEETING": "Reunião",
    "OTHER": "Outro",
}
ROLE_PT = {
    "ATHLETE": "Atleta", "COACH": "Treinador", "ASSISTANT_COACH": "Treinador adjunto", "REFEREE": "Árbitro",
    "ORGANIZER": "Organização", "OTHER": "Outro",
}
LEVEL_PT = {
    "CLUB": "Clube", "REGIONAL": "Regional", "ZONAL": "Zonal", "OPENS": "Open", "NATIONAL": "Nacional",
    "INTERNATIONAL": "Internacional", "EUROPEAN_CUP": "Taça da Europa", "EUROPEAN_CHAMPIONSHIP": "Campeonato da Europa",
    "WORLD_CHAMPIONSHIP": "Campeonato do Mundo", "OLYMPIC_GAMES": "Jogos Olímpicos",
}
PLACE_PT = {0: "Participação", 1: "1.º lugar", 2: "2.º lugar", 3: "3.º lugar", 5: "5.º lugar", 7: "7.º lugar"}
MEDAL = {1: "GOLD", 2: "SILVER", 3: "BRONZE"}
#: Le cinture in portoghese per il PDF (il catalogo ha le etichette in italiano).
BELT_PT = {
    "WHITE": "Branco", "WHITE_YELLOW": "Branco-amarelo", "YELLOW": "Amarelo", "YELLOW_ORANGE": "Amarelo-laranja",
    "ORANGE": "Laranja", "ORANGE_GREEN": "Laranja-verde", "GREEN": "Verde", "GREEN_BLUE": "Verde-azul",
    "BLUE": "Azul", "BLUE_BROWN": "Azul-castanho", "BROWN": "Castanho",
}

#: I campi del CV che il treinador scrive (`coach_profiles.data`), con i limiti.
MAX_ITEMS = 40


def belt_pt(code: str) -> str:
    if code.startswith("BLACK_"):
        return f"{code.split('_')[1]}.º Dan"
    if code.startswith("WHITE_BARS_"):
        return f"Branco, {code.split('_')[2]} barras"
    return BELT_PT.get(code, code)


# --- Chi è -----------------------------------------------------------------------------------------


async def _me(db: AsyncSession, user: User) -> dict:
    from app.domains.club.staff_clubs import coach_profile

    profile = await coach_profile(db, user=user)
    return {**profile, "email": user.email}


async def _self_athletes(db: AsyncSession, user: User) -> list[ClubAthlete]:
    """Le sue schede di atleta, in qualunque club: quella del conto (is_self)
    e quella con il suo accesso da atleta."""
    return list((await db.execute(select(ClubAthlete).where(
        or_((ClubAthlete.guardian_user_id == user.id) & ClubAthlete.is_self.is_(True), ClubAthlete.user_id == user.id),
    ))).scalars())


async def _coached_clubs(db: AsyncSession, user: User) -> list[dict]:
    """I club in cui allena o ha allenato, con da quando (la prima riga tra
    appartenenza e turni di lavoro) a quando (l'ultimo turno), e i suoi corsi."""
    ids = set((await db.execute(select(ClubStaffMembership.club_id).where(
        ClubStaffMembership.user_id == user.id, ClubStaffMembership.status == "ACTIVE",
    ))).scalars())
    if user.club_id is not None:
        ids.add(user.club_id)
    sessions = {club_id: (start, end) for club_id, start, end in (await db.execute(
        select(ClubWorkSession.club_id, func.min(ClubWorkSession.started_at), func.max(ClubWorkSession.started_at))
        .where(ClubWorkSession.user_id == user.id).group_by(ClubWorkSession.club_id)
    )).all()}
    ids |= set(sessions)
    since = dict((await db.execute(select(ClubStaffMembership.club_id, ClubStaffMembership.created_at).where(
        ClubStaffMembership.user_id == user.id,
    ))).all())
    courses: dict[uuid.UUID, list[str]] = {}
    for club_id, name in (await db.execute(
        select(ClubCourse.club_id, ClubCourse.name).join(ClubCourseStaff, ClubCourseStaff.course_id == ClubCourse.id)
        .where(ClubCourseStaff.user_id == user.id).order_by(ClubCourse.name)
    )).all():
        courses.setdefault(club_id, []).append(name)
    clubs = {c.id: c for c in (await db.execute(select(Club).where(Club.id.in_(ids)))).scalars()} if ids else {}
    out = []
    for club_id, club in clubs.items():
        first = [d for d in (since.get(club_id), (sessions.get(club_id) or (None, None))[0]) if d]
        last = (sessions.get(club_id) or (None, None))[1]
        out.append({
            "club_id": club_id, "name": club.name, "active": club.status == "ACTIVE",
            "since": min(first).date() if first else None, "last_activity": last.date() if last else None,
            "courses": courses.get(club_id, []),
        })
    out.sort(key=lambda c: (c["since"] or date.max, c["name"]))
    return out


async def _best_belt(db: AsyncSession, athletes: list[ClubAthlete]) -> dict | None:
    if not athletes:
        return None
    grades = list((await db.execute(select(ClubBeltGrade.grade).where(
        ClubBeltGrade.athlete_id.in_([a.id for a in athletes]),
    ))).scalars())
    known = [g for g in grades if g in belts_catalog.BELT_CODES]
    if not known:
        return None
    best = max(known, key=belts_catalog.rank)
    return {"code": best, "label": belt_pt(best),
            "dan": int(best.split("_")[1]) if best.startswith("BLACK_") else None}


# --- L'archivio ------------------------------------------------------------------------------------


def document_dict(d: CoachDocument, *, today: date) -> dict:
    expiring = d.expires_on is not None and 0 <= (d.expires_on - today).days <= 60
    return {
        "id": d.id, "title": d.title, "category": d.category, "category_label": CATEGORY_PT[d.category],
        "issuer": d.issuer, "issued_on": d.issued_on, "expires_on": d.expires_on, "description": d.description,
        "has_file": d.storage_key is not None, "original_filename": d.original_filename,
        "content_type": d.content_type, "size_bytes": d.size_bytes, "show_in_cv": d.show_in_cv,
        "status": "EXPIRED" if d.expires_on and d.expires_on < today else "EXPIRING" if expiring else "VALID",
        "created_at": d.created_at, "updated_at": d.updated_at,
    }


async def list_documents(db: AsyncSession, *, user: User) -> list[CoachDocument]:
    return list((await db.execute(select(CoachDocument).where(CoachDocument.user_id == user.id).order_by(
        CoachDocument.issued_on.desc().nulls_last(), CoachDocument.created_at.desc(),
    ))).scalars())


async def get_document(db: AsyncSession, *, user: User, document_id: uuid.UUID) -> CoachDocument:
    doc = await db.get(CoachDocument, document_id)
    if doc is None or doc.user_id != user.id:
        raise ClubNotFoundError("Documento non trovato.")
    return doc


def _clean_document(data: dict, *, partial: bool) -> dict:
    out = {}
    if not partial or "title" in data:
        title = " ".join((data.get("title") or "").split())
        if not 2 <= len(title) <= 200:
            raise ClubValidationError("Scrivi il titolo del documento (es.: Treinador de Judo Grau I).")
        out["title"] = title
    if not partial or "category" in data:
        if data.get("category") not in COACH_DOCUMENT_CATEGORIES:
            raise ClubValidationError("Scegli la categoria del documento.")
        out["category"] = data["category"]
    for field, limit in (("issuer", 200), ("description", 2000)):
        if field in data:
            out[field] = (data.get(field) or "").strip()[:limit] or None
    for field in ("issued_on", "expires_on", "show_in_cv"):
        if field in data:
            out[field] = data[field]
    return out


async def save_document(
    db: AsyncSession, *, user: User, data: dict, file: tuple[bytes, str, str] | None,
    document: CoachDocument | None = None,
) -> CoachDocument:
    """Un documento nuovo (o le modifiche a uno che c'è): i dati e, se c'è,
    il file nuovo nel bucket privato. `file` = (byte, content type, nome)."""
    from app.core.storage import UploadValidationError, delete_document_object, upload_document

    values = _clean_document(data, partial=document is not None)
    issued, expires = values.get("issued_on", document.issued_on if document else None), \
        values.get("expires_on", document.expires_on if document else None)
    if issued and expires and expires < issued:
        raise ClubValidationError("La scadenza non può venire prima della data di conseguimento.")
    old_key = None
    if file is not None:
        content, content_type, filename = file
        try:
            key = upload_document(file_bytes=content, content_type=content_type,
                                  key_prefix=f"coach-documents/{user.id}")
        except UploadValidationError as exc:
            raise ClubValidationError("Il file deve essere un PDF, JPG o PNG di massimo 15 MB.") from exc
        old_key = document.storage_key if document else None
        values.update({"storage_key": key, "original_filename": (filename or "")[:255] or None,
                       "content_type": content_type, "size_bytes": len(content)})
    if document is None:
        document = CoachDocument(organization_id=user.organization_id, user_id=user.id, **values)
        db.add(document)
    else:
        for k, v in values.items():
            setattr(document, k, v)
    await db.flush()
    await audit_service.record(
        db, organization_id=user.organization_id, actor_user_id=user.id, action="coach.document_saved",
        entity_type="coach_document", entity_id=str(document.id), new_value={"fields": sorted(values)},
    )
    await db.commit()
    await db.refresh(document)
    if old_key:
        delete_document_object(storage_key=old_key)
    return document


async def delete_document(db: AsyncSession, *, user: User, document_id: uuid.UUID) -> None:
    from app.core.storage import delete_document_object

    doc = await get_document(db, user=user, document_id=document_id)
    key = doc.storage_key
    await db.delete(doc)
    await audit_service.record(
        db, organization_id=user.organization_id, actor_user_id=user.id, action="coach.document_deleted",
        entity_type="coach_document", entity_id=str(document_id),
    )
    await db.commit()
    if key:
        delete_document_object(storage_key=key)


# --- Il Curriculum Vitae ---------------------------------------------------------------------------


async def profile_of(db: AsyncSession, *, user: User) -> CoachProfile | None:
    return (await db.execute(select(CoachProfile).where(CoachProfile.user_id == user.id))).scalar_one_or_none()


async def save_profile(db: AsyncSession, *, user: User, data: dict) -> CoachProfile:
    """Il CV scritto dal treinador (già validato dallo schema della rotta)."""
    row = await profile_of(db, user=user)
    if row is None:
        row = CoachProfile(organization_id=user.organization_id, user_id=user.id, data=data)
        db.add(row)
    else:
        row.data = data
    await db.flush()
    await audit_service.record(
        db, organization_id=user.organization_id, actor_user_id=user.id, action="coach.cv_saved",
        entity_type="coach_profile", entity_id=str(row.id),
    )
    await db.commit()
    await db.refresh(row)
    return row


async def cv(db: AsyncSession, *, user: User) -> dict:
    """Tutto quello che serve allo schermo del CV e al PDF: ciò che scrive il
    treinador, ciò che il gestionale sa già, le certificazioni dell'archivio."""
    today = utcnow().date()
    row = await profile_of(db, user=user)
    athletes = await _self_athletes(db, user)
    return {
        "me": await _me(db, user),
        "data": row.data if row else {},
        "updated_at": row.updated_at if row else None,
        "clubs": await _coached_clubs(db, user),
        "belt": await _best_belt(db, athletes),
        "documents": [document_dict(d, today=today) for d in await list_documents(db, user=user)],
    }


# --- Il Curriculum Sportivo ------------------------------------------------------------------------


def _manual_dict(e: CoachSportEvent) -> dict:
    return {
        "id": e.id, "source": "MANUAL", "kind": e.event_type, "kind_label": TYPE_PT[e.event_type],
        "role": e.role, "role_label": ROLE_PT[e.role], "date": e.starts_on, "end_date": e.ends_on,
        "title": e.title, "location": e.location, "club": e.organization_name, "level": e.level,
        "level_label": LEVEL_PT.get(e.level or "", None), "category": e.category, "placement": e.placement,
        "placement_label": PLACE_PT.get(e.placement) if e.placement is not None else None,
        "medal": MEDAL.get(e.placement or -1), "result": e.result, "description": e.description,
        "document_id": e.document_id,
    }


async def sport_history(db: AsyncSession, *, user: User) -> dict:
    """Lo storico sportivo: la carriera agonistica (le sue schede di atleta) e
    quella tecnica (le prove da treinador, i club, i corsi), più gli eventi
    dichiarati a mano. Ogni voce dice da dove viene (OFFICIAL / MANUAL)."""
    today = utcnow().date()
    athletes = await _self_athletes(db, user)
    ids = [a.id for a in athletes]
    clubs = {c.id: c.name for c in (await db.execute(select(Club))).scalars()}
    items: list[dict] = []
    if ids:
        for entry, comp in (await db.execute(
            select(ClubCompetitionEntry, ClubCompetition)
            .join(ClubCompetition, ClubCompetition.id == ClubCompetitionEntry.competition_id)
            .where(ClubCompetitionEntry.athlete_id.in_(ids), ClubCompetitionEntry.status == "REGISTERED",
                   ClubCompetition.starts_on <= today)
        )).all():
            items.append({
                "id": entry.id, "source": "OFFICIAL", "kind": comp.kind, "kind_label": TYPE_PT.get(comp.kind, comp.kind),
                "role": "ATHLETE", "role_label": ROLE_PT["ATHLETE"], "date": comp.starts_on, "end_date": comp.ends_on,
                "title": comp.name, "location": comp.location, "club": clubs.get(entry.club_id),
                "level": comp.level, "level_label": LEVEL_PT.get(comp.level), "category": entry.category,
                "placement": entry.placement,
                "placement_label": PLACE_PT.get(entry.placement) if entry.placement is not None else None,
                "medal": MEDAL.get(entry.placement or -1), "result": entry.result_notes, "description": None,
                "document_id": None,
            })
    seen = {i["title"] + str(i["date"]) for i in items}
    for report, comp in (await db.execute(
        select(ClubEventReport, ClubCompetition).join(ClubCompetition, ClubCompetition.id == ClubEventReport.competition_id)
        .where(ClubEventReport.author_user_id == user.id)
    )).all():
        key = comp.name + str(comp.starts_on) + "coach"
        if key in seen:
            continue
        seen.add(key)
        items.append({
            "id": report.id, "source": "OFFICIAL", "kind": comp.kind, "kind_label": TYPE_PT.get(comp.kind, comp.kind),
            "role": "COACH", "role_label": ROLE_PT["COACH"], "date": comp.starts_on, "end_date": comp.ends_on,
            "title": comp.name, "location": comp.location, "club": clubs.get(report.club_id), "level": comp.level,
            "level_label": LEVEL_PT.get(comp.level), "category": None, "placement": None, "placement_label": None,
            "medal": None, "result": None, "description": None, "document_id": None,
        })
    manual = list((await db.execute(select(CoachSportEvent).where(CoachSportEvent.user_id == user.id))).scalars())
    items += [_manual_dict(e) for e in manual]
    items.sort(key=lambda i: (i["date"], i["title"]), reverse=True)

    grades = []
    if ids:
        first: dict[str, ClubBeltGrade] = {}
        # La cintura bianca che ogni atleta riceve all'iscrizione non è un esame.
        for g in (await db.execute(select(ClubBeltGrade).where(
            ClubBeltGrade.athlete_id.in_(ids), ClubBeltGrade.grade != belts_catalog.STARTING_BELT,
        ).order_by(ClubBeltGrade.awarded_on))).scalars():
            first.setdefault(g.grade, g)
        grades = [{"id": g.id, "grade": g.grade, "label": belt_pt(g.grade), "date": g.awarded_on,
                   "club": clubs.get(g.club_id), "source": "OFFICIAL"}
                  for g in sorted(first.values(), key=lambda g: g.awarded_on)]
    grades += [{"id": e.id, "grade": None, "label": e.title, "date": e.starts_on, "club": e.organization_name,
                "source": "MANUAL"} for e in manual if e.event_type == "GRADING"]
    grades.sort(key=lambda g: g["date"])

    athlete_items = [i for i in items if i["role"] == "ATHLETE" and i["kind"] != "GRADING"]
    medals = {m: sum(1 for i in athlete_items if i["medal"] == m) for m in ("GOLD", "SILVER", "BRONZE")}
    return {
        "me": await _me(db, user),
        "belt": await _best_belt(db, athletes),
        "is_athlete": bool(athletes),
        "athlete": {"competitions": sum(1 for i in athlete_items if i["kind"] == "COMPETITION"),
                    "medals": medals, "items": athlete_items},
        "coach": {"clubs": await _coached_clubs(db, user),
                  "items": [i for i in items if i["role"] != "ATHLETE" and i["kind"] != "GRADING"]},
        "grades": grades,
        "items": items,
    }


def _clean_event(data: dict) -> dict:
    title = " ".join((data.get("title") or "").split())
    if not 2 <= len(title) <= 200:
        raise ClubValidationError("Scrivi il nome dell'evento.")
    if data.get("event_type") not in SPORT_EVENT_TYPES:
        raise ClubValidationError("Scegli il tipo di evento.")
    if data.get("role") not in SPORT_EVENT_ROLES:
        raise ClubValidationError("Scegli il ruolo che avevi.")
    if not data.get("starts_on"):
        raise ClubValidationError("Indica la data dell'evento.")
    if data.get("starts_on") > utcnow().date():
        raise ClubValidationError("Il curriculum racconta ciò che è già successo: la data è nel futuro.")
    if data.get("ends_on") and data["ends_on"] < data["starts_on"]:
        raise ClubValidationError("La fine non può venire prima dell'inizio.")
    if data.get("level") and data["level"] not in COMPETITION_LEVELS:
        raise ClubValidationError("Livello non valido.")
    if data.get("placement") is not None and data["placement"] not in PLACEMENTS:
        raise ClubValidationError("Piazzamento non valido: 1, 2, 3, 5, 7 o partecipazione.")
    return {
        "title": title, "event_type": data["event_type"], "role": data["role"], "starts_on": data["starts_on"],
        "ends_on": data.get("ends_on"), "level": data.get("level") or None,
        "placement": data.get("placement"), "document_id": data.get("document_id"),
        **{f: (data.get(f) or "").strip()[:lim] or None
           for f, lim in (("location", 200), ("organization_name", 200), ("category", 120), ("result", 300),
                          ("description", 4000))},
    }


async def save_event(db: AsyncSession, *, user: User, data: dict, event_id: uuid.UUID | None = None) -> CoachSportEvent:
    """Un evento dichiarato a mano: solo nel curriculum, mai nelle gare,
    nel calendario o nel ranking del club."""
    values = _clean_event(data)
    if values["document_id"] is not None:
        await get_document(db, user=user, document_id=values["document_id"])
    if event_id is None:
        event = CoachSportEvent(organization_id=user.organization_id, user_id=user.id, **values)
        db.add(event)
    else:
        event = await db.get(CoachSportEvent, event_id)
        if event is None or event.user_id != user.id:
            raise ClubNotFoundError("Evento non trovato.")
        for k, v in values.items():
            setattr(event, k, v)
    await db.flush()
    await audit_service.record(
        db, organization_id=user.organization_id, actor_user_id=user.id, action="coach.sport_event_saved",
        entity_type="coach_sport_event", entity_id=str(event.id),
    )
    await db.commit()
    await db.refresh(event)
    return event


async def delete_event(db: AsyncSession, *, user: User, event_id: uuid.UUID) -> None:
    event = await db.get(CoachSportEvent, event_id)
    if event is None or event.user_id != user.id:
        raise ClubNotFoundError("Evento non trovato.")
    await db.delete(event)
    await db.commit()


# --- I PDF -----------------------------------------------------------------------------------------


def _d(value: date | None) -> str:
    return value.strftime("%d/%m/%Y") if value else ""


def _ym(value: str | None) -> str:
    """"2019-09" → "09/2019" (le date del CV sono mese e anno)."""
    if not value:
        return ""
    parts = str(value).split("-")
    return f"{parts[1]}/{parts[0]}" if len(parts) >= 2 else str(value)


def _esc(text: str | None) -> str:
    from xml.sax.saxutils import escape

    return escape(text or "").replace("\n", "<br/>")


def render_pdf(*, kind: str, payload: dict, photo: bytes | None, generated_on: date) -> bytes:
    """Il CV (`kind` CV, payload di cv()) o il Curriculum Sportivo (SPORT,
    payload di sport_history()) in A4: la testata scura con la foto, il nome
    e i contatti; poi le sezioni con un titolo colorato e un filo."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import (
        BaseDocTemplate,
        Frame,
        KeepTogether,
        PageTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )

    W, H = A4
    margin = 42
    ink, muted, line = colors.HexColor("#161515"), colors.HexColor("#6B696A"), colors.HexColor("#E2E2E2")
    brand, accent = colors.HexColor("#C8311A"), colors.HexColor("#E3CC00")
    header_h = 150
    me = payload["me"]
    data = payload.get("data") or {}
    title = "Curriculum Vitae" if kind == "CV" else "Curriculum Desportivo"
    buf = io.BytesIO()

    def contacts() -> list[str]:
        if kind != "CV":
            return [me.get("email") or ""]
        show = data.get("show") or {}
        out = []
        if show.get("email", True):
            out.append(data.get("email") or me.get("email") or "")
        if show.get("phone", True) and data.get("phone"):
            out.append(data["phone"])
        if data.get("city"):
            out.append(data["city"])
        for link in (data.get("links") or [])[:3]:
            if link.get("url"):
                out.append(link["url"])
        return [c for c in out if c]

    def header(pdf, doc) -> None:
        pdf.saveState()
        pdf.setFillColor(ink)
        pdf.rect(0, H - header_h, W, header_h, stroke=0, fill=1)
        pdf.setFillColor(accent)
        pdf.rect(0, H - header_h - 5, W, 5, stroke=0, fill=1)
        text_x = margin
        show_photo = kind != "CV" or (data.get("show") or {}).get("photo", True)
        if photo and show_photo:
            try:
                pdf.drawImage(ImageReader(io.BytesIO(photo)), W - margin - 96, H - header_h + 22, 96, 108,
                              mask="auto", preserveAspectRatio=True, anchor="c")
            except Exception:  # noqa: BLE001, S110 -- una foto rovinata non ferma il PDF
                pass
        pdf.setFillColor(accent)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(text_x, H - 40, title.upper())
        pdf.setFillColor(colors.white)
        pdf.setFont("Helvetica-Bold", 24)
        pdf.drawString(text_x, H - 70, (me.get("name") or "")[:42])
        pdf.setFont("Helvetica", 11)
        subtitle = data.get("headline") if kind == "CV" else (
            (payload.get("belt") or {}).get("label") and f"Judo · {(payload.get('belt') or {}).get('label')}")
        if subtitle:
            pdf.drawString(text_x, H - 90, str(subtitle)[:80])
        pdf.setFont("Helvetica", 9)
        pdf.setFillColor(colors.HexColor("#D4D4D4"))
        y = H - 112
        for c in contacts()[:4]:
            pdf.drawString(text_x, y, c[:90])
            y -= 12
        pdf.restoreState()
        footer(pdf, doc)

    def footer(pdf, doc) -> None:
        pdf.saveState()
        pdf.setFillColor(muted)
        pdf.setFont("Helvetica", 7.5)
        pdf.drawString(margin, 22, f"{me.get('name') or ''} · {title} · {_d(generated_on)}")
        pdf.drawRightString(W - margin, 22, f"{doc.page}")
        pdf.restoreState()

    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=margin, rightMargin=margin, topMargin=40, bottomMargin=40,
                          title=f"{title} — {me.get('name') or ''}", author=me.get("name") or "")
    body_w = W - 2 * margin
    doc.addPageTemplates([
        PageTemplate(id="first", frames=[Frame(margin, 40, body_w, H - 40 - header_h - 24, id="f")], onPage=header,
                     autoNextPageTemplate="next"),
        PageTemplate(id="next", frames=[Frame(margin, 40, body_w, H - 80, id="n")], onPage=footer),
    ])

    def style(name, **kw) -> ParagraphStyle:
        base = {"fontName": "Helvetica", "fontSize": 9.5, "leading": 13.5, "textColor": ink, "alignment": TA_LEFT}
        return ParagraphStyle(name, **{**base, **kw})

    h2 = style("h2", fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=brand, spaceBefore=12, spaceAfter=2)
    body = style("body")
    small = style("small", fontSize=8.5, leading=12, textColor=muted)
    strong = style("strong", fontName="Helvetica-Bold")
    story: list = []

    def section(name: str) -> None:
        story.append(Paragraph(name.upper(), h2))
        story.append(Table([[""]], colWidths=[body_w], rowHeights=[1.2],
                           style=TableStyle([("LINEABOVE", (0, 0), (-1, -1), 1, line)])))
        story.append(Spacer(1, 5))

    def row(left: str, right_title: str, right_body: str = "", note: str = "") -> None:
        cell = [Paragraph(right_title, strong)]
        if right_body:
            cell.append(Paragraph(right_body, body))
        if note:
            cell.append(Paragraph(note, small))
        t = Table([[Paragraph(left, small), cell]], colWidths=[88, body_w - 88])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        story.append(KeepTogether(t))

    def chips(values: list[str]) -> None:
        if values:
            story.append(Paragraph(" · ".join(_esc(v) for v in values), body))

    if kind == "CV":
        if data.get("summary"):
            section("Perfil")
            story.append(Paragraph(_esc(data["summary"]), body))
        info = []
        show = data.get("show") or {}
        if data.get("birth_date") and show.get("birth_date", True):
            info.append(f"Data de nascimento: {_esc(data['birth_date'])}")
        if data.get("nationality"):
            info.append(f"Nacionalidade: {_esc(data['nationality'])}")
        if payload.get("belt"):
            info.append(f"Graduação: {_esc(payload['belt']['label'])}")
        if info:
            story.append(Spacer(1, 4))
            story.append(Paragraph(" · ".join(info), small))
        experiences = list(data.get("experiences") or [])
        clubs = payload.get("clubs") or []
        if experiences or (clubs and show.get("clubs", True)):
            section("Experiência como treinador")
            for e in experiences:
                period = f"{_ym(e.get('start'))} – {'atual' if e.get('current') else _ym(e.get('end'))}"
                place = ", ".join(x for x in (e.get("organization"), e.get("city")) if x)
                row(period, _esc(e.get("role") or ""), _esc(place), _esc(e.get("description")))
            if show.get("clubs", True):
                named = {(e.get("organization") or "").lower() for e in experiences}
                for c in clubs:
                    if c["name"].lower() in named:
                        continue
                    period = f"{_d(c['since'])[-7:] if c['since'] else ''} – {'atual' if c['active'] else ''}"
                    courses = ", ".join(c["courses"][:6])
                    row(period, "Treinador", _esc(c["name"]), _esc(courses))
        education = data.get("education") or []
        if education:
            section("Formação académica e profissional")
            for e in education:
                period = f"{_ym(e.get('start'))} – {_ym(e.get('end'))}".strip(" –")
                row(period, _esc(e.get("title") or ""), _esc(e.get("institution")), _esc(e.get("description")))
        docs = [d for d in payload.get("documents") or [] if d["show_in_cv"]]
        if docs:
            section("Qualificações e certificações")
            for d in docs:
                note = f"Válido até {_d(d['expires_on'])}" if d["expires_on"] else ""
                row(_d(d["issued_on"]) or d["category_label"], _esc(d["title"]),
                    _esc(" · ".join(x for x in (d["issuer"], d["category_label"]) if x)), note)
        skills = data.get("skills") or {}
        if any(skills.get(k) for k in ("technical", "pedagogical", "organizational")):
            section("Competências")
            for key, label in (("technical", "Técnicas"), ("pedagogical", "Pedagógicas"),
                               ("organizational", "Organizativas")):
                if skills.get(key):
                    story.append(Paragraph(f"<b>{label}:</b> " + " · ".join(_esc(s) for s in skills[key]), body))
        if data.get("specializations"):
            section("Especializações")
            chips(data["specializations"])
        if data.get("languages"):
            section("Línguas")
            chips([f"{lang.get('name')}{' — ' + lang['level'] if lang.get('level') else ''}"
                   for lang in data["languages"] if lang.get("name")])
        for extra in data.get("custom_sections") or []:
            if extra.get("title") and extra.get("body"):
                section(extra["title"])
                story.append(Paragraph(_esc(extra["body"]), body))
    else:
        athlete, coach = payload["athlete"], payload["coach"]
        medals = athlete["medals"]
        stats = []
        if payload.get("belt"):
            stats.append(f"Graduação: <b>{_esc(payload['belt']['label'])}</b>")
        if athlete["competitions"]:
            stats.append(f"Competições: <b>{athlete['competitions']}</b>")
        if sum(medals.values()):
            stats.append(f"Medalhas: <b>{medals['GOLD']}</b> ouro · <b>{medals['SILVER']}</b> prata · "
                         f"<b>{medals['BRONZE']}</b> bronze")
        if stats:
            story.append(Paragraph(" &nbsp;|&nbsp; ".join(stats), body))

        def item_row(i: dict) -> None:
            when = _d(i["date"])
            bits = [i["kind_label"], i["level_label"], i["category"], i["club"], i["location"]]
            right = " · ".join(_esc(b) for b in bits if b)
            result = " · ".join(x for x in (i["placement_label"], i["result"]) if x)
            note = (_esc(result) + ("  " if result else "")) + ("<i>(declarado)</i>" if i["source"] == "MANUAL" else "")
            row(when, _esc(i["title"]), right, note)

        if athlete["items"]:
            section("Carreira competitiva (atleta)")
            for i in athlete["items"]:
                item_row(i)
        if coach["clubs"] or coach["items"]:
            section("Carreira técnica (treinador)")
            for c in coach["clubs"]:
                period = f"{_d(c['since'])[-7:] if c['since'] else ''} – {'atual' if c['active'] else ''}"
                row(period, _esc(c["name"]), _esc(", ".join(c["courses"][:6])))
            for i in coach["items"]:
                item_row(i)
        if payload["grades"]:
            section("Graduações")
            for g in payload["grades"]:
                row(_d(g["date"]), _esc(g["label"]), _esc(g["club"]),
                    "<i>(declarado)</i>" if g["source"] == "MANUAL" else "")
        story.append(Spacer(1, 10))
        story.append(Paragraph("Os resultados oficiais vêm do registo dos clubes na plataforma; os assinalados como "
                               "«declarado» foram acrescentados pelo próprio.", small))
    if not story:
        story.append(Paragraph("Ainda sem conteúdo.", small))
    doc.build(story)
    return buf.getvalue()


async def pdf(db: AsyncSession, *, user: User, kind: str) -> tuple[bytes, str]:
    """Il PDF di oggi (anteprima o versione da salvare) e il nome del file."""
    from app.core.storage import read_media_url

    if kind not in ("CV", "SPORT"):
        raise ClubValidationError("Che curriculum?")
    payload = await cv(db, user=user) if kind == "CV" else await sport_history(db, user=user)
    photo = read_media_url(payload["me"].get("photo_url") or "")
    today = utcnow().date()
    content = render_pdf(kind=kind, payload=payload, photo=photo, generated_on=today)
    slug = "-".join((payload["me"].get("name") or "treinador").lower().split())[:60]
    return content, f"{'curriculum' if kind == 'CV' else 'curriculum-desportivo'}-{slug}-{today.isoformat()}.pdf"


async def save_export(db: AsyncSession, *, user: User, kind: str, note: str | None) -> CoachCvExport:
    """Una versione del PDF, salvata nel bucket privato: quella mandata a un
    club resta com'era anche se il profilo cambia."""
    from app.core.storage import upload_document

    content, filename = await pdf(db, user=user, kind=kind)
    key = upload_document(file_bytes=content, content_type="application/pdf", key_prefix=f"coach-cv/{user.id}")
    row = CoachCvExport(organization_id=user.organization_id, user_id=user.id, kind=kind, storage_key=key,
                        filename=filename, size_bytes=len(content), note=(note or "").strip()[:200] or None)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_exports(db: AsyncSession, *, user: User) -> list[CoachCvExport]:
    return list((await db.execute(select(CoachCvExport).where(CoachCvExport.user_id == user.id)
                                  .order_by(CoachCvExport.created_at.desc()))).scalars())


async def get_export(db: AsyncSession, *, user: User, export_id: uuid.UUID) -> CoachCvExport:
    row = await db.get(CoachCvExport, export_id)
    if row is None or row.user_id != user.id:
        raise ClubNotFoundError("Versione non trovata.")
    return row


async def delete_export(db: AsyncSession, *, user: User, export_id: uuid.UUID) -> None:
    from app.core.storage import delete_document_object

    row = await get_export(db, user=user, export_id=export_id)
    key = row.storage_key
    await db.delete(row)
    await db.commit()
    delete_document_object(storage_key=key)
