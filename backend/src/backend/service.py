from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from backend.core import CoreGraph, Database
from backend.models import GameEventRow, GameSessionRow, PuzzleRow, PuzzleSolutionRow


class GameError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail


class GameService:
    def __init__(self, database: Database, graph: CoreGraph) -> None:
        self.database = database
        self.graph = graph

    async def create_session(self, puzzle_type: str | None, difficulty: str | None) -> dict[str, object]:
        async with self.database.sessions.begin() as session:
            query = select(PuzzleRow).where(PuzzleRow.status == "published")
            if puzzle_type:
                query = query.where(PuzzleRow.puzzle_type == puzzle_type)
            if difficulty:
                query = query.where(PuzzleRow.difficulty == difficulty)
            puzzle = await session.scalar(query.order_by(func.random()).limit(1))
            if puzzle is None:
                raise GameError(404, "No published puzzle matches the requested filters")
            return await self._create_session(session, puzzle)

    async def create_session_for_puzzle(self, puzzle_id: str) -> dict[str, object]:
        async with self.database.sessions.begin() as session:
            puzzle = await session.get(PuzzleRow, puzzle_id)
            if puzzle is None:
                raise GameError(404, "Puzzle not found")
            if puzzle.status != "published":
                raise GameError(422, "Only published puzzles can be played")
            return await self._create_session(session, puzzle)

    async def admin_puzzle_counts(self) -> list[dict[str, object]]:
        async with self.database.sessions() as session:
            rows = await session.execute(
                select(PuzzleRow.puzzle_type, PuzzleRow.difficulty, func.count(PuzzleRow.id).label("count"))
                .group_by(PuzzleRow.puzzle_type, PuzzleRow.difficulty)
                .order_by(PuzzleRow.puzzle_type, PuzzleRow.difficulty)
            )
            return [
                {"puzzle_type": row.puzzle_type, "difficulty": row.difficulty, "count": row.count}
                for row in rows
            ]

    async def admin_puzzles(self, puzzle_type: str, difficulty: str) -> list[dict[str, object]]:
        async with self.database.sessions() as session:
            puzzles = (await session.scalars(
                select(PuzzleRow)
                .where(PuzzleRow.puzzle_type == puzzle_type, PuzzleRow.difficulty == difficulty)
                .order_by(PuzzleRow.created_at.desc())
            )).all()
            details: list[dict[str, object]] = []
            for puzzle in puzzles:
                solution = await session.get(PuzzleSolutionRow, puzzle.id)
                assert solution is not None
                payload = puzzle.public_payload
                sources = [payload["start"]] if puzzle.puzzle_type == "connection" else payload.get("clues", [])
                target = payload["target"] if puzzle.puzzle_type == "connection" else solution.solution_payload["canonical_answer"]
                details.append({
                    "id": puzzle.id,
                    "status": puzzle.status,
                    "source_entities": sources,
                    "target_entity": target,
                })
            return details

    async def get_session(self, session_id: str) -> dict[str, object]:
        async with self.database.sessions.begin() as session:
            game, puzzle = await self._locked_game(session, session_id)
            await self._expire_if_needed(session, game, puzzle)
            return await self._payload(session, game, puzzle)

    async def move(self, session_id: str, entity_id: str) -> dict[str, object]:
        async with self.database.sessions.begin() as session:
            game, puzzle = await self._locked_game(session, session_id)
            await self._expire_if_needed(session, game, puzzle)
            self._require_active(game, puzzle)
            if puzzle.puzzle_type != "connection":
                raise GameError(422, "Moves are only valid for connection puzzles")
            edge = self.graph.edge(game.current_entity_id or "", entity_id)
            if edge is None:
                raise GameError(422, "The proposed entity is not connected to the current entity")
            game.current_entity_id = entity_id
            game.move_count += 1
            game.updated_at = datetime.now(timezone.utc)
            await self._event(session, game, "move", {"entity_id": entity_id, "relation_type": edge.relation_type})
            if entity_id == puzzle.public_payload["target"]["id"]:
                await self._win(session, game, puzzle)
            return await self._payload(session, game, puzzle, last_relation=edge.relation_type)

    async def guess(self, session_id: str, entity_id: str) -> dict[str, object]:
        async with self.database.sessions.begin() as session:
            game, puzzle = await self._locked_game(session, session_id)
            await self._expire_if_needed(session, game, puzzle)
            self._require_active(game, puzzle)
            if puzzle.puzzle_type == "connection":
                raise GameError(422, "Connection puzzles use moves, not guesses")
            candidate = self.graph.nodes.get(entity_id)
            if candidate is None:
                raise GameError(422, "The proposed entity does not exist in the playable graph")
            expected_type = puzzle.public_payload.get("answer_entity_type")
            if candidate.entity_type != expected_type:
                raise GameError(422, f"This puzzle requires a {expected_type} guess")
            if entity_id in game.guessed_entity_ids:
                raise GameError(409, "That entity was already guessed")
            solution = await session.get(PuzzleSolutionRow, puzzle.id)
            assert solution is not None
            answers = set(solution.solution_payload["accepted_answer_ids"])
            game.guessed_entity_ids = [*game.guessed_entity_ids, entity_id]
            game.guess_count += 1
            game.updated_at = datetime.now(timezone.utc)
            correct = entity_id in answers
            await self._event(session, game, "guess", {"entity_id": entity_id, "correct": correct})
            if correct:
                await self._win(session, game, puzzle)
            else:
                game.wrong_guess_count += 1
                maximum = puzzle.policy.get("max_guesses")
                if maximum is not None and game.guess_count >= int(maximum):
                    await self._fail(session, game, "failed_guess_limit")
            return await self._payload(session, game, puzzle)

    async def hint(self, session_id: str) -> dict[str, object]:
        async with self.database.sessions.begin() as session:
            game, puzzle = await self._locked_game(session, session_id)
            await self._expire_if_needed(session, game, puzzle)
            self._require_active(game, puzzle)
            solution = await session.get(PuzzleSolutionRow, puzzle.id)
            assert solution is not None
            if puzzle.puzzle_type == "connection":
                path = self.graph.shortest_path(game.current_entity_id or "", puzzle.public_payload["target"]["id"])
                if not path or len(path) < 2:
                    raise GameError(422, "No hint is available from the current position")
                next_node = self.graph.nodes[path[1]]
                hint_payload: dict[str, object] = {"next_entity": next_node.payload()}
                if game.hint_count > 0:
                    hint_payload["relation_type"] = self.graph.edge(path[0], path[1]).relation_type  # type: ignore[union-attr]
            else:
                answer = solution.solution_payload["canonical_answer"]
                hint_payload = {"answer_entity_type": answer["entity_type"]}
                if game.hint_count > 0:
                    hint_payload["answer_initial"] = answer["name"][0]
            game.hint_count += 1
            game.updated_at = datetime.now(timezone.utc)
            await self._event(session, game, "hint", hint_payload)
            result = await self._payload(session, game, puzzle)
            result["hint"] = hint_payload
            return result

    async def give_up(self, session_id: str) -> dict[str, object]:
        async with self.database.sessions.begin() as session:
            game, puzzle = await self._locked_game(session, session_id)
            await self._expire_if_needed(session, game, puzzle)
            self._require_active(game, puzzle)
            await self._fail(session, game, "abandoned")
            return await self._payload(session, game, puzzle)

    async def disable_puzzle(self, puzzle_id: str, reason: str) -> None:
        async with self.database.sessions.begin() as session:
            puzzle = await session.get(PuzzleRow, puzzle_id, with_for_update=True)
            if puzzle is None:
                raise GameError(404, "Puzzle not found")
            puzzle.status = "disabled"
            puzzle.disabled_reason = reason
            puzzle.disabled_at = datetime.now(timezone.utc)

    async def _create_session(self, session, puzzle: PuzzleRow) -> dict[str, object]:
        now = datetime.now(timezone.utc)
        payload = puzzle.public_payload
        game = GameSessionRow(
            id=str(uuid.uuid4()), puzzle_id=puzzle.id, status="active",
            current_entity_id=payload.get("start", {}).get("id") if puzzle.puzzle_type == "connection" else None,
            move_count=0, guess_count=0, wrong_guess_count=0, hint_count=0,
            guessed_entity_ids=[], started_at=now, updated_at=now,
        )
        session.add(game)
        await self._event(session, game, "started", {})
        await session.flush()
        return await self._payload(session, game, puzzle)

    async def _locked_game(self, session, session_id: str) -> tuple[GameSessionRow, PuzzleRow]:
        game = await session.scalar(select(GameSessionRow).where(GameSessionRow.id == session_id).with_for_update())
        if game is None:
            raise GameError(404, "Session not found")
        puzzle = await session.get(PuzzleRow, game.puzzle_id)
        assert puzzle is not None
        return game, puzzle

    def _require_active(self, game: GameSessionRow, puzzle: PuzzleRow) -> None:
        if game.status != "active":
            raise GameError(409, "This game is already finished")
        if puzzle.status != "published":
            raise GameError(409, "This puzzle is no longer playable")

    async def _expire_if_needed(self, session, game: GameSessionRow, puzzle: PuzzleRow) -> None:
        if game.status == "active" and puzzle.status != "published":
            await self._fail(session, game, "puzzle_disabled")
            return
        limit = puzzle.policy.get("time_limit_seconds")
        if game.status == "active" and limit is not None and game.started_at + timedelta(seconds=int(limit)) <= datetime.now(timezone.utc):
            await self._fail(session, game, "expired")

    async def _win(self, session, game: GameSessionRow, puzzle: PuzzleRow) -> None:
        solution = await session.get(PuzzleSolutionRow, puzzle.id)
        assert solution is not None
        optimal = solution.optimal_moves or 0
        if game.hint_count == 0 and game.wrong_guess_count == 0 and (puzzle.puzzle_type != "connection" or game.move_count <= optimal):
            game.stars = 3
        elif game.hint_count <= 1 and game.wrong_guess_count <= 1 and (puzzle.puzzle_type != "connection" or game.move_count <= optimal + 2):
            game.stars = 2
        else:
            game.stars = 1
        game.status = "won"
        game.completed_at = game.updated_at = datetime.now(timezone.utc)
        await self._event(session, game, "won", {"stars": game.stars})

    async def _fail(self, session, game: GameSessionRow, reason: str) -> None:
        game.status = "failed"
        game.failure_reason = reason
        game.completed_at = game.updated_at = datetime.now(timezone.utc)
        await self._event(session, game, "failed", {"reason": reason})

    async def _event(self, session, game: GameSessionRow, event_type: str, payload: dict[str, object]) -> None:
        sequence = await session.scalar(select(func.coalesce(func.max(GameEventRow.sequence), 0)).where(GameEventRow.session_id == game.id)) or 0
        session.add(GameEventRow(
            id=str(uuid.uuid4()), session_id=game.id, sequence=sequence + 1,
            event_type=event_type, payload=payload, created_at=datetime.now(timezone.utc),
        ))

    async def _payload(self, session, game: GameSessionRow, puzzle: PuzzleRow, last_relation: str | None = None) -> dict[str, object]:
        terminal = game.status != "active"
        result: dict[str, object] = {
            "session_id": game.id, "status": game.status, "failure_reason": game.failure_reason,
            "puzzle": {"id": puzzle.id, "type": puzzle.puzzle_type, "difficulty": puzzle.difficulty, "payload": puzzle.public_payload},
            "progress": {
                "current_entity": self.graph.nodes[game.current_entity_id].payload() if game.current_entity_id else None,
                "moves": game.move_count, "guesses": game.guess_count,
                "wrong_guesses": game.wrong_guess_count, "hints": game.hint_count,
                "remaining_guesses": None if puzzle.policy.get("max_guesses") is None else max(0, int(puzzle.policy["max_guesses"]) - game.guess_count),
                "stars": game.stars,
                "elapsed_seconds": int(((game.completed_at or datetime.now(timezone.utc)) - game.started_at).total_seconds()),
            },
        }
        if last_relation:
            result["last_relation"] = last_relation
        if terminal:
            solution = await session.get(PuzzleSolutionRow, puzzle.id)
            assert solution is not None
            result["solution"] = solution.solution_payload["reveal"]
        return result
