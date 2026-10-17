"""Il relatório final di una prova (club/event_articles.py), attraverso le
rotte vere.

Le promesse: l'articolo nasce dai dati del relatório (medaglie, racconto,
spese) senza inventare niente; ritoccato a mano diventa `MANUAL`; l'IA è
spenta finché non la si accende e allora risponde con un errore leggibile;
il PDF degli articoli contiene solo quelli che chi chiede può vedere.
"""

from datetime import date, timedelta

from app.core.config import get_settings
from app.domains.club import competitions as competitions_service
from app.domains.club import event_articles
from tests.test_club_event_reports import TODAY, _client, _png, _setup
from tests.test_club_fees import _user


async def test_article_from_template_manual_edit_ai_off_and_pdf(db, scope, monkeypatch):
    past = TODAY - timedelta(days=20)
    admin, _parent, _kid, comp, entry = await _setup(db, scope, starts_on=past, name="Taça de Lagos")
    await competitions_service.record_results(db, scope=scope, competition_id=comp.id, actor_user_id=admin.id,
                                              results=[(entry.id, 1)])
    coach = await _user(db, scope, "treinador")
    colleague = await _user(db, scope, "colega")
    monkeypatch.setattr(get_settings(), "event_report_ai_enabled", False)

    app, client = await _client(db, monkeypatch, user=coach, scope=scope, granted={"club.instruct"})
    try:
        async with client:
            assert (await client.get("/club/staff/event-reports/ai")).json() == {"available": False}
            report = (await client.post("/club/staff/event-reports", json={
                "competition_id": str(comp.id), "narrative": "Grande dia em Lagos.",
                "costs": [{"kind": "FUEL", "amount_cents": 4500}, {"kind": "FOOD", "amount_cents": 2000}],
            })).json()
            assert report["article"] is None and report["article_source"] is None
            await client.post(f"/club/staff/event-reports/{report['id']}/photos",
                              files={"file": ("f.png", _png(), "image/png")})

            r = await client.post(f"/club/staff/event-reports/{report['id']}/article", json={"source": "TEMPLATE"})
            assert r.status_code == 200, r.text
            art = r.json()
            assert art["article_source"] == "TEMPLATE" and art["article_generated_at"]
            assert art["article_title"].startswith("Uma medalha para o")
            assert "ouro para Tiago Lopes" in art["article"]
            assert "Grande dia em Lagos." in art["article"]
            assert "65,00 €" in art["article"]

            # L'IA spenta non scrive niente e lo dice.
            r = await client.post(f"/club/staff/event-reports/{report['id']}/article", json={"source": "AI"})
            assert r.status_code == 400 and "IA" in r.json()["detail"]

            # Salvare il relatório senza toccare l'articolo non lo rende manuale.
            r = await client.patch(f"/club/staff/event-reports/{report['id']}", json={"title": "Lagos, ouro"})
            assert r.json()["article_source"] == "TEMPLATE"
            r = await client.patch(f"/club/staff/event-reports/{report['id']}",
                                   json={"article": art["article"] + "\n\nObrigado aos pais."})
            assert r.json()["article_source"] == "MANUAL"

            pdf = await client.get("/club/staff/event-reports/articles/pdf")
            assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
            assert pdf.headers["x-report-count"] == "1"
            none = await client.get("/club/staff/event-reports/articles/pdf?q=sagres")
            assert none.headers["x-report-count"] == "0" and none.content.startswith(b"%PDF")
    finally:
        app.dependency_overrides.clear()

    # Un collega non lo genera e non lo trova nel suo PDF.
    app, client = await _client(db, monkeypatch, user=colleague, scope=scope, granted={"club.instruct"})
    try:
        async with client:
            r = await client.post(f"/club/staff/event-reports/{report['id']}/article", json={"source": "TEMPLATE"})
            assert r.status_code == 404
            assert (await client.get("/club/staff/event-reports/articles/pdf")).headers["x-report-count"] == "0"
    finally:
        app.dependency_overrides.clear()


async def test_ai_article_uses_the_model_answer(db, scope, monkeypatch):
    past = TODAY - timedelta(days=5)
    admin, _parent, _kid, comp, _entry = await _setup(db, scope, starts_on=past, name="Open de Faro")
    settings = get_settings()
    monkeypatch.setattr(settings, "event_report_ai_enabled", True)
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    seen = {}

    async def fake(rep, *, club_name):
        seen["data"] = event_articles._ai_payload(rep, club_name=club_name)
        return "Faro recebe o clube", "Texto escrito pela IA."

    monkeypatch.setattr(event_articles, "compose_ai", fake)
    app, client = await _client(db, monkeypatch, user=admin, scope=scope, granted={"club.instruct", "club.manage"})
    try:
        async with client:
            assert (await client.get("/club/staff/event-reports/ai")).json() == {"available": True}
            report = (await client.post("/club/staff/event-reports", json={"competition_id": str(comp.id)})).json()
            r = await client.post(f"/club/staff/event-reports/{report['id']}/article", json={"source": "AI"})
            assert r.status_code == 200, r.text
            assert r.json()["article_source"] == "AI" and r.json()["article"] == "Texto escrito pela IA."
            assert seen["data"]["evento"] == "Open de Faro"
            assert seen["data"]["resultados"][0]["atleta"] == "Tiago Lopes"
    finally:
        app.dependency_overrides.clear()


def test_template_without_results_and_empty_pdf():
    rep = {
        "competition_name": "Estágio de Sagres", "competition_kind": "STAGE", "competition_level": "CLUB",
        "starts_on": date(2026, 9, 12), "ends_on": date(2026, 9, 13), "location": "Sagres", "title": "Sagres",
        "author_name": "Ana", "description": None, "narrative": None, "results": [], "costs": [],
        "total_cents": 0, "photos": [],
    }
    title, text = event_articles.compose_template(rep, club_name="Clube X")
    assert title == "Sagres"
    assert text.startswith("12 a 13 de setembro de 2026, em Sagres: o Clube X esteve presente")
    pdf = event_articles.render_pdf(articles=[], club_name="Clube X", generated_on=date(2026, 10, 17))
    assert pdf.startswith(b"%PDF")
