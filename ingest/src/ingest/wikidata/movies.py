from __future__ import annotations

import logging

from domain import Entity, EntityMetrics, ExternalId
from domain.enums import EntityType
from ingest.wikidata.client import WDQSClient
from ingest.wikidata.config import MIN_MOVIE_SITELINKS, MOVIE_END_YEAR, MOVIE_START_YEAR
from ingest.wikidata.models import WikidataMovieRecord, qid_from_entity_uri
from ingest.wikidata.queries import movie_query, movies_without_release_date_query
from ingest.wikidata.storage import PostgresWikidataStore


logger = logging.getLogger(__name__)


def parse_movie_bindings(
    bindings: list[dict[str, dict[str, str]]], min_sitelinks: int = MIN_MOVIE_SITELINKS
) -> list[WikidataMovieRecord]:
    movies = []
    for binding in bindings:
        sitelinks = int(binding["sitelinks"]["value"])
        if sitelinks >= min_sitelinks:
            movies.append(WikidataMovieRecord(
                qid=qid_from_entity_uri(binding["movie"]["value"]),
                label=binding["label"]["value"],
                sitelink_count=sitelinks,
            ))
    return movies


async def ingest_movies(
    client: WDQSClient,
    store: PostgresWikidataStore,
    start_year: int = MOVIE_START_YEAR,
    end_year: int = MOVIE_END_YEAR,
    min_sitelinks: int = MIN_MOVIE_SITELINKS,
) -> None:
    for year in range(start_year, end_year):
        stage_key = f"release-year-{year}"
        if await store.movie_stage_complete(stage_key):
            continue
        logger.info("Starting movie release-year range %d-%d", year, year + 1)
        movies = parse_movie_bindings(await client.query(movie_query(year, year + 1, min_sitelinks)), min_sitelinks)
        inserted = 0
        for movie in movies:
            entity_id = store.canonical_id_for_qid(movie.qid)
            inserted += await store.upsert_entity(Entity(
                id=entity_id, name=movie.label, entity_type=EntityType.MOVIE,
                external_ids=[ExternalId(source="wikidata", value=movie.qid)],
            ))
            await store.upsert_metrics(EntityMetrics(entity_id=entity_id, sitelink_count=movie.sitelink_count))
            await store.mark_movie_selected(movie.qid, entity_id)
        await store.mark_movie_stage_complete(stage_key)
        logger.info("Completed movie range %d-%d: %d returned, %d inserted", year, year + 1, len(movies), inserted)

    fallback_stage = "without-release-date"
    if not await store.movie_stage_complete(fallback_stage):
        movies = parse_movie_bindings(await client.query(movies_without_release_date_query(min_sitelinks)), min_sitelinks)
        for movie in movies:
            entity_id = store.canonical_id_for_qid(movie.qid)
            await store.upsert_entity(Entity(id=entity_id, name=movie.label, entity_type=EntityType.MOVIE, external_ids=[ExternalId(source="wikidata", value=movie.qid)]))
            await store.upsert_metrics(EntityMetrics(entity_id=entity_id, sitelink_count=movie.sitelink_count))
            await store.mark_movie_selected(movie.qid, entity_id)
        await store.mark_movie_stage_complete(fallback_stage)
        logger.info("Completed movies without release dates: %d returned", len(movies))
