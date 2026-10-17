"""La logica del gioco (docs/games.md). Tutto nello schema `game`.

Dal gestionale si legge una cosa sola, una volta, quando il giocatore entra
la prima volta (e ogni volta che riapre l'area, per tenere il nome
aggiornato): il nome da mostrare e il nome del club, come testo. Niente si
scrive nel gestionale.

Quiz: il server sceglie le domande e l'ordine delle risposte, il browser
riceve solo il testo; ogni risposta si corregge qui (`answer`), con il
tempo impiegato. Punti per risposta: 10 se giusta + fino a 5 di velocità.
L'XP di un quiz a tema è solo il miglioramento rispetto al miglior punteggio
di prima (rifarlo non «fabbrica» XP); un esame superato la prima volta vale
il suo premio.

Carriera: lo stato lo calcola il browser e qui si salva. I controlli: la
dimensione, l'XP che può crescere al massimo di CAREER_XP_PER_SAVE per
salvataggio, e la cintura del personaggio che non può superare l'ultimo
esame superato in Dojo Academy.
"""

import json
import math
import random
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.game import content
from app.game.models import GameBeltExam, GameCareer, GamePlayer, GameQuizAttempt

#: Quanto può crescere l'XP della carriera in un salvataggio (una settimana
#: di gioco ne dà molto meno: è solo un tetto contro i numeri inventati).
CAREER_XP_PER_SAVE = 1500
MAX_STATE_BYTES = 400_000
#: Un tentativo vale per al massimo un'ora.
ATTEMPT_TTL = timedelta(hours=1)


class GameError(Exception):
    pass


class GameNotFound(GameError):
    pass


def level_of(xp: int) -> int:
    """Il livello: 1 a 0 XP, poi sempre più lento (100, 400, 900... XP)."""
    return int(math.sqrt(max(0, xp) / 100)) + 1


def level_bounds(level: int) -> tuple[int, int]:
    return 100 * (level - 1) ** 2, 100 * level ** 2


# --- Il giocatore -------------------------------------------------------------------------------------------

async def _identity(db: AsyncSession, user_id: uuid.UUID) -> tuple[str, str | None]:
    """Nome e club dell'account, come testo: l'unica lettura dal gestionale."""
    from app.domains.club.models import Club, ClubAthlete
    from app.domains.club.people import _names
    from app.domains.users.models import User

    user = await db.get(User, user_id)
    if user is None:
        raise GameNotFound("Account non trovato.")
    athlete = (await db.execute(select(ClubAthlete).where(ClubAthlete.user_id == user_id))).scalars().first()
    if athlete is not None:
        name = f"{athlete.first_name} {athlete.last_name[:1]}."
    else:
        full = (await _names(db, {user_id})).get(user_id) or user.email
        # Senza nome nel profilo, _names dà l'email: in classifica mai l'email intera.
        full = full.split("@")[0].replace(".", " ").replace("_", " ") if "@" in full else full
        parts = full.split() or ["Judoca"]
        name = f"{parts[0]} {parts[-1][:1]}." if len(parts) > 1 else parts[0]
    club = await db.get(Club, user.club_id) if user.club_id else None
    return name[:80], (club.name[:120] if club else None)


async def get_player(db: AsyncSession, *, user_id: uuid.UUID) -> GamePlayer:
    player = (await db.execute(select(GamePlayer).where(GamePlayer.user_id == user_id))).scalar_one_or_none()
    name, club = await _identity(db, user_id)
    if player is None:
        player = GamePlayer(user_id=user_id, display_name=name, club_label=club, quiz_xp=0, career_xp=0)
        db.add(player)
        await db.commit()
        await db.refresh(player)
    elif (player.display_name, player.club_label) != (name, club):
        player.display_name, player.club_label = name, club
        await db.commit()
    return player


async def exams_passed(db: AsyncSession, *, player_id: uuid.UUID) -> list[str]:
    rows = (await db.execute(select(GameBeltExam.belt).where(GameBeltExam.player_id == player_id))).scalars().all()
    return sorted(rows, key=content.BELTS.index)


def top_belt(passed: list[str]) -> str:
    return max(passed, key=content.BELTS.index) if passed else "WHITE"


async def best_scores(db: AsyncSession, *, player_id: uuid.UUID) -> dict[str, dict]:
    rows = (await db.execute(
        select(GameQuizAttempt.quiz_id, func.max(GameQuizAttempt.score), func.max(GameQuizAttempt.max_score),
               func.count(), func.bool_or(GameQuizAttempt.passed))
        .where(GameQuizAttempt.player_id == player_id, GameQuizAttempt.finished_at.is_not(None))
        .group_by(GameQuizAttempt.quiz_id)
    )).all()
    return {q: {"best": best or 0, "max": mx or 0, "attempts": n, "passed": bool(ok)} for q, best, mx, n, ok in rows}


async def me(db: AsyncSession, *, user_id: uuid.UUID) -> dict:
    player = await get_player(db, user_id=user_id)
    passed = await exams_passed(db, player_id=player.id)
    xp = player.quiz_xp + player.career_xp
    level = level_of(xp)
    low, high = level_bounds(level)
    position = (await db.execute(
        select(func.count()).select_from(GamePlayer).where((GamePlayer.quiz_xp + GamePlayer.career_xp) > xp)
    )).scalar_one() + 1
    return {
        "id": player.id, "display_name": player.display_name, "club_label": player.club_label,
        "xp": xp, "quiz_xp": player.quiz_xp, "career_xp": player.career_xp,
        "level": level, "level_from": low, "level_to": high, "position": position,
        "exams_passed": passed, "belt": top_belt(passed),
    }


# --- I quiz --------------------------------------------------------------------------------------------------

def _quiz(quiz_id: str) -> content.Quiz:
    quiz = content.QUIZZES.get(quiz_id)
    if quiz is None:
        raise GameNotFound("Quiz non trovato.")
    return quiz


def _locked(quiz: content.Quiz, passed: list[str]) -> bool:
    """Un esame si fa in ordine: il giallo, poi l'arancione..."""
    if quiz.kind != "EXAM":
        return False
    need = content.BELTS[content.BELTS.index(quiz.belt) - 1]
    return need != "WHITE" and need not in passed


def _lang(lang: str | None) -> str:
    lang = {"es": "pt", "fr": "en", "de": "en"}.get(lang or "", lang)
    return lang if lang in content.LANGS else "pt"


async def list_quizzes(db: AsyncSession, *, user_id: uuid.UUID, lang: str | None) -> list[dict]:
    lang = _lang(lang)
    player = await get_player(db, user_id=user_id)
    passed = await exams_passed(db, player_id=player.id)
    best = await best_scores(db, player_id=player.id)
    return [
        {
            "id": q.id, "kind": q.kind, "icon": q.icon, "title": q.title[lang], "description": q.description[lang],
            "topic": q.topic, "belt": q.belt, "questions": q.size, "seconds": q.seconds, "pass_pct": q.pass_pct,
            "pass_xp": q.pass_xp, "locked": _locked(q, passed), "passed": q.belt in passed if q.belt else best.get(q.id, {}).get("passed", False),
            "best": best.get(q.id, {}).get("best", 0), "max": q.size * 15, "attempts": best.get(q.id, {}).get("attempts", 0),
        }
        for q in content.QUIZZES.values()
    ]


def _public_question(q: content.Question, order: list[int], lang: str) -> dict:
    return {"id": q.id, "topic": q.topic, "text": q.text[lang], "choices": [q.choice(i, lang) for i in order]}


async def start(db: AsyncSession, *, user_id: uuid.UUID, quiz_id: str, lang: str | None, rng: random.Random | None = None) -> dict:
    lang = _lang(lang)
    quiz = _quiz(quiz_id)
    player = await get_player(db, user_id=user_id)
    if _locked(quiz, await exams_passed(db, player_id=player.id)):
        raise GameError("Prima supera l'esame della cintura precedente.")
    rng = rng or random.SystemRandom()
    pool = content.questions_for(quiz)
    if quiz.kind == "EXAM":
        # Prima le domande proprio di questa cintura, poi le altre.
        own = [q for q in pool if q.belt == quiz.belt]
        rest = [q for q in pool if q.belt != quiz.belt]
        rng.shuffle(own)
        rng.shuffle(rest)
        # Almeno un terzo proprio della cintura; il resto da quelle prima, e
        # se non bastano ancora da quelle della cintura.
        k = max(3, quiz.size // 3)
        chosen = (own[:k] + rest + own[k:])[: quiz.size]
        rng.shuffle(chosen)
    else:
        chosen = rng.sample(pool, min(quiz.size, len(pool)))
    picked = []
    for q in chosen:
        order = list(range(len(q.choices)))
        rng.shuffle(order)
        picked.append({"id": q.id, "order": order})
    attempt = GameQuizAttempt(player_id=player.id, quiz_id=quiz.id, lang=lang, questions=picked, answers={},
                              max_score=len(picked) * 15)
    db.add(attempt)
    await db.commit()
    await db.refresh(attempt)
    return {
        "attempt_id": attempt.id, "quiz_id": quiz.id, "kind": quiz.kind, "title": quiz.title[lang], "belt": quiz.belt,
        "seconds": quiz.seconds, "pass_pct": quiz.pass_pct,
        "questions": [_public_question(content.BY_ID[p["id"]], p["order"], lang) for p in picked],
    }


async def _attempt(db: AsyncSession, *, user_id: uuid.UUID, attempt_id: uuid.UUID) -> tuple[GameQuizAttempt, GamePlayer]:
    player = await get_player(db, user_id=user_id)
    attempt = await db.get(GameQuizAttempt, attempt_id)
    if attempt is None or attempt.player_id != player.id:
        raise GameNotFound("Tentativo non trovato.")
    return attempt, player


async def answer(
    db: AsyncSession, *, user_id: uuid.UUID, attempt_id: uuid.UUID, question_id: str, choice: int | None, ms: int,
    now: datetime | None = None,
) -> dict:
    """`choice` è l'indice nell'ordine mostrato; None = tempo scaduto."""
    now = now or utcnow()
    attempt, _player = await _attempt(db, user_id=user_id, attempt_id=attempt_id)
    if attempt.finished_at is not None or now - attempt.started_at > ATTEMPT_TTL:
        raise GameError("Questo tentativo è chiuso: ricomincia il quiz.")
    item = next((p for p in attempt.questions if p["id"] == question_id), None)
    if item is None:
        raise GameNotFound("Domanda non trovata.")
    if question_id in (attempt.answers or {}):
        raise GameError("Hai già risposto a questa domanda.")
    quiz = _quiz(attempt.quiz_id)
    q = content.BY_ID[question_id]
    shown_correct = item["order"].index(0)
    correct = choice is not None and choice == shown_correct
    limit = quiz.seconds * 1000
    ms = max(0, min(int(ms), limit))
    points = 10 + round(5 * (1 - ms / limit)) if correct else 0
    answers = dict(attempt.answers or {})
    answers[question_id] = {"choice": choice, "correct": correct, "points": points, "ms": ms}
    attempt.answers = answers
    attempt.score = sum(a["points"] for a in answers.values())
    attempt.correct = sum(1 for a in answers.values() if a["correct"])
    await db.commit()
    streak = 0
    for p in attempt.questions:
        a = answers.get(p["id"])
        if a is None:
            break
        streak = streak + 1 if a["correct"] else 0
    return {"correct": correct, "correct_choice": shown_correct, "points": points, "score": attempt.score,
            "explanation": q.why[attempt.lang], "streak": streak}


async def finish(db: AsyncSession, *, user_id: uuid.UUID, attempt_id: uuid.UUID, now: datetime | None = None) -> dict:
    now = now or utcnow()
    attempt, player = await _attempt(db, user_id=user_id, attempt_id=attempt_id)
    quiz = _quiz(attempt.quiz_id)
    if attempt.finished_at is not None:
        raise GameError("Quiz già concluso.")
    previous_best = (await db.execute(
        select(func.max(GameQuizAttempt.score)).where(
            GameQuizAttempt.player_id == player.id, GameQuizAttempt.quiz_id == quiz.id,
            GameQuizAttempt.finished_at.is_not(None),
        )
    )).scalar_one() or 0
    total = len(attempt.questions)
    pct = round(100 * attempt.correct / total) if total else 0
    attempt.passed = pct >= quiz.pass_pct
    attempt.finished_at = now
    xp = max(0, attempt.score - previous_best)
    new_belt = None
    if quiz.kind == "EXAM" and attempt.passed:
        already = (await db.execute(select(GameBeltExam).where(
            GameBeltExam.player_id == player.id, GameBeltExam.belt == quiz.belt
        ))).scalar_one_or_none()
        if already is None:
            db.add(GameBeltExam(player_id=player.id, belt=quiz.belt, score_pct=pct, passed_at=now))
            xp += quiz.pass_xp
            new_belt = quiz.belt
    before = level_of(player.quiz_xp + player.career_xp)
    attempt.xp_earned = xp
    player.quiz_xp += xp
    await db.commit()
    after = level_of(player.quiz_xp + player.career_xp)
    return {
        "score": attempt.score, "max_score": attempt.max_score, "correct": attempt.correct, "total": total, "pct": pct,
        "passed": attempt.passed, "pass_pct": quiz.pass_pct, "xp_earned": xp, "new_belt": new_belt,
        "level": after, "level_up": after > before, "previous_best": previous_best,
    }


# --- La carriera ---------------------------------------------------------------------------------------------

async def get_career(db: AsyncSession, *, user_id: uuid.UUID) -> dict:
    player = await get_player(db, user_id=user_id)
    career = await db.get(GameCareer, player.id)
    return {
        "state": career.state if career else None, "week": career.week if career else 0,
        "belt": career.belt if career else "WHITE", "career_xp": player.career_xp,
        "updated_at": career.updated_at if career else None,
        "exams_passed": await exams_passed(db, player_id=player.id),
    }


async def save_career(db: AsyncSession, *, user_id: uuid.UUID, state: dict, career_xp: int, week: int, belt: str) -> dict:
    player = await get_player(db, user_id=user_id)
    if len(json.dumps(state, separators=(",", ":"))) > MAX_STATE_BYTES:
        raise GameError("La partita è troppo grande per essere salvata.")
    if belt not in content.BELTS:
        raise GameError("Cintura non valida.")
    passed = await exams_passed(db, player_id=player.id)
    if content.BELTS.index(belt) > content.BELTS.index(top_belt(passed)):
        raise GameError("Per questa cintura devi prima superare l'esame in Dojo Academy.")
    if career_xp < 0 or career_xp - player.career_xp > CAREER_XP_PER_SAVE:
        raise GameError("XP non valida.")
    career = await db.get(GameCareer, player.id)
    if career is None:
        career = GameCareer(player_id=player.id, state=state, week=week, belt=belt, saves=1)
        db.add(career)
    else:
        career.state, career.week, career.belt = state, week, belt
        career.saves += 1
    # La XP della carriera non scende mai, nemmeno con una partita nuova.
    player.career_xp = max(player.career_xp, career_xp)
    await db.commit()
    return {"saved": True, "career_xp": player.career_xp, "level": level_of(player.quiz_xp + player.career_xp)}


async def reset_career(db: AsyncSession, *, user_id: uuid.UUID) -> None:
    player = await get_player(db, user_id=user_id)
    career = await db.get(GameCareer, player.id)
    if career is not None:
        await db.delete(career)
        await db.commit()


# --- La classifica -------------------------------------------------------------------------------------------

async def leaderboard(db: AsyncSession, *, user_id: uuid.UUID, scope: str = "all", limit: int = 50) -> dict:
    player = await get_player(db, user_id=user_id)
    xp = GamePlayer.quiz_xp + GamePlayer.career_xp
    stmt = select(GamePlayer).where(xp > 0)
    if scope == "club" and player.club_label:
        stmt = stmt.where(GamePlayer.club_label == player.club_label)
    players = list((await db.execute(stmt.order_by(xp.desc(), GamePlayer.created_at).limit(limit))).scalars())
    belts = {}
    if players:
        for pid, belt in (await db.execute(select(GameBeltExam.player_id, GameBeltExam.belt)
                                           .where(GameBeltExam.player_id.in_([p.id for p in players])))).all():
            belts.setdefault(pid, []).append(belt)
    careers = dict((await db.execute(select(GameCareer.player_id, GameCareer.belt)
                                     .where(GameCareer.player_id.in_([p.id for p in players] or [uuid.uuid4()])))).all())
    rows, position, previous = [], 0, None
    for i, p in enumerate(players, start=1):
        total = p.quiz_xp + p.career_xp
        if total != previous:
            position, previous = i, total
        rows.append({"position": position, "display_name": p.display_name, "club_label": p.club_label, "xp": total,
                     "level": level_of(total), "belt": top_belt(belts.get(p.id, [])),
                     "career_belt": careers.get(p.id), "is_me": p.id == player.id})
    # I club: la somma dell'XP dei loro giocatori.
    clubs = (await db.execute(
        select(GamePlayer.club_label, func.sum(xp), func.count())
        .where(GamePlayer.club_label.is_not(None), xp > 0).group_by(GamePlayer.club_label).order_by(func.sum(xp).desc())
    )).all()
    return {"scope": scope, "rows": rows,
            "clubs": [{"club_label": c, "xp": int(s), "players": n} for c, s, n in clubs]}
