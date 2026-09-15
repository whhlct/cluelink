from __future__ import annotations

import hashlib
import json
import math
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace

from backend.core import CoreGraph, GraphNode


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
    minimum_score: float

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

    @abstractmethod
    def score(self, draft: PuzzleDraft) -> tuple[float, dict[str, float]]:
        """Return a 0-100 weighted score and the normalized factors that produced it."""

    def validate_and_score(self, draft: PuzzleDraft) -> PuzzleDraft | None:
        """Reject low-quality candidates and persist the scoring rationale on accepted ones."""
        score, factors = self.score(draft)
        if score < self.minimum_score:
            return None
        quality = {
            **draft.quality,
            "score": {
                "total": round(score, 2),
                "minimum": self.minimum_score,
                "factors": {name: round(value, 4) for name, value in factors.items()},
            },
        }
        return replace(draft, quality=quality)

    def neighbors_of_type(self, node_id: str, entity_type: str) -> list[str]:
        return [
            edge.other_id
            for edge in self.graph.adjacency[node_id]
            if self.graph.nodes[edge.other_id].entity_type == entity_type
        ]

    def popularity_quality(self, node: GraphNode, benchmark: str) -> float:
        """Normalize pageviews against the configured popularity eligibility threshold."""
        threshold = self.anchor_thresholds[node.entity_type] if benchmark == "anchor" else self.intermediate_thresholds[node.entity_type]
        pageviews = node.pageviews or 0
        return min(1.0, math.log1p(pageviews) / math.log1p(max(10, threshold * 10)))

    @staticmethod
    def average(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

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
