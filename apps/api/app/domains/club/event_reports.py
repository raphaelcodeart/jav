"""I relatórios degli eventi: dopo una gara (o uno stage) il treinador
racconta com'è andata, mette le spese voce per voce e le foto; i risultati
degli atleti del club non li riscrive, si leggono dalle iscrizioni. La
segreteria li vede tutti, ne scrive anche lei, e ne stampa un PDF unico per
un periodo (un mese, un anno, da… a…). Specifica: docs/club-portal.md,
"Risultati dal treinador, scheda dell'evento e relatórios".

Chi può cosa:
- il treinador (`club.instruct`) crea i suoi relatórios e modifica solo i
  suoi; vede i suoi;
- la segreteria (`club.manage`) vede, crea e modifica tutti quelli del club
  ed è l'unica a esportare il PDF.

Le foto stanno nel bucket **privato**: il relatório è un documento interno
con foto di minori. Si ottimizzano come quelle del sito (optimize_image:
girate, ridotte, senza GPS) prima di salvarle.
"""

import io
import uuid
from datetime import date
from xml.sax.saxutils import escape

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.club import competitions
from app.domains.club.models import (
    EVENT_REPORT_COST_KINDS,
    ClubAthlete,
    ClubCompetition,
    ClubCompetitionEntry,
    ClubEventReport,
    ClubEventReportCost,
    ClubEventReportPhoto,
)
from app.domains.club.scope import ClubScope
from app.domains.club.service import ClubNotFoundError, ClubValidationError

#: Le foto di un relatório: abbastanza per raccontare una giornata.
MAX_PHOTOS = 12
MAX_PHOTO_BYTES = 15 * 1024 * 1024
PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}
#: Un PDF di più di così non si stampa: tre anni bastano.
MAX_EXPORT_DAYS = 3 * 366


# --- Lettura --------------------------------------------------------------------------------------


async def get_report(db: AsyncSession, *, scope: ClubScope, report_id: uuid.UUID) -> ClubEventReport:
    report = await db.get(ClubEventReport, report_id)
    if report is None or report.club_id != scope.club_id:
        raise ClubNotFoundError("Relatório non trovato.")
    return report


def _check_owner(report: ClubEventReport, *, user_id: uuid.UUID, can_manage: bool) -> None:
    # Un treinador non vede né tocca il relatório di un collega: per lui è
    # come se non ci fosse.
    if not can_manage and report.author_user_id != user_id:
        raise ClubNotFoundError("Relatório non trovato.")


async def results_of(db: AsyncSession, *, scope: ClubScope, comp: ClubCompetition) -> list[dict]:
    """I risultati degli atleti del club in quell'evento, dalle iscrizioni:
    prima le medaglie, poi gli altri piazzamenti, poi chi non ha ancora un
    risultato."""
    pairs = (await db.execute(
        select(ClubCompetitionEntry, ClubAthlete)
        .join(ClubAthlete, ClubAthlete.id == ClubCompetitionEntry.athlete_id)
        .where(
            ClubCompetitionEntry.competition_id == comp.id, ClubCompetitionEntry.club_id == scope.club_id,
            ClubCompetitionEntry.status == "REGISTERED",
        )
    )).all()

    def order(pair) -> tuple:
        entry, athlete = pair
        p = entry.placement
        key = 99 if p is None else (50 + (entry.rank or 0) / 1000 if p == 0 else p)
        return key, athlete.last_name, athlete.first_name

    return [
        {
            "athlete_id": a.id, "athlete_name": f"{a.first_name} {a.last_name}", "category": e.category,
            "weight_kg": e.weight_kg, "placement": e.placement, "rank": e.rank, "result_notes": e.result_notes,
            "points": competitions.points_for(placement=e.placement, level=comp.level)
            if comp.kind == "COMPETITION" else 0,
        }
        for e, a in sorted(pairs, key=order)
    ]


async def report_dict(
    db: AsyncSession, *, scope: ClubScope, report: ClubEventReport, comp: ClubCompetition | None = None,
    author_names: dict | None = None, photo_urls: bool = True,
) -> dict:
    from app.core.storage import generate_presigned_document_url
    from app.domains.club.people import _names

    comp = comp or await db.get(ClubCompetition, report.competition_id)
    costs = {
        c.kind: c for c in (await db.execute(
            select(ClubEventReportCost).where(ClubEventReportCost.report_id == report.id)
        )).scalars()
    }
    photos = list((await db.execute(
        select(ClubEventReportPhoto).where(ClubEventReportPhoto.report_id == report.id)
        .order_by(ClubEventReportPhoto.created_at)
    )).scalars())
    if author_names is None:
        author_names = await _names(db, {report.author_user_id})
    cost_rows = [
        {"kind": kind, "amount_cents": costs[kind].amount_cents if kind in costs else 0,
         "note": costs[kind].note if kind in costs else None}
        for kind in EVENT_REPORT_COST_KINDS
    ]
    return {
        "id": report.id, "competition_id": comp.id, "competition_name": comp.name, "competition_kind": comp.kind,
        "competition_level": comp.level, "starts_on": comp.starts_on, "ends_on": comp.ends_on,
        "location": comp.location,
        "author_user_id": report.author_user_id, "author_name": author_names.get(report.author_user_id) or "—",
        "title": report.title, "description": report.description, "narrative": report.narrative,
        "costs": cost_rows, "total_cents": sum(c["amount_cents"] for c in cost_rows),
        "photos": [
            {"id": p.id, "storage_key": p.storage_key,
             "url": generate_presigned_document_url(storage_key=p.storage_key, expires_in_seconds=900)
             if photo_urls else None}
            for p in photos
        ],
        "results": await results_of(db, scope=scope, comp=comp),
        "created_at": report.created_at, "updated_at": report.updated_at,
    }


async def list_reports(
    db: AsyncSession, *, scope: ClubScope, author_user_id: uuid.UUID | None = None,
    date_from: date | None = None, date_to: date | None = None,
) -> list[tuple[ClubEventReport, ClubCompetition]]:
    """I relatórios del club (di un autore solo, se `author_user_id`), per
    data dell'evento: dal più recente."""
    stmt = (
        select(ClubEventReport, ClubCompetition)
        .join(ClubCompetition, ClubCompetition.id == ClubEventReport.competition_id)
        .where(ClubEventReport.club_id == scope.club_id)
    )
    if author_user_id is not None:
        stmt = stmt.where(ClubEventReport.author_user_id == author_user_id)
    if date_from is not None:
        stmt = stmt.where(ClubCompetition.starts_on >= date_from)
    if date_to is not None:
        stmt = stmt.where(ClubCompetition.starts_on <= date_to)
    stmt = stmt.order_by(ClubCompetition.starts_on.desc(), ClubEventReport.created_at)
    return [(r, c) for r, c in (await db.execute(stmt)).all()]


# --- Scrittura ------------------------------------------------------------------------------------


def _clean(data: dict) -> dict:
    out = {}
    if "title" in data:
        title = (data["title"] or "").strip()
        if len(title) < 3:
            raise ClubValidationError("Dai un titolo al relatório (almeno 3 caratteri).")
        out["title"] = title[:200]
    for key, limit in (("description", 4000), ("narrative", 20000)):
        if key in data:
            out[key] = (data[key] or "").strip()[:limit] or None
    return out


async def _set_costs(db: AsyncSession, *, report: ClubEventReport, costs: list[dict]) -> None:
    """Le spese arrivano tutte insieme: una voce assente o a zero e senza nota
    si toglie."""
    seen: set[str] = set()
    for c in costs:
        kind = c.get("kind")
        if kind not in EVENT_REPORT_COST_KINDS:
            raise ClubValidationError("Voce di spesa non valida.")
        if kind in seen:
            raise ClubValidationError("Ogni voce di spesa va scritta una volta sola.")
        seen.add(kind)
        amount = c.get("amount_cents") or 0
        if amount < 0 or amount > 100_000_000:
            raise ClubValidationError("Un importo non può essere negativo.")
    existing = {
        c.kind: c for c in (await db.execute(
            select(ClubEventReportCost).where(ClubEventReportCost.report_id == report.id)
        )).scalars()
    }
    wanted = {c["kind"]: c for c in costs}
    for kind in EVENT_REPORT_COST_KINDS:
        c = wanted.get(kind)
        amount = (c or {}).get("amount_cents") or 0
        note = ((c or {}).get("note") or "").strip()[:300] or None
        row = existing.get(kind)
        if not amount and not note:
            if row is not None:
                await db.delete(row)
            continue
        if row is None:
            db.add(ClubEventReportCost(report_id=report.id, kind=kind, amount_cents=amount, note=note))
        else:
            row.amount_cents, row.note = amount, note


async def create_report(
    db: AsyncSession, *, scope: ClubScope, competition_id: uuid.UUID, author_user_id: uuid.UUID, data: dict,
) -> ClubEventReport:
    comp = await competitions.get_competition(db, scope=scope, competition_id=competition_id)
    already = (await db.execute(select(ClubEventReport.id).where(
        ClubEventReport.club_id == scope.club_id, ClubEventReport.competition_id == comp.id,
        ClubEventReport.author_user_id == author_user_id,
    ))).scalar_one_or_none()
    if already is not None:
        raise ClubValidationError("Hai già un relatório per questo evento: aprilo per modificarlo.")
    clean = _clean({"title": data.get("title") or comp.name, **{k: data.get(k) for k in ("description", "narrative")}})
    report = ClubEventReport(**scope.columns(), competition_id=comp.id, author_user_id=author_user_id, **clean)
    db.add(report)
    await db.flush()
    await _set_costs(db, report=report, costs=data.get("costs") or [])
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=author_user_id,
        action="club.event_report_created", entity_type="club_event_report", entity_id=str(report.id),
        new_value={"competition_id": str(comp.id), "title": report.title},
    )
    await db.commit()
    await db.refresh(report)
    return report


async def update_report(
    db: AsyncSession, *, scope: ClubScope, report_id: uuid.UUID, actor_user_id: uuid.UUID, can_manage: bool,
    data: dict,
) -> ClubEventReport:
    report = await get_report(db, scope=scope, report_id=report_id)
    _check_owner(report, user_id=actor_user_id, can_manage=can_manage)
    for key, value in _clean(data).items():
        setattr(report, key, value)
    if data.get("costs") is not None:
        await _set_costs(db, report=report, costs=data["costs"])
    report.updated_at = utcnow()
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.event_report_updated", entity_type="club_event_report", entity_id=str(report.id),
        new_value={"fields": sorted(data)},
    )
    await db.commit()
    await db.refresh(report)
    return report


async def delete_report(
    db: AsyncSession, *, scope: ClubScope, report_id: uuid.UUID, actor_user_id: uuid.UUID, can_manage: bool,
) -> None:
    from app.core.storage import delete_document_object

    report = await get_report(db, scope=scope, report_id=report_id)
    _check_owner(report, user_id=actor_user_id, can_manage=can_manage)
    keys = list((await db.execute(
        select(ClubEventReportPhoto.storage_key).where(ClubEventReportPhoto.report_id == report.id)
    )).scalars())
    # Spese e foto se ne vanno con il relatório (ON DELETE CASCADE).
    await db.delete(report)
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.event_report_deleted", entity_type="club_event_report", entity_id=str(report_id),
    )
    await db.commit()
    for key in keys:
        delete_document_object(storage_key=key)


async def add_photo(
    db: AsyncSession, *, scope: ClubScope, report_id: uuid.UUID, actor_user_id: uuid.UUID, can_manage: bool,
    file_bytes: bytes, content_type: str,
) -> ClubEventReportPhoto:
    from app.core.storage import UploadValidationError, optimize_image, upload_document

    report = await get_report(db, scope=scope, report_id=report_id)
    _check_owner(report, user_id=actor_user_id, can_manage=can_manage)
    count = len(list((await db.execute(
        select(ClubEventReportPhoto.id).where(ClubEventReportPhoto.report_id == report.id)
    )).scalars()))
    if count >= MAX_PHOTOS:
        raise ClubValidationError(f"Un relatório ha al massimo {MAX_PHOTOS} foto: togline una per aggiungerne un'altra.")
    if content_type not in PHOTO_TYPES or len(file_bytes) > MAX_PHOTO_BYTES:
        raise ClubValidationError("La foto deve essere un JPG, PNG o WebP di massimo 15 MB.")
    try:
        optimized, optimized_type = optimize_image(file_bytes, content_type)
        key = upload_document(file_bytes=optimized, content_type=optimized_type,
                              key_prefix=f"club-event-reports/{scope.club_id}/{report.id}")
    except UploadValidationError as exc:
        raise ClubValidationError("La foto non si riesce ad aprire: prova con un JPG o un PNG.") from exc
    photo = ClubEventReportPhoto(report_id=report.id, storage_key=key, content_type=optimized_type)
    db.add(photo)
    report.updated_at = utcnow()
    await db.commit()
    await db.refresh(photo)
    return photo


async def remove_photo(
    db: AsyncSession, *, scope: ClubScope, report_id: uuid.UUID, photo_id: uuid.UUID, actor_user_id: uuid.UUID,
    can_manage: bool,
) -> None:
    from app.core.storage import delete_document_object

    report = await get_report(db, scope=scope, report_id=report_id)
    _check_owner(report, user_id=actor_user_id, can_manage=can_manage)
    photo = await db.get(ClubEventReportPhoto, photo_id)
    if photo is None or photo.report_id != report.id:
        raise ClubNotFoundError("Foto non trovata.")
    key = photo.storage_key
    await db.delete(photo)
    report.updated_at = utcnow()
    await db.commit()
    delete_document_object(storage_key=key)


# --- Il PDF della segreteria ----------------------------------------------------------------------


async def export_reports(
    db: AsyncSession, *, scope: ClubScope, date_from: date, date_to: date,
) -> list[dict]:
    """Tutti i relatórios degli eventi del periodo, pronti per render_pdf."""
    from app.domains.club.people import _names

    if date_to < date_from:
        raise ClubValidationError("La data di fine è prima di quella di inizio.")
    if (date_to - date_from).days > MAX_EXPORT_DAYS:
        raise ClubValidationError("Scegli un periodo di al massimo tre anni.")
    pairs = await list_reports(db, scope=scope, date_from=date_from, date_to=date_to)
    pairs.reverse()  # nel PDF in ordine di data, dal primo evento
    names = await _names(db, {r.author_user_id for r, _c in pairs})
    return [
        await report_dict(db, scope=scope, report=r, comp=c, author_names=names, photo_urls=False)
        for r, c in pairs
    ]


#: Colore, nome e fondo della riga di ogni medaglia.
MEDAL = {1: ("#D4A017", "Ouro", "#FEF6D8"), 2: ("#9CA3AF", "Prata", "#F1F2F4"), 3: ("#B45309", "Bronze", "#FBEBDD")}
COST_PT = {"HOTEL": "Alojamento", "TRAVEL": "Viagem / voos", "FUEL": "Combustível", "FOOD": "Alimentação",
           "ENTRY_FEES": "Inscrições", "OTHER": "Outros"}


def _euro(cents: int) -> str:
    whole, rest = divmod(abs(cents), 100)
    return f"{'-' if cents < 0 else ''}{whole:,}".replace(",", ".") + f",{rest:02d} €"


def _day(d: date) -> str:
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


def _result_label(r: dict) -> str:
    p = r["placement"]
    if p is None:
        return "—"
    if p == 0:
        return f"{r['rank']}.º lugar" if r.get("rank") else "Participação"
    return f"{p}.º lugar"


def _period_label(date_from: date, date_to: date) -> str:
    import calendar as stdcal

    from app.domains.club.calendar import MONTHS_PT

    if date_from.day == 1 and date_to == date(date_from.year, date_from.month,
                                               stdcal.monthrange(date_from.year, date_from.month)[1]):
        return f"{MONTHS_PT[date_from.month - 1]} {date_from.year}"
    if (date_from.month, date_from.day) == (1, 1) and (date_to.month, date_to.day) == (12, 31) \
            and date_from.year == date_to.year:
        return f"Ano {date_from.year}"
    return f"{_day(date_from)} – {_day(date_to)}"


def _medal_flowable():
    from reportlab.lib import colors
    from reportlab.platypus import Flowable

    class Medal(Flowable):
        def __init__(self, place: int, color: str) -> None:
            super().__init__()
            self.place, self.color = place, color
            self.width = self.height = 16

        def draw(self) -> None:
            c = self.canv
            c.setFillColor(colors.HexColor(self.color))
            c.circle(8, 8, 8, stroke=0, fill=1)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 9)
            c.drawCentredString(8, 4.8, str(self.place))

    return Medal


def render_pdf(
    *, reports: list[dict], date_from: date, date_to: date, club_name: str, generated_on: date,
    photo_loader=None,
) -> bytes:
    """Un PDF solo per tutti i relatórios del periodo, nello stile del flyer
    (calendar.render_flyer): la copertina con la barra dorata, il logo
    JudoArteVida, i numeri del periodo (eventi, atleti, medaglie, spese) e
    l'indice; poi un relatório per pagina (o più, se è lungo): l'evento, i
    risultati con le medaglie colorate, le spese voce per voce, il racconto
    del treinador e le foto. In portoghese, come il calendário.
    `photo_loader(storage_key) -> bytes | None` legge le foto dal bucket
    privato (None nei test o se una foto non c'è più)."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import (
        BaseDocTemplate,
        Frame,
        Image,
        KeepTogether,
        NextPageTemplate,
        PageBreak,
        PageTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )

    from app.domains.club.calendar import KIND_COLOR, KIND_PT, LEVEL_PT, LOGO_JAV

    _Medal = _medal_flowable()
    W, H = A4
    margin = 32
    ink, muted, line = colors.HexColor("#1F2328"), colors.HexColor("#6B7280"), colors.HexColor("#E5E7EB")
    brand = colors.HexColor("#C8311A")
    period = _period_label(date_from, date_to)
    buf = io.BytesIO()

    def gold_bar(pdf, height: float) -> None:
        steps = 24
        for i in range(steps):
            t = i / (steps - 1)
            pdf.setFillColorRGB(0.72 + 0.24 * t, 0.53 + 0.27 * t, 0.12 + 0.22 * t)
            pdf.rect(W * i / steps, H - height, W / steps + 1, height, stroke=0, fill=1)

    def footer(pdf, doc) -> None:
        pdf.saveState()
        pdf.setFillColor(muted)
        pdf.setFont("Helvetica", 8)
        pdf.drawString(margin, 18, f"Relatórios de eventos · {period} · {club_name}")
        pdf.drawRightString(W - margin, 18, f"página {doc.page} · gerado a {_day(generated_on)}")
        pdf.restoreState()

    def cover(pdf, doc) -> None:
        pdf.saveState()
        gold_bar(pdf, 120)
        pdf.setFillColor(colors.HexColor("#3B2A05"))
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(margin, H - 40, "RELATÓRIOS DE EVENTOS")
        pdf.setFont("Helvetica-Bold", 30)
        pdf.drawString(margin, H - 80, period.upper())
        pdf.setFont("Helvetica", 11)
        pdf.drawString(margin, H - 102, club_name)
        if LOGO_JAV.exists():
            logo_h = 54
            pdf.drawImage(ImageReader(str(LOGO_JAV)), W - margin - logo_h * 720 / 312, H - 100,
                          logo_h * 720 / 312, logo_h, mask="auto")
        pdf.restoreState()
        footer(pdf, doc)

    def report_page(pdf, doc) -> None:
        pdf.saveState()
        gold_bar(pdf, 8)
        pdf.restoreState()
        footer(pdf, doc)

    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=margin, rightMargin=margin, topMargin=margin + 8,
                          bottomMargin=40, title=f"Relatórios de eventos — {period}", author=club_name)
    body_w = W - 2 * margin
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[Frame(margin, 40, body_w, H - 40 - 140, id="c")], onPage=cover),
        PageTemplate(id="report", frames=[Frame(margin, 40, body_w, H - 40 - margin - 8, id="r")], onPage=report_page),
    ])

    def style(name, **kw) -> ParagraphStyle:
        base = {"fontName": "Helvetica", "fontSize": 10, "leading": 14, "textColor": ink, "alignment": TA_LEFT}
        return ParagraphStyle(name, **{**base, **kw})

    s_body = style("body")
    s_story = style("story", fontSize=10.5, leading=15, spaceAfter=7)
    s_small = style("small", fontSize=8.5, leading=11, textColor=muted)
    s_h2 = style("h2", fontName="Helvetica-Bold", fontSize=12.5, leading=16, spaceBefore=10, spaceAfter=6,
                 textColor=brand)
    s_title = style("title", fontName="Helvetica-Bold", fontSize=14, leading=18, spaceAfter=4)
    s_cell = style("cell", fontSize=9, leading=11.5)
    s_cell_b = style("cellb", fontName="Helvetica-Bold", fontSize=9, leading=11.5)
    s_tag = style("tag", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=colors.white)

    def para(text: str | None, st=s_body) -> Paragraph:
        return Paragraph(escape(text or "").replace("\n", "<br/>"), st)

    story: list = []

    # --- Copertina: i numeri del periodo e l'indice -------------------------
    athletes = {r["athlete_id"] for rep in reports for r in rep["results"]}
    medals = {p: sum(1 for rep in reports for r in rep["results"] if r["placement"] == p) for p in (1, 2, 3)}
    total = sum(rep["total_cents"] for rep in reports)
    tiles = [("Relatórios", str(len(reports)), ink), ("Atletas", str(len(athletes)), ink),
             ("Ouro", str(medals[1]), colors.HexColor(MEDAL[1][0])),
             ("Prata", str(medals[2]), colors.HexColor(MEDAL[2][0])),
             ("Bronze", str(medals[3]), colors.HexColor(MEDAL[3][0])), ("Custos", _euro(total), brand)]
    tile_w = body_w / len(tiles)
    tile_table = Table(
        [[Paragraph(f'<font size="16"><b>{escape(v)}</b></font>', style("tv", alignment=1, textColor=c, leading=20))
          for _l, v, c in tiles],
         [Paragraph(escape(label.upper()), style("tl", fontSize=7.5, alignment=1, textColor=muted))
          for label, _v, _c in tiles]],
        colWidths=[tile_w] * len(tiles),
    )
    tile_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F9FAFB")),
        ("BOX", (0, 0), (-1, -1), 0.6, line), ("LINEAFTER", (0, 0), (-2, -1), 0.6, line),
        ("TOPPADDING", (0, 0), (-1, 0), 12), ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
    ]))
    story += [Spacer(1, 6), tile_table, Spacer(1, 18)]
    if not reports:
        story += [Spacer(1, 60), Paragraph("Sem relatórios neste período", style("e", fontName="Helvetica-Bold",
                                                                                 fontSize=16, alignment=1)),
                  Spacer(1, 6), Paragraph("Os treinadores escrevem o relatório depois de cada evento.",
                                          style("e2", alignment=1, textColor=muted))]
    else:
        story.append(Paragraph("Índice", s_h2))
        rows = [[Paragraph("<b>Data</b>", s_cell), Paragraph("<b>Evento</b>", s_cell),
                 Paragraph("<b>Autor</b>", s_cell), Paragraph("<b>Medalhas</b>", s_cell),
                 Paragraph("<b>Custos</b>", s_cell)]]
        for rep in reports:
            m = [sum(1 for r in rep["results"] if r["placement"] == p) for p in (1, 2, 3)]
            rows.append([
                para(_day(rep["starts_on"]), s_cell), para(f"{rep['competition_name']}\n{rep['title']}"
                                                           if rep["title"] != rep["competition_name"]
                                                           else rep["competition_name"], s_cell),
                para(rep["author_name"], s_cell),
                Paragraph(" · ".join(f'<font color="{MEDAL[p][0]}"><b>{n}</b></font>' for p, n in zip((1, 2, 3), m, strict=True)),
                          s_cell),
                Paragraph(f"<b>{_euro(rep['total_cents'])}</b>", style("cr", fontSize=9, alignment=2)),
            ])
        index = Table(rows, colWidths=[62, body_w - 62 - 110 - 86 - 70, 110, 86, 70], repeatRows=1)
        index.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F4F6")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFAFA")]),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, line), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(index)

    # --- Un relatório dopo l'altro ------------------------------------------
    for rep in reports:
        story += [NextPageTemplate("report"), PageBreak()]
        color = colors.HexColor(KIND_COLOR.get(rep["competition_kind"], "#4B5563"))
        tag = KIND_PT.get(rep["competition_kind"], rep["competition_kind"]).upper()
        if rep["competition_kind"] == "COMPETITION" and rep["competition_level"] != "CLUB":
            tag += f" · {LEVEL_PT.get(rep['competition_level'], rep['competition_level']).upper()}"
        dates = _day(rep["starts_on"]) + (f" – {_day(rep['ends_on'])}" if rep["ends_on"] != rep["starts_on"] else "")
        head = Table(
            [[Paragraph(escape(tag), s_tag)],
             [Paragraph(escape(rep["competition_name"]), style("hn", fontName="Helvetica-Bold", fontSize=17,
                                                               leading=21, textColor=colors.white))],
             [Paragraph(escape(" · ".join(p for p in (dates, rep["location"] or "") if p)),
                        style("hd", fontSize=10, textColor=colors.white))]],
            colWidths=[body_w], cornerRadii=[10, 10, 10, 10],
        )
        head.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), color), ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 0), (-1, 0), 12), ("BOTTOMPADDING", (0, -1), (-1, -1), 12),
        ]))
        story += [head, Spacer(1, 10), para(rep["title"], s_title)]
        written = rep["updated_at"] or rep["created_at"]
        story.append(para(f"Relatório de {rep['author_name']}"
                          + (f" · {_day(written.date())}" if written else ""), s_small))
        if rep["description"]:
            story += [Spacer(1, 6), para(rep["description"])]

        story.append(Paragraph("Resultados", s_h2))
        if rep["results"]:
            rows = [[Paragraph(f"<b>{h}</b>", s_cell) for h in ("Atleta", "Categoria", "Peso", "Resultado", "Pontos")]]
            styles = [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F4F6")),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, line), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
            for i, r in enumerate(rep["results"], start=1):
                medal = MEDAL.get(r["placement"] or -1)
                label = _result_label(r)
                cell = para(label, s_cell)
                if medal:
                    # La medaglia: un tondo del suo colore con il numero dentro.
                    cell = Table([[_Medal(r["placement"], medal[0]), Paragraph(f"<b>{label}</b> · {medal[1]}", s_cell)]],
                                 colWidths=[20, None])
                    cell.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                              ("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                                              ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
                name = escape(r["athlete_name"]) + (f'<br/><font size="7.5" color="#6B7280">{escape(r["result_notes"])}</font>'
                                                    if r.get("result_notes") else "")
                rows.append([Paragraph(name, s_cell_b), para(r["category"] or "—", s_cell),
                             para(f"{r['weight_kg']:g} kg" if r["weight_kg"] is not None else "—", s_cell),
                             cell, para(str(r["points"]) if r["placement"] is not None else "—", s_cell)])
                if medal:
                    styles.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor(medal[2])))
            results = Table(rows, colWidths=[body_w * 0.32, body_w * 0.22, body_w * 0.11, body_w * 0.25, body_w * 0.10],
                            repeatRows=1)
            results.setStyle(TableStyle(styles))
            story.append(results)
        else:
            story.append(para("Nenhum atleta do clube inscrito neste evento.", s_small))

        if rep["total_cents"] or any(c["note"] for c in rep["costs"]):
            rows = [[Paragraph("<b>Despesa</b>", s_cell), Paragraph("<b>Nota</b>", s_cell),
                     Paragraph("<b>Valor</b>", style("vh", fontSize=9, alignment=2))]]
            for c in rep["costs"]:
                if c["amount_cents"] or c["note"]:
                    rows.append([para(COST_PT.get(c["kind"], c["kind"]), s_cell_b), para(c["note"] or "", s_cell),
                                 Paragraph(_euro(c["amount_cents"]), style("vr", fontSize=9, alignment=2))])
            rows.append([Paragraph("<b>Total</b>", s_cell), "",
                         Paragraph(f"<b>{_euro(rep['total_cents'])}</b>", style("vt", fontSize=10, alignment=2))])
            costs = Table(rows, colWidths=[body_w * 0.25, body_w * 0.55, body_w * 0.20])
            costs.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F4F6")),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#FEF3C7")),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, line), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            story += [Paragraph("Custos", s_h2), KeepTogether(costs)]

        if rep["narrative"]:
            story += [Paragraph("Como correu", s_h2)]
            story += [para(chunk, s_story) for chunk in rep["narrative"].split("\n\n") if chunk.strip()]

        images = []
        for photo in rep["photos"]:
            data = photo_loader(photo["storage_key"]) if photo_loader else None
            if not data:
                continue
            try:
                reader = ImageReader(io.BytesIO(data))
                iw, ih = reader.getSize()
            except Exception:  # noqa: BLE001, S112 -- una foto rovinata non ferma il PDF
                continue
            cell_w = (body_w - 16) / 3
            scale = min((cell_w - 6) / iw, 120 / ih)
            images.append(Image(io.BytesIO(data), width=iw * scale, height=ih * scale))
        if images:
            story.append(Paragraph("Fotografias", s_h2))
            grid = [images[i:i + 3] + [""] * (3 - len(images[i:i + 3])) for i in range(0, len(images), 3)]
            photos = Table(grid, colWidths=[(body_w) / 3] * 3)
            photos.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
            story.append(photos)

    doc.build(story)
    return buf.getvalue()
