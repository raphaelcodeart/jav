"""JAVBOT che spende poco (javbot/actions.py, rag.py, llm.py, service._answer).

Le promesse: un'iscrizione e le presenze chieste in chat si capiscono senza
modello, si confermano e si eseguono nel database (con il pagamento, se c'è
una quota); i documenti rispondono con una chiamata breve e la stessa
domanda la seconda volta viene dalla cache; le schede del gestionale e il
regolamento di un evento entrano nella base; ogni risposta lascia la sua
riga nel contatore, e le risposte delle regole costano zero.
"""

import io
from datetime import date, time, timedelta

from sqlalchemy import func, select

from app.domains.club import competitions as competitions_service
from app.domains.club import courses as courses_service
from app.domains.club.models import ClubAttendance, ClubCompetitionEntry, ClubCourseAthlete, ClubCourseSlot, ClubFee
from app.domains.javbot import actions, knowledge, llm, rag, service
from app.domains.javbot.models import JavbotKnowledgeDocument, JavbotTask, JavbotUsage
from tests.test_club_fees import _athlete, _no_debts, _plans, _user
from tests.test_javbot import _ctx, _say


def _fake_llm(monkeypatch, text="**Sim.** As aulas são à segunda [1]."):
    calls = []

    async def chat(db, messages, **kwargs):
        calls.append(messages)
        return llm.LlmResult(text=text, input_tokens=120, output_tokens=30, model="fake-mini")

    monkeypatch.setattr(llm, "chat", chat)
    monkeypatch.setattr(llm, "enabled", lambda: True)
    return calls


def test_dates_as_people_write_them():
    today = date(2026, 10, 18)
    assert actions.parse_date("il 17 ottobre 2026", today) == date(2026, 10, 17)
    assert actions.parse_date("no dia 28 de outubro", today) == date(2026, 10, 28)
    assert actions.parse_date("ieri", today) == date(2026, 10, 17)
    assert actions.parse_date("ontem", today) == date(2026, 10, 17)
    assert actions.parse_date("17/10", today) == date(2026, 10, 17)
    assert actions.parse_date("niente", today) is None
    assert actions.wants_signup("Iscrivimi alla gara di Lisbona") and not actions.wants_signup("quando chiudono le iscrizioni?")
    assert actions.wants_staff_attendance("segnami presenze di marco ariel e nur")


async def test_register_for_a_competition_from_the_chat(db, scope, monkeypatch):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    marco = await _athlete(db, scope, parent, birth_date=date(2014, 3, 3), first_name="Marco", today=date.today())
    await _athlete(db, scope, parent, birth_date=date(2016, 3, 3), first_name="Sara", today=date.today())
    await _no_debts(db, marco)
    day = date.today() + timedelta(days=20)
    lisbon = await competitions_service.create_competition(db, scope=scope, actor_user_id=admin.id, data={
        "name": "Torneio de Lisboa", "starts_on": day, "ends_on": day, "location": "Lisboa",
        "registration_deadline": day - timedelta(days=5), "level": "REGIONAL", "fee_cents": 1500,
        "requires_agonistic_certificate": False,
    })
    await competitions_service.create_competition(db, scope=scope, actor_user_id=admin.id, data={
        "name": "Taça de Faro", "starts_on": day + timedelta(days=7), "ends_on": day + timedelta(days=7),
        "location": "Faro", "registration_deadline": day, "level": "REGIONAL", "fee_cents": 0,
        "requires_agonistic_certificate": False,
    })
    ctx = await _ctx(db, monkeypatch, parent, scope, {"club.family"})

    # "Che gare posso fare?": le regole, con le schede e «Iscrivi Marco».
    listed = await _say(db, ctx, "che gare ci sono?")
    assert {c["title"] for c in listed.cards} == {"Torneio de Lisboa", "Taça de Faro"}
    assert any(a["type"] == "say" for c in listed.cards for a in c["actions"])

    reply = await _say(db, ctx, f"iscrivi Marco alla gara di Lisbona del {day:%d/%m}")
    assert "Marco" in reply.text and "Torneio de Lisboa" in reply.text and "15,00" in reply.text
    task_id = next(a["task_id"] for a in reply.actions if a["type"] == "confirm_task")
    task = await db.get(JavbotTask, task_id)
    assert task.kind == "COMPETITION_ENTRY" and task.status == "PENDING"
    # Prima del sì non c'è niente.
    assert (await db.execute(select(ClubCompetitionEntry))).first() is None
    _asked, done = await service.decide_task(db, ctx=ctx, task_id=task.id, accept=True)
    assert any(a["type"] == "open_pay" for a in done.actions)
    entry = (await db.execute(select(ClubCompetitionEntry).where(ClubCompetitionEntry.athlete_id == marco.id))).scalar_one()
    assert entry.competition_id == lisbon.id and entry.status == "REGISTERED"
    fee = (await db.execute(select(ClubFee).where(ClubFee.athlete_id == marco.id, ClubFee.kind == "COMPETITION"))).scalar_one()
    assert fee.amount_cents == 1500 and fee.status == "DUE"
    routes = [r for r, in (await db.execute(select(JavbotUsage.route).order_by(JavbotUsage.created_at))).all()]
    assert routes == ["RULES", "ACTION"]
    assert (await db.execute(select(func.sum(JavbotUsage.input_tokens)))).scalar_one() == 0


async def test_coach_marks_attendance_by_name(db, scope, monkeypatch):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    coach = await _user(db, scope, "treinador")
    parent = await _user(db, scope)
    kids = [await _athlete(db, scope, parent, birth_date=date(2012, 1, 1), first_name=n, today=date.today())
            for n in ("Marco", "Ariel", "Nur", "Ana")]
    course = await courses_service.create_course(db, scope=scope, actor_user_id=admin.id, data={"name": "Grupo 2"})
    on = date.today() - timedelta(days=3)
    db.add(ClubCourseSlot(course_id=course.id, weekday=on.weekday(), starts_at=time(18), ends_at=time(19)))
    for k in kids:
        db.add(ClubCourseAthlete(course_id=course.id, athlete_id=k.id))
    await db.commit()
    ctx = await _ctx(db, monkeypatch, coach, scope, {"club.instruct"})

    reply = await _say(db, ctx, f"segnami presenze di marco ariel e nur il {on:%d/%m/%Y}")
    assert "Marco" in reply.text and "Ariel" in reply.text and "Nur" in reply.text and "Ana" not in reply.text
    task_id = next(a["task_id"] for a in reply.actions if a["type"] == "confirm_task")
    assert (await db.execute(select(ClubAttendance))).first() is None
    await service.decide_task(db, ctx=ctx, task_id=task_id, accept=True)
    marked = {a for a, in (await db.execute(select(ClubAttendance.athlete_id).where(
        ClubAttendance.date == on, ClubAttendance.present.is_(True)))).all()}
    assert marked == {k.id for k in kids[:3]}
    # Nel futuro no.
    future = await _say(db, ctx, f"segna presenze di marco il {date.today() + timedelta(days=5):%d/%m/%Y}")
    assert not future.actions


async def test_documents_answer_once_then_from_the_cache(db, scope, monkeypatch):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    await _athlete(db, scope, parent, birth_date=date(2014, 3, 3), first_name="Rui", today=date.today())
    course = await courses_service.create_course(db, scope=scope, actor_user_id=admin.id,
                                                 data={"name": "Grupo Iniciação", "min_age": 6, "max_age": 9})
    db.add(ClubCourseSlot(course_id=course.id, weekday=0, starts_at=time(17, 30), ends_at=time(18, 30)))
    await db.commit()
    assert await rag.build_data_sources(db, club_id=scope.club_id) >= 3
    sources = {d.source_ref for d in (await db.execute(select(JavbotKnowledgeDocument))).scalars()}
    assert f"data:{scope.club_id}:courses" in sources
    hits = await knowledge.search(db, organization_id=scope.organization_id, club_id=scope.club_id,
                                  query="horario turma iniciacao")
    assert hits and "17:30" in hits[0]["text"]

    calls = _fake_llm(monkeypatch)
    ctx = await _ctx(db, monkeypatch, parent, scope, {"club.family"})
    first = await _say(db, ctx, "A que horas é a turma de iniciação?")
    assert first.text.startswith("**Sim.**") and first.cards and first.cards[0]["type"] == "source"
    second = await _say(db, ctx, "a que horas é a turma de iniciação")
    assert second.text == first.text and len(calls) == 1
    routes = [r for r, in (await db.execute(select(JavbotUsage.route).order_by(JavbotUsage.created_at))).all()]
    assert routes == ["RAG", "CACHE"]
    summary = await llm.usage_summary(db, organization_id=scope.organization_id)
    assert summary["answers"] == 2 and summary["free_answers"] == 1 and summary["tokens"] == 150


async def test_event_regulation_is_downloadable_and_readable(db, scope):
    from reportlab.pdfgen import canvas

    admin = await _user(db, scope, "admin")
    day = date.today() + timedelta(days=10)
    comp = await competitions_service.create_competition(db, scope=scope, actor_user_id=admin.id, data={
        "name": "Open do Algarve", "starts_on": day, "ends_on": day, "location": "Portimão",
        "registration_deadline": day - timedelta(days=2), "level": "OPENS", "fee_cents": 1000,
        "requires_agonistic_certificate": False,
    })
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf)
    pdf.drawString(72, 720, "Pesagem oficial: sexta-feira das 18h00 as 20h00 no pavilhao municipal.")
    pdf.save()
    comp = await competitions_service.set_regulation(db, scope=scope, competition_id=comp.id, actor_user_id=admin.id,
                                                     file_bytes=buf.getvalue(), filename="regulamento.pdf")
    assert comp.regulation_storage_key and comp.regulation_filename == "regulamento.pdf"
    hits = await knowledge.search(db, organization_id=scope.organization_id, club_id=scope.club_id, query="pesagem oficial")
    assert hits and hits[0]["source"] == "EVENT" and hits[0]["source_ref"] == f"event:{comp.id}"
    card = rag.source_cards(hits)[0]
    assert card["competition_id"] == str(comp.id)
    await competitions_service.set_regulation(db, scope=scope, competition_id=comp.id, actor_user_id=admin.id,
                                              file_bytes=None)
    assert not await knowledge.search(db, organization_id=scope.organization_id, club_id=scope.club_id,
                                      query="pesagem oficial")
