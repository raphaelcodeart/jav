"""JAV Games (app/game, docs/games.md).

Le promesse: il gioco vive nel suo schema e non tocca il gestionale; il
browser non riceve mai la risposta giusta prima di rispondere; rifare un
quiz non fabbrica XP; gli esami si fanno in ordine (mezze cinture fino alla
marrone, poi i dan fino al 10°, ognuno più lungo del precedente) e
sbloccano la cintura della carriera, che non può andare oltre; i corsi
chiedono un grado e danno le qualifiche (arbitro, treinador di 1° livello);
l'XP della carriera ha un tetto per salvataggio; la classifica somma quiz e
carriera.
"""

import random

import pytest

from app.game import content, service
from app.game.models import GameBase
from tests.test_club_fees import _user


def test_the_game_is_a_separate_schema():
    assert {t.schema for t in GameBase.metadata.tables.values()} == {"game"}
    for table in GameBase.metadata.tables.values():
        for fk in table.foreign_keys:
            assert fk.column.table.schema == "game", fk
    from app.core.db import Base

    assert not set(Base.metadata.tables) & set(GameBase.metadata.tables)


def test_every_question_is_complete():
    for q in content.QUESTIONS:
        assert len(q.choices) == 4 and len(set(q.choice(i, "pt") for i in range(4))) == 4, q.id
        for lang in content.LANGS:
            assert q.text[lang] and q.why[lang] and all(q.choice(i, lang) for i in range(4))
        assert q.belt in content.LEVELS, q.id
    assert len(content.BY_ID) == len(content.QUESTIONS)
    for quiz in content.QUIZZES.values():
        assert len(content.questions_for(quiz)) >= quiz.size, quiz.id


def test_the_ladder_grows_exam_by_exam():
    sizes = [content.EXAM_SIZES[g] for g in content.GRADES[1:]]
    assert sizes[:10] == [5, 10, 15, 20, 25, 30, 35, 40, 45, 50]  # fino alla marrone, +5
    assert sizes[10:] == [60, 75, 95, 120, 150, 185, 225, 270, 320, 375]  # 1° dan +10, 2° +15 …
    assert content.QUIZZES["exam-yellow"].size == 10 and content.QUIZZES["exam-dan10"].size == 375
    seconds = [content.QUIZZES[f"exam-{g.lower()}"].seconds for g in content.GRADES[1:]]
    pass_pct = [content.QUIZZES[f"exam-{g.lower()}"].pass_pct for g in content.GRADES[1:]]
    assert seconds == sorted(seconds, reverse=True) and pass_pct == sorted(pass_pct)
    assert content.career_belt("YELLOW_ORANGE") == "YELLOW" and content.career_belt("DAN7") == "BLACK"
    assert content.grade_level("BLUE_BROWN") == "BROWN"
    for groups in content.EXAM_FEATURED.values():
        assert all(i in content.BY_ID for group in groups for i in group)
    # Il 10° dan ha tempo per finire.
    assert service._ttl(content.QUIZZES["exam-dan10"]).total_seconds() >= 375 * 22


async def _play(db, user, quiz_id, *, right: int):
    started = await service.start(db, user_id=user.id, quiz_id=quiz_id, lang="it", rng=random.Random(1))
    assert all("correct" not in q for q in started["questions"])
    from app.game.models import GameQuizAttempt

    attempt = await db.get(GameQuizAttempt, started["attempt_id"])
    for i, item in enumerate(attempt.questions):
        good = item["order"].index(0)
        choice = good if i < right else (good + 1) % 4
        res = await service.answer(db, user_id=user.id, attempt_id=attempt.id, question_id=item["id"], choice=choice, ms=1000)
        assert res["correct"] == (i < right) and res["correct_choice"] == good and res["explanation"]
    return await service.finish(db, user_id=user.id, attempt_id=attempt.id)


async def test_quizzes_exams_career_and_leaderboard(db, scope):
    kid = await _user(db, scope, "kid")
    other = await _user(db, scope, "altro")

    me = await service.me(db, user_id=kid.id)
    assert (me["xp"], me["belt"], me["level"]) == (0, "WHITE", 1)

    first = await _play(db, kid, "topic-history", right=5)
    assert first["xp_earned"] == first["score"] > 0
    again = await _play(db, kid, "topic-history", right=5)
    assert again["xp_earned"] == 0  # lo stesso punteggio non dà XP nuovo
    better = await _play(db, kid, "topic-history", right=8)
    assert better["xp_earned"] == better["score"] - first["score"]

    with pytest.raises(service.GameError):
        await service.start(db, user_id=kid.id, quiz_id="exam-yellow", lang="pt")
    first_exam = await _play(db, kid, "exam-white_yellow", right=5)
    assert first_exam["new_belt"] == "WHITE_YELLOW"
    assert (await service.me(db, user_id=kid.id))["belt"] == "WHITE"  # la mezza cintura vale la bianca nella carriera
    failed = await _play(db, kid, "exam-yellow", right=5)
    assert failed["passed"] is False and failed["new_belt"] is None
    yellow = await _play(db, kid, "exam-yellow", right=10)
    assert yellow["passed"] and yellow["new_belt"] == "YELLOW" and yellow["xp_earned"] >= content.QUIZZES["exam-yellow"].pass_xp

    state = {"version": 1, "person": {"belt": "YELLOW"}}
    with pytest.raises(service.GameError):
        await service.save_career(db, user_id=kid.id, state=state, career_xp=10, week=3, belt="ORANGE")
    with pytest.raises(service.GameError):
        await service.save_career(db, user_id=kid.id, state=state, career_xp=service.CAREER_XP_PER_SAVE + 1, week=3, belt="YELLOW")
    saved = await service.save_career(db, user_id=kid.id, state=state, career_xp=300, week=3, belt="YELLOW")
    assert saved["career_xp"] == 300
    career = await service.get_career(db, user_id=kid.id)
    assert career["state"] == state and career["exams_passed"] == ["WHITE_YELLOW", "YELLOW"]
    await service.reset_career(db, user_id=kid.id)
    assert (await service.get_career(db, user_id=kid.id))["state"] is None
    assert (await service.me(db, user_id=kid.id))["career_xp"] == 300  # l'XP guadagnata resta

    await _play(db, other, "topic-rules", right=2)
    board = await service.leaderboard(db, user_id=kid.id)
    assert [r["is_me"] for r in board["rows"]][0] is True
    assert board["rows"][0]["belt"] == "YELLOW" and board["clubs"][0]["players"] == 2


def test_the_calendar_pdf_is_a_real_pdf_divided_by_month():
    from datetime import date

    from app.domains.club import calendar

    def event(day, month, **kw):
        base = {"id": f"{day}-{month}", "name": f"Prova {day}/{month}", "kind": "COMPETITION", "level": "REGIONAL",
                "status": "OPEN", "starts_on": date(2026, month, day), "ends_on": date(2026, month, day),
                "location": "Lagos", "organizer": "AJA", "age_groups": ["cadetes"], "description": None,
                "image_url": None, "registration_deadline": date(2026, month, max(1, day - 3)), "fee_cents": 1500,
                "club_name": "Judo Clube de Lagos", "network": False, "circular_url": None}
        return {**base, **kw}

    pdf = calendar.render_pdf(
        events=[event(10, 10), event(24, 10, kind="STAGE"), event(7, 11, network=True, status="DONE")],
        date_from=date(2026, 10, 1), date_to=date(2026, 11, 30), club_name="Judo Clube de Lagos", generated_on=date(2026, 10, 16),
    )
    assert pdf.startswith(b"%PDF") and len(pdf) > 2000
    assert calendar.render_pdf(events=[], date_from=date(2026, 1, 1), date_to=date(2026, 1, 31),
                               club_name="X", generated_on=date(2026, 1, 1)).startswith(b"%PDF")


async def test_courses_need_a_grade_and_give_qualifications(db, scope):
    from app.game.models import GameBeltExam

    judoka = await _user(db, scope, "verde")
    player = await service.get_player(db, user_id=judoka.id)
    cards = {c["id"]: c for c in await service.list_quizzes(db, user_id=judoka.id, lang="pt")}
    assert cards["course-ref-basic"]["lock_reason"] == "GRADE:GREEN"
    # Un verde di prima delle mezze cinture: ha il verde, non le mezze sotto.
    db.add(GameBeltExam(player_id=player.id, belt="GREEN", score_pct=90, passed_at=service.utcnow()))
    await db.commit()
    cards = {c["id"]: c for c in await service.list_quizzes(db, user_id=judoka.id, lang="pt")}
    assert not cards["exam-green_blue"]["locked"] and not cards["course-ref-basic"]["locked"]
    assert cards["course-referee"]["lock_reason"] == "GRADE:BLUE" and cards["coach1-ethics"]["lock_reason"] == "GRADE:BLACK"
    done = await _play(db, judoka, "course-ref-basic", right=30)
    assert done["passed"] and done["new_qualification"] == "REF_COURSE"
    assert done["xp_earned"] >= content.QUIZZES["course-ref-basic"].pass_xp
    again = await _play(db, judoka, "course-ref-basic", right=30)
    assert again["new_qualification"] is None and again["xp_earned"] == 0
    assert (await service.me(db, user_id=judoka.id))["qualifications"] == ["REF_COURSE"]

    db.add(GameBeltExam(player_id=player.id, belt="BLACK", score_pct=90, passed_at=service.utcnow()))
    await db.commit()
    for i, module in enumerate(content.COACH1_MODULES):
        res = await _play(db, judoka, module, right=30)
        last = i == len(content.COACH1_MODULES) - 1
        assert res["new_qualification"] == ("COACH1" if last else None), module
    me = await service.me(db, user_id=judoka.id)
    assert me["grade"] == "BLACK" and "COACH1" in me["qualifications"]


async def test_brown_and_first_dan_exams_always_ask_about_the_algarve(db, scope):
    from app.game.models import GameBeltExam

    judoka = await _user(db, scope, "algarvio")
    player = await service.get_player(db, user_id=judoka.id)
    db.add(GameBeltExam(player_id=player.id, belt="BROWN", score_pct=90, passed_at=service.utcnow()))
    await db.commit()
    for seed in range(3):
        for quiz_id, belt in (("exam-brown", "BROWN"), ("exam-black", "BLACK")):
            started = await service.start(db, user_id=judoka.id, quiz_id=quiz_id, lang="pt", rng=random.Random(seed))
            ids = {q["id"] for q in started["questions"]}
            for group in content.EXAM_FEATURED[belt]:
                assert ids & set(group), (quiz_id, group)


async def test_every_exam_keeps_its_results(db, scope):
    judoka = await _user(db, scope, "storico")
    await _play(db, judoka, "exam-white_yellow", right=2)
    await _play(db, judoka, "exam-white_yellow", right=5)
    card = next(c for c in await service.list_quizzes(db, user_id=judoka.id, lang="pt") if c["id"] == "exam-white_yellow")
    assert [h["pct"] for h in card["history"]] == [40, 100] and [h["passed"] for h in card["history"]] == [False, True]
    assert card["best_pct"] == 100 and card["passed_pct"] == 100 and card["passed_on"]
