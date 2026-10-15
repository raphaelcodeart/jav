"""JAVBOT dell'area privata: la base di conoscenza e il modello.

Le promesse: il testo di un PDF si trova cercandolo senza accenti e in un
altro modo di scriverlo; un club vede la base comune e la sua, mai quella
di un altro club; il modello riceve solo gli strumenti che l'utente può
usare, mai quelli che scrivono; ordini, messaggi e presenze restano ai
percorsi guidati con conferma; se l'API non risponde, risponde il
pianificatore di sempre.
"""

import io
import uuid
from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from reportlab.pdfgen import canvas

from app.core.deps import CurrentUser
from app.domains.club.models import Club
from app.domains.club.scope import ClubScope
from app.domains.javbot import assistant, knowledge, service
from app.domains.javbot.models import JavbotConversation
from app.domains.javbot.texts import say
from tests.test_club_fees import _user


def _pdf(*pages: str) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    for page in pages:
        y = 800
        for line in page.split("\n"):
            pdf.drawString(40, y, line)
            y -= 16
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


async def _other_club(db, scope) -> ClubScope:
    club = Club(organization_id=scope.organization_id, name="Altro club", slug=f"altro-{uuid.uuid4().hex[:8]}", settings={})
    db.add(club)
    await db.commit()
    return ClubScope(organization_id=scope.organization_id, club_id=club.id)


async def _add(db, level, user, *pages, title=None):
    return await knowledge.add_document(
        db, level=level, file_bytes=_pdf(*pages), content_type="application/pdf", filename="regolamento.pdf",
        title=title, actor_user_id=user.id,
    )


async def _ctx(db, monkeypatch, user, scope, permissions, lang="it"):
    async def _codes(*args, **kwargs):
        return permissions

    monkeypatch.setattr(service, "get_permission_codes_for_user", _codes)
    return await service.build_context(
        db, current_user=CurrentUser(user_id=user.id, organization_id=scope.organization_id, roles=[]),
        requested_club=None, lang=lang,
    )


# --- Dal PDF ai pezzi -----------------------------------------------------------------------------


def test_chunks_keep_pages_and_overlap():
    long = " ".join(f"Frase numero {i} del regolamento." for i in range(200))
    chunks = knowledge.split_chunks(["Prima pagina breve, abbastanza lunga.", long])
    assert chunks[0] == (1, "Prima pagina breve, abbastanza lunga.")
    rest = [text for page, text in chunks[1:]]
    assert all(page == 2 for page, _ in chunks[1:]) and len(rest) > 2
    assert all(len(text) <= knowledge.CHUNK_CHARS for text in rest)
    # Nessun pezzo comincia a metà parola, e due pezzi vicini si sovrappongono.
    assert all(text.split()[0] in long.split() for text in rest)
    assert rest[0][-60:] in rest[1] or rest[1][:40] in rest[0]


def test_query_terms_drop_noise_and_accept_variants():
    assert knowledge._query_terms("Quando são as inscrições?") == ["inscrico"]
    assert knowledge._query_terms("i pagamenti del mese") == ["pagamen", "mese"]


async def test_pdf_text_is_found_without_accents(db, scope):
    admin = await _user(db, scope, "admin")
    level = knowledge.Level(scope.organization_id, scope.club_id)
    document = await _add(db, level, admin, "Regulamento interno\nA inscrição anual paga-se em setembro.",
                          "Horário de verão\nEm agosto o dojo está fechado.")
    assert document.status == "READY" and document.page_count == 2

    hits = await knowledge.search(db, organization_id=scope.organization_id, club_id=scope.club_id, query="inscricao anual")
    assert hits and "setembro" in hits[0]["text"] and hits[0]["page"] == 1
    hits = await knowledge.search(db, organization_id=scope.organization_id, club_id=scope.club_id, query="agosto fechado")
    assert hits[0]["page"] == 2 and hits[0]["document"] == "regolamento"


async def test_a_scan_without_text_is_kept_but_marked(db, scope):
    admin = await _user(db, scope, "admin")
    document = await _add(db, knowledge.Level(scope.organization_id, scope.club_id), admin, "")
    assert document.status == "EMPTY"
    assert not await knowledge.has_documents(db, organization_id=scope.organization_id, club_id=scope.club_id)


async def test_only_pdfs(db, scope):
    admin = await _user(db, scope, "admin")
    with pytest.raises(knowledge.KnowledgeError):
        await knowledge.add_document(
            db, level=knowledge.Level(scope.organization_id, scope.club_id), file_bytes=b"<html>",
            content_type="application/pdf", filename="x.pdf", title=None, actor_user_id=admin.id,
        )


# --- Chi vede che cosa ----------------------------------------------------------------------------


async def test_common_for_everyone_club_only_for_itself(db, scope):
    admin = await _user(db, scope, "admin")
    other = await _other_club(db, scope)
    common = knowledge.Level(scope.organization_id, None)
    await _add(db, common, admin, "Regolamento federale: il judogi deve essere bianco o blu.", title="Federazione")
    await _add(db, knowledge.Level(other.organization_id, other.club_id), admin,
               "Nel nostro club il judogi si compra in segreteria il martedì.", title="Segreto dell'altro club")

    mine = await knowledge.search(db, organization_id=scope.organization_id, club_id=scope.club_id, query="judogi")
    assert [h["document"] for h in mine] == ["Federazione"] and mine[0]["common"]
    theirs = await knowledge.search(db, organization_id=other.organization_id, club_id=other.club_id, query="judogi")
    assert {h["document"] for h in theirs} == {"Federazione", "Segreto dell'altro club"}
    assert await knowledge.catalog(db, organization_id=scope.organization_id, club_id=scope.club_id) == ["Federazione"]

    # La segreteria di un club non apre né cancella i documenti di un altro livello.
    foreign = (await knowledge.list_documents(db, level=knowledge.Level(other.organization_id, other.club_id)))[0]
    with pytest.raises(knowledge.KnowledgeNotFoundError):
        await knowledge.remove_document(db, level=knowledge.Level(scope.organization_id, scope.club_id), document_id=foreign.id)


async def test_instructions_one_per_level(db, scope):
    admin = await _user(db, scope, "admin")
    common = knowledge.Level(scope.organization_id, None)
    club = knowledge.Level(scope.organization_id, scope.club_id)
    await knowledge.set_instructions(db, level=common, text="Dai del tu.", actor_user_id=admin.id)
    await knowledge.set_instructions(db, level=club, text="Il sensei si chiama Rui.", actor_user_id=admin.id)
    await knowledge.set_instructions(db, level=club, text="  Il sensei si chiama Rui Costa.  ", actor_user_id=admin.id)
    assert await knowledge.get_instructions(db, level=common) == "Dai del tu."
    assert await knowledge.get_instructions(db, level=club) == "Il sensei si chiama Rui Costa."
    with pytest.raises(knowledge.KnowledgeError):
        await knowledge.set_instructions(db, level=club, text="x" * 9000, actor_user_id=admin.id)


# --- Il modello -----------------------------------------------------------------------------------


def _text(text):
    return SimpleNamespace(type="text", text=text)


def _call(name, **args):
    return SimpleNamespace(type="tool_use", id=f"toolu_{uuid.uuid4().hex[:8]}", name=name, input=args)


class FakeClaude:
    """Risponde con i messaggi preparati, uno per chiamata, e ricorda che
    cosa ha ricevuto."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _response(*content, stop_reason="end_turn"):
    return SimpleNamespace(content=list(content), stop_reason=stop_reason)


@pytest.fixture
def claude(monkeypatch):
    def install(*responses):
        fake = FakeClaude(*responses)
        monkeypatch.setattr(assistant, "_client", lambda: fake)
        monkeypatch.setattr(assistant, "enabled", lambda: True)

        # Il client Redis condiviso resta legato al ciclo degli eventi del
        # primo test che lo usa: qui il tetto giornaliero non si misura.
        async def _always(_ctx):
            return True

        monkeypatch.setattr(assistant, "_under_daily_limit", _always)
        return fake

    return install


async def test_the_model_reads_the_documents_and_answers(db, scope, monkeypatch, claude):
    admin = await _user(db, scope, "admin")
    parent = await _user(db, scope)
    await _add(db, knowledge.Level(scope.organization_id, None), admin,
               "Exame de graduação: é preciso ter 80% de presenças.", title="Regras das graduações")
    await knowledge.set_instructions(db, level=knowledge.Level(scope.organization_id, scope.club_id),
                                     text="Ricorda che il dojo è al primo piano.", actor_user_id=admin.id)
    fake = claude(
        _response(_call("search_knowledge", query="exame graduacao presencas"), stop_reason="tool_use"),
        _response(_text("Per l'esame serve l'80% delle presenze (Regras das graduações, pag. 1).")),
    )
    ctx = await _ctx(db, monkeypatch, parent, scope, {"club.family"})
    _asked, answered = await service.post_message(db, ctx=ctx, text="Cosa serve per l'esame di cintura?")
    assert "80%" in answered.text

    first, second = fake.requests
    names = {t["name"] for t in first["tools"]}
    assert "search_knowledge" in names and "family_dues" in names
    # Niente strumenti che scrivono, niente strumenti della segreteria per un genitore.
    assert not names & {"create_shop_order", "mark_attendance", "send_club_message", "staff_unpaid_month"}
    system = "\n".join(block["text"] for block in first["system"])
    assert "Regras das graduações" in system and "primo piano" in system and "italiano" in system
    # Il risultato della ricerca torna al modello come tool_result.
    result = second["messages"][-1]["content"][0]
    assert result["type"] == "tool_result" and "80%" in result["content"] and not result["is_error"]


async def test_guided_paths_stay_with_the_planner(db, scope, monkeypatch, claude):
    parent = await _user(db, scope)
    fake = claude()
    ctx = await _ctx(db, monkeypatch, parent, scope, {"club.family"})
    _asked, answered = await service.post_message(db, ctx=ctx, text="Vorrei comprare un judogi")
    assert fake.requests == []
    conversation = await db.get(JavbotConversation, answered.conversation_id)
    assert conversation.state.get("flow") == "judogi"
    # A metà percorso, anche una frase qualsiasi resta al pianificatore.
    await service.post_message(db, ctx=ctx, text="non so")
    assert fake.requests == []


async def test_api_down_the_planner_answers(db, scope, monkeypatch, claude):
    parent = await _user(db, scope)
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    claude(anthropic.APIConnectionError(request=request))
    ctx = await _ctx(db, monkeypatch, parent, scope, {"club.family"})
    _asked, answered = await service.post_message(db, ctx=ctx, text="Grazie mille!")
    assert answered.text == say("it", "thanks")


async def test_without_a_key_nothing_changes(db, scope, monkeypatch):
    monkeypatch.setattr(assistant, "_client", lambda: pytest.fail("il modello non va chiamato"))
    parent = await _user(db, scope)
    ctx = await _ctx(db, monkeypatch, parent, scope, {"club.family"})
    _asked, answered = await service.post_message(db, ctx=ctx, text="Grazie mille!")
    assert answered.text == say("it", "thanks")


# --- Senza modello: si cita dai documenti ---------------------------------------------------------


def test_excerpt_keeps_the_sentence_that_answers():
    text = ("O clube foi fundado em 1990. Os treinos são de segunda a sexta. "
            "Em agosto o dojo está fechado para férias. Em setembro reabre com as inscrições.")
    out = knowledge.excerpt(text, knowledge._query_terms("o dojo está aberto em agosto?"), limit=80)
    assert "Em agosto o dojo está fechado" in out and len(out) <= 90


async def test_without_a_model_the_planner_quotes_the_documents(db, scope, monkeypatch):
    admin = await _user(db, scope, "admin")
    parent = await _user(db, scope)
    other = await _other_club(db, scope)
    await _add(db, knowledge.Level(scope.organization_id, scope.club_id), admin,
               "Horário de verão\nEm agosto o dojo está fechado para férias.", title="Regulamento interno")
    await _add(db, knowledge.Level(other.organization_id, other.club_id), admin,
               "Em agosto o dojo do outro clube está aberto.", title="Do outro clube")

    ctx = await _ctx(db, monkeypatch, parent, scope, {"club.family"}, lang="pt")
    _asked, answered = await service.post_message(db, ctx=ctx, text="O dojo está aberto em agosto?")
    assert "fechado para férias" in answered.text and "📄 Regulamento interno, pág. 1" in answered.text
    assert "outro clube" not in answered.text

    # Una domanda che i documenti non toccano: il solito "non ho capito".
    _asked, answered = await service.post_message(db, ctx=ctx, text="Qual é a capital da Mongólia?")
    assert answered.text == say("pt", "fallback")


async def test_documents_beat_a_weak_keyword_but_not_the_family_data(db, scope, monkeypatch):
    admin = await _user(db, scope, "admin")
    parent = await _user(db, scope)
    await _add(db, knowledge.Level(scope.organization_id, scope.club_id), admin,
               "Regras do dojo\nNão é permitido trazer comida para o tatami durante o treino.\n"
               "A cintura deve estar sempre bem atada.", title="Regras do dojo")
    ctx = await _ctx(db, monkeypatch, parent, scope, {"club.family"}, lang="pt")

    # "treino" da solo farebbe "lezioni di oggi": la domanda intera è nel regolamento.
    _asked, answered = await service.post_message(db, ctx=ctx, text="Posso trazer comida para o treino?")
    assert "trazer comida" in answered.text and "Regras do dojo" in answered.text

    # "Quanto tenho de pagar?" è un'intenzione forte: rispondono i dati della famiglia.
    _asked, answered = await service.post_message(db, ctx=ctx, text="Quanto tenho de pagar?")
    assert "Regras do dojo" not in answered.text
