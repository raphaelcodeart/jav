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


LOGO_JAV = __import__("pathlib").Path(__file__).resolve().parents[2] / "assets" / "judoartevida-logo.jpg"
#: I social nell'ordine del flyer, con il loro colore.
FLYER_SOCIALS = (("facebook", "#1877F2"), ("instagram", "#E1306C"), ("youtube", "#FF0000"), ("site", "#1F2328"))


def _handle(kind: str, url: str) -> str:
    """Il nome breve sotto l'icona: «@ml8126», «jav.ecodo.ai»."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if kind == "site":
        return parsed.netloc or url
    path = parsed.path.strip("/").split("/")[0] if parsed.path else ""
    return (path if path.startswith("@") else f"@{path}") if path else parsed.netloc


def _social_glyph(pdf, kind: str, cx: float, cy: float, r: float) -> None:
    """Il disegno dentro il cerchio, in bianco: semplice e leggibile anche piccolo."""
    from reportlab.lib import colors

    pdf.setFillColor(colors.white)
    pdf.setStrokeColor(colors.white)
    if kind == "facebook":
        pdf.setFont("Helvetica-Bold", r * 1.35)
        pdf.drawCentredString(cx + r * 0.08, cy - r * 0.45, "f")
    elif kind == "instagram":
        pdf.setLineWidth(r * 0.12)
        pdf.roundRect(cx - r * 0.5, cy - r * 0.5, r, r, r * 0.28, stroke=1, fill=0)
        pdf.circle(cx, cy, r * 0.22, stroke=1, fill=0)
        pdf.circle(cx + r * 0.3, cy + r * 0.3, r * 0.06, stroke=0, fill=1)
    elif kind == "youtube":
        path = pdf.beginPath()
        path.moveTo(cx - r * 0.25, cy - r * 0.35)
        path.lineTo(cx - r * 0.25, cy + r * 0.35)
        path.lineTo(cx + r * 0.4, cy)
        path.close()
        pdf.drawPath(path, stroke=0, fill=1)
    else:
        pdf.setLineWidth(r * 0.1)
        pdf.circle(cx, cy, r * 0.5, stroke=1, fill=0)
        pdf.ellipse(cx - r * 0.22, cy - r * 0.5, cx + r * 0.22, cy + r * 0.5, stroke=1, fill=0)
        pdf.line(cx - r * 0.5, cy, cx + r * 0.5, cy)


def render_flyer(
    *, events: list[dict], year: int, month: int, club_name: str, generated_on: date,
    socials: dict[str, str] | None = None, site_url: str = "",
) -> bytes:
    """Il flyer del mese, una pagina A4 da appendere o mandare su WhatsApp:
    in alto la barra dorata «EVENTOS DO MÊS · OUTUBRO 2026», sotto il logo
    JudoArteVida con le icone rotonde di Facebook, Instagram, YouTube e del
    sito (cliccabili nel PDF), poi gli eventi, ognuno una riga larga quanto la
    pagina. L'altezza delle righe si adatta al numero di eventi e, se sono
    tanti, le righe vanno su due colonne: **sempre una pagina sola**."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader, simpleSplit
    from reportlab.pdfgen import canvas

    W, H = A4
    ink, muted = colors.HexColor("#1F2328"), colors.HexColor("#4B5563")
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    month_name = f"{MONTHS_PT[month - 1]} {year}"
    pdf.setTitle(f"Eventos do mês — {month_name}")
    margin = 26

    # --- La barra dorata ---------------------------------------------------
    bar = 64
    steps = 24
    for i in range(steps):
        # Un oro che va dal più scuro al più chiaro, da sinistra a destra.
        t = i / (steps - 1)
        r, g, b = 0.72 + 0.24 * t, 0.53 + 0.27 * t, 0.12 + 0.22 * t
        pdf.setFillColorRGB(r, g, b)
        pdf.rect(W * i / steps, H - bar, W / steps + 1, bar, stroke=0, fill=1)
    pdf.setFillColorRGB(1, 1, 1, alpha=0.25)
    pdf.rect(0, H - bar, W, 3, stroke=0, fill=1)
    pdf.setFillColor(colors.HexColor("#3B2A05"))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(margin, H - 24, "EVENTOS DO MÊS")
    pdf.setFont("Helvetica-Bold", 26)
    pdf.drawString(margin, H - 52, month_name.upper())
    n = len(events)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawRightString(W - margin, H - 40, f"{n} {'evento' if n == 1 else 'eventos'}")

    # --- Logo e social -----------------------------------------------------
    band_top = H - bar
    band = 96
    if LOGO_JAV.exists():
        logo_h = 62
        pdf.drawImage(ImageReader(str(LOGO_JAV)), margin, band_top - 14 - logo_h, logo_h * 720 / 312, logo_h, mask="auto")
    links = dict(socials or {})
    if site_url:
        links["site"] = site_url
    icons = [(kind, color, links.get(kind)) for kind, color in FLYER_SOCIALS if links.get(kind)]
    radius, step = 17, 74
    x = W - margin - step / 2 - step * (len(icons) - 1)
    cy = band_top - 40
    for kind, color, url in icons:
        pdf.setFillColor(colors.HexColor(color))
        pdf.circle(x, cy, radius, stroke=0, fill=1)
        _social_glyph(pdf, kind, x, cy, radius)
        pdf.setFillColor(muted)
        pdf.setFont("Helvetica", 7.5)
        label = _handle(kind, url)
        if pdf.stringWidth(label, "Helvetica", 7.5) > step - 6:
            label = simpleSplit(label, "Helvetica", 7.5, step - 12)[0] + "…"
        pdf.drawCentredString(x, cy - radius - 12, label)
        pdf.linkURL(url, (x - radius, cy - radius - 16, x + radius, cy + radius), relative=0)
        x += step
    line_y = band_top - band
    pdf.setStrokeColor(colors.HexColor("#E5E7EB"))
    pdf.setLineWidth(1)
    pdf.line(margin, line_y, W - margin, line_y)

    # --- Il piè di pagina ----------------------------------------------------
    pdf.setFillColor(colors.HexColor("#6B7280"))
    pdf.setFont("Helvetica", 8)
    pdf.drawString(margin, 18, f"{site_url.replace('https://', '').replace('http://', '') or 'JudoArteVida'} · {club_name}")
    pdf.drawRightString(W - margin, 18, f"gerado a {generated_on.day:02d}/{generated_on.month:02d}/{generated_on.year}")

    top = line_y - 14
    bottom = 36
    if not events:
        pdf.setFillColor(ink)
        pdf.setFont("Helvetica-Bold", 18)
        pdf.drawCentredString(W / 2, (top + bottom) / 2 + 10, "Sem eventos neste mês")
        pdf.setFont("Helvetica", 11)
        pdf.drawCentredString(W / 2, (top + bottom) / 2 - 12, "Fica atento: o calendário é atualizado ao longo da época.")
        pdf.save()
        return buf.getvalue()

    # --- Gli eventi: righe che stanno tutte nella pagina ---------------------
    gap = 6
    avail = top - bottom
    cols = 1
    # Una colonna finché le righe restano leggibili (circa 25 eventi); oltre,
    # due colonne di righe più basse: il nome deve restare intero il più possibile.
    if n > 16:
        gap = 4
    row_h = min(64.0, (avail - gap * (n - 1)) / n)
    if row_h < 21:
        cols = 2
        rows = -(-n // 2)
        gap = 4 if rows < 40 else 3
        row_h = min(46.0, (avail - gap * (rows - 1)) / rows)
    col_gap = 10
    row_w = (W - 2 * margin - col_gap * (cols - 1)) / cols
    rows_per_col = -(-n // cols)
    name_size = max(6.5, min(12.5, row_h * 0.27))
    small = max(5.5, min(8.5, row_h * 0.19))
    detail = row_h >= 26
    for i, e in enumerate(events):
        c, rix = divmod(i, rows_per_col)
        x = margin + c * (row_w + col_gap)
        y = top - rix * (row_h + gap)
        color = colors.HexColor(KIND_COLOR.get(e["kind"], "#4B5563"))
        radius_card = min(10, row_h / 3)
        # La riga: ombra, fondo bianco, la data nel colore del tipo.
        pdf.setFillColor(colors.HexColor("#E5E7EB"))
        pdf.roundRect(x + 1.5, y - row_h - 1.5, row_w, row_h, radius_card, stroke=0, fill=1)
        pdf.setFillColor(colors.white)
        pdf.setStrokeColor(colors.HexColor("#E5E7EB"))
        pdf.setLineWidth(0.6)
        pdf.roundRect(x, y - row_h, row_w, row_h, radius_card, stroke=1, fill=1)
        tile = max(30.0, min(62.0, row_h * (1.05 if cols == 1 else 0.95)))
        pdf.setFillColor(color)
        pdf.roundRect(x, y - row_h, tile, row_h, radius_card, stroke=0, fill=1)
        pdf.rect(x + tile - radius_card, y - row_h, radius_card, row_h, stroke=0, fill=1)
        s, t = e["starts_on"], e["ends_on"]
        pdf.setFillColor(colors.white)
        day_size = max(9.0, min(22.0, row_h * 0.42))
        mid = y - row_h / 2
        if row_h >= 26:
            pdf.setFont("Helvetica-Bold", day_size)
            pdf.drawCentredString(x + tile / 2, mid - day_size * 0.05, f"{s.day:02d}")
            pdf.setFont("Helvetica-Bold", max(5.5, day_size * 0.36))
            sub = WEEKDAYS_PT[s.weekday()].upper() + (f"–{t.day:02d}" if t != s else "")
            pdf.drawCentredString(x + tile / 2, mid - day_size * 0.05 - day_size * 0.55, sub)
        else:
            pdf.setFont("Helvetica-Bold", day_size)
            label = f"{s.day:02d}" + (f"–{t.day:02d}" if t != s else "")
            pdf.drawCentredString(x + tile / 2, mid - day_size * 0.35, label)
        # A destra: la scadenza delle iscrizioni, se aperte.
        right = x + row_w - 8
        pill_w = 0.0
        if e["status"] == "OPEN" and e["registration_deadline"] and row_w > 200:
            d = e["registration_deadline"]
            label = (f"Inscrições até {d.day:02d}/{d.month:02d}" if cols == 1 else f"até {d.day:02d}/{d.month:02d}")
            pill_font = max(5.5, min(8.0, small))
            pill_w = pdf.stringWidth(label, "Helvetica-Bold", pill_font) + 12
            ph = pill_font + 7
            pdf.setFillColor(colors.HexColor("#FEF3C7"))
            pdf.roundRect(right - pill_w, mid - ph / 2, pill_w, ph, ph / 2, stroke=0, fill=1)
            pdf.setFillColor(colors.HexColor("#92400E"))
            pdf.setFont("Helvetica-Bold", pill_font)
            pdf.drawString(right - pill_w + 6, mid - pill_font * 0.35, label)
            pill_w += 8
        tx = x + tile + 8
        text_w = right - pill_w - tx
        tag = KIND_PT.get(e["kind"], e["kind"]).upper()
        if e.get("level") and e["level"] != "CLUB":
            tag += f" · {LEVEL_PT.get(e['level'], e['level']).upper()}"
        ages = ", ".join(AGE_PT.get(a, a) for a in e["age_groups"])
        info = " · ".join(part for part in (e["location"] or "", ages) if part)
        lines_h = small + 2 + name_size + (small + 3 if detail and info else 0)
        ty = mid + lines_h / 2 - small
        pdf.setFillColor(color)
        pdf.setFont("Helvetica-Bold", small)
        pdf.drawString(tx, ty, simpleSplit(tag, "Helvetica-Bold", small, text_w)[0] if tag else "")
        ty -= name_size + 2
        pdf.setFillColor(ink)
        pdf.setFont("Helvetica-Bold", name_size)
        name_lines = simpleSplit(e["name"], "Helvetica-Bold", name_size, text_w) or [""]
        name = name_lines[0] + ("…" if len(name_lines) > 1 else "")
        pdf.drawString(tx, ty, name)
        if detail and info:
            ty -= small + 3
            pdf.setFillColor(muted)
            pdf.setFont("Helvetica", small)
            info_lines = simpleSplit(info, "Helvetica", small, text_w) or [""]
            pdf.drawString(tx, ty, info_lines[0] + ("…" if len(info_lines) > 1 else ""))
    pdf.save()
    return buf.getvalue()
