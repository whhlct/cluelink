from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class GameBase(DeclarativeBase):
    pass


class PuzzleRow(GameBase):
    __tablename__ = "puzzles"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    puzzle_type: Mapped[str] = mapped_column(String, nullable=False)
    difficulty: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="published")
    public_payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    policy: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    generation_version: Mapped[str] = mapped_column(String, nullable=False)
    prompt_fingerprint: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    disabled_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PuzzleSolutionRow(GameBase):
    __tablename__ = "puzzle_solutions"

    puzzle_id: Mapped[str] = mapped_column(ForeignKey("puzzles.id", ondelete="CASCADE"), primary_key=True)
    solution_payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    optimal_moves: Mapped[int | None] = mapped_column(Integer)
    quality: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class GenerationRunRow(GameBase):
    __tablename__ = "generation_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    config: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    stats: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GameSessionRow(GameBase):
    __tablename__ = "game_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    puzzle_id: Mapped[str] = mapped_column(ForeignKey("puzzles.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    failure_reason: Mapped[str | None] = mapped_column(String)
    current_entity_id: Mapped[str | None] = mapped_column(String)
    move_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    guess_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wrong_guess_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hint_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    guessed_entity_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    stars: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GameEventRow(GameBase):
    __tablename__ = "game_events"
    __table_args__ = (UniqueConstraint("session_id", "sequence", name="uq_game_events_session_sequence"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("game_sessions.id", ondelete="CASCADE"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
