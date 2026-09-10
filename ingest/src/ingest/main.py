from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from ingest.wikidata.client import WDQSClient
from ingest.wikidata.movies import ingest_movies
from ingest.wikidata.movie_metadata import ingest_movie_metadata
from ingest.wikidata.people import ingest_people
from ingest.wikidata.relations import discover_relations, finalize_relations
from ingest.wikidata.storage import PostgresWikidataStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest the Wikidata movie graph")
    parser.add_argument(
        "stage",
        choices=["movies", "movie-metadata", "relations", "people", "finalize-relations", "all"],
    )
    return parser.parse_args()


async def run(stage: str) -> None:
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL must be set before running the Wikidata ingest")

    async with PostgresWikidataStore(database_url) as store:
        async with WDQSClient() as client:
            if stage in {"movies", "all"}:
                await ingest_movies(client, store)
            if stage in {"movie-metadata", "all"}:
                await ingest_movie_metadata(client, store)
            if stage in {"relations", "all"}:
                await discover_relations(client, store)
            if stage in {"people", "all"}:
                await ingest_people(client, store)
        if stage in {"finalize-relations", "all"}:
            await finalize_relations(store)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(run(parse_args().stage))


if __name__ == "__main__":
    main()
