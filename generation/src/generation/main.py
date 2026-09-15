from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import select

from backend.core import CoreGraph, Database, GraphNode
from backend.models import GenerationRunRow, PuzzleRow, PuzzleSolutionRow


GENERATION_VERSION = "v1"
PUZZLE_TYPES = ("connection", "hidden_entity", "common_link")
DIFFICULTIES = ("easy", "medium", "hard")
PATH_LENGTHS = {"easy": {2}, "medium": {3}, "hard": {4, 5}}


@dataclass(frozen=True)
class PuzzleDraft:
    puzzle_type: str
    difficulty: str
    public_payload: dict[str, object]
    policy: dict[str, object]
    solution_payload: dict[str, object]
    optimal_moves: int | None
    quality: dict[str, object]
    fingerprint: str


class PuzzleGenerator:
    def __init__(self, graph: CoreGraph, random_source: random.Random) -> None:
        self.graph = graph
        self.random = random_source
        self.anchor_thresholds = {entity_type: graph.percentile(entity_type, 0.75) for entity_type in ("person", "movie")}
        self.intermediate_thresholds = {entity_type: graph.percentile(entity_type, 0.5) for entity_type in ("person", "movie")}

    def generate(self, puzzle_type: str, difficulty: str) -> PuzzleDraft | None:
        if puzzle_type == "connection":
            return self._connection(difficulty)
        if puzzle_type == "hidden_entity":
            return self._hidden_entity(difficulty)
        return self._common_link(difficulty)

    def _connection(self, difficulty: str) -> PuzzleDraft | None:
        anchors = [
            node for entity_type in ("person", "movie")
            for node in self.graph.nodes_of_type(entity_type, self.anchor_thresholds[entity_type])
        ]
        if len(anchors) < 2:
            return None
        start, target = self.random.sample(anchors, 2)
        path = self.graph.shortest_path(start.id, target.id, max_depth=max(PATH_LENGTHS[difficulty]))
        if path is None or len(path) - 1 not in PATH_LENGTHS[difficulty]:
            return None
        nodes = [self.graph.nodes[node_id] for node_id in path]
        if any((node.pageviews or 0) < self.intermediate_thresholds[node.entity_type] for node in nodes[1:-1]):
            return None
        relations = [self.graph.edge(path[index], path[index + 1]).relation_type for index in range(len(path) - 1)]
        public = {
            "mode": "connection", "start": start.payload(), "target": target.payload(),
            "prompt": f"Connect {start.name} to {target.name} through film credits.",
        }
        solution = {
            "canonical_path": [node.payload() for node in nodes],
            "accepted_answer_ids": [],
            "canonical_answer": target.payload(),
            "reveal": {"kind": "path", "path": [node.payload() for node in nodes], "relations": relations},
        }
        return self._draft("connection", difficulty, public, solution, len(path) - 1, {"path_length": len(path) - 1})

    def _hidden_entity(self, difficulty: str) -> PuzzleDraft | None:
        answer_type = self.random.choice(("person", "movie"))
        clue_type = "movie" if answer_type == "person" else "person"
        answers = list(self.graph.nodes_of_type(answer_type, self.anchor_thresholds[answer_type]))
        if not answers:
            return None
        answer = self.random.choice(answers)
        clues = [
            self.graph.nodes[edge.other_id] for edge in self.graph.adjacency[answer.id]
            if self.graph.nodes[edge.other_id].entity_type == clue_type
            and (self.graph.nodes[edge.other_id].pageviews or 0) >= self.intermediate_thresholds[clue_type]
        ]
        clue_count = 3 if answer_type == "person" else 2
        if len(clues) < clue_count:
            return None
        selected = self.random.sample(clues, clue_count)
        candidates = set(self._neighbors_of_type(selected[0].id, answer_type))
        for clue in selected[1:]:
            candidates.intersection_update(self._neighbors_of_type(clue.id, answer_type))
        if candidates != {answer.id}:
            return None
        mode = "person_from_movies" if answer_type == "person" else "movie_from_people"
        public = {
            "mode": mode, "clues": [node.payload() for node in selected],
            "answer_entity_type": answer_type,
            "prompt": f"Which {answer_type} links all of these clues?",
        }
        solution = {
            "canonical_path": [], "accepted_answer_ids": [answer.id], "canonical_answer": answer.payload(),
            "reveal": {"kind": "answer", "answers": [answer.payload()]},
        }
        return self._draft("hidden_entity", difficulty, public, solution, None, {"clue_count": clue_count, "unique": True})

    def _common_link(self, difficulty: str) -> PuzzleDraft | None:
        answer_type = self.random.choice(("person", "movie"))
        clue_type = "movie" if answer_type == "person" else "person"
        answers = list(self.graph.nodes_of_type(answer_type, self.intermediate_thresholds[answer_type]))
        if not answers:
            return None
        answer = self.random.choice(answers)
        clues = [
            self.graph.nodes[edge.other_id] for edge in self.graph.adjacency[answer.id]
            if self.graph.nodes[edge.other_id].entity_type == clue_type
            and (self.graph.nodes[edge.other_id].pageviews or 0) >= self.anchor_thresholds[clue_type]
        ]
        if len(clues) < 2:
            return None
        first, second = self.random.sample(clues, 2)
        common = set(self._neighbors_of_type(first.id, answer_type)) & set(self._neighbors_of_type(second.id, answer_type))
        if not common:
            return None
        common_nodes = sorted((self.graph.nodes[node_id] for node_id in common), key=lambda node: (node.pageviews or 0), reverse=True)
        canonical = common_nodes[0]
        mode = "movie_for_people" if answer_type == "movie" else "person_for_movies"
        public = {
            "mode": mode, "clues": [first.payload(), second.payload()], "answer_entity_type": answer_type,
            "prompt": f"Find a {answer_type} that links both clues.",
        }
        solution = {
            "canonical_path": [], "accepted_answer_ids": [node.id for node in common_nodes],
            "canonical_answer": canonical.payload(),
            "reveal": {"kind": "common_link", "answers": [node.payload() for node in common_nodes]},
        }
        return self._draft("common_link", difficulty, public, solution, None, {"answer_count": len(common_nodes)})

    def _neighbors_of_type(self, node_id: str, entity_type: str) -> list[str]:
        return [edge.other_id for edge in self.graph.adjacency[node_id] if self.graph.nodes[edge.other_id].entity_type == entity_type]

    def _draft(
        self, puzzle_type: str, difficulty: str, public: dict[str, object], solution: dict[str, object],
        optimal_moves: int | None, quality: dict[str, object],
    ) -> PuzzleDraft:
        fingerprint = hashlib.sha256(json.dumps(public, sort_keys=True).encode()).hexdigest()
        policy: dict[str, object] = {"max_guesses": None if puzzle_type == "connection" else 3, "time_limit_seconds": None, "hint_policy": "progressive"}
        return PuzzleDraft(puzzle_type, difficulty, public, policy, solution, optimal_moves, quality, fingerprint)


async def persist_drafts(database: Database, drafts: list[PuzzleDraft], config: dict[str, object]) -> dict[str, int]:
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    inserted = duplicate = 0
    async with database.sessions.begin() as session:
        run = GenerationRunRow(id=run_id, config=config, stats={}, status="running", started_at=now)
        session.add(run)
        for draft in drafts:
            exists = await session.scalar(select(PuzzleRow.id).where(PuzzleRow.prompt_fingerprint == draft.fingerprint))
            if exists:
                duplicate += 1
                continue
            puzzle_id = str(uuid.uuid4())
            session.add(PuzzleRow(
                id=puzzle_id, puzzle_type=draft.puzzle_type, difficulty=draft.difficulty, status="published",
                public_payload=draft.public_payload, policy=draft.policy, generation_version=GENERATION_VERSION,
                prompt_fingerprint=draft.fingerprint, created_at=now,
            ))
            session.add(PuzzleSolutionRow(
                puzzle_id=puzzle_id, solution_payload=draft.solution_payload,
                optimal_moves=draft.optimal_moves, quality=draft.quality,
            ))
            inserted += 1
        run.status = "completed"
        run.stats = {"inserted": inserted, "duplicate": duplicate, "requested": len(drafts)}
        run.completed_at = datetime.now(timezone.utc)
    return {"inserted": inserted, "duplicate": duplicate}


async def generate(count: int, seed: int | None) -> dict[str, int]:
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    database = Database(os.environ["DATABASE_URL"])
    try:
        async with database.sessions() as session:
            graph = await CoreGraph.load(session)
            existing_fingerprints = set((await session.scalars(select(PuzzleRow.prompt_fingerprint))).all())
        generator = PuzzleGenerator(graph, random.Random(seed))
        drafts: list[PuzzleDraft] = []
        fingerprints = set(existing_fingerprints)
        rejected = 0
        for puzzle_type in PUZZLE_TYPES:
            for difficulty in DIFFICULTIES:
                created = 0
                attempts = 0
                while created < count and attempts < count * 500:
                    attempts += 1
                    draft = generator.generate(puzzle_type, difficulty)
                    if draft is None:
                        rejected += 1
                        continue
                    if draft.fingerprint in fingerprints:
                        rejected += 1
                        continue
                    drafts.append(draft)
                    fingerprints.add(draft.fingerprint)
                    created += 1
        result = await persist_drafts(database, drafts, {"count_per_type_difficulty": count, "seed": seed})
        result["rejected"] = rejected
        result["generated"] = len(drafts)
        return result
    finally:
        await database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate validated Cluelink puzzles")
    parser.add_argument("--count", type=int, default=25, help="Puzzles per type and difficulty")
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(generate(args.count, args.seed)), sort_keys=True))
