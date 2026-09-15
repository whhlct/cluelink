from __future__ import annotations

from generation.generators.base import PuzzleDraft, PuzzleGenerator


PATH_LENGTHS = {"easy": {2}, "medium": {3}, "hard": {4, 5}}


class ConnectionPuzzleGenerator(PuzzleGenerator):
    puzzle_type = "connection"

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
