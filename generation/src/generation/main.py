from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import select

from backend.core import CoreGraph, Database
from backend.models import GenerationRunRow, PuzzleRow, PuzzleSolutionRow
from generation.generators import (
    CommonLinkPuzzleGenerator,
    ConnectionPuzzleGenerator,
    HiddenEntityPuzzleGenerator,
    PuzzleDraft,
    PuzzleGenerator,
)


GENERATION_VERSION = "v1"
DIFFICULTIES = ("easy", "medium", "hard")
GENERATOR_TYPES: tuple[type[PuzzleGenerator], ...] = (
    ConnectionPuzzleGenerator,
    HiddenEntityPuzzleGenerator,
    CommonLinkPuzzleGenerator,
)


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
            score = draft.quality.get("score", {})
            assert isinstance(score, dict)
            factors = score.get("factors", {})
            assert isinstance(factors, dict)
            session.add(PuzzleRow(
                id=puzzle_id, puzzle_type=draft.puzzle_type, difficulty=draft.difficulty, status="published",
                public_payload=draft.public_payload, policy=draft.policy, generation_version=GENERATION_VERSION,
                prompt_fingerprint=draft.fingerprint, created_at=now,
            ))
            session.add(PuzzleSolutionRow(
                puzzle_id=puzzle_id, solution_payload=draft.solution_payload,
                optimal_moves=draft.optimal_moves, quality=draft.quality,
                final_score=float(score["total"]), score_factors=factors,
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

        random_source = random.Random(seed)
        generators = {
            generator_type.puzzle_type: generator_type(graph, random_source)
            for generator_type in GENERATOR_TYPES
        }
        drafts: list[PuzzleDraft] = []
        fingerprints = set(existing_fingerprints)
        rejected = 0
        for puzzle_type, generator in generators.items():
            for difficulty in DIFFICULTIES:
                created = 0
                attempts = 0
                while created < count and attempts < count * 500:
                    attempts += 1
                    candidate = generator.generate(difficulty)
                    draft = generator.validate_and_score(candidate) if candidate is not None else None
                    if draft is None or draft.fingerprint in fingerprints:
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
