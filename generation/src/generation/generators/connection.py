from __future__ import annotations

from generation.generators.base import PuzzleDraft, PuzzleGenerator


PATH_LENGTHS = {"easy": {2}, "medium": {3}, "hard": {4, 5}}


class ConnectionPuzzleGenerator(PuzzleGenerator):
    puzzle_type = "connection"
    minimum_score = 82.0

    def generate(self, difficulty: str) -> PuzzleDraft | None:
        anchors = [
            node
            for entity_type in ("person", "movie")
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
            "mode": "connection",
            "start": start.payload(),
            "target": target.payload(),
            "prompt": f"Connect {start.name} to {target.name} through film credits.",
        }
        solution = {
            "canonical_path": [node.payload() for node in nodes],
            "accepted_answer_ids": [],
            "canonical_answer": target.payload(),
            "reveal": {"kind": "path", "path": [node.payload() for node in nodes], "relations": relations},
        }
        return self.draft(difficulty, public, solution, len(path) - 1, {"path_length": len(path) - 1})

    def score(self, draft: PuzzleDraft) -> tuple[float, dict[str, float]]:
        path = draft.solution_payload["canonical_path"]
        assert isinstance(path, list)
        nodes = [self.graph.nodes[node["id"]] for node in path]
        distance = len(nodes) - 1
        allowed_distances = PATH_LENGTHS[draft.difficulty]
        distance_quality = (distance - min(allowed_distances) + 1) / (max(allowed_distances) - min(allowed_distances) + 1)
        endpoint_quality = self.average([self.popularity_quality(nodes[0], "anchor"), self.popularity_quality(nodes[-1], "anchor")])
        intermediate_qualities = [self.popularity_quality(node, "intermediate") for node in nodes[1:-1]]
        intermediate_average = self.average(intermediate_qualities)
        intermediate_minimum = min(intermediate_qualities, default=0.0)
        factors = {
            "distance": distance_quality,
            "endpoint_popularity": endpoint_quality,
            "intermediate_average_popularity": intermediate_average,
            "intermediate_minimum_popularity": intermediate_minimum,
        }
        score = 100 * (
            0.35 * factors["distance"]
            + 0.25 * factors["endpoint_popularity"]
            + 0.25 * factors["intermediate_average_popularity"]
            + 0.15 * factors["intermediate_minimum_popularity"]
        )
        return score, factors
