from __future__ import annotations

from generation.generators.base import PuzzleDraft, PuzzleGenerator


class HiddenEntityPuzzleGenerator(PuzzleGenerator):
    puzzle_type = "hidden_entity"

    def generate(self, difficulty: str) -> PuzzleDraft | None:
        answer_type = self.random.choice(("person", "movie"))
        clue_type = "movie" if answer_type == "person" else "person"
        answers = list(self.graph.nodes_of_type(answer_type, self.anchor_thresholds[answer_type]))
        if not answers:
            return None
        answer = self.random.choice(answers)
        clues = [
            self.graph.nodes[edge.other_id]
            for edge in self.graph.adjacency[answer.id]
            if self.graph.nodes[edge.other_id].entity_type == clue_type
            and (self.graph.nodes[edge.other_id].pageviews or 0) >= self.intermediate_thresholds[clue_type]
        ]
        clue_count = 3 if answer_type == "person" else 2
        if len(clues) < clue_count:
            return None
        selected = self.random.sample(clues, clue_count)
        candidates = set(self.neighbors_of_type(selected[0].id, answer_type))
        for clue in selected[1:]:
            candidates.intersection_update(self.neighbors_of_type(clue.id, answer_type))
        if candidates != {answer.id}:
            return None
        mode = "person_from_movies" if answer_type == "person" else "movie_from_people"
        public = {
            "mode": mode,
            "clues": [node.payload() for node in selected],
            "answer_entity_type": answer_type,
            "prompt": f"Which {answer_type} links all of these clues?",
        }
        solution = {
            "canonical_path": [],
            "accepted_answer_ids": [answer.id],
            "canonical_answer": answer.payload(),
            "reveal": {"kind": "answer", "answers": [answer.payload()]},
        }
        return self.draft(difficulty, public, solution, None, {"clue_count": clue_count, "unique": True})
