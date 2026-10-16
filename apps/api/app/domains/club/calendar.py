"""Il Calendário JudoArteVida: le prove di un periodo, del club e della
rete, come elenco (JSON per le schede e la lista dell'area riservata) e come
PDF da stampare. Specifica: docs/club-portal.md, "Il Calendário JudoArteVida".

Il PDF è una tabella sola, orizzontale, divisa per mesi: una riga colorata
con il mese («OUTUBRO 2026») e sotto le sue prove, poi il mese dopo, senza
interruzioni. Colonne: data, prova (con tipo e livello), local, estado,
escalões, notas. In portoghese, come il calendario della federazione.
"""

import io
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.club.competitions import visible_to
from app.domains.club.models import Club, ClubCompetition
from app.domains.club.scope import ClubScope
from app.domains.club.service import ClubValidationError

#: Un periodo più lungo di così non si stampa: due anni bastano.
MAX_DAYS = 731

MONTHS_PT = ("Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro",
             "Outubro", "Novembro", "Dezembro")
WEEKDAYS_PT = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")
KIND_PT = {"COMPETITION": "Competição", "STAGE": "Estágio", "REFEREEING": "Arbitragem", "EDUCATION": "Formação",
           "MEETING": "Reunião", "OTHER": "Outro"}
KIND_COLOR = {"COMPETITION": "#C8311A", "STAGE": "#0369A1", "REFEREEING": "#6D28D9", "EDUCATION": "#047857",
              "MEETING": "#B45309", "OTHER": "#4B5563"}
LEVEL_PT = {"CLUB": "Clube", "REGIONAL": "Regional", "ZONAL": "Zonal", "OPENS": "Open", "NATIONAL": "Nacional",
            "INTERNATIONAL": "Internacional", "EUROPEAN_CUP": "Taça da Europa",
            "EUROPEAN_CHAMPIONSHIP": "Campeonato da Europa", "WORLD_CHAMPIONSHIP": "Campeonato do Mundo",
            "OLYMPIC_GAMES": "Jogos Olímpicos"}
AGE_PT = {"benj_inf_inic": "Benjamins · Infantis · Iniciados", "juvenis": "Juvenis", "cadetes": "Cadetes",
          "juniores": "Juniores", "sub23": "Sub-23", "seniores": "Seniores", "veteranos": "Veteranos",
          "adaptado": "Judo adaptado", "katas": "Katas", "formacao": "Formação"}
STATUS_PT = {"OPEN": "Inscrições abertas", "CLOSED": "Inscrições fechadas", "DONE": "Realizada"}


async def calendar_events(db: AsyncSession, *, scope: ClubScope, date_from: date, date_to: date) -> list[dict]:
    if date_to < date_from:
        raise ClubValidationError("La data di fine è prima di quella di inizio.")
    if (date_to - date_from).days > MAX_DAYS:
        raise ClubValidationError("Scegli un periodo di al massimo due anni.")
    rows = (await db.execute(
        select(ClubCompetition, Club.name)
        .outerjoin(Club, Club.id == ClubCompetition.club_id)
        .where(visible_to(scope), ClubCompetition.ends_on >= date_from, ClubCompetition.starts_on <= date_to)
        .order_by(ClubCompetition.starts_on, ClubCompetition.name)
    )).all()
    return [
        {
            "id": c.id, "name": c.name, "kind": c.kind, "level": c.level, "status": c.status,
            "starts_on": c.starts_on, "ends_on": c.ends_on, "location": c.location, "organizer": c.organizer,
            "age_groups": list(c.age_groups or []), "description": c.description, "image_url": c.image_url,
            "registration_deadline": c.registration_deadline, "fee_cents": c.fee_cents,
            "club_name": club_name, "network": c.club_id is None, "circular_url": c.circular_url,
        }
        for c, club_name in rows
    ]


def _dates(e: dict) -> str:
    s, t = e["starts_on"], e["ends_on"]
    head = f"{WEEKDAYS_PT[s.weekday()]} {s.day:02d}"
    if t == s:
        return head
    if t.month == s.month:
        return f"{head}–{t.day:02d}"
    return f"{head} – {t.day:02d}/{t.month:02d}"


def _notes(e: dict) -> str:
    parts = []
    if e["organizer"]:
        parts.append(f"Org.: {e['organizer']}")
    if e["status"] == "OPEN" and e["registration_deadline"]:
        d = e["registration_deadline"]
        parts.append(f"Inscrições até {d.day:02d}/{d.month:02d}")
    if e["fee_cents"]:
        parts.append(f"{e['fee_cents'] / 100:.2f} €".replace(".", ","))
    if e["description"]:
        first = " ".join(e["description"].split())
        parts.append(first[:140] + ("…" if len(first) > 140 else ""))
    return " · ".join(parts)


def _escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_pdf(*, events: list[dict], date_from: date, date_to: date, club_name: str, generated_on: date) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    ink = colors.HexColor("#111827")
    brand = colors.HexColor("#C8311A")
    gold = colors.HexColor("#F3E017")
    title = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=ink)
    sub = ParagraphStyle("s", fontName="Helvetica", fontSize=9.5, leading=13, textColor=colors.HexColor("#4B5563"))
    cell = ParagraphStyle("c", fontName="Helvetica", fontSize=8.5, leading=10.5, textColor=ink)
    cell_b = ParagraphStyle("cb", parent=cell, fontName="Helvetica-Bold", fontSize=9)
    small = ParagraphStyle("sm", parent=cell, fontSize=7.5, leading=9.5, textColor=colors.HexColor("#4B5563"))
    head = ParagraphStyle("h", parent=cell, fontName="Helvetica-Bold", textColor=colors.white)
    month_style = ParagraphStyle("m", fontName="Helvetica-Bold", fontSize=11, leading=13, textColor=colors.white)

    widths = [24 * mm, 76 * mm, 40 * mm, 30 * mm, 44 * mm, 55 * mm]
    header = [Paragraph(h, head) for h in ("Data", "Prova", "Local", "Estado", "Escalões", "Notas")]
    base_style: list = [
        ("BACKGROUND", (0, 0), (-1, 0), ink),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 2), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
        # La riga del mese, sotto le intestazioni: tutte e due si ripetono
        # in cima a ogni pagina, così un mese lungo continua leggibile.
        ("SPAN", (0, 1), (-1, 1)), ("BACKGROUND", (0, 1), (-1, 1), brand),
        ("LINEBELOW", (0, 1), (-1, 1), 2, gold), ("TOPPADDING", (0, 1), (-1, 1), 6), ("BOTTOMPADDING", (0, 1), (-1, 1), 6),
    ]
    months: list[tuple[tuple[int, int], list[dict]]] = []
    for e in events:
        key = (e["starts_on"].year, e["starts_on"].month)
        if not months or months[-1][0] != key:
            months.append((key, []))
        months[-1][1].append(e)

    tables: list = []
    for (year, month), items in months:
        label = f"{MONTHS_PT[month - 1].upper()} {year}"
        n = len(items)
        data: list = [header, [Paragraph(f"{label} <font size=8 color='#FDE68A'>· {n} {'prova' if n == 1 else 'provas'}</font>",
                                         month_style), "", "", "", "", ""]]
        style = list(base_style)
        for i, e in enumerate(items):
            kind = KIND_PT.get(e["kind"], e["kind"])
            level = LEVEL_PT.get(e["level"], e["level"]) if e["kind"] == "COMPETITION" else None
            who = "Rede JudoArteVida" if e["network"] else (e["club_name"] or "")
            name = (f"<b>{_escape(e['name'])}</b><br/><font size=7.5 color='{KIND_COLOR.get(e['kind'], '#4B5563')}'>"
                    f"{_escape(' · '.join(x for x in (kind, level, who) if x))}</font>")
            ages = ", ".join(AGE_PT.get(a, a) for a in e["age_groups"]) or "Todos"
            data.append([
                Paragraph(_dates(e), cell_b), Paragraph(name, cell), Paragraph(_escape(e["location"] or "—"), cell),
                Paragraph(STATUS_PT.get(e["status"], e["status"]), small), Paragraph(_escape(ages), small),
                Paragraph(_escape(_notes(e)) or "—", small),
            ])
            r = len(data) - 1
            style.append(("LINEBEFORE", (0, r), (0, r), 3, colors.HexColor(KIND_COLOR.get(e["kind"], "#4B5563"))))
            if i % 2:
                style.append(("BACKGROUND", (0, r), (-1, r), colors.HexColor("#F9FAFB")))
        table = Table(data, colWidths=widths, repeatRows=2)
        table.setStyle(TableStyle(style))
        tables += [table, Spacer(1, 4 * mm)]
    if not events:
        tables.append(Paragraph("Nenhuma prova neste período.", cell))

    period = f"{date_from.day:02d}/{date_from.month:02d}/{date_from.year} – {date_to.day:02d}/{date_to.month:02d}/{date_to.year}"
    story = [
        Paragraph("Calendário <font color='#C8311A'>JudoArteVida</font>", title),
        Paragraph(f"{_escape(club_name)} · {period} · {len(events)} {'prova' if len(events) == 1 else 'provas'}", sub),
        Spacer(1, 5 * mm), *tables,
    ]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#6B7280"))
        canvas.drawString(14 * mm, 8 * mm, f"jav.ecodo.ai · gerado a {generated_on.day:02d}/{generated_on.month:02d}/{generated_on.year}")
        canvas.drawRightString(landscape(A4)[0] - 14 * mm, 8 * mm, f"Página {doc.page}")
        canvas.setFillColor(brand)
        canvas.rect(0, landscape(A4)[1] - 4 * mm, landscape(A4)[0], 4 * mm, stroke=0, fill=1)
        canvas.restoreState()

    buffer = io.BytesIO()
    SimpleDocTemplate(
        buffer, pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
        title="Calendário JudoArteVida", author=club_name,
    ).build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


LOGO = __import__("pathlib").Path(__file__).resolve().parents[2] / "assets" / "jav-logo.png"


def render_flyer(*, events: list[dict], year: int, month: int, club_name: str, generated_on: date) -> bytes:
    """Il flyer del mese: una pagina A4 da appendere o mandare su WhatsApp,
    con il logo JAV, il mese in grande e una scheda per prova (data, tipo,
    luogo, scadenza). Con molte prove le schede si stringono su tre colonne
    e, oltre, continuano in una seconda pagina."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader, simpleSplit
    from reportlab.pdfgen import canvas

    W, H = A4
    red, dark, yellow, ink = colors.HexColor("#C8311A"), colors.HexColor("#8E1F10"), colors.HexColor("#F7DB16"), colors.HexColor("#1F2328")
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    pdf.setTitle(f"Calendário JudoArteVida — {MONTHS_PT[month - 1]} {year}")
    margin = 28

    def header(first: bool) -> float:
        band = 168 if first else 92
        pdf.setFillColor(red)
        pdf.rect(0, H - band, W, band, stroke=0, fill=1)
        pdf.setFillColor(dark)
        pdf.circle(W - 40, H - 30, 120, stroke=0, fill=1)
        pdf.setFillColor(yellow)
        pdf.rect(0, H - band - 10, W, 10, stroke=0, fill=1)
        pdf.setFillColor(colors.HexColor("#6B7280"))
        pdf.rect(0, H - band - 13, W, 3, stroke=0, fill=1)
        if LOGO.exists():
            size = 74 if first else 52
            pdf.drawImage(ImageReader(str(LOGO)), margin, H - 18 - size, size * 1.1, size, mask="auto")
        pdf.setFillColor(colors.white)
        x = margin + (96 if first else 72)
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(x, H - 40, "CALENDÁRIO JUDOARTEVIDA")
        pdf.setFont("Helvetica-Bold", 40 if first else 26)
        pdf.drawString(x, H - (86 if first else 72), f"{MONTHS_PT[month - 1].upper()} {year}")
        if first:
            pdf.setFont("Helvetica", 12)
            n = len(events)
            pdf.drawString(x, H - 110, f"{n} {'evento' if n == 1 else 'eventos'} · {club_name}")
            pdf.setFont("Helvetica-Oblique", 10)
            pdf.drawString(x, H - 130, "Provas, estágios e formações da rede e do clube")
        return H - band - 13 - 18

    def footer() -> None:
        pdf.setFillColor(colors.HexColor("#6B7280"))
        pdf.setFont("Helvetica", 8)
        pdf.drawString(margin, 16, f"jav.ecodo.ai · gerado a {generated_on.day:02d}/{generated_on.month:02d}/{generated_on.year}")
        pdf.drawRightString(W - margin, 16, "Judo Arte e Vida")

    top = header(True)
    if not events:
        pdf.setFillColor(ink)
        pdf.setFont("Helvetica-Bold", 18)
        pdf.drawCentredString(W / 2, top - 120, "Sem eventos neste mês")
        pdf.setFont("Helvetica", 11)
        pdf.drawCentredString(W / 2, top - 142, "Fica atento: o calendário é atualizado ao longo da época.")
        footer()
        pdf.save()
        return buf.getvalue()

    cols = 2 if len(events) <= 10 else 3
    gap = 12
    card_w = (W - 2 * margin - gap * (cols - 1)) / cols
    card_h = 104 if cols == 2 else 92
    text_w = card_w - 64
    y = top
    col = 0
    for e in events:
        if col == 0 and y - card_h < 34:
            footer()
            pdf.showPage()
            y = header(False)
        x = margin + col * (card_w + gap)
        color = colors.HexColor(KIND_COLOR.get(e["kind"], "#4B5563"))
        # La scheda: ombra, fondo bianco, barra del tipo.
        pdf.setFillColor(colors.HexColor("#E5E7EB"))
        pdf.roundRect(x + 2, y - card_h - 2, card_w, card_h, 12, stroke=0, fill=1)
        pdf.setFillColor(colors.white)
        pdf.setStrokeColor(colors.HexColor("#E5E7EB"))
        pdf.roundRect(x, y - card_h, card_w, card_h, 12, stroke=1, fill=1)
        pdf.setFillColor(color)
        pdf.roundRect(x, y - card_h, 52, card_h, 12, stroke=0, fill=1)
        pdf.rect(x + 40, y - card_h, 12, card_h, stroke=0, fill=1)
        s, t = e["starts_on"], e["ends_on"]
        pdf.setFillColor(colors.white)
        pdf.setFont("Helvetica-Bold", 24)
        pdf.drawCentredString(x + 26, y - 40, f"{s.day:02d}")
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawCentredString(x + 26, y - 54, WEEKDAYS_PT[s.weekday()].upper())
        if t != s:
            pdf.setFont("Helvetica", 8)
            pdf.drawCentredString(x + 26, y - 68, f"a {t.day:02d}/{t.month:02d}")
        tx = x + 62
        pdf.setFillColor(color)
        pdf.setFont("Helvetica-Bold", 7.5)
        tag = KIND_PT.get(e["kind"], e["kind"]).upper()
        if e.get("level"):
            tag += f" · {LEVEL_PT.get(e['level'], e['level']).upper()}"
        pdf.drawString(tx, y - 16, tag[:60])
        pdf.setFillColor(ink)
        pdf.setFont("Helvetica-Bold", 11 if cols == 2 else 10)
        lines = simpleSplit(e["name"], "Helvetica-Bold", 11 if cols == 2 else 10, text_w)[:2]
        ly = y - 31
        for line in lines:
            pdf.drawString(tx, ly, line)
            ly -= 13
        pdf.setFont("Helvetica", 8.5)
        pdf.setFillColor(colors.HexColor("#4B5563"))
        if e["location"]:
            pdf.drawString(tx, ly - 2, simpleSplit(f"Local: {e['location']}", "Helvetica", 8.5, text_w)[0])
            ly -= 12
        ages = ", ".join(AGE_PT.get(a, a) for a in e["age_groups"])
        if ages:
            pdf.drawString(tx, ly - 2, simpleSplit(ages, "Helvetica", 8.5, text_w)[0])
            ly -= 12
        if e["status"] == "OPEN" and e["registration_deadline"]:
            d = e["registration_deadline"]
            label = f"Inscrições até {d.day:02d}/{d.month:02d}"
            pdf.setFillColor(colors.HexColor("#FEF3C7"))
            w = pdf.stringWidth(label, "Helvetica-Bold", 8) + 12
            pdf.roundRect(tx, y - card_h + 8, w, 14, 7, stroke=0, fill=1)
            pdf.setFillColor(colors.HexColor("#92400E"))
            pdf.setFont("Helvetica-Bold", 8)
            pdf.drawString(tx + 6, y - card_h + 12, label)
        col += 1
        if col == cols:
            col = 0
            y -= card_h + gap
    footer()
    pdf.save()
    return buf.getvalue()
