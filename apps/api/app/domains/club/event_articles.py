"""Il relatório final di una prova: dopo aver scritto risultati, spese, foto
e racconto nel relatório (event_reports.py), il treinador ne ricava un
articolo breve, come quelli del giornale locale — che cosa, dove, chi ha
vinto che cosa, quanto è costato — da rileggere, ritoccare e stampare.

Due modi di scriverlo, stesso risultato (titolo + testo):
- **modello** (`TEMPLATE`): frasi fisse riempite con i dati, sempre
  disponibile e senza costi;
- **IA** (`AI`): Claude scrive l'articolo dagli stessi dati. È pronto ma
  spento: si accende con `EVENT_REPORT_AI_ENABLED=true` e la chiave
  `ANTHROPIC_API_KEY` (la stessa di JAVBOT). Se l'IA non risponde, non si
  inventa niente: l'errore lo dice e resta il modello.

Chi lo ritocca a mano lo fa diventare `MANUAL`. In portoghese, come il PDF
dei relatórios e il calendário: è un testo per i soci del club.
Specifica: docs/club-portal.md, "Relatório final".
"""

import io
import json
import logging
import uuid
from datetime import date
from xml.sax.saxutils import escape

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.club import event_reports
from app.domains.club.calendar import KIND_PT, LEVEL_PT, MONTHS_PT
from app.domains.club.models import ClubEventReport
from app.domains.club.scope import ClubScope
from app.domains.club.service import ClubValidationError

logger = logging.getLogger(__name__)

MAX_ARTICLE_CHARS = 20000
#: Un articolo, non un romanzo: il modello si ferma molto prima.
AI_MAX_TOKENS = 2000

_COUNT_F = {1: "Uma", 2: "Duas", 3: "Três", 4: "Quatro", 5: "Cinco", 6: "Seis", 7: "Sete", 8: "Oito",
            9: "Nove", 10: "Dez"}
_MEDAL_WORD = {1: "ouro", 2: "prata", 3: "bronze"}
_COST_WORD = {"HOTEL": "alojamento", "TRAVEL": "viagem", "FUEL": "combustível", "FOOD": "alimentação",
              "ENTRY_FEES": "inscrições", "OTHER": "outras despesas"}


def ai_available() -> bool:
    settings = get_settings()
    return bool(settings.event_report_ai_enabled and settings.anthropic_api_key)


def _long_date(d: date) -> str:
    return f"{d.day} de {MONTHS_PT[d.month - 1].lower()} de {d.year}"


def _names(items: list[str]) -> str:
    """«A», «A e B», «A, B e C»."""
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " e " + items[-1]


def _euro(cents: int) -> str:
    return event_reports._euro(cents)


def _placed(r: dict) -> str:
    if r["placement"] == 0:
        return f"{r['athlete_name']} ({r['rank']}.º lugar)" if r.get("rank") else r["athlete_name"]
    return f"{r['athlete_name']} ({r['placement']}.º lugar)"


def compose_template(rep: dict, *, club_name: str) -> tuple[str, str]:
    """L'articolo scritto con frasi fisse: titolo e paragrafi separati da
    una riga vuota. Ogni frase esiste solo se c'è il dato che racconta."""
    results = rep["results"]
    medals = {p: [r["athlete_name"] for r in results if r["placement"] == p] for p in (1, 2, 3)}
    n_medals = sum(len(v) for v in medals.values())
    event = rep["competition_name"]

    if n_medals:
        count = _COUNT_F.get(n_medals, str(n_medals))
        title = f"{count} medalha{'s' if n_medals > 1 else ''} para o {club_name} em {event}"
    elif results:
        title = f"{club_name} em {event}"
    else:
        title = rep["title"] or event

    kind = KIND_PT.get(rep["competition_kind"], "")
    if rep["competition_kind"] == "COMPETITION" and rep["competition_level"] not in (None, "CLUB"):
        kind = f"{kind} {LEVEL_PT.get(rep['competition_level'], '').lower()}".strip()
    when = _long_date(rep["starts_on"])
    if rep["ends_on"] and rep["ends_on"] != rep["starts_on"]:
        when = f"{rep['starts_on'].day} a {_long_date(rep['ends_on'])}" if rep["ends_on"].month == rep["starts_on"].month \
            else f"{_long_date(rep['starts_on'])} a {_long_date(rep['ends_on'])}"
    where = f", em {rep['location']}" if rep.get("location") else ""
    who = f"com {len(results)} atleta{'s' if len(results) != 1 else ''}" if results else "com a sua equipa técnica"
    paragraphs = [
        f"{when[0].upper()}{when[1:]}{where}: o {club_name} esteve presente em «{event}»"
        + (f" ({kind.lower()})" if kind else "") + f", {who}."
    ]

    if n_medals:
        parts = [f"{_MEDAL_WORD[p]} para {_names(medals[p])}" for p in (1, 2, 3) if medals[p]]
        sentence = "; ".join(parts)
        paragraphs.append(f"Nos resultados, {sentence}.")
    others = [r for r in results if r["placement"] == 0 or (r["placement"] or 0) > 3]
    if others:
        paragraphs.append(f"{'Competiram também' if n_medals else 'Competiram'} {_names([_placed(r) for r in others])}.")
    pending = [r for r in results if r["placement"] is None]
    if pending and len(pending) == len(results):
        paragraphs.append("Os resultados ainda não foram registados.")

    if rep.get("description"):
        paragraphs.append(rep["description"].strip())
    if rep.get("narrative"):
        story = [p.strip() for p in rep["narrative"].split("\n\n") if p.strip()]
        if story:
            paragraphs.append(f"{rep['author_name']} conta como correu: «{story[0]}")
            paragraphs.extend(story[1:])
            paragraphs[-1] += "»"

    if rep["total_cents"]:
        lines = [f"{_COST_WORD.get(c['kind'], c['kind'])} {_euro(c['amount_cents'])}"
                 for c in rep["costs"] if c["amount_cents"]]
        paragraphs.append(f"A participação custou ao clube {_euro(rep['total_cents'])}"
                          + (f" ({_names(lines)})." if len(lines) > 1 else "."))

    if n_medals:
        paragraphs.append("Parabéns a todos os atletas e aos treinadores!")
    elif results:
        paragraphs.append("Obrigado a todos os atletas pelo empenho: a próxima prova já está à espera.")
    return title[:200], "\n\n".join(paragraphs)[:MAX_ARTICLE_CHARS]


_AI_SYSTEM = """És o redator do site de um clube de judo português. Escreves crónicas curtas sobre as provas \
em que os atletas do clube participam, no estilo de um jornal desportivo local: factual, caloroso, sem exageros.

Regras:
- Português de Portugal. Entre 120 e 250 palavras, 3 a 5 parágrafos curtos.
- Usa SÓ os factos dos dados fornecidos: não inventes nomes, resultados, adversários, golpes, citações ou números.
- Abre com onde, quando e quantos atletas; depois as medalhas e os resultados; depois o que o treinador contou; \
os custos numa frase só, se existirem; fecha com uma frase de parabéns ou de incentivo.
- Os atletas são muitas vezes menores: refere-os só pelo nome com que aparecem nos dados, sem idades nem outros dados pessoais.
- Formato da resposta: a primeira linha é o título (sem aspas, sem «Título:»), depois uma linha vazia, depois o texto. \
Nada de markdown."""


def _ai_payload(rep: dict, *, club_name: str) -> dict:
    return {
        "clube": club_name,
        "evento": rep["competition_name"],
        "tipo": KIND_PT.get(rep["competition_kind"], rep["competition_kind"]),
        "nivel": LEVEL_PT.get(rep["competition_level"], rep["competition_level"]),
        "data_inicio": rep["starts_on"].isoformat(),
        "data_fim": rep["ends_on"].isoformat() if rep.get("ends_on") else None,
        "local": rep.get("location"),
        "autor_do_relatorio": rep["author_name"],
        "titulo_do_relatorio": rep["title"],
        "descricao": rep.get("description"),
        "relato_do_treinador": rep.get("narrative"),
        "resultados": [
            {"atleta": r["athlete_name"], "categoria": r.get("category"),
             "resultado": event_reports._result_label(r), "notas": r.get("result_notes")}
            for r in rep["results"]
        ],
        "custos_total": _euro(rep["total_cents"]) if rep["total_cents"] else None,
        "custos": [{"voce": _COST_WORD.get(c["kind"], c["kind"]), "valor": _euro(c["amount_cents"]),
                    "nota": c.get("note")} for c in rep["costs"] if c["amount_cents"]],
        "numero_de_fotografias": len(rep["photos"]),
    }


async def compose_ai(rep: dict, *, club_name: str) -> tuple[str, str]:
    """L'articolo scritto da Claude con gli stessi dati del modello."""
    import anthropic

    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=90.0, max_retries=2)
    data = json.dumps(_ai_payload(rep, club_name=club_name), ensure_ascii=False, default=str, indent=1)
    try:
        response = await client.beta.messages.create(
            model=settings.javbot_model,
            max_tokens=AI_MAX_TOKENS,
            system=_AI_SYSTEM,
            messages=[{"role": "user", "content": f"Escreve a crónica desta prova.\n\nDados:\n{data}"}],
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.APIError as exc:
        logger.exception("event article: API error")
        raise ClubValidationError("L'IA non ha risposto: riprova tra poco, oppure usa il testo automatico.") from exc
    text = "".join(getattr(b, "text", "") for b in response.content if b.type == "text").strip()
    if response.stop_reason == "refusal" or not text:
        raise ClubValidationError("L'IA non ha scritto l'articolo: usa il testo automatico e correggilo a mano.")
    title, _, body = text.partition("\n")
    title = title.strip().strip("#*«»\"").strip()
    body = body.strip()
    if not body:
        title, body = rep["title"], text
    return title[:200], body[:MAX_ARTICLE_CHARS]


async def generate(
    db: AsyncSession, *, scope: ClubScope, report_id: uuid.UUID, actor_user_id: uuid.UUID, can_manage: bool,
    source: str, club_name: str,
) -> ClubEventReport:
    """Scrive (o riscrive) il relatório final dai dati attuali del relatório."""
    if source not in ("TEMPLATE", "AI"):
        raise ClubValidationError("Modo di scrittura non valido.")
    if source == "AI" and not ai_available():
        raise ClubValidationError("La scrittura con l'IA non è ancora attiva: usa il testo automatico.")
    report = await event_reports.get_report(db, scope=scope, report_id=report_id)
    event_reports._check_owner(report, user_id=actor_user_id, can_manage=can_manage)
    rep = await event_reports.report_dict(db, scope=scope, report=report, photo_urls=False)
    if source == "AI":
        title, text = await compose_ai(rep, club_name=club_name)
    else:
        title, text = compose_template(rep, club_name=club_name)
    report.article_title, report.article, report.article_source = title, text, source
    report.article_generated_at = report.updated_at = utcnow()
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.event_report_article_generated", entity_type="club_event_report", entity_id=str(report.id),
        new_value={"source": source},
    )
    await db.commit()
    await db.refresh(report)
    return report


def clean_article(data: dict, report: ClubEventReport) -> dict:
    """Il relatório final ritoccato a mano: diventa `MANUAL` solo se il
    testo cambia davvero (salvare il relatório non basta)."""
    out: dict = {}
    if "article_title" in data:
        out["article_title"] = (data["article_title"] or "").strip()[:200] or None
    if "article" in data:
        out["article"] = (data["article"] or "").strip()[:MAX_ARTICLE_CHARS] or None
    changed = any(getattr(report, k) != v for k, v in out.items())
    if changed:
        out["article_source"] = "MANUAL" if out.get("article", report.article) else None
        if not out.get("article", report.article):
            out["article_title"] = None
            out["article_generated_at"] = None
    return out if changed else {}


# --- Il PDF degli articoli ------------------------------------------------------------------------


def render_pdf(
    *, articles: list[dict], club_name: str, generated_on: date, photo_loader=None, logo: bytes | None = None,
) -> bytes:
    """Tutti i relatórios finali in un PDF solo, impaginati come le pagine
    di un giornale: la copertina con l'indice, poi un articolo per pagina
    (o più, se è lungo) con occhiello colorato, titolo grande, firma, foto
    d'apertura, testo giustificato, il riquadro delle medaglie e le altre
    foto in fondo. `articles` sono i dict di report_dict con `article_*`."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
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

    from app.domains.club.calendar import KIND_COLOR

    W, H = A4
    margin = 40
    ink, muted, line = colors.HexColor("#1F2328"), colors.HexColor("#6B7280"), colors.HexColor("#D1D5DB")
    brand = colors.HexColor("#C8311A")
    body_w = W - 2 * margin
    buf = io.BytesIO()

    def masthead(pdf, doc) -> None:
        pdf.saveState()
        pdf.setStrokeColor(ink)
        pdf.setLineWidth(1.2)
        pdf.line(margin, H - 30, W - margin, H - 30)
        pdf.setLineWidth(0.4)
        pdf.line(margin, H - 33, W - margin, H - 33)
        pdf.setFillColor(muted)
        pdf.setFont("Times-Italic", 8.5)
        pdf.drawString(margin, H - 26, f"Crónicas das provas · {club_name}")
        pdf.drawRightString(W - margin, 20, f"página {doc.page}")
        pdf.drawString(margin, 20, f"gerado a {event_reports._day(generated_on)}")
        pdf.restoreState()

    def cover(pdf, doc) -> None:
        pdf.saveState()
        pdf.setFillColor(ink)
        pdf.rect(0, H - 150, W, 150, stroke=0, fill=1)
        pdf.setFillColor(colors.HexColor("#F5C542"))
        pdf.rect(0, H - 156, W, 6, stroke=0, fill=1)
        pdf.setFillColor(colors.white)
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(margin, H - 46, "RELATÓRIOS FINAIS")
        pdf.setFont("Times-Bold", 38)
        pdf.drawString(margin, H - 92, "Crónicas das provas")
        pdf.setFont("Times-Italic", 13)
        pdf.drawString(margin, H - 120, club_name)
        if logo:
            try:
                pdf.drawImage(ImageReader(io.BytesIO(logo)), W - margin - 140, H - 125, 140, 80,
                              mask="auto", preserveAspectRatio=True, anchor="e")
            except Exception:  # noqa: BLE001, S110 -- un logo rovinato non ferma il PDF
                pass
        pdf.restoreState()
        pdf.saveState()
        pdf.setFillColor(muted)
        pdf.setFont("Times-Italic", 8.5)
        pdf.drawString(margin, 20, f"gerado a {event_reports._day(generated_on)}")
        pdf.restoreState()

    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=margin, rightMargin=margin, topMargin=48, bottomMargin=40,
                          title=f"Crónicas das provas — {club_name}", author=club_name)
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[Frame(margin, 40, body_w, H - 40 - 180, id="c")], onPage=cover),
        PageTemplate(id="article", frames=[Frame(margin, 40, body_w, H - 40 - 44, id="a")], onPage=masthead),
    ])

    def style(name, **kw) -> ParagraphStyle:
        base = {"fontName": "Times-Roman", "fontSize": 11, "leading": 15.5, "textColor": ink, "alignment": TA_LEFT}
        return ParagraphStyle(name, **{**base, **kw})

    s_kicker = style("kicker", fontName="Helvetica-Bold", fontSize=8.5, leading=11)
    s_head = style("head", fontName="Times-Bold", fontSize=26, leading=30, spaceAfter=6)
    s_by = style("by", fontName="Times-Italic", fontSize=9.5, leading=12, textColor=muted)
    s_lead = style("lead", fontName="Times-Bold", fontSize=12, leading=17, alignment=TA_JUSTIFY, spaceAfter=8)
    s_body = style("body", alignment=TA_JUSTIFY, spaceAfter=8, firstLineIndent=12)
    s_box = style("box", fontName="Helvetica", fontSize=8.8, leading=12)
    s_box_h = style("boxh", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=brand)
    s_index = style("idx", fontSize=11, leading=15)
    s_caption = style("cap", fontName="Times-Italic", fontSize=8.5, leading=10.5, textColor=muted, alignment=TA_CENTER)

    def photo(key: str, max_w: float, max_h: float):
        data = photo_loader(key) if photo_loader else None
        if not data:
            return None
        try:
            iw, ih = ImageReader(io.BytesIO(data)).getSize()
        except Exception:  # noqa: BLE001 -- una foto rovinata non ferma il PDF
            return None
        scale = min(max_w / iw, max_h / ih)
        return Image(io.BytesIO(data), width=iw * scale, height=ih * scale)

    story: list = [Spacer(1, 10)]
    if not articles:
        story += [Spacer(1, 80), Paragraph("Ainda não há relatórios finais",
                                           style("e", fontName="Times-Bold", fontSize=20, alignment=TA_CENTER)),
                  Spacer(1, 8), Paragraph("Gere o relatório final a partir do relatório de cada prova.",
                                          style("e2", alignment=TA_CENTER, textColor=muted))]
    else:
        medals = sum(1 for a in articles for r in a["results"] if r["placement"] in (1, 2, 3))
        story.append(Paragraph(
            f"{len(articles)} crónica{'s' if len(articles) != 1 else ''} · {medals} medalha{'s' if medals != 1 else ''}",
            style("sum", fontName="Helvetica-Bold", fontSize=10, textColor=muted, spaceAfter=10)))
        rows = []
        for a in articles:
            rows.append([Paragraph(event_reports._day(a["starts_on"]), style("d", fontName="Helvetica", fontSize=9,
                                                                                   textColor=muted)),
                         Paragraph(f"<b>{escape(a['article_title'] or a['title'])}</b><br/>"
                                   f'<font size="9" color="#6B7280">{escape(a["competition_name"])}</font>', s_index)])
        index = Table(rows, colWidths=[70, body_w - 70])
        index.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, line), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                   ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        story.append(index)

    for a in articles:
        story += [NextPageTemplate("article"), PageBreak()]
        color = KIND_COLOR.get(a["competition_kind"], "#4B5563")
        kicker = KIND_PT.get(a["competition_kind"], a["competition_kind"]).upper()
        if a["competition_kind"] == "COMPETITION" and a["competition_level"] != "CLUB":
            kicker += f" · {LEVEL_PT.get(a['competition_level'], a['competition_level']).upper()}"
        place = " · ".join(p for p in (_long_date(a["starts_on"]), a.get("location") or "") if p)
        story += [
            Paragraph(f'<font color="{color}">■ {escape(kicker)}</font>'
                      f'<font color="#6B7280">  ·  {escape(place.upper())}</font>', s_kicker),
            Spacer(1, 6),
            Paragraph(escape(a["article_title"] or a["title"]), s_head),
            Paragraph(f"Por {escape(a['author_name'])} · {escape(a['competition_name'])}", s_by),
            Spacer(1, 10),
        ]
        keys = [p["storage_key"] for p in a["photos"]]
        lead = photo(keys[0], body_w, 210) if keys else None
        if lead:
            story += [lead, Spacer(1, 10)]
        paragraphs = [p.strip() for p in (a["article"] or "").split("\n\n") if p.strip()]
        for i, p in enumerate(paragraphs):
            story.append(Paragraph(escape(p).replace("\n", "<br/>"), s_lead if i == 0 else s_body))

        # Il riquadro dei numeri: medaglie, atleti, spese.
        medal_rows = []
        for place_n, (hex_color, label, _bg) in event_reports.MEDAL.items():
            names = [r["athlete_name"] for r in a["results"] if r["placement"] == place_n]
            if names:
                medal_rows.append(Paragraph(f'<font color="{hex_color}">●</font> <b>{label}</b>: '
                                            f"{escape(', '.join(names))}", s_box))
        facts = [Paragraph("EM NÚMEROS", s_box_h),
                 Paragraph(f"<b>{len(a['results'])}</b> atleta{'s' if len(a['results']) != 1 else ''} do clube", s_box),
                 *medal_rows]
        if a["total_cents"]:
            facts.append(Paragraph(f"<b>Custos:</b> {_euro(a['total_cents'])}", s_box))
        box = Table([[f] for f in facts], colWidths=[body_w])
        box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F9FAFB")),
                                 ("LINEBEFORE", (0, 0), (0, -1), 3, brand),
                                 ("LEFTPADDING", (0, 0), (-1, -1), 12), ("TOPPADDING", (0, 0), (-1, -1), 2),
                                 ("BOTTOMPADDING", (0, 0), (-1, -1), 2), ("TOPPADDING", (0, 0), (-1, 0), 8),
                                 ("BOTTOMPADDING", (0, -1), (-1, -1), 8)]))
        story += [Spacer(1, 6), KeepTogether(box)]

        extra = [img for img in (photo(k, (body_w - 16) / 3 - 4, 95) for k in keys[1:7]) if img]
        if extra:
            grid = [extra[i:i + 3] + [""] * (3 - len(extra[i:i + 3])) for i in range(0, len(extra), 3)]
            gallery = Table(grid, colWidths=[body_w / 3] * 3)
            gallery.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                         ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
            story += [Spacer(1, 10), gallery, Paragraph(f"Fotografias: {escape(a['competition_name'])}", s_caption)]

    doc.build(story)
    return buf.getvalue()
