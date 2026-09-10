from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable
from urllib.parse import urlsplit

from domain.enums import EntityType
from ingest.wikidata.client import WDQSClient
from ingest.wikidata.config import WIKIPEDIA_SITELINK_BATCH_SIZE
from ingest.wikidata.models import qid_from_entity_uri
from ingest.wikidata.queries import enwiki_sitelink_query
from ingest.wikidata.relations import _async_batches
from ingest.wikidata.storage import PostgresWikidataStore


logger = logging.getLogger(__name__)
_ENTITY_TYPES = (EntityType.MOVIE, EntityType.PERSON)


def parse_enwiki_sitelink_bindings(
    bindings: Iterable[dict[str, dict[str, str]]],
) -> dict[str, str]:
    sitelinks: dict[str, str] = {}
    for binding in bindings:
        try:
            qid = qid_from_entity_uri(binding["entity"]["value"])
            article_url = urlsplit(binding["article"]["value"])
            if article_url.netloc != "en.wikipedia.org" or not article_url.path.startswith("/wiki/"):
                raise ValueError("not an English Wikipedia article URL")
            title = article_url.path.removeprefix("/wiki/")
            if not title:
                raise ValueError("article URL has no title")
            sitelinks[qid] = title
        except (KeyError, ValueError):
            logger.warning("Skipping invalid English Wikipedia sitelink binding: %s", binding)
    return sitelinks


async def ingest_wikipedia_sitelinks(
    client: WDQSClient,
    store: PostgresWikidataStore,
    batch_size: int = WIKIPEDIA_SITELINK_BATCH_SIZE,
) -> None:
    batch_number = 0
    async for entity_qids in _async_batches(store.iter_wikidata_entity_qids(_ENTITY_TYPES), batch_size):
        batch_number += 1
        batch_key = hashlib.sha256(",".join(entity_qids).encode()).hexdigest()
        if await store.wikipedia_sitelink_batch_complete(batch_key):
            continue

        logger.info("Starting English Wikipedia sitelink batch %d (%d entities)", batch_number, len(entity_qids))
        sitelinks = parse_enwiki_sitelink_bindings(
            await client.query(enwiki_sitelink_query(entity_qids))
        )
        await store.upsert_enwiki_sitelinks(sitelinks)
        await store.mark_wikipedia_sitelink_batch_complete(batch_key)
        logger.info("Completed English Wikipedia sitelink batch %d: %d sitelinks", batch_number, len(sitelinks))
