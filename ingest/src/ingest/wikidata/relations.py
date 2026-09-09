from __future__ import annotations

import hashlib
import logging
from collections.abc import AsyncIterator, Iterable, Iterator

from domain import Relation
from domain.enums import RelationType, Source
from ingest.wikidata.client import WDQSClient
from ingest.wikidata.config import RELATION_BATCH_SIZE
from ingest.wikidata.models import WikidataRelationship, qid_from_entity_uri
from ingest.wikidata.queries import cast_member_query, director_query
from ingest.wikidata.storage import PostgresWikidataStore


logger = logging.getLogger(__name__)


def parse_relation_bindings(
    bindings: list[dict[str, dict[str, str]]], relation_type: RelationType, source_relation_id: str
) -> list[WikidataRelationship]:
    relationships: list[WikidataRelationship] = []
    skipped = 0

    for binding in bindings:
        try:
            movie_qid = qid_from_entity_uri(binding["movie"]["value"])
            person_qid = qid_from_entity_uri(binding["person"]["value"])
        except (KeyError, ValueError):
            skipped += 1
            continue

        relationships.append(WikidataRelationship(
            movie_qid=movie_qid,
            person_qid=person_qid,
            relation_type=relation_type,
            source_relation_id=source_relation_id,
        ))

    if skipped:
        logger.warning(
            "Skipped %d %s bindings with non-entity movie or person values",
            skipped,
            source_relation_id,
        )

    return relationships


async def discover_relations(client: WDQSClient, store: PostgresWikidataStore, batch_size: int = RELATION_BATCH_SIZE) -> None:
    batch_number = 0
    async for movie_batch in _async_batches(store.iter_selected_movie_qids(), batch_size):
        batch_number += 1
        batch_key = hashlib.sha256(",".join(movie_batch).encode()).hexdigest()
        if await store.relation_batch_complete(batch_key):
            continue
        logger.info("Starting relation batch %d (%d movies)", batch_number, len(movie_batch))
        cast = parse_relation_bindings(await client.query(cast_member_query(movie_batch)), RelationType.ACTED_IN, "P161")
        directors = parse_relation_bindings(await client.query(director_query(movie_batch)), RelationType.DIRECTED, "P57")
        await store.upsert_raw_relationships([*cast, *directors])
        await store.mark_relation_batch_complete(batch_key)
        logger.info("Completed relation batch %d: %d cast, %d directors", batch_number, len(cast), len(directors))


async def finalize_relations(store: PostgresWikidataStore) -> None:
    inserted = skipped = 0
    async for raw in store.iter_raw_relationships():
        movie_id = await store.entity_id_for_wikidata_qid(raw.movie_qid)
        person_id = await store.entity_id_for_wikidata_qid(raw.person_qid)
        if movie_id is None or person_id is None:
            skipped += 1
            continue
        relation = Relation(person_id, movie_id, raw.relation_type, Source.WIKIDATA, raw.source_relation_id)
        if await store.upsert_relation(relation):
            inserted += 1
        else:
            skipped += 1
    logger.info("Finalized relations: %d inserted, %d skipped", inserted, skipped)


async def _async_batches(values: AsyncIterator[str], size: int) -> AsyncIterator[list[str]]:
    batch: list[str] = []
    async for value in values:
        batch.append(value)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch
