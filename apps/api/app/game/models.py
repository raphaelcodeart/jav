"""Le tabelle del gioco, nello schema `game` (vedi __init__.py): mai una FK
verso il gestionale."""

import uuid
from datetime import datetime
from typing import ClassVar

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, MetaData, SmallInteger, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.db import NAMING_CONVENTION, utcnow

SCHEMA = "game"


class GameBase(DeclarativeBase):
    """La base del gioco: una MetaData sua, nello schema `game`. Non è
    app.core.db.Base: create_all e le migrazioni del gestionale non la
    vedono, e viceversa."""

    metadata = MetaData(schema=SCHEMA, naming_convention=NAMING_CONVENTION)
    type_annotation_map: ClassVar[dict] = {datetime: DateTime(timezone=True)}


class GamePlayer(GameBase):
    """Un giocatore. `user_id` è l'account di jav, senza chiave esterna: il
    nome e il club sono una copia in testo, per la classifica."""

    __tablename__ = "players"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    club_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    #: XP dei quiz (Dojo Academy) e della carriera (Judo Career): la
    #: classifica è la somma.
    quiz_xp: Mapped[int] = mapped_column(BigInteger, default=0)
    career_xp: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class GameQuizAttempt(GameBase):
    """Un tentativo a un quiz o a un esame. Le domande scelte e le risposte
    date stanno qui (`questions`, `answers`): il browser non riceve mai la
    risposta giusta prima di aver risposto."""

    __tablename__ = "quiz_attempts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("game.players.id", ondelete="CASCADE"), index=True)
    quiz_id: Mapped[str] = mapped_column(String(40), index=True)
    lang: Mapped[str] = mapped_column(String(2), default="pt")
    #: [{"id": "h01", "order": [2, 0, 1, 3]}]: le domande e l'ordine delle risposte mostrato.
    questions: Mapped[list] = mapped_column(JSONB, default=list)
    #: {"h01": {"choice": 1, "correct": true, "points": 14, "ms": 3200}}
    answers: Mapped[dict] = mapped_column(JSONB, default=dict)
    score: Mapped[int] = mapped_column(Integer, default=0)
    max_score: Mapped[int] = mapped_column(Integer, default=0)
    correct: Mapped[int] = mapped_column(SmallInteger, default=0)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    xp_earned: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)


class GameBeltExam(GameBase):
    """Un esame di cintura superato nel gioco (Dojo Academy). Sblocca la
    cintura nella carriera simulata: è una cintura del gioco, non quella
    vera del judoca."""

    __tablename__ = "belt_exams"
    __table_args__ = (UniqueConstraint("player_id", "belt", name="uq_belt_exams_player_belt"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("game.players.id", ondelete="CASCADE"), index=True)
    belt: Mapped[str] = mapped_column(String(16))
    score_pct: Mapped[int] = mapped_column(SmallInteger)
    passed_at: Mapped[datetime] = mapped_column(default=utcnow)


class GameCareer(GameBase):
    """La partita di Judo Career: lo stato intero della simulazione (il
    personaggio, il suo club inventato, gli atleti inventati, il
    calendario...) come JSON. Lo calcola il browser; qui si salva."""

    __tablename__ = "careers"

    player_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("game.players.id", ondelete="CASCADE"), primary_key=True)
    state: Mapped[dict] = mapped_column(JSONB, default=dict)
    #: La settimana di gioco e la cintura del personaggio, per la classifica e i controlli.
    week: Mapped[int] = mapped_column(Integer, default=0)
    belt: Mapped[str] = mapped_column(String(16), default="WHITE")
    saves: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
