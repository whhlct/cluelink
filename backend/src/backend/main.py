from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.core import CoreGraph, Database
from backend.service import GameError, GameService


class StartRequest(BaseModel):
    puzzle_type: str | None = None
    difficulty: str | None = None


class EntityRequest(BaseModel):
    entity_id: str


class DisableRequest(BaseModel):
    reason: str


def create_app() -> FastAPI:
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL must be configured")
        database = Database(database_url)
        async with database.sessions() as session:
            graph = await CoreGraph.load(session)
        app.state.games = GameService(database, graph)
        yield
        await database.dispose()

    app = FastAPI(title="Cluelink Gameplay API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")],
        allow_methods=["*"], allow_headers=["*"],
    )

    def games() -> GameService:
        return app.state.games

    def api_error(error: GameError) -> HTTPException:
        return HTTPException(error.status_code, error.detail)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/sessions")
    async def start(request: StartRequest) -> dict[str, object]:
        try:
            return await games().create_session(request.puzzle_type, request.difficulty)
        except GameError as error:
            raise api_error(error)

    @app.get("/v1/sessions/{session_id}")
    async def get_session(session_id: str) -> dict[str, object]:
        try:
            return await games().get_session(session_id)
        except GameError as error:
            raise api_error(error)

    @app.post("/v1/sessions/{session_id}/moves")
    async def move(session_id: str, request: EntityRequest) -> dict[str, object]:
        try:
            return await games().move(session_id, request.entity_id)
        except GameError as error:
            raise api_error(error)

    @app.post("/v1/sessions/{session_id}/guesses")
    async def guess(session_id: str, request: EntityRequest) -> dict[str, object]:
        try:
            return await games().guess(session_id, request.entity_id)
        except GameError as error:
            raise api_error(error)

    @app.post("/v1/sessions/{session_id}/hints")
    async def hint(session_id: str) -> dict[str, object]:
        try:
            return await games().hint(session_id)
        except GameError as error:
            raise api_error(error)

    @app.post("/v1/sessions/{session_id}/give-up")
    async def give_up(session_id: str) -> dict[str, object]:
        try:
            return await games().give_up(session_id)
        except GameError as error:
            raise api_error(error)

    @app.get("/v1/entities")
    async def entities(query: str = Query(min_length=1), entity_type: str | None = None) -> list[dict[str, object]]:
        return [node.payload() for node in games().graph.search(query, entity_type)]

    @app.get("/v1/admin/puzzles")
    async def admin_puzzle_counts() -> list[dict[str, object]]:
        return await games().admin_puzzle_counts()

    @app.get("/v1/admin/puzzles/{puzzle_type}/{difficulty}")
    async def admin_puzzles(puzzle_type: str, difficulty: str) -> list[dict[str, object]]:
        return await games().admin_puzzles(puzzle_type, difficulty)

    @app.delete("/v1/admin/puzzles")
    async def admin_clear_all_puzzles() -> dict[str, int]:
        return {"deleted_puzzles": await games().clear_puzzles()}

    @app.delete("/v1/admin/puzzles/{puzzle_type}/{difficulty}")
    async def admin_clear_puzzles(puzzle_type: str, difficulty: str) -> dict[str, int]:
        return {"deleted_puzzles": await games().clear_puzzles(puzzle_type, difficulty)}

    @app.post("/v1/admin/puzzles/{puzzle_id}/sessions")
    async def admin_start_puzzle(puzzle_id: str) -> dict[str, object]:
        try:
            return await games().create_session_for_puzzle(puzzle_id)
        except GameError as error:
            raise api_error(error)

    @app.post("/v1/admin/puzzles/{puzzle_id}/disable", status_code=204)
    async def disable(puzzle_id: str, request: DisableRequest, x_admin_token: str | None = Header(default=None)) -> None:
        expected = os.environ.get("ADMIN_TOKEN")
        if not expected or not secrets.compare_digest(expected, x_admin_token or ""):
            raise HTTPException(403, "Invalid admin token")
        try:
            await games().disable_puzzle(puzzle_id, request.reason)
        except GameError as error:
            raise api_error(error)

    return app


app = create_app()


def run() -> None:
    uvicorn.run("backend.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), reload=True)
