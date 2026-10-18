"""Le API di JAV Games (`/game/...`, service.py). Basta essere entrati:
famiglie, atleti con il loro accesso, staff. Ognuno gioca per sé."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.rate_limit import rate_limit
from app.game import fights, service

router = APIRouter(prefix="/game", tags=["game"])


def _raise(exc: service.GameError) -> None:
    code = status.HTTP_404_NOT_FOUND if isinstance(exc, service.GameNotFound) else status.HTTP_400_BAD_REQUEST
    raise HTTPException(code, str(exc)) from exc


class DiplomaRead(BaseModel):
    code: str
    kind: str
    pct: int
    on: str


class MeRead(BaseModel):
    id: uuid.UUID
    display_name: str
    club_label: str | None
    xp: int
    quiz_xp: int
    career_xp: int
    level: int
    level_from: int
    level_to: int
    position: int
    exams_passed: list[str]
    belt: str
    grade: str
    qualifications: list[str]
    diplomas: list[DiplomaRead]


class AttemptRow(BaseModel):
    pct: int
    score: int
    passed: bool
    on: str


class QuizRead(BaseModel):
    id: str
    kind: str
    icon: str
    title: str
    description: str
    topic: str | None
    belt: str | None
    questions: int
    seconds: int
    pass_pct: int
    pass_xp: int
    locked: bool
    passed: bool
    best: int
    max: int
    attempts: int
    lock_reason: str | None
    group: str | None
    qualification: str | None
    min_grade: str | None
    jp: str | None
    focus: str | None
    history: list[AttemptRow]
    best_pct: int
    passed_on: str | None
    passed_pct: int | None


class QuestionRead(BaseModel):
    id: str
    topic: str
    text: str
    choices: list[str]


class StartRead(BaseModel):
    attempt_id: uuid.UUID
    quiz_id: str
    kind: str
    title: str
    belt: str | None
    seconds: int
    pass_pct: int
    questions: list[QuestionRead]


class AnswerWrite(BaseModel):
    question_id: str = Field(max_length=10)
    #: L'indice nell'ordine mostrato; null = tempo scaduto.
    choice: int | None = Field(default=None, ge=0, le=9)
    ms: int = Field(ge=0, le=600_000)


class AnswerRead(BaseModel):
    correct: bool
    correct_choice: int
    points: int
    score: int
    explanation: str
    streak: int


class FinishRead(BaseModel):
    score: int
    max_score: int
    correct: int
    total: int
    pct: int
    passed: bool
    pass_pct: int
    xp_earned: int
    new_belt: str | None
    new_qualification: str | None
    level: int
    level_up: bool
    previous_best: int


class CareerRead(BaseModel):
    state: dict | None
    week: int
    belt: str
    career_xp: int
    updated_at: datetime | None
    exams_passed: list[str]


class CareerWrite(BaseModel):
    state: dict
    career_xp: int = Field(ge=0)
    week: int = Field(ge=0, le=100_000)
    belt: str = Field(max_length=16)


class CareerSavedRead(BaseModel):
    saved: bool
    career_xp: int
    level: int


class LeaderRow(BaseModel):
    position: int
    display_name: str
    club_label: str | None
    xp: int
    level: int
    belt: str
    grade: str
    career_belt: str | None
    is_me: bool


class ClubRow(BaseModel):
    club_label: str
    xp: int
    players: int


class LeaderboardRead(BaseModel):
    scope: str
    rows: list[LeaderRow]
    clubs: list[ClubRow]


@router.get("/me", response_model=MeRead)
async def get_me(user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> MeRead:
    try:
        return MeRead(**await service.me(db, user_id=user.user_id))
    except service.GameError as exc:
        _raise(exc)


@router.get("/quizzes", response_model=list[QuizRead])
async def get_quizzes(
    lang: str = Query(default="pt", max_length=2),
    user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> list[QuizRead]:
    return [QuizRead(**q) for q in await service.list_quizzes(db, user_id=user.user_id, lang=lang)]


@router.post("/quizzes/{quiz_id}/start", response_model=StartRead,
             dependencies=[Depends(rate_limit("game-start", max_requests=60, window_seconds=600))])
async def start_quiz(
    quiz_id: str, lang: str = Query(default="pt", max_length=2),
    user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> StartRead:
    try:
        return StartRead(**await service.start(db, user_id=user.user_id, quiz_id=quiz_id, lang=lang))
    except service.GameError as exc:
        _raise(exc)


@router.post("/attempts/{attempt_id}/answer", response_model=AnswerRead)
async def answer_question(
    attempt_id: uuid.UUID, payload: AnswerWrite,
    user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> AnswerRead:
    try:
        return AnswerRead(**await service.answer(db, user_id=user.user_id, attempt_id=attempt_id,
                                                 question_id=payload.question_id, choice=payload.choice, ms=payload.ms))
    except service.GameError as exc:
        _raise(exc)


@router.post("/attempts/{attempt_id}/finish", response_model=FinishRead)
async def finish_quiz(
    attempt_id: uuid.UUID, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> FinishRead:
    try:
        return FinishRead(**await service.finish(db, user_id=user.user_id, attempt_id=attempt_id))
    except service.GameError as exc:
        _raise(exc)


@router.get("/career", response_model=CareerRead)
async def get_career(user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> CareerRead:
    return CareerRead(**await service.get_career(db, user_id=user.user_id))


@router.put("/career", response_model=CareerSavedRead,
            dependencies=[Depends(rate_limit("game-save", max_requests=120, window_seconds=600))])
async def save_career(
    payload: CareerWrite, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> CareerSavedRead:
    try:
        return CareerSavedRead(**await service.save_career(
            db, user_id=user.user_id, state=payload.state, career_xp=payload.career_xp, week=payload.week, belt=payload.belt,
        ))
    except service.GameError as exc:
        _raise(exc)


@router.delete("/career", status_code=status.HTTP_204_NO_CONTENT)
async def reset_career(user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
    await service.reset_career(db, user_id=user.user_id)


@router.get("/leaderboard", response_model=LeaderboardRead)
async def get_leaderboard(
    scope: str = Query(default="all", pattern="^(all|club)$"),
    user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> LeaderboardRead:
    return LeaderboardRead(**await service.leaderboard(db, user_id=user.user_id, scope=scope))


# --- Combattimenti (fights.py): gare della carriera passo a passo e randori del club ---------------------------

class FightAct(BaseModel):
    seq: int = Field(ge=1, le=1000)
    #: L'id di una delle opzioni mostrate; null = tempo scaduto.
    option: str | None = Field(default=None, max_length=20)


class CareerFightWrite(BaseModel):
    comp_id: str = Field(max_length=40)
    round: int = Field(ge=1, le=10)


class ChallengeWrite(BaseModel):
    opponent_id: uuid.UUID
    mode: str = Field(pattern="^(SIM|STEP)$")


_fight_limit = Depends(rate_limit("game-fight", max_requests=600, window_seconds=600))


@router.get("/fights/{fight_id}")
async def get_fight(fight_id: uuid.UUID, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    try:
        return await fights.get_fight(db, user_id=user.user_id, fight_id=fight_id)
    except service.GameError as exc:
        _raise(exc)


@router.post("/fights/{fight_id}/act", dependencies=[_fight_limit])
async def fight_act(fight_id: uuid.UUID, payload: FightAct, user: CurrentUser = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)) -> dict:
    try:
        return await fights.act(db, user_id=user.user_id, fight_id=fight_id, seq=payload.seq, option=payload.option)
    except service.GameError as exc:
        _raise(exc)


@router.post("/fights/{fight_id}/forfeit")
async def fight_forfeit(fight_id: uuid.UUID, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    try:
        return await fights.forfeit(db, user_id=user.user_id, fight_id=fight_id)
    except service.GameError as exc:
        _raise(exc)


@router.get("/career/fights/{comp_id}")
async def career_fights(comp_id: str, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    return await fights.career_rounds(db, user_id=user.user_id, comp_id=comp_id[:40])


@router.post("/career/fights", dependencies=[_fight_limit])
async def start_career_fight(
    payload: CareerFightWrite, lang: str = Query(default="pt", max_length=2),
    user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        return await fights.start_career_fight(db, user_id=user.user_id, comp_id=payload.comp_id, round_no=payload.round, lang=lang)
    except service.GameError as exc:
        _raise(exc)


@router.get("/randori")
async def get_randori(user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    return await fights.randori_overview(db, user_id=user.user_id)


@router.post("/randori/challenge", dependencies=[_fight_limit])
async def randori_challenge(
    payload: ChallengeWrite, lang: str = Query(default="pt", max_length=2),
    user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        return await fights.challenge(db, user_id=user.user_id, opponent_id=payload.opponent_id, mode=payload.mode, lang=lang)
    except service.GameError as exc:
        _raise(exc)
