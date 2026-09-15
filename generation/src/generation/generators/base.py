from __future__ import annotations

import hashlib
import json
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass

from backend.core import CoreGraph


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


class PuzzleGenerator(ABC):
    """Shared graph eligibility, policy, and draft construction for one puzzle type."""

    puzzle_type: str

    def __init__(self, graph: CoreGraph, random_source: random.Random) -> None:
        self.graph = graph
        self.random = random_source
        self.anchor_thresholds = {
            entity_type: graph.percentile(entity_type, 0.75)
            for entity_type in ("person", "movie")
        }
        self.intermediate_thresholds = {
            entity_type: graph.percentile(entity_type, 0.5)
            for entity_type in ("person", "movie")
        }

    @abstractmethod
    def generate(self, difficulty: str) -> PuzzleDraft | None:
        """Return one validated puzzle candidate, or None when the sample is invalid."""

    def neighbors_of_type(self, node_id: str, entity_type: str) -> list[str]:
        return [
            edge.other_id
            for edge in self.graph.adjacency[node_id]
            if self.graph.nodes[edge.other_id].entity_type == entity_type
        ]

    def draft(
        self,
        difficulty: str,
        public_payload: dict[str, object],
        solution_payload: dict[str, object],
        optimal_moves: int | None,
        quality: dict[str, object],
    ) -> PuzzleDraft:
        fingerprint = hashlib.sha256(json.dumps(public_payload, sort_keys=True).encode()).hexdigest()
        policy: dict[str, object] = {
            "max_guesses": None if self.puzzle_type == "connection" else 3,
            "time_limit_seconds": None,
            "hint_policy": "progressive",
        }
        return PuzzleDraft(
            self.puzzle_type,
            difficulty,
            public_payload,
            policy,
            solution_payload,
            optimal_moves,
            quality,
            fingerprint,
        )
