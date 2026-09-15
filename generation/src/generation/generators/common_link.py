from __future__ import annotations

from generation.generators.base import PuzzleDraft, PuzzleGenerator


class CommonLinkPuzzleGenerator(PuzzleGenerator):
    puzzle_type = "common_link"
    minimum_score = 80.0

    def generate(self, difficulty: str) -> PuzzleDraft | None:
        answer_type = self.random.choice(("person", "movie"))
        clue_type = "movie" if answer_type == "person" else "person"
        answers = list(self.graph.nodes_of_type(answer_type, self.intermediate_thresholds[answer_type]))
        if not answers:
            return None
        answer = self.random.choice(answers)
        clues = [
            self.graph.nodes[edge.other_id]
            for edge in self.graph.adjacency[answer.id]
            if self.graph.nodes[edge.other_id].entity_type == clue_type
            and (self.graph.nodes[edge.other_id].pageviews or 0) >= self.anchor_thresholds[clue_type]
        ]
        if len(clues) < 2:
            return None
        first, second = self.random.sample(clues, 2)
        common = set(self.neighbors_of_type(first.id, answer_type)) & set(self.neighbors_of_type(second.id, answer_type))
        if not common:
            return None
        common_nodes = sorted(
            (self.graph.nodes[node_id] for node_id in common),
            key=lambda node: (node.pageviews or 0),
            reverse=True,
        )
        canonical = common_nodes[0]
        mode = "movie_for_people" if answer_type == "movie" else "person_for_movies"
        public = {
            "mode": mode,
            "clues": [first.payload(), second.payload()],
            "answer_entity_type": answer_type,
            "prompt": f"Find a {answer_type} that links both clues.",
        }
        solution = {
            "canonical_path": [],
            "accepted_answer_ids": [node.id for node in common_nodes],
            "canonical_answer": canonical.payload(),
            "reveal": {"kind": "common_link", "answers": [node.payload() for node in common_nodes]},
        }
        return self.draft(difficulty, public, solution, None, {"answer_count": len(common_nodes)})

    def score(self, draft: PuzzleDraft) -> tuple[float, dict[str, float]]:
        answer = draft.solution_payload["canonical_answer"]
        clues = draft.public_payload["clues"]
        accepted_answers = draft.solution_payload["accepted_answer_ids"]
        assert isinstance(answer, dict)
        assert isinstance(clues, list)
        assert isinstance(accepted_answers, list)
        answer_node = self.graph.nodes[answer["id"]]
        clue_nodes = [self.graph.nodes[clue["id"]] for clue in clues]
        clue_qualities = [self.popularity_quality(node, "anchor") for node in clue_nodes]
        answer_count = len(accepted_answers)
        factors = {
            "canonical_answer_popularity": self.popularity_quality(answer_node, "intermediate"),
            "clue_average_popularity": self.average(clue_qualities),
            "clue_minimum_popularity": min(clue_qualities, default=0.0),
            "answer_specificity": 1 / (1 + 0.2 * max(0, answer_count - 1)),
        }
        score = 100 * (
            0.3 * factors["canonical_answer_popularity"]
            + 0.35 * factors["clue_average_popularity"]
            + 0.15 * factors["clue_minimum_popularity"]
            + 0.2 * factors["answer_specificity"]
        )
        return score, factors
