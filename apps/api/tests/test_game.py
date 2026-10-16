"""JAV Games (app/game, docs/games.md).

Le promesse: il gioco vive nel suo schema e non tocca il gestionale; il
browser non riceve mai la risposta giusta prima di rispondere; rifare un
quiz non fabbrica XP; gli esami si fanno in ordine e sbloccano la cintura
della carriera, che non può andare oltre; l'XP della carriera ha un tetto
per salvataggio; la classifica somma quiz e carriera.
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
        assert q.belt in content.BELTS[1:]
    for quiz in content.QUIZZES.values():
        assert len(content.questions_for(quiz)) >= quiz.size, quiz.id


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
        await service.start(db, user_id=kid.id, quiz_id="exam-orange", lang="pt")
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
    assert career["state"] == state and career["exams_passed"] == ["YELLOW"]
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
