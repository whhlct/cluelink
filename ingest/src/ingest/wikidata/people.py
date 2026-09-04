from __future__ import annotations

import logging

from domain import Entity, EntityMetrics, ExternalId
from domain.enums import EntityType
from ingest.wikidata.client import WDQSClient
from ingest.wikidata.config import PERSON_BATCH_SIZE
from ingest.wikidata.models import WikidataPersonRecord, qid_from_entity_uri
from ingest.wikidata.queries import person_metadata_query
from ingest.wikidata.relations import _async_batches
from ingest.wikidata.storage import PostgresWikidataStore


logger = logging.getLogger(__name__)


def parse_person_bindings(bindings: list[dict[str, dict[str, str]]]) -> list[WikidataPersonRecord]:
    people = []
    for binding in bindings:
        label = binding.get("label", {}).get("value")
        if not label:
            logger.warning("Skipping person without an English label: %s", binding.get("person", {}))
            continue
        sitelinks = binding.get("sitelinks", {}).get("value")
        people.append(WikidataPersonRecord(
            qid=qid_from_entity_uri(binding["person"]["value"]), label=label,
            sitelink_count=int(sitelinks) if sitelinks is not None else None,
        ))
    return people


async def ingest_people(client: WDQSClient, store: PostgresWikidataStore, batch_size: int = PERSON_BATCH_SIZE) -> None:
    batch_number = 0
    async for qids in _async_batches(store.iter_pending_person_qids(), batch_size):
        batch_number += 1
        logger.info("Starting person batch %d (%d people)", batch_number, len(qids))
        people = parse_person_bindings(await client.query(person_metadata_query(qids)))
        for person in people:
            entity_id = store.canonical_id_for_qid(person.qid)
            await store.upsert_entity(Entity(id=entity_id, name=person.label, entity_type=EntityType.PERSON, external_ids=[ExternalId(source="wikidata", value=person.qid)]))
            if person.sitelink_count is not None:
                await store.upsert_metrics(EntityMetrics(entity_id=entity_id, sitelink_count=person.sitelink_count))
        await store.mark_people_processed(qids)
        logger.info("Completed person batch %d: %d entities inserted or updated", batch_number, len(people))
